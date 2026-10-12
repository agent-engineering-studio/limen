import { screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import FiguraFrane from "../components/figure/frane";
import { CORSA, SCALA } from "../components/figure/frane/geometry";
import { PESI, livelloDi, statoDi } from "../components/figure/frane/model";
import { render } from "../test-utils";

describe("figura frane: il modello è il motore", () => {
  // `core/scoring/engine.py`, ramo senza sensori, con i pesi di landslide.yaml.
  it("è la somma pesata dei cinque componenti", () => {
    const s = statoDi({ s: 0.7, m: 0.85, e: 0.9, f: 0, h: 0.2 });
    expect(s.punteggio).toBeCloseTo(0.35 * 0.7 + 0.4 * 0.85 + 0.15 * 0.9 + 0.07 * 0 + 0.03 * 0.2, 9);
    expect(s.livello).toBe("High");
  });

  it("i pesi sommano a uno, quindi tutto al massimo è 1", () => {
    expect(Object.values(PESI).reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    expect(statoDi({ s: 1, m: 1, e: 1, f: 1, h: 1 }).punteggio).toBeCloseTo(1, 9);
  });

  it("la corsa di ogni carrello è il suo peso sulla scala", () => {
    expect(CORSA.m).toBeCloseTo(0.4 * SCALA, 9);
    expect(Object.values(CORSA).reduce((a, b) => a + b, 0)).toBeCloseTo(SCALA, 9);
  });

  it("le classi sono quelle delle frane", () => {
    expect([0.14, 0.15, 0.35, 0.55, 0.75].map(livelloDi)).toEqual(["None", "Low", "Moderate", "High", "VeryHigh"]);
  });
});

describe("figura frane: si monta nelle due lingue", () => {
  beforeAll(() => {
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });

  it("in italiano", () => {
    render(<FiguraFrane />, { lingua: "it" });
    expect(screen.getByText("Frane")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /slitta composta/ })).toBeInTheDocument();
    expect(screen.getByText(/→ 0,31 basso/)).toBeInTheDocument();
  });

  it("in inglese", () => {
    render(<FiguraFrane />, { lingua: "en" });
    expect(screen.getByText("Landslides")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /compound slide/ })).toBeInTheDocument();
    expect(screen.getByText(/→ 0.31 low/)).toBeInTheDocument();
  });
});
