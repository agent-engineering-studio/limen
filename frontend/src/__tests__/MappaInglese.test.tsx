// La mappa, la legenda e la timeline in inglese: i testi cambiano con la
// lingua senza ricaricare, e la lettera del pericolo sulle celle segue la
// lingua (F/L/W in inglese, A/F/I in italiano).

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import maplibregl from "maplibre-gl";

import FreshnessBadge from "../components/FreshnessBadge";
import HazardSelector from "../components/HazardSelector";
import LegendPanel from "../components/LegendPanel";
import OverlayControl from "../components/OverlayControl";
import { quantoFa, traQuanto } from "../components/PrevisioneTesta";
import RiskMap from "../components/RiskMap";
import Timeline from "../components/Timeline";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import { useLingua } from "../lib/i18n";
import { fireEvent, render, screen, waitFor } from "../test-utils";
import type { HazardsResponse } from "../types";

const THREE: HazardsResponse = {
  items: [
    { hazard: "landslide", label_it: "Frana" },
    { hazard: "flood", label_it: "Alluvione" },
    { hazard: "wildfire", label_it: "Incendio" },
  ],
  default: "landslide",
};

function Cambia(): JSX.Element {
  const { lingua, imposta } = useLingua();
  return (
    <button type="button" onClick={() => imposta(lingua === "it" ? "en" : "it")}>
      cambia-lingua
    </button>
  );
}

interface Livello {
  id: string;
  layout?: Record<string, unknown>;
}

function letteraLayout(): unknown[] {
  const opzioni = (maplibregl.Map as unknown as { ultimeOpzioni: { style: { layers: Livello[] } } })
    .ultimeOpzioni;
  const livello = opzioni.style.layers.find((l) => l.id === "limen-worst-hazard-lettera");
  return livello?.layout?.["text-field"] as unknown[];
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("legenda in inglese", () => {
  it("nomi delle classi e note in inglese, e torna all'italiano senza ricaricare", () => {
    render(
      <>
        <Cambia />
        <LegendPanel />
      </>,
      { lingua: "en" },
    );
    expect(screen.getByText("Very high")).toBeInTheDocument();
    expect(screen.getByText("Moderate")).toBeInTheDocument();
    expect(screen.getByText("no data")).toBeInTheDocument();
    expect(screen.getByText(/Estimated hazard · not a warning/)).toBeInTheDocument();
    expect(screen.getByText("How the risk is computed")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "cambia-lingua" }));
    expect(screen.getByText("Molto alto")).toBeInTheDocument();
    expect(screen.queryByText("Very high")).toBeNull();
  });
});

describe("selettore e mappa in inglese", () => {
  it("nomi dei pericoli, lettere L/F/W e lettera sulle celle che segue la lingua", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    vi.spyOn(defaultApiClient, "getLegend").mockResolvedValue({ classes: [], model_version: "t" });
    render(
      <HazardProvider>
        <Cambia />
        <HazardSelector />
        <RiskMap tileservUrl="http://tiles.test" />
      </HazardProvider>,
      { lingua: "en" },
    );

    expect(await screen.findByRole("button", { name: "Landslide" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Flood" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All hazards" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const lettera = (nome: string): string | null | undefined =>
      screen.getByRole("button", { name: nome }).querySelector(".hz-lettera")?.textContent;
    expect(lettera("Landslide")).toBe("L");
    expect(lettera("Flood")).toBe("F");
    expect(lettera("Wildfire")).toBe("W");
    await waitFor(() =>
      expect(screen.getByTestId("risk-map")).toHaveAttribute(
        "aria-label",
        "Interactive risk map: all hazards",
      ),
    );
    expect(letteraLayout()).toEqual([
      "match",
      ["get", "worst_hazard"],
      "flood",
      "F",
      "landslide",
      "L",
      "wildfire",
      "W",
      "",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "cambia-lingua" }));
    await waitFor(() =>
      expect(screen.getByTestId("risk-map")).toHaveAttribute(
        "aria-label",
        "Mappa interattiva del rischio: tutti i pericoli",
      ),
    );
    expect(letteraLayout()).toEqual([
      "match",
      ["get", "worst_hazard"],
      "flood",
      "A",
      "landslide",
      "F",
      "wildfire",
      "I",
      "",
    ]);
    expect(screen.getByRole("button", { name: "Alluvione" })).toBeInTheDocument();
  });
});

describe("timeline in inglese", () => {
  it("adesso e le scadenze in inglese", async () => {
    vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(THREE);
    vi.spyOn(defaultApiClient, "getForecastSchedule").mockRejectedValue(new Error("down"));
    render(
      <HazardProvider>
        <Timeline orizzonte={0} onCambia={() => {}} />
      </HazardProvider>,
      { lingua: "en" },
    );
    expect(screen.getByRole("group", { name: "Time shown on the map" })).toBeInTheDocument();
    expect(screen.getByText("Now")).toBeInTheDocument();
    expect(screen.getByText("now")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play through the forecast times" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("not computed")).toHaveLength(3));
  });
});

describe("livelli e testata in inglese", () => {
  it("i livelli di contesto in inglese, con le classi tradotte", () => {
    render(<OverlayControl attivi={new Set(["idraulica"])} onToggle={() => undefined} />, {
      lingua: "en",
    });
    expect(screen.getByRole("group", { name: "Context layers" })).toBeInTheDocument();
    expect(screen.getByText("Landslides")).toBeInTheDocument();
    expect(screen.getByText(/Burnt areas/)).toBeInTheDocument();
    expect(screen.getByText(/from zoom 10/)).toBeInTheDocument();
    expect(screen.getByText(/P3 high/)).toBeInTheDocument();
  });

  it("l'ora dell'ultimo sweep in inglese", async () => {
    vi.spyOn(defaultApiClient, "getJobStatus").mockRejectedValue(new Error("down"));
    render(<FreshnessBadge />, { lingua: "en" });
    await waitFor(() => expect(screen.getByText(/upd\. 1h · 20 regions/)).toBeInTheDocument());
  });

  it("tra quanto e quanto fa, in inglese", () => {
    const adesso = Date.parse("2026-10-12T10:00:00Z");
    expect(traQuanto("2026-10-12T12:14:00Z", adesso, "en")).toBe("in 2 h 14 min");
    expect(traQuanto("2026-10-12T12:14:00Z", adesso)).toBe("tra 2 h 14 min");
    expect(quantoFa("2026-10-12T09:00:00Z", adesso, "en")).toBe("1 hour ago");
    expect(quantoFa("2026-10-12T02:00:00Z", adesso)).toBe("8 ore fa");
  });
});
