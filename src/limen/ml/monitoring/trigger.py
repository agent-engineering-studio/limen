"""Retraining trigger — combines drift signals with new-event arrivals.

Fires when EITHER:
* the configured PSI / KS / prediction-drift thresholds are breached, OR
* enough new IFFI events have landed since the last training run.

The trigger does NOT auto-promote — it merely signals that a new
training run should be scheduled. Operators still apply the promotion
gate from :mod:`limen.ml.train` before the new model becomes champion.
"""

from __future__ import annotations

from dataclasses import dataclass

from limen.ml.monitoring.drift import DriftReport


@dataclass(frozen=True, slots=True)
class RetrainingTrigger:
    """Decision result for one monitoring tick."""

    should_retrain: bool
    reason: str

    @classmethod
    def from_inputs(
        cls,
        *,
        drift: DriftReport,
        new_iffi_since_last_train: int,
        new_iffi_threshold: int = 50,
    ) -> RetrainingTrigger:
        if drift.psi_alert:
            return cls(True, f"PSI={drift.psi:.3f} ≥ threshold")
        if drift.ks_alert:
            return cls(True, f"KS={drift.ks:.3f} ≥ threshold")
        if drift.pred_alert:
            return cls(True, f"prediction_drift={drift.pred_drift:.3f} ≥ threshold")
        if new_iffi_since_last_train >= new_iffi_threshold:
            return cls(
                True,
                f"{new_iffi_since_last_train} new IFFI events ≥ {new_iffi_threshold}",
            )
        return cls(False, "no signals")


__all__ = ["RetrainingTrigger"]
