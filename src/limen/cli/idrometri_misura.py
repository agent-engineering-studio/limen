"""``limen idrometri-misura`` — gli idrometri Arpae separano i giorni di piena? (#501)

Solo una misura, niente cambia nel motore. Prima di far entrare il livello
degli idrometri nel ramo fluviale serve sapere se, normalizzato sulla storia
di ogni stazione, distingue i giorni in cui l'acqua è uscita da quelli
qualunque, e su che scala: le soglie del ramo fluviale (``normal_ratio``,
``saturation_ratio`` in ``flood.yaml``) sono state derivate così per GloFAS,
con due percentili e nessun parametro libero, e la stessa tabella qui dice se
servono soglie proprie.

* **Rapporto** di una stazione in un giorno: il livello massimo sopra il fondo
  diviso la piena ordinaria sopra il fondo (:func:`idrometri.rapporti`), con
  il percentile e la finestra della piena ordinaria letti da ``flood.yaml``,
  gli stessi di GloFAS.
* **Giorno di piena** di una stazione: un poligono Copernicus EMS
  (``flood_events``) entro ``LIMEN_IDROMETRI_RAGGIO_KM`` (5) con data
  dell'evento a un giorno o meno. **Giorno qualunque**: a più di tre giorni da
  ogni giorno di piena della stazione.
* Due letture: il giorno stesso (il tetto: in esercizio il colmo del giorno
  si conosce a giorno finito) e il **giorno prima**, che è ciò che il sistema
  avrebbe avuto a mezzanotte.

Env: ``LIMEN_IDROMETRI_INIZIO`` / ``_FINE`` (date ISO, default maggio 2023),
``LIMEN_IDROMETRI_RAGGIO_KM``. I mesi Arpae restano su disco in
``$LIMEN_DATA_ROOT/archivio/arpae``. Il report va in ``LIMEN_REPORTS_DIR``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from limen.cli import provenienza
from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.data.db import acquire, lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.arpae import idrometri
from limen.integrations.arpae.idrometri import Stazione

log = get_logger(__name__)

_PERCENTILI = (0.10, 0.50, 0.75, 0.90, 0.99)
_SOGLIE = (1.0, 1.6, 2.0, 3.0)
_LONTANO_GIORNI = 3
#: Una stazione deve avere almeno un anno di storia prima della finestra.
_MINIMO_GIORNI = 365


@dataclass(frozen=True, slots=True)
class Campioni:
    piena: list[float]
    qualunque: list[float]


def campioni(
    rapporti: dict[str, dict[date, float]],
    giorni_di_piena: dict[str, set[date]],
    *,
    ritardo: int,
) -> Campioni:
    """I rapporti dei giorni di piena e dei giorni qualunque, letti ``ritardo`` giorni prima."""
    piena: list[float] = []
    qualunque: list[float] = []
    for chiave, serie in rapporti.items():
        piene = giorni_di_piena.get(chiave, set())
        for giorno in serie:
            valore = serie.get(giorno - timedelta(days=ritardo))
            if valore is None:
                continue
            if giorno in piene:
                piena.append(valore)
            elif all(abs((giorno - p).days) > _LONTANO_GIORNI for p in piene):
                qualunque.append(valore)
    return Campioni(piena=piena, qualunque=qualunque)


def _percentile(valori: list[float], p: float) -> float:
    ordinati = sorted(valori)
    return ordinati[min(len(ordinati) - 1, round(p * (len(ordinati) - 1)))]


def tabella(titolo: str, c: Campioni) -> list[str]:
    righe = [
        f"### {titolo}",
        "",
        "| | n | " + " | ".join(f"p{round(p * 100)}" for p in _PERCENTILI) + " |",
        "|---|---|" + "---|" * len(_PERCENTILI),
    ]
    for nome, valori in (("giorni di piena", c.piena), ("giorni qualunque", c.qualunque)):
        if not valori:
            righe.append(f"| {nome} | 0 |" + " — |" * len(_PERCENTILI))
            continue
        cifre = " | ".join(f"{_percentile(valori, p):.2f}" for p in _PERCENTILI)
        righe.append(f"| {nome} | {len(valori)} | {cifre} |")
    righe += ["", "| rapporto ≥ | giorni di piena sopra | giorni qualunque sopra | rapporto |"]
    righe.append("|---|---|---|---|")
    for s in _SOGLIE:
        colti = sum(v >= s for v in c.piena) / len(c.piena) if c.piena else 0.0
        base = sum(v >= s for v in c.qualunque) / len(c.qualunque) if c.qualunque else 0.0
        quanto = f"{colti / base:.1f}" if base else "—"
        righe.append(f"| {s:.1f} | {colti:.0%} | {base:.1%} | {quanto} |")
    return [*righe, ""]


async def _giorni_di_piena(
    stazioni: list[Stazione], *, inizio: date, fine: date, raggio_km: float
) -> dict[str, set[date]]:
    """Per stazione, i giorni con un poligono EMS vicino (a un giorno o meno).

    Una query per stazione: tutte insieme passano il tetto di 30 s del pool
    (13.000 poligoni nel solo maggio 2023), una alla volta ~0,2 s.
    """
    out: dict[str, set[date]] = {}
    async with acquire() as conn:
        for s in stazioni:
            giorni = await conn.fetch(
                """
                SELECT DISTINCT (f.event_time AT TIME ZONE 'UTC')::date AS giorno
                FROM flood_events f
                WHERE f.event_time >= $4 AND f.event_time < $5
                  -- Il riquadro prima, che usa l'indice; i metri dopo.
                  AND f.geom && ST_Expand(ST_SetSRID(ST_MakePoint($1, $2), 4326), $3 / 70000.0)
                  AND ST_DWithin(
                      f.geom::geography, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3
                  )
                """,
                s.lon,
                s.lat,
                raggio_km * 1000.0,
                inizio - timedelta(days=1),
                fine + timedelta(days=2),
            )
            for r in giorni:
                giorno: date = r["giorno"]
                out.setdefault(s.chiave, set()).update(
                    giorno + timedelta(days=k) for k in (-1, 0, 1)
                )
    return out


async def run() -> int:
    inizio = date.fromisoformat(os.getenv("LIMEN_IDROMETRI_INIZIO", "2023-05-01"))
    fine = date.fromisoformat(os.getenv("LIMEN_IDROMETRI_FINE", "2023-05-31"))
    raggio_km = float(os.getenv("LIMEN_IDROMETRI_RAGGIO_KM", "5"))
    soglie = load_hazard_thresholds(HazardType.FLOOD)
    if not isinstance(soglie, FloodThresholds):  # pragma: no cover - schema garantito
        raise TypeError("flood.yaml non è una configurazione alluvione")
    fluviale = soglie.fluvial
    storia_dal = inizio - timedelta(days=fluviale.reference_window_days)
    try:
        livelli, mancati = await idrometri.livelli(
            storia_dal, fine, cartella=radice_dati() / "archivio" / "arpae"
        )
    finally:
        await SharedHttpClient.aclose()
    rapporti = {
        chiave: r
        for chiave, giorni in livelli.massimi.items()
        if (
            r := idrometri.rapporti(
                giorni,
                prima_di=inizio,
                percentile=fluviale.reference_percentile,
                minimo_giorni=_MINIMO_GIORNI,
            )
        )
    }
    if not rapporti:
        log.error("idrometri_misura.nessuna_stazione", mesi_mancati=mancati)
        return 1
    stazioni = [livelli.stazioni[k] for k in rapporti]
    async with lifespan_pool():
        piene = await _giorni_di_piena(stazioni, inizio=inizio, fine=fine, raggio_km=raggio_km)

    testo = [
        f"# Idrometri Arpae contro gli allagamenti EMS, {inizio} → {fine}",
        "",
        f"Stazioni con storia sufficiente: **{len(rapporti)}** su {len(livelli.stazioni)}; "
        f"con almeno un giorno di piena entro {raggio_km:g} km: **{len(piene)}**. "
        f"Piena ordinaria: p{round(fluviale.reference_percentile * 100)} del livello massimo "
        f"giornaliero nei {fluviale.reference_window_days} giorni prima, sopra il fondo "
        f"(p{round(idrometri.PERCENTILE_FONDO * 100)}).",
        "",
        f"Mesi Arpae non letti: {', '.join(mancati) if mancati else 'nessuno'}. "
        f"Dati: {idrometri.LICENZA}. Verità: Copernicus EMS Rapid Mapping.",
        "",
        "Per confronto, GloFAS in `flood.yaml`: giorni qualunque p90 1,63, giorni di piena "
        "p10 1,66 e p50 6,39 (picco a 7 giorni sul q90 del nodo).",
        "",
        *tabella("Il giorno stesso (tetto)", campioni(rapporti, piene, ritardo=0)),
        *tabella(
            "Il giorno prima (ciò che c'è a mezzanotte)", campioni(rapporti, piene, ritardo=1)
        ),
    ]
    uscita = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    uscita.mkdir(parents=True, exist_ok=True)
    report = uscita / f"idrometri_er_{inizio}_{fine}.md"
    provenienza.scrivi_report(report, "\n".join(testo))
    log.info(
        "idrometri_misura.done",
        stazioni=len(rapporti),
        con_piena=len(piene),
        report=str(report),
    )
    return 0
