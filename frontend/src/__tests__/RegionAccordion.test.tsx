import { describe, expect, it } from "vitest";

import { groupByRegion } from "../components/RegionAccordion";
import type { AlertItem } from "../types";

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
