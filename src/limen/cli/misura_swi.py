"""``limen misura-swi`` — l'SWI 1 km Copernicus aggiunge qualcosa alle frane? (#507)

Solo una misura: niente cambia nel motore. Ripete il protocollo con cui la
#282 ha scartato l'umidità EDO, sul dato più fine e più fresco di Copernicus
Land, con la stessa domanda: **letto come in esercizio**, separa i giorni di
frana dagli altri giorni nello stesso punto, e aggiunge qualcosa a pioggia e
umidità Open-Meteo?

* **Campione**: frane datate ``P0``/``P1`` dal 2015 (l'SWI parte da lì) al
  2024, ITALICA e FraneItalia (``landslide_events``), una per punto e giorno;
  ``LIMEN_SWI_EVENTI`` (1500) estratte a caso con seme fisso.
* **Controlli appaiati**: lo stesso punto, ``_CONTROLLI`` giorni fra 4 e 30
  prima o dopo, lontani almeno tre giorni da ogni frana vicina.
* **Latenza vera**: l'SWI con etichetta ``D`` è pubblicato circa un giorno e
  mezzo dopo (misurato il 12/11/2026 sul catalogo CDSE), quindi per il giorno
  ``D`` in esercizio c'è il file di ``D-2``. Il file di ``D`` è riportato
  accanto come tetto, perché contiene la pioggia dell'evento: la lezione EDO
  è che il tetto non si confonde con la skill.
* **Base**: pioggia dei tre giorni ``D-2..D`` (quella che il motore vede con
  la previsione), pioggia dei trenta giorni prima e umidità 0-7 cm a
  mezzanotte, dall'archivio Open-Meteo (``LIMEN_SWI_ARCHIVIO_URL``, default
  quello configurato).
* **Lettura**: AUC appaiata di ogni grandezza (la frazione di coppie in cui
  il giorno di frana supera il suo controllo), e il guadagno di AUC
  aggiungendo l'SWI a una logistica sulla base, validata lasciando fuori una
  regione alla volta. GO solo se aggiunge in modo stabile.

Env: ``LIMEN_SWI_EVENTI``, ``LIMEN_SWI_T`` (tempo caratteristico, ``020``),
``LIMEN_SWI_ARCHIVIO_URL``; chiavi ``COPERNICUS__CDSE_S3_*``. Report in
``LIMEN_REPORTS_DIR``.
"""

from __future__ import annotations

import asyncio
import math
import os
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

from limen.cli import provenienza
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.integrations.copernicus_land import swi as swi_client
from limen.integrations.openmeteo.client import archive_url

log = get_logger(__name__)

_SEME = 507
_CONTROLLI = 4
_SCARTI = [d for d in range(-30, 31) if abs(d) >= 4]
_LATENZA_GIORNI = 2
_MINIMO_REGIONE = 30
_PRIMO_GIORNO = date(2015, 1, 15)
_ULTIMO_GIORNO = date(2024, 12, 31)


@dataclass(slots=True)
class Campione:
    evento: int
    frana: bool
    lon: float
    lat: float
    giorno: date
    regione: str
    x: dict[str, float | None] = field(default_factory=dict)


def _cella(lon: float, lat: float) -> tuple[int, int]:
    return round(lon * 100), round(lat * 100)


def controlli(
    eventi: list[tuple[float, float, date]],
    tutti: dict[tuple[int, int], list[date]],
    *,
    rng: random.Random,
) -> list[list[date]]:
    """Per ogni evento, fino a ``_CONTROLLI`` giorni nello stesso punto lontani da ogni frana.

    «Vicina» è una frana nella stessa cella da 0,01° o in una confinante
    (~1 km), entro tre giorni: un controllo che cade su un'altra frana non è
    un giorno senza frana.
    """
    out: list[list[date]] = []
    for lon, lat, giorno in eventi:
        cx, cy = _cella(lon, lat)
        vicine = [
            g for dx in (-1, 0, 1) for dy in (-1, 0, 1) for g in tutti.get((cx + dx, cy + dy), ())
        ]
        candidati = [
            giorno + timedelta(days=s)
            for s in _SCARTI
            if all(abs((giorno + timedelta(days=s) - v).days) > 3 for v in vicine)
        ]
        out.append(sorted(rng.sample(candidati, min(_CONTROLLI, len(candidati)))))
    return out


def auc_appaiata(campioni: list[Campione], chiave: str) -> tuple[float | None, int]:
    """Frazione di coppie (frana, suo controllo) in cui la frana supera il controllo."""
    per_evento: dict[int, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for c in campioni:
        v = c.x.get(chiave)
        if v is not None:
            per_evento[c.evento][0 if c.frana else 1].append(v)
    punti = 0.0
    coppie = 0
    for frane, ctrl in per_evento.values():
        for f in frane:
            for k in ctrl:
                punti += 1.0 if f > k else 0.5 if f == k else 0.0
                coppie += 1
    return (punti / coppie if coppie else None), coppie


def auc(punteggi: NDArray[np.float64], etichette: NDArray[np.bool_]) -> float:
    """AUC di Mann-Whitney, con i pari merito a metà."""
    ordine = np.argsort(punteggi, kind="mergesort")
    ranghi = np.empty(len(punteggi))
    ordinati = punteggi[ordine]
    i = 0
    while i < len(ordinati):
        j = i
        while j + 1 < len(ordinati) and ordinati[j + 1] == ordinati[i]:
            j += 1
        ranghi[ordine[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    pos = int(etichette.sum())
    neg = len(etichette) - pos
    if pos == 0 or neg == 0:
        return math.nan
    return float((ranghi[etichette].sum() - pos * (pos + 1) / 2.0) / (pos * neg))


def logistica(
    x: NDArray[np.float64], y: NDArray[np.float64], *, l2: float = 1e-3
) -> NDArray[np.float64]:
    """Coefficienti (intercetta in testa) di una logistica con IRLS e un filo di L2."""
    xb = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(xb.shape[1])
    for _ in range(50):
        p = 1.0 / (1.0 + np.exp(-(xb @ beta)))
        w = p * (1.0 - p)
        h = xb.T @ (xb * w[:, None]) + l2 * np.eye(xb.shape[1])
        passo = np.linalg.solve(h, xb.T @ (y - p) - l2 * beta)
        beta = beta + passo
        if float(np.abs(passo).max()) < 1e-8:
            break
    return beta


def fuori_regione(
    campioni: list[Campione], base: list[str], extra: str
) -> tuple[dict[str, tuple[float, float, int]], float, float]:
    """AUC lasciando fuori una regione alla volta: senza e con ``extra``.

    Restituisce per regione ``(auc_base, auc_con, n)`` e le due AUC sui
    punteggi fuori campione messi insieme.
    """
    righe = [c for c in campioni if all(c.x.get(k) is not None for k in [*base, extra])]
    conti: dict[str, int] = defaultdict(int)
    for c in righe:
        conti[c.regione] += c.frana
    regioni = sorted(r for r, n in conti.items() if n >= _MINIMO_REGIONE)
    righe = [c for c in righe if c.regione in regioni]
    if len(regioni) < 2:
        return {}, math.nan, math.nan

    def matrice(chiavi: list[str]) -> NDArray[np.float64]:
        return np.array([[float(c.x[k] or 0.0) for k in chiavi] for c in righe])

    y = np.array([1.0 if c.frana else 0.0 for c in righe])
    reg = np.array([c.regione for c in righe])
    out: dict[str, tuple[float, float, int]] = {}
    tutti_base = np.zeros(len(righe))
    tutti_con = np.zeros(len(righe))
    for chiavi, dest in ((base, tutti_base), ([*base, extra], tutti_con)):
        x = matrice(chiavi)
        for r in regioni:
            prova = reg == r
            media = x[~prova].mean(axis=0)
            scarto = x[~prova].std(axis=0)
            scarto[scarto == 0] = 1.0
            beta = logistica((x[~prova] - media) / scarto, y[~prova])
            xp = (x[prova] - media) / scarto
            dest[prova] = np.column_stack([np.ones(len(xp)), xp]) @ beta
    etichette = y.astype(bool)
    for r in regioni:
        prova = reg == r
        out[r] = (
            auc(tutti_base[prova], etichette[prova]),
            auc(tutti_con[prova], etichette[prova]),
            int(etichette[prova].sum()),
        )
    return out, auc(tutti_base, etichette), auc(tutti_con, etichette)


async def _eventi() -> list[tuple[float, float, date, str]]:
    async with acquire() as conn:
        righe = await conn.fetch(
            """
            SELECT DISTINCT ON (round(ST_X(e.geom)::numeric, 2), round(ST_Y(e.geom)::numeric, 2),
                                (e.event_time AT TIME ZONE 'Europe/Rome')::date)
                   ST_X(e.geom) AS lon, ST_Y(e.geom) AS lat,
                   (e.event_time AT TIME ZONE 'Europe/Rome')::date AS giorno, a.id AS regione
            FROM landslide_events e
            JOIN aoi a ON a.kind = 'region' AND ST_Contains(a.geom, e.geom)
            WHERE e.geographic_accuracy IN ('P0', 'P1')
              AND e.event_time >= $1 AND e.event_time < $2
            """,
            datetime.combine(_PRIMO_GIORNO, datetime.min.time()),
            datetime.combine(_ULTIMO_GIORNO + timedelta(days=1), datetime.min.time()),
        )
    return [(float(r["lon"]), float(r["lat"]), r["giorno"], r["regione"]) for r in righe]


async def _meteo(lon: float, lat: float, dal: date, al: date, url: str) -> dict[str, Any]:
    resp = await fetch_with_retry(
        "GET",
        url,
        client=await SharedHttpClient.get(),
        params={
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "start_date": dal.isoformat(),
            "end_date": al.isoformat(),
            "daily": "precipitation_sum",
            "hourly": "soil_moisture_0_to_7cm",
            "timezone": "Europe/Rome",
        },
    )
    resp.raise_for_status()
    dati: dict[str, Any] = resp.json()
    return dati


def base_meteo(dati: dict[str, Any], giorno: date) -> dict[str, float | None]:
    """Pioggia D-2..D, pioggia dei trenta giorni prima, umidità a mezzanotte di D."""
    giornaliero = dati.get("daily") or {}
    pioggia = {
        date.fromisoformat(t): v
        for t, v in zip(
            giornaliero.get("time") or [], giornaliero.get("precipitation_sum") or [], strict=False
        )
        if v is not None
    }
    orario = dati.get("hourly") or {}
    suolo = {
        t: v
        for t, v in zip(
            orario.get("time") or [], orario.get("soil_moisture_0_to_7cm") or [], strict=False
        )
        if v is not None
    }

    def somma(da: int, a: int) -> float | None:
        giorni = [giorno - timedelta(days=k) for k in range(da, a + 1)]
        if any(g not in pioggia for g in giorni):
            return None
        return float(sum(pioggia[g] for g in giorni))

    tre = somma(0, 2)
    trenta = somma(3, 32)
    umido = suolo.get(f"{giorno.isoformat()}T00:00")
    return {
        "pioggia_3g": math.log1p(tre) if tre is not None else None,
        "pioggia_30g": math.log1p(trenta) if trenta is not None else None,
        "suolo_om": float(umido) if umido is not None else None,
    }


async def run() -> int:
    cfg = get_settings().copernicus
    if cfg.cdse_s3_access_key is None or cfg.cdse_s3_secret_key is None:
        log.error("misura_swi.senza_chiavi", hint="COPERNICUS__CDSE_S3_ACCESS_KEY / _SECRET_KEY")
        return 1
    chiavi = swi_client.Chiavi(
        accesso=cfg.cdse_s3_access_key.get_secret_value(),
        segreto=cfg.cdse_s3_secret_key.get_secret_value(),
    )
    quanti = int(os.getenv("LIMEN_SWI_EVENTI", "1500"))
    t = os.getenv("LIMEN_SWI_T", "020")
    url = os.getenv("LIMEN_SWI_ARCHIVIO_URL") or archive_url()
    rng = random.Random(_SEME)

    async with lifespan_pool():
        tutti = await _eventi()
    per_cella: dict[tuple[int, int], list[date]] = defaultdict(list)
    for lon, lat, giorno, _ in tutti:
        per_cella[_cella(lon, lat)].append(giorno)
    scelti = rng.sample(tutti, min(quanti, len(tutti)))
    ctrl = controlli([(lo, la, g) for lo, la, g, _ in scelti], per_cella, rng=rng)

    campioni: list[Campione] = []
    for i, ((lon, lat, giorno, regione), giorni_ctrl) in enumerate(zip(scelti, ctrl, strict=True)):
        campioni.append(Campione(i, True, lon, lat, giorno, regione))
        campioni += [Campione(i, False, lon, lat, g, regione) for g in giorni_ctrl]

    limite = asyncio.Semaphore(8)

    async def meteo_evento(i: int) -> None:
        mio = [c for c in campioni if c.evento == i]
        dal = min(c.giorno for c in mio) - timedelta(days=33)
        al = max(c.giorno for c in mio)
        async with limite:
            try:
                dati = await _meteo(mio[0].lon, mio[0].lat, dal, al, url)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning(
                    "integration.degraded", source="openmeteo_archive", error=str(exc)[:200]
                )
                dati = {}
        for c in mio:
            c.x.update(base_meteo(dati, c.giorno))

    try:
        await asyncio.gather(*(meteo_evento(i) for i in range(len(scelti))))
        for chiave, scarto in (("swi_esercizio", _LATENZA_GIORNI), ("swi_tetto", 0)):
            punti: dict[date, list[tuple[float, float]]] = defaultdict(list)
            dove: dict[date, list[Campione]] = defaultdict(list)
            for c in campioni:
                g = c.giorno - timedelta(days=scarto)
                punti[g].append((c.lon, c.lat))
                dove[g].append(c)
            letti = await swi_client.swi(punti, t=t, chiavi=chiavi)
            for g, valori in letti.items():
                for c, v in zip(dove[g], valori, strict=True):
                    c.x[chiave] = v
    finally:
        await SharedHttpClient.aclose()

    report = scrivi(campioni, t=t, eventi_totali=len(tutti))
    log.info("misura_swi.done", eventi=len(scelti), campioni=len(campioni), report=str(report))
    return 0


def scrivi(campioni: list[Campione], *, t: str, eventi_totali: int) -> Path:
    frane = [c for c in campioni if c.frana]
    righe = [
        f"# SWI {t} Copernicus Land contro le frane, protocollo #282",
        "",
        f"Frane P0/P1 {_PRIMO_GIORNO.year}-{_ULTIMO_GIORNO.year} nel catalogo (una per punto e "
        f"giorno): {eventi_totali}; nel campione: **{len(frane)}**, con "
        f"{len(campioni) - len(frane)} controlli appaiati (stesso punto, 4-30 giorni, "
        "lontani da altre frane).",
        "",
        f"SWI in esercizio = file del giorno D-{_LATENZA_GIORNI} (latenza ~1,5 giorni); "
        "tetto = file del giorno D, che contiene già la pioggia dell'evento e in esercizio "
        f"non c'è. Fonte: {swi_client.ATTRIBUZIONE}.",
        "",
        "## AUC appaiata (0,5 = caso)",
        "",
        "| grandezza | AUC appaiata | coppie | frane con valore |",
        "|---|---|---|---|",
    ]
    for chiave in ("swi_esercizio", "swi_tetto", "suolo_om", "pioggia_3g", "pioggia_30g"):
        valore, coppie = auc_appaiata(campioni, chiave)
        con = sum(c.x.get(chiave) is not None for c in frane)
        righe.append(
            f"| {chiave} | {'—' if valore is None else f'{valore:.3f}'} | {coppie} | {con} |"
        )
    base = ["pioggia_3g", "pioggia_30g", "suolo_om"]
    per_regione, tot_base, tot_con = fuori_regione(campioni, base, "swi_esercizio")
    righe += [
        "",
        "## Guadagno aggiungendo l'SWI in esercizio, una regione fuori alla volta",
        "",
        f"Logistica su {', '.join(base)}; con e senza `swi_esercizio`. Solo i campioni con "
        f"tutte le grandezze e le regioni con almeno {_MINIMO_REGIONE} frane.",
        "",
        f"Tutte le regioni insieme (fuori campione): **{tot_base:.3f} → {tot_con:.3f}** "
        f"({tot_con - tot_base:+.3f}).",
        "",
        "| regione | frane | AUC base | AUC con SWI | Δ |",
        "|---|---|---|---|---|",
    ]
    for r, (a, b, n) in per_regione.items():
        righe.append(f"| {r} | {n} | {a:.3f} | {b:.3f} | {b - a:+.3f} |")
    migliori = sum(b > a for a, b, _ in per_regione.values())
    righe += ["", f"Regioni in cui l'SWI migliora: {migliori} su {len(per_regione)}.", ""]
    uscita = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    uscita.mkdir(parents=True, exist_ok=True)
    report = uscita / f"misura_swi_{t}_{date.today().isoformat()}.md"
    return provenienza.scrivi_report(report, "\n".join(righe))
