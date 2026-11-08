"""Legge i dati di base di una cella (#422): valori, classi e cosa è caricato.

Le colonne vengono dal catalogo del pacchetto, validate come identificatori
al caricamento (`config/catalogo_dati.py`), non da un input. Per ogni colonna
si guarda anche se la regione della cella ne ha almeno un valore: è ciò che
distingue «fuori dalle aree PAI» da «PAI non caricato».
"""

from __future__ import annotations

from limen.config.catalogo_dati import CatalogoDati
from limen.core.dati_di_base import DatoDiBase, dati_di_base
from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.pai_repo import PAI_CLASS_TO_NORM

_NORM_TO_PAI = {round(v, 2): k for k, v in PAI_CLASS_TO_NORM.items()}


async def leggi(catalogo: CatalogoDati, cell_id: str, pericolo: HazardType) -> list[DatoDiBase]:
    colonne = [
        v.misura.colonna
        for v in catalogo.voci
        if v.misura.colonna is not None and pericolo in v.pericoli
    ]
    if not colonne:
        return []
    valori_sql = ", ".join(f"f.{c} AS v_{c}" for c in colonne)
    caricati_sql = ", ".join(f"bool_or(x.{c} IS NOT NULL) AS c_{c}" for c in colonne)
    async with acquire() as conn:
        riga = await conn.fetchrow(
            f"SELECT {valori_sql}, f.flood_hazard_class, f.lithology, k.* "
            "FROM grid_cells g "
            "LEFT JOIN cell_static_factors f ON f.cell_id = g.id "
            f"CROSS JOIN LATERAL (SELECT {caricati_sql} FROM grid_cells g2 "
            "  JOIN cell_static_factors x ON x.cell_id = g2.id WHERE g2.aoi_id = g.aoi_id) k "
            "WHERE g.id = $1",
            cell_id,
        )
    if riga is None:
        return []
    valori: dict[str, float | str | None] = {}
    for c in colonne:
        v = riga[f"v_{c}"]
        valori[c] = None if v is None else (v if isinstance(v, str) else float(v))
    pai = valori.get("pai_class_norm")
    classi: dict[str, str | None] = {
        "flood_hazard_norm": riga["flood_hazard_class"],
        "litho_weight": riga["lithology"],
        "pai_class_norm": (_NORM_TO_PAI.get(round(pai, 2)) if isinstance(pai, float) else None),
    }
    caricati = {c: bool(riga[f"c_{c}"]) for c in colonne}
    return dati_di_base(catalogo, pericolo, valori, classi, caricati)


__all__ = ["leggi"]
