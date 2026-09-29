import { describe, expect, it } from "vitest";

import { COLORE_IGNOTO, maplibreColorMatch } from "../lib/risk-colors";

/** L'espressione di classe, dentro il `case` che la protegge. */
function scala(expr: unknown[]): unknown[] {
  return expr[3] as unknown[];
}

describe("maplibreColorMatch", () => {
  it("defaults to the risk_level property (cell/region tiles)", () => {
    const expr = maplibreColorMatch() as unknown[];
    expect(scala(expr)[0]).toBe("match");
    expect(scala(expr)[1]).toEqual(["get", "risk_level"]);
  });

  it("binds to worst_class for the comune rollup layer", () => {
    const expr = maplibreColorMatch("worst_class") as unknown[];
    expect(scala(expr)[1]).toEqual(["get", "worst_class"]);
    // still maps every class to a colour + a neutral fallback at the end
    const inner = scala(expr);
    expect(typeof inner[inner.length - 1]).toBe("string");
  });

  it("una cella non misurata è neutra, non in fondo alla scala", () => {
    // Uno zero per assenza di dato, dipinto nella classe più tranquilla, si
    // legge come una buona notizia: è l'unico posto in cui questo sistema
    // sbaglierebbe in direzione rassicurante (#143).
    const expr = maplibreColorMatch() as unknown[];
    expect(expr[0]).toBe("case");
    expect(expr[1]).toEqual(["==", ["get", "measured"], false]);
    expect(expr[2]).toBe(COLORE_IGNOTO);
  });

  it("le tile senza l'attributo restano colorate", () => {
    // `measured` manca sulle tile scritte prima che la colonna esistesse, e
    // `["==", ["get", "measured"], false]` su un attributo assente è falso:
    // si cade sulla scala, che è il comportamento giusto per «non lo so».
    const expr = maplibreColorMatch() as unknown[];
    expect(expr[1]).toEqual(["==", ["get", "measured"], false]);
    expect(scala(expr)[0]).toBe("match");
  });
});
