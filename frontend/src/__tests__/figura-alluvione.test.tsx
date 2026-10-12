import { screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import FiguraAlluvione from "../components/figure/alluvione";
import { livelloDi, statoDi } from "../components/figure/alluvione/model";
import { render } from "../test-utils";

describe("figura alluvione: il modello è il motore", () => {
  // Rifà a mano `core/scoring/flood/engine.py` con i numeri di flood.yaml
  // (threshold_mm 40, saturation_mm 120, normal_ratio 1,6, saturation_ratio 10).
  it("la pioggia mediana delle celle allagate porta in classe alta", () => {
    const s = statoDi({ pioggiaMm: 86.2, rapporto: 0, suscettibilita: 0.8 });
    expect(s.pluviale).toBeCloseTo((86.2 - 40) / (120 - 40), 9);
    expect(s.punteggio).toBeCloseTo(0.8 * ((86.2 - 40) / 80), 9);
    expect(s.livello).toBe("High");
    expect(s.ramo).toBe("pioggia");
  });

  it("il giorno di piena mediano porta in classe alta dal ramo fiume", () => {
    const s = statoDi({ pioggiaMm: 20, rapporto: 6.39, suscettibilita: 0.8 });
    expect(s.fluviale).toBeCloseTo((6.39 - 1.6) / (10 - 1.6), 9);
    expect(s.ramo).toBe("fiume");
    expect(s.livello).toBe("High");
  });

  it("è un massimo, non una somma", () => {
    const entrambi = statoDi({ pioggiaMm: 80, rapporto: 5.8, suscettibilita: 1 });
    expect(entrambi.pluviale).toBeCloseTo(0.5, 9);
    expect(entrambi.fluviale).toBeCloseTo(0.5, 9);
    expect(entrambi.punteggio).toBeCloseTo(0.5, 9);
  });

  it("sotto il floor della suscettibilità la paratoia è chiusa", () => {
    const s = statoDi({ pioggiaMm: 160, rapporto: 12, suscettibilita: 0.04 });
    expect(s.chiusa).toBe(true);
    expect(s.punteggio).toBe(0);
  });

  it("le classi sono quelle dell'allagamento", () => {
    expect([0.09, 0.1, 0.25, 0.45, 0.7].map(livelloDi)).toEqual(["None", "Low", "Moderate", "High", "VeryHigh"]);
  });
});

describe("figura alluvione: si monta nelle due lingue", () => {
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
    render(<FiguraAlluvione />, { lingua: "it" });
    expect(screen.getByText("Allagamento")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /valvola a navetta/ })).toBeInTheDocument();
    expect(screen.getByText(/96 mm · 1,3× · s 0,80 → 0,56 alto/)).toBeInTheDocument();
  });

  it("in inglese", () => {
    render(<FiguraAlluvione />, { lingua: "en" });
    expect(screen.getByText("Flooding")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /shuttle valve/ })).toBeInTheDocument();
    expect(screen.getByText(/96 mm · 1.3× · s 0.80 → 0.56 high/)).toBeInTheDocument();
  });
});
