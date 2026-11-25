"""L'archivio orario dei pluviometri regionali (migrazione 099): passo notturno e CLI.

Due fonti, ciascuna riscritta un mese alla volta, dal più recente:

* **Meteotrentino**: un mese si rilegge solo se è cambiato lo SHA-256 del suo
  file nel manifest, o del mese dopo, che porta l'ultima ora del mese (le
  etichette sono di fine intervallo). Così la validazione, che arriva dopo più
  di un anno e cambia i codici di qualità, rientra da sola.
* **ARPA Lombardia**: il portale non dà impronte, quindi i due mesi più recenti
  si rileggono ogni notte e lo storico una volta; l'impronta della pioggia letta
  (``dataset_versions``) evita di riscrivere un mese uguale.

Lo storico si recupera ``mesi_per_notte`` mesi alla volta per fonte: un server
nuovo lo completa in poche notti senza tenere ferma la pipeline;
``LIMEN_PLUVIOMETRI_TUTTI=1`` lo fa in una volta sola.

Una fonte che non risponde si salta e lo dice (``integration.degraded``): il
mese non registrato si riprova la notte dopo. Un mese che risponde vuoto si
salta senza fermare gli altri: le fonti hanno buchi veri (la Lombardia non
pubblica dal 1° marzo al 25 aprile 2026), e fermarsi lì bloccherebbe per sempre
lo storico più vecchio. Il mese vuoto conta nel limite della notte, così una
fonte che risponde vuoto a tutto non fa scorrere ogni notte l'intero archivio.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta

import httpx

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.repos import dataset_versions_repo, pluviometri_repo
from limen.data.repos.pluviometri_repo import GiornoPioggia, Stazione, id_di, per_giorno
from limen.integrations.arpa_lombardia import pluviometri as lombardia
from limen.integrations.arpa_lombardia.pluviometri import Pluviometro
from limen.integrations.meteotrentino import pluviometri as trentino

log = get_logger(__name__)

TRENTINO = "meteotrentino"
LOMBARDIA = "arpa_lombardia"
_TUTTA = (-180.0, -90.0, 180.0, 90.0)
#: Sensori per richiesta al portale lombardo: l'elenco va nell'URL.
_BLOCCO_SENSORI = 80
#: I mesi lombardi che si rileggono ogni notte anche se già archiviati.
_MESI_RECENTI = 2


def mesi(dal_anno: int, oggi: date) -> list[tuple[int, int]]:
    """``(anno, mese)`` da ``oggi`` indietro fino a gennaio di ``dal_anno``."""
    out = []
    anno, mese = oggi.year, oggi.month
    while anno >= dal_anno:
        out.append((anno, mese))
        anno, mese = (anno - 1, 12) if mese == 1 else (anno, mese - 1)
    return out


def _confini_utc(anno: int, mese: int) -> tuple[datetime, datetime]:
    dopo = (anno + 1, 1) if mese == 12 else (anno, mese + 1)
    return datetime(anno, mese, 1, tzinfo=UTC), datetime(*dopo, 1, tzinfo=UTC)


def _stazione(fonte: str, p: Pluviometro) -> Stazione:
    return Stazione(
        id=id_di(fonte, p.idsensore),
        fonte=fonte,
        codice=p.idsensore,
        nome=p.nome,
        lon=p.lon,
        lat=p.lat,
        quota_m=p.quota_m,
        dal=p.dal,
        al=p.al,
    )


def _attivi(stazioni: list[Pluviometro], start: datetime, end: datetime) -> list[str]:
    return sorted(
        p.idsensore
        for p in stazioni
        if (p.dal is None or p.dal <= end.date()) and (p.al is None or p.al >= start.date())
    )


def _vuoto_sospetto(
    fonte: str, dataset: str, sensori: list[str], giorni: list[GiornoPioggia]
) -> bool:
    """Sensori attivi e nemmeno un giorno misurato: è la fonte che non ha risposto
    davvero (manutenzione, dataset vuoto), non un mese senza misure. Riscriverlo
    cancellerebbe i giorni buoni già archiviati."""
    if sensori and not giorni:
        log.warning(
            "integration.degraded", source=fonte, mese=dataset, error="nessuna ora misurata"
        )
        return True
    return False


async def _scrivi(fonte: str, anno: int, mese: int, giorni: list[GiornoPioggia]) -> int:
    start, end = _confini_utc(anno, mese)
    return await pluviometri_repo.sostituisci(
        fonte, start.date(), (end - timedelta(days=1)).date(), giorni
    )


async def _mese_trentino(
    anno: int,
    mese: int,
    sensori: list[str],
    percorso: str,
    seguente: str | None,
) -> list[GiornoPioggia]:
    da, a = trentino.confini_mese(anno, mese)
    ore = trentino.ore_del_file((await trentino.scarica(percorso)).content, sensori, da=da, a=a)
    if seguente is not None:
        da, a = trentino.confini_mese(*((anno + 1, 1) if mese == 12 else (anno, mese + 1)))
        ore += trentino.ore_del_file(
            (await trentino.scarica(seguente)).content, sensori, da=da, a=a
        )
    start, end = _confini_utc(anno, mese)
    per_sensore = trentino.ore_dai_cinque_minuti(ore, sensori=sensori, start=start, end=end)
    validata: dict[tuple[str, date], bool | None] = {}
    for o in ore:
        chiave = (id_di(TRENTINO, o.stazione), (o.ora - timedelta(hours=1)).date())
        validata[chiave] = validata.get(chiave, True) is True and o.teletrasmesse == 0
    return per_giorno(per_sensore, [id_di(TRENTINO, s) for s in sensori], validata)


async def sincronizza_trentino(*, dal_anno: int, limite: int | None) -> dict[str, int | str]:
    stazioni = await trentino.pluviometri(_TUTTA)
    if not stazioni:
        return {"stato": "degradato"}
    await pluviometri_repo.salva_stazioni([_stazione(TRENTINO, p) for p in stazioni])
    try:
        manifest = (await trentino.scarica(trentino.MANIFEST)).json()["files"]
        per_mese = {
            (int(v["year"]), int(v["month"])): (percorso, str(v["sha256"]))
            for percorso, v in manifest.items()
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.warning("integration.degraded", source=TRENTINO, error=str(exc))
        return {"stato": "degradato", "stazioni": len(stazioni)}
    conti: dict[str, int | str] = {"stazioni": len(stazioni), "mesi": 0, "giorni": 0, "uguali": 0}
    for anno, mese in mesi(dal_anno, datetime.now(UTC).date()):
        if (anno, mese) not in per_mese:
            continue
        percorso, impronta = per_mese[(anno, mese)]
        seguente = per_mese.get((anno + 1, 1) if mese == 12 else (anno, mese + 1))
        versione = f"{impronta}:{seguente[1] if seguente else ''}"
        dataset = f"pluviometri/{anno}-{mese:02d}"
        if await dataset_versions_repo.find(TRENTINO, dataset, versione) is not None:
            conti["uguali"] = int(conti["uguali"]) + 1
            continue
        if limite is not None and int(conti["mesi"]) >= limite:
            break
        start, end = _confini_utc(anno, mese)
        sensori = _attivi(stazioni, start, end)
        try:
            giorni = await _mese_trentino(
                anno, mese, sensori, percorso, seguente[0] if seguente else None
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning(
                "integration.degraded",
                source=TRENTINO,
                mese=dataset,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            conti["stato"] = "degradato"
            break
        conti["mesi"] = int(conti["mesi"]) + 1
        if _vuoto_sospetto(TRENTINO, dataset, sensori, giorni):
            conti["vuoti"] = int(conti.get("vuoti", 0)) + 1
            continue
        conti["giorni"] = int(conti["giorni"]) + await _scrivi(TRENTINO, anno, mese, giorni)
        await dataset_versions_repo.record(
            source=TRENTINO, dataset=dataset, version=versione, metadata={"giorni": len(giorni)}
        )
    return conti


def _impronta(giorni: list[GiornoPioggia]) -> str:
    righe = [[g.pluviometro_id, g.giorno.isoformat(), list(g.mm)] for g in giorni]
    return dataset_versions_repo.content_hash([json.dumps(righe, sort_keys=True)])


async def sincronizza_lombardia(*, dal_anno: int, limite: int | None) -> dict[str, int | str]:
    stazioni = await lombardia.pluviometri(_TUTTA)
    if not stazioni:
        return {"stato": "degradato"}
    await pluviometri_repo.salva_stazioni([_stazione(LOMBARDIA, p) for p in stazioni])
    conti: dict[str, int | str] = {"stazioni": len(stazioni), "mesi": 0, "giorni": 0, "uguali": 0}
    for k, (anno, mese) in enumerate(mesi(dal_anno, datetime.now(UTC).date())):
        dataset = f"pluviometri/{anno}-{mese:02d}"
        recente = k < _MESI_RECENTI
        if not recente and await dataset_versions_repo.latest(LOMBARDIA, dataset) is not None:
            continue
        if limite is not None and int(conti["mesi"]) >= limite + _MESI_RECENTI:
            break
        start, end = _confini_utc(anno, mese)
        sensori = _attivi(stazioni, start, end)
        ore: dict[datetime, list[float | None]] = {}
        try:
            for i in range(0, len(sensori), _BLOCCO_SENSORI):
                blocco = await lombardia.orarie(sensori[i : i + _BLOCCO_SENSORI], start, end)
                for ora, valori in blocco.items():
                    ore.setdefault(ora, []).extend(valori)
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            log.warning(
                "integration.degraded",
                source=LOMBARDIA,
                mese=dataset,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            conti["stato"] = "degradato"
            break
        giorni = per_giorno(ore, [id_di(LOMBARDIA, s) for s in sensori])
        conti["mesi"] = int(conti["mesi"]) + 1
        if _vuoto_sospetto(LOMBARDIA, dataset, sensori, giorni):
            conti["vuoti"] = int(conti.get("vuoti", 0)) + 1
            continue
        versione = _impronta(giorni)
        if await dataset_versions_repo.find(LOMBARDIA, dataset, versione) is not None:
            conti["uguali"] = int(conti["uguali"]) + 1
            continue
        conti["giorni"] = int(conti["giorni"]) + await _scrivi(LOMBARDIA, anno, mese, giorni)
        await dataset_versions_repo.record(
            source=LOMBARDIA, dataset=dataset, version=versione, metadata={"giorni": len(giorni)}
        )
    return conti


async def sincronizza(*, dal_anno: int, limite: int | None) -> dict[str, dict[str, int | str]]:
    return {
        TRENTINO: await sincronizza_trentino(dal_anno=dal_anno, limite=limite),
        LOMBARDIA: await sincronizza_lombardia(dal_anno=dal_anno, limite=limite),
    }


async def run() -> int:
    """``limen pluviometri-sync``: lo stesso passo del notturno, a mano."""
    cfg = get_settings().pluviometri
    tutti = os.environ.get("LIMEN_PLUVIOMETRI_TUTTI", "").strip().lower() in {"1", "true", "yes"}
    async with lifespan_pool():
        conti = await sincronizza(
            dal_anno=cfg.dal_anno, limite=None if tutti else cfg.mesi_per_notte
        )
    log.info("pluviometri_sync.done", **{f: str(c) for f, c in conti.items()})
    return 0
