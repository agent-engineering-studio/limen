"""#511: i moduli «Segnala un evento» e «Contesta un punteggio».

Il modulo dell'evento chiede quello che `limen registra-verifica` vuole per
l'evento: se il comando aggiunge un campo obbligatorio, o cambia le scale di
precisione, questo test chiede di cambiare anche il modulo.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import yaml

from limen.cli.registra_verifica import _Evento

RADICE = Path(__file__).resolve().parents[2]
MODULI = RADICE / ".github" / "ISSUE_TEMPLATE"

# Campo del file del fact-check → id del campo nel modulo che lo alimenta.
# `regione` si ricava dal Comune; `lon`/`lat` vengono dalle coordinate.
DAL_MODULO = {
    "quando": "quando",
    "precisione_ora": "precisione_ora",
    "luogo": "luogo",
    "comuni": "comuni",
    "lon": "coordinate",
    "lat": "coordinate",
    "precisione_luogo": "precisione_luogo",
}


def _campi(nome: str) -> dict[str, dict[str, Any]]:
    modulo = yaml.safe_load((MODULI / nome).read_text(encoding="utf-8"))
    return {b["id"]: b for b in modulo["body"] if "id" in b}


def _obbligatorio(campo: dict[str, Any]) -> bool:
    return bool(campo.get("validations", {}).get("required"))


def test_ogni_campo_dell_evento_ha_il_suo_posto_nel_modulo() -> None:
    campi = _campi("evento.yml")
    for nome in _Evento.model_fields:
        if nome == "regione":
            continue
        assert DAL_MODULO[nome] in campi, nome


def test_gli_obbligatori_del_comando_sono_obbligatori_nel_modulo() -> None:
    campi = _campi("evento.yml")
    for nome, campo in _Evento.model_fields.items():
        if campo.is_required() and nome != "luogo":
            assert _obbligatorio(campi[DAL_MODULO[nome]]), nome
    assert _obbligatorio(campi["fonti"])


def _letterali(tipo: Any) -> set[str]:
    """I valori di un `Literal`, anche dentro `Literal[...] | None`."""
    if get_origin(tipo) is Literal:
        return set(get_args(tipo))
    return {v for a in get_args(tipo) for v in _letterali(a)}


def test_le_scale_di_precisione_sono_quelle_del_registro() -> None:
    campi = _campi("evento.yml")
    for nome in ("precisione_ora", "precisione_luogo"):
        opzioni = " ".join(campi[nome]["attributes"]["options"])
        codici = set(re.findall(r"\((T\d|P\d+)\)", opzioni))
        attesi = _letterali(_Evento.model_fields[nome].annotation)
        assert codici == attesi, nome


def test_contestare_chiede_cella_istante_e_conto() -> None:
    campi = _campi("contesta-punteggio.yml")
    for nome in ("cella", "pericolo", "istante", "valore_mostrato", "valore_atteso", "conto"):
        assert _obbligatorio(campi[nome]), nome
