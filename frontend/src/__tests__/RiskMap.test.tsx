import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RiskMap from "../components/RiskMap";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import type { HazardsResponse } from "../types";

const TWO: HazardsResponse = {
  items: [
    { hazard: "landslide", label_it: "Frana" },
    { hazard: "wildfire", label_it: "Incendio" },
  ],
  default: "wildfire",
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("RiskMap", () => {
  it("renders the map container with the composed tile URL", () => {
    render(
      <RiskMap
        tileservUrl="http://tiles.test"
        tileLayer="public.mv_latest_risk"
      />,
    );
    const node = screen.getByTestId("risk-map");
    expect(node).toBeInTheDocument();
    expect(node.dataset["tileUrl"]).toBe(
      "http://tiles.test/public.mv_latest_risk/{z}/{x}/{y}.pbf",
    );
    expect(node).toHaveAttribute(
      "aria-label",
      "Mappa interattiva del rischio: frane",
    );
  });

  it("passa alla funzione risk_at quando il pericolo non è quello di default", async () => {
    // `v_risk_tiles` è fissata sulle frane in SQL: per ogni altro pericolo la
    // mappa deve cambiare sorgente, o mostrerebbe le frane sotto un'altra
    // etichetta. È il difetto che il marchio "solo frane" copriva in #87.
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(TWO);

    render(
      <HazardProvider>
        <RiskMap tileservUrl="http://tiles.test" />
      </HazardProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("risk-map").dataset["tileUrl"]).toBe(
        "http://tiles.test/public.risk_at/{z}/{x}/{y}.pbf?p_hazard=wildfire",
      ),
    );
    expect(screen.getByTestId("risk-map")).toHaveAttribute(
      "aria-label",
      "Mappa interattiva del rischio: Incendio",
    );
  });
});
