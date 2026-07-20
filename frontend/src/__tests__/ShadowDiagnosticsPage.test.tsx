import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ShadowDiagnosticsPage, {
  championClassIndex,
  championWouldAlert,
} from "../components/ShadowDiagnosticsPage";
import { defaultApiClient } from "../lib/api-client";
import type { ShadowSummaryResponse } from "../types";

const BASE: ShadowSummaryResponse = {
  since: "2026-07-06T13:00:00+00:00",
  aoi_filter: null,
  model_versions: ["ml-v2"],
  total_pairs: 1000,
  regions: [
    { aoi_id: "puglia", n: 700, mean_abs_div: 0.4, p95_abs_div: 0.6, max_abs_div: 0.8, correlation: 0.3, class_agreement: 0.5 },
    { aoi_id: "basilicata", n: 300, mean_abs_div: 0.3, p95_abs_div: 0.5, max_abs_div: 0.7, correlation: 0.2, class_agreement: 0.3 },
  ],
  truth_events: [],
};

afterEach(() => vi.restoreAllMocks());

describe("champion classification (pure)", () => {
  it("maps score to class index and Moderate+ alerting", () => {
    expect(championClassIndex(0.05)).toBe(0); // None
    expect(championClassIndex(0.4)).toBe(2); // Moderate
    expect(championClassIndex(0.8)).toBe(4); // VeryHigh
    expect(championWouldAlert(0.34)).toBe(false); // Low
    expect(championWouldAlert(0.36)).toBe(true); // Moderate
  });
});

describe("ShadowDiagnosticsPage", () => {
  it("shows agreement + per-region table + empty recall state", async () => {
    vi.spyOn(defaultApiClient, "getShadowSummary").mockResolvedValue(BASE);
    render(<ShadowDiagnosticsPage />);
    expect(screen.getByText(/Nessuna promozione avviene da qui/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/concorda col sistema ufficiale/)).toBeInTheDocument(),
    );
    // no events → honest empty recall state
    expect(screen.getByText(/Nessun evento di frana datato/)).toBeInTheDocument();
    // per-region table lists both regions
    expect(screen.getByText("puglia")).toBeInTheDocument();
    expect(screen.getByText("basilicata")).toBeInTheDocument();
  });

  it("counts events the official system would have caught", async () => {
    vi.spyOn(defaultApiClient, "getShadowSummary").mockResolvedValue({
      ...BASE,
      truth_events: [
        { cell_id: "c1", aoi_id: "puglia", event_time: "2026-07-10T02:00:00+00:00", champion_score: 0.62, ml_probability: 0.4 },
        { cell_id: "c2", aoi_id: "puglia", event_time: "2026-07-11T05:00:00+00:00", champion_score: 0.2, ml_probability: 0.1 },
      ],
    });
    render(<ShadowDiagnosticsPage />);
    // 1 of 2 events was Moderate+ for the champion (0.62 yes, 0.20 no)
    await waitFor(() =>
      expect(screen.getByText(/ne aveva già/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Alto (0.62)")).toBeInTheDocument();
  });
});
