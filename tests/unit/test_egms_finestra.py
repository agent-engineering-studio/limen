"""La finestra di una release EGMS non è il suo nome (#699)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from limen.data.repos.cell_insar_features_repo import CellInsarFeatures
from limen.integrations.egms.sync_job import _periodo
from limen.ml import feature_store
from limen.ml.dataset import NON_MISURATA_SE_ASSENTE, to_matrix
from limen.ml.feature_store import _insar_al


def test_il_periodo_e_la_finestra_letta_dai_file() -> None:
    assert _periodo("2020_2025") == (date(2020, 12, 9), date(2025, 11, 19))


def test_una_release_non_ancora_letta_non_ha_date_inventate() -> None:
    assert _periodo("2021_2026") == (None, None)


def _riga(inizio: date | None) -> CellInsarFeatures:
    return CellInsarFeatures(
        cell_id="c",
        insar_velocity_mmy=4.0,
        scatterer_count=80,
        period_start=inizio,
        period_end=date(2025, 11, 19),
    )


def test_un_campione_prima_della_serie_non_ha_egms() -> None:
    riga = _riga(date(2020, 12, 9))
    assert _insar_al(riga, datetime(2020, 3, 15, tzinfo=UTC)) is None
    assert _insar_al(riga, datetime(2020, 12, 8, 23, tzinfo=UTC)) is None
    assert _insar_al(riga, datetime(2020, 12, 9, tzinfo=UTC)) is riga


def test_un_campione_dopo_la_serie_la_tiene_come_fa_il_servizio() -> None:
    riga = _riga(date(2020, 12, 9))
    assert _insar_al(riga, datetime(2026, 10, 10, tzinfo=UTC)) is riga


def test_senza_inizio_noto_la_misura_resta() -> None:
    riga = _riga(None)
    assert _insar_al(riga, datetime(2019, 1, 1, tzinfo=UTC)) is riga
    assert _insar_al(None, datetime(2024, 1, 1, tzinfo=UTC)) is None


async def test_nel_campione_la_misura_tolta_e_mancante_non_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _nessuno(*_a: object, **_k: object) -> None:
        return None

    async def _zero(*_a: object, **_k: object) -> float:
        return 0.0

    async def _insar(_cell_id: str) -> CellInsarFeatures:
        return _riga(date(2020, 12, 9))

    monkeypatch.setattr(feature_store.cell_static_factors_repo, "get_for_cell", _nessuno)
    monkeypatch.setattr(feature_store, "_suscettibilita", _nessuno)
    monkeypatch.setattr(feature_store, "_pga_max_before", _zero)
    monkeypatch.setattr(feature_store.cell_insar_features_repo, "get_for_cell", _insar)

    prima = await feature_store._build_features("c", datetime(2020, 3, 15, tzinfo=UTC))
    dopo = await feature_store._build_features("c", datetime(2023, 5, 16, tzinfo=UTC))
    assert prima["insar"]["velocity_mmy"] is None
    assert prima["insar"]["scatterer_count"] == 0
    assert dopo["insar"]["velocity_mmy"] == 4.0
    assert dopo["insar"]["scatterer_count"] == 80

    from limen.data.repos.training_samples_repo import TrainingSample

    matrice = to_matrix(
        [
            TrainingSample(
                cell_id="c",
                valuation_time=datetime(2020, 3, 15, tzinfo=UTC),
                label=1,
                label_source="italica",
                features=prima,
                split_block="b",
            )
        ]
    )
    import math

    for nome in NON_MISURATA_SE_ASSENTE:
        assert math.isnan(matrice.X[0, matrice.feature_names.index(nome)]), nome
