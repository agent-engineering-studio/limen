"""Una cella senza pixel EGMS non è «terreno fermo» (#698)."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from limen.api.jobs import drift_monitor
from limen.config.settings import Settings
from limen.core.models.risk import CellFeatureBundle, DynamicInputs, StaticFactors
from limen.core.scoring.ml_engine import (
    MLScoringEngine,
    _bundle_to_feature_row,
    _component_attribution,
    _MLArtefacts,
)
from limen.data.repos.model_runs_repo import ModelRunRow
from limen.data.repos.training_samples_repo import TrainingSample
from limen.ml.dataset import (
    CANONICAL_FEATURES,
    NON_MISURATA_SE_ASSENTE,
    TrainingMatrix,
    prune_collinear,
    to_matrix,
)

T = datetime(2026, 10, 10, 12, tzinfo=UTC)
NOMI = list(CANONICAL_FEATURES)


def _bundle(**insar: Any) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="a",
        cell_id="a|0|0",
        static=StaticFactors(cell_id="a|0|0", slope_deg=21.0, **insar),
        dynamic=DynamicInputs(valuation_time=T),
    )


def _campione(insar: dict[str, Any], *, label: int = 0) -> TrainingSample:
    return TrainingSample(
        cell_id="a|0|0",
        valuation_time=T,
        label=label,
        label_source="background",
        features={"static": {"slope_deg": 21.0}, "insar": insar},
        split_block="b",
    )


def _artefatti(names: list[str]) -> _MLArtefacts:
    return _MLArtefacts(
        model_uri="test://m",
        model_version="v0",
        booster=object(),
        calibrator=None,
        explainer=None,
        feature_names=names,
    )


# Come le scrive `feature_store._build_features` per una cella senza riga
# EGMS, e per un campione estratto prima che le colonne esistessero.
_SENZA_PIXEL = {
    "velocity_mmy": None,
    "accel_mmy2": None,
    "scatterer_count": 0,
    "velocita_verticale_mmy": None,
    "velocita_est_mmy": None,
    "stagionalita_verticale_mm": None,
}


@pytest.mark.parametrize("insar", [_SENZA_PIXEL, {}])
def test_addestramento_e_servizio_trattano_il_mancante_allo_stesso_modo(
    insar: dict[str, Any],
) -> None:
    addestramento = to_matrix([_campione(insar)]).X[0].tolist()
    servizio = _bundle_to_feature_row(_bundle(), names=NOMI)
    for nome, a, s in zip(NOMI, addestramento, servizio, strict=True):
        if nome in NON_MISURATA_SE_ASSENTE:
            assert math.isnan(a), nome
            assert math.isnan(s), nome
        else:
            assert a == pytest.approx(s), nome


def test_una_cella_misurata_e_ferma_resta_zero() -> None:
    fermo = {
        "insar_velocity_mmy": 0.0,
        "insar_accel_mmy2": 0.0,
        "insar_scatterer_count": 7,
        "velocita_verticale_mmy": 0.0,
        "velocita_est_mmy": 0.0,
        "stagionalita_verticale_mm": 0.0,
    }
    riga = dict(zip(NOMI, _bundle_to_feature_row(_bundle(**fermo), names=NOMI), strict=True))
    for nome in NON_MISURATA_SE_ASSENTE:
        assert riga[nome] == 0.0, nome
    campione = _campione(
        {
            "velocity_mmy": 0.0,
            "accel_mmy2": 0.0,
            "scatterer_count": 7,
            "velocita_verticale_mmy": 0.0,
            "velocita_est_mmy": 0.0,
            "stagionalita_verticale_mm": 0.0,
        }
    )
    matrice = to_matrix([campione])
    for nome in NON_MISURATA_SE_ASSENTE:
        assert matrice.X[0, NOMI.index(nome)] == 0.0, nome


def test_il_conteggio_dei_pixel_resta_zero() -> None:
    riga = dict(zip(NOMI, _bundle_to_feature_row(_bundle(), names=NOMI), strict=True))
    assert riga["insar.scatterer_count"] == 0.0
    assert "insar.scatterer_count" not in NON_MISURATA_SE_ASSENTE


def test_lo_shadow_scrive_null_e_non_nan() -> None:
    motore = MLScoringEngine(_artefatti(NOMI))
    riga = motore.feature_row(_bundle())
    for nome in NON_MISURATA_SE_ASSENTE:
        assert riga[nome] is None, nome
    assert riga["static.slope_deg"] == 21.0
    # `allow_nan=False` è quello che jsonb pretende.
    json.dumps(riga, allow_nan=False)


def test_il_ripiego_dello_shap_non_propaga_nan() -> None:
    art = _artefatti(["static.slope_deg", "insar.velocity_mmy", "rain.rain_72h_mm"])
    out = _component_attribution(art, feature_row=[0.4, math.nan, 0.6], total=0.5)
    assert all(math.isfinite(v) for v in out.values())
    assert sum(out.values()) == pytest.approx(0.5)


def test_la_collinearita_si_misura_dove_entrambe_sono_misurate() -> None:
    import numpy as np

    rng = np.random.default_rng(0)
    a = rng.normal(size=200)
    gemella = a * 2.0
    gemella[:60] = np.nan
    matrice = TrainingMatrix(
        feature_names=("insar.velocity_mmy", "insar.velocita_verticale_mmy", "static.twi"),
        X=np.column_stack([a, gemella, rng.normal(size=200)]),
        y=np.zeros(200, dtype=int),
        groups=tuple("b" for _ in range(200)),
    )
    potata, tolte = prune_collinear(matrice, threshold=0.95)
    assert potata.feature_names == ("insar.velocity_mmy", "static.twi")
    assert [(k, d) for k, d, _ in tolte] == [("insar.velocity_mmy", "insar.velocita_verticale_mmy")]


async def test_la_deriva_lascia_fuori_i_non_misurati(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stessa velocità dove è misurata; metà delle celle dal vivo non lo è.
    # A 0.0 quella metà sarebbe stata una deriva che non c'è.
    campioni = [_campione({"velocity_mmy": float(i % 50)}, label=i % 2) for i in range(100)]
    recenti = [
        ModelRunRow(
            cell_id=f"c{i}",
            valuation_time=T,
            aoi_id="a",
            model_uri="m",
            model_version="v",
            role="challenger",
            probability=0.5,
            risk_class="Low",
            breakdown={"features": {"insar.velocity_mmy": float(i % 50) if i < 100 else None}},
        )
        for i in range(200)
    ]

    async def fetch_samples() -> list[TrainingSample]:
        return campioni

    async def recent_for_role(*_a: Any, **_k: Any) -> list[ModelRunRow]:
        return recenti

    monkeypatch.setattr(drift_monitor, "fetch_samples", fetch_samples)
    monkeypatch.setattr(drift_monitor, "recent_for_role", recent_for_role)
    deps: Any = SimpleNamespace(
        settings=Settings(monitoring={"drift_features": ["insar.velocity_mmy"]})
    )
    assert await drift_monitor.run_drift_monitor_job(deps) == 0


def test_il_boosting_distingue_non_misurato_da_fermo() -> None:
    np = pytest.importorskip("numpy")
    try:
        import lightgbm as lgb
    except (ImportError, OSError):
        pytest.skip("lightgbm non caricabile")

    rng = np.random.default_rng(0)
    velocita = rng.normal(size=600)
    non_misurata = rng.random(600) < 0.4
    # Le celle non misurate franano più spesso di quelle ferme: a 0.0 il
    # modello non potrebbe saperlo.
    y = np.where(non_misurata, rng.random(600) < 0.8, np.abs(velocita) > 1.0).astype(int)
    x = np.where(non_misurata, np.nan, velocita).reshape(-1, 1)
    modello = lgb.LGBMClassifier(n_estimators=40, verbosity=-1, seed=0).fit(x, y)
    fermo, mancante = modello.predict_proba(np.array([[0.0], [np.nan]]))[:, 1]
    assert mancante > fermo + 0.3


def test_la_logistica_di_confronto_accetta_i_non_misurati() -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    try:
        from limen.ml.train import _algorithm_candidates
    except OSError:
        pytest.skip("lightgbm non caricabile")
    try:
        candidati = _algorithm_candidates(0, {0: 1.0, 1: 1.0})
    except (ImportError, OSError):
        pytest.skip("lightgbm non caricabile")

    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 3))
    y = (x[:, 0] > 0).astype(int)
    x[rng.random(200) < 0.3, 1] = np.nan
    for nome in ("logistic", "random_forest"):
        proba = candidati[nome].fit(x, y).predict_proba(x)[:, 1]
        assert np.isfinite(proba).all(), nome
