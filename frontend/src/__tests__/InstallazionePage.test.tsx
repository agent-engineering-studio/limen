import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InstallazionePage, {
  daCaricare,
  percentuale,
  semaforo,
} from "../components/InstallazionePage";
import { ApiClientError, defaultApiClient } from "../lib/api-client";
import { render as renderLingua } from "../test-utils";
import type { InstallazioneStato, VoceDato } from "../types";

function voce(id: string, extra: Partial<VoceDato> = {}): VoceDato {
  return {
    id,
    nome: `nome ${id}`,
    a_cosa_serve: `serve a ${id}`,
    pericoli: ["landslide"],
    livello: "essenziale",
    fonte: "ISPRA",
    url: "https://idrogeo.isprambiente.it",
    licenza: "CC-BY 4.0",
    attribuzione: "ISPRA",
    peso_gb: 1,
    deriva_da: null,
    copertura: 1000,
    regioni_senza: [],
    download: null,
    ...extra,
  };
}

function stato(extra: Partial<InstallazioneStato> = {}): InstallazioneStato {
  return {
    celle_totali: 312550,
    regioni: 20,
    elenco_regioni: [
      { id: "it-basilicata", nome: "Basilicata", celle: 10353, semina: null },
      { id: "it-lazio", nome: "Lazio", celle: 0, semina: null },
      { id: "it-molise", nome: "Molise", celle: 0, semina: null },
    ],
    pericoli: [
      { pericolo: "landslide", pronto: true, mancano: [] },
      { pericolo: "flood", pronto: false, mancano: ["idraulica"] },
      { pericolo: "wildfire", pronto: true, mancano: [] },
    ],
    voci: [
      voce("dtm", { pericoli: ["landslide", "wildfire"] }),
      voce("idraulica", { pericoli: ["flood"], copertura: 0 }),
      voce("strade", { livello: "consigliato", copertura: 0 }),
      voce("wui", { pericoli: ["wildfire"], livello: "consigliato", deriva_da: "corine" }),
    ],
    elaborazione: null,
    azioni_abilitate: true,
    ...extra,
  };
}

describe("semaforo (puro)", () => {
  it("rosso quando manca un essenziale, con la voce che lo spiega", () => {
    const r = semaforo("flood", stato());
    expect(r.colore).toBe("rosso");
    expect(r.mancano.map((v) => v.id)).toEqual(["idraulica"]);
  });

  it("giallo quando mancano solo consigliati", () => {
    const r = semaforo("landslide", stato());
    expect(r.colore).toBe("giallo");
    expect(r.mancano.map((v) => v.id)).toEqual(["strade"]);
  });

  it("verde quando c'è tutto", () => {
    expect(semaforo("wildfire", stato()).colore).toBe("verde");
  });

  it("rosso per tutti se le regioni non sono seminate", () => {
    const vuoto = stato({ celle_totali: 0 });
    expect(semaforo("wildfire", vuoto).colore).toBe("rosso");
  });
});

describe("percentuale e daCaricare", () => {
  const dl = { stato: "in_corso" as const, aggiornato_il: "", errore: null };
  it("non supera il 100 % e tace senza totale", () => {
    expect(percentuale({ ...dl, byte_fatti: 5, byte_totali: 20 })).toBe(25);
    expect(percentuale({ ...dl, byte_fatti: 30, byte_totali: 20 })).toBe(100);
    expect(percentuale({ ...dl, byte_fatti: 30, byte_totali: null })).toBeNull();
  });

  it("scaricato ma senza celle è da caricare", () => {
    const fatto = { ...dl, stato: "fatto" as const, byte_fatti: 1, byte_totali: 1 };
    expect(daCaricare(voce("iffi", { copertura: 0, download: fatto }))).toBe(true);
    expect(daCaricare(voce("iffi", { download: fatto }))).toBe(false);
  });
});

describe("InstallazionePage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    window.location.hash = "#/installazione";
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra i tre pericoli con la parola, non solo il colore", async () => {
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(stato());
    render(<InstallazionePage />);
    expect(await screen.findByText("Non pronto")).toBeInTheDocument();
    expect(screen.getByText("Parziale")).toBeInTheDocument();
    expect(screen.getByText("Pronto")).toBeInTheDocument();
    expect(screen.getAllByText(/serve a idraulica/).length).toBeGreaterThan(0);
  });

  it("aggiunge le regioni scelte con il token (#407)", async () => {
    window.location.hash = "#/installazione?token=segreto123";
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(stato());
    const aggiungi = vi
      .spyOn(defaultApiClient, "aggiungiRegioni")
      .mockResolvedValue({ accodate: ["regione:it-lazio"], gia_in_corso: [] });
    render(<InstallazionePage />);

    expect(await screen.findByText("Basilicata")).toBeInTheDocument();
    const bottone = screen.getByRole("button", { name: /Aggiungi la regione scelta|Aggiungi le/ });
    expect(bottone).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Lazio" }));
    fireEvent.click(screen.getByRole("button", { name: "Aggiungi la regione scelta" }));
    await waitFor(() => expect(aggiungi).toHaveBeenCalledWith(["it-lazio"], "segreto123"));
  });

  it("senza token le regioni non si scelgono", async () => {
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(stato());
    render(<InstallazionePage />);
    expect(await screen.findByRole("checkbox", { name: "Lazio" })).toBeDisabled();
  });

  it("prende il token dal link, lo toglie dall'indirizzo e lo usa per scaricare", async () => {
    window.location.hash = "#/installazione?token=segreto123";
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(stato());
    const avvia = vi
      .spyOn(defaultApiClient, "avviaDownload")
      .mockResolvedValue({ accodate: ["idraulica"], gia_in_corso: [] });
    render(<InstallazionePage />);

    expect(window.location.hash).toBe("#/installazione");
    expect(sessionStorage.getItem("limen-installazione-token")).toBe("segreto123");

    fireEvent.click(await screen.findByRole("button", { name: /tutti i dati essenziali/ }));
    expect(avvia).toHaveBeenCalledWith(["idraulica"], "segreto123");
    expect(await screen.findByText(/1 download in coda/)).toBeInTheDocument();
  });

  it("un token rifiutato si dimentica e lo si dice", async () => {
    sessionStorage.setItem("limen-installazione-token", "vecchio");
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(stato());
    vi.spyOn(defaultApiClient, "avviaDownload").mockRejectedValue(
      new ApiClientError("no", 401, null),
    );
    render(<InstallazionePage />);
    const [primo] = await screen.findAllByRole("button", { name: "Scarica" });
    fireEvent.click(primo!);
    expect(await screen.findByText(/token non è valido/)).toBeInTheDocument();
    await waitFor(() => expect(sessionStorage.getItem("limen-installazione-token")).toBeNull());
  });

  it("dice che sta caricando nelle celle, senza chiedere comandi", async () => {
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(
      stato({
        elaborazione: {
          stato: "in_corso",
          byte_fatti: 0,
          byte_totali: null,
          aggiornato_il: "2026-11-05T10:00:00Z",
          errore: null,
        },
      }),
    );
    render(<InstallazionePage />);
    expect(await screen.findByText(/sta caricando nelle celle/)).toBeInTheDocument();
    expect(screen.queryByText(/make static-data/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Riprova" })).not.toBeInTheDocument();
  });

  it("un caricamento fallito mostra il motivo e si può rifare con il token", async () => {
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(
      stato({
        elaborazione: {
          stato: "errore",
          byte_fatti: 0,
          byte_totali: null,
          aggiornato_il: "2026-11-05T10:00:00Z",
          errore: "Non è riuscito: calibrate.",
        },
      }),
    );
    const rifai = vi
      .spyOn(defaultApiClient, "avviaElaborazione")
      .mockResolvedValue({ accodate: ["elaborazione"], gia_in_corso: [] });
    window.location.hash = "#/installazione?token=segreto";
    render(<InstallazionePage />);
    expect(await screen.findByText(/Non è riuscito: calibrate/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Riprova" }));
    await waitFor(() => expect(rifai).toHaveBeenCalledWith("segreto"));
  });

  it("senza token sul server non mostra pulsanti", async () => {
    sessionStorage.setItem("limen-installazione-token", "qualsiasi");
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(
      stato({ azioni_abilitate: false }),
    );
    render(<InstallazionePage />);
    expect(await screen.findByText(/azioni sono disabilitate/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Scarica" })).toBeNull();
  });

  it("in inglese", async () => {
    vi.spyOn(defaultApiClient, "getInstallazioneStato").mockResolvedValue(stato());
    renderLingua(<InstallazionePage />, { lingua: "en" });
    expect(await screen.findByText("Not ready")).toBeInTheDocument();
    expect(screen.getByText("Is Limen ready?")).toBeInTheDocument();
  });
});
