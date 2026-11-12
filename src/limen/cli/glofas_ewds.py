"""``limen glofas-ewds`` — la piena ordinaria di Open-Meteo contro la rianalisi EWDS (#448).

Scarica lo storico GloFAS 4 sull'Italia dall'Early Warning Data Store di
Copernicus sulla finestra dei riferimenti, ne prende per ogni nodo la cella
i cui valori Open-Meteo restituisce, e confronta il percentile con quello in
`glofas_riferimento`. Scrive un report, **non la tabella**: dal #448 la fonte
dei riferimenti è una sola, Open-Meteo (`glofas_repo.FONTE_RIFERIMENTO`),
perché la sua storia recente è la catena della previsione che sta al
numeratore, e la rianalisi in un nodo su dieci se ne discosta di oltre il 19 %.
Il comando resta per rifare quella misura.

    uv run --group copernicus limen glofas-ewds

* ``COPERNICUS__EWDS_KEY`` — la chiave EWDS (in ``.env``); la licenza
  CEMS-Floods va accettata una volta sul sito.
* ``LIMEN_EWDS_DIR`` — dove tenere i file mensili (obbligatoria). Rilanciando,
  i mesi già scaricati non si richiedono.
* ``LIMEN_REPORTS_DIR`` — dove finisce il report (default ``reports``).
"""

from __future__ import annotations

import asyncio
import math
import os
import statistics
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from limen.cli import provenienza
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.data.db import lifespan_pool
from limen.data.repos import glofas_repo
from limen.integrations.copernicus import ewds_glofas

log = get_logger(__name__)

#: Le classi di portata del confronto, in m³/s della piena ordinaria Open-Meteo.
_CLASSI = ((0.0, 1.0), (1.0, 10.0), (10.0, 100.0), (100.0, math.inf))
#: Una differenza «grande»: |log2(EWDS/OM)| > 0,25, cioè oltre ~19 %.
_SOGLIA_LOG2 = 0.25
_PEGGIORI = 15


def _riga(nome: str, rapporti: list[float]) -> str:
    if not rapporti:
        return f"| {nome} | 0 | | | | |"
    q = statistics.quantiles(rapporti, n=10) if len(rapporti) > 1 else [rapporti[0]] * 9
    grandi = sum(abs(math.log2(r)) > _SOGLIA_LOG2 for r in rapporti) / len(rapporti)
    return (
        f"| {nome} | {len(rapporti)} | {statistics.median(rapporti):.3f} "
        f"| {q[0]:.3f} | {q[-1]:.3f} | {grandi:.1%} |"
    )


def confronto(
    om: dict[glofas_repo.Nodo, float],
    ewds: dict[glofas_repo.Nodo, float | None],
    *,
    inizio: date,
    fine: date,
) -> str:
    """Il report: rapporto EWDS/OM per classe di portata e i nodi più lontani."""
    coppie = [(n, o, ewds.get(n)) for n, o in om.items()]
    ok = [(n, o, e) for n, o, e in coppie if e is not None and e > 0]
    righe = [
        "# Piena ordinaria GloFAS: Open-Meteo contro la rianalisi EWDS",
        "",
        f"Finestra {inizio.isoformat()} → {fine.isoformat()}. Nodi con un riferimento "
        f"Open-Meteo: {len(om)}; confrontabili: {len(ok)}; senza serie EWDS: "
        f"{len(coppie) - len(ok)}.",
        "",
        "| piena ordinaria OM (m³/s) | nodi | EWDS/OM mediana | p10 | p90 | oltre ±19 % |",
        "|---|---:|---:|---:|---:|---:|",
        _riga("tutti", [e / o for _, o, e in ok]),
    ]
    for lo, hi in _CLASSI:
        nome = f"{lo:g}-{hi:g}" if hi != math.inf else f"≥ {lo:g}"
        righe.append(_riga(nome, [e / o for _, o, e in ok if lo <= o < hi]))
    peggiori = sorted(ok, key=lambda t: -abs(math.log2(t[2] / t[1])))[:_PEGGIORI]
    righe += [
        "",
        "## I nodi più lontani",
        "",
        "| nodo (lon, lat) | OM | EWDS | EWDS/OM |",
        "|---|---:|---:|---:|",
        *(f"| {n[0]:.2f}, {n[1]:.2f} | {o:.2f} | {e:.2f} | {e / o:.2f} |" for n, o, e in peggiori),
    ]
    return "\n".join(righe) + "\n"


async def run() -> int:
    cartella = os.getenv("LIMEN_EWDS_DIR")
    if not cartella:
        log.error("cli.glofas_ewds.manca_cartella", hint="imposta LIMEN_EWDS_DIR")
        return 2
    cfg = get_settings().copernicus
    if cfg.ewds_key is None or not cfg.attivo:
        log.error("cli.glofas_ewds.manca_chiave", hint="imposta COPERNICUS__EWDS_KEY")
        return 2
    client = ewds_glofas.nuovo_client(cfg.ewds_url, cfg.ewds_key.get_secret_value())
    flood = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(flood, FloodThresholds)
    percentile = flood.fluvial.reference_percentile
    window_days = flood.fluvial.reference_window_days
    # La finestra del riempimento da Open-Meteo, chiusa dove l'EWDS ha già i
    # dati: per un percentile su due anni, quattro giorni non contano.
    fine = datetime.now(UTC).date() - timedelta(days=ewds_glofas.LATENZA_STORICO_GIORNI)
    inizio = fine - timedelta(days=window_days)

    async with lifespan_pool():
        om = await glofas_repo.salvati(
            percentile=percentile, window_days=window_days, fonte=glofas_repo.FONTE_RIFERIMENTO
        )
    if not om:
        log.info("cli.glofas_ewds.niente_da_confrontare")
        return 0
    nodi = list(om)
    # Ore di attesa in coda all'EWDS e qualche centinaio di MB da leggere.
    files = await asyncio.to_thread(
        ewds_glofas.scarica, Path(cartella), inizio, fine, client=client
    )
    serie = await asyncio.to_thread(
        ewds_glofas.serie_per_nodo, files, nodi, inizio=inizio, fine=fine
    )
    ewds = ewds_glofas.riferimenti(serie, percentile=percentile)

    uscita = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    uscita.mkdir(parents=True, exist_ok=True)
    report = uscita / f"glofas_riferimento_confronto_{fine.isoformat()}.md"
    provenienza.scrivi_report(report, confronto(om, ewds, inizio=inizio, fine=fine))
    log.info("cli.glofas_ewds.done", nodi=len(nodi), mesi=len(files), report=str(report))
    return 0
