// L'andamento del comune (#144): tre linee sulla stessa scala, e gli stati
// onesti quando la serie non c'è.

import { render, screen, waitFor } from "../test-utils";
import { describe, expect, it, vi } from "vitest";

const { getComuneHistory } = vi.hoisted(() => ({ getComuneHistory: vi.fn() }));
vi.mock("../lib/api-client", async (importActual) => {
  const vero = await importActual<typeof import("../lib/api-client")>();
  return { ...vero, defaultApiClient: { getComuneHistory } };
});

import ComuneTrend from "../components/ComuneTrend";

const serie = (n: number, base: number) =>
  Array.from({ length: n }, (_, i) => ({
    t: new Date(Date.UTC(2026, 8, 24 + i)).toISOString(),
    score: base + i * 0.01,
  }));

describe("ComuneTrend", () => {
  it("disegna una linea per ogni pericolo che ha una serie", async () => {
    getComuneHistory.mockResolvedValue({
      landslide: serie(5, 0.4),
      wildfire: serie(5, 0.2),
      flood: serie(5, 0.1),
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.querySelectorAll("svg path")).toHaveLength(3);
    // La legenda dice quale linea è quale: tre colori senza nomi non si
    // leggono, ed è la stessa ragione per cui la palette del rischio ha
    // sempre l'etichetta accanto.
    expect(container.textContent).toContain("frane");
    expect(container.textContent).toContain("incendio");
    expect(container.textContent).toContain("alluvione");
  });

  it("un pericolo con un solo punto non diventa una linea", async () => {
    // Due punti fanno una tendenza, uno fa un punto: disegnarlo come una
    // riga orizzontale direbbe «stabile» di un dato che non lo dice.
    getComuneHistory.mockResolvedValue({
      landslide: serie(4, 0.4),
      wildfire: serie(1, 0.2),
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.querySelectorAll("svg path")).toHaveLength(1);
  });

  it("senza misure lo dice, invece di mostrare un riquadro vuoto", async () => {
    getComuneHistory.mockResolvedValue({});
    render(<ComuneTrend istatCode="001001" />);
    await waitFor(() =>
      expect(screen.getByText(/non ci sono ancora abbastanza misure/i)).toBeInTheDocument(),
    );
  });

  it("dichiara che segue la cella peggiore, non l'insieme del comune", async () => {
    // La cella peggiore di oggi poteva non esserlo cinque giorni fa: chi
    // legge deve saperlo, perché è il prezzo di un grafico che si disegna in
    // millisecondi invece che in due minuti.
    getComuneHistory.mockResolvedValue({ landslide: serie(3, 0.5) });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.textContent).toContain("cella peggiore");
  });
});
