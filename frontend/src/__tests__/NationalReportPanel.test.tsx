import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { NationalReportResponse } from "../types";

const report: NationalReportResponse = {
  generated_at: "2026-07-06T06:00:00+00:00",
  regions: [
    {
      aoi_id: "it-liguria",
      computed_at: "2026-07-06T05:00:00+00:00",
      cells_scored: 5000,
      max_score: 0.47,
      high_or_above: 2,
      moderate: 300,
    },
    {
      aoi_id: "it-puglia",
      computed_at: "2026-07-06T05:00:00+00:00",
      cells_scored: 19000,
      max_score: 0.3,
      high_or_above: 0,
      moderate: 12,
    },
  ],
  totals: { regions: 2, cells: 24000, high_or_above: 2, moderate: 312 },
  top_cells: [
    {
      cell_id: "it-liguria|1|1",
      aoi_id: "it-liguria",
      score: 0.47,
      level: "Moderate",
      computed_at: "2026-07-06T05:00:00+00:00",
    },
  ],
  ml_top_cells: [
    { cell_id: "it-liguria|2|2", aoi_id: "it-liguria", probability: 0.89, level: "High" },
  ],
  alerts_24h: 7,
  forecast_alerts_24h: 1,
  report_it: "Report Limen — situazione frane Italia.",
};

vi.mock("../lib/api-client", () => ({
  defaultApiClient: {
    getNationalReport: vi.fn(() => Promise.resolve(report)),
    getLegend: vi.fn(() => Promise.resolve({ classes: [], model_version: "x" })),
  },
}));

import NationalReportPanel from "../components/NationalReportPanel";

describe("NationalReportPanel", () => {
  it("shows loading, then the national picture with regions sorted by exposure", async () => {
    render(<NationalReportPanel />);
    expect(screen.getByText(/Caricamento del quadro nazionale/)).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByText(/Report Limen — situazione frane Italia./)).toBeInTheDocument(),
    );

    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("liguria");
    expect(screen.getByText("celle High o superiori")).toBeInTheDocument();
    expect(screen.getByText(/alert previsionali 24h/)).toBeInTheDocument();
    // ML shadow section is labelled as observational, not authoritative.
    expect(screen.getByText(/non guida gli\s+alert/)).toBeInTheDocument();
    expect(screen.getByText("P=0.89")).toBeInTheDocument();
  });
});
