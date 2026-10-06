// La dashboard della sala operativa (#155, fase 2).

import { fireEvent, render, screen, waitFor } from "../test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { posizioneIspettore } from "../App";
import HazardSelector from "../components/HazardSelector";
import RiskMap, { filtroSoglia } from "../components/RiskMap";
import Timeline from "../components/Timeline";
import { letturaIncendio } from "../components/CellPopup";
import { RigaAllerta } from "../components/ComuniBoard";
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

describe("come leggere il numero dell'incendio", () => {
  it("dice che è un pericolo potenziale, con la classe EFFIS e la siccità", () => {
    // I valori di Montegiordano del 2 ottobre 2026: un ottobre mite ma
    // secco, che EFFIS metteva nella stessa classe.
    const righe = letturaIncendio({
      fire_weather: { fwi: 36.23, dc: 543.1, day: "2026-10-02" },
    });
    expect(righe).not.toBeNull();
    const testo = (righe ?? []).join(" ");
    expect(testo).toContain("potenziale");
    expect(testo).toContain("non la probabilità che parta");
    expect(testo).toContain("High (21,3–38)");
    expect(testo).toContain("DC 543");
    expect(testo).toContain("piogge abbondanti");
  });

  it("con la climatologia dice dove cade rispetto al solito del mese", () => {
    const righe = letturaIncendio(
      { fire_weather: { fwi: 36.23, dc: 543.1, day: "2026-10-02" } },
      { percentile: 97, mediana: 6.6, p90: 15.2, giorni: 310, anni: [2016, 2025] },
    );
    const testo = (righe ?? []).join(" ");
    expect(testo).toContain("Molto sopra il solito per ottobre");
    expect(testo).toContain("97 %");
    expect(testo).toContain("2016–2025");
  });

  it("senza meteo nel breakdown non inventa niente", () => {
    expect(letturaIncendio({ fwi_norm: 0.5 })).toBeNull();
  });
});

describe("l'allerta ufficiale accanto al nostro numero", () => {
  const nessuna = { valido: "2026-10-06", livello: 0, idrogeologico: 0, idraulico: 0, temporali: 0 };

  it("quando Limen segnala più del bollettino lo dice, e dice quale vale", () => {
    // Trieste, 6 ottobre 2026: 0,75 per alluvione sulle 72 ore, nessuna
    // allerta nel bollettino per oggi e domani.
    const { container } = render(
      <RigaAllerta
        allerta={{ zona: "Bacino di Levante / Carso", emesso: "2026-10-05T14:17:00+02:00", oggi: nessuna, domani: nessuna }}
        picco={{ hazard: "flood", score: 0.75, level: "VeryHigh" }}
      />,
    );
    expect(container.textContent).toContain("Allerta ufficiale");
    expect(container.textContent).toContain("oggi nessuna");
    expect(container.textContent).toContain("vale il bollettino");
  });

  it("dice i rischi per cui è in allerta", () => {
    const { container } = render(
      <RigaAllerta
        allerta={{
          zona: "Zona B",
          emesso: "2026-10-05T14:17:00+02:00",
          oggi: { ...nessuna, livello: 1, temporali: 1 },
          domani: nessuna,
        }}
        picco={{ hazard: "landslide", score: 0.4, level: "Moderate" }}
      />,
    );
    expect(container.textContent).toContain("oggi gialla (temporali)");
    expect(container.textContent).not.toContain("vale il bollettino");
  });
});
