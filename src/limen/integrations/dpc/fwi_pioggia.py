"""La catena FWI rifatta con la pioggia misurata dal DPC.

I codici di siccità del FWI (DMC, DC) scendono solo quando piove, e il
modello a ~9 km non vede i temporali: a Montegiordano, fra il 14 settembre e
il 14 ottobre 2026, la catena aveva 9 mm di pioggia contro i 35-45 misurati
dal «Merging» DPC (radar più pluviometri), ed era rimasta all'estate. Il
14 ottobre dava FWI 50, «molto alto»; con la pioggia vera 26.

La correzione rifà gli ultimi giorni di ogni nodo dallo stato del giorno
prima, con gli ingressi già salvati in ``fwi_state`` — temperatura, umidità
e vento di mezzogiorno — e la cumulata osservata delle 24 ore fino alle
12 UTC al posto di quella del modello. Dove il radar non ha misurato resta la
pioggia salvata: un buco del dato non è un giorno asciutto. Le righe si
riscrivono, e i giorni dopo (oggi, le previsioni) ripartono dallo stato
corretto. Nessuna chiamata a Open-Meteo.

Due fonti con la stessa firma: l'API pubblica del DPC per il passo notturno
(tiene circa cinque mesi), l'archivio locale per il backtest.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta

from limen.core.logging import get_logger
from limen.core.scoring.wildfire.fwi import FwiParams, advance
from limen.data.repos import fwi_state_repo
from limen.data.repos.fwi_state_repo import NodeDay
from limen.integrations.dpc.client import CUM_PERIOD, get_cum_at
from limen.integrations.dpc.merging_archive import MergingArchive
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import FireWeatherObservation, MeteoSnapshot

log = get_logger(__name__)

#: Pioggia delle 24 ore fino a mezzogiorno UTC di un giorno, per nodo (mm).
Fonte = Callable[[list[tuple[float, float]], date], Awaitable[list[float | None]]]
#: Il meteo analizzato di mezzogiorno di più giorni, per nodo.
Meteo = Callable[
    [list[tuple[float, float]], list[date]],
    Awaitable[list[dict[date, FireWeatherObservation]]],
]

#: Ore misurate sotto le quali la somma dall'archivio non vale come giornata.
_ORE_MINIME = 20


def _mezzogiorno(giorno: date) -> datetime:
    return datetime.combine(giorno, time(12), UTC)


def fonte_dpc(max_step_mm: float) -> Fonte:
    """La cumulata CUM24 delle 12 UTC dall'API DPC, controllata come in #235."""

    async def pioggia(nodi: list[tuple[float, float]], giorno: date) -> list[float | None]:
        t = _mezzogiorno(giorno)
        grid = await get_cum_at(24, t)
        if grid is None:
            return [None] * len(nodi)
        prima = await get_cum_at(24, t - CUM_PERIOD)
        if prima is not None:
            grid, _ = grid.discard_inconsistent(prima, max_step=max_step_mm)
        return grid.sample(nodi)

    return pioggia


def fonte_archivio(archivio: MergingArchive) -> Fonte:
    """La stessa cumulata ricostruita dall'archivio locale del «Merging»."""

    async def pioggia(nodi: list[tuple[float, float]], giorno: date) -> list[float | None]:
        fine = _mezzogiorno(giorno)
        ore = archivio.oraria(nodi, fine - timedelta(hours=24), fine)
        out: list[float | None] = []
        for k in range(len(nodi)):
            misurate = [x for v in ore.values() if (x := v[k]) is not None]
            out.append(sum(misurate) if len(misurate) >= _ORE_MINIME else None)
        return out

    return pioggia


def meteo_open_meteo(client: OpenMeteoHttpClient | None = None) -> Meteo:
    """Mezzogiorno dei giorni passati dall'API di previsione, che per il
    passato dà le corse più recenti: meglio della previsione delle 00 UTC con
    cui la riga di quel giorno era stata scritta (#201)."""
    cli = client or OpenMeteoHttpClient()

    async def meteo(
        nodi: list[tuple[float, float]], giorni: list[date]
    ) -> list[dict[date, FireWeatherObservation]]:
        inizio = datetime.combine(giorni[0] - timedelta(days=1), time.min, UTC)
        fine = datetime.combine(giorni[-1], time.max, UTC)
        serie = await cli.get_fire_weather_grid(
            nodes=nodi, window_start=inizio, window_end=fine, use_archive=False
        )
        out: list[dict[date, FireWeatherObservation]] = []
        for (lon, lat), campioni in zip(nodi, serie, strict=True):
            snap = MeteoSnapshot(
                centroid_lon=lon,
                centroid_lat=lat,
                window_start=inizio,
                window_end=fine,
                samples=campioni,
            )
            out.append({g: o for g in giorni if (o := snap.noon_observation(g)) is not None})
        return out

    return meteo


def _con_meteo(r: NodeDay, oss: FireWeatherObservation | None) -> NodeDay:
    if oss is None:
        return r
    return NodeDay(
        lon=r.lon,
        lat=r.lat,
        day=r.day,
        outputs=r.outputs,
        chain_days=r.chain_days,
        temperature_c=oss.temperature_c,
        relative_humidity_pct=oss.relative_humidity_pct,
        wind_speed_kmh=oss.wind_speed_kmh,
        rain_24h_mm=oss.rain_24h_mm,
    )


def ricalcola(
    righe: list[NodeDay],
    prima: NodeDay,
    pioggia: dict[date, float | None],
    params: FwiParams,
    max_gap_days: int,
) -> list[NodeDay]:
    """La catena di un nodo rifatta dal giorno ``prima`` con la pioggia data.

    Pura. Un giorno mancante si salta come lo salta la catena operativa,
    che prosegue dallo stato precedente; oltre ``max_gap_days`` quella
    ripartiva dal seme, e saldarla qui ne inventerebbe la storia.
    """
    out: list[NodeDay] = []
    stato = prima.outputs.state
    ultimo = prima.day
    for r in righe:
        if (r.day - ultimo).days > max_gap_days:
            break
        oss = pioggia.get(r.day)
        mm = r.rain_24h_mm if oss is None else oss
        uscita = advance(
            stato,
            month=r.day.month,
            temperature_c=r.temperature_c,
            relative_humidity_pct=r.relative_humidity_pct,
            wind_speed_kmh=r.wind_speed_kmh,
            rain_24h_mm=mm,
            params=params,
        )
        out.append(
            NodeDay(
                lon=r.lon,
                lat=r.lat,
                day=r.day,
                outputs=uscita,
                chain_days=r.chain_days,
                temperature_c=r.temperature_c,
                relative_humidity_pct=r.relative_humidity_pct,
                wind_speed_kmh=r.wind_speed_kmh,
                rain_24h_mm=mm,
            )
        )
        stato = uscita.state
        ultimo = r.day
    return out


async def correggi(
    *,
    dal: date,
    al: date,
    params: FwiParams,
    max_gap_days: int,
    fonte: Fonte,
    meteo: Meteo | None = None,
) -> dict[str, int | float]:
    """Rifà la catena di ogni nodo da ``dal`` ad ``al`` e riscrive le righe.

    Idempotente: rifatta due volte con la stessa pioggia dà le stesse righe.
    Si riparte dall'ultima riga prima di ``dal``; un nodo la cui catena è
    nata dopo riparte dalla sua prima riga, che resta com'è. Con ``meteo``,
    i giorni prima di ``al`` prendono anche temperatura, umidità e vento
    analizzati al posto di quelli salvati; ``al``, che di solito è oggi,
    resta quello della previsione.
    """
    righe = await fwi_state_repo.read_between(dal - timedelta(days=max_gap_days), al)
    nodi = list(righe)
    giorni = [dal + timedelta(days=i) for i in range((al - dal).days + 1)]
    osservata = {g: await fonte(nodi, g) for g in giorni}
    passati = [g for g in giorni if g < al]
    analizzato = await meteo(nodi, passati) if meteo is not None and passati else None
    scritte: list[NodeDay] = []
    con_osservata = 0
    delta_fwi: list[float] = []
    for k, nodo in enumerate(nodi):
        serie = righe[nodo]
        precedenti = [r for r in serie if r.day < dal]
        partenza = precedenti[-1] if precedenti else serie[0]
        da_rifare = [r for r in serie if r.day > partenza.day]
        if analizzato is not None:
            da_rifare = [_con_meteo(r, analizzato[k].get(r.day)) for r in da_rifare]
        pioggia = {g: osservata[g][k] for g in giorni}
        con_osservata += sum(1 for v in pioggia.values() if v is not None)
        nuove = ricalcola(da_rifare, partenza, pioggia, params, max_gap_days)
        vecchie = {r.day: r for r in serie}
        delta_fwi.extend(n.outputs.fwi - vecchie[n.day].outputs.fwi for n in nuove)
        scritte.extend(nuove)
    await fwi_state_repo.upsert_many(scritte)
    conti: dict[str, int | float] = {
        "nodi": len(nodi),
        "righe": len(scritte),
        "giorni_con_pioggia_osservata": con_osservata,
        "fwi_variazione_media": round(sum(delta_fwi) / len(delta_fwi), 2) if delta_fwi else 0.0,
        "fwi_variazione_minima": round(min(delta_fwi), 2) if delta_fwi else 0.0,
    }
    log.info("fwi.pioggia_osservata.done", dal=dal.isoformat(), al=al.isoformat(), **conti)
    return conti
