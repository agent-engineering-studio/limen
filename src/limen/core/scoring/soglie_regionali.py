"""Le soglie di pioggia regionali per le frane, e la variante che le usa (#506).

Il file `config/soglie_frane_regionali.yaml` raccoglie le soglie pubblicate
da Regioni e letteratura, con fonte e licenza. La produzione non le legge:
usa le curve di Caine per macroregione di `landslide.yaml`. Le legge
:func:`con_soglie_regionali`, che restituisce le soglie frana con la curva
regionale al posto di quella della macroregione nelle AOI che ne hanno una,
per il confronto in `limen backtest` (`LIMEN_BACKTEST_SOGLIE_REGIONALI=1`).
"""

from __future__ import annotations

from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from limen.core.scoring.regional_thresholds import CaineMacroregion, RegionalThresholds

_FILE = "soglie_frane_regionali.yaml"


class Fonte(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citazione: str
    url: str
    licenza: str


class Soglia(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    forma: Literal["E-D", "I-D"]
    alpha: float = Field(..., gt=0.0)
    gamma: float | None = None
    beta: float | None = None
    aoi: tuple[str, ...] = ()
    zona: str | None = None
    durata_h: tuple[float, float] | None = None
    livello: str | None = None
    nrg_h: float | None = None
    fonte: str
    nota: str | None = None

    @model_validator(mode="after")
    def _esponente(self) -> Soglia:
        if (self.forma == "E-D") != (self.gamma is not None) or (
            (self.forma == "I-D") != (self.beta is not None)
        ):
            raise ValueError(f"{self.id}: E-D vuole gamma, I-D vuole beta")
        if not self.aoi and self.zona is None:
            raise ValueError(f"{self.id}: serve aoi o zona")
        return self

    def in_intensita(self) -> CaineMacroregion:
        """La curva come la legge Caine: I = alpha · D^(-beta), mm/h."""
        if self.gamma is not None:
            return CaineMacroregion(alpha=self.alpha, beta=1.0 - self.gamma)
        assert self.beta is not None  # garantito da _esponente
        return CaineMacroregion(alpha=self.alpha, beta=self.beta)


class Catalogo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fonti: dict[str, Fonte]
    soglie: tuple[Soglia, ...]

    @model_validator(mode="after")
    def _coerente(self) -> Catalogo:
        ignote = {s.fonte for s in self.soglie} - set(self.fonti)
        if ignote:
            raise ValueError(f"fonti non dichiarate: {sorted(ignote)}")
        ripetute = [a for s in self.soglie for a in s.aoi]
        if len(ripetute) != len(set(ripetute)):
            raise ValueError("un'AOI ha due soglie regionali")
        return self

    def per_aoi(self) -> dict[str, Soglia]:
        return {a: s for s in self.soglie for a in s.aoi}


def carica() -> Catalogo:
    testo = files("limen.config").joinpath(_FILE).read_text(encoding="utf-8")
    return Catalogo.model_validate(yaml.safe_load(testo))


def con_soglie_regionali(
    soglie: RegionalThresholds, catalogo: Catalogo | None = None
) -> RegionalThresholds:
    """Le soglie frana con la curva regionale dove c'è, il resto invariato.

    Ogni AOI con una soglia regionale passa a una macroregione sua. Gli altri
    blocchi che leggono la macroregione per nome (``rain_floor``,
    ``flood_forecast``) ricevono sotto il nome nuovo una copia della voce di
    prima: la variante deve cambiare solo la curva di Caine, o il confronto
    misurerebbe due cose insieme.
    """
    per_aoi = (catalogo or carica()).per_aoi()
    if not per_aoi or soglie.macroregion_by_aoi is None:
        return soglie
    caine = dict(soglie.caine.macroregions)
    assegnate = {nome: list(aois) for nome, aois in soglie.macroregion_by_aoi.root.items()}
    origine: dict[str, str] = {}
    for aoi, soglia in sorted(per_aoi.items()):
        nome = f"regionale_{soglia.id}"
        origine[nome] = soglie.macroregion_for(aoi)
        caine[nome] = soglia.in_intensita()
        for aois in assegnate.values():
            if aoi in aois:
                aois.remove(aoi)
        assegnate.setdefault(nome, []).append(aoi)

    update: dict[str, object] = {
        "caine": soglie.caine.model_copy(update={"macroregions": caine}),
        "macroregion_by_aoi": soglie.macroregion_by_aoi.model_validate(assegnate),
    }
    for campo in ("rain_floor", "flood_forecast"):
        blocco = getattr(soglie, campo)
        if blocco is None:
            continue
        voci = dict(blocco.macroregions)
        for nome, prima in origine.items():
            voci[nome] = voci.get(prima, voci["italy_default"])
        update[campo] = blocco.model_copy(update={"macroregions": voci})
    return soglie.model_copy(update=update)
