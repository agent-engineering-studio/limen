"""``limen misura-radar``, parte «adozione» (#643): che cosa farebbero gli usi del radar spenti.

Gli usi di dpc-radar che toccherebbero i punteggi sono nel codice ma spenti
(``pluvial.observed.blind|rarity|nowcast`` in ``flood.yaml``,
``NOWCAST__BIAS_CORRECTION``). Qui si misura, sugli eventi verificati di
``verifiche_eventi`` e su un campione di giorni qualunque, che cosa
cambierebbe accendendoli. Solo misura: niente si scrive, niente cambia nei
motori. I fotogrammi vengono dall'API del DPC (CUM24 e SRT1 circa cinque mesi,
SRI almeno due): poche centinaia di richieste, una volta.

* **cieco**: le celle di Limen dove il radar vede male (``reliability`` sotto
  0,5) e gli eventi che ci cadono;
* **rarità**: il tempo di ritorno della pioggia caduta entro 5 km dall'evento,
  contro la quota di celle-giorno qualunque sopra lo stesso tempo di ritorno
  (il tasso di base: senza, una regola che accende tutto sembra perfetta);
* **nowcast**: sugli eventi con l'ora nota, i mm che il nowcast a 60 minuti
  dava ora per ora contro quelli che il radar ha poi misurato (SRT1);
* **bias**: i pixel della sveglia (≥ ``NOWCAST__MIN_INTENSITY_MMH``) entro
  0,5° dall'evento e sull'Italia, con e senza la correzione.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import numpy as np
from dpc_radar import DpcRadarError, RainGrid, correct, rain_ahead, reliability_map, return_period
from dpc_radar.reliability import RELIABLE_FROM

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.dpc.client import _download

log = get_logger(__name__)

#: L'intorno dell'evento: il comune è un punto, la pioggia che lo ha colpito no.
_INTORNO_DEG = 0.05
#: Le soglie di tempo di ritorno lette sugli eventi e sul tasso di base, anni.
SOGLIE_ANNI = (2.0, 5.0, 20.0)
#: Una cella ogni tanti per il tasso di base: 312.000 celle per giorno sono troppe.
_PASSO_CELLE = 10
_NOWCAST_MINUTI = 60
_PASSO_SRI = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class Evento:
    slug: str
    hazard: str
    at: datetime
    precisione: str
    lon: float
    lat: float


#: Il caso da cui nasce l'osservata (#199): Melito di Porto Salvo, 10/10/2026,
#: 20 mm previsti e 152 caduti. Non è in `verifiche_eventi`, e ogni misura del
#: radar deve dire che cosa ne fa.
RIFERIMENTI = (
    Evento(
        "2026-10-10-alluvione-melito (riferimento #199)",
        "flood",
        datetime(2026, 10, 10, 6, tzinfo=UTC),
        "T1",
        15.78,
        37.92,
    ),
)


@dataclass(frozen=True, slots=True)
class EsitoEvento:
    evento: Evento
    affidabilita: float | None
    pioggia_24h_mm: float | None
    ritorno_anni: float | None


@dataclass(frozen=True, slots=True)
class OraNowcast:
    slug: str
    ora: datetime
    previsti_mm: float | None
    caduti_mm: float | None
    sveglia_px: int
    sveglia_corretta_px: int


async def eventi(dal: date, al: date) -> list[Evento]:
    """Gli eventi verificati con un punto, più i riferimenti che cadono nel periodo."""
    return [
        *(r for r in RIFERIMENTI if dal <= r.at.date() <= al),
        *await _verificati(dal, al),
    ]


async def _verificati(dal: date, al: date) -> list[Evento]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT slug, hazard_type::text AS hazard, evento_at, precisione_ora,
                   ST_X(geom) AS lon, ST_Y(geom) AS lat
            FROM verifiche_eventi
            WHERE geom IS NOT NULL AND hazard_type IN ('flood', 'landslide')
              AND evento_at >= $1 AND evento_at < $2
            ORDER BY evento_at
            """,
            datetime.combine(dal, time(), UTC),
            datetime.combine(al + timedelta(days=1), time(), UTC),
        )
    return [
        Evento(r["slug"], r["hazard"], r["evento_at"], r["precisione_ora"], r["lon"], r["lat"])
        for r in rows
    ]


async def celle_campione() -> list[tuple[float, float]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT ST_X(centroid) AS lon, ST_Y(centroid) AS lat FROM grid_cells ORDER BY id"
        )
    return [(r["lon"], r["lat"]) for r in rows[::_PASSO_CELLE]]


def _intorno(lon: float, lat: float) -> tuple[float, float, float, float]:
    return (lon - _INTORNO_DEG, lat - _INTORNO_DEG, lon + _INTORNO_DEG, lat + _INTORNO_DEG)


def massimo_intorno(grid: RainGrid, lon: float, lat: float) -> float | None:
    try:
        parte = grid.crop(_intorno(lon, lat)).data
    except DpcRadarError:
        return None
    return float(np.nanmax(parte)) if np.isfinite(parte).any() else None


def intorno_massimo(grid: RainGrid, valori: np.ndarray) -> RainGrid:
    """Ogni pixel prende il massimo entro ``_INTORNO_DEG``: la stessa lettura degli eventi.

    Sugli eventi conta la pioggia più rara entro 5 km dal punto; contare il
    tasso di base sul solo pixel della cella gonfierebbe il confronto a favore
    della regola.
    """
    from scipy.ndimage import maximum_filter

    lato = 2 * round(_INTORNO_DEG / abs(grid.transform.a)) + 1
    pieno = maximum_filter(np.nan_to_num(valori, nan=-1.0), size=lato, mode="nearest")
    return replace(grid, data=np.where(pieno < 0, np.nan, pieno))


def fine_finestra(e: Evento) -> datetime:
    """La CUM24 che contiene l'evento: alla mezz'ora dopo se l'ora è nota, a fine giorno se no."""
    if e.precisione == "T3":
        return datetime.combine(e.at.astimezone(UTC).date() + timedelta(days=1), time(), UTC)
    minuti = 30 - e.at.minute % 30
    return (e.at + timedelta(minutes=minuti)).replace(second=0, microsecond=0)


async def esito_evento(e: Evento) -> EsitoEvento:
    rmap = reliability_map()
    affid = rmap.at(e.lon, e.lat).score
    cum = await _download("CUM24", at=fine_finestra(e))
    if cum is None:
        return EsitoEvento(e, affid, None, None)
    anni = replace(cum, data=return_period(cum))
    return EsitoEvento(
        e, affid, massimo_intorno(cum, e.lon, e.lat), massimo_intorno(anni, e.lon, e.lat)
    )


async def base_rarita(giorni: list[date], celle: list[tuple[float, float]]) -> dict[str, Any]:
    """Quante celle-giorno qualunque passano ogni soglia di tempo di ritorno."""
    sopra = dict.fromkeys(SOGLIE_ANNI, 0)
    misurate = 0
    usati = 0
    for g in giorni:
        cum = await _download("CUM24", at=datetime.combine(g + timedelta(days=1), time(), UTC))
        if cum is None:
            continue
        usati += 1
        anni = [a for a in intorno_massimo(cum, return_period(cum)).sample(celle) if a is not None]
        misurate += len(anni)
        for s in SOGLIE_ANNI:
            sopra[s] += sum(a >= s for a in anni)
    return {"giorni": usati, "celle_giorno": misurate, "sopra": sopra}


def celle_cieche(grid: RainGrid, celle: list[tuple[float, float]]) -> tuple[int, int]:
    """Celle del campione sotto ``RELIABLE_FROM``, e quelle con un'affidabilità nota."""
    punteggi = replace(grid, data=reliability_map().like(grid)).sample(celle)
    note = [p for p in punteggi if p is not None]
    return sum(p < RELIABLE_FROM for p in note), len(note)


async def nowcast_evento(e: Evento, soglia_mmh: float) -> list[OraNowcast]:
    """Ora per ora nel giorno dell'evento: nowcast a 60 minuti contro SRT1 dell'ora dopo."""
    giorno = datetime.combine(e.at.astimezone(UTC).date(), time(), UTC)
    out: list[OraNowcast] = []
    for h in range(24):
        t = giorno + timedelta(hours=h)
        serie = [await _download("SRI", at=t - k * _PASSO_SRI) for k in (2, 1, 0)]
        dopo = await _download("SRT1", at=t + timedelta(minutes=_NOWCAST_MINUTI))
        frames = [s for s in serie if s is not None]
        if not frames:
            continue
        ultimo = frames[-1]
        box = _intorno(e.lon, e.lat)
        previsti = None
        if len(frames) >= 2:
            try:
                avanti = rain_ahead(frames, minutes=_NOWCAST_MINUTI)
                [previsti] = avanti.sample([(e.lon, e.lat)])
            except DpcRadarError as exc:
                log.info("misura_radar.nowcast_saltato", ora=t.isoformat(), error=str(exc))
        try:
            corretto = correct(ultimo)
            px_c = corretto.peak(box, threshold=soglia_mmh)[1]
        except DpcRadarError:
            px_c = 0
        out.append(
            OraNowcast(
                e.slug,
                t,
                previsti,
                dopo.sample([(e.lon, e.lat)])[0] if dopo is not None else None,
                ultimo.peak(box, threshold=soglia_mmh)[1],
                px_c,
            )
        )
    return out


async def misura(
    dal: date, al: date, soglia_mmh: float
) -> tuple[
    list[EsitoEvento], dict[str, Any], tuple[int, int], list[OraNowcast], tuple[int, int, int]
]:
    """Tutta la parte «adozione»; serve il database (eventi e celle) e l'API del DPC."""
    trovati = await eventi(dal, al)
    celle = await celle_campione()
    esiti = [await esito_evento(e) for e in trovati]
    giorni = [dal + timedelta(days=k) for k in range((al - dal).days + 1)]
    base = await base_rarita(giorni, celle)
    griglia = await _download("CUM24", at=datetime.combine(al, time(), UTC))
    cieche = celle_cieche(griglia, celle) if griglia is not None else (0, 0)
    # Ora per ora costa 96 richieste per evento: solo le alluvioni con l'ora nota,
    # per restare dentro il tetto di richieste al DPC dichiarato (#627).
    ore = [
        o
        for e in trovati
        if e.hazard == "flood" and e.precisione != "T3"
        for o in await nowcast_evento(e, soglia_mmh)
    ]
    sveglia = await base_sveglia(giorni, soglia_mmh)
    log.info(
        "misura_radar.adozione",
        eventi=len(trovati),
        giorni=len(giorni),
        ore_nowcast=len(ore),
    )
    return esiti, base, cieche, ore, sveglia


async def base_sveglia(giorni: list[date], soglia_mmh: float) -> tuple[int, int, int]:
    """Pixel d'Italia sopra la soglia della sveglia a mezzogiorno, senza e con correzione."""
    senza = con = usati = 0
    for g in giorni:
        sri = await _download("SRI", at=datetime.combine(g, time(12), UTC))
        if sri is None:
            continue
        usati += 1
        senza += int(np.nansum(sri.data >= soglia_mmh))
        con += int(np.nansum(correct(sri).data >= soglia_mmh))
    return usati, senza, con


def _f(x: float | None, cifre: int = 1) -> str:
    return "—" if x is None else f"{x:.{cifre}f}"


def _quota(a: int, b: int) -> str:
    return "—" if b == 0 else f"{100 * a / b:.1f} %"


def righe_adozione(
    esiti: list[EsitoEvento],
    base: dict[str, Any],
    cieche: tuple[int, int],
    ore: list[OraNowcast],
    sveglia: tuple[int, int, int],
    soglia_mmh: float,
) -> list[str]:
    righe = [
        "## Gli usi del radar ancora spenti: che cosa cambierebbe (#643)",
        "",
        "Misura e basta: in `flood.yaml` i blocchi `pluvial.observed.blind`, `rarity` e "
        "`nowcast` restano commentati, e `NOWCAST__BIAS_CORRECTION` resta falso, finché "
        "questa tabella non dice di accenderli. Eventi da `verifiche_eventi` (frane e "
        "alluvioni con un punto); fotogrammi dall'API del DPC.",
        "",
        "### Eventi",
        "",
        "| evento | pericolo | affidabilità radar | pioggia 24 h entro 5 km | tempo di ritorno |",
        "|---|---|---|---|---|",
    ]
    for x in esiti:
        righe.append(
            f"| {x.evento.slug} | {x.evento.hazard} | {_f(x.affidabilita, 2)} | "
            f"{_f(x.pioggia_24h_mm)} mm | {_f(x.ritorno_anni)} anni |"
        )
    n_cieche, n_note = cieche
    righe += [
        "",
        "### Cieco",
        "",
        f"Celle di Limen (una ogni {_PASSO_CELLE}) dove il radar vede male (affidabilità "
        f"sotto {RELIABLE_FROM}): **{n_cieche} su {n_note}** ({_quota(n_cieche, n_note)}). "
        f"Eventi in quelle zone: {sum((x.affidabilita or 0) < RELIABLE_FROM for x in esiti)} "
        f"su {len(esiti)}. Lì una pioggia osservata sotto `dry_mm` diventerebbe «non "
        "misurata»: conta solo dove manca anche la previsione, perché altrimenti vale la "
        "maggiore delle due.",
        "",
        "### Rarità",
        "",
        f"Tasso di base su {base['giorni']} giorni e {base['celle_giorno']} celle-giorno "
        "(CUM24 a mezzanotte UTC, una cella ogni dieci, con la stessa lettura degli eventi: "
        "il massimo entro 5 km), accanto agli eventi. Gli eventi con l'ora ignota usano il "
        "giorno UTC intero:",
        "",
        "| tempo di ritorno | eventi sopra | celle-giorno sopra (base) |",
        "|---|---|---|",
    ]
    con_pioggia = [x for x in esiti if x.ritorno_anni is not None]
    for s in SOGLIE_ANNI:
        ev = sum((x.ritorno_anni or 0) >= s for x in con_pioggia)
        righe.append(
            f"| ≥ {s:g} anni | {ev} su {len(con_pioggia)} ({_quota(ev, len(con_pioggia))}) | "
            f"{base['sopra'][s]} su {base['celle_giorno']} "
            f"({_quota(base['sopra'][s], base['celle_giorno'])}) |"
        )
    righe += ["", "### Nowcast e bias della sveglia", ""]
    con_caduta = [o for o in ore if o.caduti_mm is not None and o.previsti_mm is not None]
    if con_caduta:
        bagnate = [o for o in con_caduta if (o.caduti_mm or 0) >= 1.0]
        mae = (
            float(np.mean([abs((o.previsti_mm or 0) - (o.caduti_mm or 0)) for o in bagnate]))
            if bagnate
            else None
        )
        forti = [o for o in con_caduta if (o.caduti_mm or 0) >= 10.0]
        colte = sum((o.previsti_mm or 0) >= 10.0 for o in forti)
        falsi = sum((o.previsti_mm or 0) >= 10.0 and (o.caduti_mm or 0) < 10.0 for o in con_caduta)
        righe += [
            f"Nowcast a {_NOWCAST_MINUTI} minuti sul punto dell'evento, ora per ora nel suo "
            f"giorno ({len(con_caduta)} ore con entrambe le letture): errore medio "
            f"**{_f(mae)} mm** nelle ore con almeno 1 mm caduto; ore con 10 mm o più cadute "
            f"colte {colte} su {len(forti)}; ore con 10 mm previsti e non caduti {falsi}.",
            "",
        ]
    usati, senza, con = sveglia
    righe += [
        f"Sveglia (pixel SRI ≥ {soglia_mmh:g} mm/h): sugli eventi, ore con almeno 3 pixel "
        f"senza correzione {sum(o.sveglia_px >= 3 for o in ore)}, con correzione "
        f"{sum(o.sveglia_corretta_px >= 3 for o in ore)}; sull'Italia a mezzogiorno di "
        f"{usati} giorni, pixel sopra soglia {senza} senza correzione e {con} con.",
        "",
        "| evento | ora UTC | nowcast 60 min | caduti (SRT1) | pixel sveglia | corretti |",
        "|---|---|---|---|---|---|",
    ]
    for o in ore:
        if (o.caduti_mm or 0) >= 1.0 or (o.previsti_mm or 0) >= 1.0 or o.sveglia_px:
            righe.append(
                f"| {o.slug} | {o.ora:%d/%m %H:%M} | {_f(o.previsti_mm)} | {_f(o.caduti_mm)} | "
                f"{o.sveglia_px} | {o.sveglia_corretta_px} |"
            )
    righe.append("")
    return righe
