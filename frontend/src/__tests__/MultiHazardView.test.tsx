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
import {
  HAZARD_HUE,
  maplibreMultiHazardColorMatch,
  maplibreWorstHazardLine,
} from "../lib/risk-colors";
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
    // La matrice 5×3 non c'è più: il segno della vista d'insieme è la
    // legenda a scala sola.
    expect(await screen.findByText(/Il colore dice/)).toBeInTheDocument();

    // Tornando indietro si riparte dall'incendio, non dal default — e senza
    // una nuova richiesta: il pericolo scelto non è mai cambiato, quindi i
    // cutoff in mano sono già i suoi.
    fireEvent.click(screen.getByRole("button", { name: "Incendio" }));
    await waitFor(() => expect(screen.queryByText(/Il colore dice/)).toBeNull());
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
  it("mostra una scala sola e la chiave dei bordi, non una matrice", async () => {
    // La matrice 5×3 chiedeva quindici caselle per leggere una cella,
    // perché il colore portava due informazioni. Ora ne porta una.
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    vi.spyOn(defaultApiClient, "getLegend").mockResolvedValue(EMPTY_LEGEND);

    render(
      <HazardProvider>
        <HazardSelector />
        <LegendPanel />
      </HazardProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "tutti" }));

    expect(await screen.findByText(/Il colore dice/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    // I tre pericoli restano nominati nella chiave: senza, il bordo
    // colorato sarebbe un colore senza significato dichiarato. Si cerca
    // dentro la chiave perché il selettore li nomina a sua volta.
    const chiave = document.querySelector(".legend-hazards");
    expect(chiave).not.toBeNull();
    for (const label of ["Frana", "Alluvione", "Incendio"]) {
      expect(chiave?.textContent).toContain(label);
    }
    // E le soglie numeriche restano dichiarate come quelle delle frane,
    // invece di lasciar credere che valgano per tutti e tre.
    expect(screen.getByText(/quelle qui sopra sono delle frane/i)).toBeInTheDocument();
  });
});

describe("colore della vista d'insieme", () => {
  it("il colore dice quanto, non quale: una scala sola sulla classe", () => {
    const expr = maplibreMultiHazardColorMatch() as unknown[];
    // La scala sta dentro il `case` che protegge le celle non misurate
    // (#143): la guardia viene prima, la classe resta quella di sempre.
    expect(expr[0]).toBe("case");
    const scala = expr[3] as unknown[];
    expect(scala[0]).toBe("match");
    // Sulla classe, non sul pericolo: è tutto il cambiamento.
    expect(scala[1]).toEqual(["get", "worst_level"]);
    expect(scala).toContain("VeryHigh");
  });

  it("quale pericolo lo dice il bordo, con una tinta per pericolo", () => {
    const expr = maplibreWorstHazardLine() as unknown[];
    expect(expr[0]).toBe("match");
    expect(expr[1]).toEqual(["get", "worst_hazard"]);
    expect(expr).toContain("wildfire");
    expect(expr).toContain(HAZARD_HUE.wildfire);
    // L'ultimo elemento è il ripiego: una cella senza pericolo dichiarato
    // non deve restare senza bordo e sembrare non selezionata.
    expect(typeof expr[expr.length - 1]).toBe("string");
  });
});
