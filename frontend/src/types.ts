// Frontend-facing DTOs. These mirror the FastAPI Pydantic models from
// `src/limen/api/schemas.py` and `src/limen/core/models/`. Keep them in
// sync — the typed `api-client` is the single contract with the backend.

export type RiskLevel = "None" | "Low" | "Moderate" | "High" | "VeryHigh";

export const RISK_LEVELS: readonly RiskLevel[] = [
  "None",
  "Low",
  "Moderate",
  "High",
  "VeryHigh",
] as const;

export interface AoiSummary {
  id: string;
  name: string | null;
  kind: string | null;
}

/** Un pericolo dentro la riga di un comune. */
export interface ComuneHazard {
  /** La classe della cella peggiore del comune per questo pericolo. */
  class: RiskLevel;
  score: number;
  /** `punteggio per uno piu l'esposizione`: la priorità degli alert. */
  priority: number;
  n_cells: number;
  n_alert: number;
  /** Falso quando il segnale dinamico che questo pericolo richiede non è
   *  arrivato: il punteggio è zero per assenza di dato, non per quiete.
   *  Si scrive «non misurato», non «0,00 basso». */
  measured: boolean;
  /** Solo per l'alluvione: pioggia a 72 h più alta fra le celle, la soglia
   *  sotto cui il ramo pluviale vale zero, e se la portata dei fiumi c'è. */
  rain_mm?: number | null;
  rain_threshold_mm?: number | null;
  discharge_known?: boolean | null;
}

export interface ComuneRisk {
  istat_code: string;
  name: string;
  aoi_id: string;
  /** Il peggiore fra i pericoli, e quale. */
  worst_hazard: HazardType;
  worst_class: RiskLevel;
  max_score: number;
  n_cells: number;
  n_alert: number;
  counts: Record<string, number>;
  exposure_rank: number;
  /** Il centroide, per portare la mappa sul comune al clic. */
  lon: number;
  lat: number;
  /** Il numero unico del comune: massimo delle priorità, con l'incremento
   *  quando più di un pericolo è oltre soglia. Non è una somma.
   *  `null` quando nessun pericolo è stato misurato. */
  attention: number | null;
  /** I tre indicatori affiancati: sempre tutti, anche a zero. */
  hazards: Record<string, ComuneHazard>;
  /** Il picco previsto per pericolo. Un pericolo assente è previsto **sotto
   *  Moderato**, non ignoto: lo stato previsionale tiene solo le celle sopra
   *  soglia. */
  forecast: Record<string, ComuneForecast>;
  /** L'attenzione sul futuro, con la stessa regola: più alta ⇒ sta salendo. */
  forecast_attention: number | null;
}

export interface ComuneForecast {
  class: RiskLevel;
  score: number;
  horizon_h: number;
  target_at: string;
  priority: number;
}

/** Una cella scelta sulla mappa o nella colonna. Viveva in
 *  `RegionAccordion`, che non esiste più: la lista per regione e quella per
 *  comune dicevano cose sovrapposte, e ne è rimasta una. */
export interface CellSelection {
  cellId: string;
  lon: number | null;
  lat: number | null;
  priority?: number;
  exposure?: string | null;
  place?: string | null;
}

export interface ComuneListResponse {
  comuni: ComuneRisk[];
}

/** Una cella dentro il dettaglio di un comune. */
export interface ComuneCell {
  cell_id: string;
  hazard: HazardType;
  score: number;
  level: RiskLevel;
  /** Quando è stato calcolato. Un punteggio senza data non si sa se è di
   *  adesso o di ieri, e su un rischio è la differenza fra
   *  un'informazione e un numero. */
  computed_at: string;
  lon: number;
  lat: number;
}

export interface SeriePunto {
  t: string;
  score: number;
  level?: RiskLevel;
}

/** Passato e futuro del comune, una serie per pericolo. I pericoli non
 *  misurati non compaiono: uno zero per assenza di dato disegnerebbe una
 *  discesa a fondo scala che non è mai avvenuta.
 *
 *  `forecast` porta il momento a cui la previsione si riferisce già composto
 *  — chi disegna non deve sapere che `+48h` va sommato all'ora della corsa. */
export interface ComuneHistory {
  observed: Record<string, SeriePunto[]>;
  forecast: Record<string, SeriePunto[]>;
}

export interface ComuneDetailResponse {
  comune: ComuneRisk;
  cells: ComuneCell[];
}

export interface AoiListResponse {
  items: AoiSummary[];
}

export interface StaticBreakdown {
  susc_ispra: number;
  iffi_density: number;
  slope: number;
  pai: number;
  litho_weight: number;
}

export interface MeteoBreakdown {
  caine_excess: number;
  caine_norm: number;
  api_factor: number;
  soil_factor: number;
}

/** Mirror di limen.core.models.hazard.HazardType. */
export type HazardType = "landslide" | "flood" | "wildfire";

/**
 * Cosa il selettore sta mostrando. Non è un `HazardType`: "multi" non è un
 * pericolo, e allargare `HazardType` lo farebbe finire nei parametri `hazard`
 * delle richieste API, dove il backend lo rifiuterebbe.
 */
export type HazardView = HazardType | "multi";

export interface Hazard {
  hazard: HazardType;
  /** Etichetta italiana dal database, non hard-coded qui. */
  label_it: string;
}

/** GET /api/hazards — solo i pericoli che questo deployment sa valutare. */
export interface HazardsResponse {
  items: Hazard[];
  default: HazardType;
}

export interface CellRiskRecord {
  cell_id: string;
  // Sempre presente: il DTO Python lo serializza con un default. I campi
  // hazard a livello di risposta (LatestAssessmentResponse, AlertItem)
  // arrivano quando l'API espone il parametro (issue #86).
  hazard_type: HazardType;
  score: number;
  level: RiskLevel;
  // Il breakdown del pericolo, con la sua forma (#62). Non più S/M/E/F/H
  // appiattiti: i componenti hanno nomi diversi per pericolo, e leggerli per
  // nome qui rimetterebbe la conoscenza delle frane nel client.
  breakdown: Record<string, unknown>;
  monitored?: boolean;
  hard_escalation?: boolean;
}

export interface RiskAnalysisDTO {
  driver: string;
  anomalies: string[];
  attention_window_hours: number;
  confidence: number;
}

export interface LatestAssessmentResponse {
  aoi_id: string;
  horizon: string;
  pipeline_version: string;
  computed_at: string;
  cells: CellRiskRecord[];
  cells_high_or_above: number;
  cells_by_level: Record<string, number>;
  briefing_it: string | null;
  // True quando il testo è il riassunto deterministico e non quello del
  // modello narrativo: lo sweep orario non chiama l'LLM, il briefing arriva
  // con qualche minuto di ritardo (#78).
  briefing_is_fallback: boolean;
  analysis: RiskAnalysisDTO | null;
}

export interface CellBreakdownResponse {
  cell_id: string;
  // Il pericolo della riga letta, che può differire dal selettore per un
  // istante mentre una fetch è in volo.
  hazard_type: HazardType;
  computed_at: string;
  score: number;
  level: RiskLevel;
  horizon: string;
  pipeline_version: string;
  factors: Record<string, unknown>;
  explanation: Record<string, unknown>;
  /** Falso quando il segnale dinamico richiesto non è arrivato: il punteggio
   *  è zero per assenza di misura, non per quiete. È qui che la domanda
   *  nasce — chi clicca una cella grigia vuole sapere perché. */
  measured: boolean;
}

export interface AlertItem {
  cell_id: string;
  aoi_id: string | null;
  score: number;
  level: RiskLevel;
  computed_at: string;
  lon?: number | null;
  lat?: number | null;
  place?: string | null;
  exposure?: string | null;
  priority?: number | null;
}

export interface CellHistoryPoint {
  t: string; // ISO time
  score: number;
  level: RiskLevel;
}

/** Per-cell risk trend: observed past + forecast tail (#41). */
export interface CellHistoryResponse {
  observed: CellHistoryPoint[];
  forecast: CellHistoryPoint[];
}

export interface AlertsResponse {
  items: AlertItem[];
}

export interface HealthResponse {
  status: string;
  pool: boolean;
  cache: boolean;
  llm_provider: string | null;
}

export interface LegendClass {
  level: RiskLevel;
  lo: number;
  hi: number;
  pc_alert: "verde" | "gialla" | "arancione" | "rossa";
}

export interface CaineParams {
  alpha: number;
  beta: number;
}

/** Model card served by /api/legend — the versioned YAML weights/thresholds,
 * so the "Il modello, spiegato" page never hard-codes numbers. */
export interface ModelCard {
  weights: {
    static: number;
    meteo: number;
    seismic: number;
    fire: number;
    hydrology: number;
  };
  meteo_weights: { caine: number; api: number; soil: number };
  caine: { macroregions: Record<string, CaineParams> };
  api: { sigmoid_sigma_mm: number; baseline_fallback_mm: number };
  soil: { sigmoid_center: number; sigmoid_steepness: number };
  seismic: { tau_days: number; pga_threshold_g: number; pga_scale_g: number };
  post_fire: {
    peak_months: number;
    curve_denominator: number;
    window_months_max: number;
  };
}

export interface LegendResponse {
  classes: LegendClass[];
  model_version: string;
  // Optional for backward-compat with older backends / cached responses.
  model?: ModelCard;
}

export interface ReliabilityBin {
  lo: number;
  hi: number;
  predicted_mean: number;
  observed_freq: number;
  count: number;
}

/** ML calibration curve — gated: `sufficient` false until enough real events. */
export interface ReliabilityResponse {
  sufficient: boolean;
  n_positives: number;
  min_positives: number;
  bins: ReliabilityBin[];
}

export interface ShadowRegion {
  aoi_id: string;
  aoi_name: string;
  n: number;
  mean_abs_div: number;
  p95_abs_div: number;
  max_abs_div: number;
  correlation: number | null;
  class_agreement: number;
}

/** Champion (V1) vs shadow challenger (ML) diagnostics — NON-authoritative. */
export interface ShadowSummaryResponse {
  since: string;
  aoi_filter: string | null;
  model_versions: string[];
  total_pairs: number;
  regions: ShadowRegion[];
  truth_events: {
    cell_id: string;
    aoi_id: string;
    aoi_name: string;
    event_time: string;
    champion_score: number | null;
    ml_probability: number | null;
  }[];
}

export interface NationalRegionSummary {
  aoi_id: string;
  computed_at: string;
  cells_scored: number;
  max_score: number;
  high_or_above: number;
  moderate: number;
}

export interface NationalTopCell {
  cell_id: string;
  aoi_id: string;
  score: number;
  level: RiskLevel;
  computed_at: string;
}

export interface NationalMlCell {
  cell_id: string;
  aoi_id: string;
  probability: number;
  level: string;
  place?: string | null;
}

/** Un blocco per pericolo dentro il report nazionale (#58). */
export interface NationalHazardBlock {
  hazard: HazardType;
  label_it: string;
  regions: NationalRegionSummary[];
  totals: {
    regions: number;
    cells: number;
    high_or_above: number;
    moderate: number;
  };
  /** Quando è stato calcolato l'ultimo dato di **questo** pericolo: senza,
   *  la pagina mostrava un solo «aggiornato» per tutti e tre e con uno fermo
   *  da due giorni diceva una cosa falsa. `null` se non c'è nulla. */
  computed_at: string | null;
  top_cells: NationalTopCell[];
}

/** Sezione cascate del report nazionale. Le chiavi mancano quando la regola
 *  corrispondente è disattivata in `cascades.yaml`. */
export interface NationalCascades {
  post_fire_flood?: {
    window_months: number;
    cells: number;
    max_multiplier: number | null;
    months_since_fire_min: number | null;
  };
  joint_rain?: {
    min_level: RiskLevel;
    window_hours: number;
    cells: number;
    top_cells: {
      cell_id: string;
      aoi_id: string;
      score: number;
      hazards: HazardType[];
    }[];
  };
}

export interface CellMultiHazardResponse {
  scope: "cell";
  cell_id: string;
  aoi_id: string;
  worst_hazard: HazardType | null;
  worst_level: RiskLevel | null;
  hazards_at_moderate: HazardType[];
  hazards_at_high: HazardType[];
  per_hazard: {
    hazard: HazardType;
    score: number | null;
    level: RiskLevel | null;
    computed_at: string | null;
  }[];
}

export interface NationalReportResponse {
  generated_at: string;
  hazard: HazardType;
  regions: NationalRegionSummary[];
  totals: {
    regions: number;
    cells: number;
    high_or_above: number;
    moderate: number;
  };
  top_cells: NationalTopCell[];
  ml_top_cells: NationalMlCell[];
  alerts_24h: number;
  forecast_alerts_24h: number;
  hazards: NationalHazardBlock[];
  cascades: NationalCascades;
  report_it: string;
}

export interface ForecastAlertItem {
  aoi_id: string;
  horizon_h: number;
  max_level: string;
  max_score: number;
  cells_alerted: number;
  summary: string | null;
  dispatched_at: string;
}

export interface ForecastAlertsResponse {
  items: ForecastAlertItem[];
}

/** Sono due calcoli diversi, e il timer li mostra tutti e due: l'allerta per
 *  regione ogni `interval_hours`, e la previsione **per cella** — quella del
 *  grafico dei comuni — una volta al giorno, dentro il job notturno. */
export interface ForecastSchedule {
  cells: {
    next_run_at: string | null;
    last_run_by_hazard: Record<string, string>;
  };
  interval_hours: number;
  horizon_hours: number;
  /** `null` = il worker non l'ha pubblicato: «non lo so», non «subito». */
  next_run_at: string | null;
  running_since: string | null;
  last_run: {
    started_at: string;
    finished_at: string | null;
    status: string;
    duration_s: number | null;
  } | null;
}

// --- Stato dei job (mirror src/limen/api/schemas.py, #75) ---
export interface SweepStatus {
  started_at: string;
  finished_at: string | null;
  status: string;
  duration_s: number | null;
}

export interface JobRunStatus {
  aoi_id: string;
  last_assessed_at: string | null;
  duration_s: number | null;
  status: string;
  cells: number | null;
}

export interface JobStatusResponse {
  sweep: SweepStatus | null;
  per_aoi: JobRunStatus[];
}
