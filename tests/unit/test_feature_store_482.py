"""Feature store dello sfidante: segnali nuovi, schema alluvione, deriva (#482)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from limen.api.jobs import drift_monitor
from limen.config.settings import Settings
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    SeismicHistoryEvent,
    StaticFactors,
)
from limen.core.scoring.ml_engine import _bundle_to_feature_row
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.repos.model_runs_repo import ModelRunRow
from limen.data.repos.seismic_repo import ScossaCella
from limen.data.repos.training_samples_repo import TrainingSample
from limen.ml import feature_store
from limen.ml.dataset import (
    CANONICAL_FEATURES,
    FLOOD_FEATURES,
    WILDFIRE_FEATURES,
    features_for,
)
from limen.ml.monitoring.drift import make_report, peggiore

T = datetime(2026, 10, 10, 12, tzinfo=UTC)

_PRIMA_DELLA_482 = (
    "static.susc_ispra",
    "static.iffi_density_500",
    "static.distance_to_iffi_m",
    "static.slope_deg",
    "static.twi",
    "static.curvature",
    "static.litho_weight",
    "static.pai_class_norm",
    "insar.velocity_mmy",
    "insar.accel_mmy2",
    "insar.scatterer_count",
    "rain.rain_24h_mm",
    "rain.rain_72h_mm",
    "rain.rain_30d_mm",
    "rain.max_i_24h_mmh",
)


def test_lo_schema_frane_si_allunga_solo_in_coda() -> None:
    # I modelli registrati leggono il loro feature_names.json: l'ordine di
    # testa non si tocca.
    assert CANONICAL_FEATURES[: len(_PRIMA_DELLA_482)] == _PRIMA_DELLA_482
    assert CANONICAL_FEATURES[len(_PRIMA_DELLA_482) :] == (
        "seismic.pga_max_g",
        "static.imperviousness_norm",
        "insar.velocita_verticale_mmy",
        "insar.velocita_est_mmy",
        "insar.stagionalita_verticale_mm",
    )


def test_l_alluvione_ha_il_suo_schema() -> None:
    assert features_for(HazardType.FLOOD) == FLOOD_FEATURES
    assert not set(FLOOD_FEATURES) & {n for n in CANONICAL_FEATURES if n.startswith("insar.")}


def _bundle() -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="a",
        cell_id="a|0|0",
        static=StaticFactors(
            cell_id="a|0|0",
            susc_ispra=0.55,
            iffi_density_500=2.0,
            distance_to_iffi_m=300.0,
            slope_deg=21.0,
            twi=7.5,
            curvature=0.2,
            litho_weight=0.6,
            pai_class_norm=0.75,
            flood_hazard_norm=0.8,
            imperviousness_norm=0.3,
            quota_sul_fondo_m=12.0,
            elevation_m=140.0,
            insar_velocity_mmy=-4.5,
            insar_accel_mmy2=-0.3,
            insar_scatterer_count=12,
            velocita_verticale_mmy=-3.9,
            velocita_est_mmy=1.2,
            stagionalita_verticale_mm=2.5,
        ),
        dynamic=DynamicInputs(
            valuation_time=T,
            seismic_history=(
                SeismicHistoryEvent(
                    event_id="e1",
                    origin_time=T - timedelta(days=3),
                    magnitude=5.1,
                    distance_km=20.0,
                    pga_g=0.08,
                ),
                SeismicHistoryEvent(
                    event_id="e2",
                    origin_time=T - timedelta(days=1),
                    magnitude=4.2,
                    distance_km=8.0,
                    pga_g=0.12,
                ),
            ),
        ),
    )


@pytest.mark.parametrize("schema", [CANONICAL_FEATURES, FLOOD_FEATURES])
def test_ogni_feature_dello_schema_e_servita(schema: tuple[str, ...]) -> None:
    """Una feature che il servizio non conosce vale zero in silenzio: lo
    sfidante frane l'ha fatto con InSAR, imparata sui valori veri e servita a
    zero finché il bundle non la portava (#568). Nessuna eccezione."""
    nomi = list(schema)
    riga = dict(zip(nomi, _bundle_to_feature_row(_bundle(), names=nomi), strict=True))
    statiche = _bundle().static
    insar = {
        "velocity_mmy": statiche.insar_velocity_mmy,
        "accel_mmy2": statiche.insar_accel_mmy2,
        "scatterer_count": statiche.insar_scatterer_count,
        "velocita_verticale_mmy": statiche.velocita_verticale_mmy,
        "velocita_est_mmy": statiche.velocita_est_mmy,
        "stagionalita_verticale_mm": statiche.stagionalita_verticale_mm,
    }
    for nome in nomi:
        top, _, sub = nome.partition(".")
        if top == "rain":
            continue
        atteso: Any
        if top == "static":
            atteso = getattr(statiche, sub)
        elif top == "insar":
            atteso = insar[sub]
        else:
            assert nome == "seismic.pga_max_g"
            atteso = 0.12
        assert atteso, nome
        assert riga[nome] == pytest.approx(float(atteso)), nome


def test_wildfire_invariato() -> None:
    assert features_for(HazardType.WILDFIRE) == WILDFIRE_FEATURES


async def test_pga_di_addestramento_e_di_servizio_coincidono(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viste: list[tuple[datetime, datetime, float]] = []

    async def scosse(
        cell_ids: list[str], dal: datetime, al: datetime, *, min_magnitude: float
    ) -> list[ScossaCella]:
        viste.append((dal, al, min_magnitude))
        return [
            ScossaCella(
                cell_id=cell_ids[0],
                event_id=e.event_id,
                origin_time=e.origin_time,
                magnitude=e.magnitude,
                pga_g=e.pga_g,
                distanza_km=e.distance_km,
            )
            for e in _bundle().dynamic.seismic_history
        ]

    monkeypatch.setattr(feature_store, "scosse_per_cella", scosse)
    addestramento = await feature_store._pga_max_before("a|0|0", at=T)
    servizio = _bundle_to_feature_row(_bundle(), names=["seismic.pga_max_g"])[0]
    assert addestramento == pytest.approx(servizio) == pytest.approx(0.12)
    # La finestra è quella di SeismicCheck, e finisce al campione.
    cfg = load_regional_thresholds().seismic
    assert viste == [(T - timedelta(days=cfg.giorni_da_leggere), T, cfg.min_magnitude)]


async def test_pga_senza_terremoti_e_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nessuna(*_a: Any, **_k: Any) -> list[ScossaCella]:
        return []

    monkeypatch.setattr(feature_store, "scosse_per_cella", nessuna)
    assert await feature_store._pga_max_before("a|0|0", at=T) == 0.0


def _report(psi_ref: list[float], psi_cand: list[float]) -> Any:
    return make_report(
        reference=psi_ref,
        candidate=psi_cand,
        reference_probs=[0.1],
        candidate_probs=[0.1],
        psi_alert=0.25,
        ks_alert=0.9,
        pred_alert=0.9,
    )


def test_peggiore_preferisce_chi_supera_la_soglia() -> None:
    ferma = _report([float(i) for i in range(50)], [float(i) for i in range(50)])
    mossa = _report([float(i) for i in range(50)], [float(i) + 40 for i in range(50)])
    nome, r = peggiore({"static.slope_deg": ferma, "rain.rain_72h_mm": mossa})
    assert nome == "rain.rain_72h_mm"
    assert r.psi_alert
    with pytest.raises(ValueError):
        peggiore({})


async def test_la_deriva_guarda_tutte_le_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    campioni = [
        TrainingSample(
            cell_id=f"c{i}",
            valuation_time=T,
            label=i % 2,
            label_source="italica",
            features={"static": {"slope_deg": float(i)}, "rain": {"rain_72h_mm": float(i)}},
            split_block="b",
        )
        for i in range(50)
    ]
    # Pendenza uguale all'addestramento, pioggia spostata: deve vincere la pioggia,
    # che con la sola `rain.rain_72h_mm` di prima era anche l'unica guardata.
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
            breakdown={"features": {"static.slope_deg": float(i), "rain.rain_72h_mm": i + 40.0}},
        )
        for i in range(50)
    ]

    async def fetch_samples() -> list[TrainingSample]:
        return campioni

    async def recent_for_role(*_a: Any, **_k: Any) -> list[ModelRunRow]:
        return recenti

    monkeypatch.setattr(drift_monitor, "fetch_samples", fetch_samples)
    monkeypatch.setattr(drift_monitor, "recent_for_role", recent_for_role)
    deps: Any = SimpleNamespace(settings=Settings())
    assert await drift_monitor.run_drift_monitor_job(deps) == 1

    solo_pendenza: Any = SimpleNamespace(
        settings=Settings(monitoring={"drift_features": ["static.slope_deg"]})
    )
    assert await drift_monitor.run_drift_monitor_job(solo_pendenza) == 0
