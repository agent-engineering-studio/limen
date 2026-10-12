import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api-client", () => ({
  defaultApiClient: {
    getNationalReport: vi.fn(() =>
      Promise.resolve({
        generated_at: "2026-07-06T06:00:00+00:00",
        regions: [],
        totals: { regions: 20, cells: 312550, high_or_above: 0, moderate: 100 },
        top_cells: [],
        ml_top_cells: [],
        alerts_24h: 12,
        forecast_alerts_24h: 0,
        report_it: "x",
      }),
    ),
  },
}));

import HomePage from "../components/HomePage";
import { useLingua } from "../lib/i18n";
import { fireEvent, render as renderConLingua } from "../test-utils";

describe("HomePage", () => {
  it("renders the pitch, the dashboard CTA and live stats", async () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Il rischio del territorio/,
    );
    // Nessun login: la dashboard è pubblica (#71).
    expect(screen.getByText("Apri la dashboard")).toBeInTheDocument();
    expect(screen.getByText("Cos'è Limen")).toBeInTheDocument();
    // Static fallback first, live numbers after the fetch resolves.
    await waitFor(() =>
      expect(screen.getByText("312.550")).toBeInTheDocument(),
    );
    expect(screen.getByText("celle monitorate")).toBeInTheDocument();
    // License attributions are a legal requirement, not decoration.
    expect(screen.getAllByText(/ISPRA IdroGEO/).length).toBeGreaterThan(0);
  });

  it("non promette ciò che oggi non è vero", () => {
    // #155: il design diceva «verificato su vent'anni di frane reali» (#122
    // aperta), un ML che «corre accanto» (in produzione è spento) e il rischio
    // come «S × M» (per le frane è una somma pesata).
    const { container } = render(<HomePage />);
    const testo = container.textContent ?? "";
    expect(testo).not.toMatch(/vent.anni di frane/);
    expect(testo).not.toMatch(/corre (accanto|in parallelo)/);
    expect(testo).not.toContain("S × M");
    expect(testo).not.toMatch(/AUC/);
    expect(testo).toContain("0,35 S + 0,40 M");
  });

  it("in inglese: titolo, formule con il punto decimale e crediti", async () => {
    const { container } = renderConLingua(<HomePage />, { lingua: "en" });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Territorial risk, cell by cell.",
    );
    expect(screen.getByText("Open the dashboard")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("312,550")).toBeInTheDocument());
    const testo = container.textContent ?? "";
    expect(testo).toContain("0.35 S + 0.40 M");
    expect(testo).toContain("not affiliated with Anthropic");
    expect(testo).toContain("Contains modified Copernicus Emergency Management Service information");
    expect(testo).toContain("CC-BY 4.0");
    expect(testo).not.toContain("Apri la dashboard");
  });

  it("cambia lingua senza ricaricare", async () => {
    function ConSelettore() {
      const { imposta } = useLingua();
      return (
        <>
          <button type="button" onClick={() => imposta("en")}>
            EN
          </button>
          <HomePage />
        </>
      );
    }
    renderConLingua(<ConSelettore />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/Il rischio del territorio/);
    fireEvent.click(screen.getByText("EN"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/Territorial risk/);
    await waitFor(() => expect(screen.getByText("312,550")).toBeInTheDocument());
  });
});
