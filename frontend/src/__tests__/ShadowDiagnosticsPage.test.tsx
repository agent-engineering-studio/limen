import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ShadowDiagnosticsPage, {
  championClassIndex,
  championWouldAlert,
} from "../components/ShadowDiagnosticsPage";
import { defaultApiClient } from "../lib/api-client";
import type { ShadowSummaryResponse } from "../types";

// Clerk role is switchable per test via the hoisted holder.
const h = vi.hoisted(() => ({ role: "ml-ops" as string | undefined }));
vi.mock("@clerk/react", () => ({
  useUser: () => ({
    isLoaded: true,
    user: { publicMetadata: h.role ? { role: h.role } : {} },
  }),
}));

const SUMMARY: ShadowSummaryResponse = {
  since: "2026-07-06T13:00:00+00:00",
  aoi_filter: null,
  model_versions: ["ml-v2"],
  total_pairs: 1000,
  regions: [
    { aoi_id: "it-puglia", aoi_name: "Puglia", n: 700, mean_abs_div: 0.4, p95_abs_div: 0.6, max_abs_div: 0.8, correlation: 0.3, class_agreement: 0.5 },
    { aoi_id: "it-basilicata", aoi_name: "Basilicata", n: 300, mean_abs_div: 0.3, p95_abs_div: 0.5, max_abs_div: 0.7, correlation: 0.2, class_agreement: 0.3 },
  ],
  truth_events: [],
};

afterEach(() => {
  vi.restoreAllMocks();
  h.role = "ml-ops";
});

describe("champion classification (pure)", () => {
  it("maps score to class index and Moderate+ alerting", () => {
    expect(championClassIndex(0.05)).toBe(0);
    expect(championClassIndex(0.4)).toBe(2);
    expect(championWouldAlert(0.34)).toBe(false);
    expect(championWouldAlert(0.36)).toBe(true);
  });
});

describe("ShadowDiagnosticsPage — didactic intro (public)", () => {
  it("always shows the intro explaining the shadow model", () => {
    h.role = undefined; // non ml-ops
    render(<ShadowDiagnosticsPage />);
    expect(
      screen.getByRole("heading", { name: /modello in ombra/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Perché due modelli/)).toBeInTheDocument();
    // live data is NOT shown, but a note explains it's gated
    expect(screen.getByText(/riservati agli operatori con ruolo/)).toBeInTheDocument();
    expect(screen.queryByText(/Accordo complessivo/)).not.toBeInTheDocument();
  });
});

describe("ShadowDiagnosticsPage — live data (ml-ops)", () => {
  it("shows agreement + per-region table with human region names + calibration", async () => {
    h.role = "ml-ops";
    vi.spyOn(defaultApiClient, "getShadowSummary").mockResolvedValue(SUMMARY);
    vi.spyOn(defaultApiClient, "getShadowReliability").mockResolvedValue({
      sufficient: false,
      n_positives: 0,
      min_positives: 20,
      bins: [],
    });
    render(<ShadowDiagnosticsPage />);
    await waitFor(() =>
      expect(screen.getByText(/Accordo complessivo/)).toBeInTheDocument(),
    );
    // human names, not raw it-* ids
    expect(screen.getByText("Basilicata")).toBeInTheDocument();
    expect(screen.queryByText("it-basilicata")).not.toBeInTheDocument();
    // calibration section present, gated to insufficient-data state
    await waitFor(() =>
      expect(screen.getByText(/Dati insufficienti/)).toBeInTheDocument(),
    );
  });
});
