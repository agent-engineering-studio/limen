import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CellTrendSparkline from "../components/CellTrendSparkline";
import { defaultApiClient } from "../lib/api-client";

afterEach(() => vi.restoreAllMocks());

describe("CellTrendSparkline", () => {
  it("draws observed + forecast with an accessible alt", async () => {
    vi.spyOn(defaultApiClient, "getCellHistory").mockResolvedValue({
      observed: [
        { t: "2026-07-20T00:00:00Z", score: 0.3, level: "Moderate" },
        { t: "2026-07-21T00:00:00Z", score: 0.36, level: "Moderate" },
      ],
      forecast: [
        { t: "2026-07-22T00:00:00Z", score: 0.42, level: "Moderate" },
        { t: "2026-07-24T00:00:00Z", score: 0.55, level: "High" },
      ],
    });
    render(<CellTrendSparkline cellId="it-toscana|1|1" />);
    await waitFor(() =>
      expect(screen.getByRole("img", { name: /Andamento rischio/ })).toBeInTheDocument(),
    );
    // alt mentions both observed and forecast counts
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/2 punti osservati/);
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/2 previsti/);
  });

  it("shows an empty-state note when there is no history yet", async () => {
    vi.spyOn(defaultApiClient, "getCellHistory").mockResolvedValue({
      observed: [],
      forecast: [],
    });
    render(<CellTrendSparkline cellId="it-toscana|9|9" />);
    await waitFor(() =>
      expect(screen.getByText(/storico non ancora disponibile/)).toBeInTheDocument(),
    );
  });
});
