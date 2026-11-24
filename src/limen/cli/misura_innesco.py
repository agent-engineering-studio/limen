"""``limen misura-innesco`` — tre termini d'innesco a parità di carico (#676).

Solo una misura: niente cambia nel motore. Sulle dodici finestre della #122
(e-ITALICA, la pioggia dell'archivio Open-Meteo) si confrontano, allo stesso
carico di allerta, tre letture della pioggia:

* **caine**: l'eccesso in decadi dell'evento scelto da
  ``event_reconstruction.scelta_evento`` sulla curva della macroregione, fra
  gli eventi delle ``_FINESTRA_CAINE_ORE`` ore prima, ricostruiti come fa il
  motore. Non tagliato a zero: sotto la curva conta quanto sotto;
  ``_SENZA_EVENTO`` se non ha piovuto.
* **cumulata**: la pioggia delle ``_ORE_CUMULATA`` ore prima, in mm.
* **relativa**: la stessa cumulata divisa per il quantile climatologico del
  suo nodo (``limen clima-pioggia``, file ``LIMEN_CLIMA_PIOGGIA``).

* **Unità**: un nodo di pioggia (0,1°, quelli più vicini a una cella dell'AOI)
  e un istante ogni ``_PASSO_ORE`` ore della finestra.
* **Frana colta**: il suo nodo supera la soglia in almeno un istante delle
  ``_ANTICIPO_ORE`` ore prima; per una data senza ora fino alla fine di quel
  giorno, perché 00:00 UTC non è l'ora della frana.
* **Misure**: ``rainfall_thresholds.measure``, a carico uguale in ogni
  regione (ordinamento) e con una soglia nazionale scelta sulle regioni di
  taratura della #122 e applicata a quelle di verifica (scala). Una lettura
  non misurata (un nodo senza pioggia dall'archivio) resta fuori e si conta.

Env: ``LIMEN_INNESCO_FINESTRE`` (``aoi:AAAA-MM-GG:AAAA-MM-GG`` separate da
spazi; default le dodici della #122), ``LIMEN_CLIMA_PIOGGIA``,
``LIMEN_BACKTEST_SORGENTI`` (default ``IR,NR``). Report e CSV (una riga per
frana) in ``LIMEN_REPORTS_DIR``.
"""

from __future__ import annotations

import csv
import math
import os
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from rainfall_thresholds import (
    PowerLawThreshold,
    Skill,
    auc,
    cutoff_at_budget,
    latest_event,
    reconstruct_events,
    skill,
    skill_at_budget,
    strongest_event,
)

from limen.cli import provenienza
from limen.cli.backtest import _SENZA_ORA
from limen.cli.clima_pioggia import CLIMA_DEFAULT, CLIMA_ENV, leggi, riferimenti_aoi
from limen.core.logging import get_logger
from limen.core.scoring.regional_thresholds import RegionalThresholds, load_regional_thresholds
from limen.data.db import acquire, lifespan_pool
from limen.data.repos.aoi_repo import get_aoi
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.grid import build_rain_nodes

log = get_logger(__name__)

REPORTS_DIR = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
#: Le dodici finestre della #122: il mese con più frane e-ITALICA per regione.
FINESTRE_122 = (
    "it-liguria:2019-11-01:2019-11-30 it-piemonte:2009-04-01:2009-04-30 "
    "it-sicilia:2009-01-01:2009-01-31 it-toscana:2008-12-01:2008-12-31 "
    "it-lombardia:2014-11-01:2014-11-30 it-campania:2009-01-01:2009-01-31 "
    "it-marche:2014-05-01:2014-05-31 it-calabria:2009-01-01:2009-01-31 "
    "it-lazio:2010-05-01:2010-05-31 it-umbria:2008-12-01:2008-12-31 "
    "it-sardegna:2018-05-01:2018-05-31 it-puglia:2009-03-01:2009-03-31"
)
#: La divisione della #122: la soglia nazionale si sceglie qui e si verifica sulle altre.
TARATURA = frozenset(
    {"it-liguria", "it-piemonte", "it-sicilia", "it-toscana", "it-lombardia", "it-campania"}
)
#: Il passo del reticolo di pioggia di ``limen backtest`` e di ``limen clima-pioggia``.
_PASSO_NODI = 0.1
_PASSO_ORE = 6
_ANTICIPO_ORE = 72
_FINESTRA_CAINE_ORE = 48
_ORE_CUMULATA = 24
#: Le ore prima dell'inizio della finestra, perché il primo istante abbia la sua storia.
_STORIA_ORE = 48
_CARICHI = (0.02, 0.05)
_SENZA_EVENTO = -99.0
LETTURE = ("caine", "cumulata", "relativa")
_PRECISIONI_DATA_AL_GIORNO = ("T1", "T2")


@dataclass(frozen=True, slots=True)
class Finestra:
    aoi_id: str
    dal: date
    al: date

    @property
    def taratura(self) -> bool:
        return self.aoi_id in TARATURA


@dataclass(slots=True)
class Frana:
    aoi_id: str
    lon: float
    lat: float
    istante: datetime
    precisione_data: str | None
    precisione_luogo: str | None
    nodo: int = -1
    letture: dict[str, float | None] = field(default_factory=dict)

    @property
    def al_giorno(self) -> bool:
        return self.precisione_data in _PRECISIONI_DATA_AL_GIORNO


@dataclass(slots=True)
class Misurata:
    """Una finestra misurata: le frane con le loro letture e le letture ordinarie."""

    finestra: Finestra
    frane: list[Frana]
    ordinarie: dict[str, list[float | None]]
    nodi: int


def finestre(testo: str) -> list[Finestra]:
    out: list[Finestra] = []
    for voce in testo.split():
        aoi_id, dal, al = voce.split(":")
        out.append(Finestra(aoi_id, date.fromisoformat(dal), date.fromisoformat(al)))
    return out


def lettura_caine(
    serie: NDArray[np.float64],
    e: int,
    soglia: PowerLawThreshold,
    *,
    pausa_ore: int,
    minimo_mm: float,
    piu_forte: bool,
) -> float | None:
    """L'eccesso dell'evento scelto fra quelli delle ore fino a ``e`` compresa.

    ``None`` se la finestra non è misurata; ``_SENZA_EVENTO`` senza un evento.
    """
    inizio = e - _FINESTRA_CAINE_ORE + 1
    if inizio < 0 or e >= len(serie):
        return None
    tratto = serie[inizio : e + 1]
    if bool(np.isnan(tratto).any()):
        return None
    t0 = datetime(2000, 1, 1, tzinfo=UTC)
    eventi = reconstruct_events(
        ((t0 + timedelta(hours=k), float(v)) for k, v in enumerate(tratto)),
        no_rain_break_hours=pausa_ore,
        min_event_mm=minimo_mm,
    )
    evento = strongest_event(eventi, soglia) if piu_forte else latest_event(eventi)
    if evento is None or evento.duration_hours <= 0 or evento.total_mm <= 0:
        return _SENZA_EVENTO
    return soglia.exceedance(evento.intensity_mm_h, evento.duration_hours)


def lettura_cumulata(serie: NDArray[np.float64], e: int) -> float | None:
    """I mm delle ``_ORE_CUMULATA`` ore fino a ``e`` compresa; ``None`` se non misurati."""
    inizio = e - _ORE_CUMULATA + 1
    if inizio < 0 or e >= len(serie):
        return None
    tratto = serie[inizio : e + 1]
    if bool(np.isnan(tratto).any()):
        return None
    return float(tratto.sum())


def relativa(cumulata: float | None, riferimento: float | None) -> float | None:
    if cumulata is None or riferimento is None or riferimento <= 0:
        return None
    return cumulata / riferimento


def massimo(valori: Sequence[float | None]) -> float | None:
    """Il più alto dei misurati; ``None`` se nessuno lo è."""
    misurati = [v for v in valori if v is not None]
    return max(misurati) if misurati else None


def nodo_piu_vicino(
    nodi: Sequence[tuple[float, float]], candidati: Sequence[int], lon: float, lat: float
) -> int:
    return min(candidati, key=lambda i: (nodi[i][0] - lon) ** 2 + (nodi[i][1] - lat) ** 2)


def istanti(base: datetime, n_ore: int, dal: datetime, al: datetime) -> list[int]:
    """Gli indici orari fra ``dal`` e ``al`` (compresi) all'ora multipla di ``_PASSO_ORE``."""
    out = []
    for e in range(n_ore):
        t = base + timedelta(hours=e)
        if dal <= t <= al and t.hour % _PASSO_ORE == 0:
            out.append(e)
    return out


def fine_finestra_frana(frana: Frana) -> datetime:
    """Fino a quando cercare la pioggia di una frana: l'ora, o la fine del giorno se non c'è."""
    if frana.precisione_data in _SENZA_ORA:
        return frana.istante + timedelta(hours=23)
    return frana.istante


async def _frane(f: Finestra, sorgenti: list[str]) -> list[Frana]:
    async with acquire() as conn:
        righe = await conn.fetch(
            """
            SELECT DISTINCT ST_X(e.geom) AS lon, ST_Y(e.geom) AS lat, e.event_time,
                   e.temporal_accuracy, e.geographic_accuracy
            FROM landslide_events e
            JOIN aoi a ON a.id = $1 AND ST_Intersects(a.geom, e.geom)
            WHERE e.event_time >= $2 AND e.event_time < $3 AND e.source = ANY($4)
            """,
            f.aoi_id,
            datetime(f.dal.year, f.dal.month, f.dal.day, tzinfo=UTC),
            datetime(f.al.year, f.al.month, f.al.day, tzinfo=UTC) + timedelta(days=1),
            sorgenti,
        )
    return [
        Frana(
            aoi_id=f.aoi_id,
            lon=float(r["lon"]),
            lat=float(r["lat"]),
            istante=r["event_time"].astimezone(UTC),
            precisione_data=r["temporal_accuracy"],
            precisione_luogo=r["geographic_accuracy"],
        )
        for r in righe
    ]


async def _nodi_delle_celle(aoi_id: str, nodi: Sequence[tuple[float, float]]) -> list[int]:
    """I nodi che sono il più vicino di almeno una cella dell'AOI: niente mare, niente fuori."""
    async with acquire() as conn:
        righe = await conn.fetch(
            "SELECT ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat "
            "FROM grid_cells WHERE aoi_id = $1",
            aoi_id,
        )
    lon0, lat0 = nodi[0]
    colonne = sum(1 for _, lat in nodi if abs(lat - lat0) < 1e-9)
    righe_nodi = len(nodi) // colonne
    usati: set[int] = set()
    for r in righe:
        i = min(max(round((r["lon"] - lon0) / _PASSO_NODI), 0), colonne - 1)
        j = min(max(round((r["lat"] - lat0) / _PASSO_NODI), 0), righe_nodi - 1)
        usati.add(j * colonne + i)
    return sorted(usati)


async def misura_finestra(
    f: Finestra,
    *,
    soglie: RegionalThresholds,
    clima: dict[str, Any],
    sorgenti: list[str],
    client: OpenMeteoHttpClient,
) -> Misurata | None:
    aoi = await get_aoi(f.aoi_id)
    if aoi is None:
        log.warning("misura_innesco.aoi_assente", aoi_id=f.aoi_id)
        return None
    minx, miny, maxx, maxy = aoi.bbox.bounds
    nodi = build_rain_nodes((minx, miny, maxx, maxy), spacing=_PASSO_NODI)
    riferimenti = riferimenti_aoi(clima, f.aoi_id, ore=_ORE_CUMULATA)
    if riferimenti is None or len(riferimenti) != len(nodi):
        log.error("misura_innesco.clima_assente", aoi_id=f.aoi_id, rimedio="limen clima-pioggia")
        return None
    usati = await _nodi_delle_celle(f.aoi_id, nodi)

    inizio = datetime(f.dal.year, f.dal.month, f.dal.day, tzinfo=UTC)
    fine = datetime(f.al.year, f.al.month, f.al.day, 23, tzinfo=UTC)
    base = inizio - timedelta(hours=_STORIA_ORE)
    # Un giorno dopo la fine: una frana dell'ultimo giorno senza ora guarda fino a sera.
    griglia = await client.get_rainfall_grid(
        nodes=[nodi[i] for i in usati],
        window_start=base,
        window_end=fine + timedelta(hours=24),
        batch_size=50,
    )
    n_ore = int((fine + timedelta(hours=24) - base).total_seconds() // 3600) + 1
    pioggia = np.full((len(usati), n_ore), np.nan)
    for k, serie in enumerate(griglia[: len(usati)]):
        for s in serie:
            e = int((s.timestamp - base).total_seconds() // 3600)
            if 0 <= e < n_ore:
                pioggia[k, e] = s.precipitation_mm

    macro = soglie.macroregion_for(f.aoi_id)
    regione = soglie.caine.macroregions.get(macro) or soglie.caine.macroregions["italy_default"]
    curva = PowerLawThreshold(alpha=regione.alpha, beta=regione.beta)
    ricostruzione = soglie.caine.event_reconstruction
    piu_forte = ricostruzione.scelta_evento == "piu_forte"

    def letture(k: int, e: int) -> dict[str, float | None]:
        serie = pioggia[k]
        cum = lettura_cumulata(serie, e)
        return {
            "caine": lettura_caine(
                serie,
                e,
                curva,
                pausa_ore=ricostruzione.no_rain_break_hours,
                minimo_mm=ricostruzione.min_event_mm,
                piu_forte=piu_forte,
            ),
            "cumulata": cum,
            "relativa": relativa(cum, riferimenti[usati[k]][2]),
        }

    tutti = istanti(base, n_ore, inizio, fine + timedelta(hours=24))
    cache: dict[tuple[int, int], dict[str, float | None]] = {}

    def alla(k: int, e: int) -> dict[str, float | None]:
        if (k, e) not in cache:
            cache[(k, e)] = letture(k, e)
        return cache[(k, e)]

    ordinarie: dict[str, list[float | None]] = {nome: [] for nome in LETTURE}
    for k in range(len(usati)):
        for e in tutti:
            if base + timedelta(hours=e) > fine:
                break
            valori = alla(k, e)
            for nome in LETTURE:
                ordinarie[nome].append(valori[nome])

    frane = await _frane(f, sorgenti)
    posizione = {nodo: k for k, nodo in enumerate(usati)}
    for frana in frane:
        frana.nodo = nodo_piu_vicino(nodi, usati, frana.lon, frana.lat)
        k = posizione[frana.nodo]
        dal = frana.istante - timedelta(hours=_ANTICIPO_ORE)
        al = fine_finestra_frana(frana)
        prima = [e for e in tutti if dal <= base + timedelta(hours=e) <= al]
        frana.letture = {nome: massimo([alla(k, e)[nome] for e in prima]) for nome in LETTURE}
    log.info("misura_innesco.finestra", aoi_id=f.aoi_id, nodi=len(usati), frane=len(frane))
    return Misurata(finestra=f, frane=frane, ordinarie=ordinarie, nodi=len(usati))


# ---------------------------------------------------------------------------
# Il report
# ---------------------------------------------------------------------------
Filtro = Callable[[Frana], bool]


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.1%}".replace(".", ",")


def _num(x: float | None, cifre: int = 2) -> str:
    return "—" if x is None or math.isinf(x) else f"{x:.{cifre}f}".replace(".", ",")


def _somma(abilita: Sequence[Skill]) -> Skill:
    return Skill(
        cutoff=math.nan,
        caught=sum(s.caught for s in abilita),
        landslides=sum(s.landslides for s in abilita),
        alerts=sum(s.alerts for s in abilita),
        ordinary=sum(s.ordinary for s in abilita),
        unmeasured=sum(s.unmeasured for s in abilita),
    )


def _cella(s: Skill) -> str:
    colte = f"{s.caught}/{s.landslides} = {_pct(s.hit_rate)}"
    return f"{colte}, {_num(s.alerts_per_caught, 0)} allerte per frana colta"


def per_regione(misurate: Sequence[Misurata], lettura: str, carico: float, filtro: Filtro) -> Skill:
    """A parità di carico in ogni regione: un confronto di ordinamento."""
    return _somma(
        [
            skill_at_budget(
                [fr.letture[lettura] for fr in m.frane if filtro(fr)],
                m.ordinarie[lettura],
                carico,
            )
            for m in misurate
        ]
    )


def nazionale(
    misurate: Sequence[Misurata], lettura: str, carico: float, filtro: Filtro
) -> tuple[float, Skill, Skill]:
    """La soglia al carico scelta sulla taratura, e cosa fa in taratura e in verifica."""
    taratura = [m for m in misurate if m.finestra.taratura]
    verifica = [m for m in misurate if not m.finestra.taratura]
    soglia = cutoff_at_budget([v for m in taratura for v in m.ordinarie[lettura]], carico)

    def applica(gruppo: Sequence[Misurata]) -> Skill:
        return _somma(
            [
                skill(
                    [fr.letture[lettura] for fr in m.frane if filtro(fr)],
                    m.ordinarie[lettura],
                    soglia,
                )
                for m in gruppo
            ]
        )

    return soglia, applica(taratura), applica(verifica)


def auc_media(gruppo: Sequence[Misurata], lettura: str, filtro: Filtro) -> float | None:
    valori = [
        a
        for m in gruppo
        if (a := auc([fr.letture[lettura] for fr in m.frane if filtro(fr)], m.ordinarie[lettura]))
        is not None
    ]
    return statistics.fmean(valori) if valori else None


def _sezione(misurate: Sequence[Misurata], titolo: str, filtro: Filtro) -> list[str]:
    taratura = [m for m in misurate if m.finestra.taratura]
    verifica = [m for m in misurate if not m.finestra.taratura]
    n = sum(1 for m in misurate for fr in m.frane if filtro(fr))
    righe = [f"## {titolo} ({n} frane)", ""]
    righe += [
        "### A parità di carico in ogni regione (ordinamento)",
        "",
        "| Lettura | "
        + " | ".join(
            f"{g} al {carico:.0%}" for carico in _CARICHI for g in ("taratura", "verifica")
        )
        + " |",
        "|---|" + "---|" * (2 * len(_CARICHI)),
    ]
    for lettura in LETTURE:
        celle = [
            _cella(per_regione(gruppo, lettura, carico, filtro))
            for carico in _CARICHI
            for gruppo in (taratura, verifica)
        ]
        righe.append(f"| {lettura} | " + " | ".join(celle) + " |")
    righe += [
        "",
        "### Soglia nazionale scelta in taratura, applicata alla verifica (scala)",
        "",
        "| Lettura | Carico | Soglia | Taratura | Verifica | Verifica: quota in allerta |",
        "|---|---|---|---|---|---|",
    ]
    for lettura in LETTURE:
        for carico in _CARICHI:
            soglia, t, v = nazionale(misurate, lettura, carico, filtro)
            righe.append(
                f"| {lettura} | {carico:.0%} | {_num(soglia)} | {_cella(t)} | {_cella(v)} "
                f"| {_pct(v.alert_share)} |"
            )
    righe += [
        "",
        "### AUC media per finestra",
        "",
        "Più alta che nella #243: il punteggio di una frana è il massimo delle "
        f"{_ANTICIPO_ORE} ore prima, quello di un'unità ordinaria un istante solo. "
        "Vale per confrontare le letture fra loro, non come numero assoluto.",
        "",
        "| Lettura | Taratura | Verifica |",
        "|---|---|---|",
    ]
    for lettura in LETTURE:
        righe.append(
            f"| {lettura} | {_num(auc_media(taratura, lettura, filtro))} "
            f"| {_num(auc_media(verifica, lettura, filtro))} |"
        )
    righe += ["", "### Per regione, al 5 % in ogni regione", ""]
    righe += [
        "| Regione | Gruppo | Nodi | Frane | " + " | ".join(LETTURE) + " |",
        "|---|---|---|---|" + "---|" * len(LETTURE),
    ]
    for m in misurate:
        frane = [fr for fr in m.frane if filtro(fr)]
        colte = [
            skill_at_budget([fr.letture[x] for fr in frane], m.ordinarie[x], 0.05).caught
            for x in LETTURE
        ]
        gruppo = "taratura" if m.finestra.taratura else "verifica"
        righe.append(
            f"| {m.finestra.aoi_id} ({m.finestra.dal:%Y-%m}) | {gruppo} | {m.nodi} "
            f"| {len(frane)} | " + " | ".join(str(c) for c in colte) + " |"
        )
    righe.append("")
    return righe


_CAMPI = ("aoi", "gruppo", "lon", "lat", "istante", "precisione_data", "precisione_luogo", *LETTURE)


def scrivi(misurate: Sequence[Misurata], *, sorgenti: list[str], quantile: float) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    nome = "misura_innesco_122"
    with (REPORTS_DIR / f"{nome}.csv").open("w", newline="", encoding="utf-8") as fh:
        scrittore = csv.writer(fh, lineterminator="\n")
        scrittore.writerow(_CAMPI)
        for m in misurate:
            for fr in m.frane:
                scrittore.writerow(
                    [
                        m.finestra.aoi_id,
                        "taratura" if m.finestra.taratura else "verifica",
                        round(fr.lon, 5),
                        round(fr.lat, 5),
                        fr.istante.isoformat(),
                        fr.precisione_data or "",
                        fr.precisione_luogo or "",
                        *("" if (v := fr.letture[x]) is None else round(v, 4) for x in LETTURE),
                    ]
                )
    non_misurate = {
        x: sum(v is None for m in misurate for v in m.ordinarie[x])
        + sum(fr.letture[x] is None for m in misurate for fr in m.frane)
        for x in LETTURE
    }
    unita = sum(len(m.ordinarie["cumulata"]) for m in misurate)
    testa = [
        "# Tre termini d'innesco a parità di carico (#676)",
        "",
        f"- Finestre: le dodici della #122; taratura {', '.join(sorted(TARATURA))}, "
        "le altre in verifica.",
        f"- Frane: e-ITALICA (sorgenti {', '.join(sorgenti)}), una per punto e istante. "
        f"Colta se il suo nodo supera la soglia in un istante delle {_ANTICIPO_ORE} ore prima "
        "(per una data senza ora, fino alla fine di quel giorno).",
        f"- Unità ordinarie: {unita} nodi-istanti (nodi a {_num(_PASSO_NODI, 1)}° più vicini "
        f"a una cella dell'AOI, un istante ogni {_PASSO_ORE} ore), con o senza frane.",
        f"- Letture: **caine** = eccesso in decadi sulla curva della macroregione, eventi delle "
        f"{_FINESTRA_CAINE_ORE} ore prima, non tagliato a zero ({_SENZA_EVENTO:g} senza evento); "
        f"**cumulata** = mm delle {_ORE_CUMULATA} ore; **relativa** = cumulata / q{quantile:g} "
        "della cumulata del nodo (`limen clima-pioggia`, anni prima di ogni finestra).",
        "- Letture non misurate (nodo senza pioggia dall'archivio, o senza riferimento): "
        + ", ".join(f"{x} {non_misurate[x]}" for x in LETTURE)
        + ". Restano fuori, mai contate come zero.",
        "- Misure: `rainfall_thresholds.measure` (`skill_at_budget`, `cutoff_at_budget`, "
        "`skill`, `auc`).",
        f"- Una riga per frana in `{nome}.csv`.",
        "",
    ]
    corpo = [
        *testa,
        *_sezione(misurate, "Tutte le frane", lambda _: True),
        *_sezione(misurate, "Solo le frane datate al giorno (T1, T2)", lambda fr: fr.al_giorno),
    ]
    return provenienza.scrivi_report(REPORTS_DIR / f"{nome}.md", "\n".join(corpo))


async def run() -> int:
    elenco = finestre(os.getenv("LIMEN_INNESCO_FINESTRE") or FINESTRE_122)
    sorgenti = (os.getenv("LIMEN_BACKTEST_SORGENTI") or "IR,NR").split(",")
    clima = leggi(Path(os.getenv(CLIMA_ENV, CLIMA_DEFAULT)))
    soglie = load_regional_thresholds()
    client = OpenMeteoHttpClient()
    misurate: list[Misurata] = []
    try:
        async with lifespan_pool():
            for f in elenco:
                m = await misura_finestra(
                    f, soglie=soglie, clima=clima, sorgenti=sorgenti, client=client
                )
                if m is None:
                    return 1
                misurate.append(m)
    finally:
        await SharedHttpClient.aclose()
    report = scrivi(misurate, sorgenti=sorgenti, quantile=float(clima.get("quantile", math.nan)))
    log.info("misura_innesco.done", report=str(report), finestre=len(misurate))
    return 0


__all__ = [
    "FINESTRE_122",
    "TARATURA",
    "fine_finestra_frana",
    "finestre",
    "istanti",
    "lettura_caine",
    "lettura_cumulata",
    "massimo",
    "nodo_piu_vicino",
    "relativa",
    "run",
]
