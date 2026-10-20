// Il modulo di registrazione dei sensori (#253): chiuso non si mostra, aperto
// manda la CSR e mai una chiave privata.

import { fireEvent, render, screen, waitFor } from "../test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RegistrazioneSensore from "../components/RegistrazioneSensore";
import { ApiClientError, defaultApiClient } from "../lib/api-client";

const CSR =
  "-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----";

function aperta(valore: boolean): void {
  vi.spyOn(defaultApiClient, "getRegistrazioneSensori").mockResolvedValue({
    aperta: valore,
  });
}

async function compila(csr: string | null = CSR): Promise<void> {
  await screen.findByLabelText("Tipo di sensore");
  const aperto = Date.now();
  vi.spyOn(Date, "now").mockReturnValue(aperto + 60_000);
  fireEvent.change(screen.getByLabelText(/Latitudine/), {
    target: { value: "40.66" },
  });
  fireEvent.change(screen.getByLabelText(/Longitudine/), {
    target: { value: "16.6" },
  });
  if (csr !== null) {
    fireEvent.change(screen.getByLabelText(/CSR del dispositivo/), {
      target: { value: csr },
    });
  }
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "maker@example.org" },
  });
  fireEvent.click(screen.getByLabelText(/CC BY 4.0/));
  fireEvent.click(screen.getByLabelText(/regole di sicurezza/));
  fireEvent.click(screen.getByLabelText(/informativa/));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("RegistrazioneSensore", () => {
  it("chiusa: nessun campo, solo l'avviso", async () => {
    aperta(false);
    render(<RegistrazioneSensore />);
    expect(await screen.findByText(/non sono ancora aperte/)).toBeTruthy();
    expect(screen.queryByLabelText(/CSR del dispositivo/)).toBeNull();
  });

  it("aperta: manda CSR, posizione e consensi, e ringrazia", async () => {
    aperta(true);
    const invia = vi
      .spyOn(defaultApiClient, "registraSensore")
      .mockResolvedValue({ ricevuta: true });
    render(<RegistrazioneSensore />);
    await compila();
    fireEvent.click(screen.getByRole("button", { name: "Invia la richiesta" }));

    expect(await screen.findByText(/Richiesta inviata/)).toBeTruthy();
    const body = invia.mock.calls[0]![0];
    expect(body).toMatchObject({
      tipo: "pluviometro",
      lat: 40.66,
      lon: 16.6,
      modo: "certificato",
      csr: CSR,
      email: "maker@example.org",
      note: null,
      foto: null,
      licenza: "CC-BY-4.0",
      regole_sicurezza: true,
      informativa: true,
      sito_web: "",
    });
  });

  it("LoRaWAN: manda id, DevEUI e applicazione TTN, senza CSR", async () => {
    aperta(true);
    const invia = vi
      .spyOn(defaultApiClient, "registraSensore")
      .mockResolvedValue({ ricevuta: true });
    render(<RegistrazioneSensore />);
    await screen.findByLabelText("Collegamento");
    fireEvent.change(screen.getByLabelText("Collegamento"), {
      target: { value: "lorawan" },
    });
    expect(screen.queryByLabelText(/CSR del dispositivo/)).toBeNull();
    fireEvent.change(screen.getByLabelText(/^Id del dispositivo/), {
      target: { value: "pluvio-aliano-01" },
    });
    fireEvent.change(screen.getByLabelText(/DevEUI/), {
      target: { value: "70B3D57ED0012345" },
    });
    fireEvent.change(screen.getByLabelText(/applicazione su The Things/), {
      target: { value: "pluviometri-aliano" },
    });
    await compila(null);
    fireEvent.click(screen.getByRole("button", { name: "Invia la richiesta" }));

    expect(await screen.findByText(/Richiesta inviata/)).toBeTruthy();
    const body = invia.mock.calls[0]![0];
    expect(body).toMatchObject({
      modo: "lorawan",
      device_id: "pluvio-aliano-01",
      dev_eui: "70B3D57ED0012345",
      ttn_applicazione: "pluviometri-aliano",
    });
    expect(body).not.toHaveProperty("csr");
  });

  it("una chiave privata incollata blocca l'invio", async () => {
    aperta(true);
    const invia = vi.spyOn(defaultApiClient, "registraSensore");
    render(<RegistrazioneSensore />);
    await compila(
      "-----BEGIN EC PRIVATE KEY-----\nMHcC\n-----END EC PRIVATE KEY-----",
    );
    expect(screen.getByRole("alert").textContent).toMatch(/chiave privata/);
    const bottone = screen.getByRole("button", {
      name: "Invia la richiesta",
    }) as HTMLButtonElement;
    expect(bottone.disabled).toBe(true);
    expect(invia).not.toHaveBeenCalled();
  });

  it("un 422 mostra il motivo del server", async () => {
    aperta(true);
    vi.spyOn(defaultApiClient, "registraSensore").mockRejectedValue(
      new ApiClientError("x", 422, { detail: "l'id 'pluvio-01' è già in uso" }),
    );
    render(<RegistrazioneSensore />);
    await compila();
    fireEvent.click(screen.getByRole("button", { name: "Invia la richiesta" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toMatch(/già in uso/),
    );
  });
});
