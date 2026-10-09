// Il pericolo scelto nel quadro nazionale guida la lista dei comuni e il loro
// grafico; «Tutti i pericoli» li lascia su tutti.
import { fireEvent, render, screen, waitFor } from "../test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getTopComuni, getForecastSchedule, getComuneHistory, getLegend, getComune, stato } =
  vi.hoisted(() => ({
    getTopComuni: vi.fn(),
    getForecastSchedule: vi.fn(),
    getComuneHistory: vi.fn(),
    getLegend: vi.fn(),
    getComune: vi.fn(),
    stato: { view: "multi" as string },
  }));
vi.mock("../lib/api-client", async (importActual) => {
  const vero = await importActual<typeof import("../lib/api-client")>();
  return {
    ...vero,
    defaultApiClient: { getTopComuni, getForecastSchedule, getComuneHistory, getLegend, getComune },
  };
});
vi.mock("../lib/hazard", () => ({
  useHazard: () => ({
    available: [
      { hazard: "landslide", label_it: "Frana" },
      { hazard: "flood", label_it: "Allagamento" },
      { hazard: "wildfire", label_it: "Incendio" },
    ],
    selected: stato.view === "multi" ? "landslide" : stato.view,
    view: stato.view,
    multi: stato.view === "multi",
    select: () => undefined,
  }),
}));

import ComuniBoard from "../components/ComuniBoard";

const ORA = Date.now();
const riga = {
  istat_code: "076001",
  name: "Calitri",
  aoi_id: "it-campania",
  worst_hazard: "wildfire",
  worst_class: "High",
  max_score: 0.6,
  n_cells: 10,
  n_alert: 2,
  counts: {},
  exposure_rank: 1,
  lon: 15.4,
  lat: 40.9,
  attention: 1.2,
  forecast: {},
  forecast_attention: null,
  hazards: {
    landslide: { class: "Moderate", score: 0.42, priority: 0.5, n_cells: 10, n_alert: 0, measured: true },
    flood: { class: "None", score: 0.0, priority: 0.0, n_cells: 10, n_alert: 0, measured: true },
    wildfire: { class: "High", score: 0.6, priority: 1.0, n_cells: 10, n_alert: 2, measured: true },
  },
};
const punti = (s: number) => [
  { t: new Date(ORA - 48 * 3600_000).toISOString(), score: s },
  { t: new Date(ORA - 3600_000).toISOString(), score: s + 0.01 },
];

beforeEach(() => {
  getTopComuni.mockReset().mockResolvedValue({ comuni: [riga] });
  getForecastSchedule.mockReset().mockResolvedValue(null);
  getComune.mockReset().mockReturnValue(new Promise(() => undefined));
  getComuneHistory.mockReset().mockResolvedValue({
    observed: { landslide: punti(0.4), wildfire: punti(0.58) },
    forecast: {},
  });
  getLegend.mockReset().mockResolvedValue({
    classes: [
      { level: "Moderate", lo: 0.24, hi: 0.42, pc_alert: "gialla" },
      { level: "High", lo: 0.42, hi: 0.76, pc_alert: "arancione" },
    ],
    model_version: "t",
  });
});

describe("ComuniBoard e il pericolo scelto", () => {
  it("con tutti i pericoli chiede la classifica su tutti e disegna tutte le linee", async () => {
    stato.view = "multi";
    const { container } = render(<ComuniBoard />);
    await waitFor(() =>
      expect(getTopComuni).toHaveBeenCalledWith(undefined, 30, expect.anything(), undefined, "now", undefined),
    );
    fireEvent.click(await screen.findByText("Calitri"));
    await waitFor(() => expect(container.querySelectorAll("svg path").length).toBe(2));
    expect(getLegend).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Comuni più esposti");
  });

  it("scelto l'incendio, classifica, testata e grafico parlano dell'incendio", async () => {
    stato.view = "wildfire";
    const { container } = render(<ComuniBoard />);
    await waitFor(() =>
      expect(getTopComuni).toHaveBeenCalledWith(undefined, 30, expect.anything(), undefined, "now", "wildfire"),
    );
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Comuni più esposti · incendio");
    fireEvent.click(await screen.findByText("Calitri"));
    // Una linea sola, con le soglie dell'incendio e non quelle delle frane.
    await waitFor(() => expect(container.querySelectorAll("svg path").length).toBe(1));
    expect(getLegend).toHaveBeenCalledWith(expect.anything(), "wildfire");
  });

  it("scelte le frane, la testata è la frana anche se l'incendio è più alto", async () => {
    stato.view = "landslide";
    const { container } = render(<ComuniBoard />);
    await screen.findByText("Calitri");
    const testa = container.querySelector(".cb-head")?.textContent ?? "";
    // La testata (prima degli indicatori F/A/I) è la frana, non l'incendio.
    expect(testa).toMatch(/^01Calitri\w+frana0,42moderato/);
    expect(testa).toContain("In cima per: frana");
    // L'ordine è sulla sola frana: la concomitanza non è un motivo.
    expect(testa).not.toContain("pericoli oltre soglia");
  });

  it("senza la legenda del pericolo non disegna le soglie delle frane", async () => {
    stato.view = "wildfire";
    getLegend.mockRejectedValue(new Error("503"));
    const { container } = render(<ComuniBoard />);
    fireEvent.click(await screen.findByText("Calitri"));
    await waitFor(() => expect(container.querySelectorAll("svg path").length).toBe(1));
    expect(container.querySelector("svg")?.textContent).not.toContain("alto");
  });

  it("senza comuni sopra soglia dice per quale pericolo", async () => {
    stato.view = "flood";
    getTopComuni.mockResolvedValue({ comuni: [] });
    render(<ComuniBoard />);
    expect(
      await screen.findByText(/Moderata o superiore per allagamento\./),
    ).toBeInTheDocument();
  });
});
