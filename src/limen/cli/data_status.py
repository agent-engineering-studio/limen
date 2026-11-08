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

from limen.cli.dem_tiles import cartella_tile
from limen.config.catalogo_dati import CatalogoDati, carica_catalogo
from limen.core.installazione import regioni_senza
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.data.db import lifespan_pool
from limen.data.repos import copertura_repo

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Layer:
    """Un fattore statico, la sua colonna e ciò che lo popola: la vista di
    ``data-status`` su una voce del catalogo (``config/dati.yaml``)."""

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


#: Come ``data-status`` chiama i pericoli, nell'ordine in cui li elenca.
_NOMI_PERICOLO: dict[HazardType, str] = {
    HazardType.LANDSLIDE: "frana",
    HazardType.WILDFIRE: "incendio",
    HazardType.FLOOD: "alluvione",
}


def _layers(catalogo: CatalogoDati) -> tuple[Layer, ...]:
    colonne = {v.id: v.misura.colonna for v in catalogo.voci}
    return tuple(
        Layer(
            column=v.misura.colonna,
            label=v.nome,
            gate=v.variabile,
            derived_from=colonne[v.deriva_da] if v.deriva_da else None,
            fetch_with=v.procura_con,
        )
        for v in catalogo.voci
        if v.misura.colonna is not None
    )


_CATALOGO = carica_catalogo()
LAYERS: tuple[Layer, ...] = _layers(_CATALOGO)

#: Di cosa ha bisogno ogni pericolo per discriminare nello spazio: le voci
#: essenziali del catalogo. Un pericolo a cui manca tutto produce una mappa
#: uniforme: leggibile, e inutile.
HAZARD_NEEDS: dict[str, tuple[str, ...]] = {
    nome: tuple(v.misura.colonna for v in _CATALOGO.essenziali(h) if v.misura.colonna)
    for h, nome in _NOMI_PERICOLO.items()
}
_PERIMETRI = _CATALOGO.voce("perimetri_effis")
_CONTATE_SUI_VERI = frozenset(v.id for v in _CATALOGO.voci if v.misura.conta == "veri")


def _bar(pct: float, width: int = 20) -> str:
    filled = round(pct * width)
    return "#" * filled + "." * (width - filled)


async def run() -> int:
    async with lifespan_pool():
        copertura = await copertura_repo.leggi(_CATALOGO)
    total = copertura.celle_totali
    aois = copertura.regioni
    if total == 0:
        print("Nessuna cella nella griglia: esegui prima `limen seed`.")
        return 0

    voce_di = {v.misura.colonna: v.id for v in _CATALOGO.voci if v.misura.colonna}
    counts = {layer.column: copertura.totali[voce_di[layer.column]] for layer in LAYERS}
    senza = regioni_senza(_CATALOGO, copertura.per_regione)
    # I perimetri di area bruciata non stanno in cell_static_factors: sono
    # il truth set del backtest incendio, e la loro assenza si nota solo lì.
    perimeters = copertura.totali[_PERIMETRI.id]

    print(f"\nCopertura dei fattori statici — {total:,} celle in {aois} AOI\n".replace(",", "."))
    print(f"  {'layer':34s} {'celle':>10s}  {'':20s}  gate")
    for layer in LAYERS:
        n = counts[layer.column]
        pct = n / total if total else 0.0
        gate = layer.gate or (
            f"deriva da {layer.derived_from}" if layer.derived_from else layer.fetch_with or ""
        )
        # Contate sui `true` (#473): il numero è quante celle hanno un abitato
        # vicino, non quanta Italia è coperta, e una barra al 31 % si leggerebbe
        # come un caricamento a metà.
        barra = (
            _bar(pct)
            if voce_di[layer.column] not in _CONTATE_SUI_VERI
            else (f"{'calcolato' if n else 'non calcolato':20s}")
        )
        print(f"  {layer.label:34s} {n:>10,}  {barra}  {gate}".replace(",", "."))
    print(f"\n  {_PERIMETRI.nome:34s} {perimeters:>10,}".replace(",", "."))
    # Le tile del rilievo non sono un fattore per cella: servono alla vista
    # «Rilievo» della mappa, e mancano senza che lo score se ne accorga.
    rilievo = sorted(p.name for p in cartella_tile().glob("rilievo-*.pmtiles"))
    print(
        f"  {'tile del rilievo (vista «Rilievo»)':34s} {len(rilievo):>10}  "
        + (", ".join(rilievo) if rilievo else "nessuna   → limen dem-tiles")
    )

    print("\nCosa manca a ciascun pericolo\n")
    for hazard, needed in HAZARD_NEEDS.items():
        # In ogni regione, come la pagina di installazione: un dato caricato per
        # due regioni su venti non è «tutto presente».
        missing = [
            next(x.label for x in LAYERS if x.column == c)
            + (f" ({len(senza[voce_di[c]])} regioni su {aois})" if counts[c] else "")
            for c in needed
            if senza[voce_di[c]]
        ]
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
        # `make static-data` è la strada di tutti i layer che non ne hanno una
        # propria: stamparlo accanto a ogni variabile non direbbe niente.
        comandi = {
            layer.gate: layer.fetch_with
            for layer in LAYERS
            if layer.fetch_with and layer.fetch_with != "make static-data"
        }
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
