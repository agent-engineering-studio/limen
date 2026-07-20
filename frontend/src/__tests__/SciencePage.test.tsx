import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ScienceContent,
  caineThreshold,
  postFireBell,
  seismicDecay,
  sigmoid,
} from "../components/SciencePage";
import type { ModelCard } from "../types";

const MODEL: ModelCard = {
  weights: { static: 0.35, meteo: 0.4, seismic: 0.15, fire: 0.07, hydrology: 0.03 },
  meteo_weights: { caine: 0.45, api: 0.3, soil: 0.25 },
  caine: { macroregions: { italy_default: { alpha: 7.19, beta: 0.568 } } },
  api: { sigmoid_sigma_mm: 60, baseline_fallback_mm: 80 },
  soil: { sigmoid_center: 0.3, sigmoid_steepness: 12 },
  seismic: { tau_days: 2, pga_threshold_g: 0.05, pga_scale_g: 0.05 },
  post_fire: { peak_months: 6, curve_denominator: 50, window_months_max: 24 },
};

const PC = {
  None: "verde",
  Low: "verde",
  Moderate: "gialla",
  High: "arancione",
  VeryHigh: "rossa",
};

describe("ScienceContent", () => {
  it("covers the components, aggregation, V1-vs-V2 and the five classes", () => {
    render(<ScienceContent model={MODEL} pcByLevel={PC} version="limen-deterministic-v1" />);
    expect(screen.getByText("Il modello, spiegato")).toBeInTheDocument();
    // component codes S/M/E/F/H(/K) — appear at least in the block badges
    for (const code of ["S", "M", "E", "F", "H", "K"]) {
      expect(screen.getAllByText(code).length).toBeGreaterThan(0);
    }
    // weights rendered from the model card, not hard-coded
    expect(screen.getAllByText("40%").length).toBeGreaterThan(0); // meteo weight
    // the honesty section
    expect(screen.getByText(/NON una probabilità/)).toBeInTheDocument();
    // five class labels with ranges + PC mapping
    expect(screen.getByText("Molto alto")).toBeInTheDocument();
    expect(screen.getByText("0.75–1.00")).toBeInTheDocument();
    expect(screen.getByText(/allerta rossa/)).toBeInTheDocument();
    // spatial-block CV + SHAP + glossary (each appears in body and glossary/note)
    expect(screen.getAllByText(/blocchi spaziali/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("SHAP").length).toBeGreaterThan(0);
  });

  it("includes the plain-language ML theory and external references", () => {
    render(<ScienceContent model={MODEL} pcByLevel={PC} version="v1" />);
    expect(screen.getByText(/come funziona l'algoritmo/i)).toBeInTheDocument();
    expect(screen.getByText(/Gradient boosting/)).toBeInTheDocument();
    expect(screen.getByText(/Per approfondire il ML/)).toBeInTheDocument();
    // real references are linked out
    const shap = screen.getByText(/il paper di SHAP/);
    expect(shap.closest("li")?.querySelector("a")).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/1705.07874",
    );
  });
});

describe("physical-model math (pure)", () => {
  it("Caine threshold falls with duration", () => {
    expect(caineThreshold(7.19, 0.568, 1)).toBeGreaterThan(
      caineThreshold(7.19, 0.568, 24),
    );
  });
  it("sigmoid is 0.5 at the centre and monotone", () => {
    expect(sigmoid(0)).toBeCloseTo(0.5, 6);
    expect(sigmoid(3)).toBeGreaterThan(sigmoid(-3));
  });
  it("seismic effect decays toward zero", () => {
    expect(seismicDecay(2, 0)).toBeCloseTo(1, 6);
    expect(seismicDecay(2, 7)).toBeLessThan(0.05);
  });
  it("post-fire bell peaks near peak_months and is zero outside the window", () => {
    expect(postFireBell(6, 50, 24, 6)).toBeCloseTo(1, 6);
    expect(postFireBell(6, 50, 24, 30)).toBe(0);
  });
});
