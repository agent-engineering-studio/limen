// «Regioni da monitorare»: l'ordine viene dai numeri, il racconto dall'AI, e i
// colori non si spacciano per allerte.

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RegioniPage, { attacco, regioneDaHash } from "../components/RegioniPage";
import { defaultApiClient } from "../lib/api-client";
import type { RegioneMonitorata } from "../types";

const geom = { type: "Polygon" as const, coordinates: [[[7, 44], [8, 44], [8, 45], [7, 44]]] };

const PIEMONTE: RegioneMonitorata = {
  aoi_id: "it-piemonte",
  nome: "Piemonte",
  lon: 7.9,
  lat: 45.0,
  geom,
  peggiore: { hazard: "flood", classe: "VeryHigh", score: 0.8, previsto: false, rango: 4 },
  pericoli: { flood: { alte: 35, moderate: 76, max_score: 0.8, classe: "VeryHigh" } },
  previsto: { flood: { score: 0.6, classe: "High", target_at: "2026-10-09T02:25:00Z" } },
  comuni: [
    { istat_code: "004110", nome: "Limone Piemonte", hazard: "flood", score: 0.8, celle_alte: 31 },
  ],
  allerta: { oggi: 0, domani: null },
  spiegazioni: {
    flood: {
      testo: "In Piemonte è attesa pioggia molto forte. Le zone più esposte sono nelle valli. Terza frase.",
      modello: "quality-cloud",
      scritta: "2026-10-07T07:19:00Z",
      livello: "VeryHigh",
      analisi: { driver: "pluvial_rain", anomalies: [], attention_window_hours: 24, confidence: 0.7 },
    },
  },
};

const MOLISE: RegioneMonitorata = {
  ...PIEMONTE,
  aoi_id: "it-molise",
  nome: "Molise",
  peggiore: null,
  pericoli: {},
  previsto: {},
  comuni: [],
  allerta: null,
  spiegazioni: {},
};

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  window.location.hash = "";
});

describe("regioneDaHash", () => {
  it("legge la regione dalla sotto-rotta", () => {
    expect(regioneDaHash("#/regioni/it-piemonte")).toBe("it-piemonte");
    expect(regioneDaHash("#/regioni")).toBeNull();
  });
});

describe("attacco", () => {
  it("tiene le prime due frasi", () => {
    expect(attacco("Uno. Due! Tre? Quattro.")).toBe("Uno. Due!");
  });
});

describe("RegioniPage", () => {
  it("mostra le regioni nell'ordine dei numeri, con allerta, comuni e racconto firmato", async () => {
    vi.spyOn(defaultApiClient, "getRegioni").mockResolvedValue({ regioni: [PIEMONTE, MOLISE] });
    const { container } = render(<RegioniPage />);

    expect(await screen.findByText("Piemonte")).toBeTruthy();
    const testo = container.textContent ?? "";
    expect(testo).toContain("Allagamenti · molto alto");
    expect(testo).toContain("Allagamenti: 35 aree in classe alta adesso");
    expect(testo).toContain("oggi nessuna · domani non ancora emessa");
    expect(testo).toContain("Limone Piemonte");
    expect(testo).toContain("Claude (Anthropic)");
    expect(testo).toContain("la pioggia prevista");
    expect(testo).toContain("non l'allerta");
    expect(testo).not.toMatch(/alluvion/i);
    expect(testo).toContain("nessun segnale");
    const nomi = [...container.querySelectorAll(".reg-nome")].map((n) => n.textContent);
    expect(nomi).toEqual(["Piemonte", "Molise"]);
  });

  it("un errore del servizio non lascia la pagina vuota", async () => {
    vi.spyOn(defaultApiClient, "getRegioni").mockRejectedValue(new Error("giù"));
    render(<RegioniPage />);
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
