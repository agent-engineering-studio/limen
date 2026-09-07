"""``limen data-status`` — quali layer statici sono caricati, e cosa li blocca.

Ogni pericolo poggia su fattori per cella che arrivano da sorgenti diverse,
ognuna dietro la sua variabile d'ambiente. Senza un posto dove leggerlo, la
domanda "perché la mappa è uniforme?" si risponde solo interrogando il
database a mano — ed è la domanda che ci si fa per prima.

Il comando dice tre cose: quante celle hanno ciascun layer, quale variabile
lo abilita, e quali pericoli restano indeboliti da ciò che manca. Non tocca
nulla: è sicuro eseguirlo in produzione.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Layer:
    """Un fattore statico, la sua colonna e ciò che lo popola."""

    column: str
    label: str
    #: Variabile d'ambiente che abilita l'ingest, o ``None`` se è derivato.
    gate: str | None
    #: Nota per i layer che dipendono da un altro layer invece che da un file.
    derived_from: str | None = None
    #: Comando che procura la sorgente, per i layer che si scaricano da soli.
    #: Vale la pena stamparlo qui: questo è il posto dove si guarda quando la
    #: mappa è uniforme, e sapere che manca una variabile non dice come
    #: riempirla.
    fetch_with: str | None = None


LAYERS: tuple[Layer, ...] = (
    Layer("iffi_density_500", "densità frane storiche (IFFI)", "GEOSERVER_SOURCE__DB_DSN"),
    Layer("pai_class_norm", "pericolosità frana PAI", "GEOSERVER_SOURCE__DB_DSN"),
    Layer("flood_hazard_norm", "pericolosità idraulica ISPRA", "GEOSERVER_SOURCE__DB_DSN"),
    Layer("slope_deg", "pendenza (DTM)", "LIMEN_DEM_RASTER"),
    Layer("landuse_code", "copertura del suolo (CORINE)", "LIMEN_CORINE_RASTER"),
    Layer(
        "imperviousness_norm",
        "suolo impermeabilizzato (CLMS)",
        "LIMEN_IMPERVIOUSNESS_RASTER",
        fetch_with="make imperviousness-data",
    ),
    Layer(
        "wui_proximity_norm",
        "interfaccia urbano-bosco",
        None,
        derived_from="landuse_code",
    ),
    Layer("distance_to_road_m", "distanza dalla rete stradale", "LIMEN_OSM_ROADS"),
    Layer("litho_weight", "litologia", "LIMEN_GEOLOGICAL_SHAPEFILE"),
)

#: Di cosa ha bisogno ogni pericolo per discriminare nello spazio. Un pericolo
#: a cui manca tutto produce una mappa uniforme: leggibile, e inutile.
HAZARD_NEEDS: dict[str, tuple[str, ...]] = {
    "frana": ("iffi_density_500", "pai_class_norm", "slope_deg", "litho_weight"),
    "incendio": ("landuse_code", "slope_deg"),
    "alluvione": ("flood_hazard_norm", "imperviousness_norm"),
}


def _bar(pct: float, width: int = 20) -> str:
    filled = round(pct * width)
    return "#" * filled + "." * (width - filled)


async def run() -> int:
    async with lifespan_pool(), acquire() as conn:
        total = int(await conn.fetchval("SELECT count(*) FROM cell_static_factors") or 0)
        aois = int(await conn.fetchval("SELECT count(*) FROM aoi") or 0)
        if total == 0:
            print("Nessuna cella in cell_static_factors: esegui prima `limen seed`.")
            return 0

        counts: dict[str, int] = {}
        for layer in LAYERS:
            counts[layer.column] = int(
                await conn.fetchval(
                    f"SELECT count({layer.column}) FROM cell_static_factors"
                    # Nome di colonna da una costante del modulo, non da input.
                )
                or 0
            )

        # I perimetri di area bruciata non stanno in cell_static_factors: sono
        # il truth set del backtest incendio, e la loro assenza si nota solo lì.
        perimeters = int(await conn.fetchval("SELECT count(*) FROM fire_perimeters") or 0)

    print(f"\nCopertura dei fattori statici — {total:,} celle in {aois} AOI\n".replace(",", "."))
    print(f"  {'layer':34s} {'celle':>10s}  {'':20s}  gate")
    for layer in LAYERS:
        n = counts[layer.column]
        pct = n / total if total else 0.0
        gate = layer.gate or f"deriva da {layer.derived_from}"
        print(f"  {layer.label:34s} {n:>10,}  {_bar(pct)}  {gate}".replace(",", "."))
    print(f"\n  {'perimetri EFFIS (truth set incendio)':34s} {perimeters:>10,}".replace(",", "."))

    print("\nCosa manca a ciascun pericolo\n")
    for hazard, needed in HAZARD_NEEDS.items():
        missing = [next(x.label for x in LAYERS if x.column == c) for c in needed if counts[c] == 0]
        if not missing:
            print(f"  {hazard:11s} tutto presente")
        else:
            print(f"  {hazard:11s} manca: {', '.join(missing)}")

    unset = sorted(
        {
            layer.gate
            for layer in LAYERS
            if layer.gate and counts[layer.column] == 0 and not os.getenv(layer.gate)
        }
    )
    if unset:
        print("\nVariabili non impostate in questo ambiente:")
        comandi = {layer.gate: layer.fetch_with for layer in LAYERS if layer.fetch_with}
        for var in unset:
            comando = comandi.get(var)
            print(f"  {var}" + (f"   → {comando}" if comando else ""))
    print()
    return 0


def main() -> int:  # convenience for pyproject entry points
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
