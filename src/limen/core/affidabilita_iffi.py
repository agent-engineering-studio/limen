"""Quanto fidarsi dell'inventario IFFI in un comune o in una regione (#669).

IFFI non è uguale in tutta Italia: alcune regioni datano al giorno un quinto
delle frane e altre quasi nessuna, alcune hanno toccato i record negli ultimi
anni e altre no, e una densità bassa può voler dire geologia oppure frane mai
rilevate. Da ispra-idrogeo 0.13 la tabella dice anche quante frane sono
censite per km² di territorio in pericolosità da frana P3+P4: dove sono poche
rispetto all'Italia, la frase lo dice. ``ispra_idrogeo.reliability`` lo
misura da una tabella inclusa nel pacchetto (nessuna chiamata di rete) e, da
0.14, scrive anche la frase (``Reliability.reading``) e dice se l'inventario è
scarso (``Reliability.thin``, un comune giudicato dalla sua provincia): qui
diventano un modello da mettere **accanto** al contributo IFFI, con i nomi di
Limen.

Solo da mostrare: non cambia il peso di ``iffi_density_500`` né alcun
punteggio. Se e come pesarla va misurato con il backtest, non deciso qui.
"""

from __future__ import annotations

from typing import Literal

from ispra_idrogeo.reliability import NOT_MEASURED_IT, reliability
from pydantic import BaseModel, ConfigDict

Livello = Literal["comuni", "regioni"]

#: Quello che la tabella non sa dire, in italiano: ``reliability.NOT_MEASURED_IT``.
NON_MISURATO: tuple[str, ...] = NOT_MEASURED_IT


class AffidabilitaIffi(BaseModel):
    """L'affidabilità di IFFI in un'area, con le sue parole in italiano e in inglese."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    livello: Livello
    codice: str
    nome: str | None
    frane: int
    densita_km2: float | None
    #: Quote da 0 a 1 delle frane IFFI dell'area; ``None`` se non ce ne sono.
    quota_datate: float | None
    quota_al_giorno: float | None
    frane_al_giorno: int
    quota_modificate_dal_2021: float | None
    frane_iffi_al_giorno_dal_2018: int
    eventi_dal_2018: int
    #: Frane IFFI per km² di territorio in pericolosità da frana P3+P4: qui,
    #: in Italia, e il rapporto fra le due. ``None`` sotto 1 km² in pericolo.
    frane_per_km2_pericolo: float | None = None
    italia_per_km2_pericolo: float | None = None
    rispetto_italia: float | None = None
    #: Le stesse due cifre per la provincia di un comune: è su queste che si
    #: giudica un comune, perché il suo rapporto segue la forma della sua mappa.
    provincia_per_km2_pericolo: float | None = None
    provincia_rispetto_italia: float | None = None
    #: Sotto ``ispra_idrogeo.reliability.THIN`` dell'Italia: una densità IFFI
    #: bassa qui può voler dire «poco rilevato».
    inventario_scarso: bool = False
    lettura: str
    lettura_en: str
    non_misurato: tuple[str, ...] = NON_MISURATO
    #: Il giorno in cui ispra-idrogeo ha costruito la tabella.
    aggiornata_al: str
    fonte: str


def affidabilita_iffi(livello: Livello, codice: str | int | None) -> AffidabilitaIffi | None:
    """L'affidabilità di IFFI nell'area con questo codice ISTAT, o ``None``."""
    if codice is None:
        return None
    try:
        r = reliability(livello, int(codice))
    except (TypeError, ValueError):
        return None
    al_giorno = round((r.day_share or 0.0) * r.landslides)
    return AffidabilitaIffi(
        livello=livello,
        codice=str(codice),
        nome=r.name,
        frane=r.landslides,
        densita_km2=r.density_per_km2,
        quota_datate=r.dated_share,
        quota_al_giorno=r.day_share,
        frane_al_giorno=al_giorno,
        quota_modificate_dal_2021=r.edited_since_2021_share,
        frane_iffi_al_giorno_dal_2018=r.iffi_day_since_2018,
        eventi_dal_2018=r.events_since_2018,
        frane_per_km2_pericolo=r.landslides_per_hazard_km2,
        italia_per_km2_pericolo=r.italy_per_hazard_km2,
        rispetto_italia=r.vs_italy,
        provincia_per_km2_pericolo=r.province_per_hazard_km2,
        provincia_rispetto_italia=r.province_vs_italy,
        inventario_scarso=r.thin,
        lettura=r.reading("it"),
        lettura_en=r.reading("en"),
        aggiornata_al=r.built_on,
        fonte=r.source,
    )


__all__ = ["NON_MISURATO", "AffidabilitaIffi", "affidabilita_iffi"]
