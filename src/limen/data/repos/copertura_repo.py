"""Quanta parte dell'Italia ha ciascun dato del catalogo (#404).

Celle di ``cell_static_factors`` con un valore nella colonna della voce,
**regione per regione** (la prontezza di un pericolo chiede che il dato ci
sia in ogni regione seminata), o righe della tabella della voce. Una sola
scansione della tabella delle celle per tutte le colonne: l'endpoint che la
usa è pubblico. I nomi di colonna e tabella vengono dal catalogo del
pacchetto, validati come identificatori al caricamento, non da un input.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from limen.config.catalogo_dati import CatalogoDati
from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class Copertura:
    celle_totali: int
    regioni: int
    #: Per id di voce: celle con il dato, o righe della tabella.
    totali: dict[str, int]
    #: Per regione e id di voce (solo le voci misurate per cella).
    per_regione: dict[str, dict[str, int]]
    #: Le celle di ogni regione seminata.
    celle_per_regione: dict[str, int]
    #: Per regione e id di voce, le celle con un valore > 0 (solo le voci con
    #: ``informativo``): una colonna scritta a zero ovunque non è un dato.
    informativi_per_regione: dict[str, dict[str, int]] = field(default_factory=dict)


async def leggi(catalogo: CatalogoDati) -> Copertura:
    colonne = {v.id: v.misura.colonna for v in catalogo.voci if v.misura.colonna is not None}
    veri = {v.id for v in catalogo.voci if v.misura.conta == "veri"}
    conte = ", ".join(
        f"count(*) FILTER (WHERE f.{col}) AS {id_}" if id_ in veri else f"count(f.{col}) AS {id_}"
        for id_, col in colonne.items()
    )
    positivi = {
        v.id: v.misura.colonna
        for v in catalogo.voci
        if v.misura.colonna is not None and v.misura.informativo == "positivi"
    }
    conte += "".join(
        f", count(*) FILTER (WHERE f.{col} > 0) AS i_{id_}" for id_, col in positivi.items()
    )
    async with acquire() as conn:
        righe = await conn.fetch(
            f"SELECT g.aoi_id, count(*) AS celle, {conte} "
            # Dalla griglia: una regione seminata ma senza fattori non ha righe in
            # `cell_static_factors`, e partendo da lì non esisterebbe, così il
            # pericolo risulterebbe «pronto» con due regioni caricate su venti.
            "FROM grid_cells g LEFT JOIN cell_static_factors f ON f.cell_id = g.id "
            "GROUP BY g.aoi_id"
        )
        regioni = int(await conn.fetchval("SELECT count(*) FROM aoi") or 0)
        totali: dict[str, int] = {}
        for voce in catalogo.voci:
            if voce.misura.tabella is not None:
                totali[voce.id] = int(
                    await conn.fetchval(f"SELECT count(*) FROM {voce.misura.tabella}") or 0
                )
    per_regione = {str(r["aoi_id"]): {id_: int(r[id_]) for id_ in colonne} for r in righe}
    for id_ in colonne:
        totali[id_] = sum(conte_[id_] for conte_ in per_regione.values())
    return Copertura(
        celle_totali=sum(int(r["celle"]) for r in righe),
        regioni=regioni,
        totali=totali,
        per_regione=per_regione,
        celle_per_regione={str(r["aoi_id"]): int(r["celle"]) for r in righe},
        informativi_per_regione={
            str(r["aoi_id"]): {id_: int(r[f"i_{id_}"]) for id_ in positivi} for r in righe
        },
    )


__all__ = ["Copertura", "leggi"]
