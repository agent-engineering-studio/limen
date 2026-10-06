"""Studio: un FWI «alto» vale lo stesso a ottobre e ad agosto?

Rigioca la catena FWI su un campione di nodi per 2016-2024 (ERA5 dalla
nostra istanza) e conta, per mese e classe FWI, i giorni-nodo e quelli con
almeno un fuoco FIRMS nelle celle del nodo. Due verità: tutti i fuochi, e
solo quelli su vegetazione naturale (CORINE 31x-32x), per togliere le
bruciature agricole che d'autunno gonfiano il conto.

Uso (l'archivio della nostra istanza, dall'host):

    OPENMETEO__ARCHIVE_URL=http://127.0.0.1:8085/v1/archive \
        uv run python scripts/spike_incendio_stagione.py 300 > studio.json

Risultato del 6 ottobre 2026 (300 nodi, 2016-2024, fuochi su vegetazione
naturale). Probabilità che il nodo abbia un fuoco in un giorno di classe:

    mese        alto    molto alto   giorni alto+ sul totale
    lug-ago     1,18 %  3,49 %       38 %
    settembre   0,78 %  1,66 %       21 %
    ottobre     0,97 %  1,92 %        7 %
    novembre    0,81 %  0,85 %        2 %

Un giorno «alto» di ottobre è quasi pericoloso come uno d'estate, e la
classe discrimina di più (lift 4,8 contro 2,2 ad agosto). Ottobre brucia
poco perché ha pochi giorni alti, non perché «alto» valga meno: le classi
assolute restano, e nessuna correzione stagionale va nel motore.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from limen.cli.fwi_backfill import _observations, params_from
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.core.scoring.wildfire.fwi import advance
from limen.data.db import acquire, lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import MeteoSnapshot

N_NODI = int(sys.argv[1]) if len(sys.argv) > 1 else 200
ANNI = range(2016, 2025)
AVVIAMENTO = 60
SOGLIE = (6.0, 12.0, 21.0, 38.0)  # nessuno | basso | moderato | alto | molto alto
CLASSI = ("nessuno", "basso", "moderato", "alto", "molto_alto")


def classe(fwi: float) -> str:
    for i, s in enumerate(SOGLIE):
        if fwi < s:
            return CLASSI[i]
    return CLASSI[-1]


def snap(v: float, passo: float) -> float:
    return round(round(v / passo) * passo, 4)


async def main() -> None:
    soglie = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(soglie, WildfireThresholds)
    params = params_from(soglie)
    passo = soglie.fwi.node_spacing_deg
    async with lifespan_pool():
        async with acquire() as conn:
            tutti = [
                (float(r[0]), float(r[1]))
                for r in await conn.fetch(
                    "SELECT DISTINCT node_lon, node_lat FROM fwi_climatology ORDER BY 1, 2"
                )
            ]
            fuochi = await conn.fetch(
                """
                SELECT fe.event_date,
                       ST_X(ST_Centroid(g.geom)) AS lon, ST_Y(ST_Centroid(g.geom)) AS lat,
                       COALESCE(csf.landuse_code, '') AS lu
                FROM fire_events fe
                JOIN grid_cells g ON g.id = fe.cell_id
                LEFT JOIN cell_static_factors csf ON csf.cell_id = fe.cell_id
                WHERE fe.event_date BETWEEN '2016-01-01' AND '2024-12-31'
                """
            )
        random.seed(7)
        nodi = random.sample(tutti, min(N_NODI, len(tutti)))
        insieme = set(nodi)
        fuoco_tutti: set[tuple[tuple[float, float], date]] = set()
        fuoco_nat: set[tuple[tuple[float, float], date]] = set()
        for f in fuochi:
            n = (snap(float(f["lon"]), passo), snap(float(f["lat"]), passo))
            if n not in insieme:
                continue
            fuoco_tutti.add((n, f["event_date"]))
            if str(f["lu"])[:2] in ("31", "32"):
                fuoco_nat.add((n, f["event_date"]))

        conti: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0, 0])
        client = OpenMeteoHttpClient()
        try:
            stati = dict.fromkeys(nodi, params.initial_state)
            avviati = dict.fromkeys(nodi, 0)
            for anno in ANNI:
                primo, ultimo = date(anno, 1, 1), date(anno, 12, 31)
                giorni = [primo + timedelta(days=i) for i in range((ultimo - primo).days + 1)]
                for k in range(0, len(nodi), 100):
                    lotto = nodi[k : k + 100]
                    serie = await client.get_fire_weather_grid(
                        nodes=lotto,
                        window_start=datetime.combine(
                            primo - timedelta(days=1), datetime.min.time(), UTC
                        ),
                        window_end=datetime.combine(ultimo, datetime.max.time(), UTC),
                        use_archive=True,
                    )
                    for nodo, campioni in zip(lotto, serie, strict=True):
                        oss = _observations(
                            MeteoSnapshot(
                                centroid_lon=nodo[0],
                                centroid_lat=nodo[1],
                                window_start=datetime.combine(primo, datetime.min.time(), UTC),
                                window_end=datetime.combine(ultimo, datetime.max.time(), UTC),
                                samples=campioni,
                            ),
                            giorni,
                        )
                        stato = stati[nodo]
                        for g in giorni:
                            o = oss.get(g)
                            if o is None:
                                continue
                            u = advance(
                                stato,
                                month=g.month,
                                temperature_c=o.temperature_c,
                                relative_humidity_pct=o.relative_humidity_pct,
                                wind_speed_kmh=o.wind_speed_kmh,
                                rain_24h_mm=o.rain_24h_mm,
                                params=params,
                            )
                            stato = u.state
                            avviati[nodo] += 1
                            if avviati[nodo] <= AVVIAMENTO:
                                continue
                            c = conti[(g.month, classe(u.fwi))]
                            c[0] += 1
                            c[1] += (nodo, g) in fuoco_tutti
                            c[2] += (nodo, g) in fuoco_nat
                        stati[nodo] = stato
                print(f"anno {anno} fatto", file=sys.stderr, flush=True)
        finally:
            await SharedHttpClient.aclose()
    out = {f"{m}|{c}": v for (m, c), v in sorted(conti.items())}
    print(json.dumps({"nodi": len(nodi), "conti": out}))


asyncio.run(main())
