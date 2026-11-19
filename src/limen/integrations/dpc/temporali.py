"""I temporali di un fotogramma SRI e dove vanno (#643): ``dpc_radar.storms`` e ``motion``.

Una macchia di pixel che si toccano sopra la soglia della sveglia radar è un
temporale: centro della pioggia, area, picco. Il moto viene dagli SRI
dell'ultima mezz'ora (``motion``): la velocità e la direzione verso cui va,
nel centro del temporale. Senza fotogrammi precedenti, o se il moto non si
trova, velocità e direzione restano ``None``: non si sa, non è «fermo».

Informazione e basta: non entra nei punteggi né decide la sveglia.
"""

from __future__ import annotations

import math
from typing import Any

from dpc_radar import DpcRadarError, RainGrid, motion, storms

from limen.core.logging import get_logger
from limen.data.repos.radar_temporali_repo import Temporale

log = get_logger(__name__)


def temporali(frames: list[RainGrid], *, soglia_mmh: float) -> list[Temporale]:
    """I temporali dell'ultimo fotogramma, il più forte per primo."""
    if not frames:
        return []
    ultimo = frames[-1]
    moto = None
    if len(frames) >= 2:
        try:
            trovato = motion(frames)
            moto = trovato if trovato.found else None
        except DpcRadarError as exc:
            log.info("dpc.temporali.senza_moto", error=str(exc))
    out: list[Temporale] = []
    for n, s in enumerate(storms(ultimo, threshold=soglia_mmh)):
        va = moto.at(s.lon, s.lat) if moto is not None else None
        out.append(
            Temporale(
                osservato_at=ultimo.time,
                n=n,
                soglia_mmh=soglia_mmh,
                lon=round(s.lon, 4),
                lat=round(s.lat, 4),
                area_km2=round(s.area_km2, 1),
                picco_mmh=round(s.peak, 1),
                media_mmh=round(s.mean, 1),
                picco_lon=round(s.peak_lon, 4),
                picco_lat=round(s.peak_lat, 4),
                bbox=(s.bbox[0], s.bbox[1], s.bbox[2], s.bbox[3]),
                velocita_kmh=round(va[0], 1) if va else None,
                direzione_gradi=round(va[1]) if va else None,
            )
        )
    return out


#: Km per grado di latitudine; quelli di longitudine scalano col coseno.
_KM_PER_GRADO = 111.2


def fra_un_ora(t: Temporale) -> tuple[float, float] | None:
    """Dove arriva il centro del temporale in un'ora, se il moto è noto."""
    if t.velocita_kmh is None or t.direzione_gradi is None:
        return None
    rad = math.radians(t.direzione_gradi)
    dlat = t.velocita_kmh * math.cos(rad) / _KM_PER_GRADO
    dlon = t.velocita_kmh * math.sin(rad) / (_KM_PER_GRADO * math.cos(math.radians(t.lat)))
    return round(t.lon + dlon, 4), round(t.lat + dlat, 4)


def geojson(temporali_: list[Temporale]) -> dict[str, Any]:
    """Per la mappa: il centro di ogni temporale e, se il moto è noto, la linea fino
    a dove sarà fra un'ora. Il moto sposta la pioggia, non la fa crescere né morire."""
    features: list[dict[str, Any]] = []
    for t in temporali_:
        props = {
            "n": t.n,
            "picco_mmh": t.picco_mmh,
            "area_km2": t.area_km2,
            "velocita_kmh": t.velocita_kmh,
            "direzione_gradi": t.direzione_gradi,
            "osservato_at": t.osservato_at.isoformat(),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [t.lon, t.lat]},
                "properties": props,
            }
        )
        dopo = fra_un_ora(t)
        if dopo is not None:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[t.lon, t.lat], list(dopo)]},
                    "properties": props,
                }
            )
    return {"type": "FeatureCollection", "features": features}
