import { describe, expect, it } from "vitest";

import { maplibreColorMatch } from "../lib/risk-colors";

describe("maplibreColorMatch", () => {
  it("defaults to the risk_level property (cell/region tiles)", () => {
    const expr = maplibreColorMatch() as unknown[];
    expect(expr[0]).toBe("match");
    expect(expr[1]).toEqual(["get", "risk_level"]);
  });

  it("binds to worst_class for the comune rollup layer", () => {
    const expr = maplibreColorMatch("worst_class") as unknown[];
    expect(expr[1]).toEqual(["get", "worst_class"]);
    // still maps every class to a colour + a neutral fallback at the end
    expect(typeof expr[expr.length - 1]).toBe("string");
  });
});
