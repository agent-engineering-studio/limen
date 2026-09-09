// Typed fetch wrapper for the Limen FastAPI backend.
// AbortSignal-aware so callers (React effects) can cancel in-flight
// requests on unmount.

import type {
  ForecastAlertsResponse,
  LegendResponse,
  NationalReportResponse,
  AlertsResponse,
  AoiListResponse,
  CellBreakdownResponse,
  CellHistoryResponse,
  CellMultiHazardResponse,
  ComuneListResponse,
  HazardType,
  HazardsResponse,
  JobStatusResponse,
  HealthResponse,
  LatestAssessmentResponse,
  ReliabilityResponse,
  ShadowSummaryResponse,
} from "../types";

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.body = body;
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions = {}) {
    const fallback =
      typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL
        ? (import.meta.env.VITE_API_URL as string)
        : "http://localhost:8080";
    this.baseUrl = (options.baseUrl ?? fallback).replace(/\/+$/, "");
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
    signal?: AbortSignal,
  ): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      signal: signal ?? init.signal ?? null,
      headers: {
        Accept: "application/json",
        ...(init.headers ?? {}),
      },
    });
    if (!response.ok) {
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        body = await response.text();
      }
      throw new ApiClientError(
        `request to ${path} failed with ${response.status}`,
        response.status,
        body,
      );
    }
    return (await response.json()) as T;
  }

  health(signal?: AbortSignal): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health", {}, signal);
  }

  getAoiList(signal?: AbortSignal): Promise<AoiListResponse> {
    return this.request<AoiListResponse>("/api/aoi", {}, signal);
  }

  /**
   * `hazard` è l'ultimo parametro di ogni metodo, non il primo: le firme
   * esistenti restano valide e ometterlo produce la stessa richiesta di
   * prima, che è il contratto di retrocompatibilità di #86.
   */
  private static hazardQuery(hazard?: HazardType, prefix = "?"): string {
    return hazard ? `${prefix}hazard=${encodeURIComponent(hazard)}` : "";
  }

  getHazards(signal?: AbortSignal): Promise<HazardsResponse> {
    return this.request<HazardsResponse>("/api/hazards", {}, signal);
  }

  getLatestRisk(
    aoiId: string,
    signal?: AbortSignal,
    hazard?: HazardType,
  ): Promise<LatestAssessmentResponse> {
    return this.request<LatestAssessmentResponse>(
      `/api/aoi/${encodeURIComponent(aoiId)}/risk/latest` +
        ApiClient.hazardQuery(hazard),
      {},
      signal,
    );
  }

  getCellBreakdown(
    cellId: string,
    signal?: AbortSignal,
    hazard?: HazardType,
  ): Promise<CellBreakdownResponse> {
    return this.request<CellBreakdownResponse>(
      `/api/cell/${encodeURIComponent(cellId)}/breakdown` +
        ApiClient.hazardQuery(hazard),
      {},
      signal,
    );
  }

  getCellHistory(
    cellId: string,
    hours = 72,
    signal?: AbortSignal,
    hazard?: HazardType,
  ): Promise<CellHistoryResponse> {
    return this.request<CellHistoryResponse>(
      `/api/cell/${encodeURIComponent(cellId)}/history?hours=${hours}` +
        ApiClient.hazardQuery(hazard, "&"),
      {},
      signal,
    );
  }

  getAlerts(
    opts: {
      threshold?: string;
      sinceHours?: number;
      limit?: number;
      hazard?: HazardType;
    } = {},
    signal?: AbortSignal,
  ): Promise<AlertsResponse> {
    const params = new URLSearchParams();
    if (opts.threshold) params.set("threshold", opts.threshold);
    if (opts.sinceHours != null)
      params.set("since_hours", String(opts.sinceHours));
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.hazard) params.set("hazard", opts.hazard);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<AlertsResponse>(`/api/alerts${query}`, {}, signal);
  }

  getForecastAlerts(
    opts: { sinceHours?: number; limit?: number; hazard?: HazardType } = {},
    signal?: AbortSignal,
  ): Promise<ForecastAlertsResponse> {
    const params = new URLSearchParams();
    if (opts.sinceHours != null)
      params.set("since_hours", String(opts.sinceHours));
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.hazard) params.set("hazard", opts.hazard);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<ForecastAlertsResponse>(
      `/api/alerts/forecast${query}`,
      {},
      signal,
    );
  }

  getLegend(signal?: AbortSignal, hazard?: HazardType): Promise<LegendResponse> {
    return this.request<LegendResponse>(
      `/api/legend${ApiClient.hazardQuery(hazard)}`,
      {},
      signal,
    );
  }

  getNationalReport(
    signal?: AbortSignal,
    hazard?: HazardType,
  ): Promise<NationalReportResponse> {
    return this.request<NationalReportResponse>(
      `/api/report/national${ApiClient.hazardQuery(hazard)}`,
      {},
      signal,
    );
  }

  getCellMultiHazard(
    cellId: string,
    signal?: AbortSignal,
  ): Promise<CellMultiHazardResponse> {
    return this.request<CellMultiHazardResponse>(
      `/api/cell/${encodeURIComponent(cellId)}/multi-hazard`,
      {},
      signal,
    );
  }

  getShadowSummary(signal?: AbortSignal): Promise<ShadowSummaryResponse> {
    return this.request<ShadowSummaryResponse>("/api/shadow/summary", {}, signal);
  }

  getShadowReliability(signal?: AbortSignal): Promise<ReliabilityResponse> {
    return this.request<ReliabilityResponse>("/api/shadow/reliability", {}, signal);
  }

  getJobStatus(signal?: AbortSignal): Promise<JobStatusResponse> {
    return this.request<JobStatusResponse>("/api/status/jobs", {}, signal);
  }

  getTopComuni(aoi?: string, limit = 50, signal?: AbortSignal): Promise<ComuneListResponse> {
    const qs = new URLSearchParams();
    if (aoi) qs.set("aoi", aoi);
    qs.set("limit", String(limit));
    return this.request<ComuneListResponse>(`/api/comuni?${qs.toString()}`, {}, signal);
  }

}

export const defaultApiClient = new ApiClient();
