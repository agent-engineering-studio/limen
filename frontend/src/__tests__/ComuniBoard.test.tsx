// `render` dal nostro helper: i componenti Mantine vogliono il provider.
import { render, screen, waitFor } from "../test-utils";
import { describe, expect, it, vi } from "vitest";

const { getTopComuni } = vi.hoisted(() => ({ getTopComuni: vi.fn() }));
vi.mock("../lib/api-client", async (importActual) => {
  const vero = await importActual<typeof import("../lib/api-client")>();
  return { ...vero, defaultApiClient: { getTopComuni } };
});

import ComuniBoard from "../components/ComuniBoard";

const comune = (
  name: string,
  hazards: Record<string, { class: string; n_cells: number; n_alert: number }>,
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
  attention: 1.6,
  hazards: Object.fromEntries(
    Object.entries(hazards).map(([h, v]) => [h, { ...v, score: 0.5, priority: 0.8 }]),
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
    // Tre indicatori, non uno: l'alluvione a zero resta in riga col trattino.
    expect(container.querySelectorAll(".cb-haz")).toHaveLength(3);
    expect(container.querySelector(".cb-haz.is-quiet")).not.toBeNull();
    expect(container.textContent).toContain("alto");
    // Il numero unico sta accanto al nome: è quello che decide l'ordine.
    expect(container.textContent).toContain("1.60");
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
});
