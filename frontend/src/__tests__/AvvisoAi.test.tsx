import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AvvisoAi from "../components/AvvisoAi";
import ConsumiAi from "../components/ConsumiAi";
import { defaultApiClient } from "../lib/api-client";
import type { LlmStatusResponse } from "../types";

const STATO: LlmStatusResponse = {
  mese: "2026-10",
  in_pausa: false,
  ripresa: null,
  richieste: 42,
  input_tokens: 123456,
  output_tokens: 7890,
  per_giorno: [],
  per_modello: [
    { chiave: "claude-haiku-5-5", richieste: 40, input_tokens: 120000, output_tokens: 7000 },
    { chiave: "chat-8b", richieste: 2, input_tokens: 3456, output_tokens: 890 },
  ],
};

describe("AvvisoAi", () => {
  it("non dice niente finché l'AI non è in pausa", async () => {
    const spia = vi.spyOn(defaultApiClient, "getLlmStatus").mockResolvedValue(STATO);
    const { container } = render(<AvvisoAi />);
    await waitFor(() => expect(spia).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("a tetto raggiunto dice quando torna, senza importi", async () => {
    vi.spyOn(defaultApiClient, "getLlmStatus").mockResolvedValue({
      ...STATO,
      in_pausa: true,
      ripresa: "2026-11-01",
    });
    render(<AvvisoAi />);
    const avviso = await screen.findByText("AI in pausa");
    expect(avviso.getAttribute("title")).toMatch(/1 novembre/);
    expect(avviso.getAttribute("title")).not.toMatch(/\$|€|dollar/i);
  });

  it("se lo stato non arriva resta muto", async () => {
    const spia = vi.spyOn(defaultApiClient, "getLlmStatus").mockRejectedValue(new Error("down"));
    const { container } = render(<AvvisoAi />);
    await waitFor(() => expect(spia).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ConsumiAi", () => {
  it("mostra i token del mese per modello, e nessun importo", async () => {
    vi.spyOn(defaultApiClient, "getLlmStatus").mockResolvedValue(STATO);
    const { container } = render(<ConsumiAi />);
    expect(await screen.findByText("claude-haiku-5-5")).toBeInTheDocument();
    expect(screen.getByText("chat-8b")).toBeInTheDocument();
    expect(screen.getByText(/42 richieste/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\$|€/);
  });

  it("un mese senza chiamate lo dice", async () => {
    vi.spyOn(defaultApiClient, "getLlmStatus").mockResolvedValue({
      ...STATO,
      richieste: 0,
      per_modello: [],
    });
    render(<ConsumiAi />);
    expect(await screen.findByText(/Nessuna chiamata/)).toBeInTheDocument();
  });
});
