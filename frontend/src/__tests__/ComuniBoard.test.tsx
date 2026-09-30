// `render` dal nostro helper: i componenti Mantine vogliono il provider.
import { fireEvent, render, screen, waitFor } from "../test-utils";
import { describe, expect, it, vi } from "vitest";

const { getTopComuni } = vi.hoisted(() => ({ getTopComuni: vi.fn() }));
vi.mock("../lib/api-client", async (importActual) => {
  const vero = await importActual<typeof import("../lib/api-client")>();
  return { ...vero, defaultApiClient: { getTopComuni } };
});

import ComuniBoard from "../components/ComuniBoard";

type Pericolo = {
  class: string;
  n_cells: number;
  n_alert: number;
  measured?: boolean;
};

const comune = (
  name: string,
  hazards: Record<string, Pericolo>,
  attention: number | null = 1.6,
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
});
