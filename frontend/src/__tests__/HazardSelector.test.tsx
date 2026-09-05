// Selettore del pericolo (issue #87).
//
// La proprietà che tiene la Fase 1 invisibile all'utente: con un solo
// pericolo disponibile **non deve esserci alcun controllo nel DOM**. Con due,
// cambiare selezione deve rifare le richieste con il parametro giusto.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HazardSelector from "../components/HazardSelector";
import LandslideOnlyBadge from "../components/LandslideOnlyBadge";
import LegendPanel from "../components/LegendPanel";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import type { HazardsResponse, LegendResponse } from "../types";

const ONE: HazardsResponse = {
  items: [{ hazard: "landslide", label_it: "Frana" }],
  default: "landslide",
};

const TWO: HazardsResponse = {
  items: [
    { hazard: "landslide", label_it: "Frana" },
    { hazard: "flood", label_it: "Alluvione" },
  ],
  default: "landslide",
};

const EMPTY_LEGEND: LegendResponse = { classes: [], model_version: "test" };

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("HazardSelector", () => {
  it("non rende nulla con un solo pericolo disponibile", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(ONE);

    const { container } = render(
      <HazardProvider>
        <HazardSelector />
      </HazardProvider>,
    );

    await waitFor(() => expect(defaultApiClient.getHazards).toHaveBeenCalled());
    expect(screen.queryByRole("group", { name: /pericolo/i })).toBeNull();
    expect(container.querySelector(".hazard-selector")).toBeNull();
  });

  it("non rende nulla se il backend è irraggiungibile", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockRejectedValue(new Error("down"));

    const { container } = render(
      <HazardProvider>
        <HazardSelector />
      </HazardProvider>,
    );

    await waitFor(() => expect(defaultApiClient.getHazards).toHaveBeenCalled());
    expect(container.querySelector(".hazard-selector")).toBeNull();
  });

  it("rende un pulsante per pericolo quando ce n'è più di uno", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(TWO);

    render(
      <HazardProvider>
        <HazardSelector />
      </HazardProvider>,
    );

    const frana = await screen.findByRole("button", { name: "Frana" });
    expect(frana).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Alluvione" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("cambiare selezione rifà la richiesta con il pericolo scelto", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(TWO);
    const legend = vi
      .spyOn(defaultApiClient, "getLegend")
      .mockResolvedValue(EMPTY_LEGEND);

    render(
      <HazardProvider>
        <HazardSelector />
        <LegendPanel />
      </HazardProvider>,
    );

    // Prima richiesta: il default deciso dal backend.
    await waitFor(() =>
      expect(legend).toHaveBeenCalledWith(expect.anything(), "landslide"),
    );

    fireEvent.click(await screen.findByRole("button", { name: "Alluvione" }));

    await waitFor(() =>
      expect(legend).toHaveBeenCalledWith(expect.anything(), "flood"),
    );
  });
});

describe("pannelli fissati sul pericolo di default", () => {
  it("il marchio compare solo quando il pericolo scelto non è quello mostrato", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(TWO);

    render(
      <HazardProvider>
        <HazardSelector />
        <LandslideOnlyBadge />
      </HazardProvider>,
    );

    // Sul default il pannello non mente, quindi nessun marchio.
    const alluvione = await screen.findByRole("button", { name: "Alluvione" });
    expect(screen.queryByText(/solo frana/i)).toBeNull();

    fireEvent.click(alluvione);
    expect(await screen.findByText(/solo frana/i)).toBeInTheDocument();
  });
});

describe("LegendPanel", () => {
  it("mostra i cutoff del backend, non quelli statici delle frane", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(ONE);
    vi.spyOn(defaultApiClient, "getLegend").mockResolvedValue({
      classes: [
        { level: "VeryHigh", lo: 0.71, hi: 1, pc_alert: "rossa" },
        { level: "High", lo: 0.52, hi: 0.71, pc_alert: "arancione" },
        { level: "Moderate", lo: 0.33, hi: 0.52, pc_alert: "gialla" },
        { level: "Low", lo: 0.14, hi: 0.33, pc_alert: "verde" },
        { level: "None", lo: 0, hi: 0.14, pc_alert: "verde" },
      ],
      model_version: "test",
    });

    render(
      <HazardProvider>
        <LegendPanel />
      </HazardProvider>,
    );

    // 0.52-0.71 è del backend; il valore statico di High sarebbe un altro.
    expect(await screen.findByText("0.52-0.71")).toBeInTheDocument();
  });
});

describe("palette per pericolo", () => {
  it("l'incendio non riusa i colori delle frane", async () => {
    // Con due pericoli sulla stessa mappa il colore è l'unico indizio
    // immediato di cosa si sta guardando: due rampe rosso-arancio identiche
    // si confondono. Classi ed etichette restano le stesse, cambia la tinta.
    const { riskClassesFor } = await import("../lib/risk-colors");
    const frane = riskClassesFor("landslide");
    const incendio = riskClassesFor("wildfire");

    expect(incendio.map((c) => c.level)).toEqual(frane.map((c) => c.level));
    expect(incendio.map((c) => c.label)).toEqual(frane.map((c) => c.label));
    expect(incendio.every((c, i) => c.color !== frane[i]?.color)).toBe(true);
  });
});

describe("palette dei tre pericoli", () => {
  it("nessuna rampa è riusata da due pericoli", async () => {
    // Con tre pericoli sulla stessa mappa il colore è l'unico indizio
    // immediato di cosa si sta guardando. L'acqua è l'unica delle tre che non
    // si legge come "caldo", ed è giusto che sia l'unica fredda.
    const { riskClassesFor } = await import("../lib/risk-colors");
    const rampe = (["landslide", "wildfire", "flood"] as const).map((h) =>
      riskClassesFor(h).map((c) => c.color).join(","),
    );
    expect(new Set(rampe).size).toBe(3);

    // Classi ed etichette restano identiche: cambia solo la tinta.
    const livelli = riskClassesFor("flood").map((c) => c.level);
    expect(livelli).toEqual(riskClassesFor("landslide").map((c) => c.level));
  });
});
