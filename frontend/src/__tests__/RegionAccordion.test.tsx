import { describe, expect, it } from "vitest";

import { groupByRegion } from "../components/RegionAccordion";
import type { AlertItem } from "../types";

function item(
  cell: string,
  aoi: string,
  score: number,
  level: AlertItem["level"] = "Moderate",
): AlertItem {
  return {
    cell_id: cell,
    aoi_id: aoi,
    score,
    level,
    computed_at: "2026-07-07T10:00:00Z",
    lon: 10,
    lat: 44,
  };
}

describe("groupByRegion", () => {
  it("groups by region, worst region first, cells by score desc", () => {
    const groups = groupByRegion([
      item("it-puglia|1|1", "it-puglia", 0.36),
      item("it-liguria|2|2", "it-liguria", 0.44, "Moderate"),
      item("it-liguria|3|3", "it-liguria", 0.4),
      item("it-puglia|4|4", "it-puglia", 0.38),
    ]);
    expect(groups.map((g) => g.aoiId)).toEqual(["it-liguria", "it-puglia"]);
    expect(groups[0]?.maxScore).toBe(0.44);
    // Dentro la regione: ordine per indice di griglia (riga, colonna).
    expect(groups[1]?.cells.map((c) => c.cell_id)).toEqual([
      "it-puglia|1|1",
      "it-puglia|4|4",
    ]);
    expect(groups[1]?.name).toBe("puglia");
  });

  it("handles the empty list", () => {
    expect(groupByRegion([])).toEqual([]);
  });
});
