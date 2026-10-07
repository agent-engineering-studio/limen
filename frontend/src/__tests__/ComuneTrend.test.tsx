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
      observed: {
        landslide: serie(5, 0.4),
        wildfire: serie(5, 0.2),
        flood: serie(5, 0.1),
      },
      forecast: {},
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.querySelectorAll("svg path")).toHaveLength(3);
    // La legenda dice quale linea è quale: tre colori senza nomi non si
    // leggono, ed è la stessa ragione per cui la palette del rischio ha
    // sempre l'etichetta accanto.
    expect(container.textContent).toContain("frane");
    expect(container.textContent).toContain("incendio");
    expect(container.textContent).toContain("allagamento");
  });

  it("un pericolo con un solo punto non diventa una linea", async () => {
    // Due punti fanno una tendenza, uno fa un punto: disegnarlo come una
    // riga orizzontale direbbe «stabile» di un dato che non lo dice.
    getComuneHistory.mockResolvedValue({
      observed: { landslide: serie(4, 0.4), wildfire: serie(1, 0.2) },
      forecast: {},
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.querySelectorAll("svg path")).toHaveLength(1);
  });

  it("senza misure lo dice, invece di mostrare un riquadro vuoto", async () => {
    getComuneHistory.mockResolvedValue({ observed: {}, forecast: {} });
    render(<ComuneTrend istatCode="001001" />);
    await waitFor(() =>
      expect(screen.getByText(/non ci sono ancora abbastanza misure/i)).toBeInTheDocument(),
    );
  });

  it("dichiara che segue la cella peggiore, non l'insieme del comune", async () => {
    // La cella peggiore di oggi poteva non esserlo cinque giorni fa: chi
    // legge deve saperlo, perché è il prezzo di un grafico che si disegna in
    // millisecondi invece che in due minuti.
    getComuneHistory.mockResolvedValue({
      observed: { landslide: serie(3, 0.5) },
      forecast: {},
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.textContent).toContain("cella peggiore");
  });

  it("la previsione prosegue la linea, tratteggiata e dopo un confine", async () => {
    // La previsione è il cuore dell'applicazione e viveva solo in un elenco
    // per regione: «nessuna regione sopra soglia» non dice se il *tuo*
    // comune sta salendo. Qui la stessa linea attraversa l'adesso.
    getComuneHistory.mockResolvedValue({
      observed: { landslide: serie(4, 0.3) },
      forecast: {
        landslide: [
          { t: new Date(Date.now() + 24 * 3600_000).toISOString(), score: 0.45 },
          { t: new Date(Date.now() + 48 * 3600_000).toISOString(), score: 0.58 },
        ],
      },
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());

    // Due tracciati per lo stesso pericolo: il vissuto e il previsto.
    const tracciati = container.querySelectorAll("svg path");
    expect(tracciati).toHaveLength(2);
    expect(tracciati[1]?.getAttribute("stroke-dasharray")).toBe("3 3");
    // Il confine fra fatto e calcolo: senza, una linea che sale a destra si
    // legge come qualcosa che è già successo.
    expect(container.textContent).toContain("ora");
    expect(container.textContent).toContain("previsione");
    expect(container.textContent).toContain("non un fatto");
  });

  it("la legenda dice dove si va, non solo dove si è", async () => {
    getComuneHistory.mockResolvedValue({
      observed: { landslide: serie(3, 0.3) },
      forecast: {
        landslide: [
          { t: new Date(Date.now() + 48 * 3600_000).toISOString(), score: 0.58 },
        ],
      },
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    // Un 0,58 previsto non dice niente finché non si sa che adesso è 0,32.
    expect(container.textContent).toContain("0,32");
    expect(container.textContent).toContain("0,58");
  });
});

describe("previsione d'alluvione", () => {
  it("disegna il tratteggio anche a zero, e dice la pioggia prevista", async () => {
    // Prevista sotto soglia ovunque, l'alluvione non lasciava righe e il
    // grafico non mostrava nessun tratteggio, come se mancasse. «Previsto
    // 0,00» è una previsione, e la pioggia è il numero che dice quanto manca.
    getComuneHistory.mockResolvedValue({
      observed: { flood: serie(3, 0) },
      forecast: {
        flood: [
          { t: new Date(Date.now() + 24 * 3600_000).toISOString(), score: 0, rain_mm: 3.2 },
          { t: new Date(Date.now() + 48 * 3600_000).toISOString(), score: 0, rain_mm: 12.6 },
        ],
      },
    });
    const { container } = render(<ComuneTrend istatCode="001001" />);
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    const tracciati = [...container.querySelectorAll("svg path")];
    expect(tracciati.some((t) => t.getAttribute("stroke-dasharray") === "3 3")).toBe(true);
    expect(container.textContent).toContain("previsti 13 mm");
  });
});
