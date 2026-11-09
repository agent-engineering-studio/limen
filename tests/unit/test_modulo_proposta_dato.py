"""#502: il modulo «Proposta di dato» parla la lingua del catalogo `dati.yaml`.

Una proposta accettata diventa una voce del catalogo ricopiando i campi: se il
catalogo cambia una chiave, questo test chiede di cambiare anche il modulo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

RADICE = Path(__file__).resolve().parents[2]
MODULO = RADICE / ".github" / "ISSUE_TEMPLATE" / "proposta-dato.yml"
CATALOGO = RADICE / "src" / "limen" / "config" / "dati.yaml"

# Le chiavi che scrive solo Limen, dopo la misura: come si conta la copertura,
# con quale comando o variabile si procura il dato, da quale altro dato deriva.
SOLO_DI_LIMEN = {"id", "misura", "procura_con", "variabile", "deriva_da"}
OBBLIGATORI = {
    "nome",
    "a_cosa_serve",
    "livello",
    "fonte",
    "url",
    "licenza",
    "copertura",
    "come_misurarlo",
}


def _campi() -> dict[str, dict[str, Any]]:
    modulo = yaml.safe_load(MODULO.read_text(encoding="utf-8"))
    return {b["id"]: b for b in modulo["body"] if "id" in b}


def test_ogni_chiave_del_catalogo_ha_il_suo_campo() -> None:
    catalogo = yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))
    chiavi = {k for voce in catalogo["voci"] for k in voce}
    assert chiavi - SOLO_DI_LIMEN <= set(_campi())


def test_licenza_link_copertura_e_misura_sono_obbligatori() -> None:
    campi = _campi()
    obbligatori = {k for k, b in campi.items() if b.get("validations", {}).get("required") is True}
    assert obbligatori == OBBLIGATORI


def test_i_pericoli_sono_quelli_di_limen() -> None:
    opzioni = " ".join(o["label"] for o in _campi()["pericoli"]["attributes"]["options"])
    for pericolo in ("landslide", "flood", "wildfire"):
        assert f"({pericolo})" in opzioni


def test_il_modulo_porta_l_etichetta_delle_proposte() -> None:
    modulo = yaml.safe_load(MODULO.read_text(encoding="utf-8"))
    assert "dato-proposto" in modulo["labels"]
