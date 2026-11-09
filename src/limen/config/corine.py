"""Il nome di una classe CORINE Land Cover, in italiano e in inglese (#470)."""

from __future__ import annotations

from functools import cache
from importlib import resources

import yaml
from pydantic import BaseModel, ConfigDict


class NomeClasse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    it: str
    en: str


class LegendaCorine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classi: dict[str, NomeClasse]

    def nome(self, codice: str | None) -> NomeClasse | None:
        return self.classi.get(codice.strip()) if codice else None


@cache
def legenda_corine() -> LegendaCorine:
    testo = resources.files("limen.config").joinpath("corine_classi.yaml").read_text("utf-8")
    return LegendaCorine.model_validate(yaml.safe_load(testo))


__all__ = ["LegendaCorine", "NomeClasse", "legenda_corine"]
