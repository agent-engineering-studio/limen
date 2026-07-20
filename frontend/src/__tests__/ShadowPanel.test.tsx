import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ShadowPanel, { nationalAgreement } from "../components/ShadowPanel";
import { defaultApiClient } from "../lib/api-client";
import type { ShadowSummaryResponse } from "../types";

const SUMMARY: ShadowSummaryResponse = {
  since: "2026-07-06T13:00:00+00:00",
  aoi_filter: null,
  model_versions: ["ml-v2"],
  total_pairs: 1200,
  regions: [
    { aoi_id: "it-puglia", aoi_name: "Puglia", n: 800, mean_abs_div: 0.4, p95_abs_div: 0.6, max_abs_div: 0.8, correlation: 0.3, class_agreement: 0.5 },
    { aoi_id: "it-basilicata", aoi_name: "Basilicata", n: 200, mean_abs_div: 0.3, p95_abs_div: 0.5, max_abs_div: 0.7, correlation: 0.2, class_agreement: 0.25 },
  ],
  truth_events: [],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("nationalAgreement (pure)", () => {
  it("weights class agreement by cell count", () => {
    // (0.5*800 + 0.25*200) / 1000 = 0.45
    expect(nationalAgreement(SUMMARY.regions)).toBeCloseTo(0.45, 6);
  });
  it("returns null with no observations", () => {
    expect(nationalAgreement([])).toBeNull();
  });
});

describe("ShadowPanel", () => {
  it("shows the non-authoritative disclaimer and the plain-language agreement", async () => {
    vi.spyOn(defaultApiClient, "getShadowSummary").mockResolvedValue(SUMMARY);
    render(<ShadowPanel />);
    expect(screen.getByText(/non decide le allerte/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/stessa classe di rischio/)).toBeInTheDocument(),
    );
    // weighted national agreement 45%, rendered as text (not colour-only)
    expect(screen.getByText("45%")).toBeInTheDocument();
  });

  it("hides itself if the diagnostics endpoint fails (no operator-facing error)", async () => {
    vi.spyOn(defaultApiClient, "getShadowSummary").mockRejectedValue(new Error("boom"));
    const { container } = render(<ShadowPanel />);
    await waitFor(() => expect(container.querySelector(".shadow-panel")).toBeNull());
  });
});
