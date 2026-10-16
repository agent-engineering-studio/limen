"""Le stazioni dei sensori sulla mappa pubblica (#255, epic #247).

Una stazione compare sotto un pericolo se misura qualcosa che quel pericolo
legge. Una stazione che non ha ancora mandato niente compare sotto ogni
pericolo che legge qualche grandezza: chi l'ha appena installata deve poterla
trovare. Un pericolo che non ne legge nessuna non ha stazioni.
"""

from __future__ import annotations

from typing import Any

from limen.core.models.hazard import HazardType
from limen.data.repos.sensor_devices_repo import StazionePubblica

# Quali grandezze legge ciascun pericolo: la pioggia due, il terreno solo la
# frana. L'incendio non ne legge ancora nessuna (#248).
PERICOLI_PER_GRANDEZZA: dict[str, frozenset[str]] = {
    "rainfall": frozenset({"landslide", "flood"}),
    "soil_moisture": frozenset({"landslide"}),
    "pore_pressure": frozenset({"landslide"}),
    "displacement": frozenset({"landslide"}),
    "velocity": frozenset({"landslide"}),
    "acceleration": frozenset({"landslide"}),
}


def per_pericolo(stazione: StazionePubblica, hazard: HazardType | None) -> bool:
    if hazard is None:
        return True
    if not any(hazard in pericoli for pericoli in PERICOLI_PER_GRANDEZZA.values()):
        return False
    if not stazione.grandezze:
        return True
    return any(hazard in PERICOLI_PER_GRANDEZZA.get(g, frozenset()) for g in stazione.grandezze)


def geojson(stazioni: list[StazionePubblica], hazard: HazardType | None) -> dict[str, Any]:
    """Una FeatureCollection, già senza nulla che non sia pubblico."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s.lon, s.lat]},
                "properties": {
                    "id": s.id,
                    "tipo": s.device_type,
                    "livello": s.livello,
                    "stato": s.status,
                    "arrotondata": s.arrotondata,
                    "ultima_grandezza": s.ultima_grandezza,
                    "ultimo_valore": s.ultimo_valore,
                    "ultima_unita": s.ultima_unita,
                    "ultimo_istante": (
                        s.ultimo_istante.isoformat() if s.ultimo_istante is not None else None
                    ),
                    "valide_24h": s.valide_24h,
                    "segnalate_24h": s.segnalate_24h,
                },
            }
            for s in stazioni
            if per_pericolo(s, hazard)
        ],
    }


__all__ = ["PERICOLI_PER_GRANDEZZA", "geojson", "per_pericolo"]
