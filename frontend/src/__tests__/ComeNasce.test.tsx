// «Come nasce questo numero»: l'ispettore deve dire chi ha fatto cosa —
// formula, meteo, ML, AI — e non attribuire all'AI quello che non ha scritto.

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ComeNasce, { modelloLeggibile, RigaProvenienza } from "../components/ComeNasce";
import { defaultApiClient } from "../lib/api-client";
import type { ProvenienzaResponse, RainModelsResponse, SpiegazioneResponse } from "../types";

const PROVENIENZA: ProvenienzaResponse = {
  motore: "deterministic",
  sfidante_ml_attivo: false,
  meteo_modello: "best_match",
  correttore_pioggia: { stato: "raccolta_dati", nodi_raccolti: 32, nodi_obiettivo: 150 },
  spiegazioni_modello: "quality-cloud",
};

const MODELLI: RainModelsResponse = {
  cell_id: "it-friuli-venezia-giulia|1|1",
  hours: 72,
  modelli: [
    { id: "gfs_seamless", nome: "GFS (NOAA, USA)", mm: 29.4 },
    { id: "ecmwf_aifs025_single", nome: "ECMWF AIFS (rete neurale)", mm: 68.4 },
    { id: "ecmwf_ifs025", nome: "ECMWF IFS", mm: 93.3 },
  ],
};

const SCRITTA: SpiegazioneResponse = {
  aoi_id: "it-friuli-venezia-giulia",
  hazard_type: "flood",
  spiegazione: {
    testo: "In Friuli la pioggia prevista spinge l'alluvione.",
    modello: "quality-cloud",
    scritta: "2026-10-06T14:05:00Z",
    livello: "High",
    analisi: {
      driver: "pluvial_rain",
      anomalies: [],
      attention_window_hours: 48,
      confidence: 0.7,
    },
  },
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(defaultApiClient, "getProvenienza").mockResolvedValue(PROVENIENZA);
});

describe("modelloLeggibile", () => {
  it("dà un nome umano ai modelli del gateway", () => {
    expect(modelloLeggibile("quality-cloud")).toBe("Claude (Anthropic)");
    expect(modelloLeggibile("sconosciuto")).toBe("sconosciuto");
  });
});

describe("ComeNasce", () => {
  it("mostra la forbice dei modelli e la spiegazione firmata", async () => {
    vi.spyOn(defaultApiClient, "getCellRainModels").mockResolvedValue(MODELLI);
    vi.spyOn(defaultApiClient, "getAoiSpiegazione").mockResolvedValue(SCRITTA);

    render(<ComeNasce cellId="it-friuli-venezia-giulia|1|1" hazard="flood" />);

    expect(await screen.findByText(/I modelli non sono d'accordo: da 29 a 93 mm/)).toBeTruthy();
    expect(screen.getByText(/scritta da Claude \(Anthropic\)/)).toBeTruthy();
    expect(screen.getByText("la pioggia prevista")).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/32\/150 punti/)).toBeTruthy());
    expect(screen.getByText(/non ancora nel numero/)).toBeTruthy();
  });

  it("senza spiegazione non attribuisce niente all'AI", async () => {
    vi.spyOn(defaultApiClient, "getCellRainModels").mockResolvedValue(MODELLI);
    vi.spyOn(defaultApiClient, "getAoiSpiegazione").mockResolvedValue({
      ...SCRITTA,
      spiegazione: null,
    });

    render(<ComeNasce cellId="it-friuli-venezia-giulia|1|1" hazard="flood" />);

    expect(await screen.findByText(/Non ancora scritta per questo pericolo/)).toBeTruthy();
    expect(screen.queryByText(/scritta da/)).toBeNull();
  });

  it("per l'incendio non chiede la pioggia dei modelli", async () => {
    const pioggia = vi.spyOn(defaultApiClient, "getCellRainModels").mockResolvedValue(MODELLI);
    vi.spyOn(defaultApiClient, "getAoiSpiegazione").mockResolvedValue(SCRITTA);

    render(<ComeNasce cellId="it-basilicata|1|1" hazard="wildfire" />);

    await screen.findByText(/Spiegazione dell'AI/);
    expect(pioggia).not.toHaveBeenCalled();
  });
});

describe("RigaProvenienza", () => {
  it("dice che il ML non è ancora nel numero", async () => {
    render(<RigaProvenienza />);
    expect(await screen.findByText(/non ancora attivo/)).toBeTruthy();
  });
});
