// Il popup della cella per un pericolo che non sia le frane (#62).
//
// Prima il popup leggeva `s/m/e/f/h` dai `factors` e mostrava le etichette
// delle frane: una cella d'incendio dava cinque barre a 0.000 accanto a un
// punteggio non nullo. Con il marchio "solo frane" tolto dalla mappa il
// popup è raggiungibile anche per il fuoco, quindi il difetto sarebbe stato
// visibile al primo click.

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CellPopup from "../components/CellPopup";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import type { CellBreakdownResponse, HazardsResponse } from "../types";

const HAZARDS: HazardsResponse = {
  items: [
    { hazard: "landslide", label_it: "Frana" },
    { hazard: "wildfire", label_it: "Incendio" },
  ],
  default: "wildfire",
};

const WILDFIRE_ROW: CellBreakdownResponse = {
  cell_id: "it-basilicata|1|1",
  hazard_type: "wildfire",
  computed_at: "2026-09-05T12:00:00Z",
  score: 0.44,
  level: "High",
  horizon: "24h",
  pipeline_version: "v1-deterministic",
  factors: {
    fwi_norm: 0.96,
    fuel: 0.35,
    slope: 0.0,
    spinup: false,
    fire_weather: { day: "2026-09-05", fwi: 47.9, chain_days: 46 },
  },
  explanation: {},
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("CellPopup per pericolo", () => {
  it("mostra i componenti dell'incendio, non quelli delle frane", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(HAZARDS);
    vi.spyOn(defaultApiClient, "getCellBreakdown").mockResolvedValue(WILDFIRE_ROW);

    render(
      <HazardProvider>
        <CellPopup cellId="it-basilicata|1|1" />
      </HazardProvider>,
    );

    expect(await screen.findByText("FWI (tempo)")).toBeInTheDocument();
    expect(screen.getByText("Combustibile")).toBeInTheDocument();
    // Le etichette delle frane non devono comparire su una cella d'incendio.
    expect(screen.queryByText("S statico")).toBeNull();
    expect(screen.queryByText("H idrologico")).toBeNull();
    // E i valori sono quelli veri, non cinque zeri.
    expect(screen.getByText("0.960")).toBeInTheDocument();
  });

  it("dichiara l'avviamento della catena invece di nasconderlo", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(HAZARDS);
    vi.spyOn(defaultApiClient, "getCellBreakdown").mockResolvedValue({
      ...WILDFIRE_ROW,
      factors: { ...WILDFIRE_ROW.factors, spinup: true },
    });

    render(
      <HazardProvider>
        <CellPopup cellId="it-basilicata|1|1" />
      </HazardProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText(/in avviamento/i)).toBeInTheDocument(),
    );
  });
});
