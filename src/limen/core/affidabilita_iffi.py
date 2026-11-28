"""Quanto fidarsi dell'inventario IFFI in un comune o in una regione (#669).

IFFI non è uguale in tutta Italia: alcune regioni datano al giorno un quinto
delle frane e altre quasi nessuna, alcune hanno toccato i record negli ultimi
anni e altre no, e una densità bassa può voler dire geologia oppure frane mai
rilevate. Da ispra-idrogeo 0.13 la tabella dice anche quante frane sono
censite per km² di territorio in pericolosità da frana P3+P4: dove sono poche
rispetto all'Italia, la frase lo dice. ``ispra_idrogeo.reliability`` lo
misura da una tabella inclusa nel pacchetto (nessuna chiamata di rete); qui
diventa una frase da mettere **accanto** al contributo IFFI.

Solo da mostrare: non cambia il peso di ``iffi_density_500`` né alcun
punteggio. Se e come pesarla va misurato con il backtest, non deciso qui.
"""

from __future__ import annotations

from typing import Literal

from ispra_idrogeo.reliability import THIN, Reliability, reliability
from pydantic import BaseModel, ConfigDict

Livello = Literal["comuni", "regioni"]

#: Quello che la tabella non sa dire, in italiano (``reliability.NOT_MEASURED``).
#: La terza voce dice in più la regola di ``ispra_idrogeo.dated.twins`` (0.13).
NON_MISURATO = (
    "la precisione delle posizioni IFFI: ogni record dice «esatta»",
    "quanto l'inventario sia completo: non c'è un riferimento con cui confrontarlo",
    "se un evento e un record IFFI sono la stessa frana: c'è solo una regola "
    "(stesso giorno, entro 1 km), non una verifica",
    "l'anno in cui ogni regione ha rilevato le sue frane: ISPRA non lo pubblica",
)


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


def _intero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _quota(q: float) -> str:
    if 0 < q < 0.001:
        return "meno dello 0,1 %"
    return f"{q * 100:.1f}".replace(".", ",") + " %"


def _quota_en(q: float) -> str:
    return "less than 0.1%" if 0 < q < 0.001 else f"{q * 100:.1f}%"


def _numero(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _giudicata(r: Reliability, livello: Livello) -> tuple[float | None, float | None]:
    """Le frane per km² in pericolo e il rapporto con l'Italia su cui si giudica l'area."""
    if livello == "comuni":
        return r.province_per_hazard_km2, r.province_vs_italy
    return r.landslides_per_hazard_km2, r.vs_italy


def _scarso(r: Reliability, livello: Livello) -> bool:
    rapporto = _giudicata(r, livello)[1]
    return rapporto is not None and rapporto < THIN


def _poche(r: Reliability, livello: Livello) -> tuple[str, str]:
    """La frase sull'inventario scarso, con lo spazio davanti; vuota se non lo è."""
    valore = _giudicata(r, livello)[0]
    if not _scarso(r, livello) or valore is None or r.italy_per_hazard_km2 is None:
        return "", ""
    dove = "in questa provincia" if livello == "comuni" else "in questa regione"
    dove_en = "in this province" if livello == "comuni" else "in this region"
    return (
        f" Poche frane censite per il pericolo mappato {dove}: {_numero(valore)} per km² di "
        f"territorio in pericolosità da frana P3+P4, contro {_numero(r.italy_per_hazard_km2)} "
        "in Italia. Una densità bassa qui può voler dire che si è rilevato poco, non che le "
        "frane siano poche.",
        f" Few IFFI landslides for the hazard mapped {dove_en}: {valore:g} per km² of land in "
        f"landslide hazard P3+P4, against {r.italy_per_hazard_km2:g} in Italy. A low density "
        "here may mean that little was surveyed, not that few landslides happen.",
    )


def _letture(r: Reliability, al_giorno: int, livello: Livello) -> tuple[str, str]:
    dove = "In questo comune" if livello == "comuni" else "In questa regione"
    dove_en = "In this municipality" if livello == "comuni" else "In this region"
    limite = "Completezza dell'inventario e precisione delle posizioni non sono misurate."
    limite_en = "How complete the inventory is and how accurate its positions are is not measured."
    poche, poche_en = _poche(r, livello)
    if r.landslides == 0:
        return (
            f"{dove} IFFI non censisce frane: può voler dire che non ce ne sono "
            f"o che nessuno le ha rilevate.{poche} {limite}",
            f"{dove_en} IFFI maps no landslides: there may be none, or none were surveyed."
            f"{poche_en} {limite_en}",
        )
    frane = "frana" if r.landslides == 1 else "frane"
    giorno = _quota(r.day_share or 0.0)
    modificate = _quota(r.edited_since_2021_share or 0.0)
    datate = (
        "nessuna datata al giorno"
        if al_giorno == 0
        else f"{_intero(al_giorno)} datate al giorno ({giorno})"
    )
    datate_en = (
        "none dated to the day"
        if al_giorno == 0
        else f"{al_giorno:,} dated to the day ({_quota_en(r.day_share or 0.0)})"
    )
    it = (
        f"{dove} IFFI censisce {_intero(r.landslides)} {frane}: {datate}; "
        f"{modificate} dei record modificati dal 2021.{poche} {limite}"
    )
    en = (
        f"{dove_en} IFFI maps {r.landslides:,} landslides: {datate_en}; "
        f"{_quota_en(r.edited_since_2021_share or 0.0)} of the records edited since 2021."
        f"{poche_en} {limite_en}"
    )
    return it, en


def affidabilita_iffi(livello: Livello, codice: str | int | None) -> AffidabilitaIffi | None:
    """L'affidabilità di IFFI nell'area con questo codice ISTAT, o ``None``."""
    if codice is None:
        return None
    try:
        r = reliability(livello, int(codice))
    except (TypeError, ValueError):
        return None
    al_giorno = round((r.day_share or 0.0) * r.landslides)
    it, en = _letture(r, al_giorno, livello)
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
        inventario_scarso=_scarso(r, livello),
        lettura=it,
        lettura_en=en,
        aggiornata_al=r.built_on,
        fonte=r.source,
    )


__all__ = ["NON_MISURATO", "AffidabilitaIffi", "affidabilita_iffi"]
