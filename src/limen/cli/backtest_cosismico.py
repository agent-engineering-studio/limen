"""``limen backtest-cosismico`` — lo scuotimento ShakeMap contro le frane sismoindotte.

La domanda della componente sismica E, posta al dato giusto: **le frane che un
terremoto ha innescato stanno dove la ShakeMap INGV dice che ha tremato di
più?** Il backtest #287 aveva misurato E sulle frane di ITALICA, che sono solo
da pioggia, e non poteva premiarla: una frana sismoindotta lì non c'è.

Verità: un inventario di frane cosismiche per evento, un file che GeoPandas
sappia leggere (punti o poligoni, in qualunque CRS dichiarato). Il CEDIT della
Sapienza (CERI) è pubblicato per evento da USGS, in CC0
(«Earthquake-induced ground failures in Italy from a reviewed database»).

È un confronto caso-controllo sui punti della ShakeMap, non un replay:

* **casi**: il punto di griglia più vicino a ogni frana (passo ~900 m, la
  scala delle celle di Limen), contato una volta sola;
* **controlli**: tutti gli altri punti della griglia **su terra italiana** —
  i confini delle regioni del seme nazionale, senza database. Il mare non
  frana e abbasserebbe lo scuotimento dei controlli a favore di qualunque
  misura.

Per PGA, PGV e MMI si dà l'**AUC** (la probabilità che un punto franato abbia
tremato più di un punto qualunque), accanto a quella della sola **vicinanza
all'epicentro**: se la ShakeMap non batte la distanza, alla mappa non serve
scaricare 12 MB. Per una serie di soglie di PGA, compresa ``seismic.pga_min_g``
(la soglia sotto cui E vale zero), recall, carico (la quota di territorio sopra
soglia) e il loro rapporto, il **lift**: lo stesso metro della
discriminazione spaziale degli altri backtest.

Non c'è la pendenza: questo dice se lo scuotimento separa, non se un modello
con il terreno separa meglio. È la fase dopo (modello «ground failure»).

Env:

* ``LIMEN_BACKTEST_COSISMICO`` — ``id_evento=percorso`` separati da virgole,
  l'id INGV (FDSN/ShakeMap) e l'inventario delle sue frane;
* ``LIMEN_BACKTEST_COSISMICO_CACHE`` — dove tenere le ShakeMap scaricate
  (default ``reports/shakemap``): 5-18 MB l'una, e il backtest si rigira.
"""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
import shapely
from ingv_shakemap import ShakeGrid
from shapely.geometry.base import BaseGeometry

from limen.cli import provenienza
from limen.core.logging import get_logger
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.seed.loader import load_regions
from limen.integrations._http import SharedHttpClient
from limen.integrations.ingv.shakemap_client import IngvHttpClient, IngvNonDisponibileError
from limen.integrations.ingv.shakemap_grid import GrigliaNonValidaError, leggi_griglia

log = get_logger(__name__)

REPORTS_DIR = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
_EVENTI_ENV = "LIMEN_BACKTEST_COSISMICO"
_CACHE_ENV = "LIMEN_BACKTEST_COSISMICO_CACHE"

#: Le soglie di PGA del report, in g, oltre a ``seismic.pga_min_g``.
SOGLIE_PGA_G: tuple[float, ...] = (0.02, 0.05, 0.1, 0.2, 0.3)
#: Le misure confrontate, nell'ordine del report.
MISURE: tuple[str, ...] = ("PGA", "PGV", "MMI", "vicinanza")


@dataclass(frozen=True, slots=True)
class Soglia:
    pga_g: float
    #: Quota dei punti franati con PGA ≥ soglia.
    recall: float
    #: Quota dei punti su terra con PGA ≥ soglia.
    carico: float

    @property
    def lift(self) -> float | None:
        return self.recall / self.carico if self.carico > 0 else None


@dataclass(frozen=True, slots=True)
class EsitoEvento:
    event_id: str
    frane: int
    #: Frane cadute su un punto di griglia su terra; le altre stanno fuori mappa.
    frane_in_mappa: int
    #: Punti di griglia distinti con almeno una frana: i casi.
    casi: int
    punti_terra: int
    auc: dict[str, float | None]
    #: L'AUC dentro l'area dove E è acceso (PGA ≥ ``pga_min_g``): casi e
    #: controlli lì soltanto. Sull'intera mappa vince qualunque misura che
    #: cresca verso l'epicentro, anche la sola distanza.
    auc_campo_vicino: dict[str, float | None]
    soglie: tuple[Soglia, ...]
    pga_mediana_casi_g: float | None
    versione: int | None = None
    stato: str | None = None


def auc(casi: npt.ArrayLike, controlli: npt.ArrayLike) -> float | None:
    """L'AUC di Mann-Whitney: P(caso > controllo), i pareggi contano mezzo.

    ``None`` senza casi o senza controlli. I NaN si scartano.
    """
    a = np.asarray(casi, dtype=float)
    b = np.asarray(controlli, dtype=float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if a.size == 0 or b.size == 0:
        return None
    valori = np.concatenate([a, b])
    ordine = np.argsort(valori, kind="mergesort")
    ranghi = np.empty(valori.size, dtype=float)
    ordinati = valori[ordine]
    # Ranghi medi sui pareggi: inizio e fine di ogni gruppo di valori uguali.
    inizi = np.flatnonzero(np.r_[True, ordinati[1:] != ordinati[:-1]])
    fini = np.r_[inizi[1:], ordinati.size]
    medi = (inizi + fini - 1) / 2.0 + 1.0
    ranghi[ordine] = np.repeat(medi, fini - inizi)
    u = ranghi[: a.size].sum() - a.size * (a.size + 1) / 2.0
    return float(u / (a.size * b.size))


def _distanza_km(
    lon: npt.NDArray[np.float64], lat: npt.NDArray[np.float64], lon0: float, lat0: float
) -> npt.NDArray[np.float64]:
    p1, p2 = np.radians(lat), math.radians(lat0)
    a = (
        np.sin((p2 - p1) / 2) ** 2
        + np.cos(p1) * math.cos(p2) * np.sin(np.radians(lon0 - lon) / 2) ** 2
    )
    return np.asarray(2 * 6371.0 * np.arcsin(np.sqrt(a)), dtype=float)


def italia() -> BaseGeometry:
    """La terra italiana: l'unione delle regioni del seme nazionale."""
    return shapely.union_all([r.geom for r in load_regions()])


def valuta(
    griglia: ShakeGrid,
    frane: Sequence[tuple[float, float]],
    terra: BaseGeometry,
    *,
    event_id: str,
    epicentro: tuple[float, float] | None = None,
    soglie_pga_g: Sequence[float] = SOGLIE_PGA_G,
    pga_min_g: float = 0.02,
) -> EsitoEvento:
    """Lo scuotimento dei punti franati contro quello di tutta la terra in mappa."""
    nlat, nlon = griglia.nlat, griglia.nlon
    cols, rows = np.meshgrid(np.arange(nlon), np.arange(nlat))
    lons = np.asarray(griglia.lon_min + cols.ravel() * griglia.lon_step, dtype=np.float64)
    lats = np.asarray(griglia.lat_max - rows.ravel() * griglia.lat_step, dtype=np.float64)
    su_terra = shapely.contains_xy(terra, lons, lats)

    caso = np.zeros(lons.size, dtype=bool)
    in_mappa = 0
    if frane:
        f_lon = np.array([f[0] for f in frane], dtype=float)
        f_lat = np.array([f[1] for f in frane], dtype=float)
        c = np.rint((f_lon - griglia.lon_min) / griglia.lon_step)
        r = np.rint((griglia.lat_max - f_lat) / griglia.lat_step)
        dentro = (c >= 0) & (c < nlon) & (r >= 0) & (r < nlat)
        indici = (r[dentro] * nlon + c[dentro]).astype(int)
        indici = indici[su_terra[indici]]
        in_mappa = int(indici.size)
        caso[indici] = True
    controllo = su_terra & ~caso

    pga = griglia.sample_g("PGA", lons, lats)
    misure: dict[str, npt.NDArray[np.float64]] = {"PGA": pga}
    for nome in ("PGV", "MMI"):
        if nome in griglia.fields:
            misure[nome] = griglia.sample(nome, lons, lats)
    ev = griglia.event
    if epicentro is None and ev.longitude is not None and ev.latitude is not None:
        epicentro = (ev.longitude, ev.latitude)
    if epicentro is not None:
        misure["vicinanza"] = -_distanza_km(lons, lats, *epicentro)

    vicino = pga >= pga_min_g
    n_terra = int(su_terra.sum())
    soglie = tuple(
        Soglia(
            pga_g=s,
            recall=float((pga[caso] >= s).mean()) if caso.any() else 0.0,
            carico=float((pga[su_terra] >= s).sum() / n_terra) if n_terra else 0.0,
        )
        for s in sorted(set(soglie_pga_g))
    )
    return EsitoEvento(
        event_id=event_id,
        frane=len(frane),
        frane_in_mappa=in_mappa,
        casi=int(caso.sum()),
        punti_terra=n_terra,
        auc={
            nome: auc(misure[nome][caso], misure[nome][controllo]) if nome in misure else None
            for nome in MISURE
        },
        auc_campo_vicino={
            nome: auc(misure[nome][caso & vicino], misure[nome][controllo & vicino])
            if nome in misure
            else None
            for nome in MISURE
        },
        soglie=soglie,
        pga_mediana_casi_g=float(np.median(pga[caso])) if caso.any() else None,
    )


def leggi_inventario(percorso: Path) -> list[tuple[float, float]]:
    """Le frane di un inventario come (lon, lat) in WGS84; un poligono vale un suo punto interno."""
    import geopandas as gpd

    gdf = gpd.read_file(percorso)
    if gdf.crs is not None:
        gdf = gdf.to_crs(4326)
    punti = gdf.geometry.dropna().representative_point()
    return [(float(p.x), float(p.y)) for p in punti if not p.is_empty]


def parse_eventi(valore: str) -> list[tuple[str, Path]]:
    """``id=percorso,id=percorso`` → coppie; solleva ``ValueError`` su un pezzo storto."""
    coppie: list[tuple[str, Path]] = []
    for pezzo in filter(None, (p.strip() for p in valore.split(","))):
        event_id, sep, percorso = pezzo.partition("=")
        if not sep or not event_id.strip() or not percorso.strip():
            raise ValueError(f"atteso id=percorso, trovato {pezzo!r}")
        coppie.append((event_id.strip(), Path(percorso.strip())))
    return coppie


def auc_media(
    esiti: Sequence[EsitoEvento], misura: str, *, campo_vicino: bool = False
) -> float | None:
    """L'AUC di ``misura`` mediata sugli eventi, ognuno pesato per i suoi casi."""
    pesi = [
        (a, e.casi)
        for e in esiti
        if (a := (e.auc_campo_vicino if campo_vicino else e.auc).get(misura)) is not None and e.casi
    ]
    totale = sum(n for _, n in pesi)
    return sum(a * n for a, n in pesi) / totale if totale else None


def _fmt(x: float | None, formato: str = ".3f") -> str:
    return "—" if x is None else format(x, formato)


def _tabella_auc(esiti: Sequence[EsitoEvento], titolo: str, *, campo_vicino: bool) -> list[str]:
    righe = [
        f"### {titolo}",
        "",
        "| Evento | " + " | ".join(MISURE) + " |",
        "|---|" + "---|" * len(MISURE),
    ]
    for e in esiti:
        valori = e.auc_campo_vicino if campo_vicino else e.auc
        righe.append(f"| {e.event_id} | " + " | ".join(_fmt(valori[m]) for m in MISURE) + " |")
    if len(esiti) > 1:
        medie = " | ".join(
            f"**{_fmt(auc_media(esiti, m, campo_vicino=campo_vicino))}**" for m in MISURE
        )
        righe.append(f"| **media pesata sui casi** | {medie} |")
    return [*righe, ""]


def write_report(esiti: Sequence[EsitoEvento], *, pga_min_g: float) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"backtest_cosismico_{datetime.now(UTC):%Y%m%d}.md"
    righe = [
        "# Limen backtest cosismico — scuotimento ShakeMap contro frane sismoindotte",
        "",
        f"Generato: {datetime.now(UTC).isoformat()}",
        f"Soglia di E (`seismic.pga_min_g`): **{pga_min_g:g} g**",
        "",
        "## Eventi",
        "",
        "| Evento | ShakeMap | Frane | In mappa | Casi | Punti su terra | PGA mediana casi |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in esiti:
        mappa = f"v{e.versione} {e.stato or ''}".strip() if e.versione is not None else "—"
        righe.append(
            f"| {e.event_id} | {mappa} | {e.frane} | {e.frane_in_mappa} | {e.casi} | "
            f"{e.punti_terra} | {_fmt(e.pga_mediana_casi_g)} g |"
        )
    righe += [
        "",
        "## AUC: le frane stanno dove ha tremato di più?",
        "",
        "0,5 è il caso; 1 separa perfettamente. `vicinanza` è la sola distanza",
        "dall'epicentro: è il riferimento che la ShakeMap deve battere.",
        "",
    ]
    righe += _tabella_auc(esiti, "Su tutta la terra in mappa", campo_vicino=False)
    righe += _tabella_auc(
        esiti,
        f"Nel campo vicino: solo dove E è acceso (PGA ≥ {pga_min_g:g} g)",
        campo_vicino=True,
    )
    righe += [
        "La seconda tabella è quella che decide: sull'intera mappa vince",
        "qualunque misura che cresca verso l'epicentro, anche la sola distanza.",
        "",
        "## Soglie di PGA: recall, carico, lift",
        "",
        "Recall: la quota di punti franati sopra soglia. Carico: la quota di",
        "territorio in mappa sopra soglia. Lift = recall / carico: quante volte",
        "la soglia concentra le frane rispetto al caso.",
        "",
        "| Evento | PGA ≥ | Recall | Carico | Lift |",
        "|---|---|---|---|---|",
    ]
    for e in esiti:
        for s in e.soglie:
            segno = " ← E" if math.isclose(s.pga_g, pga_min_g) else ""
            righe.append(
                f"| {e.event_id} | {s.pga_g:g} g{segno} | {s.recall:.1%} | {s.carico:.1%} | "
                f"{_fmt(s.lift, '.2f')} |"
            )
    righe += [
        "",
        "> Lo scuotimento solo, senza il terreno: una frana chiede un versante,",
        "> e un AUC alto della PGA in pianura non vuol dire nulla. La pendenza",
        "> entra con il modello «ground failure», sulle celle di Limen.",
        "",
    ]
    provenienza.scrivi_report(out, "\n".join(righe))
    return out


async def _griglia(client: IngvHttpClient, event_id: str, cache: Path) -> ShakeGrid | None:
    file = cache / f"{event_id}.xml"
    if file.exists():
        grezzo: bytes | None = file.read_bytes()
    else:
        grezzo = await client.fetch_shakemap_grid(event_id, solleva=True)
        if grezzo is not None:
            cache.mkdir(parents=True, exist_ok=True)
            file.write_bytes(grezzo)
    if grezzo is None:
        return None
    return await asyncio.to_thread(leggi_griglia, grezzo)


async def run() -> int:
    try:
        eventi = parse_eventi(os.getenv(_EVENTI_ENV, ""))
    except ValueError as exc:
        log.error("backtest_cosismico.bad_env", var=_EVENTI_ENV, error=str(exc))
        return 1
    if not eventi:
        log.error("backtest_cosismico.nessun_evento", hint=f"{_EVENTI_ENV}=id=percorso,...")
        return 1
    cache = Path(os.getenv(_CACHE_ENV, str(REPORTS_DIR / "shakemap")))
    pga_min_g = load_regional_thresholds().seismic.pga_min_g
    terra = italia()
    client = IngvHttpClient()
    esiti: list[EsitoEvento] = []
    try:
        for event_id, percorso in eventi:
            frane = leggi_inventario(percorso)
            griglia = await _griglia(client, event_id, cache)
            if griglia is None:
                log.warning("backtest_cosismico.senza_shakemap", event_id=event_id)
                continue
            info = await client.fetch_info(event_id, solleva=True)
            esito = valuta(
                griglia,
                frane,
                terra,
                event_id=event_id,
                soglie_pga_g=(*SOGLIE_PGA_G, pga_min_g),
                pga_min_g=pga_min_g,
            )
            if info is not None:
                esito = replace(esito, versione=info.version, stato=info.map_status)
            log.info(
                "backtest_cosismico.evento",
                event_id=event_id,
                frane=esito.frane,
                casi=esito.casi,
                auc_pga=esito.auc["PGA"],
                auc_vicinanza=esito.auc["vicinanza"],
            )
            esiti.append(esito)
    except (IngvNonDisponibileError, GrigliaNonValidaError) as exc:
        log.error("backtest_cosismico.ingv", error=str(exc))
        return 1
    finally:
        await SharedHttpClient.aclose()
    report = write_report(esiti, pga_min_g=pga_min_g)
    log.info("backtest_cosismico.report", path=str(report), eventi=len(esiti))
    return 0


__all__ = [
    "MISURE",
    "SOGLIE_PGA_G",
    "EsitoEvento",
    "Soglia",
    "auc",
    "auc_media",
    "italia",
    "leggi_inventario",
    "parse_eventi",
    "run",
    "valuta",
    "write_report",
]
