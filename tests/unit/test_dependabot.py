"""#465: Dependabot guarda Python, SPA e Actions, e le librerie compagne
fissate con `~=` stanno tutte nel loro gruppo."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

RADICE = Path(__file__).resolve().parents[2]


def _config() -> dict[str, dict[str, object]]:
    dati = yaml.safe_load((RADICE / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    return {u["package-ecosystem"]: u for u in dati["updates"]}


def test_tre_ecosistemi() -> None:
    config = _config()
    assert set(config) == {"uv", "npm", "github-actions"}
    assert config["npm"]["directory"] == "/frontend"


def test_le_librerie_compagne_sono_tutte_nel_loro_gruppo() -> None:
    progetto = tomllib.loads((RADICE / "pyproject.toml").read_text(encoding="utf-8"))
    compagne = {
        re.split(r"[\[~]", d, maxsplit=1)[0]
        for d in progetto["project"]["dependencies"]
        if "~=" in d
    }
    gruppi = _config()["uv"]["groups"]
    assert isinstance(gruppi, dict)
    assert set(gruppi["librerie-compagne"]["patterns"]) == compagne
    # Il primo gruppo che corrisponde vince: le compagne vanno prima del gruppo generico.
    assert next(iter(gruppi)) == "librerie-compagne"


def test_niente_versioni_maggiori_e_un_giro_al_mese() -> None:
    """Il primo giro aprì dieci PR in un'ora e due PR uv unite in fila
    ruppero `uv.lock` su main: le maggiori si fanno a mano."""
    for ecosistema, voce in _config().items():
        schedule = voce["schedule"]
        assert isinstance(schedule, dict)
        assert schedule["interval"] == "monthly", ecosistema
        if ecosistema == "github-actions":
            continue
        ignorate = voce["ignore"]
        assert isinstance(ignorate, list)
        assert {"dependency-name": "*", "update-types": ["version-update:semver-major"]} in ignorate
