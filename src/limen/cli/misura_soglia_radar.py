"""``limen misura-soglia-radar`` — una soglia dei pluviometri vale sulla pioggia del radar? (#677)

Solo una misura: niente cambia nel motore. Le curve di ``landslide.yaml`` sono
``rainfall_thresholds.ITALICA_T5``, tarate sulla pioggia dei pluviometri, e il
motore le applica anche alla pioggia del radar. Qui si guarda che cosa succede
con il radar storico (IT-DPC-SRI, dal 2018: prima lo strumento è un altro).

* **Frane**: e-ITALICA dal 2018 al 2021, che per ogni frana dà la pioggia
  d'innesco al pluviometro (durata e cumulata), e le frane datate al giorno
  di IdroGEO (``ispra_idrogeo.dated``) dal 2018 alla fine dell'archivio.
* **Unità**: un punto di frana e un istante. Si guardano gli eventi di pioggia
  che toccano le ``_FINESTRA_ORE`` prima, ricostruiti come fa il motore
  (``caine.event_reconstruction``); il punteggio è l'eccesso più alto sulla
  curva della macroregione, in decadi.
* **Momenti ordinari**: gli stessi punti, ogni ``_PASSO_ORDINARIE_GIORNI``
  giorni, lontani almeno ``_DISTANZA_GIORNI`` da una frana in quel punto.
* **Letture**: il radar da solo, il radar per ``dpc_radar.bias.radar_factor``
  del punto, e i soli punti con ``dpc_radar.reliability`` ≥ ``RELIABLE_FROM``.
* **Misure**: ``rainfall_thresholds.measure`` (frane colte alla curva e a
  parità di carico, AUC), e una curva tarata sul radar con ``fit_threshold``.

La pioggia oraria nei punti si estrae una volta, un file per mese, in
``LIMEN_SOGLIA_RADAR_CACHE`` (default ``$LIMEN_DATA_ROOT/radar/soglia_radar``):
è il passo lungo, mezz'ora per anno. Env: ``LIMEN_BACKTEST_RADAR_ZARR`` (lo
Zarr di ``make radar-data``), ``LIMEN_ITALICA_CSV``. Report e CSV (una riga per
frana) in ``LIMEN_REPORTS_DIR``.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from dpc_radar import reliability
from dpc_radar.bias import radar_factor
from dpc_radar.reliability import RELIABLE_FROM
from ispra_idrogeo import IdroGEO
from ispra_idrogeo.dated import dated_landslides
from numpy.typing import NDArray
from rainfall_thresholds import (
    ITALICA_T5,
    MACROREGIONS,
    PowerLawThreshold,
    auc,
    fit_threshold,
    reconstruct_events,
    skill,
    skill_at_budget,
)

from limen.cli import provenienza
from limen.cli.ingest_events import _resolve_csv
from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.integrations._http import SharedHttpClient
from limen.integrations.dpc.sri_archive import STRUMENTO_DI_OGGI, SriArchive

log = get_logger(__name__)

REPORTS_DIR = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
_RADAR_ZARR = Path("radar/it_dpc_sri/italian-radar-dpc-sri.zarr")
#: Un mese prima del 2018: gli eventi di pioggia delle prime frane cominciano lì.
_BASE = STRUMENTO_DI_OGGI - timedelta(days=31)
_ROMA = ZoneInfo("Europe/Rome")
_FINESTRA_ORE = 48
_STORIA_ORE = 15 * 24
_PASSO_ORDINARIE_GIORNI = 30
_DISTANZA_GIORNI = 15
#: Primo con le 720 ore del passo: i punti si spargono su tutte le ore del mese.
_SFASAMENTO_ORE = 37
_SPOSTAMENTO_ORE = 12
_CARICHI = (0.02, 0.05)
#: Nessun evento di pioggia nella finestra: sotto ogni curva, ma misurato.
SENZA_EVENTO = -99.0
_MACRO = {regione: macro for macro, regioni in MACROREGIONS.items() for regione in regioni}
#: I codici ISTAT delle regioni con il nome che usano e-ITALICA e ``MACROREGIONS``.
_NOMI = {
    1: "Piemonte",
    2: "Valle d'Aosta",
    3: "Lombardia",
    4: "Trentino-Alto Adige",
    5: "Veneto",
    6: "Friuli-Venezia Giulia",
    7: "Liguria",
    8: "Emilia-Romagna",
    9: "Toscana",
    10: "Umbria",
    11: "Marche",
    12: "Lazio",
    13: "Abruzzo",
    14: "Molise",
    15: "Campania",
    16: "Puglia",
    17: "Basilicata",
    18: "Calabria",
    19: "Sicilia",
    20: "Sardegna",
}
_CAMPI = (
    "id",
    "insieme",
    "regione",
    "macro",
    "precisione_data",
    "affidabilita",
    "fattore",
    "pluvio_durata_h",
    "pluvio_mm",
    "pluvio_eccesso",
    "radar_mm_stessa_durata",
    "radar_durata_h",
    "radar_mm",
    "radar_eccesso",
    "radar_corretto_eccesso",
)


@dataclass(slots=True)
class Frana:
    insieme: str
    id: str
    lon: float
    lat: float
    regione: str
    istante: datetime
    precisione_data: str
    pluvio_durata_h: float | None = None
    pluvio_mm: float | None = None
    affidabilita: float | None = None
    fattore: float | None = None
    pluvio_eccesso: float | None = None
    radar_mm_stessa_durata: float | None = None
    radar_durata_h: float | None = None
    radar_mm: float | None = None
    radar_eccesso: float | None = None
    radar_corretto_eccesso: float | None = None

    @property
    def punto(self) -> tuple[float, float]:
        return round(self.lon, 5), round(self.lat, 5)

    @property
    def macro(self) -> str:
        return _MACRO.get(self.regione, "italy")


def indice(t: datetime) -> int:
    """L'indice dell'ultima ora che finisce entro ``t`` (l'ora 0 finisce a ``_BASE`` + 1 h)."""
    return int((t - _BASE).total_seconds() // 3600) - 1


def _numero(testo: str | None) -> float | None:
    try:
        return float((testo or "").replace(",", "."))
    except ValueError:
        return None


def frane_italica(percorso: Path, dal: int = STRUMENTO_DI_OGGI.year) -> list[Frana]:
    """Le frane di e-ITALICA da ``dal``, con la pioggia al pluviometro dove c'è.

    Una data senza ora (``T3``) è messa alla mezzanotte locale: la frana può
    essere caduta fino alla fine di quel giorno, e lì va l'istante.
    """
    frane = []
    with percorso.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if not r["year"] or int(r["year"]) < dal:
                continue
            istante = datetime.strptime(r["utc_date"], "%d/%m/%Y %H:%M").replace(tzinfo=UTC)
            if r["temporal_accuracy"] == "T3":
                istante += timedelta(hours=24)
            frane.append(
                Frana(
                    insieme="italica",
                    id=r["id"],
                    lon=float(r["lon"]),
                    lat=float(r["lat"]),
                    regione=r["region"],
                    istante=istante,
                    precisione_data=r["temporal_accuracy"],
                    pluvio_durata_h=_numero(r["duration"]),
                    pluvio_mm=_numero(r["cumulated_rainfall"]),
                )
            )
    return frane


async def frane_idrogeo(fino_a: date, cartella: Path) -> list[Frana]:
    """Le frane di IdroGEO datate al giorno o meglio, dal 2018 a ``fino_a``."""
    idrogeo = IdroGEO(await SharedHttpClient.get(), retries=0)
    datate = await dated_landslides(
        idrogeo,
        since=STRUMENTO_DI_OGGI.date(),
        until=fino_a,
        max_interval_days=1,
        directory=cartella,
    )
    frane = []
    for x in datate:
        if x.lon is None or x.lat is None:
            continue
        giorno = datetime(x.start.year, x.start.month, x.start.day, tzinfo=UTC)
        # Senza ora la frana vale fino alla fine del suo giorno.
        istante = giorno + timedelta(hours=24)
        if x.precision == "hour" and x.time:
            ore, minuti = (int(parte) for parte in x.time.split(":")[:2])
            istante = giorno.replace(hour=ore, minute=minuti, tzinfo=_ROMA).astimezone(UTC)
        frane.append(
            Frana(
                insieme="idrogeo",
                id=f"{x.source}:{x.id}",
                lon=x.lon,
                lat=x.lat,
                regione=_NOMI.get(x.region or 0, str(x.region)),
                istante=istante,
                precisione_data=x.precision,
            )
        )
    return frane


def punteggio(
    serie: NDArray[np.float32],
    e: int,
    soglia: PowerLawThreshold,
    *,
    pausa_ore: int,
    minimo_mm: float,
    fattore: float = 1.0,
) -> tuple[float | None, float | None, float | None]:
    """Eccesso, durata e millimetri dell'evento più sopra la curva fra quelli
    che toccano le ``_FINESTRA_ORE`` prima dell'ora ``e``.

    ``(None, …)`` se la finestra esce dalla serie o è per più di metà non
    misurata; ``(SENZA_EVENTO, None, None)`` se non ha piovuto.
    """
    inizio = e - _STORIA_ORE
    if inizio < 0 or e >= len(serie):
        return None, None, None
    finestra = serie[inizio : e + 1]
    if float(np.isnan(finestra[-_FINESTRA_ORE:]).mean()) > 0.5:
        return None, None, None
    t0 = _BASE + timedelta(hours=inizio + 1)
    eventi = reconstruct_events(
        (
            (t0 + timedelta(hours=k), None if np.isnan(v) else float(v) * fattore)
            for k, v in enumerate(finestra)
        ),
        no_rain_break_hours=pausa_ore,
        min_event_mm=minimo_mm,
    )
    limite = _BASE + timedelta(hours=e + 1 - _FINESTRA_ORE)
    meglio: tuple[float, float | None, float | None] = (SENZA_EVENTO, None, None)
    for evento in eventi:
        if evento.end < limite or evento.duration_hours <= 0 or evento.total_mm <= 0:
            continue
        x = soglia.exceedance(evento.intensity_mm_h, evento.duration_hours)
        if x > meglio[0]:
            meglio = (x, float(evento.duration_hours), evento.total_mm)
    return meglio


def sulla_stessa_durata(serie: NDArray[np.float32], e: int, durata_h: float) -> float | None:
    """I millimetri del radar sulla durata dell'evento al pluviometro, con la
    fine spostata al meglio entro ``_SPOSTAMENTO_ORE``; ``None`` se non misurati."""
    n = round(durata_h)
    if n <= 0:
        return None
    somme = []
    for sposta in range(-_SPOSTAMENTO_ORE, _SPOSTAMENTO_ORE + 1):
        fine = e + sposta
        if fine - n + 1 < 0 or fine >= len(serie):
            continue
        tratto = serie[fine - n + 1 : fine + 1]
        if float(np.isnan(tratto).mean()) <= 0.2:
            somme.append(float(np.nansum(tratto)))
    return max(somme) if somme else None


def istanti_ordinari(ore: int, occupati: Iterable[int], sfasamento: int = 0) -> list[int]:
    """Un'ora ogni ``_PASSO_ORDINARIE_GIORNI`` giorni, lontana dalle frane del punto.

    ``sfasamento`` sposta l'inizio, punto per punto: con lo stesso inizio per
    tutti si guarderebbero le stesse 97 date in tutta Italia, e la quota di
    momenti sopra la curva cambierebbe di tre punti spostandole di due settimane.
    """
    frane = list(occupati)
    passo = _PASSO_ORDINARIE_GIORNI * 24
    return [
        e
        for e in range(_STORIA_ORE + _FINESTRA_ORE + sfasamento % passo, ore, passo)
        if all(abs(e - x) >= _DISTANZA_GIORNI * 24 for x in frane)
    ]


def estrai(
    archivio: SriArchive, punti: list[tuple[float, float]], fine: datetime, cache: Path
) -> NDArray[np.float32]:
    """La pioggia oraria del radar nei punti, da ``_BASE`` a ``fine``: [ore x punti].

    ``NaN`` è un'ora non misurata. Un file per mese nella cache, legato
    all'elenco dei punti: se cambiano, la cache non vale più e si rifà.
    """
    cache.mkdir(parents=True, exist_ok=True)
    elenco = cache / "punti.json"
    if not elenco.exists() or json.loads(elenco.read_text()) != [list(p) for p in punti]:
        for vecchio in cache.glob("*.npy"):
            vecchio.unlink()
        elenco.write_text(json.dumps(punti))
    mesi = []
    inizio = _BASE.replace(day=1)
    while inizio < fine:
        dopo = datetime(inizio.year + (inizio.month == 12), inizio.month % 12 + 1, 1, tzinfo=UTC)
        file = cache / f"{inizio:%Y%m}.npy"
        if not file.exists():
            ore = int((dopo - inizio).total_seconds() // 3600)
            mese = np.full((ore, len(punti)), np.nan, dtype=np.float32)
            giorno = inizio
            while giorno < dopo:  # un giorno alla volta: la memoria resta piccola
                letto = archivio.hourly(punti, giorno, giorno + timedelta(days=1))
                for t, valori in letto.items():
                    i = int((t - inizio).total_seconds() // 3600) - 1
                    if 0 <= i < ore:
                        mese[i] = [np.nan if v is None else v for v in valori]
                giorno += timedelta(days=1)
            appoggio = file.with_suffix(".tmp.npy")
            np.save(appoggio, mese)
            appoggio.rename(file)
            log.info("misura_soglia_radar.mese", mese=file.stem)
        mesi.append(np.load(file))
        inizio = dopo
    tutto: NDArray[np.float32] = np.concatenate(mesi)
    return tutto[int((_BASE - _BASE.replace(day=1)).total_seconds() // 3600) :]


Ordinaria = tuple[tuple[float, float], float | None, float | None]


#: Le colonne del riepilogo per gruppo, per chi vuole rifare i conti senza i
#: momenti ordinari (rainfall-thresholds tiene i due CSV accanto alla libreria).
_CAMPI_RIEPILOGO = (
    "insieme",
    "gruppo",
    "pioggia",
    "frane_misurate",
    "frane_sopra_la_curva",
    "ordinarie_misurate",
    "ordinarie_sopra_la_curva",
    *(f"{nome}_{c:.0%}".replace("%", "") for c in _CARICHI for nome in ("soglia", "colte")),
    "auc",
)


def _misura(frane: list[float | None], ordinarie: list[float | None]) -> list[float | int] | None:
    """I numeri di una riga, nell'ordine di ``_CAMPI_RIEPILOGO`` dopo ``pioggia``."""
    if sum(v is not None for v in frane) < 3 or sum(v is not None for v in ordinarie) < 3:
        return None
    # `skill` conta «≥ soglia»: sopra la curva è un eccesso maggiore di zero.
    alla_curva = skill(frane, ordinarie, 1e-9)
    numeri: list[float | int] = [
        alla_curva.landslides,
        alla_curva.caught,
        alla_curva.ordinary,
        alla_curva.alerts,
    ]
    for carico in _CARICHI:
        a_carico = skill_at_budget(frane, ordinarie, carico)
        numeri += [a_carico.cutoff, a_carico.caught]
    separa = auc(frane, ordinarie)
    return [*numeri, float("nan") if separa is None else separa]


def blocco(
    titolo: str,
    frane: list[Frana],
    ordinarie: list[Ordinaria],
    riepilogo: list[list[object]] | None = None,
) -> list[str]:
    """La tabella frane contro momenti ordinari, radar e radar corretto.

    ``titolo`` è ``insieme: gruppo``; le stesse righe, come numeri, vanno in ``riepilogo``.
    """
    letture = (
        ("radar", [f.radar_eccesso for f in frane], [o[1] for o in ordinarie]),
        ("radar corretto", [f.radar_corretto_eccesso for f in frane], [o[2] for o in ordinarie]),
    )
    righe = []
    for nome, delle_frane, delle_ordinarie in letture:
        numeri = _misura(delle_frane, delle_ordinarie)
        if numeri is None:
            continue
        n, sopra, n_ordinarie, ordinarie_sopra, *a_carico, separa = numeri
        colte = a_carico[1::2]
        righe.append(
            f"| {nome} | {n} | {sopra / n:.1%} ({sopra}) | {ordinarie_sopra / n_ordinarie:.1%} | "
            + " | ".join(f"{c / n:.1%}" for c in colte)
            + f" | {separa:.2f} |"
        )
        if riepilogo is not None:
            insieme, _, gruppo = titolo.partition(": ")
            riepilogo.append([insieme, gruppo, nome, *numeri])
    if not righe:
        return []
    carichi = " | ".join(f"Colte al {c:.0%}" for c in _CARICHI)
    return [
        f"### {titolo}",
        "",
        "| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | "
        f"{carichi} | AUC |",
        "|---|---:|---:|---:|" + "---:|" * (len(_CARICHI) + 1),
        *righe,
        "",
    ]


def _mediana(valori: Iterable[float]) -> float:
    return statistics.median(valori)


def _sezione_pluviometro(frane: list[Frana]) -> list[str]:
    con = [f for f in frane if f.pluvio_mm and f.radar_mm_stessa_durata is not None]
    gruppi: dict[str, list[Frana]] = defaultdict(list)
    for f in con:
        gruppi[f.regione].append(f)
    maggiore = max(gruppi, key=lambda r: len(gruppi[r]), default="")
    gruppi = {
        "Tutte": con,
        f"Tutte senza {maggiore}": [f for f in con if f.regione != maggiore],
        **gruppi,
    }
    righe = [
        "## 1. Le stesse frane, al pluviometro e sul radar",
        "",
        "Radar sommato sulla durata dell'evento al pluviometro, fine spostata al meglio "
        f"entro ±{_SPOSTAMENTO_ORE} ore.",
        "",
        "| Regione | Frane | Pluviometro (mm, mediana) | Radar (mm, mediana) | "
        "Radar / pluviometro | Con la mappa del bias |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for nome, gruppo in sorted(gruppi.items(), key=lambda kv: -len(kv[1])):
        if len(gruppo) < 5:
            continue
        rapporti = [(f.radar_mm_stessa_durata or 0.0) / (f.pluvio_mm or 1.0) for f in gruppo]
        corretti = [
            (f.radar_mm_stessa_durata or 0.0) * f.fattore / (f.pluvio_mm or 1.0)
            for f in gruppo
            if f.fattore
        ]
        righe.append(
            f"| {nome} | {len(gruppo)} | {_mediana(f.pluvio_mm or 0.0 for f in gruppo):.0f} | "
            f"{_mediana(f.radar_mm_stessa_durata or 0.0 for f in gruppo):.0f} | "
            f"{_mediana(rapporti):.2f} | {f'{_mediana(corretti):.2f}' if corretti else 'n.d.'} |"
        )
    righe += [
        "",
        "Sopra la curva della macroregione, le stesse frane:",
        "",
        "| Insieme | Frane | Pluviometro | Radar | Radar corretto |",
        "|---|---:|---:|---:|---:|",
    ]
    misurate = [f for f in frane if f.pluvio_eccesso is not None and f.radar_eccesso is not None]
    scelte: list[tuple[str, Callable[[Frana], bool]]] = [
        ("Tutte", lambda _: True),
        (f"Senza {maggiore}", lambda f: f.regione != maggiore),
        (
            f"Radar affidabile (≥ {RELIABLE_FROM:g})",
            lambda f: (f.affidabilita or 0.0) >= RELIABLE_FROM,
        ),
    ]
    for nome, tiene in scelte:
        gruppo = [f for f in misurate if tiene(f)]
        if not gruppo:
            continue

        def quota(valori: Iterable[float | None], n: int = len(gruppo)) -> float:
            return sum((v if v is not None else SENZA_EVENTO) > 0 for v in valori) / n

        righe.append(
            f"| {nome} | {len(gruppo)} | {quota(f.pluvio_eccesso for f in gruppo):.1%} | "
            f"{quota(f.radar_eccesso for f in gruppo):.1%} | "
            f"{quota(f.radar_corretto_eccesso for f in gruppo):.1%} |"
        )
    return [*righe, ""]


def _sezione_ordinarie(
    frane: list[Frana], ordinarie: list[Ordinaria], riepilogo: list[list[object]]
) -> list[str]:
    righe = [
        "## 2. Frane contro momenti ordinari, sul radar",
        "",
        "«Colte al 2 %»: le frane sopra la soglia che accende il 2 % dei momenti ordinari.",
        "",
    ]
    for insieme in ("italica", "idrogeo"):
        sue = [f for f in frane if f.insieme == insieme]
        punti = {f.punto for f in sue}
        loro = [o for o in ordinarie if o[0] in punti]
        per_regione: dict[str, int] = defaultdict(int)
        for f in sue:
            per_regione[f.regione] += 1
        maggiore = max(per_regione, key=lambda r: per_regione[r], default="")
        buoni = {f.punto for f in sue if (f.affidabilita or 0.0) >= RELIABLE_FROM}
        fuori = {f.punto for f in sue if f.regione != maggiore}
        righe += blocco(f"{insieme}: tutte", sue, loro, riepilogo)
        righe += blocco(
            f"{insieme}: dove il radar è affidabile (≥ {RELIABLE_FROM:g})",
            [f for f in sue if f.punto in buoni],
            [o for o in loro if o[0] in buoni],
            riepilogo,
        )
        righe += blocco(
            f"{insieme}: dove il radar è poco affidabile",
            [f for f in sue if f.punto not in buoni],
            [o for o in loro if o[0] not in buoni],
            riepilogo,
        )
        righe += blocco(
            f"{insieme}: senza {maggiore}",
            [f for f in sue if f.punto in fuori],
            [o for o in loro if o[0] in fuori],
            riepilogo,
        )
        for macro in MACROREGIONS:
            suoi = {f.punto for f in sue if f.macro == macro}
            righe += blocco(
                f"{insieme}: {macro}",
                [f for f in sue if f.macro == macro],
                [o for o in loro if o[0] in suoi],
                riepilogo,
            )
    return righe


def _sezione_curva(frane: list[Frana]) -> list[str]:
    righe = [
        "## 3. Una curva tarata sul radar",
        "",
        "Inviluppo al 5° percentile (`fit_threshold`) sugli eventi radar delle frane, "
        "contro `ITALICA_T5`.",
        "",
        "| Insieme | Macroregione | Eventi | alfa | beta | alfa ITALICA_T5 | beta ITALICA_T5 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    note = []
    for insieme in ("italica", "idrogeo"):
        sue = [f for f in frane if f.insieme == insieme]
        for macro in ("italy", *MACROREGIONS):
            eventi = [
                (f.radar_durata_h, f.radar_mm / f.radar_durata_h)
                for f in sue
                if f.radar_durata_h and f.radar_mm and (macro == "italy" or f.macro == macro)
            ]
            if len(eventi) < 30:
                continue
            tarata = fit_threshold(eventi)
            righe.append(
                f"| {insieme} | {macro} | {tarata.n_events} | {tarata.threshold.alpha:.2f} | "
                f"{tarata.threshold.beta:.3f} | {ITALICA_T5[macro].alpha:.2f} | "
                f"{ITALICA_T5[macro].beta:.3f} |"
            )
        note.append(
            f"- {insieme}: {sum(f.radar_eccesso == SENZA_EVENTO for f in sue)} frane senza un "
            f"evento di pioggia sul radar nelle {_FINESTRA_ORE} ore, "
            f"{sum(f.radar_eccesso is None for f in sue)} non misurate."
        )
    return [*righe, "", *note, ""]


def scrivi(
    frane: list[Frana], ordinarie: list[Ordinaria], *, fine: datetime, non_misurate: float
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"misura_soglia_radar_{STRUMENTO_DI_OGGI.year}_{(fine - timedelta(days=1)).year}"
    with (REPORTS_DIR / f"{nome}.csv").open("w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f, lineterminator="\n")
        scrittore.writerow(_CAMPI)
        for frana in frane:
            valori = [frana.macro if c == "macro" else getattr(frana, c) for c in _CAMPI]
            scrittore.writerow([round(v, 4) if isinstance(v, float) else v for v in valori])
    conta = {i: sum(f.insieme == i for f in frane) for i in ("italica", "idrogeo")}
    testa = [
        "# La soglia dei pluviometri sulla pioggia del radar (#677)",
        "",
        f"- Radar: IT-DPC-SRI (FBK su dati DPC, CC BY-SA 4.0, doi:10.5281/zenodo.18637608), "
        f"{STRUMENTO_DI_OGGI.year}-{(fine - timedelta(days=1)).year}, in "
        f"{len({f.punto for f in frane})} punti di frana; {non_misurate:.1%} delle ore-punto "
        "non misurato.",
        f"- Frane: {conta['italica']} di e-ITALICA v4 (CC BY 4.0, doi:10.5281/zenodo.14204473), "
        f"{conta['idrogeo']} di IdroGEO datate al giorno (ISPRA, IFFI ed eventi, CC BY-SA 4.0).",
        f"- Momenti ordinari: {len(ordinarie)} (gli stessi punti, ogni "
        f"{_PASSO_ORDINARIE_GIORNI} giorni con un inizio diverso per punto, ad almeno "
        f"{_DISTANZA_GIORNI} da una frana lì).",
        f"- Punteggio: l'eccesso più alto sulla curva `ITALICA_T5` della macroregione fra gli "
        f"eventi che toccano le {_FINESTRA_ORE} ore prima, ricostruiti come fa il motore.",
        f"- Una riga per frana in `{nome}.csv`, una per gruppo in `{nome}_gruppi.csv`.",
        "",
        "Limiti: il radar è letto nel punto della frana, il pluviometro è quello più vicino di "
        "e-ITALICA; le durate di e-ITALICA vengono da un'altra ricostruzione degli eventi; i "
        "momenti ordinari sono solo in punti dove c'è stata una frana; la mappa del bias è "
        "costruita sul 2026, contro il «Merging».",
        "",
    ]
    riepilogo: list[list[object]] = []
    corpo = [
        *testa,
        *_sezione_pluviometro([f for f in frane if f.insieme == "italica"]),
        *_sezione_ordinarie(frane, ordinarie, riepilogo),
        *_sezione_curva(frane),
    ]
    with (REPORTS_DIR / f"{nome}_gruppi.csv").open("w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f, lineterminator="\n")
        scrittore.writerow(_CAMPI_RIEPILOGO)
        for riga in riepilogo:
            scrittore.writerow([round(v, 4) if isinstance(v, float) else v for v in riga])
    return provenienza.scrivi_report(REPORTS_DIR / f"{nome}.md", "\n".join(corpo))


async def run() -> int:
    zarr = Path(os.getenv("LIMEN_BACKTEST_RADAR_ZARR") or radice_dati() / _RADAR_ZARR)
    if not zarr.is_dir():
        log.error("misura_soglia_radar.zarr_assente", path=str(zarr), rimedio="make radar-data")
        return 1
    cache = Path(os.getenv("LIMEN_SOGLIA_RADAR_CACHE") or radice_dati() / "radar" / "soglia_radar")
    archivio = SriArchive(zarr)
    ultimo = archivio.last
    fine = datetime(ultimo.year, ultimo.month, ultimo.day, tzinfo=UTC) + timedelta(days=1)
    try:
        csv_italica = await _resolve_csv()
        if csv_italica is None:
            return 1
        cache.mkdir(parents=True, exist_ok=True)
        frane = [
            *frane_italica(csv_italica),
            *await frane_idrogeo((fine - timedelta(days=1)).date(), cache),
        ]
    finally:
        await SharedHttpClient.aclose()

    punti = sorted({f.punto for f in frane})
    pioggia = estrai(archivio, punti, fine, cache)
    colonna = {p: i for i, p in enumerate(punti)}
    ricostruzione = load_regional_thresholds().caine.event_reconstruction
    occupati: dict[tuple[float, float], list[int]] = defaultdict(list)
    for f in frane:
        occupati[f.punto].append(indice(f.istante))

    def misura(
        punto: tuple[float, float], e: int, soglia: PowerLawThreshold, fattore: float = 1.0
    ) -> tuple[float | None, float | None, float | None]:
        return punteggio(
            pioggia[:, colonna[punto]],
            e,
            soglia,
            pausa_ore=ricostruzione.no_rain_break_hours,
            minimo_mm=ricostruzione.min_event_mm,
            fattore=fattore,
        )

    fattori = {p: radar_factor(*p) for p in punti}
    for f in frane:
        soglia = ITALICA_T5[f.macro]
        e = indice(f.istante)
        f.affidabilita = reliability(*f.punto).score
        f.fattore = fattori[f.punto]
        f.radar_eccesso, f.radar_durata_h, f.radar_mm = misura(f.punto, e, soglia)
        if f.fattore:
            f.radar_corretto_eccesso = misura(f.punto, e, soglia, f.fattore)[0]
        if f.pluvio_mm and f.pluvio_durata_h:
            f.pluvio_eccesso = soglia.exceedance(f.pluvio_mm / f.pluvio_durata_h, f.pluvio_durata_h)
            f.radar_mm_stessa_durata = sulla_stessa_durata(
                pioggia[:, colonna[f.punto]], e, f.pluvio_durata_h
            )

    macro_del_punto = {f.punto: f.macro for f in frane}
    ordinarie: list[Ordinaria] = []
    for punto, ore_frana in occupati.items():
        soglia = ITALICA_T5[macro_del_punto[punto]]
        fattore = fattori[punto]
        sfasamento = colonna[punto] * _SFASAMENTO_ORE
        for e in istanti_ordinari(len(pioggia), ore_frana, sfasamento):
            ordinarie.append(
                (
                    punto,
                    misura(punto, e, soglia)[0],
                    misura(punto, e, soglia, fattore)[0] if fattore else None,
                )
            )
    report = scrivi(frane, ordinarie, fine=fine, non_misurate=float(np.isnan(pioggia).mean()))
    log.info(
        "misura_soglia_radar.done",
        report=str(report),
        frane=len(frane),
        ordinarie=len(ordinarie),
    )
    return 0
