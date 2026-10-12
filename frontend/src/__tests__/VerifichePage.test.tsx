import { afterEach, describe, expect, it } from "vitest";

import VerifichePage, { anticipo, verificaDaHash } from "../components/VerifichePage";
import { ordina, verificate } from "../content/verifiche";
import type { Verifica } from "../content/verifiche";
import { render, screen } from "../test-utils";

function verifica(over: Partial<Verifica> = {}): Verifica {
  return {
    slug: "2026-10-10-incendio-matera",
    titolo: "Incendio sulle colline di Matera",
    pericolo: "wildfire",
    esito: "anticipata",
    evento: {
      quando: "2026-10-10T13:00:00Z",
      luogo: "Matera (MT)",
      regione: "Basilicata",
      comuni: [{ istat: "077014", nome: "Matera" }],
    },
    pubblicato: "2026-10-11T08:00:00Z",
    aggiornato: "2026-10-11T08:00:00Z",
    sommario: "Il fronte è partito nel primo pomeriggio.",
    corpo: ["Limen lo aveva in classe molto alta da tre giorni."],
    fonti: [
      {
        testata: "La Gazzetta del Mezzogiorno",
        titolo: "Incendio a Matera",
        url: "https://example.org/articolo",
        data: "2026-10-10",
      },
    ],
    foto: [],
    previsione: {
      anticipo_ore_moderato: 83,
      anticipo_ore_alto: 83,
      classe_max: "VeryHigh",
      allerta_prima: "2026-10-07T15:57:00Z",
      corse: [
        {
          run_at: "2026-10-07T02:07:00Z",
          horizon_h: 72,
          target_at: "2026-10-10T02:07:00Z",
          classe: "VeryHigh",
          score: 0.855,
        },
      ],
    },
    perche: [{ nome: "FWI", valore: "48,3", spiegazione: "tempo secco e ventoso" }],
    en: {
      titolo: "Wildfire on the hills of Matera",
      luogo: "Matera (MT)",
      sommario: "The fire started in the early afternoon.",
      corpo: ["Limen had it in the very high class for three days."],
      perche: [{ nome: "FWI", valore: "48.3", spiegazione: "dry and windy weather" }],
      foto: [],
    },
    ...over,
  };
}

describe("VerifichePage", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("legge lo slug dall'hash, query esclusa", () => {
    expect(verificaDaHash("#/verifiche")).toBeNull();
    expect(verificaDaHash("#/verifiche/abc?x=1")).toBe("abc");
    expect(verificaDaHash("#/regioni/abc")).toBeNull();
  });

  it("scrive l'anticipo in ore, poi in giorni, nelle due lingue", () => {
    expect(anticipo(null)).toBe("—");
    expect(anticipo(30)).toBe("30 ore");
    expect(anticipo(48)).toBe("2 giorni");
    expect(anticipo(83)).toBe("3 giorni e 11 ore");
    expect(anticipo(30, "en")).toBe("30 hours");
    expect(anticipo(83, "en")).toBe("3 days and 11 hours");
  });

  it("ordina dalla più recente", () => {
    const vecchia = verifica({
      slug: "vecchia",
      evento: { ...verifica().evento, quando: "2026-09-01T00:00:00Z" },
    });
    expect(ordina([vecchia, verifica()]).map((v) => v.slug)).toEqual([
      "2026-10-10-incendio-matera",
      "vecchia",
    ]);
  });

  it("tiene solo gli eventi anticipati con l'inglese completo", () => {
    const mancata = { ...verifica({ slug: "m" }), esito: "mancata" } as unknown as Verifica;
    const senzaInglese = { ...verifica({ slug: "s" }), en: undefined } as unknown as Verifica;
    const disallineata = verifica({
      slug: "d",
      en: { ...verifica().en, corpo: [] },
    });
    expect(verificate([verifica(), mancata, senzaInglese, disallineata]).map((v) => v.slug)).toEqual(
      ["2026-10-10-incendio-matera"],
    );
  });

  it("l'indice mostra gli articoli con l'anticipo, e nient'altro", () => {
    render(<VerifichePage verifiche={[verifica()]} />);
    expect(screen.getByText("Incendio sulle colline di Matera")).toBeInTheDocument();
    expect(screen.getByText(/anticipo 3 giorni e 11 ore/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Inefficienza")).not.toBeInTheDocument();
  });

  it("l'indice vuoto lo dice", () => {
    render(<VerifichePage verifiche={[]} />);
    expect(screen.getByText(/Nessun evento previsto in anticipo/)).toBeInTheDocument();
  });

  it("in inglese l'indice usa il blocco en", () => {
    render(<VerifichePage verifiche={[verifica()]} />, { lingua: "en" });
    expect(screen.getByText("Wildfire on the hills of Matera")).toBeInTheDocument();
    expect(screen.getByText(/lead time 3 days and 11 hours/)).toBeInTheDocument();
    expect(screen.queryByText("Incendio sulle colline di Matera")).not.toBeInTheDocument();
  });

  it("l'articolo su un'alluvione cita Copernicus e dice che non è un avviso", () => {
    window.location.hash = "#/verifiche/2026-10-10-incendio-matera";
    render(<VerifichePage verifiche={[verifica({ pericolo: "flood" })]} />);
    expect(
      screen.getByText(/Copernicus Emergency Management Service, 2026.*non sono un avviso di piena/),
    ).toBeInTheDocument();
  });

  it("l'articolo su un incendio non porta la clausola GloFAS", () => {
    window.location.hash = "#/verifiche/2026-10-10-incendio-matera";
    render(<VerifichePage verifiche={[verifica()]} />);
    expect(screen.queryByText(/avviso di piena/)).not.toBeInTheDocument();
  });

  it("l'articolo mostra anticipo, corse, perché e fonti", () => {
    window.location.hash = "#/verifiche/2026-10-10-incendio-matera";
    render(<VerifichePage verifiche={[verifica()]} />);
    expect(screen.getAllByText("3 giorni e 11 ore")).toHaveLength(2);
    expect(screen.getByText("+72 h")).toBeInTheDocument();
    expect(screen.getByText("FWI")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Incendio a Matera" })).toHaveAttribute(
      "href",
      "https://example.org/articolo",
    );
  });

  it("l'articolo in inglese traduce testo ed etichette, non le fonti", () => {
    window.location.hash = "#/verifiche/2026-10-10-incendio-matera";
    render(<VerifichePage verifiche={[verifica()]} />, { lingua: "en" });
    expect(screen.getByRole("heading", { name: "Wildfire on the hills of Matera" })).toBeInTheDocument();
    expect(screen.getByText("Lead time (≥ moderate)")).toBeInTheDocument();
    expect(screen.getAllByText("3 days and 11 hours")).toHaveLength(2);
    expect(screen.getByText(/dry and windy weather/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Incendio a Matera" })).toBeInTheDocument();
  });
});
