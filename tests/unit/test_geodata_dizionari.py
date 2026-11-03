"""I dizionari IFFI come li serve oggi l'API di IdroGEO."""

from __future__ import annotations

from geodata.init.importers import _coerce_dizionario


def test_le_chiavi_italiane_dell_api() -> None:
    # Risposta reale di /api/dizionari/tipo_movimento, ridotta.
    payload = [
        {"diz": "tipo_movimento", "codice": "1", "descrizione": "Crollo/Ribaltamento"},
        {"diz": "tipo_movimento", "codice": "0", "descrizione": "n.d."},
    ]
    assert _coerce_dizionario(payload) == [("1", "Crollo/Ribaltamento"), ("0", "n.d.")]


def test_le_forme_di_prima_restano() -> None:
    assert _coerce_dizionario({"A": "uno"}) == [("A", "uno")]
    assert _coerce_dizionario([{"code": "B", "label": "due"}, "rumore"]) == [("B", "due")]
