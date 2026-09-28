import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getNationalReport } = vi.hoisted(() => ({ getNationalReport: vi.fn() }));
// Solo il client è finto: `ApiClientError` resta quella vera, perché è su
// `instanceof` che `describeFailure` decide cosa scrivere in pagina.
vi.mock("../lib/api-client", async (importActual) => {
  const vero = await importActual<typeof import("../lib/api-client")>();
  return { ...vero, defaultApiClient: { getNationalReport } };
});

import { ApiClientError } from "../lib/api-client";
import NationalStrip from "../components/NationalStrip";

const report = (high: number, moderate: number, generated: string) => ({
  hazard: "landslide",
  generated_at: generated,
  totals: { cells: 312550, regions: 20, high_or_above: high, moderate },
  alerts_24h: 0,
  forecast_alerts_24h: 0,
  hazards: [{ hazard: "landslide", label_it: "Frana", totals: { high_or_above: high, moderate } }],
  cascades: {},
  report_it: "",
  ml_top_cells: [],
});

beforeEach(() => {
  getNationalReport.mockReset();
  vi.useRealTimers();
});

describe("il pannello quando il servizio è giù", () => {
  it("non mostra mai l'indirizzo dell'API né il codice di stato", async () => {
    getNationalReport.mockRejectedValue(
      new ApiClientError("request to /api/report/national failed with 500", 500, null),
    );
    const { container } = render(<NationalStrip />);
    await waitFor(() =>
      expect(screen.getByText("Il servizio non risponde")).toBeInTheDocument(),
    );
    expect(container.textContent).not.toContain("/api/");
    expect(container.textContent).not.toContain("500");
  });

  it("offre di riprovare, e riprovare richiama il servizio", async () => {
    getNationalReport.mockRejectedValue(new ApiClientError("x", 500, null));
    render(<NationalStrip />);
    const bottone = await screen.findByRole("button", { name: "Riprova" });
    getNationalReport.mockResolvedValue(report(0, 0, new Date().toISOString()));
    fireEvent.click(bottone);
    await waitFor(() =>
      expect(screen.getByText(/Nessuna area sopra la soglia/)).toBeInTheDocument(),
    );
  });
});

describe("il verdetto in cima", () => {
  it("dice quante aree sono in classe alta", async () => {
    getNationalReport.mockResolvedValue(report(3, 40, new Date().toISOString()));
    render(<NationalStrip />);
    await waitFor(() =>
      expect(screen.getByText(/3 aree in classe Alta/)).toBeInTheDocument(),
    );
  });

  it("dichiara che i numeri sono vecchi invece di spacciarli per attuali", async () => {
    const sei_ore_fa = new Date(Date.now() - 6 * 3600 * 1000).toISOString();
    getNationalReport.mockResolvedValue(report(0, 0, sei_ore_fa));
    render(<NationalStrip />);
    await waitFor(() =>
      expect(screen.getByText(/Dati fermi da più di tre ore/)).toBeInTheDocument(),
    );
  });

  it("a giornata tranquilla non promette che non ci sia rischio", async () => {
    getNationalReport.mockResolvedValue(report(0, 0, new Date().toISOString()));
    const { container } = render(<NationalStrip />);
    await waitFor(() =>
      expect(screen.getByText(/Nessuna area sopra la soglia/)).toBeInTheDocument(),
    );
    expect(container.textContent).not.toContain("nessun rischio");
    // Il limite più importante della pagina, dove lo si legge per primo.
    expect(container.textContent).toContain("non sostituisce");
  });
});
