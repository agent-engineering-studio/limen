// La dashboard della sala operativa (#155, fase 2).

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { posizioneIspettore } from "../App";
import HazardSelector from "../components/HazardSelector";
import { filtroSoglia } from "../components/RiskMap";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import type { HazardsResponse } from "../types";

const THREE: HazardsResponse = {
  items: [
    { hazard: "landslide", label_it: "Frana" },
    { hazard: "flood", label_it: "Alluvione" },
    { hazard: "wildfire", label_it: "Incendio" },
  ],
  default: "landslide",
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("solo sopra soglia", () => {
  it("spento non filtra niente", () => {
    expect(filtroSoglia("risk_level", false)).toBeNull();
  });

  it("acceso tiene da Moderato in su, e le aree non misurate", () => {
    // Togliere le grigie insieme alle tranquille le farebbe passare per
    // tranquille: «non so» non è «niente» (#143).
    expect(filtroSoglia("worst_level", true)).toEqual([
      "any",
      ["==", ["get", "measured"], false],
      ["in", ["get", "worst_level"], ["literal", ["Moderate", "High", "VeryHigh"]]],
    ]);
  });
});

describe("ispettore accanto alla cella", () => {
  const mappa = { width: 1000, height: 800 };

  it("si apre a destra quando c'è spazio", () => {
    expect(posizioneIspettore({ x: 300, y: 400 }, mappa)).toEqual({
      left: 328,
      top: 280,
      maxHeight: 504,
    });
  });

  it("passa a sinistra vicino al bordo destro, senza uscire dalla mappa", () => {
    const p = posizioneIspettore({ x: 900, y: 40 }, mappa);
    expect(p.left).toBe(900 - 28 - 360);
    expect(p.top).toBe(16);
  });
});

describe("il quadro nazionale come selettore", () => {
  it("ogni pericolo porta il suo conteggio e la sua classe", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    render(
      <HazardProvider>
        <HazardSelector
          righe={{
            wildfire: { cifra: "9.510", dettaglio: "aree in classe alta", tono: "alert" },
            flood: { cifra: "0", dettaglio: "nessuna area sopra la soglia", tono: "quiet" },
          }}
        />
      </HazardProvider>,
    );
    const incendio = await screen.findByRole("button", { name: "Incendio" });
    expect(incendio.textContent).toContain("9.510");
    expect(incendio.textContent).toContain("alta+");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Alluvione" }).textContent).toContain(
        "nessuna",
      ),
    );
  });
});
