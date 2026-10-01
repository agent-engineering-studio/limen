// Il confine del comune scelto dalla colonna. Con la griglia a 1 km, portare
// la mappa sul comune non bastava: dove finisce un comune e comincia il
// vicino non si capiva. Il velo scurisce fuori, il bordo dice dove.

import { describe, expect, it } from "vitest";

import { maschera } from "../components/RiskMap";

const quadrato = (x: number, y: number): [number, number][] => [
  [x, y],
  [x + 0.1, y],
  [x + 0.1, y + 0.1],
  [x, y + 0.1],
  [x, y],
];

describe("maschera del comune", () => {
  it("senza comune scelto non vela niente", () => {
    expect(maschera(null).features).toHaveLength(0);
  });

  it("il comune è un buco nel velo, e il suo confine una linea a parte", () => {
    const fc = maschera({
      type: "Feature",
      properties: { name: "Atrani" },
      geometry: { type: "Polygon", coordinates: [quadrato(14.6, 40.6)] },
    });
    const velo = fc.features.find((f) => f.properties?.["ruolo"] === "maschera");
    const confine = fc.features.find((f) => f.properties?.["ruolo"] === "confine");
    expect(velo?.geometry.type).toBe("Polygon");
    // Due anelli: il mondo, e il comune come buco — è ciò che lascia le sue
    // celle in chiaro mentre tutto intorno si scurisce.
    const anelli = (velo?.geometry as GeoJSON.Polygon).coordinates;
    expect(anelli).toHaveLength(2);
    expect(anelli[1]).toEqual(quadrato(14.6, 40.6));
    expect(confine?.properties?.["name"]).toBe("Atrani");
  });

  it("un comune in più parti ha un buco per parte", () => {
    // Un comune con un'isola o un'exclave: ogni parte deve restare in chiaro.
    const fc = maschera({
      type: "Feature",
      properties: {},
      geometry: {
        type: "MultiPolygon",
        coordinates: [[quadrato(10, 44)], [quadrato(10.5, 44)]],
      },
    });
    const velo = fc.features.find((f) => f.properties?.["ruolo"] === "maschera");
    expect((velo?.geometry as GeoJSON.Polygon).coordinates).toHaveLength(3);
  });
});
