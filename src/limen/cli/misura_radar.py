"""``limen misura-radar`` — che cosa c'è, e quanto vale, l'archivio del «Merging» (#625-#629).

Solo misure: niente cambia nei motori. Legge l'archivio che il passo notturno
``radar_archivio`` tiene dalla #240 (``RADAR_ARCHIVE__CARTELLA``) e scrive un
report con cinque parti, una per domanda rimasta aperta nell'appendice E del
libro:

* **copertura** (#625): fotogrammi CUM3 e SRT1 in archivio per mese, quelli che
  il DPC non teneva più, la data del primo. È il dato per la lettera al DPC.
* **richieste** (#627): quante richieste al giorno fa Limen al servizio radar,
  contate dalla configurazione (sveglia, pioggia caduta, catena degli incendi,
  archivio).
* **bollettini** (#629): per ogni giorno con le otto CUM3, la pioggia media e
  massima delle 24 ore UTC in ogni zona di allerta, accanto al colore
  annunciato dall'ultimo bollettino del giorno prima. Nessun giudizio sul
  bollettino: l'allerta parla di effetti al suolo, non di millimetri.
* **qualità** (#628): per blocco di ``_PASSO_BLOCCO`` gradi e per giorno
  piovoso, il rapporto fra il solo radar (somma delle 24 SRT1) e il «Merging»
  (somma delle otto CUM3); la mediana per blocco è la mappa stimata, scritta
  anche come GeoTIFF accanto al report.
* **limen** (#629): accanto al colore annunciato in ogni zona, la classe più
  alta che le corse previsionali per cella di Limen avevano dato a quel giorno
  prima dell'emissione del bollettino, per frane e alluvioni, sulla scala
  della Protezione civile di ``pc_alert`` (YAML del pericolo). Legge il
  database, non l'archivio del radar.
* **adozione** (#643): che cosa farebbero gli usi del radar ancora spenti
  (radar cieco, rarità, nowcast, bias della sveglia) sugli eventi verificati e
  su un campione di giorni: vedi ``misura_radar_adozione``. Legge il database e
  l'API del DPC, non l'archivio.
* **ore** (#626): le ore ricostruite (CUM3 ripartito con lo SRT1) e quelle del
  solo radar contro i pluviometri a 10 minuti di ARPA Lombardia. Una parte di
  quei pluviometri è già dentro il «Merging»: il confronto non è indipendente.

Env: ``LIMEN_RADAR_DAL`` / ``LIMEN_RADAR_AL`` (giorni, default tutto
l'archivio; per ``limen`` senza archivio, gli ultimi ``_GIORNI_LIMEN`` giorni),
``LIMEN_RADAR_MISURE`` (default tutte tranne ``adozione``, che va chiesta:
``copertura,richieste,bollettini,qualita,limen,ore``; ``richieste``, ``limen``
e ``adozione`` girano anche senza l'archivio),
``LIMEN_RADAR_AREE`` (aree monitorate per il conto delle richieste, 20).
Report in ``LIMEN_REPORTS_DIR``.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from dpc_radar import RainGrid
from dpc_radar.bulletins import COLOURS, Zone, issued
from numpy.typing import NDArray

from limen.cli import misura_radar_adozione as adozione
from limen.cli import provenienza
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import PcAlertMapping, load_hazard_thresholds
from limen.data.db import lifespan_pool
from limen.data.repos import carico_repo
from limen.integrations._http import SharedHttpClient
from limen.integrations.arpa_lombardia import pluviometri
from limen.integrations.dpc import bollettini
from limen.integrations.dpc.merging_archive import PASSI, MergingArchive, istanti

log = get_logger(__name__)

MISURE = ("copertura", "richieste", "bollettini", "qualita", "limen", "ore", "adozione")
_SENZA_ARCHIVIO = {"richieste", "limen", "adozione"}
_COLORI = {0: "nessuna", 1: "gialla", 2: "arancione", 3: "rossa"}
assert _COLORI.keys() == COLOURS.keys()
_FILE_ASSENTI = ("absent.txt", "assenti.txt")
#: Una zona conta se almeno questa quota dei suoi pixel è misurata.
_QUOTA_MISURATA = 0.5
_TANTA_PIOGGIA_MM = 50.0
_POCA_PIOGGIA_MM = 10.0
#: Il riquadro della mappa di qualità (ovest, sud, est, nord) e il lato del blocco.
_ITALIA = (6.0, 35.0, 19.0, 48.0)
_PASSO_BLOCCO = 0.1
#: Sotto questa pioggia del «Merging» sul blocco il rapporto è rumore.
_GIORNO_PIOVOSO_MM = 5.0
_GIORNI_MINIMI = 5
_LOMBARDIA = (8.4, 44.6, 11.5, 46.7)
_RAGGIO_PLUVIOMETRO_KM = 0.5
_GIORNI_PER_RICHIESTA = 10
_ORA_PIOVOSA_MM = 1.0
_ORA_FORTE_MM = 30.0
#: Il DPC pubblica una cumulata nuova ogni mezz'ora.
_CUMULATE_AL_GIORNO = 48
#: ``limen`` senza archivio e senza ``LIMEN_RADAR_DAL``: quanti giorni indietro.
_GIORNI_LIMEN = 90


# ── copertura (#625) ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Copertura:
    prodotto: str
    mese: str
    attesi: int
    presenti: int
    persi: int


def _istante(testo: str) -> datetime | None:
    try:
        return datetime.strptime(testo, "%Y%m%d%H%M").replace(tzinfo=UTC)
    except ValueError:
        return None


def in_archivio(cartella: Path, prodotto: str) -> set[datetime]:
    """Gli istanti dei fotogrammi di ``prodotto`` che sono sul disco."""
    trovati = (
        _istante(f.stem.rsplit("_", 1)[-1])
        for f in (cartella / prodotto).glob(f"*/*/*/{prodotto}_*.tif")
    )
    return {t for t in trovati if t is not None}


def persi(cartella: Path, prodotto: str) -> set[datetime]:
    """Gli istanti che il DPC non teneva più quando l'archivio li ha chiesti."""
    out: set[datetime] = set()
    for nome in _FILE_ASSENTI:
        elenco = cartella / prodotto / nome
        if elenco.exists():
            out.update(t for riga in elenco.read_text().split() if (t := _istante(riga)))
    return out


def copertura(cartella: Path) -> list[Copertura]:
    """Per prodotto e mese: fotogrammi attesi fra il primo e l'ultimo noto, presenti, persi."""
    out: list[Copertura] = []
    for prodotto in PASSI:
        presenti, assenti = in_archivio(cartella, prodotto), persi(cartella, prodotto)
        noti = presenti | assenti
        if not noti:
            continue
        per_mese: dict[str, list[datetime]] = defaultdict(list)
        for t in istanti(prodotto, min(noti), max(noti)):
            per_mese[f"{t:%Y-%m}"].append(t)
        out += [
            Copertura(
                prodotto,
                mese,
                attesi=len(attesi),
                presenti=sum(t in presenti for t in attesi),
                persi=sum(t in assenti and t not in presenti for t in attesi),
            )
            for mese, attesi in sorted(per_mese.items())
        ]
    return out


# ── richieste (#627) ─────────────────────────────────────────────────────────


def richieste_al_giorno(
    *, aree: int, sveglia_minuti: int, giro_minuti: int
) -> list[tuple[str, int, int]]:
    """``(voce, richieste al servizio, file scaricati)`` in un giorno a regime.

    Un fotogramma costa due richieste al servizio (qual è l'ultimo, e il link)
    e un file; se l'ultimo è quello già in memoria si ferma alla prima. La
    sveglia non tiene niente in memoria: l'SRI cambia ogni cinque minuti. La
    pioggia caduta chiede l'ultimo a ogni giro per ogni area e scarica solo i
    fotogrammi nuovi, più quello di mezz'ora prima per il controllo (#235).
    L'archivio a regime salva otto CUM3 e ventiquattro SRT1, senza chiedere
    qual è l'ultimo.
    """
    cicli = 24 * 60 // sveglia_minuti
    giri = 24 * 60 // giro_minuti
    nuove = 2 * min(giri, _CUMULATE_AL_GIORNO)
    archivio = sum(24 // passo for passo in PASSI.values())
    return [
        ("sveglia (SRI)", 2 * cicli, cicli),
        ("pioggia caduta (CUM)", giri * aree + nuove, nuove),
        ("catena degli incendi (CUM24)", 2, 2),
        ("archivio (CUM3 e SRT1)", archivio, archivio),
    ]


# ── la pioggia di un giorno ──────────────────────────────────────────────────


def fine_blocchi(prodotto: str, giorno: date) -> list[datetime]:
    """Gli istanti dei fotogrammi che coprono le 24 ore UTC di ``giorno``."""
    mezzanotte = datetime.combine(giorno, time(0), UTC)
    passo = PASSI[prodotto]
    return [mezzanotte + timedelta(hours=h) for h in range(passo, 24 + passo, passo)]


def somma_del_giorno(archivio: MergingArchive, prodotto: str, giorno: date) -> RainGrid | None:
    """La pioggia delle 24 ore UTC, o ``None`` se manca anche un solo fotogramma.

    Un pixel senza dato in un fotogramma resta senza dato nella somma.
    """
    fotogrammi = [archivio.leggi(prodotto, t) for t in fine_blocchi(prodotto, giorno)]
    primo = fotogrammi[0]
    if primo is None or any(f is None or f.data.shape != primo.data.shape for f in fotogrammi):
        return None
    dati = np.sum([f.data for f in fotogrammi if f is not None], axis=0, dtype=np.float32)
    return RainGrid(primo.product, fotogrammi[-1].time, dati, primo.transform, primo.crs)  # type: ignore[union-attr]


def giorni_completi(cartella: Path, prodotto: str, dal: date | None, al: date | None) -> list[date]:
    """I giorni di cui l'archivio ha tutti i fotogrammi di ``prodotto``."""
    presenti = in_archivio(cartella, prodotto)
    giorni = sorted({(t - timedelta(minutes=1)).date() for t in presenti})
    return [
        g
        for g in giorni
        if (dal is None or g >= dal)
        and (al is None or g <= al)
        and all(t in presenti for t in fine_blocchi(prodotto, g))
    ]


# ── bollettini (#629) ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ZonaGiorno:
    giorno: date
    zona: str
    livello: int
    media: float
    massimo: float


class Maschere:
    """I pixel di ogni zona di allerta: si calcolano una volta, le zone non cambiano ogni giorno."""

    def __init__(self) -> None:
        self._indici: dict[tuple[Any, ...], NDArray[np.intp]] = {}

    def indici(self, zona: Zone, griglia: RainGrid) -> NDArray[np.intp]:
        from rasterio.features import geometry_mask

        chiave = (zona.name, zona.geometry.bounds, griglia.data.shape, tuple(griglia.transform))
        if chiave not in self._indici:
            dentro = geometry_mask(
                [zona.geometry], griglia.data.shape, griglia.transform, invert=True
            )
            self._indici[chiave] = np.flatnonzero(dentro)
        return self._indici[chiave]


def pioggia_di_zona(
    valori: NDArray[np.float32], indici: NDArray[np.intp]
) -> tuple[float, float] | None:
    """Media e massimo sui pixel della zona, o ``None`` se è misurata per meno di metà."""
    dentro = valori.ravel()[indici]
    misurati = dentro[np.isfinite(dentro)]
    if misurati.size == 0 or misurati.size < _QUOTA_MISURATA * dentro.size:
        return None
    return float(misurati.mean()), float(misurati.max())


def bollettino_per(nomi: list[str], giorno: date) -> str | None:
    """L'ultimo bollettino emesso il giorno prima di ``giorno``: il suo «domani» è ``giorno``."""
    vigilia = giorno - timedelta(days=1)
    del_giorno = [n for n in nomi if (e := issued(n)) is not None and e.date() == vigilia]
    return max(del_giorno, default=None)


def zone_del_giorno(
    griglia: RainGrid, zone: list[Zone], giorno: date, maschere: Maschere
) -> list[ZonaGiorno]:
    out: list[ZonaGiorno] = []
    for z in zone:
        if z.valid != giorno:
            continue
        letta = pioggia_di_zona(griglia.data, maschere.indici(z, griglia))
        if letta is not None:
            out.append(ZonaGiorno(giorno, z.name, z.level, *letta))
    return out


def _quartili(valori: list[float]) -> tuple[float, float, float]:
    q1, q2, q3 = np.percentile(np.asarray(valori), [25, 50, 75])
    return float(q1), float(q2), float(q3)


def _quota(parte: int, tutto: int) -> str:
    return "—" if tutto == 0 else f"{100 * parte / tutto:.1f} %"


def righe_bollettini(zg: list[ZonaGiorno], senza_bollettino: int) -> list[str]:
    giorni = len({r.giorno for r in zg})
    righe = [
        "## Allerta annunciata e pioggia caduta (#629)",
        "",
        f"Giorni confrontati: **{giorni}**; zone-giorno: **{len(zg)}**; zone diverse: "
        f"{len({r.zona for r in zg})}. Giorni con la pioggia ma senza un bollettino della "
        f"vigilia: {senza_bollettino}.",
        "",
        "Pioggia delle 24 ore UTC dal «Merging» (somma di otto CUM3), media sui pixel della "
        "zona e pixel peggiore. Colore: quello sulla mappa del bollettino, emesso il giorno "
        "prima e valido per il giorno. L'allerta parla di effetti al suolo (frane, piene, "
        "temporali), non di millimetri: la tabella affianca, non giudica.",
        "",
        "| colore | zone-giorno | media: 1° quartile | mediana | 3° quartile "
        "| punto peggiore: mediana |",
        "|---|---|---|---|---|---|",
    ]
    if not zg:
        return [*righe[:4], "Nessun giorno da confrontare.", ""]
    for livello, nome in _COLORI.items():
        mie = [r for r in zg if r.livello == livello]
        if not mie:
            righe.append(f"| {nome} | 0 | — | — | — | — |")
            continue
        q1, q2, q3 = _quartili([r.media for r in mie])
        picco = _quartili([r.massimo for r in mie])[1]
        righe.append(f"| {nome} | {len(mie)} | {q1:.1f} | {q2:.1f} | {q3:.1f} | {picco:.1f} |")
    senza = [r for r in zg if r.livello == 0]
    forti = [r for r in zg if r.livello >= 2]
    righe += [
        "",
        f"- zone senza allerta con più di {_TANTA_PIOGGIA_MM:.0f} mm nel punto peggiore: "
        f"{sum(r.massimo > _TANTA_PIOGGIA_MM for r in senza)} su {len(senza)} "
        f"({_quota(sum(r.massimo > _TANTA_PIOGGIA_MM for r in senza), len(senza))});",
        f"- zone arancioni o rosse con meno di {_POCA_PIOGGIA_MM:.0f} mm in media: "
        f"{sum(r.media < _POCA_PIOGGIA_MM for r in forti)} su {len(forti)} "
        f"({_quota(sum(r.media < _POCA_PIOGGIA_MM for r in forti), len(forti))}); "
        f"con meno di {_POCA_PIOGGIA_MM:.0f} mm anche nel punto peggiore: "
        f"{sum(r.massimo < _POCA_PIOGGIA_MM for r in forti)} "
        f"({_quota(sum(r.massimo < _POCA_PIOGGIA_MM for r in forti), len(forti))}).",
        "",
        "Per mese, mediana della pioggia media di zona (mm) e numero di zone-giorno:",
        "",
        "| mese | " + " | ".join(_COLORI.values()) + " |",
        "|---|" + "---|" * len(_COLORI),
    ]
    for mese in sorted({f"{r.giorno:%Y-%m}" for r in zg}):
        celle = []
        for livello in _COLORI:
            medie = [r.media for r in zg if r.livello == livello and f"{r.giorno:%Y-%m}" == mese]
            celle.append(f"{_quartili(medie)[1]:.1f} ({len(medie)})" if medie else "—")
        righe.append(f"| {mese} | " + " | ".join(celle) + " |")
    righe += [
        "",
        "La classe più alta data da Limen nella stessa zona è nella parte «Limen accanto al "
        "bollettino» (`LIMEN_RADAR_MISURE=limen`), che legge il database.",
        "",
    ]
    return righe


# ── Limen accanto al bollettino (#629) ───────────────────────────────────────

#: Il bollettino parla di frane, piene e temporali: i pericoli di Limen che gli corrispondono.
PERICOLI_BOLLETTINO = (HazardType.LANDSLIDE, HazardType.FLOOD)
_LIVELLO_PC = {"verde": 0, "gialla": 1, "arancione": 2, "rossa": 3}
assert set(_LIVELLO_PC.values()) == _COLORI.keys()


@dataclass(frozen=True, slots=True)
class ZonaPrevista:
    giorno: date
    zona: str
    bollettino: int
    #: Il livello più alto previsto da Limen nella zona, per pericolo, sulla scala del bollettino.
    limen: dict[HazardType, int]

    @property
    def massimo(self) -> int:
        return max(self.limen.values(), default=0)


def livello_pc(classi: list[str], mappa: PcAlertMapping) -> int:
    """Il colore più alto delle classi, come livello del bollettino (0 = nessuna allerta)."""
    return max((_LIVELLO_PC[mappa.for_level(c)] for c in classi), default=0)


class CelleDelleZone:
    """Le celle il cui centroide sta in ogni zona: si calcolano una volta per zona."""

    def __init__(self, celle: list[tuple[str, float, float]]) -> None:
        from shapely import STRtree, points

        self._id = [c[0] for c in celle]
        self._albero = STRtree(points([(c[1], c[2]) for c in celle]))
        self._celle: dict[tuple[Any, ...], list[str]] = {}

    def di(self, zona: Zone) -> list[str]:
        chiave = (zona.name, zona.geometry.bounds)
        if chiave not in self._celle:
            dentro = self._albero.query(zona.geometry, predicate="covers")
            self._celle[chiave] = [self._id[i] for i in dentro]
        return self._celle[chiave]


def zone_previste(
    zone: list[Zone],
    giorno: date,
    celle: CelleDelleZone,
    classi: dict[str, dict[HazardType, list[str]]],
    mappe: dict[HazardType, PcAlertMapping],
) -> list[ZonaPrevista]:
    """Le zone del giorno con il livello di Limen; una zona senza celle è fuori dalla griglia."""
    out: list[ZonaPrevista] = []
    for z in zone:
        if z.valid != giorno:
            continue
        mie = celle.di(z)
        if not mie:
            continue
        limen = {
            p: max((livello_pc(classi.get(c, {}).get(p, []), m) for c in mie), default=0)
            for p, m in mappe.items()
        }
        out.append(ZonaPrevista(giorno, z.name, z.level, limen))
    return out


def _concordanza(coppie: list[tuple[int, int]]) -> str:
    """Quota di coppie uguali, e di quelle in cui Limen sta sopra o sotto il bollettino."""
    n = len(coppie)
    uguali = sum(b == lim for b, lim in coppie)
    sopra = sum(lim > b for b, lim in coppie)
    return (
        f"concordano {uguali} su {n} ({_quota(uguali, n)}); Limen più alto in {sopra} "
        f"({_quota(sopra, n)}), più basso in {n - uguali - sopra} ({_quota(n - uguali - sopra, n)})"
    )


def righe_limen(zp: list[ZonaPrevista], non_valutati: int) -> list[str]:
    nomi = " e ".join(p.value for p in PERICOLI_BOLLETTINO)
    righe = [
        "## Limen accanto al bollettino (#629)",
        "",
        f"Giorni confrontati: **{len({r.giorno for r in zp})}**; zone-giorno: **{len(zp)}**. "
        f"Giorni senza bollettino della vigilia o senza una corsa previsionale riuscita "
        f"prima della sua emissione (non valutati, non calmi): {non_valutati}.",
        "",
        f"Per ogni zona e giorno, il colore più alto che Limen dava a una cella della zona "
        f"({nomi}), letto dalle corse previsionali per cella partite **prima** dell'emissione "
        "del bollettino e puntate su quel giorno: previsione contro previsione. La classe "
        "diventa colore con `pc_alert` dello YAML del pericolo; una cella sotto Moderato "
        "conta «nessuna». Il colore del bollettino è il più alto fra idrogeologico, idraulico "
        "e temporali; Limen non ha un pericolo «temporali». Nessun giudizio: le due scale "
        "dicono cose vicine, non uguali. Lo storico previsionale non tiene il flag "
        "`measured`: un pericolo degradato in una corsa riuscita (il tetto Open-Meteo del "
        "29/09/2026) qui si legge «nessuna», quindi «Limen più basso» può essere un dato "
        "mancato, non una previsione calma.",
        "",
    ]
    if not zp:
        return [*righe, "Nessun giorno da confrontare.", ""]
    righe += [
        "Zone-giorno per colore del bollettino (righe) e di Limen (colonne), "
        "frane e alluvioni insieme:",
        "",
        "| bollettino \\ Limen | " + " | ".join(_COLORI.values()) + " | totale |",
        "|---|" + "---|" * (len(_COLORI) + 1),
    ]
    for livello, nome in _COLORI.items():
        mie = [r for r in zp if r.bollettino == livello]
        conti = [sum(r.massimo == lim for r in mie) for lim in _COLORI]
        righe.append(f"| {nome} | " + " | ".join(map(str, conti)) + f" | {len(mie)} |")
    righe += [
        "",
        f"- frane e alluvioni insieme: {_concordanza([(r.bollettino, r.massimo) for r in zp])};",
    ]
    for p in PERICOLI_BOLLETTINO:
        coppie = [(r.bollettino, r.limen[p]) for r in zp if p in r.limen]
        righe.append(f"- solo {p.value}: {_concordanza(coppie)};")
    con_allerta = [r for r in zp if r.bollettino >= 1]
    righe += [
        f"- zone con allerta almeno gialla in cui Limen dava almeno gialla: "
        f"{sum(r.massimo >= 1 for r in con_allerta)} su {len(con_allerta)} "
        f"({_quota(sum(r.massimo >= 1 for r in con_allerta), len(con_allerta))}).",
        "",
    ]
    return righe


# ── qualità (#628) ───────────────────────────────────────────────────────────


def _lato() -> tuple[int, int]:
    ovest, sud, est, nord = _ITALIA
    return round((nord - sud) / _PASSO_BLOCCO), round((est - ovest) / _PASSO_BLOCCO)


def blocco_dei_pixel(griglia: RainGrid) -> NDArray[np.intp]:
    """Per ogni pixel (in ordine di riga) il suo blocco della mappa di qualità, ``-1`` se fuori."""
    from rasterio.warp import transform as riproietta

    righe, colonne = griglia.data.shape
    cc, rr = np.meshgrid(np.arange(colonne) + 0.5, np.arange(righe) + 0.5)
    xs, ys = griglia.transform * (cc.ravel(), rr.ravel())
    if griglia.crs.to_epsg() != 4326:
        lon, lat = riproietta(griglia.crs, "EPSG:4326", xs, ys)
        xs, ys = np.asarray(lon), np.asarray(lat)
    ovest, _, _, nord = _ITALIA
    n_righe, n_colonne = _lato()
    c = np.floor((xs - ovest) / _PASSO_BLOCCO).astype(np.intp)
    r = np.floor((nord - ys) / _PASSO_BLOCCO).astype(np.intp)
    fuori = (c < 0) | (c >= n_colonne) | (r < 0) | (r >= n_righe)
    out: NDArray[np.intp] = np.where(fuori, -1, r * n_colonne + c)
    return out


def media_per_blocco(valori: NDArray[np.float32], blocco: NDArray[np.intp]) -> NDArray[np.float64]:
    """La media dei pixel misurati di ogni blocco; ``NaN`` se è misurato per meno di metà."""
    n = int(np.prod(_lato()))
    piatti = valori.ravel()
    dentro = blocco >= 0
    misurati = dentro & np.isfinite(piatti)
    somme = np.bincount(blocco[misurati], weights=piatti[misurati], minlength=n)
    conti = np.bincount(blocco[misurati], minlength=n)
    tutti = np.bincount(blocco[dentro], minlength=n)
    buoni = (conti > 0) & (conti >= _QUOTA_MISURATA * tutti)
    out: NDArray[np.float64] = np.where(buoni, somme / np.maximum(conti, 1), np.nan)
    return out


def rapporto_del_giorno(
    radar: NDArray[np.float64], merging: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Solo radar diviso «Merging», dove il «Merging» dice che è piovuto; ``NaN`` altrove."""
    piovoso = np.isfinite(radar) & np.isfinite(merging) & (merging >= _GIORNO_PIOVOSO_MM)
    out: NDArray[np.float64] = np.where(piovoso, radar / np.where(piovoso, merging, 1.0), np.nan)
    return out


def mappa_di_qualita(
    rapporti: list[NDArray[np.float64]],
) -> tuple[NDArray[np.float64], NDArray[np.intp]]:
    """Mediana del rapporto e giorni piovosi per blocco; ``NaN`` sotto ``_GIORNI_MINIMI``."""
    pila = np.vstack(rapporti)
    giorni: NDArray[np.intp] = np.isfinite(pila).sum(axis=0)
    ordinati = np.sort(pila, axis=0)  # i NaN in fondo
    meta = (giorni - 1) // 2
    colonne = np.arange(pila.shape[1])
    mediana = (ordinati[meta, colonne] + ordinati[np.maximum(giorni // 2, 0), colonne]) / 2
    out: NDArray[np.float64] = np.where(giorni >= _GIORNI_MINIMI, mediana, np.nan)
    return out, giorni


def scrivi_mappa(percorso: Path, mediana: NDArray[np.float64], giorni: NDArray[np.intp]) -> None:
    import rasterio
    from rasterio.transform import from_origin

    n_righe, n_colonne = _lato()
    with rasterio.open(
        percorso,
        "w",
        driver="GTiff",
        height=n_righe,
        width=n_colonne,
        count=2,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(_ITALIA[0], _ITALIA[3], _PASSO_BLOCCO, _PASSO_BLOCCO),
        nodata=float("nan"),
        compress="deflate",
    ) as ds:
        ds.write(mediana.reshape(n_righe, n_colonne).astype("float32"), 1)
        ds.write(giorni.reshape(n_righe, n_colonne).astype("float32"), 2)
        ds.set_band_description(1, "mediana di SRT1/CUM sui giorni piovosi")
        ds.set_band_description(2, "giorni piovosi")


def _centro(blocco: int) -> tuple[float, float]:
    r, c = divmod(blocco, _lato()[1])
    return _ITALIA[0] + (c + 0.5) * _PASSO_BLOCCO, _ITALIA[3] - (r + 0.5) * _PASSO_BLOCCO


def righe_qualita(
    mediana: NDArray[np.float64], giorni: NDArray[np.intp], n_giorni: int, mappa: str | None
) -> list[str]:
    stimati = mediana[np.isfinite(mediana)]
    righe = [
        "## Quanto vede il solo radar, blocco per blocco (#628)",
        "",
        f"Giorni con tutte le SRT1 e le CUM3: **{n_giorni}**. Per blocco di {_PASSO_BLOCCO}° "
        f"(circa 10 km) e per giorno con almeno {_GIORNO_PIOVOSO_MM:.0f} mm nel «Merging»: "
        "somma delle 24 SRT1 divisa per la somma delle otto CUM3, tutte e due in media sul "
        f"blocco. La stima è la mediana sui giorni piovosi, dove sono almeno {_GIORNI_MINIMI}. "
        "Sotto 1 il radar da solo vede meno pioggia dei pluviometri, sopra 1 di più.",
        "",
    ]
    if stimati.size == 0:
        return [*righe, "Nessun blocco con abbastanza giorni piovosi.", ""]
    q1, q2, q3 = np.percentile(stimati, [25, 50, 75])
    righe += [
        f"- blocchi con una stima: **{stimati.size}** (giorni piovosi per blocco: mediana "
        f"{int(np.median(giorni[np.isfinite(mediana)]))});",
        f"- rapporto: mediana **{q2:.2f}**, quartili {q1:.2f} e {q3:.2f};",
        f"- blocchi sotto 0,5: {_quota(int((stimati < 0.5).sum()), stimati.size)}; "
        f"sopra 1,5: {_quota(int((stimati > 1.5).sum()), stimati.size)}.",
        "",
        "I dieci blocchi dove il radar vede meno:",
        "",
        "| lon | lat | rapporto | giorni piovosi |",
        "|---|---|---|---|",
    ]
    for b in np.argsort(np.where(np.isfinite(mediana), mediana, np.inf))[:10]:
        if np.isfinite(mediana[b]):
            lon, lat = _centro(int(b))
            righe.append(f"| {lon:.2f} | {lat:.2f} | {mediana[b]:.2f} | {int(giorni[b])} |")
    if mappa is not None:
        righe += ["", f"Mappa: `{mappa}` (banda 1 il rapporto, banda 2 i giorni piovosi)."]
    return [*righe, ""]


# ── ore (#626) ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Ora:
    stazione: int
    pluviometro: float
    radar: float
    ricostruita: float


def confronta_ore(
    misurate: dict[datetime, list[float | None]],
    radar: dict[datetime, list[float | None]],
    ricostruite: dict[datetime, list[float | None]],
) -> list[Ora]:
    """Le ore piovose in cui pluviometro, solo radar e ora ricostruita ci sono tutti e tre."""
    out: list[Ora] = []
    for ora, valori in misurate.items():
        if ora not in radar or ora not in ricostruite:
            continue
        for k, (g, s, r) in enumerate(zip(valori, radar[ora], ricostruite[ora], strict=True)):
            if g is None or s is None or r is None:
                continue
            if max(g, s, r) >= _ORA_PIOVOSA_MM:
                out.append(Ora(k, g, s, r))
    return out


def righe_ore(ore: list[Ora]) -> list[str]:
    righe = [
        "## L'ora ricostruita contro i pluviometri (#626)",
        "",
        f"Ore piovose (almeno {_ORA_PIOVOSA_MM:.0f} mm per una delle tre letture): "
        f"**{len(ore)}**, su **{len({o.stazione for o in ore})}** pluviometri di ARPA Lombardia "
        "(open data CC0, misure a 10 minuti sommate sull'ora). Il radar è letto sul "
        "pluviometro (mediana dei nove pixel intorno). Una parte di questi pluviometri è già "
        "dentro il «Merging»: l'ora ricostruita parte avvantaggiata, il confronto non è "
        "indipendente.",
        "",
    ]
    if not ore:
        return [*righe, "Nessuna ora da confrontare.", ""]
    forti = [o for o in ore if o.pluviometro >= _ORA_FORTE_MM]
    righe += [
        f"| lettura | errore medio (mm) | errore assoluto medio (mm) | ore ≥ {_ORA_FORTE_MM:.0f} "
        f"mm colte | ore ≥ {_ORA_FORTE_MM:.0f} mm che il pluviometro non ha |",
        "|---|---|---|---|---|",
    ]
    for nome, letti in (
        ("solo radar (SRT1)", [o.radar for o in ore]),
        ("ora ricostruita", [o.ricostruita for o in ore]),
    ):
        scarti = np.asarray(letti) - np.asarray([o.pluviometro for o in ore])
        colte = sum(
            x >= _ORA_FORTE_MM
            for x, o in zip(letti, ore, strict=True)
            if o.pluviometro >= _ORA_FORTE_MM
        )
        false = sum(
            x >= _ORA_FORTE_MM
            for x, o in zip(letti, ore, strict=True)
            if o.pluviometro < _ORA_FORTE_MM
        )
        righe.append(
            f"| {nome} | {scarti.mean():+.2f} | {np.abs(scarti).mean():.2f} "
            f"| {colte} su {len(forti)} | {false} |"
        )
    return [*righe, ""]


async def _ore(archivio: MergingArchive, giorni: list[date]) -> list[Ora]:
    """Tutte le ore dei ``giorni`` (con SRT1 e CUM3 completi) sui pluviometri lombardi."""
    if not giorni:
        return []
    stazioni = await pluviometri.pluviometri(_LOMBARDIA)
    punti = sorted({(p.lon, p.lat) for p in stazioni})
    if not punti:
        return []
    buoni = set(giorni)
    out: list[Ora] = []
    primo = giorni[0]
    while primo <= giorni[-1]:
        ultimo = min(primo + timedelta(days=_GIORNI_PER_RICHIESTA - 1), giorni[-1])
        start = datetime.combine(primo, time(0), UTC)
        end = datetime.combine(ultimo + timedelta(days=1), time(0), UTC)
        misurate = await pluviometri.oraria(
            punti, start, end, raggio_km=_RAGGIO_PLUVIOMETRO_KM, bbox=_LOMBARDIA
        )
        misurate = {h: v for h, v in misurate.items() if (h - timedelta(minutes=1)).date() in buoni}
        radar: dict[datetime, list[float | None]] = {}
        for h in misurate:
            fotogramma = archivio.leggi("SRT1", h)
            if fotogramma is not None:
                radar[h] = fotogramma.sample(punti)
        out += confronta_ore(misurate, radar, archivio.oraria(punti, start, end))
        primo = ultimo + timedelta(days=1)
    return out


# ── il report ────────────────────────────────────────────────────────────────


def righe_copertura(voci: list[Copertura], primo: datetime | None) -> list[str]:
    righe = ["## Che cosa c'è nell'archivio (#625)", ""]
    if not voci or primo is None:
        return [*righe, "L'archivio è vuoto.", ""]
    righe += [
        f"Primo fotogramma: **{primo:%d/%m/%Y %H:%M} UTC**. «Persi» sono quelli che il DPC non "
        "teneva più quando l'archivio li ha chiesti; il resto di quelli che mancano si "
        "ritenta a ogni giro.",
        "",
        "| prodotto | mese | attesi | presenti | persi | mancanti |",
        "|---|---|---|---|---|---|",
    ]
    righe += [
        f"| {v.prodotto} | {v.mese} | {v.attesi} | {v.presenti} | {v.persi} "
        f"| {v.attesi - v.presenti - v.persi} |"
        for v in voci
    ]
    return [*righe, ""]


def righe_richieste(voci: list[tuple[str, int, int]], *, aree: int, per_notte: int) -> list[str]:
    richieste, file = sum(v[1] for v in voci), sum(v[2] for v in voci)
    return [
        "## Quante richieste fa Limen al servizio radar (#627)",
        "",
        f"Contate dalla configurazione, per **{aree}** aree monitorate, in un giorno a regime. "
        "Le richieste vanno a `radar-api.protezionecivile.it`; i file si scaricano dal link "
        "che il servizio restituisce.",
        "",
        "| per che cosa | richieste al servizio | file |",
        "|---|---|---|",
        *(f"| {nome} | {r} | {f} |" for nome, r, f in voci),
        f"| **totale** | **{richieste}** | **{file}** |",
        "",
        f"In media una richiesta ogni {86400 // max(richieste, 1)} secondi. Il primo recupero "
        f"dell'archivio aggiunge al più {per_notte} file per notte "
        "(`RADAR_ARCHIVE__FILE_PER_NOTTE`), finché i mesi che il DPC tiene ancora non sono "
        "tutti sul disco.",
        "",
    ]


def _giorno(nome: str) -> date | None:
    testo = os.getenv(nome)
    return date.fromisoformat(testo) if testo else None


async def _bollettini(archivio: MergingArchive, giorni: list[date]) -> tuple[list[ZonaGiorno], int]:
    nomi = await bollettini.nomi()
    maschere = Maschere()
    out: list[ZonaGiorno] = []
    senza = 0
    for giorno in giorni:
        nome = bollettino_per(nomi, giorno)
        letto = await bollettini.scarica(nome) if nome is not None else None
        griglia = somma_del_giorno(archivio, "CUM3", giorno)
        if letto is None or griglia is None:
            senza += 1
            continue
        out += zone_del_giorno(griglia, letto.zones, giorno, maschere)
    return out, senza


async def _limen(giorni: list[date]) -> tuple[list[ZonaPrevista], int]:
    nomi = await bollettini.nomi()
    mappe: dict[HazardType, PcAlertMapping] = {
        p: load_hazard_thresholds(p).pc_alert for p in PERICOLI_BOLLETTINO
    }
    out: list[ZonaPrevista] = []
    non_valutati = 0
    async with lifespan_pool():
        celle = CelleDelleZone(await carico_repo.centroidi())
        for giorno in giorni:
            nome = bollettino_per(nomi, giorno)
            letto = await bollettini.scarica(nome) if nome is not None else None
            classi = (
                await carico_repo.classi_previste(giorno, letto.issued, list(PERICOLI_BOLLETTINO))
                if letto is not None
                else None
            )
            if letto is None or classi is None:
                non_valutati += 1
                continue
            out += zone_previste(letto.zones, giorno, celle, classi, mappe)
    return out, non_valutati


def _giorni_limen(dal: date | None, al: date | None) -> list[date]:
    fine = al or datetime.now(UTC).date() - timedelta(days=1)
    inizio = dal or fine - timedelta(days=_GIORNI_LIMEN - 1)
    return [inizio + timedelta(days=k) for k in range((fine - inizio).days + 1)]


def _qualita(
    archivio: MergingArchive, giorni: list[date]
) -> tuple[NDArray[np.float64], NDArray[np.intp], int] | None:
    blocchi: dict[tuple[Any, ...], NDArray[np.intp]] = {}

    def per_blocco(griglia: RainGrid) -> NDArray[np.float64]:
        chiave = (griglia.data.shape, tuple(griglia.transform))
        if chiave not in blocchi:
            blocchi[chiave] = blocco_dei_pixel(griglia)
        return media_per_blocco(griglia.data, blocchi[chiave])

    rapporti = []
    for giorno in giorni:
        radar = somma_del_giorno(archivio, "SRT1", giorno)
        merging = somma_del_giorno(archivio, "CUM3", giorno)
        if radar is not None and merging is not None:
            rapporti.append(rapporto_del_giorno(per_blocco(radar), per_blocco(merging)))
    if not rapporti:
        return None
    return (*mappa_di_qualita(rapporti), len(rapporti))


async def run() -> int:
    settings = get_settings()
    cfg = settings.radar_archive
    # «adozione» costa circa 300 richieste al DPC: solo quando la si chiede.
    predefinite = ",".join(m for m in MISURE if m != "adozione")
    misure = [m.strip() for m in os.getenv("LIMEN_RADAR_MISURE", predefinite).split(",")]
    if sconosciute := sorted(set(misure) - set(MISURE)):
        log.error("misura_radar.misura_sconosciuta", misure=sconosciute, note=list(MISURE))
        return 2
    if not cfg.attivo and set(misure) - _SENZA_ARCHIVIO:
        log.error("misura_radar.non_configurato", hint="RADAR_ARCHIVE__CARTELLA")
        return 1
    cartella = Path(cfg.cartella)
    dal, al = _giorno("LIMEN_RADAR_DAL"), _giorno("LIMEN_RADAR_AL")
    aree = int(os.getenv("LIMEN_RADAR_AREE", "20"))
    archivio = MergingArchive(cartella) if cfg.attivo else None
    con_cum = giorni_completi(cartella, "CUM3", dal, al) if cfg.attivo else []
    con_tutto = (
        sorted(set(con_cum) & set(giorni_completi(cartella, "SRT1", dal, al))) if cfg.attivo else []
    )
    giorni_limen = con_cum or _giorni_limen(dal, al)
    uscita = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    uscita.mkdir(parents=True, exist_ok=True)
    periodo = (
        f"{con_cum[0]}_{con_cum[-1]}"
        if con_cum
        else f"{giorni_limen[0]}_{giorni_limen[-1]}"
        if {"limen", "adozione"} & set(misure)
        else "vuoto"
    )
    report = uscita / f"misura_radar_{periodo}.md"

    righe = [
        "# L'archivio del «Merging»: copertura, richieste, bollettini, qualità, Limen, ore",
        "",
        (
            f"Giorni con tutte le CUM3: **{len(con_cum)}**"
            + (f" (dal {con_cum[0]:%d/%m/%Y} al {con_cum[-1]:%d/%m/%Y})" if con_cum else "")
            + f"; con anche tutte le SRT1: **{len(con_tutto)}**. "
            if archivio is not None
            else f"Senza l'archivio del «Merging»: giorni dal {giorni_limen[0]:%d/%m/%Y} al "
            f"{giorni_limen[-1]:%d/%m/%Y}. "
        )
        + "Dati © Dipartimento della Protezione Civile: radar e «Merging» CC BY-SA 4.0, "
        "bollettini CC BY 4.0.",
        "",
    ]
    try:
        if "copertura" in misure:
            noti = [t for p in PASSI for t in in_archivio(cartella, p)]
            righe += righe_copertura(copertura(cartella), min(noti, default=None))
        if "richieste" in misure:
            voci = richieste_al_giorno(
                aree=aree,
                sveglia_minuti=settings.nowcast.interval_minutes,
                giro_minuti=settings.scheduler.hourly_monitoring_minutes,
            )
            righe += righe_richieste(voci, aree=aree, per_notte=cfg.file_per_notte)
        if archivio is not None and "bollettini" in misure:
            righe += righe_bollettini(*await _bollettini(archivio, con_cum))
        if archivio is not None and "qualita" in misure:
            stima = _qualita(archivio, con_tutto)
            if stima is None:
                righe += righe_qualita(np.array([]), np.array([], dtype=np.intp), 0, None)
            else:
                mappa = report.with_suffix(".qualita.tif")
                scrivi_mappa(mappa, stima[0], stima[1])
                righe += righe_qualita(*stima, mappa.name)
        if "limen" in misure:
            righe += righe_limen(*await _limen(giorni_limen))
        if archivio is not None and "ore" in misure:
            righe += righe_ore(await _ore(archivio, con_tutto))
        if "adozione" in misure:
            async with lifespan_pool():
                misurato = await adozione.misura(
                    giorni_limen[0], giorni_limen[-1], settings.nowcast.min_intensity_mmh
                )
            righe += adozione.righe_adozione(*misurato, settings.nowcast.min_intensity_mmh)
    finally:
        await SharedHttpClient.aclose()

    provenienza.scrivi_report(report, "\n".join(righe))
    log.info(
        "misura_radar.done", giorni=len(con_cum), giorni_con_srt1=len(con_tutto), report=str(report)
    )
    return 0
