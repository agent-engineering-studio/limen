"""Il catalogo dei dati statici (#401): ``limen/config/dati.yaml``.

Un solo posto dice quali dati servono a Limen, a cosa servono, da dove
vengono e come si procurano. Prima lo dicevano a pezzi ``data-status``, gli
script e i commenti del ``.env.example``, e nessuno dei tre in una lingua
leggibile da chi installa.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cache
from importlib import resources
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from limen.core.models.hazard import HazardType

_Testo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Livello(StrEnum):
    #: Senza, il pericolo non distingue un posto dall'altro.
    ESSENZIALE = "essenziale"
    #: Migliora la precisione; la mappa ha senso anche senza.
    CONSIGLIATO = "consigliato"
    #: Serve al modello in ombra o ai backtest, non alla mappa.
    AVANZATO = "avanzato"


class _Rigido(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


#: Finiscono in una query (``copertura_repo``): un refuso nel YAML deve
#: fermare il caricamento del catalogo, non far rispondere 500 a una pagina.
_Identificatore = Annotated[str, StringConstraints(pattern=r"^[a-z_][a-z0-9_]*$")]


class Misura(_Rigido):
    """Come si conta la copertura: celle con un valore, o righe di una tabella."""

    colonna: _Identificatore | None = None
    tabella: _Identificatore | None = None
    #: ``veri`` per le colonne booleane con default ``false``: lì ogni cella ha
    #: un valore anche quando il passo non è mai girato (#473), quindi conta
    #: solo il ``true``.
    conta: Literal["valori", "veri"] = "valori"
    #: ``positivi``: la colonna può essere scritta a zero su un'intera regione
    #: per un errore di caricamento (IFFI in Trentino, #454), e un conteggio dei
    #: valori non la distingue da una caricata bene. Si contano anche i valori
    #: > 0, per segnalare le regioni con una quota anomala (#467).
    informativo: Literal["positivi"] | None = None

    @model_validator(mode="after")
    def _una_sola(self) -> Self:
        if (self.colonna is None) == (self.tabella is None):
            raise ValueError("misura: indicare esattamente uno fra `colonna` e `tabella`")
        return self


class VoceDato(_Rigido):
    id: _Testo
    nome: _Testo
    a_cosa_serve: _Testo
    pericoli: tuple[HazardType, ...] = Field(min_length=1)
    livello: Livello
    misura: Misura
    #: La variabile d'ambiente che abilita il caricamento.
    variabile: str | None = None
    #: L'id della voce da cui il dato si calcola, per i derivati.
    deriva_da: str | None = None
    #: Il comando che procura la sorgente.
    procura_con: str | None = None
    fonte: _Testo
    url: str | None = None
    licenza: _Testo
    attribuzione: str | None = None
    peso_gb: float = Field(ge=0)

    @model_validator(mode="after")
    def _si_sa_come_caricarlo(self) -> Self:
        # Una voce senza variabile né origine lascerebbe chi installa senza il
        # prossimo passo — proprio dove lo cerca.
        if not (self.variabile or self.deriva_da or self.procura_con):
            raise ValueError(f"{self.id}: serve `variabile`, `deriva_da` o `procura_con`")
        return self


class CatalogoDati(_Rigido):
    voci: tuple[VoceDato, ...]

    @model_validator(mode="after")
    def _coerente(self) -> Self:
        ids = [v.id for v in self.voci]
        doppi = {i for i in ids if ids.count(i) > 1}
        if doppi:
            raise ValueError(f"id ripetuti: {sorted(doppi)}")
        orfani = {v.deriva_da for v in self.voci if v.deriva_da and v.deriva_da not in ids}
        if orfani:
            raise ValueError(f"`deriva_da` verso voci inesistenti: {sorted(orfani)}")
        return self

    def voce(self, id_: str) -> VoceDato:
        return next(v for v in self.voci if v.id == id_)

    def essenziali(self, pericolo: HazardType) -> tuple[VoceDato, ...]:
        """I dati senza i quali ``pericolo`` produce una mappa uniforme."""
        return tuple(
            v for v in self.voci if pericolo in v.pericoli and v.livello is Livello.ESSENZIALE
        )


@cache
def carica_catalogo() -> CatalogoDati:
    testo = resources.files("limen.config").joinpath("dati.yaml").read_text(encoding="utf-8")
    return CatalogoDati.model_validate(yaml.safe_load(testo))


__all__ = ["CatalogoDati", "Livello", "Misura", "VoceDato", "carica_catalogo"]
