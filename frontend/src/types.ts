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
