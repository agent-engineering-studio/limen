// La dashboard della sala operativa (#155, fase 2).

import { fireEvent, render, screen, waitFor } from "../test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { posizioneIspettore } from "../App";
import HazardSelector from "../components/HazardSelector";
import RiskMap, { filtroSoglia } from "../components/RiskMap";
import Timeline from "../components/Timeline";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import type { ForecastSchedule, HazardsResponse } from "../types";

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

/** Una corsa notturna di frane e incendio, `ore` fa. */
function corsa(ore: number): ForecastSchedule {
  const t = new Date(Date.now() - ore * 3600_000).toISOString();
  return {
    cells: { next_run_at: null, last_run_by_hazard: { landslide: t, wildfire: t } },
    interval_hours: 6,
    horizon_hours: 72,
    next_run_at: null,
    running_since: null,
    last_run: null,
  } as unknown as ForecastSchedule;
}

describe("la previsione sulla mappa", () => {
  it("legge la tile della previsione all'orizzonte scelto, per tutti i pericoli", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    render(
      <HazardProvider>
        <RiskMap tileservUrl="http://tiles.test" orizzonte={48} />
      </HazardProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("risk-map").dataset["tileUrl"]).toBe(
        "http://tiles.test/public.forecast_at/{z}/{x}/{y}.pbf?p_horizon=48",
      ),
    );
  });

  it("con un pericolo scelto lo passa alla tile", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    render(
      <HazardProvider>
        <HazardSelector />
        <RiskMap tileservUrl="http://tiles.test" orizzonte={24} />
      </HazardProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Incendio" }));
    await waitFor(() =>
      expect(screen.getByTestId("risk-map").dataset["tileUrl"]).toBe(
        "http://tiles.test/public.forecast_at/{z}/{x}/{y}.pbf?p_horizon=24&p_hazard=wildfire",
      ),
    );
  });

  it("una scadenza già passata lo dice, invece di presentarsi come futuro", async () => {
    // La corsa notturna saltata: +24 h da una corsa di 30 ore fa è ieri.
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    vi.spyOn(defaultApiClient, "getForecastSchedule").mockResolvedValue(corsa(30));
    render(
      <HazardProvider>
        <Timeline orizzonte={0} onCambia={() => {}} />
      </HazardProvider>,
    );
    const piu24 = await screen.findByRole("button", { name: /\+24 h/ });
    await waitFor(() => expect(piu24.textContent).toContain("passato"));
    expect(screen.getByRole("button", { name: /\+48 h/ }).textContent).not.toContain("passato");
  });

  it("un pericolo senza corsa previsionale non ha futuro da scegliere", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    vi.spyOn(defaultApiClient, "getForecastSchedule").mockResolvedValue(corsa(2));
    const scelte: number[] = [];
    render(
      <HazardProvider>
        <HazardSelector />
        <Timeline orizzonte={48} onCambia={(h) => scelte.push(h)} />
      </HazardProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Alluvione" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /\+48 h/ })).toBeDisabled());
    // E si torna all'adesso: «+48 h» su una mappa vuota sembrerebbe quiete.
    await waitFor(() => expect(scelte).toContain(0));
  });
});
