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

// --- auth (mirror src/limen/auth/models.py) ---
export interface AuthUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  email_verified: boolean;
  status: string;
  roles: string[];
}

export interface MeResponse {
  user: AuthUser;
}

export interface MessageResponse {
  message: string;
}

export interface RegisterBody {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
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

export interface CellRiskRecord {
  cell_id: string;
  score: number;
  level: RiskLevel;
  s: number;
  m: number;
  e: number;
  f: number;
  h: number;
  static_terms: StaticBreakdown;
  meteo_terms: MeteoBreakdown;
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
  analysis: RiskAnalysisDTO | null;
}

export interface CellBreakdownResponse {
  cell_id: string;
  computed_at: string;
  score: number;
  level: RiskLevel;
  horizon: string;
  pipeline_version: string;
  factors: Record<string, unknown>;
  explanation: Record<string, unknown>;
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

export interface NationalReportResponse {
  generated_at: string;
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
