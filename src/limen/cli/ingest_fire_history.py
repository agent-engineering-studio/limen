"""``limen ingest-fire-history`` — archivio storico FIRMS 2000-2024 (#66).

Per gli incendi è quello che e-ITALICA è per le frane: detection datate al
giorno e geolocalizzate, venticinque anni di storia italiana. Serve a tre
cose — la feature statica `fire_density`, il truth set del backtest incendio,
e le etichette del futuro challenger ML.

**Nessuna credenziale.** La issue prevedeva il portale di download FIRMS, che
chiede un'utenza Earthdata e consegna lo zip via email. Non serve: gli
archivi per paese e anno sono CSV statici in chiaro (vedi
`integrations/firms/archive.py`). L'Italia intera, 2000-2024, pesa 35 MB.

Cosa fa, in ordine:

1. scarica gli anni mancanti (cache in `LIMEN_DATA_DIR/fires/firms/`, o un
   file locale con `LIMEN_FIRMS_CSV` per lavorare offline);
2. scrive in `fire_hotspots` — la stessa tabella dell'NRT, con `source`
   distinta e la stessa chiave naturale, quindi l'upsert è idempotente;
3. ricostruisce `fire_events`, una riga per cella-giorno;
4. riscrive `fire_density` su ogni AOI seminata;
5. confronta EFFIS e FIRMS su due stagioni estive e scrive il report.

Idempotenza forte: l'hash del contenuto va in `dataset_versions`, quindi un
secondo giro su un archivio non cambiato **salta tutte le scritture** (il
report viene comunque rigenerato, perché è un ricalcolo di secondi e non una
scrittura). Per forzare una re-ingestione — per esempio dopo un cambio di
schema che aggiunge una colonna alle detection — si cancella la riga:

    DELETE FROM dataset_versions WHERE source='nasa' AND dataset='firms_archive';

Env:

* ``LIMEN_FIRE_HISTORY_FROM`` / ``_TO`` — anni da ingerire (default: dal primo
  pubblicato di ogni prodotto all'anno scorso).
* ``LIMEN_FIRE_HISTORY_COUNTRY`` — paese dell'archivio (default ``Italy``).
* ``LIMEN_FIRMS_CSV`` — un CSV già scaricato, invece della rete.
* ``LIMEN_FIRE_HISTORY_CHECK_YEARS`` — stagioni del confronto EFFIS
  (default: le due più recenti con perimetri).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import fire_events_repo
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.data.repos.dataset_versions_repo import content_hash
from limen.data.repos.dataset_versions_repo import find as find_version
from limen.data.repos.dataset_versions_repo import record as record_version
from limen.data.repos.fire_repo import FireHotspot, count_hotspots, upsert_hotspots
from limen.integrations._http import SharedHttpClient
from limen.integrations.firms.archive import (
    ARCHIVE_PRODUCTS,
    DEFAULT_COUNTRY,
    ArchiveProduct,
    archive_years,
    fetch_archive_year,
)
from limen.integrations.firms.client import parse_hotspot_csv

log = get_logger(__name__)

SOURCE = "nasa"
DATASET = "firms_archive"
REPORTS_DIR = Path("reports")

#: Il bootstrap set-based su 312.000 celle esce dal timeout di default del
#: pool, come gli altri passi di `static_bootstrap`.
_STMT_TIMEOUT_S = 1800.0


def _year_bounds() -> tuple[int, int]:
    """Anni da ingerire. Il default si ferma all'anno scorso: l'archivio per
    paese dell'anno in corso non è ancora pubblicato, e quel tratto è coperto
    dal feed NRT (`limen firms-sync`)."""
    last_published = datetime.now(UTC).year - 1
    lo = int(os.getenv("LIMEN_FIRE_HISTORY_FROM", "0") or 0)
    hi = int(os.getenv("LIMEN_FIRE_HISTORY_TO", "0") or 0)
    return lo, hi or last_published


def _hotspots_hash(hotspots: list[FireHotspot]) -> str:
    """Hash sulla chiave naturale, indipendente dall'ordine di scarico."""
    canonical = sorted(
        json.dumps(
            [h.source, h.acq_date.isoformat(), h.acq_time, h.latitude, h.longitude],
            separators=(",", ":"),
        )
        for h in hotspots
    )
    return content_hash(canonical)


async def _from_local_csv() -> list[FireHotspot] | None:
    """Un CSV già scaricato, per un init riproducibile senza rete."""
    raw = os.getenv("LIMEN_FIRMS_CSV", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_file():
        log.error("fire_history.csv_missing", path=str(path))
        return []
    firms = get_settings().firms
    # `source` dal nome del file quando riconoscibile: un CSV d'archivio non
    # porta la colonna, e marcarlo NRT mescolerebbe due prodotti diversi
    # sotto la stessa etichetta.
    stem = path.stem.lower()
    product = next(
        (p for p in ARCHIVE_PRODUCTS if stem.startswith(p.slug)),
        ARCHIVE_PRODUCTS[0],
    )
    hotspots = parse_hotspot_csv(
        path.read_text(encoding="utf-8", errors="replace"),
        source=product.source,
        min_confidence=firms.min_confidence,
        min_confidence_pct=firms.min_confidence_pct,
        min_frp_mw=firms.min_frp_mw,
    )
    log.info(
        "fire_history.local_csv",
        path=str(path),
        source=product.source,
        hotspots=len(hotspots),
    )
    return hotspots


async def _download(
    products: tuple[ArchiveProduct, ...], *, lo: int, hi: int, country: str
) -> list[FireHotspot]:
    firms = get_settings().firms
    out: list[FireHotspot] = []
    for product in products:
        for year in archive_years(product, until_year=hi):
            if lo and year < lo:
                continue
            out.extend(
                await fetch_archive_year(
                    product=product,
                    year=year,
                    country=country,
                    min_confidence=firms.min_confidence,
                    min_confidence_pct=firms.min_confidence_pct,
                    min_frp_mw=firms.min_frp_mw,
                )
            )
    return out


async def _ingested_span() -> tuple[date, date] | None:
    """La finestra **davvero** in tabella, non quella richiesta.

    L'anno richiesto e quello ottenuto non coincidono: il default chiede fino
    all'anno scorso, ma l'archivio per paese pubblica con più ritardo. Il
    report deve dire cosa c'è, non cosa è stato chiesto.
    """
    from limen.data.db import acquire

    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT min(acq_date) AS lo, max(acq_date) AS hi FROM fire_hotspots "
            "WHERE detection_type IS NOT NULL"
        )
    if row is None or row["lo"] is None:
        return None
    return row["lo"], row["hi"]


def _write_report(
    *,
    hotspots: int,
    events: int,
    country: str,
    span: tuple[date, date] | None,
    agreement: list[tuple[int, dict[str, int]]],
    density: dict[str, int],
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"fire_history_{country.lower()}.md"
    window = f"{span[0]} - {span[1]}" if span else "vuota"
    lines = [
        f"# Storia del fuoco — {country}",
        "",
        f"Generato: {datetime.now(UTC).isoformat(timespec='seconds')}  ",
        f"Detection in tabella: **{window}**",
        "",
        "## Provenienza",
        "",
        "- Fonte: **NASA FIRMS**, archivi per paese e anno "
        "(`firms.modaps.eosdis.nasa.gov/data/country/`)",
        "- Credenziali richieste: **nessuna** — il portale di download chiede "
        "un'utenza Earthdata e consegna via email, gli archivi per paese sono "
        "CSV statici in chiaro",
        "- Prodotti: MODIS 1 km dal 2000, VIIRS S-NPP 375 m dal 2012. "
        "NOAA-20 e NOAA-21 non sono pubblicati come archivio per paese, "
        "nonostante siano nel feed NRT",
        f"- Detection ingerite: **{hotspots}**",
        f"- Eventi (cella-giorno) ricostruiti: **{events}**",
        "",
        "> **FIRMS è presence-only.** L'assenza di un evento non prova che "
        "non sia bruciato: nuvole, chioma e roghi sotto la soglia di "
        "rilevamento non compaiono. Chi usa `fire_events` come etichetta deve "
        "campionare le pseudo-assenze, non leggere lo zero come "
        '"qui non brucia".',
        "",
        "> **Solo incendi di vegetazione** (`type = 0` di FIRMS). Senza questo "
        "filtro la cella con la densità più alta d'Italia era l'ILVA di "
        "Taranto, con 3.308 giorni-incendio su ~4.700 giorni d'archivio: "
        "un'acciaieria è una detection ad alta confidenza e alta potenza "
        "radiativa, perché è davvero calda, e il filtro di qualità non la "
        "distingue da un rogo. Escluse anche le sorgenti vulcaniche (Etna) e "
        "quelle offshore. Con il filtro il massimo scende a 184 giorni.",
        "",
        "> **La vegetazione include le stoppie.** I massimi residui in "
        "Lombardia e Piemonte sono bruciature di residui colturali: sono "
        "incendi di vegetazione veri e inneschi reali, ma non incendi "
        "boschivi. Chi usa `fire_density` come predisposizione al fuoco "
        "boschivo lo sappia — la pianura padana comparirà in alto. Non è "
        "filtrato di proposito: distinguerli richiederebbe la copertura del "
        "suolo, non un'euristica sui conteggi.",
        "",
    ]
    if agreement:
        lines += [
            "## Controllo di sanità: EFFIS contro FIRMS",
            "",
            "I due dataset sono indipendenti, quindi il loro accordo è la "
            "prova migliore che l'ingest funzioni. Un accordo parziale non "
            "significa che uno dei due sbagli: EFFIS mappa i perimetri sopra "
            "una soglia di area, FIRMS vede anche i roghi piccoli ma perde "
            "quelli sotto le nuvole.",
            "",
            "| Stagione | Perimetri EFFIS | Con hotspot entro 1 km / ±2 g | Accordo |",
            "|---|---:|---:|---:|",
        ]
        for year, row in agreement:
            total = row["perimeters"]
            share = f"{row['matched'] / total:.0%}" if total else "-"
            lines.append(f"| {year} | {total} | {row['matched']} | {share} |")
        lines.append("")
        if len(agreement) < 2:
            lines += [
                "Una sola stagione confrontabile: l'archivio FIRMS per paese "
                "si ferma all'anno scorso, quindi le stagioni EFFIS più "
                "recenti non hanno hotspot d'archivio con cui confrontarsi. "
                "Per coprirle serve il feed NRT (`limen firms-sync`, richiede "
                "`FIRMS__MAP_KEY`).",
                "",
            ]
    if density:
        lines += [
            "## Densità storica per AOI",
            "",
            "| AOI | Celle con almeno un incendio |",
            "|---|---:|",
        ]
        for aoi_id, touched in sorted(density.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{aoi_id}` | {touched} |")
        lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


async def _agreement_seasons() -> list[int]:
    """Le stagioni su cui confrontare EFFIS e FIRMS.

    Le più recenti coperte da **entrambi**, non le più recenti di EFFIS. Il
    primo giro prendeva 2026 e 2025 — gli anni con più perimetri — e misurava
    un accordo dello 0% su 106 perimetri, perché l'archivio FIRMS per paese si
    ferma al 2024: sovrapposizione zero per costruzione. Un accordo nullo fra
    due dataset indipendenti sullo stesso paese non è un accordo parziale, è
    un errore di chi confronta.
    """
    raw = os.getenv("LIMEN_FIRE_HISTORY_CHECK_YEARS", "").strip()
    if raw:
        return [int(part) for part in raw.split(",") if part.strip()]
    from limen.data.db import acquire

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT y FROM (
                SELECT DISTINCT extract(year FROM fire_date)::int AS y
                FROM fire_perimeters WHERE fire_date IS NOT NULL
            ) effis
            WHERE EXISTS (
                SELECT 1 FROM fire_hotspots h
                WHERE extract(year FROM h.acq_date)::int = effis.y
            )
            ORDER BY y DESC
            LIMIT 2
            """
        )
    return [int(r["y"]) for r in rows]


async def _density_counts() -> dict[str, int]:
    """Celle con almeno un giorno-incendio, per AOI. Solo lettura."""
    from limen.data.db import acquire

    out: dict[str, int] = {}
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.aoi_id, count(*)::int AS touched
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE c.fire_density > 0
            GROUP BY g.aoi_id
            """
        )
    for row in rows:
        out[str(row["aoi_id"])] = int(row["touched"])
    return out


async def _agreement() -> list[tuple[int, dict[str, int]]]:
    return [
        (
            year,
            await fire_events_repo.effis_firms_agreement(
                start=date(year, 1, 1), end=date(year, 12, 31)
            ),
        )
        for year in await _agreement_seasons()
    ]


async def run() -> int:
    country = os.getenv("LIMEN_FIRE_HISTORY_COUNTRY", DEFAULT_COUNTRY)
    lo, hi = _year_bounds()

    try:
        local = await _from_local_csv()
        hotspots = (
            local
            if local is not None
            else await _download(ARCHIVE_PRODUCTS, lo=lo, hi=hi, country=country)
        )
    finally:
        await SharedHttpClient.aclose()

    if not hotspots:
        log.warning("fire_history.empty", country=country, years=[lo, hi])
        return 1

    async with lifespan_pool():
        await run_migrations()
        version = _hotspots_hash(hotspots)
        existing = await find_version(SOURCE, DATASET, version)
        if existing is not None:
            # Il gate di versione protegge le **scritture** — l'upsert delle
            # detection, la ricostruzione degli eventi, la densità per cella —
            # non la generazione del report, che è un ricalcolo di secondi su
            # dati già in tabella. Saltare anche quello significherebbe che
            # chi rilancia il comando dopo aver corretto il confronto si tiene
            # il report vecchio, ed è esattamente il caso in cui l'ho scritto.
            log.info(
                "fire_history.skip",
                reason="content unchanged",
                version=version,
                version_id=existing.id,
                fetched=len(hotspots),
            )
            report = _write_report(
                hotspots=0,
                events=await fire_events_repo.count_events(),
                country=country,
                span=await _ingested_span(),
                agreement=await _agreement(),
                density=await _density_counts(),
            )
            log.info("fire_history.report", report=str(report), rebuilt=False)
            return 0

        version_id = await record_version(
            source=SOURCE,
            dataset=DATASET,
            version=version,
            metadata={
                "country": country,
                "year_from": lo or None,
                "year_to": hi,
                "products": [p.source for p in ARCHIVE_PRODUCTS],
                "hotspot_count": len(hotspots),
            },
        )
        written = await upsert_hotspots(hotspots, dataset_version_id=version_id)
        total = await count_hotspots()

        days = [h.acq_date for h in hotspots]
        events = await fire_events_repo.rebuild_events(
            start=min(days), end=max(days), timeout=_STMT_TIMEOUT_S
        )

        for aoi_id in await list_aoi_ids():
            await fire_events_repo.refresh_density(aoi_id, timeout=_STMT_TIMEOUT_S)

        report = _write_report(
            hotspots=written,
            events=events,
            country=country,
            span=await _ingested_span(),
            agreement=await _agreement(),
            density=await _density_counts(),
        )

    log.info(
        "fire_history.done",
        hotspots=written,
        total_in_db=total,
        events=events,
        report=str(report),
    )
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
