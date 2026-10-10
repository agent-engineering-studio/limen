// «Sei un esperto?»: il modulo sotto la cella manda il contributo con la cella
// e il pericolo che si stava guardando, e dice a parole cosa è successo.

import { fireEvent, render, screen, waitFor } from "../test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ContributoEsperto from "../components/ContributoEsperto";
import { ApiClientError, defaultApiClient } from "../lib/api-client";

const CELLA = "it-basilicata|12|34";

// Il modulo non spedisce prima di 6 s dall'apertura (il server scarterebbe
// l'invio come automatico): qui il tempo «passa» dopo l'apertura.
function compila(): void {
  fireEvent.click(screen.getByRole("button", { name: /Sei un esperto/ }));
  const aperto = Date.now();
  vi.spyOn(Date, "now").mockReturnValue(aperto + 10_000);
  fireEvent.change(screen.getByLabelText("Cosa vedi"), {
    target: { value: "Il versante è in argille e ha avuto un movimento nel 2019." },
  });
  fireEvent.change(screen.getByLabelText("Nome e cognome"), { target: { value: "Maria Rossi" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "maria@example.org" } });
  fireEvent.click(screen.getByLabelText(/acconsento al trattamento/));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("ContributoEsperto", () => {
  it("parte chiuso: un pulsante, nessun campo", () => {
    render(<ContributoEsperto cellId={CELLA} hazard="landslide" />);
    expect(screen.getByRole("button", { name: /Sei un esperto/ })).toBeTruthy();
    expect(screen.queryByLabelText("Cosa vedi")).toBeNull();
  });

  it("invia cella, pericolo e campi, e ringrazia", async () => {
    const invia = vi
      .spyOn(defaultApiClient, "inviaContributo")
      .mockResolvedValue({ ricevuto: true });
    render(<ContributoEsperto cellId={CELLA} hazard="landslide" />);
    compila();
    fireEvent.click(screen.getByRole("button", { name: "Invia il contributo" }));

    expect(await screen.findByText(/il contributo è arrivato/)).toBeTruthy();
    const body = invia.mock.calls[0]![0];
    expect(body.cell_id).toBe(CELLA);
    expect(body.hazard).toBe("landslide");
    expect(body.tipo).toBe("valutazione");
    expect(body.fonte_url).toBeNull();
    expect(body.consenso).toBe(true);
    expect(body.nome).toBe("Maria Rossi");
    expect(body.linkedin_url).toBeNull();
    expect(body.sito_web).toBe("");
    expect(body.compilato_in_ms).toBeGreaterThanOrEqual(0);
  });

  it("senza consenso il pulsante resta spento", () => {
    render(<ContributoEsperto cellId={CELLA} hazard={null} />);
    fireEvent.click(screen.getByRole("button", { name: /Sei un esperto/ }));
    fireEvent.change(screen.getByLabelText("Cosa vedi"), {
      target: { value: "Un testo abbastanza lungo da superare il minimo." },
    });
    const invia = screen.getByRole("button", { name: "Invia il contributo" }) as HTMLButtonElement;
    expect(invia.disabled).toBe(true);
  });

  it("basta il profilo LinkedIn al posto del nome", () => {
    render(<ContributoEsperto cellId={CELLA} hazard="landslide" />);
    fireEvent.click(screen.getByRole("button", { name: /Sei un esperto/ }));
    fireEvent.change(screen.getByLabelText("Cosa vedi"), {
      target: { value: "Il versante è in argille e ha avuto un movimento nel 2019." },
    });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "maria@example.org" } });
    fireEvent.click(screen.getByLabelText(/acconsento al trattamento/));
    const invia = screen.getByRole("button", { name: "Invia il contributo" }) as HTMLButtonElement;
    expect(invia.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Profilo LinkedIn/), {
      target: { value: "https://www.linkedin.com/in/maria-rossi" },
    });
    expect(invia.disabled).toBe(false);
  });

  it("chi invia subito aspetta la soglia invece di essere scartato", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "Date"] });
    try {
      const invia = vi
        .spyOn(defaultApiClient, "inviaContributo")
        .mockResolvedValue({ ricevuto: true });
      render(<ContributoEsperto cellId={CELLA} hazard="landslide" />);
      fireEvent.click(screen.getByRole("button", { name: /Sei un esperto/ }));
      fireEvent.change(screen.getByLabelText("Cosa vedi"), {
        target: { value: "Testo incollato già pronto, lungo abbastanza." },
      });
      fireEvent.change(screen.getByLabelText("Nome e cognome"), {
        target: { value: "Maria Rossi" },
      });
      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "maria@example.org" },
      });
      fireEvent.click(screen.getByLabelText(/acconsento al trattamento/));
      fireEvent.click(screen.getByRole("button", { name: "Invia il contributo" }));
      await vi.advanceTimersByTimeAsync(5_000);
      expect(invia).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(1_500);
      expect(invia).toHaveBeenCalledTimes(1);
      expect(invia.mock.calls[0]![0].compilato_in_ms).toBeGreaterThanOrEqual(6_000);
    } finally {
      vi.useRealTimers();
    }
  });

  it("al limite di invii lo dice a parole e tiene i campi", async () => {
    vi.spyOn(defaultApiClient, "inviaContributo").mockRejectedValue(
      new ApiClientError("x", 429, null),
    );
    render(<ContributoEsperto cellId={CELLA} hazard="flood" />);
    compila();
    fireEvent.click(screen.getByRole("button", { name: "Invia il contributo" }));

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Troppi invii in poco tempo: riprova fra un'ora.",
    );
    await waitFor(() =>
      expect((screen.getByLabelText("Nome e cognome") as HTMLInputElement).value).toBe(
        "Maria Rossi",
      ),
    );
  });
});
