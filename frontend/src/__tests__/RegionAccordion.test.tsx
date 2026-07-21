import { describe, expect, it } from "vitest";

import { groupByComune, groupByRegion } from "../components/RegionAccordion";
import type { AlertItem, RiskLevel } from "../types";

function item(
  cell: string,
  aoi: string,
  score: number,
  priority?: number,
): AlertItem {
  return {
    cell_id: cell,
    aoi_id: aoi,
    score,
    level: "Moderate",
    computed_at: "2026-07-07T10:00:00Z",
    lon: 10,
    lat: 44,
    priority: priority ?? score,
  };
}

describe("groupByRegion", () => {
  it("groups by region, ordered by priority (risk x exposure)", () => {
    const groups = groupByRegion([
      // Puglia: score più basso ma priorità alta (abitato) → prima.
      item("it-puglia|1|1", "it-puglia", 0.36, 0.72),
      item("it-liguria|2|2", "it-liguria", 0.44),
      item("it-liguria|3|3", "it-liguria", 0.4),
      item("it-puglia|4|4", "it-puglia", 0.38),
    ]);
    expect(groups.map((g) => g.aoiId)).toEqual(["it-puglia", "it-liguria"]);
    expect(groups[0]?.maxScore).toBe(0.72);
    expect(groups[0]?.cells.map((c) => c.cell_id)).toEqual([
      "it-puglia|1|1",
      "it-puglia|4|4",
    ]);
    expect(groups[1]?.name).toBe("liguria");
  });

  it("handles the empty list", () => {
    expect(groupByRegion([])).toEqual([]);
  });
});

function cell(
  cellId: string,
  place: string | null,
  score: number,
  level: RiskLevel,
  opts: { exposure?: string; priority?: number } = {},
): AlertItem {
  return {
    cell_id: cellId,
    aoi_id: "it-toscana",
    score,
    level,
    computed_at: "2026-07-07T10:00:00Z",
    place,
    exposure: opts.exposure ?? null,
    priority: opts.priority ?? score,
  };
}

describe("groupByComune", () => {
  it("groups cells by comune with min/max, worst level and exposed count", () => {
    const groups = groupByComune([
      cell("it-toscana|1|1", "Firenzuola", 0.36, "Moderate", { exposure: "abitato" }),
      cell("it-toscana|2|2", "Firenzuola", 0.39, "Moderate"),
      cell("it-toscana|3|3", "Bagni di Lucca", 0.35, "Moderate"),
    ]);
    const firenzuola = groups.find((g) => g.place === "Firenzuola");
    expect(firenzuola?.cells.length).toBe(2);
    expect(firenzuola?.minScore).toBeCloseTo(0.36);
    expect(firenzuola?.maxScore).toBeCloseTo(0.39);
    expect(firenzuola?.worstLevel).toBe("Moderate");
    expect(firenzuola?.exposedCount).toBe(1);
  });

  it("orders comuni worst-first by max priority", () => {
    const groups = groupByComune([
      cell("it-toscana|1|1", "Basso", 0.36, "Moderate", { priority: 0.4 }),
      cell("it-toscana|2|2", "Alto", 0.36, "Moderate", { priority: 0.9 }),
    ]);
    expect(groups.map((g) => g.place)).toEqual(["Alto", "Basso"]);
  });

  it("puts cells without a comune in a dedicated bucket", () => {
    const groups = groupByComune([cell("it-toscana|9|9", null, 0.4, "Moderate")]);
    expect(groups[0]?.place).toBeNull();
    expect(groups[0]?.label).toBe("Fuori comune / griglia");
  });
});
