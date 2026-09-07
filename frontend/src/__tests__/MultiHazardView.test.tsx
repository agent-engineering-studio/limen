// Vista "tutti i pericoli" (#58).
//
// Tre proprietà, tutte già rotte una volta durante l'implementazione:
// la sorgente dei tile deve cambiare (una vista per pericolo mostrerebbe un
// pericolo solo), il `source-layer` deve restare quello che `ST_AsMVT`
// scrive dentro il tile, e passare alla vista d'insieme non deve perdere il
// pericolo scelto — i pannelli fissati continuano a leggerlo.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HazardSelector from "../components/HazardSelector";
import LegendPanel from "../components/LegendPanel";
import RiskMap from "../components/RiskMap";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import { maplibreMultiHazardColorMatch } from "../lib/risk-colors";
import type { HazardsResponse, LegendResponse } from "../types";

const ONE: HazardsResponse = {
  items: [{ hazard: "landslide", label_it: "Frana" }],
  default: "landslide",
};

const THREE: HazardsResponse = {
  items: [
    { hazard: "landslide", label_it: "Frana" },
    { hazard: "flood", label_it: "Alluvione" },
    { hazard: "wildfire", label_it: "Incendio" },
  ],
  default: "landslide",
};

const EMPTY_LEGEND: LegendResponse = { classes: [], model_version: "test" };

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("selettore", () => {
  it("offre «tutti» solo con più di un pericolo", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(ONE);
    render(
      <HazardProvider>
        <HazardSelector />
      </HazardProvider>,
    );
    await waitFor(() => expect(defaultApiClient.getHazards).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "tutti" })).toBeNull();
  });
});

describe("mappa in vista d'insieme", () => {
  it("cambia sorgente dei tile e non passa più il parametro hazard", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);

    render(
      <HazardProvider>
        <HazardSelector />
        <RiskMap tileservUrl="http://tiles.test" />
      </HazardProvider>,
    );

    const tutti = await screen.findByRole("button", { name: "tutti" });
    fireEvent.click(tutti);

    await waitFor(() =>
      expect(screen.getByTestId("risk-map").dataset["tileUrl"]).toBe(
        "http://tiles.test/public.multi_hazard_at/{z}/{x}/{y}.pbf",
      ),
    );
    expect(screen.getByTestId("risk-map")).toHaveAttribute(
      "aria-label",
      "Mappa interattiva del rischio: tutti i pericoli",
    );
  });

  it("non perde il pericolo scelto: i pannelli fissati continuano a leggerlo", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    const legend = vi
      .spyOn(defaultApiClient, "getLegend")
      .mockResolvedValue(EMPTY_LEGEND);

    render(
      <HazardProvider>
        <HazardSelector />
        <LegendPanel />
      </HazardProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Incendio" }));
    await waitFor(() =>
      expect(legend).toHaveBeenCalledWith(expect.anything(), "wildfire"),
    );

    fireEvent.click(screen.getByRole("button", { name: "tutti" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();

    // Tornando indietro si riparte dall'incendio, non dal default — e senza
    // una nuova richiesta: il pericolo scelto non è mai cambiato, quindi i
    // cutoff in mano sono già i suoi.
    fireEvent.click(screen.getByRole("button", { name: "Incendio" }));
    await waitFor(() => expect(screen.queryByRole("table")).toBeNull());
    expect(screen.getByRole("button", { name: "Incendio" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // L'ultima richiesta di cutoff resta quella dell'incendio: il default lo
    // si è chiesto al primo montaggio, non dopo il passaggio dalla vista
    // d'insieme.
    expect(legend.mock.calls.at(-1)?.[1]).toBe("wildfire");
  });
});

describe("legenda in vista d'insieme", () => {
  it("mostra una colonna per pericolo invece dei cutoff numerici", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    vi.spyOn(defaultApiClient, "getLegend").mockResolvedValue(EMPTY_LEGEND);

    render(
      <HazardProvider>
        <HazardSelector />
        <LegendPanel />
      </HazardProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "tutti" }));

    const matrice = await screen.findByRole("table");
    expect(matrice).toBeInTheDocument();
    for (const label of ["Frana", "Alluvione", "Incendio"]) {
      expect(
        screen.getByRole("columnheader", { name: label }),
      ).toBeInTheDocument();
    }
    // Ogni combinazione classe×pericolo è nominata per i lettori di schermo:
    // il colore da solo non è un'informazione accessibile.
    expect(screen.getByText("Incendio: Molto alto")).toBeInTheDocument();
  });
});

describe("colore della vista d'insieme", () => {
  it("annida la classe dentro il pericolo, così la tinta dice quale", () => {
    const expr = maplibreMultiHazardColorMatch() as unknown[];
    expect(expr[0]).toBe("match");
    expect(expr[1]).toEqual(["get", "worst_hazard"]);
    expect(expr[2]).toBe("wildfire");
    // Il ramo dell'incendio è a sua volta un match sulla classe, non un
    // colore fisso: senza, l'intensità sparirebbe dalla mappa d'insieme.
    const incendio = expr[3] as unknown[];
    expect(incendio[0]).toBe("match");
    expect(incendio[1]).toEqual(["get", "worst_level"]);
    expect(incendio).toContain("#993404");
  });
});
