import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api-client", () => ({
  defaultApiClient: {
    getNationalReport: vi.fn(() =>
      Promise.resolve({
        generated_at: "2026-07-06T06:00:00+00:00",
        regions: [],
        totals: { regions: 20, cells: 312550, high_or_above: 0, moderate: 100 },
        top_cells: [],
        ml_top_cells: [],
        alerts_24h: 12,
        forecast_alerts_24h: 0,
        report_it: "x",
      }),
    ),
  },
}));

import HomePage from "../components/HomePage";

describe("HomePage", () => {
  it("renders the pitch, the dashboard CTA and live stats", async () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Rischio frana e inondazione/,
    );
    // Nessun login: la dashboard è pubblica (#71).
    expect(screen.getByText("Apri la dashboard")).toBeInTheDocument();
    expect(screen.getByText("Cos'è Limen")).toBeInTheDocument();
    // Static fallback first, live numbers after the fetch resolves.
    await waitFor(() =>
      expect(screen.getByText("312.550")).toBeInTheDocument(),
    );
    expect(screen.getByText("celle monitorate")).toBeInTheDocument();
    // License attributions are a legal requirement, not decoration.
    expect(screen.getAllByText(/ISPRA IdroGEO/).length).toBeGreaterThan(0);
  });
});
