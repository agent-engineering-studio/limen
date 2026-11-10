"""Il dato di base di una cella, con la sua fonte (#422).

«Perché questa cella è alta?» Il breakdown dice quale ingrediente l'ha spinta;
qui c'è il dato da cui l'ingrediente nasce — «suolo sigillato al 42 %» — con
la fonte e l'attribuzione accanto, che alcune licenze chiedono. Quali dati e
da dove vengono lo dice il catalogo (`config/dati.yaml`), non questo modulo:
aggiungere un dato al catalogo lo aggiunge anche qui.

Puro: i valori arrivano già letti (`data/repos/dati_di_base_repo.py`). Il
testo è deterministico, così un agente che lo cita non ha niente da calcolare.

Una colonna vuota **non** diventa zero. Può voler dire due cose diverse, e la
lettura le distingue: il dato non è caricato in quella regione («non
caricato»), oppure è caricato ma questa cella ne è fuori — fuori dalle aree
PAI, per esempio, che è un'informazione e non un buco.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from limen.config.catalogo_dati import CatalogoDati, VoceDato
from limen.config.corine import legenda_corine
from limen.core.models.hazard import HazardType


class StatoDato(StrEnum):
    PRESENTE = "presente"
    #: Il dato è caricato nella regione, ma questa cella non ne ha.
    ASSENTE_QUI = "assente_qui"
    #: Il dato non è caricato nella regione della cella.
    NON_CARICATO = "non_caricato"


class DatoDiBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    nome: str
    colonna: str
    stato: StatoDato
    valore: float | str | None
    #: La classe, dove il dato è una classe (P3, il codice CORINE, la litologia).
    classe: str | None = None
    #: Il nome inglese della classe, dove una legenda lo dà (CORINE): la SPA
    #: scrive la lettura inglese da sé, e una legenda non si copia nel frontend.
    nome_classe_en: str | None = None
    lettura: str
    fonte: str
    licenza: str
    attribuzione: str | None = None
    url: str | None = None


#: Classi della pericolosità idraulica ISPRA (Direttiva Alluvioni).
_CLASSI_IDRAULICHE = {"P3": "elevata", "P2": "media", "P1": "bassa"}
#: Classi PAI frana.
_CLASSI_PAI = {
    "P4": "molto elevata",
    "P3": "elevata",
    "P2": "media",
    "P1": "moderata",
    "AA": "area di attenzione",
}

#: Che cosa dire di una cella fuori da un dato caricato, per colonna.
_ASSENTE_QUI = {
    "flood_hazard_norm": "fuori dalle aree a pericolosità idraulica",
    "pai_class_norm": "fuori dalle aree PAI",
}


def _numero(x: float, decimali: int) -> str:
    return f"{x:.{decimali}f}".replace(".", ",")


def _metri(x: float) -> str:
    return f"{_numero(x / 1000, 1)} km" if x >= 1000 else f"{round(x)} m"


def _corine_it(codice: float | str) -> str:
    nome = legenda_corine().nome(str(codice))
    return f"{nome.it} (CORINE {codice})" if nome else f"classe CORINE {codice}"


def _classe_con_nome(nomi: Mapping[str, str]) -> Callable[[float | str, str | None], str]:
    def leggi(_valore: float | str, classe: str | None) -> str:
        if classe is None:
            return "classe non indicata"
        nome = nomi.get(classe)
        return f"{classe} {nome}" if nome else classe

    return leggi


#: Unità di misura e forma, per colonna: presentazione, non calibrazione.
_LETTURE: dict[str, Callable[[float | str, str | None], str]] = {
    "iffi_density_500": lambda v, _c: f"{round(float(v))} frane censite entro 500 m",
    "pai_class_norm": _classe_con_nome(_CLASSI_PAI),
    "flood_hazard_norm": _classe_con_nome(_CLASSI_IDRAULICHE),
    "slope_deg": lambda v, _c: f"pendenza {_numero(float(v), 1)}°",
    "quota_sul_fondo_m": lambda v, _c: f"{round(float(v))} m sopra il fondo valle",
    "landuse_code": lambda v, _c: _corine_it(v),
    "imperviousness_norm": lambda v, _c: f"suolo impermeabilizzato al {round(float(v) * 100)} %",
    "wui_proximity_norm": lambda v, _c: (
        f"vicinanza all'interfaccia urbano-foresta {_numero(float(v), 2)} su 1"
    ),
    "near_urban": lambda v, _c: (
        "case entro circa 2 km" if float(v) else "nessun abitato entro circa 2 km"
    ),
    "distance_to_road_m": lambda v, _c: f"strada più vicina a {_metri(float(v))}",
    "litho_weight": lambda v, c: (
        f"{c} (peso {_numero(float(v), 2)})" if c else f"peso litologico {_numero(float(v), 2)}"
    ),
}


def _leggi(colonna: str, valore: float | str, classe: str | None) -> str:
    formato = _LETTURE.get(colonna)
    if formato is not None:
        return formato(valore, classe)
    return _numero(valore, 2) if isinstance(valore, float) else str(valore)


#: I segnali del giorno, per id di :meth:`HazardBreakdown.segnali`.
NOMI_SEGNALI = {
    "fwi": "catena FWI (meteo degli ultimi giorni)",
    "pioggia": "pioggia prevista e osservata",
    "portata": "portata del fiume (GloFAS)",
}


class Completezza(BaseModel):
    """Su quanti ingredienti poggia il punteggio della cella (#484).

    Un dato caricato di cui la cella è fuori (fuori dalle aree PAI) è un
    ingrediente noto, non mancante: dice qualcosa. Manca solo ciò che non è
    caricato nella regione e il segnale del giorno che non è arrivato. Un
    conteggio con i nomi, non una media pesata: i pesi degli YAML mescolano
    scale diverse, e «mancano pendenza e litologia» si legge da solo.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    presenti: int
    totali: int
    #: Gli id dei dati di base non caricati (`config/dati.yaml`).
    dati_mancanti: list[str]
    #: Gli id dei segnali del giorno non arrivati (:data:`NOMI_SEGNALI`).
    segnali_mancanti: list[str]
    lettura: str


def completezza(dati: list[DatoDiBase], segnali: Mapping[str, bool]) -> Completezza:
    dati_mancanti = [d for d in dati if d.stato is StatoDato.NON_CARICATO]
    segnali_mancanti = [s for s, arrivato in segnali.items() if not arrivato]
    totali = len(dati) + len(segnali)
    presenti = totali - len(dati_mancanti) - len(segnali_mancanti)
    nomi = [d.nome for d in dati_mancanti] + [NOMI_SEGNALI.get(s, s) for s in segnali_mancanti]
    lettura = f"{presenti} ingredienti su {totali}"
    lettura += f"; mancano: {', '.join(nomi)}" if nomi else ", tutti presenti"
    return Completezza(
        presenti=presenti,
        totali=totali,
        dati_mancanti=[d.id for d in dati_mancanti],
        segnali_mancanti=segnali_mancanti,
        lettura=lettura,
    )


def dati_di_base(
    catalogo: CatalogoDati,
    pericolo: HazardType,
    valori: Mapping[str, float | str | None],
    classi: Mapping[str, str | None],
    caricati: Mapping[str, bool],
) -> list[DatoDiBase]:
    """I dati di base di una cella per ``pericolo``, nell'ordine del catalogo.

    ``valori`` e ``classi`` sono per colonna; ``caricati`` dice, per colonna,
    se la regione della cella ha almeno un valore.
    """
    out: list[DatoDiBase] = []
    for voce in catalogo.voci:
        colonna = voce.misura.colonna
        if colonna is None or pericolo not in voce.pericoli:
            continue
        out.append(_dato(voce, colonna, valori.get(colonna), classi.get(colonna), caricati))
    return out


def _dato(
    voce: VoceDato,
    colonna: str,
    valore: float | str | None,
    classe: str | None,
    caricati: Mapping[str, bool],
) -> DatoDiBase:
    if valore is not None:
        stato, lettura = StatoDato.PRESENTE, _leggi(colonna, valore, classe)
    elif caricati.get(colonna, False):
        stato = StatoDato.ASSENTE_QUI
        lettura = _ASSENTE_QUI.get(colonna, "nessun valore per questa cella")
    else:
        stato, lettura = StatoDato.NON_CARICATO, "non caricato"
    nome_en = None
    if colonna == "landuse_code" and valore is not None:
        nome = legenda_corine().nome(str(valore))
        nome_en = nome.en if nome else None
    return DatoDiBase(
        id=voce.id,
        nome=voce.nome,
        colonna=colonna,
        stato=stato,
        valore=valore,
        classe=classe if valore is not None else None,
        nome_classe_en=nome_en,
        lettura=lettura,
        fonte=voce.fonte,
        licenza=voce.licenza,
        attribuzione=voce.attribuzione,
        url=voce.url,
    )


__all__ = ["NOMI_SEGNALI", "Completezza", "DatoDiBase", "StatoDato", "completezza", "dati_di_base"]
