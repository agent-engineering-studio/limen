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

  it("il punto delle migliaia non chiude la frase", () => {
    expect(attacco("Su 23.214 aree nessuna è alta. Poche sono moderate. Fine.")).toBe(
      "Su 23.214 aree nessuna è alta. Poche sono moderate.",
    );
  });
});

describe("RegioniPage", () => {
  it("mostra le regioni nell'ordine dei numeri, con allerta, comuni e racconto firmato", async () => {
    vi.spyOn(defaultApiClient, "getRegioni").mockResolvedValue({ regioni: [PIEMONTE, MOLISE] });
    const { container } = render(<RegioniPage />);

    expect(await screen.findByText("Piemonte")).toBeTruthy();
    const testo = container.textContent ?? "";
    expect(testo).toContain("Allagamenti · molto alto");
    expect(testo).toContain("Allagamenti 35 aree in classe alta adesso");
    expect(testo).toContain("oggi nessuna · domani non ancora emessa");
    expect(testo).toContain("Limone Piemonte");
    // Il modello non si nomina nei racconti: lo dice una volta la testata.
    for (const racconto of container.querySelectorAll(".reg-ai")) {
      expect(racconto.textContent).not.toContain("Claude");
    }
    expect(testo).toContain("Racconti scritti con Claude, il modello di Anthropic");
    expect(testo).toContain("la pioggia prevista");
    expect(testo).toContain("non l'allerta");
    expect(testo).not.toMatch(/alluvion/i);
    expect(testo).toContain("nessun segnale");
    const pdf = screen.getByRole("link", { name: "Scarica il rapporto (PDF)" });
    expect(pdf.getAttribute("href")).toMatch(/\/api\/regioni\/rapporto\.pdf$/);
    const una = screen.getAllByRole("link", { name: "PDF di questa regione" })[0];
    expect(una?.getAttribute("href")).toContain("rapporto.pdf?aoi=it-piemonte");
    const nomi = [...container.querySelectorAll(".reg-nome")].map((n) => n.textContent);
    expect(nomi).toEqual(["Piemonte", "Molise"]);
  });

  it("un errore del servizio non lascia la pagina vuota", async () => {
    vi.spyOn(defaultApiClient, "getRegioni").mockRejectedValue(new Error("giù"));
    render(<RegioniPage />);
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

describe("RegioniPage e la mappa", () => {
  it("non tocca i filtri prima che lo stile sia caricato", async () => {
    // Il 7 ottobre 2026 la pagina era nera: `setFilter` prima del caricamento
    // dello stile lancia in MapLibre, e l'eccezione smontava l'applicazione.
    const maplibre = (await import("maplibre-gl")).default;
    const spia = vi
      .spyOn(maplibre.Map.prototype, "setFilter")
      .mockImplementation(() => {
        throw new Error("Style is not done loading.");
      });
    window.location.hash = "#/regioni/it-piemonte";
    vi.spyOn(defaultApiClient, "getRegioni").mockResolvedValue({ regioni: [PIEMONTE, MOLISE] });
    render(<RegioniPage />);
    expect(await screen.findByText("Piemonte")).toBeTruthy();
    expect(spia).not.toHaveBeenCalled();
  });
});
