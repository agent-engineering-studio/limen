"""Misura dell'archivio «Merging» (#625-#629): copertura, richieste, bollettini, qualità, ore."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import rasterio
from dpc_radar.bulletins import Bulletin, Zone
from rasterio.transform import from_origin
from shapely.geometry import box

from limen.cli import misura_radar
from limen.cli.misura_radar import (
    Maschere,
    Ora,
    ZonaGiorno,
    bollettino_per,
    confronta_ore,
    copertura,
    fine_blocchi,
    giorni_completi,
    mappa_di_qualita,
    pioggia_di_zona,
    rapporto_del_giorno,
    richieste_al_giorno,
    righe_bollettini,
    righe_ore,
    righe_qualita,
    somma_del_giorno,
    zone_del_giorno,
)
from limen.integrations.arpa_lombardia import pluviometri
from limen.integrations.arpa_lombardia.pluviometri import Pluviometro
from limen.integrations.dpc import bollettini
from limen.integrations.dpc.merging_archive import MergingArchive, percorso

_G = date(2026, 10, 10)
_T = datetime(2026, 10, 10, 0, tzinfo=UTC)
#: La griglia finta: 20 pixel per 20 da 0,05° con l'angolo a 9°E 46°N (dentro la Lombardia).
_OVEST, _NORD, _PIXEL, _LATO = 9.0, 46.0, 0.05, 20


def _tif(path: Path, valori: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dati = np.broadcast_to(np.asarray(valori, dtype=np.float32), (_LATO, _LATO))
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=_LATO,
        height=_LATO,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(_OVEST, _NORD, _PIXEL, _PIXEL),
        nodata=-9999.0,
    ) as ds:
        ds.write(dati[np.newaxis])


def _giorno(cartella: Path, giorno: date, *, cum3: Any, srt1: Any) -> None:
    for t in fine_blocchi("CUM3", giorno):
        _tif(percorso(cartella, "CUM3", t), cum3)
    for t in fine_blocchi("SRT1", giorno):
        _tif(percorso(cartella, "SRT1", t), srt1)


def _zona(giorno: date, nome: str, livello: int, riquadro: tuple[float, ...]) -> Zone:
    return Zone(giorno, nome, livello, livello, 0, 0, (), box(*riquadro))


def test_i_fotogrammi_di_un_giorno_finiscono_a_mezzanotte() -> None:
    cum = fine_blocchi("CUM3", _G)
    assert len(cum) == 8
    assert (cum[0], cum[-1]) == (_T + timedelta(hours=3), _T + timedelta(hours=24))
    assert [t.hour for t in fine_blocchi("SRT1", _G)] == [*range(1, 24), 0]


def test_la_copertura_conta_presenti_persi_e_mancanti(tmp_path: Path) -> None:
    for ora in (3, 6, 12):
        _tif(percorso(tmp_path, "CUM3", _T + timedelta(hours=ora)), 1.0)
    (tmp_path / "CUM3" / "absent.txt").write_text("202610100900\nnon-una-data\n")
    (tmp_path / "CUM3" / "2026" / "10" / "10" / "CUM3_rotto.tif").write_bytes(b"")
    (voce,) = copertura(tmp_path)
    assert (voce.prodotto, voce.mese) == ("CUM3", "2026-10")
    assert (voce.attesi, voce.presenti, voce.persi) == (4, 3, 1)
    assert copertura(tmp_path / "vuota") == []


def test_le_richieste_al_giorno_si_contano_dalla_configurazione() -> None:
    voci = richieste_al_giorno(aree=20, sveglia_minuti=15, giro_minuti=60)
    assert [v[1:] for v in voci] == [(192, 96), (528, 48), (2, 2), (32, 32)]
    assert sum(v[1] for v in voci) == 754
    fitto = richieste_al_giorno(aree=1, sveglia_minuti=15, giro_minuti=10)
    assert fitto[1][2] == 96, "più di 48 cumulate nuove al giorno il DPC non ne pubblica"


def test_la_somma_del_giorno_vuole_tutti_i_fotogrammi(tmp_path: Path) -> None:
    valori = np.full((_LATO, _LATO), 2.0, dtype=np.float32)
    valori[0, 0] = -9999.0
    _giorno(tmp_path, _G, cum3=valori, srt1=0.5)
    archivio = MergingArchive(tmp_path)
    somma = somma_del_giorno(archivio, "CUM3", _G)
    assert somma is not None
    assert float(somma.data[5, 5]) == 16.0
    assert np.isnan(somma.data[0, 0]), "senza dato in un fotogramma, senza dato nel giorno"
    assert somma_del_giorno(archivio, "CUM3", _G + timedelta(days=1)) is None
    assert giorni_completi(tmp_path, "CUM3", None, None) == [_G]
    assert giorni_completi(tmp_path, "SRT1", _G + timedelta(days=1), None) == []
    percorso(tmp_path, "SRT1", _T + timedelta(hours=5)).unlink()
    assert giorni_completi(tmp_path, "SRT1", None, None) == []


def test_il_bollettino_di_un_giorno_e_l_ultimo_della_vigilia() -> None:
    nomi = [
        "20261008_1500_today.json",
        "20261009_1400_today.json",
        "20261009_1730_today.json",
        "20261010_1400_today.json",
    ]
    assert bollettino_per(nomi, _G) == "20261009_1730_today.json"
    assert bollettino_per(nomi, date(2026, 10, 8)) is None


def test_la_pioggia_di_zona_e_media_e_punto_peggiore(tmp_path: Path) -> None:
    valori = np.zeros((_LATO, _LATO), dtype=np.float32)
    valori[:, :10] = 1.0
    valori[3, 3] = 9.0
    _giorno(tmp_path, _G, cum3=valori, srt1=0.0)
    griglia = somma_del_giorno(MergingArchive(tmp_path), "CUM3", _G)
    assert griglia is not None
    zone = [
        _zona(_G, "Ovest", 2, (9.0, 45.0, 9.5, 46.0)),
        _zona(_G, "Est", 0, (9.5, 45.0, 10.0, 46.0)),
        _zona(_G + timedelta(days=1), "Domani", 3, (9.0, 45.0, 10.0, 46.0)),
        _zona(_G, "Altrove", 1, (12.0, 41.0, 13.0, 42.0)),
    ]
    maschere = Maschere()
    lette = zone_del_giorno(griglia, zone, _G, maschere)
    assert [(z.zona, z.livello) for z in lette] == [("Ovest", 2), ("Est", 0)]
    assert lette[0].massimo == 72.0
    assert lette[0].media == pytest.approx(8.0 + 64.0 / 200)
    assert (lette[1].media, lette[1].massimo) == (0.0, 0.0)
    assert zone_del_giorno(griglia, zone, _G, maschere) == lette


def test_una_zona_misurata_per_meno_di_meta_non_conta() -> None:
    valori = np.array([1.0, np.nan, np.nan, 3.0], dtype=np.float32)
    assert pioggia_di_zona(valori, np.array([0, 1, 2])) is None
    assert pioggia_di_zona(valori, np.array([0, 1, 3])) == (2.0, 3.0)


def test_il_report_dei_bollettini_affianca_colore_e_pioggia() -> None:
    zg = [
        ZonaGiorno(_G, "A", 0, 2.0, 80.0),
        ZonaGiorno(_G, "B", 0, 1.0, 5.0),
        ZonaGiorno(_G, "C", 2, 4.0, 8.0),
        ZonaGiorno(_G, "D", 3, 60.0, 140.0),
    ]
    testo = "\n".join(righe_bollettini(zg, 3))
    assert "| nessuna | 2 | 1.2 | 1.5 | 1.8 | 42.5 |" in testo
    assert "| gialla | 0 | — | — | — | — |" in testo
    assert "1 su 2 (50.0 %)" in testo
    assert "| 2026-10 | 1.5 (2) | — | 4.0 (1) | 60.0 (1) |" in testo
    assert "senza un bollettino della vigilia: 3" in testo
    assert "Nessun giorno da confrontare." in "\n".join(righe_bollettini([], 0))


def test_il_rapporto_si_calcola_solo_dove_e_piovuto() -> None:
    radar = np.array([5.0, 1.0, np.nan, 10.0])
    merging = np.array([10.0, 2.0, 20.0, 5.0])
    rapporto = rapporto_del_giorno(radar, merging)
    assert rapporto[0] == 0.5
    assert rapporto[3] == 2.0
    assert np.isnan(rapporto[1]), "sotto 5 mm il rapporto è rumore"
    assert np.isnan(rapporto[2])


def test_la_mappa_e_la_mediana_sui_giorni_piovosi() -> None:
    giorni = [np.array([v, v, np.nan]) for v in (0.2, 0.4, 0.9, 0.5, 0.6)]
    giorni.append(np.array([1.0, np.nan, np.nan]))
    mediana, conti = mappa_di_qualita(giorni)
    assert list(conti) == [6, 5, 0]
    assert mediana[0] == pytest.approx(0.55)
    assert mediana[1] == pytest.approx(0.5)
    assert np.isnan(mediana[2])
    poche, _ = mappa_di_qualita(giorni[:4])
    assert np.isnan(poche).all(), "sotto cinque giorni piovosi non c'è stima"


def test_il_report_della_qualita_elenca_i_blocchi_peggiori() -> None:
    mediana = np.full(int(np.prod(misura_radar._lato())), np.nan)
    conti = np.zeros(mediana.size, dtype=np.intp)
    mediana[:4] = [0.3, 0.8, 1.0, 1.7]
    conti[:4] = 9
    testo = "\n".join(righe_qualita(mediana, conti, 30, "mappa.tif"))
    assert "blocchi con una stima: **4**" in testo
    assert "sotto 0,5: 25.0 %; sopra 1,5: 25.0 %" in testo
    assert "| 6.05 | 47.95 | 0.30 | 9 |" in testo
    assert "`mappa.tif`" in testo
    vuoto = "\n".join(righe_qualita(np.array([]), np.array([], dtype=np.intp), 0, None))
    assert "Nessun blocco" in vuoto


def test_le_ore_si_confrontano_dove_ci_sono_tutte_e_tre() -> None:
    h1, h2, h3 = (_T + timedelta(hours=h) for h in (1, 2, 3))
    misurate: dict[datetime, list[float | None]] = {
        h1: [40.0, 0.0],
        h2: [2.0, None],
        h3: [5.0, 5.0],
    }
    radar: dict[datetime, list[float | None]] = {h1: [20.0, 0.2], h2: [1.0, 3.0]}
    ricostruite: dict[datetime, list[float | None]] = {
        h1: [35.0, 0.1],
        h2: [None, 3.0],
        h3: [5.0, 5.0],
    }
    assert confronta_ore(misurate, radar, ricostruite) == [Ora(0, 40.0, 20.0, 35.0)]


def test_il_report_delle_ore_da_errore_e_ore_forti() -> None:
    ore = [Ora(0, 40.0, 20.0, 35.0), Ora(1, 2.0, 31.0, 4.0)]
    testo = "\n".join(righe_ore(ore))
    assert "**2**, su **2** pluviometri" in testo
    assert "| solo radar (SRT1) | +4.50 | 24.50 | 0 su 1 | 1 |" in testo
    assert "| ora ricostruita | -1.50 | 3.50 | 1 su 1 | 0 |" in testo
    assert "Nessuna ora da confrontare." in "\n".join(righe_ore([]))


def _impostazioni(cartella: Path | str) -> SimpleNamespace:
    return SimpleNamespace(
        radar_archive=SimpleNamespace(
            cartella=str(cartella), attivo=bool(cartella), file_per_notte=1500
        ),
        nowcast=SimpleNamespace(interval_minutes=15),
        scheduler=SimpleNamespace(hourly_monitoring_minutes=60),
    )


async def test_il_comando_scrive_il_report_con_le_cinque_parti(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archivio = tmp_path / "archivio"
    for k in range(5):
        _giorno(archivio, _G + timedelta(days=k), cum3=3.0, srt1=0.5)
    _giorno(archivio, _G + timedelta(days=5), cum3=3.0, srt1=np.nan)
    percorso(archivio, "SRT1", _T + timedelta(days=5, hours=7)).unlink()

    async def _nomi() -> list[str]:
        return [f"202610{g:02d}_1500_today.json" for g in range(9, 14)]

    async def _scarica(nome: str) -> Bulletin:
        giorno = date(2026, 10, int(nome[6:8])) + timedelta(days=1)
        zone = [_zona(giorno, "Lario", 1, (9.0, 45.0, 10.0, 46.0))]
        return Bulletin(nome, datetime(2026, 10, 9, 15, tzinfo=UTC), zone)

    async def _pluviometri(_bbox: Any) -> list[Pluviometro]:
        return [Pluviometro("1", "Lecco", 9.42, 45.83, None, None)]

    async def _oraria(
        nodi: list[tuple[float, float]], start: datetime, end: datetime, **_kw: Any
    ) -> dict[datetime, list[float | None]]:
        ore = int((end - start).total_seconds() // 3600)
        return {start + timedelta(hours=h): [1.5] * len(nodi) for h in range(1, ore + 1)}

    monkeypatch.setattr(misura_radar, "get_settings", lambda: _impostazioni(archivio))
    monkeypatch.setattr(bollettini, "nomi", _nomi)
    monkeypatch.setattr(bollettini, "scarica", _scarica)
    monkeypatch.setattr(pluviometri, "pluviometri", _pluviometri)
    monkeypatch.setattr(pluviometri, "oraria", _oraria)
    monkeypatch.setenv("LIMEN_REPORTS_DIR", str(tmp_path / "reports"))

    assert await misura_radar.run() == 0

    report = tmp_path / "reports" / "misura_radar_2026-10-10_2026-10-15.md"
    testo = report.read_text()
    assert "Giorni con tutte le CUM3: **6**" in testo
    assert "con anche tutte le SRT1: **5**" in testo
    assert "| CUM3 | 2026-10 | 48 | 48 | 0 | 0 |" in testo
    assert "| SRT1 | 2026-10 | 144 | 143 | 0 | 1 |" in testo
    assert "| **totale** | **754** | **178** |" in testo
    assert "Giorni confrontati: **5**; zone-giorno: **5**" in testo
    assert "senza un bollettino della vigilia: 1" in testo
    assert "| gialla | 5 | 24.0 | 24.0 | 24.0 | 24.0 |" in testo
    assert "rapporto: mediana **0.50**" in testo
    assert "**120**, su **1** pluviometri" in testo
    assert "| solo radar (SRT1) | -1.00 | 1.00 | 0 su 0 | 0 |" in testo
    assert "| ora ricostruita | -0.50 | 0.50 | 0 su 0 | 0 |" in testo
    assert report.with_suffix(".provenienza.json").exists()
    with rasterio.open(report.with_suffix(".qualita.tif")) as mappa:
        assert mappa.count == 2
        assert float(np.nanmax(mappa.read(1))) == pytest.approx(0.5)
        assert float(mappa.read(2).max()) == 5.0


async def test_il_comando_si_ferma_senza_archivio_o_con_una_misura_ignota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(misura_radar, "get_settings", lambda: _impostazioni(""))
    assert await misura_radar.run() == 1
    monkeypatch.setattr(misura_radar, "get_settings", lambda: _impostazioni(tmp_path))
    monkeypatch.setenv("LIMEN_RADAR_MISURE", "copertura,meteo")
    assert await misura_radar.run() == 2
    monkeypatch.setenv("LIMEN_RADAR_MISURE", "copertura,richieste,qualita,ore,bollettini")
    monkeypatch.setenv("LIMEN_REPORTS_DIR", str(tmp_path / "reports"))

    async def _nessuno() -> list[str]:
        return []

    monkeypatch.setattr(bollettini, "nomi", _nessuno)
    assert await misura_radar.run() == 0
    testo = (tmp_path / "reports" / "misura_radar_vuoto.md").read_text()
    assert "L'archivio è vuoto." in testo
    assert "Nessun blocco con abbastanza giorni piovosi." in testo


def test_una_griglia_in_metri_cade_sugli_stessi_blocchi() -> None:
    from dpc_radar import RainGrid
    from dpc_radar.products import SRT1
    from rasterio.crs import CRS

    dati = np.zeros((2, 2), dtype=np.float32)
    gradi = RainGrid(SRT1, _T, dati, from_origin(9.0, 46.0, 0.05, 0.05), CRS.from_epsg(4326))
    # Lo stesso angolo in UTM 32N (9°E è il meridiano centrale), pixel da 1 km.
    metri = RainGrid(
        SRT1, _T, dati, from_origin(500_000, 5_094_000, 1000, 1000), CRS.from_epsg(32632)
    )
    in_gradi = misura_radar.blocco_dei_pixel(gradi)
    assert in_gradi[0] == 20 * 130 + 30
    assert misura_radar.blocco_dei_pixel(metri)[0] == in_gradi[0]
    lontano = RainGrid(SRT1, _T, dati, from_origin(30.0, 60.0, 0.05, 0.05), CRS.from_epsg(4326))
    assert set(misura_radar.blocco_dei_pixel(lontano)) == {-1}
