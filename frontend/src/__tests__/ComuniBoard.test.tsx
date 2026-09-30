// `render` dal nostro helper: i componenti Mantine vogliono il provider.
import { fireEvent, render, screen, waitFor } from "../test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getTopComuni, getForecastSchedule, getForecastAlerts } = vi.hoisted(() => ({
  getTopComuni: vi.fn(),
  getForecastSchedule: vi.fn(),
  getForecastAlerts: vi.fn(),
}));
vi.mock("../lib/api-client", async (importActual) => {
  const vero = await importActual<typeof import("../lib/api-client")>();
  return {
    ...vero,
    defaultApiClient: { getTopComuni, getForecastSchedule, getForecastAlerts },
  };
});

// Di default la previsione per cella esiste per le frane, calcolata
// stanotte, con la prossima corsa fra sei ore: è la forma di tutti i giorni.
const ORA = Date.now();
const SCHEDULE = {
  cells: {
    next_run_at: new Date(ORA + 6 * 3600_000).toISOString(),
    last_run_by_hazard: { landslide: new Date(ORA - 8 * 3600_000).toISOString() },
  },
  interval_hours: 6,
  horizon_hours: 48,
  next_run_at: new Date(ORA + 2 * 3600_000 + 14 * 60_000).toISOString(),
  running_since: null,
  last_run: null,
};
beforeEach(() => {
  getTopComuni.mockReset();
  getForecastSchedule.mockReset().mockResolvedValue(SCHEDULE);
  getForecastAlerts.mockReset().mockResolvedValue({ items: [] });
});

import ComuniBoard from "../components/ComuniBoard";

type Pericolo = {
  class: string;
  n_cells: number;
  n_alert: number;
  measured?: boolean;
};

type Previsto = { class: string; score: number; horizon_h: number; priority: number };

const comune = (
  name: string,
  hazards: Record<string, Pericolo>,
  attention: number | null = 1.6,
  forecast: Record<string, Previsto> = {},
) => ({
  istat_code: name,
  name,
  aoi_id: "it-test",
  worst_hazard: "wildfire",
  worst_class: "High",
  max_score: 0.8,
  n_cells: 12,
  n_alert: 3,
  counts: {},
  exposure_rank: 1,
  lon: 13.1,
  lat: 46.5,
  attention,
  forecast: Object.fromEntries(
    Object.entries(forecast).map(([h, v]) => [
      h,
      { ...v, target_at: new Date(ORA + v.horizon_h * 3600_000).toISOString() },
    ]),
  ),
  forecast_attention: Object.keys(forecast).length ? 1.9 : null,
  hazards: Object.fromEntries(
    Object.entries(hazards).map(([h, v]) => [
      h,
      { score: 0.5, priority: 0.8, measured: true, ...v },
    ]),
  ),
});

describe("ComuniBoard", () => {
  it("mostra i tre pericoli sulla stessa riga, anche quelli a zero", async () => {
    // È il punto del cambio: prima la classifica era fissata sulle frane e lo
    // dichiarava con un badge, quindi scegliendo un altro pericolo metà
    // colonna parlava d'altro.
    getTopComuni.mockResolvedValue({
      comuni: [
        comune("Avezzano", {
          landslide: { class: "Moderate", n_cells: 12, n_alert: 0 },
          flood: { class: "None", n_cells: 12, n_alert: 0 },
          wildfire: { class: "High", n_cells: 12, n_alert: 3 },
        }),
      ],
    });
    const { container } = render(<ComuniBoard />);
    await waitFor(() => expect(screen.getByText("Avezzano")).toBeInTheDocument());
    // Tre indicatori, non uno: l'alluvione in classe «nessuno» resta in riga.
    expect(container.querySelectorAll(".cb-haz")).toHaveLength(3);
    expect(container.textContent).toContain("alto");
    // Il numero unico sta accanto al nome, con la parola che dice cos'è:
    // un 1,60 nudo non si sa interpretare.
    expect(container.textContent).toContain("attenzione");
    expect(container.textContent).toContain("1,60");
  });

  it("un pericolo non misurato non si mostra come «nessuno»", async () => {
    // Un'integrazione degradata dà zero, e uno zero dipinto in fondo alla
    // scala si legge come una buona notizia (#143). Qui ha uno stato suo.
    getTopComuni.mockResolvedValue({
      comuni: [
        comune("Antrodoco", {
          landslide: { class: "Moderate", n_cells: 75, n_alert: 0 },
          flood: { class: "None", n_cells: 0, n_alert: 0, measured: false },
          wildfire: { class: "Moderate", n_cells: 75, n_alert: 0 },
        }),
      ],
    });
    const { container } = render(<ComuniBoard />);
    await waitFor(() => expect(screen.getByText("Antrodoco")).toBeInTheDocument());
    expect(container.textContent).toContain("non misurato");
    expect(container.querySelector(".cb-chip.is-unknown")).not.toBeNull();
    // E non lo racconta come una classe: «nessuno» sarebbe la bugia.
    expect(container.textContent).not.toContain("nessuno");
  });

  it("senza niente di misurato il numero non si inventa", async () => {
    getTopComuni.mockResolvedValue({
      comuni: [
        comune(
          "Vattelapesca",
          {
            landslide: { class: "None", n_cells: 0, n_alert: 0, measured: false },
            flood: { class: "None", n_cells: 0, n_alert: 0, measured: false },
            wildfire: { class: "None", n_cells: 0, n_alert: 0, measured: false },
          },
          null,
        ),
      ],
    });
    const { container } = render(<ComuniBoard />);
    await waitFor(() => expect(screen.getByText("Vattelapesca")).toBeInTheDocument());
    // Nessun numero di attenzione, e nemmeno uno zero al suo posto.
    expect(container.textContent).not.toContain("0,00");
    expect(container.querySelector(".cb-bar.is-unknown")).not.toBeNull();
  });

  it("i due numeri hanno scale diverse, e la colonna lo dice", async () => {
    // Il punteggio di un pericolo va da 0 a 1, l'attenzione del comune da 0
    // a 3: leggere 0,40 come «poco» rispetto a 1,37 è l'errore da evitare.
    getTopComuni.mockResolvedValue({
      comuni: [
        comune("Antrodoco", {
          landslide: { class: "Moderate", n_cells: 75, n_alert: 0 },
        }),
      ],
    });
    const { container } = render(<ComuniBoard />);
    await waitFor(() => expect(screen.getByText("Antrodoco")).toBeInTheDocument());
    // Il punteggio del pericolo è scritto accanto alla classe, non solo la
    // classe: «moderato» da solo non dice quanto.
    expect(container.textContent).toContain("0,50");
    expect(container.textContent).toContain("moderato");
  });

  it("una giornata tranquilla è una notizia, non un pannello vuoto", async () => {
    getTopComuni.mockResolvedValue({ comuni: [] });
    render(<ComuniBoard />);
    await waitFor(() =>
      expect(screen.getByText(/Nessun comune sopra la soglia/)).toBeInTheDocument(),
    );
  });

  it("la ricerca chiede al servizio il termine, non filtra le trenta righe in mano", async () => {
    // I comuni sono ottomila e in pagina ce ne sono trenta: filtrare qui
    // vorrebbe dire non trovare il proprio.
    getTopComuni.mockResolvedValue({ comuni: [] });
    render(<ComuniBoard />);
    await waitFor(() => expect(getTopComuni).toHaveBeenCalled());
    expect(screen.getByLabelText("Cerca il tuo comune")).toBeInTheDocument();
  });

  it("cliccare un comune porta la mappa sulle sue coordinate", async () => {
    // Una classifica geografica su cui si clicca e non succede niente è una
    // lista di nomi: il posto è metà dell'informazione.
    getTopComuni.mockResolvedValue({
      comuni: [
        comune("Bardonecchia", {
          landslide: { class: "Moderate", n_cells: 134, n_alert: 0 },
        }),
      ],
    });
    const visti: { lon: number; lat: number }[] = [];
    render(<ComuniBoard onComune={(c) => visti.push({ lon: c.lon, lat: c.lat })} />);
    await waitFor(() => expect(screen.getByText("Bardonecchia")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Bardonecchia"));

    expect(visti).toEqual([{ lon: 13.1, lat: 46.5 }]);
  });

  it("la previsione sta nella riga del comune, con il verso e l'orizzonte", async () => {
    // Stava in un pannello a parte, per regione: «nessuna regione sopra
    // soglia» non dice se il *tuo* comune sta salendo.
    getTopComuni.mockResolvedValue({
      comuni: [
        comune(
          "Montegiordano",
          { landslide: { class: "Moderate", n_cells: 36, n_alert: 0 } },
          1.4,
          { landslide: { class: "High", score: 0.62, horizon_h: 48, priority: 1.8 } },
        ),
      ],
    });
    const { container } = render(<ComuniBoard />);
    await waitFor(() => expect(container.textContent).toContain("Previsto:"));
    expect(container.textContent).toContain("0,62");
    expect(container.textContent).toContain("in salita");
    expect(container.textContent).toContain("+48 h");
  });

  it("senza righe previsionali, per un pericolo previsto dice «sotto moderato»", async () => {
    // L'assenza è una risposta solo per i pericoli la cui corsa c'è stata:
    // per le frane vuol dire previsto sotto soglia.
    getTopComuni.mockResolvedValue({
      comuni: [comune("Antrodoco", { landslide: { class: "Moderate", n_cells: 75, n_alert: 0 } })],
    });
    const { container } = render(<ComuniBoard />);
    await waitFor(() => expect(container.textContent).toContain("sotto"));
    expect(container.textContent).toContain("frana");
    // E non si allarga agli altri due: per incendio e alluvione la corsa
    // previsionale non esiste, e «sotto moderato» sarebbe inventato.
    expect(container.textContent).not.toMatch(/incendio[^·]*sotto\s+moderato/i);
  });

  it("il selettore riordina sul futuro, e lo chiede al servizio", async () => {
    getTopComuni.mockResolvedValue({ comuni: [] });
    render(<ComuniBoard />);
    await waitFor(() => expect(getTopComuni).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Più esposti fra 72 h"));
    await waitFor(() =>
      expect(getTopComuni).toHaveBeenLastCalledWith(
        undefined,
        30,
        expect.anything(),
        undefined,
        "forecast",
      ),
    );
  });

  it("dice quando arriva la prossima previsione, e che è una al giorno", async () => {
    // Due calcoli, due timer: un solo conto alla rovescia da sei ore farebbe
    // credere che la curva di un comune si aggiorni quattro volte al giorno.
    getTopComuni.mockResolvedValue({ comuni: [] });
    const { container } = render(<ComuniBoard />);
    await waitFor(() => expect(container.textContent).toContain("prossima tra"));
    expect(container.textContent).toContain("una volta al giorno");
    expect(container.textContent).toContain("ogni 6 ore");
    expect(container.textContent).toContain("Disponibile per: frane");
  });
});
