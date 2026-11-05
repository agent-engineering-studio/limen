"""Le ShakeMap storiche nel backtest frane (#287): stesso conto del job di produzione."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ingv_shakemap import Event
from ingv_shakemap.events import parse_event

from limen.cli import backtest
from limen.core.models.risk import StaticFactors
from limen.core.scoring.regional_thresholds import SeismicBlock
from limen.integrations.ingv import shakemap_client
from tests.unit.test_shakemap_grid import RIGHE, griglia_xml

SISMA = SeismicBlock(
    tau_days=2.0,
    min_magnitude=3.5,
    lookback_days=7,
    pga_threshold_g=0.05,
    pga_scale_g=0.05,
    pga_min_g=0.02,
)
CELLE = [
    (StaticFactors(cell_id="forte"), 10.1, 43.1),  # 7,5 %g
    (StaticFactors(cell_id="al_limite"), 10.0, 43.0),  # 2 %g: conta
    (StaticFactors(cell_id="debole"), 10.2, 43.0),  # 0,5 %g: no
    (StaticFactors(cell_id="fuori"), 12.0, 44.0),  # fuori dalla griglia
]


def _evento(event_id: str, mag: float) -> dict[str, Any]:
    return {
        "id": event_id,
        "geometry": {"coordinates": [10.1, 43.05, 10.0]},
        "properties": {"time": "2016-10-30T06:40:17Z", "mag": mag},
    }


class _Finto:
    scaricati: ClassVar[list[str]] = []
    finestra: ClassVar[dict[str, Any]] = {}

    def __init__(self, **_: Any) -> None:
        pass

    async def fetch_events(self, **kw: Any) -> list[Event]:
        assert kw.pop("solleva") is True
        _Finto.finestra = kw
        eventi = [parse_event(_evento("con-mappa", 5.0)), parse_event(_evento("senza-mappa", 4.0))]
        return [e for e in eventi if e is not None]

    async def fetch_shakemap_grid(self, event_id: str, *, solleva: bool = False) -> bytes | None:
        assert solleva, "il backtest non deve scambiare un guasto per «nessuna ShakeMap»"
        _Finto.scaricati.append(event_id)
        return griglia_xml(RIGHE) if event_id == "con-mappa" else None


@pytest.fixture(autouse=True)
def _client_finto(monkeypatch: pytest.MonkeyPatch) -> None:
    _Finto.scaricati = []
    monkeypatch.setattr(shakemap_client, "IngvHttpClient", _Finto)


async def _scosse(cache: Path | None = None) -> dict[str, Any]:
    return await backtest.scosse_storiche(
        CELLE,
        bbox=(10.0, 43.0, 10.2, 43.1),
        start=datetime(2016, 11, 1, tzinfo=UTC),
        end=datetime(2016, 11, 30, tzinfo=UTC),
        seismic=SISMA,
        cache=cache,
    )


async def test_solo_le_celle_scosse_oltre_la_soglia() -> None:
    scosse = await _scosse()
    assert set(scosse) == {"forte", "al_limite"}
    [forte] = scosse["forte"]
    assert forte.event_id == "con-mappa"
    assert forte.pga_g == pytest.approx(0.075)
    assert forte.magnitude == 5.0
    assert forte.distance_km == pytest.approx(5.56, abs=0.1)
    # La finestra comincia `lookback_days` prima e il riquadro si allarga di un grado.
    assert _Finto.finestra["start"] == datetime(2016, 10, 25, tzinfo=UTC)
    assert _Finto.finestra["bbox"] == (9.0, 42.0, 11.2, 44.1)
    assert _Finto.finestra["min_magnitude"] == 3.5


async def test_la_cache_evita_di_riscaricare(tmp_path: Path) -> None:
    prima = await _scosse(tmp_path)
    assert sorted(_Finto.scaricati) == ["con-mappa", "senza-mappa"]
    _Finto.scaricati = []
    assert await _scosse(tmp_path) == prima
    # Un evento senza ShakeMap non lascia file: si richiede, la griglia no.
    assert _Finto.scaricati == ["senza-mappa"]


async def test_un_catalogo_irraggiungibile_ferma_il_backtest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex su #310: un catalogo che non risponde non è un periodo senza terremoti."""

    async def guasto(self: _Finto, **kw: Any) -> list[Event]:
        raise shakemap_client.IngvNonDisponibileError("catalogo FDSN: HTTP 503")

    monkeypatch.setattr(_Finto, "fetch_events", guasto)
    with pytest.raises(shakemap_client.IngvNonDisponibileError):
        await _scosse()


def test_la_soglia_di_e_si_sovrascrive_solo_nel_backtest() -> None:
    """`LIMEN_BACKTEST_PGA_MIN_G`: si misura una soglia prima di scriverla nella YAML."""
    from limen.core.scoring.regional_thresholds import load_regional_thresholds
    from limen.core.scoring.seismic_decay import seismic_factor

    yaml = load_regional_thresholds()
    assert backtest.soglie_backtest() == yaml
    alta = backtest.soglie_backtest(0.1)
    assert alta.seismic.pga_min_g == 0.1
    assert alta.seismic.model_copy(update={"pga_min_g": yaml.seismic.pga_min_g}) == yaml.seismic
    assert alta.model_copy(update={"seismic": yaml.seismic}) == yaml
    # 0,05 g accende E con la soglia della YAML, non con 0,1 g.
    assert seismic_factor(0.05, seismic=yaml.seismic) > 0
    assert seismic_factor(0.05, seismic=alta.seismic) == 0
    # La YAML in cache non è stata toccata.
    assert load_regional_thresholds().seismic.pga_min_g == yaml.seismic.pga_min_g


@pytest.mark.parametrize("valore", ["zero virgola uno", "0", "-0.1"])
async def test_una_soglia_storta_ferma_il_backtest(
    valore: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_BACKTEST_PGA_MIN_G", valore)
    assert await backtest.run() == 1
