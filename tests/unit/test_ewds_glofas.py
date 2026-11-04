"""Lo storico GloFAS dall'EWDS: l'adattatore di Limen sopra `glofas-ewds` (#200).

Richieste, download e lettura dei NetCDF sono provati nel pacchetto. Qui resta
ciò che Limen ci mette sopra o ne pretende: le celle misurate sui nodi veri,
la regola dei giorni minimi, i nomi dei file già scaricati (una cache che
cambia nome si riscarica da capo), il ripiego su «intermediate» e il log.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from glofas_ewds import open_meteo_cell

from limen.integrations.copernicus import ewds_fwi
from limen.integrations.copernicus import ewds_glofas as eg


@pytest.mark.parametrize(
    ("nodo", "cella"),
    [
        # Coordinate dichiarate da Open-Meteo l'11 ottobre 2026 (sul bordo fra
        # due celle va a volte in su e a volte in giù: float32), più il passo
        # verso est fra la cella dichiarata e quella i cui valori restituisce.
        ((11.9, 44.3), (11.925, 44.275)),
        ((12.0, 44.2), (12.025, 44.225)),
        ((16.6, 40.7), (16.675, 40.725)),
        ((7.7, 45.1), (7.725, 45.125)),
        ((15.6, 38.1), (15.675, 38.075)),
    ],
)
def test_la_cella_e_quella_di_open_meteo(
    nodo: tuple[float, float], cella: tuple[float, float]
) -> None:
    assert open_meteo_cell(*nodo) == pytest.approx(cella, abs=1e-3)


def test_la_fonte_e_glofas_4() -> None:
    # Un riferimento v5 sotto una previsione v4 darebbe rapporti dimezzati.
    assert eg.FONTE == "ewds:version_4_0"


def test_il_riferimento_vuole_un_anno_di_dati() -> None:
    lunga = [float(k) for k in range(400)]
    rif = eg.riferimenti({(1.0, 1.0): lunga, (2.0, 2.0): [5.0] * 10}, percentile=0.9)
    assert rif[(1.0, 1.0)] == pytest.approx(359.1)
    assert rif[(2.0, 2.0)] is None


class _Client:
    def __init__(self, *, senza_consolidato: bool = False) -> None:
        self.chiesti: list[tuple[str, dict[str, Any]]] = []
        self.senza_consolidato = senza_consolidato

    def retrieve(self, name: str, request: dict[str, Any], target: str) -> None:
        self.chiesti.append((name, request))
        # Il GloFAS dice il prodotto in `product_type` (una lista), l'FWI in
        # `dataset_type` (una stringa: il suo `product_type` è «reanalysis»).
        prodotto = request.get("dataset_type") or request["product_type"][0]
        if self.senza_consolidato and prodotto.startswith("consolidated"):
            raise RuntimeError("Request has not produced a valid combination of values")
        Path(target).write_bytes(b"x")


def test_i_file_tengono_il_nome_della_cache(tmp_path: Path) -> None:
    # I nomi di prima del pacchetto: i mesi già in LIMEN_EWDS_DIR non si richiedono.
    (tmp_path / "glofas_version_4_0_202404_29-30.nc").write_bytes(b"x")
    (tmp_path / "fwi").mkdir()
    (tmp_path / "fwi" / "cems_fire_4_1_202404_29-30.nc").write_bytes(b"x")
    client = _Client()
    eg.scarica(tmp_path, date(2024, 4, 29), date(2024, 5, 2), client=client)
    ewds_fwi.scarica(tmp_path / "fwi", date(2024, 4, 29), date(2024, 5, 2), client=client)
    assert [r["month"] for _, r in client.chiesti] == [["05"], ["05"]]
    assert not list(tmp_path.rglob("*.part"))


def test_un_mese_senza_consolidato_si_prende_intermedio_e_si_logga(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    righe: list[dict[str, Any]] = []
    monkeypatch.setattr(eg.log, "info", lambda evento, **kw: righe.append({"e": evento, **kw}))
    interno = _Client(senza_consolidato=True)
    client = eg._ConLog(interno)
    eg.scarica(tmp_path, date(2026, 7, 1), date(2026, 7, 3), client=client)
    ewds_fwi.scarica(tmp_path, date(2026, 7, 1), date(2026, 7, 3), client=client)
    assert [r["prodotto"] for r in righe] == [
        "consolidated",
        "intermediate",
        "consolidated_dataset",
        "intermediate_dataset",
    ]
    assert {r["dataset"] for r in righe} == {"cems-glofas-historical", "cems-fire-historical-v1"}
    assert all(r["giorni"] == 3 for r in righe)
    assert len(list(tmp_path.glob("*.nc"))) == 2


def test_un_altro_errore_non_diventa_intermedio(tmp_path: Path) -> None:
    class _Rifiuta:
        def retrieve(self, _ds: str, _req: dict[str, Any], _dest: str) -> None:
            raise RuntimeError("403 required licences not accepted")

    with pytest.raises(RuntimeError, match="licences"):
        eg.scarica(tmp_path, date(2026, 7, 1), date(2026, 7, 3), client=eg._ConLog(_Rifiuta()))


def test_scarica_previsione_non_riscarica_una_corsa(tmp_path: Path) -> None:
    client = _Client()
    a = eg.scarica_previsione(tmp_path, date(2026, 10, 10), client=client)
    b = eg.scarica_previsione(tmp_path, date(2026, 10, 10), client=client)
    assert a == b
    assert len(client.chiesti) == 1
    name, req = client.chiesti[0]
    assert name == "cems-glofas-forecast"
    assert req["product_type"] == ["control_forecast"]
    assert req["leadtime_hour"] == ["24", "48", "72", "96", "120", "144", "168"]
