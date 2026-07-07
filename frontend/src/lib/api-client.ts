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
  HealthResponse,
  LatestAssessmentResponse,
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

  getLatestRisk(
    aoiId: string,
    signal?: AbortSignal,
  ): Promise<LatestAssessmentResponse> {
    return this.request<LatestAssessmentResponse>(
      `/api/aoi/${encodeURIComponent(aoiId)}/risk/latest`,
      {},
      signal,
    );
  }

  getCellBreakdown(
    cellId: string,
    signal?: AbortSignal,
  ): Promise<CellBreakdownResponse> {
    return this.request<CellBreakdownResponse>(
      `/api/cell/${encodeURIComponent(cellId)}/breakdown`,
      {},
      signal,
    );
  }

  getAlerts(
    opts: { threshold?: string; sinceHours?: number; limit?: number } = {},
    signal?: AbortSignal,
  ): Promise<AlertsResponse> {
    const params = new URLSearchParams();
    if (opts.threshold) params.set("threshold", opts.threshold);
    if (opts.sinceHours != null)
      params.set("since_hours", String(opts.sinceHours));
    if (opts.limit != null) params.set("limit", String(opts.limit));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<AlertsResponse>(`/api/alerts${query}`, {}, signal);
  }

  getForecastAlerts(
    opts: { sinceHours?: number; limit?: number } = {},
    signal?: AbortSignal,
  ): Promise<ForecastAlertsResponse> {
    const params = new URLSearchParams();
    if (opts.sinceHours != null)
      params.set("since_hours", String(opts.sinceHours));
    if (opts.limit != null) params.set("limit", String(opts.limit));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<ForecastAlertsResponse>(
      `/api/alerts/forecast${query}`,
      {},
      signal,
    );
  }

  getLegend(signal?: AbortSignal): Promise<LegendResponse> {
    return this.request<LegendResponse>("/api/legend", {}, signal);
  }

  getNationalReport(signal?: AbortSignal): Promise<NationalReportResponse> {
    return this.request<NationalReportResponse>("/api/report/national", {}, signal);
  }
}

export const defaultApiClient = new ApiClient();
