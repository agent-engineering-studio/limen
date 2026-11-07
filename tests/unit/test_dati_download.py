"""I download dei dati statici nel worker (#402).

Il consumatore è il pezzo che chi installa non vede ma da cui dipende tutto
quello che vede: una voce che resta `in_corso` dopo un errore, o un errore
scritto come un traceback, è una pagina di installazione che mente.
"""

from __future__ import annotations

import argparse
import asyncio
import errno
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from limen.api.jobs import dati_download as dd
from limen.cli import dati as cli_dati
from limen.config.catalogo_dati import carica_catalogo


def test_ogni_voce_che_si_scarica_ha_un_procuratore() -> None:
    """Una voce del catalogo senza procuratore resterebbe in coda per sempre
    sulla pagina, come se il download stesse partendo."""
    catalogo = carica_catalogo()
    proc = dd.procuratori()
    scaricabili = {v.id for v in catalogo.voci if v.deriva_da is None}
    assert set(proc) == scaricabili


def test_misura_byte_somma_file_e_cartelle(tmp_path: Path) -> None:
    (tmp_path / "a.zip").write_bytes(b"x" * 10)
    (tmp_path / "a.zip.part").write_bytes(b"x" * 5)
    cartella = tmp_path / "dtm"
    (cartella / "sotto").mkdir(parents=True)
    (cartella / "sotto" / "f.tif").write_bytes(b"x" * 7)
    percorsi = [tmp_path / "a.zip", tmp_path / "a.zip.part", cartella, tmp_path / "manca"]
    assert dd.misura_byte(percorsi) == 22


def _http(codice: int) -> httpx.HTTPStatusError:
    richiesta = httpx.Request("GET", "https://example.org/f.zip")
    return httpx.HTTPStatusError(
        "x", request=richiesta, response=httpx.Response(codice, request=richiesta)
    )


@pytest.mark.parametrize(
    ("exc", "frammento"),
    [
        (_http(404), "errore 404"),
        (_http(403), "serve una chiave"),
        (_http(429), "troppe richieste"),
        (_http(503), "riprova più tardi"),
        (httpx.ConnectTimeout("t"), "non ha risposto in tempo"),
        (httpx.ConnectError("c"), "accesso a Internet"),
        (PermissionError(13, "negato", "/data/dtm"), "/data/dtm"),
        (OSError(errno.ENOSPC, "pieno"), "Spazio su disco esaurito"),
        (RuntimeError("DTM: servono 22.1 GB"), "DTM: servono 22.1 GB"),
        (dd.DownloadFallitoError("3 file su 105"), "3 file su 105"),
        (KeyError("x"), "log del worker"),
    ],
)
def test_ogni_errore_diventa_una_frase_per_chi_installa(exc: BaseException, frammento: str) -> None:
    testo = dd.messaggio(exc, "ISPRA IdroGEO")
    assert frammento in testo
    assert "Traceback" not in testo


class _Coda:
    """La coda in memoria al posto del repo."""

    def __init__(self, voci: list[str]) -> None:
        self.voci = list(voci)
        self.chiuse: dict[str, str | None] = {}
        self.avanzamenti: list[tuple[str, int]] = []
        self.accodate: list[str] = []

    async def accoda(self, voci: list[str], *, byte_totali: dict[str, int]) -> list[str]:
        self.accodate.extend(voci)
        self.voci.extend(voci)
        return voci

    async def prendi_prossima(self) -> str | None:
        return self.voci.pop(0) if self.voci else None

    async def avanza(self, voce: str, byte_fatti: int) -> None:
        self.avanzamenti.append((voce, byte_fatti))

    async def chiudi(self, voce: str, *, errore: str | None, byte_fatti: int | None = None) -> None:
        self.chiuse[voce] = errore


@pytest.fixture
def coda(monkeypatch: pytest.MonkeyPatch) -> _Coda:
    c = _Coda(["iffi", "dtm", "wui"])
    for nome in ("prendi_prossima", "avanza", "chiudi", "accoda"):
        monkeypatch.setattr(dd.repo, nome, getattr(c, nome))
    monkeypatch.setattr(dd.repo, "blocco_download", _blocco(libero=True))
    return c


def _blocco(*, libero: bool) -> Any:
    @asynccontextmanager
    async def blocco() -> AsyncIterator[bool]:
        yield libero

    return blocco


async def _niente() -> None:
    return None


async def _nessuna_elaborazione() -> None:
    raise AssertionError("non doveva partire")


async def test_la_coda_si_svuota_e_ogni_voce_si_chiude(coda: _Coda, tmp_path: Path) -> None:
    scritto = tmp_path / "f.part"

    async def ok() -> None:
        scritto.write_bytes(b"x" * 100)
        await asyncio.sleep(0.05)

    async def rotto() -> None:
        raise _http(503)

    consumatore = dd.ConsumatoreDownload(
        da_procurare={
            "iffi": dd.Procuratore(ok, lambda: [scritto]),
            "dtm": dd.Procuratore(rotto, list),
        },
        intervallo_s=0.01,
        elabora=_niente,
    )
    await consumatore.svuota_coda()

    assert coda.chiuse["iffi"] is None
    assert "errore 503" in (coda.chiuse["dtm"] or "")
    # Una voce derivata non si scarica: si chiude con la spiegazione, non resta in coda.
    assert "calcola da un altro" in (coda.chiuse["wui"] or "")
    assert ("iffi", 100) in coda.avanzamenti


async def test_un_errore_non_ferma_le_voci_dopo(coda: _Coda) -> None:
    fatte: list[str] = []

    async def esplode() -> None:
        raise KeyError("x")

    async def ok() -> None:
        fatte.append("dtm")

    consumatore = dd.ConsumatoreDownload(
        da_procurare={"iffi": dd.Procuratore(esplode, list), "dtm": dd.Procuratore(ok, list)},
        elabora=_niente,
    )
    await consumatore.svuota_coda()
    assert fatte == ["dtm"]
    assert coda.chiuse["iffi"] is not None


def _args(**kw: Any) -> argparse.Namespace:
    return argparse.Namespace(**({"voci": [], "essenziali": False, "tutte": False} | kw))


def test_la_cli_sceglie_le_voci_giuste() -> None:
    catalogo = carica_catalogo()
    tutte = cli_dati.scelte(_args(tutte=True), catalogo)
    assert "wui" not in tutte
    assert "dtm" in tutte
    essenziali = cli_dati.scelte(_args(essenziali=True), catalogo)
    assert "strade" not in essenziali
    assert "perimetri_effis" not in essenziali
    assert cli_dati.scelte(_args(voci=["dtm"]), catalogo) == ["dtm"]
    with pytest.raises(SystemExit, match="sconosciuta"):
        cli_dati.scelte(_args(voci=["meteo"]), catalogo)
    with pytest.raises(SystemExit, match="calcola"):
        cli_dati.scelte(_args(voci=["wui"]), catalogo)


async def test_con_un_altro_download_in_corso_non_si_tocca_niente(
    coda: _Coda, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`make static-data` dall'host e il worker sullo stesso `.part` mescolano i
    byte: chi trova il lock occupato rinuncia e lo dice."""
    monkeypatch.setattr(dd.repo, "blocco_download", _blocco(libero=False))
    partito: list[str] = []

    async def scarica() -> None:
        partito.append("iffi")

    consumatore = dd.ConsumatoreDownload(da_procurare={"iffi": dd.Procuratore(scarica, list)})
    await consumatore.esegui("iffi")
    assert partito == []
    assert "make static-data" in (coda.chiuse["iffi"] or "")


async def test_il_dtm_rielaborato_non_si_riscarica(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Con il VRT di `make dtm-vrt` il worker non deve chiedere 22 GB a Zenodo."""
    from limen.integrations.geoserver_source import dati_base

    (tmp_path / "dtm").mkdir()
    (tmp_path / "dtm" / "dtm5m.vrt").write_text("<VRTDataset/>")
    monkeypatch.setenv("GEOSERVER_SHAPEFILE_DIR", str(tmp_path))

    async def mai(_: Path) -> bool:
        raise AssertionError("ha provato a scaricare il DTM")

    monkeypatch.setattr(dati_base, "dtm", mai)
    await dd.procuratori()["dtm"].scarica()


def test_un_catalogo_rotto_non_ferma_il_costruttore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il catalogo si carica nel ciclo protetto, non quando il worker crea il
    consumatore: un `dati.yaml` malformato non deve fermare lo sweep orario."""

    def rotto() -> None:
        raise ValueError("dati.yaml malformato")

    monkeypatch.setattr(dd, "carica_catalogo", rotto)
    monkeypatch.setattr(dd, "procuratori", rotto)
    dd.ConsumatoreDownload()


async def test_dopo_i_download_i_dati_entrano_nelle_celle_una_volta_sola(coda: _Coda) -> None:
    """Un file scaricato non è ancora un dato: senza questo passo la pagina resta
    rossa dopo ogni download, e chi installa non ha un comando da lanciare."""
    giri: list[int] = []

    async def elabora() -> None:
        giri.append(1)

    consumatore = dd.ConsumatoreDownload(
        da_procurare={v: dd.Procuratore(_niente, list) for v in ("iffi", "dtm")},
        elabora=elabora,
    )
    await consumatore.svuota_coda()
    assert giri == [1]
    assert coda.chiuse[dd.repo.ELABORAZIONE] is None


async def test_se_nessun_download_riesce_non_si_elabora(
    coda: _Coda, monkeypatch: pytest.MonkeyPatch
) -> None:
    coda.voci[:] = ["wui"]
    consumatore = dd.ConsumatoreDownload(da_procurare={}, elabora=_nessuna_elaborazione)
    await consumatore.svuota_coda()
    assert coda.accodate == []


async def test_un_elaborazione_fallita_lo_dice_e_si_puo_rifare(coda: _Coda) -> None:
    async def rotta() -> None:
        raise dd.DownloadFallitoError("Non è riuscito: calibrate.")

    await dd.ConsumatoreDownload(da_procurare={}, elabora=rotta).elabora()
    assert "calibrate" in (coda.chiuse[dd.repo.ELABORAZIONE] or "")


async def test_col_lock_occupato_non_si_elabora(
    coda: _Coda, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dd.repo, "blocco_download", _blocco(libero=False))
    await dd.ConsumatoreDownload(da_procurare={}, elabora=_nessuna_elaborazione).elabora()
    assert "riprova" in (coda.chiuse[dd.repo.ELABORAZIONE] or "")


async def test_un_passo_fallito_non_ferma_gli_altri(monkeypatch: pytest.MonkeyPatch) -> None:
    """La calibrazione deve girare anche se un download non è entrato, e il
    motivo che arriva alla pagina nomina il passo."""
    passi: list[tuple[str, dict[str, str]]] = []

    async def finto(nome: str, *comando: str, ambiente: dict[str, str]) -> str | None:
        passi.append((nome, ambiente))
        return nome if nome == "ingest-events" else None

    monkeypatch.setattr(dd, "_esegui_passo", finto)
    with pytest.raises(dd.DownloadFallitoError, match="ingest-events"):
        await dd.elabora_dati()
    assert [p for p, _ in passi][:4] == [
        "fattori per cella",
        "seed-comuni",
        "ingest-events",
        "calibrate",
    ]
    # Non riscarica: i file li ha portati la coda, e solo quelli chiesti.
    assert passi[0][1]["LIMEN_STATICI"] == "qui"
    assert passi[0][1]["LIMEN_STATICI_SCARICA"] == "0"


@pytest.mark.parametrize(("archivio", "attesa"), [("", False), ("http://openmeteo:8080", True)])
async def test_la_catena_fwi_solo_con_un_istanza_propria(
    monkeypatch: pytest.MonkeyPatch, archivio: str, attesa: bool
) -> None:
    """Sull'API pubblica l'archivio consumerebbe il tetto giornaliero dello sweep."""
    passi: list[str] = []

    async def finto(nome: str, *comando: str, ambiente: dict[str, str]) -> str | None:
        passi.append(nome)
        return None

    class _Finti:
        class openmeteo:  # noqa: N801
            archive_url = archivio

    monkeypatch.setattr(dd, "_esegui_passo", finto)
    monkeypatch.setattr(dd, "get_settings", _Finti)
    await dd.elabora_dati()
    assert ("fwi-backfill" in passi) is attesa


async def test_il_passo_riporta_il_codice_del_processo() -> None:
    assert await dd._esegui_passo("ok", "true", ambiente={}) is None
    assert await dd._esegui_passo("rotto", "false", ambiente={}) == "rotto"


def _fatta(voce: str) -> Any:
    from datetime import UTC, datetime

    adesso = datetime(2026, 11, 7, tzinfo=UTC)
    return dd.repo.StatoDownload(
        voce=voce,
        stato="fatto",
        byte_fatti=0,
        byte_totali=None,
        richiesto_il=adesso,
        avviato_il=adesso,
        aggiornato_il=adesso,
        finito_il=adesso,
        errore=None,
        tentativi=1,
    )


async def test_una_regione_aggiunta_si_semina_e_poi_entra_nelle_celle(
    coda: _Coda, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#407: una regione aggiunta dalla pagina ha celle vuote finché
    l'elaborazione non le riempie; e se l'inventario frane c'era, servono
    anche i suoi file."""
    import limen.cli.seed as seed

    seminate: list[str] = []

    async def semina(aois: Any) -> None:
        seminate.extend(a.id for a in aois)

    async def elenco() -> list[Any]:
        return [_fatta("iffi")]

    monkeypatch.setattr(seed, "semina", semina)
    monkeypatch.setattr(dd.repo, "elenco", elenco)
    coda.voci[:] = ["regione:it-lazio"]
    giri: list[int] = []

    async def elabora() -> None:
        giri.append(1)

    consumatore = dd.ConsumatoreDownload(
        da_procurare={"iffi": dd.Procuratore(_niente, list)}, elabora=elabora
    )
    await consumatore.svuota_coda()

    assert seminate == ["it-lazio"]
    assert coda.chiuse["regione:it-lazio"] is None
    assert coda.accodate[0] == "iffi"
    assert coda.chiuse["iffi"] is None
    assert giri == [1]


async def test_una_regione_sconosciuta_si_chiude_in_errore_e_non_elabora(
    coda: _Coda, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def elenco() -> list[Any]:
        return []

    monkeypatch.setattr(dd.repo, "elenco", elenco)
    coda.voci[:] = ["regione:it-atlantide"]
    consumatore = dd.ConsumatoreDownload(da_procurare={}, elabora=_nessuna_elaborazione)
    await consumatore.svuota_coda()
    assert "it-atlantide" in (coda.chiuse["regione:it-atlantide"] or "")
    assert coda.accodate == []


def test_le_aree_iffi_seguono_le_regioni_e_il_trentino_ha_due_province() -> None:
    from limen.integrations.idrogeo.geodati import AREE, aree_iffi

    assert aree_iffi([16, 4]) == ("puglia", "bolzano", "trento")
    assert set(aree_iffi(range(1, 21))) == set(AREE)
