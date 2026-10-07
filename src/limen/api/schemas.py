"""Pydantic v2 request/response schemas for the API layer.

Kept small on purpose — the heavy DTOs (RiskScore, breakdowns,
MonitoringContext, AggregateAssessment) already live in
:mod:`limen.core.models` and are reused verbatim.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from limen.core.models.context import (
    CellRiskRecord,
    RiskAnalysisDTO,
)
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    pool: bool
    cache: bool
    llm_provider: str | None = None


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    pool: bool
    migrations: bool
    detail: str | None = None


class AoiSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    kind: str | None = None


class AoiListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AoiSummary]


class LatestAssessmentResponse(BaseModel):
    """Latest persisted assessment summary for an AOI."""

    model_config = ConfigDict(extra="forbid")

    aoi_id: str
    hazard_type: HazardType = DEFAULT_HAZARD
    horizon: str
    pipeline_version: str
    computed_at: datetime
    cells: list[CellRiskRecord]
    cells_high_or_above: int
    cells_by_level: dict[str, int]
    briefing_it: str | None = None
    #: True quando ``briefing_it`` è il testo deterministico e non quello del
    #: modello narrativo (#78): lo sweep orario non chiama più l'LLM, il
    #: briefing arriva dopo. Senza questo flag la SPA presenterebbe un
    #: segnaposto come se fosse l'analisi.
    briefing_is_fallback: bool = False
    #: Il nome del modello sul gateway che ha scritto ``briefing_it``
    #: (``quality-cloud`` = Claude), e quando. ``None`` quando il testo è
    #: deterministico: la SPA dice chi ha scritto cosa.
    briefing_model: str | None = None
    briefing_written_at: datetime | None = None
    analysis: RiskAnalysisDTO | None = None


class CellBreakdownResponse(BaseModel):
    """Per-cell breakdown of the latest scoring run."""

    model_config = ConfigDict(extra="forbid")

    cell_id: str
    hazard_type: HazardType = DEFAULT_HAZARD
    computed_at: datetime
    score: float
    level: str
    horizon: str
    pipeline_version: str
    factors: dict[str, object]
    explanation: dict[str, object]
    #: Falso quando il segnale dinamico richiesto da questo pericolo non è
    #: arrivato: il punteggio è zero per assenza di misura, non per quiete
    #: (#143). È il posto in cui la domanda nasce — chi clicca una cella
    #: grigia vuole sapere perché.
    measured: bool = True


class AlertItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: str
    aoi_id: str | None = None
    hazard_type: HazardType = DEFAULT_HAZARD
    score: float
    level: str
    computed_at: datetime
    lon: float | None = None
    lat: float | None = None
    # Nome del comune (ISTAT) del centroide — leggibile per non esperti.
    place: str | None = None
    # Tag di esposizione CORINE: "abitato", "vicino abitato",
    # "infrastrutture", "infrastrutture vicine" (comma-separated).
    exposure: str | None = None
    # score x (1 + fattore esposizione) — ordina la lista operativa.
    priority: float | None = None


class AlertsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AlertItem]


class ComuneHazard(BaseModel):
    """Un pericolo dentro la riga di un comune."""

    #: La classe della **cella peggiore**. È la scelta prudente: una soglia
    #: («almeno tre celle sopra Moderato») ridurrebbe il rumore ma
    #: nasconderebbe il versante singolo sopra un abitato, che è il caso per
    #: cui questo sistema esiste. `n_cells` sta accanto a dire quanto è esteso.
    class_: str = Field(alias="class")
    score: float
    #: `punteggio per uno piu l'esposizione`: la stessa priorità che il
    #: dispacciatore degli alert usa per decidere chi viene prima.
    priority: float = 0.0
    n_cells: int
    n_alert: int
    #: Falso quando il segnale dinamico che questo pericolo richiede non è
    #: arrivato: il punteggio è zero per assenza di dato, non per quiete
    #: (#143). Chi lo mostra scrive «non misurato», non «0,00 basso».
    measured: bool = True
    #: Solo per l'alluvione: la pioggia a 72 ore più alta fra le celle del
    #: comune, la soglia sotto cui il ramo pluviale vale zero, e se la portata
    #: dei fiumi c'è. Sotto soglia il punteggio resta 0,00 per settimane, e
    #: questi tre numeri sono ciò che dice quanto manca.
    rain_mm: float | None = None
    rain_threshold_mm: float | None = None
    discharge_known: bool | None = None
    #: Solo per gli allagamenti: quante volte l'anno, nel punto della pioggia
    #: più alta, tre giorni portano almeno quei mm (ERA5 2016-2025). Contesto,
    #: non punteggio: «105 mm» a Trieste capita ogni anno, a Bari mai.
    rain_volte_anno: float | None = None
    #: Solo per l'incendio: l'FWI della cella peggiore e a che percentile cade
    #: fra i giorni dello stesso mese in quel punto (2016-2025). Le classi sono
    #: assolute, come quelle di EFFIS; questo dice se il valore è insolito per
    #: la stagione. ``fwi_percentile`` nullo = climatologia assente.
    fwi: float | None = None
    fwi_month: int | None = None
    fwi_percentile: int | None = None

    model_config = ConfigDict(populate_by_name=True)


class ComuneForecast(BaseModel):
    """Il picco previsto di un pericolo su un comune, e quando arriva."""

    class_: str = Field(alias="class")
    score: float
    #: A quale orizzonte cade il picco: +24, +48 o +72 ore.
    horizon_h: int
    #: Il momento a cui la previsione si riferisce, già composto.
    target_at: str
    priority: float = 0.0

    model_config = ConfigDict(populate_by_name=True)


class AllertaGiorno(BaseModel):
    """Un giorno del bollettino DPC per la zona del comune: 0 nessuna allerta,
    1 gialla, 2 arancione, 3 rossa."""

    valido: date
    livello: int
    idrogeologico: int
    idraulico: int
    temporali: int


class AllertaUfficiale(BaseModel):
    """L'allerta della Protezione Civile per la zona del comune (#155).

    Accanto al nostro numero perché è l'unica che vale: Limen affianca e non
    sostituisce l'allertamento ufficiale.
    """

    zona: str
    emesso: datetime
    oggi: AllertaGiorno | None = None
    domani: AllertaGiorno | None = None


class ComuneRisk(BaseModel):
    istat_code: str
    name: str
    aoi_id: str
    #: Il peggiore fra i pericoli, e quale: ordina la classifica e resta la
    #: forma che i consumatori a pericolo unico leggevano.
    worst_hazard: str
    worst_class: str
    max_score: float
    n_cells: int
    n_alert: int
    counts: dict[str, int]
    exposure_rank: float
    #: Il centroide, per portare la mappa sul comune al clic. Sta nella lista
    #: e non dietro una seconda richiesta: la vista lo ha già calcolato.
    lon: float
    lat: float
    #: Il numero unico: il massimo delle priorità, con l'incremento quando
    #: più di un pericolo è oltre soglia. Non è una somma — sommare i tre
    #: punteggi farebbe passare tre pericoli blandi davanti a un versante
    #: sopra la soglia alta.
    #: `None` quando **nessuno** dei pericoli è stato misurato: è l'unica
    #: risposta vera, e vale più di uno zero che si legge come "tranquillo".
    attention: float | None
    #: I tre indicatori affiancati, sempre tutti: un pericolo a zero mostra
    #: un trattino, e un trattino è una risposta — una colonna che sparisce no.
    hazards: dict[str, ComuneHazard]
    #: Il futuro, per pericolo. Un pericolo assente è **previsto sotto
    #: Moderato**, non ignoto: lo stato previsionale tiene solo le celle sopra
    #: soglia.
    forecast: dict[str, ComuneForecast] = Field(default_factory=dict)
    #: Il bollettino DPC per la zona del comune; `None` se non è ancora stato
    #: importato o il comune non cade in nessuna zona.
    allerta_ufficiale: AllertaUfficiale | None = None
    #: Lo stesso numero di `attention`, sul futuro e con la stessa regola:
    #: se è più alto, il comune sta salendo.
    forecast_attention: float | None = None


class ComuneListResponse(BaseModel):
    comuni: list[ComuneRisk]


class ComuneDetailResponse(BaseModel):
    comune: ComuneRisk
    cells: list[dict[str, object]]


# --- Stato dei job (#75) ---
class SweepStatus(BaseModel):
    """L'ultimo sweep nazionale nel suo insieme."""

    started_at: datetime
    finished_at: datetime | None = None
    status: str
    duration_s: float | None = None


class JobRunStatus(BaseModel):
    """Quando una regione è stata valutata l'ultima volta, e quanto ci è voluto."""

    aoi_id: str
    last_assessed_at: datetime | None = None
    duration_s: float | None = None
    status: str
    cells: int | None = None


class JobStatusResponse(BaseModel):
    sweep: SweepStatus | None = None
    per_aoi: list[JobRunStatus] = Field(default_factory=list)
