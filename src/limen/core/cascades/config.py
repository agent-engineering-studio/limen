"""Schema della configurazione delle cascate (#58).

Un file a sé, `config/hazards/cascades.yaml`, e non un blocco dentro un
pericolo: una cascata non appartiene a nessuno dei due, dice cosa un pericolo
passato fa a un pericolo futuro e vive fra i due.

Caricato e validato come le soglie dei pericoli, con lo stesso schema strict:
un refuso in una regola di cascata deve fermare l'avvio, non scoprirsi come
un moltiplicatore silenziosamente a zero.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from limen.core.models.risk import RiskLevel

CASCADES_PACKAGE = "limen.config"
CASCADES_DIR = "hazards"
CASCADES_FILE = "cascades.yaml"


def cascades_path() -> Path:
    """Il file delle cascate, risolto come le soglie dei pericoli."""
    ref = resources.files(CASCADES_PACKAGE).joinpath(CASCADES_DIR).joinpath(CASCADES_FILE)
    return Path(str(ref))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PostFireFloodRule(_Strict):
    """Incendio → alluvione: suolo idrofobico che amplifica il ramo pluviale.

    Una campana gaussiana come il post-incendio delle frane, e con numeri
    suoi: l'idrofobicità del suolo si esaurisce prima della perdita di
    radici, quindi la finestra è più corta.
    """

    enabled: bool
    window_months: float = Field(..., gt=0.0)
    peak_months: float = Field(..., ge=0.0)
    curve_denominator: float = Field(..., gt=0.0)
    max_multiplier: float = Field(..., ge=1.0)

    @model_validator(mode="after")
    def _peak_inside_window(self) -> PostFireFloodRule:
        if self.peak_months > self.window_months:
            raise ValueError(
                f"post_fire_flood.peak_months ({self.peak_months}) cade fuori dalla "
                f"finestra ({self.window_months}): l'amplificazione non arriverebbe "
                "mai al massimo"
            )
        return self


class JointRainRule(_Strict):
    """Pioggia estrema → un solo messaggio con due rischi."""

    enabled: bool
    min_level: RiskLevel
    window_hours: float = Field(..., gt=0.0)

    # In YAML la classe è una stringa e lo schema è strict, che pretende
    # l'istanza dell'enum: la conversione va fatta prima della validazione.
    # Un nome di classe inesistente resta un errore, ed è ciò che serve —
    # una soglia scritta male non deve diventare silenziosamente "None".
    @field_validator("min_level", mode="before")
    @classmethod
    def _coerce_level(cls, v: object) -> object:
        return RiskLevel(v) if isinstance(v, str) else v


class CascadeRules(_Strict):
    """Tutte le regole di cascata."""

    post_fire_flood: PostFireFloodRule
    joint_rain: JointRainRule


def load_cascades(path: Path | str | None = None) -> CascadeRules:
    """Carica e valida le regole. ``path`` esplicito scavalca la cache."""
    if path is None:
        return _load_cached()
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return CascadeRules.model_validate(raw)


@cache
def _load_cached() -> CascadeRules:
    raw: dict[str, Any] = yaml.safe_load(cascades_path().read_text(encoding="utf-8")) or {}
    return CascadeRules.model_validate(raw)


__all__ = [
    "CascadeRules",
    "JointRainRule",
    "PostFireFloodRule",
    "cascades_path",
    "load_cascades",
]
