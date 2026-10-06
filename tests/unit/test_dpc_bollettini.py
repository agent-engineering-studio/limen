"""Il bollettino di criticità DPC (#155): le parti pure dell'import.

Il bollettino è già strutturato — testo del livello, zona, poligono — e
questi test fissano come si legge, senza rete.
"""

from __future__ import annotations

from datetime import date

from limen.integrations.dpc.bollettini import emissione, livello, zone_da_geojson

_NESSUNA = "Assenza di fenomeni significativi prevedibili / NESSUNA ALLERTA"


def test_il_livello_si_legge_dal_colore_scritto() -> None:
    assert livello("Assenza di fenomeni significativi prevedibili / NESSUNA ALLERTA") == 0
    assert livello("Ordinaria per rischio temporali / ALLERTA GIALLA") == 1
    assert livello("Moderata per rischio idrogeologico / ALLERTA ARANCIONE") == 2
    assert livello("Elevata per rischio idraulico / ALLERTA ROSSA") == 3
    assert livello(None) == 0


def test_l_emissione_viene_dal_nome_del_file_in_ora_italiana() -> None:
    e = emissione("20261005_1417_today.json")
    assert e is not None
    assert (e.date(), e.hour, e.minute) == (date(2026, 10, 5), 14, 17)
    assert e.utcoffset() is not None
    assert emissione("20261005_1417_tomorrow.json") is None


def test_le_zone_portano_i_tre_rischi_e_un_multipoligono() -> None:
    dati = {
        "features": [
            {
                "properties": {
                    "Nome zona": "Bacino di Levante / Carso",
                    "Rappresentata nella mappa": "Ordinaria per rischio temporali / ALLERTA GIALLA",
                    "Per rischio idrogeologico": _NESSUNA,
                    "Per rischio idraulico": _NESSUNA,
                    "Per rischio temporali": "Ordinaria per rischio temporali / ALLERTA GIALLA",
                    "Comuni": ["Trieste"],
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[13.7, 45.6], [13.9, 45.6], [13.9, 45.7], [13.7, 45.6]]],
                },
            },
            # Una zona senza nome non entra: non si saprebbe a chi attribuirla.
            {"properties": {}, "geometry": {"type": "Point", "coordinates": [13.7, 45.6]}},
        ]
    }
    [zona] = zone_da_geojson(dati, date(2026, 10, 6))
    assert zona.zona == "Bacino di Levante / Carso"
    assert (zona.livello, zona.idrogeologico, zona.idraulico, zona.temporali) == (1, 0, 0, 1)
    assert zona.geom.geom_type == "MultiPolygon"
