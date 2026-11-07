import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InstallazionePage from "../components/InstallazionePage";
import SalutePanel, { discoBasso, workerFermo } from "../components/SalutePanel";
import { defaultApiClient } from "../lib/api-client";
import { render } from "../test-utils";
import type { InstallazioneStato, LlmStatusResponse, SaluteStato } from "../types";

const ADESSO = "2026-11-03T12:00:00Z";

function salute(extra: Partial<SaluteStato> = {}): SaluteStato {
  return {
    fonti: [
      {
        id: "openmeteo",
        nome: "Open-Meteo pubblico",
        pericoli: ["landslide", "flood", "wildfire"],
        ultimo_ok: "2026-11-03T09:00:00Z",
        ultimo_errore: ADESSO,
        errore: "Quota esaurita (429): la fonte rifiuta altre richieste per ora.",
        in_errore: true,
      },
    ],
    openmeteo: "pubblica",
    glofas_in_pausa_fino: null,
    non_misurate: [
      { pericolo: "wildfire", celle: 312550, totali: 312550, cause: ["Open-Meteo pubblico"] },
      { pericolo: "landslide", celle: 0, totali: 312550, cause: [] },
    ],
    dischi: [{ nome: "Dati (LIMEN_DATA_ROOT)", libero_gb: 20, totale_gb: 500 }],
    db_gb: 41.3,
    battito: new Date().toISOString(),
    backup: { nome: "backup", stato: "ok", finito_il: ADESSO, nota: null },
    notturno: [{ nome: "backup", stato: "ok", finito_il: ADESSO, nota: null }],
    ...extra,
  };
}

const LLM: LlmStatusResponse = {
  mese: "2026-11",
  in_pausa: false,
  ripresa: null,
  richieste: 0,
  input_tokens: 0,
  output_tokens: 0,
  per_giorno: [],
  per_modello: [],
};

afterEach(() => vi.restoreAllMocks());

describe("regole pure", () => {
  it("disco basso sotto il 10 % libero", () => {
    expect(discoBasso({ nome: "d", libero_gb: 20, totale_gb: 500 })).toBe(true);
    expect(discoBasso({ nome: "d", libero_gb: 200, totale_gb: 500 })).toBe(false);
  });

  it("worker fermo senza battito o con un battito vecchio", () => {
    const t = Date.parse(ADESSO);
    expect(workerFermo(null, t)).toBe(true);
    expect(workerFermo("2026-11-03T11:50:00Z", t)).toBe(true);
    expect(workerFermo("2026-11-03T11:58:00Z", t)).toBe(false);
  });
});

describe("SalutePanel", () => {
  it("dice la fonte in 429 e il pericolo non misurato con la sua causa", async () => {
    vi.spyOn(defaultApiClient, "getSalute").mockResolvedValue(salute());
    vi.spyOn(defaultApiClient, "getLlmStatus").mockResolvedValue(LLM);
    render(<SalutePanel />);
    expect(await screen.findByText(/Quota esaurita \(429\)/)).toBeInTheDocument();
    expect(screen.getByText(/312.550 celle su 312.550/)).toBeInTheDocument();
    expect(screen.getByText(/causa probabile: Open-Meteo pubblico/)).toBeInTheDocument();
    expect(screen.getByText(/API pubblica/)).toBeInTheDocument();
    expect(screen.queryByText(/non dà segni di vita/)).not.toBeInTheDocument();
  });

  it("avvisa quando il worker non batte", async () => {
    vi.spyOn(defaultApiClient, "getSalute").mockResolvedValue(salute({ battito: null }));
    vi.spyOn(defaultApiClient, "getLlmStatus").mockResolvedValue(LLM);
    render(<SalutePanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/non dà segni di vita/);
  });
});

describe("InstallazionePage a installazione finita", () => {
  it("diventa «Come sta Limen» con il pannello Salute", async () => {
    const pronto: InstallazioneStato = {
      celle_totali: 312550,
      regioni: 20,
      elenco_regioni: [],
      pericoli: [
        { pericolo: "landslide", pronto: true, mancano: [] },
        { pericolo: "flood", pronto: true, mancano: [] },
        { pericolo: "wildfire", pronto: true, mancano: [] },
      ],
      voci: [],
      elaborazione: null,
      azioni_abilitate: false,
    };
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(pronto);
    const getSalute = vi.spyOn(defaultApiClient, "getSalute").mockResolvedValue(salute());
    vi.spyOn(defaultApiClient, "getLlmStatus").mockResolvedValue(LLM);
    render(<InstallazionePage />);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Come sta Limen");
    await waitFor(() => expect(getSalute).toHaveBeenCalled());
  });
});
