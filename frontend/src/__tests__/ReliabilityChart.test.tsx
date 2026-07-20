import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ReliabilityChart from "../components/ReliabilityChart";
import type { ReliabilityResponse } from "../types";

describe("ReliabilityChart", () => {
  it("shows an explicit insufficient-data state when gated", () => {
    const data: ReliabilityResponse = {
      sufficient: false,
      n_positives: 0,
      min_positives: 20,
      bins: [],
    };
    render(<ReliabilityChart data={data} />);
    expect(screen.getByText(/Dati insufficienti/)).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    // no chart when insufficient
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders the calibration chart with the diagonal when sufficient", () => {
    const data: ReliabilityResponse = {
      sufficient: true,
      n_positives: 40,
      min_positives: 20,
      bins: [
        { lo: 0.0, hi: 0.1, predicted_mean: 0.05, observed_freq: 0.04, count: 100 },
        { lo: 0.5, hi: 0.6, predicted_mean: 0.55, observed_freq: 0.6, count: 30 },
      ],
    };
    render(<ReliabilityChart data={data} />);
    expect(screen.getByRole("img", { name: /calibrazione/i })).toBeInTheDocument();
    // one point per bin (each has a <title> tooltip)
    expect(screen.getByText(/previsto 5% → osservato 4%/)).toBeInTheDocument();
    expect(screen.getByText(/previsto 55% → osservato 60%/)).toBeInTheDocument();
  });
});
