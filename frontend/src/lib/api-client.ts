// Typed fetch wrapper for the Limen FastAPI backend.
// AbortSignal-aware so callers (React effects) can cancel in-flight
// requests on unmount.

import type {
  ForecastAlertsResponse,
  ForecastSchedule,
  LegendResponse,
  NationalReportResponse,
  AlertsResponse,
  AoiListResponse,
  CellBreakdownResponse,
  CellHistoryResponse,
  CellFwiNormaleResponse,
  CellRainOutlookResponse,
  CellMultiHazardResponse,
  ComuneDetailResponse,
  ComuneGeometry,
  ComuneHistory,
  ComuneListResponse,
  HazardType,
  HazardsResponse,
  JobStatusResponse,
  HealthResponse,
  LatestAssessmentResponse,
  ProvenienzaResponse,
  RainModelsResponse,
  SpiegazioneResponse,
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
      // Il corpo si legge UNA volta sola e poi si prova a interpretarlo.
      // Prima si tentava `json()` e, fallendo, `text()`: ma il primo tentativo
      // consuma comunque il flusso, quindi il secondo lanciava "body stream
      // already read" e quel messaggio finiva in pagina al posto dell'errore
      // vero — con l'API giù, la dashboard diceva tre volte una cosa che non
      // c'entrava nulla.
      const raw = await response.text().catch(() => "");
      let body: unknown = raw || null;
      try {
        body = raw ? JSON.parse(raw) : null;
      } catch {
        // Non era JSON: resta il testo, che è comunque più informativo.
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

  /** La pioggia a 48 ore sulla cella, dalla nostra istanza meteo (#159). */
  getCellRainOutlook(cellId: string, signal?: AbortSignal): Promise<CellRainOutlookResponse> {
    return this.request<CellRainOutlookResponse>(
      `/api/cell/${encodeURIComponent(cellId)}/rain-outlook`,
      {},
      signal,
    );
  }

  /** La pioggia a 72 ore sulla cella secondo cinque modelli meteo. */
  getCellRainModels(cellId: string, signal?: AbortSignal): Promise<RainModelsResponse> {
    return this.request<RainModelsResponse>(
      `/api/cell/${encodeURIComponent(cellId)}/rain-models`,
      {},
      signal,
    );
  }

  /** La spiegazione scritta dall'AI per una regione e un pericolo. */
  getAoiSpiegazione(
    aoiId: string,
    hazard: HazardType,
    signal?: AbortSignal,
  ): Promise<SpiegazioneResponse> {
    return this.request<SpiegazioneResponse>(
      `/api/aoi/${encodeURIComponent(aoiId)}/spiegazione?hazard=${hazard}`,
      {},
      signal,
    );
  }

  /** Chi calcola i numeri, con quale meteo, e cosa fanno oggi ML e AI. */
  getProvenienza(signal?: AbortSignal): Promise<ProvenienzaResponse> {
    return this.request<ProvenienzaResponse>("/api/provenienza", {}, signal);
  }

  /** A che percentile cade un FWI fra i giorni dello stesso mese in quel
   *  punto (climatologia, migrazione 061). */
  getCellFwiNormale(
    cellId: string,
    fwi: number,
    month: number,
    signal?: AbortSignal,
  ): Promise<CellFwiNormaleResponse> {
    return this.request<CellFwiNormaleResponse>(
      `/api/cell/${encodeURIComponent(cellId)}/fwi-normale?fwi=${fwi.toFixed(2)}&month=${month}`,
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

  getTopComuni(
    aoi?: string,
    limit = 50,
    signal?: AbortSignal,
    /** Cerca per nome. Con una ricerca la soglia non si applica: chi cerca il
     *  proprio comune vuole vederlo anche quando è tranquillo, ed è il caso in
     *  cui «nessun pericolo sopra soglia» è la notizia. */
    q?: string,
    /** `forecast` ordina sul picco previsto: trova il comune che oggi è
     *  sotto soglia e domani no. */
    order: "now" | "forecast" = "now",
  ): Promise<ComuneListResponse> {
    const qs = new URLSearchParams();
    if (aoi) qs.set("aoi", aoi);
    qs.set("limit", String(limit));
    if (q) qs.set("q", q);
    if (order !== "now") qs.set("order", order);
    return this.request<ComuneListResponse>(`/api/comuni?${qs.toString()}`, {}, signal);
  }

  /** Quando gira il prossimo calcolo previsionale, e quanto è vecchio l'ultimo. */
  getForecastSchedule(signal?: AbortSignal): Promise<ForecastSchedule> {
    return this.request<ForecastSchedule>("/api/alerts/forecast/schedule", {}, signal);
  }

  /** Il dettaglio di un comune: la riga e le sue celle peggiori. */
  getComune(istatCode: string, signal?: AbortSignal): Promise<ComuneDetailResponse> {
    return this.request<ComuneDetailResponse>(
      `/api/comune/${encodeURIComponent(istatCode)}`,
      {},
      signal,
    );
  }

  /** Il confine del comune in GeoJSON, con `bbox` per inquadrarlo. */
  getComuneGeometry(istatCode: string, signal?: AbortSignal): Promise<ComuneGeometry> {
    return this.request<ComuneGeometry>(
      `/api/comune/${encodeURIComponent(istatCode)}/geometry`,
      {},
      signal,
    );
  }

  getComuneHistory(
    istatCode: string,
    hours = 168,
    signal?: AbortSignal,
  ): Promise<ComuneHistory> {
    return this.request<ComuneHistory>(
      `/api/comune/${encodeURIComponent(istatCode)}/history?hours=${hours}`,
      {},
      signal,
    );
  }

}

export const defaultApiClient = new ApiClient();
