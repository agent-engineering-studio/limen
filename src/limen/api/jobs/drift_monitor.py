"""Periodic drift monitor — compares recent challenger predictions
against the training-time distribution and emits a retraining signal.

Gated by ``monitoring.enable_drift_monitoring``. On a freshly migrated
DB it logs and returns 0 — the empty-state behaviour is the same as
the EGMS sync.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.data.repos.model_runs_repo import recent_for_role
from limen.data.repos.training_samples_repo import fetch_samples
from limen.ml.dataset import valore_assente
from limen.ml.monitoring import RetrainingTrigger
from limen.ml.monitoring.drift import DriftReport, make_report, peggiore

log = get_logger(__name__)


def _misurati(valori: Iterable[float | None], assente: float) -> list[float]:
    pieni = (assente if v is None else float(v) for v in valori)
    return [v for v in pieni if not math.isnan(v)]


async def run_drift_monitor_job(deps: AppDependencies) -> int:
    """One drift tick. Returns 1 if a retrain trigger fired, else 0."""
    if not deps.settings.monitoring.enable_drift_monitoring:
        log.debug("job.drift.skip_disabled")
        return 0

    training_samples = await fetch_samples()
    if not training_samples:
        log.info("job.drift.skip_no_training_samples")
        return 0

    # Compare the model's features training-vs-live (#482: all of them, not
    # one). The shadow persists the exact vector the model consumed under
    # breakdown["features"] (same keys and scales as training_samples), so
    # the comparison is apples-to-apples by construction.
    reference_labels = [float(s.label) for s in training_samples]

    window_start = datetime.now(UTC) - timedelta(days=7)
    recent = await recent_for_role(
        "challenger", since=window_start, limit=10_000, require_features=True
    )
    if not recent:
        log.info("job.drift.no_recent_challenger_runs")
        return 0

    m = deps.settings.monitoring
    features = m.drift_features or sorted(
        {k for r in recent for k in (r.breakdown.get("features") or {})}
    )
    candidate_probs = [r.probability for r in recent]
    reports: dict[str, DriftReport] = {}
    for feature in features:
        # Un non misurato (#698) esce dal confronto da tutte e due le parti:
        # la deriva si misura sui valori, non su quante celle il satellite vede.
        assente = valore_assente(feature)
        candidate = _misurati(
            (
                r.breakdown["features"][feature]
                for r in recent
                if feature in (r.breakdown.get("features") or {})
            ),
            assente,
        )
        top, _, sub = feature.partition(".")
        reference = _misurati(
            ((s.features.get(top) or {}).get(sub) for s in training_samples), assente
        )
        if not candidate or not reference:
            continue
        reports[feature] = make_report(
            reference=reference,
            candidate=candidate,
            reference_probs=reference_labels,
            candidate_probs=candidate_probs,
            psi_alert=m.psi_alert,
            ks_alert=m.ks_alert,
            pred_alert=m.prediction_drift_alert,
        )
    if not reports:
        log.info("job.drift.no_feature_rows", features=features)
        return 0
    feature, report = peggiore(reports)

    trigger = RetrainingTrigger.from_inputs(drift=report, new_iffi_since_last_train=0)
    log.info(
        "job.drift.done",
        feature=feature,
        features=len(reports),
        in_allarme=sorted(f for f, r in reports.items() if r.psi_alert or r.ks_alert),
        psi_per_feature={f: round(r.psi, 3) for f, r in reports.items()},
        psi=report.psi,
        ks=report.ks,
        pred_drift=report.pred_drift,
        psi_alert=report.psi_alert,
        ks_alert=report.ks_alert,
        pred_alert=report.pred_alert,
        should_retrain=trigger.should_retrain,
        reason=trigger.reason,
    )
    return 1 if trigger.should_retrain else 0
