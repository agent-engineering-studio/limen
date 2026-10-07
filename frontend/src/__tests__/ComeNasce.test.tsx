// «Come nasce questo numero»: l'ispettore dice chi ha fatto cosa — formula,
// meteo, ML, AI — senza ripetere la spiegazione della regione, che vive in
// «Regioni da monitorare».

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ComeNasce, { modelloLeggibile, RigaProvenienza } from "../components/ComeNasce";
import { defaultApiClient } from "../lib/api-client";
import type { ProvenienzaResponse, RainModelsResponse } from "../types";

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
  it("mostra la forbice dei modelli senza parlare di modelli in addestramento", async () => {
    vi.spyOn(defaultApiClient, "getCellRainModels").mockResolvedValue(MODELLI);

    const { container } = render(<ComeNasce cellId="it-friuli-venezia-giulia|1|1" hazard="flood" />);

    expect(await screen.findByText(/I modelli meteo non concordano: da 29 a 93 mm/)).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/non entra nel numero/)).toBeTruthy());
    expect(container.textContent).not.toContain("addestramento");
    expect(container.textContent).not.toContain("raccolta dati");
  });

  it("la spiegazione della regione è un link, non un testo ripetuto per ogni cella", async () => {
    vi.spyOn(defaultApiClient, "getCellRainModels").mockResolvedValue(MODELLI);
    render(<ComeNasce cellId="it-piemonte|3|4" hazard="flood" />);
    const link = await screen.findByRole("link", { name: /Regioni da monitorare/ });
    expect(link.getAttribute("href")).toBe("#/regioni/it-piemonte");
  });

  it("per l'incendio non chiede la pioggia dei modelli", async () => {
    const pioggia = vi.spyOn(defaultApiClient, "getCellRainModels").mockResolvedValue(MODELLI);
    render(<ComeNasce cellId="it-basilicata|1|1" hazard="wildfire" />);
    await screen.findByText(/Come nasce questo numero/);
    expect(pioggia).not.toHaveBeenCalled();
  });
});

describe("RigaProvenienza", () => {
  it("dice che il ML non entra nel numero", async () => {
    render(<RigaProvenienza />);
    expect(await screen.findByText(/non entra nel numero/)).toBeTruthy();
  });
});
