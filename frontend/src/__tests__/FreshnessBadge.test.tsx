import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import FreshnessBadge, { formatSweepTime } from "../components/FreshnessBadge";
import { defaultApiClient } from "../lib/api-client";

describe("formatSweepTime (pure)", () => {
  it("returns null for absent or unparseable timestamps", () => {
    expect(formatSweepTime(null)).toBeNull();
    expect(formatSweepTime(undefined)).toBeNull();
    expect(formatSweepTime("non-una-data")).toBeNull();
  });

  it("renders HH:MM", () => {
    expect(formatSweepTime("2026-09-09T15:02:14+00:00")).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe("FreshnessBadge", () => {
  it("shows the real end time of the last national sweep", async () => {
    vi.spyOn(defaultApiClient, "getJobStatus").mockResolvedValue({
      sweep: {
        started_at: "2026-09-09T14:59:38+00:00",
        finished_at: "2026-09-09T15:02:14+00:00",
        status: "ok",
        duration_s: 155.8,
      },
      per_aoi: [
        {
          aoi_id: "it-basilicata",
          last_assessed_at: "2026-09-09T15:02:14+00:00",
          duration_s: 155.7,
          status: "ok",
          cells: 10353,
        },
      ],
    });

    render(<FreshnessBadge />);

    await waitFor(() =>
      expect(screen.getByText(/aggiornato alle \d{2}:\d{2}/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/1 regioni/)).toBeInTheDocument();
  });

  it("falls back to the generic label when the status call fails", async () => {
    // Meglio l'etichetta vecchia che un buco nell'header.
    vi.spyOn(defaultApiClient, "getJobStatus").mockRejectedValue(new Error("down"));

    render(<FreshnessBadge />);

    await waitFor(() => expect(screen.getByText(/agg\. 1h/)).toBeInTheDocument());
  });
});
