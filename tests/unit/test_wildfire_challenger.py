"""Challenger incendio: schema, riproducibilità e catena FWI (issue #68).

Le proprietà provate qui sono quelle che un errore renderebbe invisibile:

* lo **schema per pericolo** — un modello incendio non deve portarsi dietro
  sedici colonne di frana sempre a zero;
* la **riproducibilità della matrice** — stessi input, stesso SHA, che è il
  criterio di accettazione della issue;
* la catena FWI **dal seme**, deterministica;
* il bundle della baseline che si rifiuta di esistere senza FWI, invece di
  regalare uno zero al motore V1.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.data.repos.training_samples_repo import TrainingSample
from limen.ml.dataset import (
    CANONICAL_FEATURES,
    WILDFIRE_FEATURES,
    features_for,
    matrix_sha,
    to_matrix,
)
from limen.ml.feature_store import wildfire_features_to_bundle
from limen.ml.fire_features import chain_for_days

NOW = dt.datetime(2024, 8, 1, 12, tzinfo=dt.UTC)


def _sample(*, label: int, fwi: float = 30.0, block: str = "b1") -> TrainingSample:
    return TrainingSample(
        cell_id=f"c{label}-{fwi}",
        valuation_time=NOW,
        label=label,
        label_source="firms",
        features={
            "fire": {
                "fwi": fwi,
                "isi": fwi / 3.0,
                "dc": 300.0,
                "fuel_class_norm": 0.6,
                "wui_proximity_norm": 0.2,
                "density_hist": 4.0,
                # Stringa: provenienza per rigiocare la V1, non una colonna.
                "landuse_code": "312",
            },
            "static": {"slope_deg": 15.0},
            "rain": {"rain_30d_mm": 12.0},
        },
        split_block=block,
        hazard_type=HazardType.WILDFIRE,
    )


# ---------------------------------------------------------------------------
# Schema per pericolo
# ---------------------------------------------------------------------------
def test_each_hazard_gets_its_own_ordered_schema() -> None:
    assert features_for(HazardType.WILDFIRE) == WILDFIRE_FEATURES
    assert features_for(HazardType.LANDSLIDE) == CANONICAL_FEATURES
    # Un pericolo senza voce ricade su quello delle frane: è il comportamento
    # di prima della #68 e non deve rompersi.
    assert features_for(HazardType.FLOOD) == CANONICAL_FEATURES


def test_the_two_schemas_share_only_what_means_the_same_thing() -> None:
    """Due sole grandezze in comune, e nessuna per comodità.

    Trenta giorni di pioggia sono la stessa cosa per un versante saturo e per
    un bosco secco, letta con il segno opposto; la pendenza destabilizza un
    versante e accelera la propagazione di un fronte. Densità IFFI, velocità
    InSAR e peso litologico descrivono un versante che si muove, e in un
    modello di incendio sarebbero colonne mute.
    """
    shared = set(CANONICAL_FEATURES) & set(WILDFIRE_FEATURES)

    assert shared == {"rain.rain_30d_mm", "static.slope_deg"}
    assert not any(name.startswith("insar.") for name in WILDFIRE_FEATURES)


def test_the_wildfire_matrix_has_no_landslide_columns() -> None:
    matrix = to_matrix([_sample(label=1)], hazard=HazardType.WILDFIRE)

    assert matrix.feature_names == WILDFIRE_FEATURES
    assert not any(name.startswith("insar.") for name in matrix.feature_names)


def test_a_string_feature_is_provenance_not_a_column() -> None:
    """`landuse_code` serve a rigiocare la V1 sullo stesso campione. Senza il
    filtro, `float("312")` riuscirebbe e infilerebbe un codice CLC nella
    matrice come se fosse una grandezza continua."""
    matrix = to_matrix([_sample(label=1)], hazard=HazardType.WILDFIRE)

    assert "fire.landuse_code" not in matrix.feature_names
    assert matrix.X.shape[1] == len(WILDFIRE_FEATURES)


# ---------------------------------------------------------------------------
# Riproducibilità della matrice
# ---------------------------------------------------------------------------
def test_same_inputs_give_the_same_matrix_sha() -> None:
    samples = [_sample(label=1, fwi=40.0), _sample(label=0, fwi=10.0)]

    first = matrix_sha(to_matrix(samples, hazard=HazardType.WILDFIRE))
    second = matrix_sha(to_matrix(list(samples), hazard=HazardType.WILDFIRE))

    assert first == second


def test_the_sha_notices_a_changed_value_a_changed_label_and_a_changed_block() -> None:
    base = [_sample(label=1, fwi=40.0)]
    reference = matrix_sha(to_matrix(base, hazard=HazardType.WILDFIRE))

    changed_value = matrix_sha(to_matrix([_sample(label=1, fwi=41.0)], hazard=HazardType.WILDFIRE))
    changed_label = matrix_sha(to_matrix([_sample(label=0, fwi=40.0)], hazard=HazardType.WILDFIRE))
    changed_block = matrix_sha(
        to_matrix([_sample(label=1, fwi=40.0, block="b2")], hazard=HazardType.WILDFIRE)
    )

    assert len({reference, changed_value, changed_label, changed_block}) == 4


def test_the_sha_notices_a_changed_schema() -> None:
    """La stessa X con colonne diverse non è lo stesso dataset."""
    samples = [_sample(label=1)]

    wildfire = matrix_sha(to_matrix(samples, hazard=HazardType.WILDFIRE))
    landslide = matrix_sha(to_matrix(samples, hazard=HazardType.LANDSLIDE))

    assert wildfire != landslide


def test_the_sha_survives_floating_point_summation_noise() -> None:
    """Arrotondato a nove decimali: BLAS somma in ordine dipendente dal numero
    di thread, e un controllo che dà falsi allarmi non lo guarda più nessuno."""
    exact = [_sample(label=1, fwi=30.0)]
    jittered = [_sample(label=1, fwi=30.0 + 1e-12)]

    assert matrix_sha(to_matrix(exact, hazard=HazardType.WILDFIRE)) == matrix_sha(
        to_matrix(jittered, hazard=HazardType.WILDFIRE)
    )


# ---------------------------------------------------------------------------
# Bundle della baseline
# ---------------------------------------------------------------------------
def test_the_baseline_bundle_refuses_to_exist_without_fwi() -> None:
    """Senza meteo il motore V1 darebbe zero, e zero non è "nessun pericolo
    misurato" ma "nessun pericolo": la baseline sembrerebbe brava proprio dove
    tace."""
    out = wildfire_features_to_bundle(
        cell_id="c1",
        aoi_id="aoi",
        valuation_time=NOW,
        features={"fire": {"fuel_class_norm": 0.6}, "static": {"slope_deg": 15.0}},
    )

    assert out is None


def test_the_baseline_bundle_carries_the_raw_clc_code() -> None:
    """Il campione V1 deve leggere il combustibile con la **sua** mappa: se
    challenger e campione lo leggessero in due modi diversi, una vittoria non
    direbbe quale delle due cose ha vinto."""
    bundle = wildfire_features_to_bundle(
        cell_id="c1",
        aoi_id="aoi",
        valuation_time=NOW,
        features=_sample(label=1).features,
    )

    assert bundle is not None
    assert bundle.static.landuse_code == "312"
    assert bundle.dynamic.fire_weather is not None
    assert bundle.dynamic.fire_weather.fwi == 30.0


# ---------------------------------------------------------------------------
# Catena FWI
# ---------------------------------------------------------------------------
def _thresholds() -> WildfireThresholds:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return t


class _Snapshot:
    """Osservazioni di mezzogiorno costanti, per una catena deterministica."""

    def __init__(self, *, rain_mm: float = 0.0) -> None:
        self._rain = rain_mm

    def noon_observation(self, day: dt.date) -> object:
        class _Obs:
            temperature_c = 30.0
            relative_humidity_pct = 25.0
            wind_speed_kmh = 15.0
            rain_24h_mm = self._rain

        return _Obs()


def test_the_chain_is_deterministic_from_the_seed() -> None:
    days = [dt.date(2024, 7, 1) + dt.timedelta(days=i) for i in range(10)]

    first = chain_for_days(snapshot=_Snapshot(), days=days, thresholds=_thresholds())  # type: ignore[arg-type]
    second = chain_for_days(snapshot=_Snapshot(), days=days, thresholds=_thresholds())  # type: ignore[arg-type]

    assert first == second


def test_dry_days_build_the_drought_code_up() -> None:
    """La catena è ricorsiva: è il motivo per cui il FWI non si legge da una
    tabella statica ma si cammina dal seme."""
    days = [dt.date(2024, 7, 1) + dt.timedelta(days=i) for i in range(20)]

    chain = chain_for_days(snapshot=_Snapshot(), days=days, thresholds=_thresholds())  # type: ignore[arg-type]

    assert chain[days[-1]]["dc"] > chain[days[0]]["dc"]
    assert chain[days[-1]]["chain_days"] == 20.0


def test_the_thirty_day_rain_comes_from_the_same_fetch() -> None:
    """Zero richieste in più: la precipitazione è già uno dei quattro ingressi
    del FWI, e l'enricher pioggia non poteva darla (CERRA finisce nel 2021)."""
    days = [dt.date(2024, 7, 1) + dt.timedelta(days=i) for i in range(40)]

    chain = chain_for_days(
        snapshot=_Snapshot(rain_mm=2.0),
        days=days,
        thresholds=_thresholds(),  # type: ignore[arg-type]
    )

    # Trenta giorni a 2 mm, una volta che la finestra è piena.
    assert chain[days[-1]]["rain_30d_mm"] == pytest.approx(60.0)
    # E all'inizio la finestra è parziale, non inventata.
    assert chain[days[0]]["rain_30d_mm"] == pytest.approx(2.0)
