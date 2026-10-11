import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import VerifichePage, {
  anticipo,
  verificaDaHash,
} from "../components/VerifichePage";
import { ordina } from "../content/verifiche";
import type { Verifica } from "../content/verifiche";

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
    perche: [
      { nome: "FWI", valore: "48,3", spiegazione: "tempo secco e ventoso" },
    ],
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

  it("scrive l'anticipo in ore, poi in giorni", () => {
    expect(anticipo(null)).toBe("—");
    expect(anticipo(30)).toBe("30 ore");
    expect(anticipo(48)).toBe("2 giorni");
    expect(anticipo(83)).toBe("3 giorni e 11 ore");
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

  it("l'indice pubblica solo gli anticipi e conta il resto come inefficienza", () => {
    render(
      <VerifichePage
        verifiche={[
          verifica(),
          verifica({ slug: "m", titolo: "Frana a Pisticci", esito: "mancata" }),
          verifica({
            slug: "c",
            titolo: "Piena a Bari",
            esito: "contemporanea",
          }),
          verifica({
            slug: "n",
            titolo: "Frana fuori copertura",
            esito: "non_verificabile",
          }),
        ]}
      />,
    );
    expect(
      screen.getByText("Incendio sulle colline di Matera"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Frana a Pisticci")).not.toBeInTheDocument();
    expect(
      screen.getByText(/non previsti in anticipo: 2 su 3 verificati/),
    ).toBeInTheDocument();
    expect(screen.getByText("Non prevista")).toBeInTheDocument();
    expect(screen.getByText("Vista mentre accadeva")).toBeInTheDocument();
    expect(
      screen.getByText(/Un evento non è verificabile/),
    ).toBeInTheDocument();
  });

  it("senza anticipi lo dice, e l'inefficienza resta", () => {
    render(<VerifichePage verifiche={[verifica({ esito: "mancata" })]} />);
    expect(
      screen.getByText(/Nessun evento previsto in anticipo/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/non previsti in anticipo: 1 su 1 verificati/),
    ).toBeInTheDocument();
  });

  it("l'indice vuoto lo dice, senza riquadro", () => {
    render(<VerifichePage verifiche={[]} />);
    expect(
      screen.getByText(/Nessun evento previsto in anticipo/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Inefficienza")).not.toBeInTheDocument();
  });

  it("un link a un evento non previsto apre l'indice, non un articolo", () => {
    window.location.hash = "#/verifiche/m";
    render(
      <VerifichePage verifiche={[verifica({ slug: "m", esito: "mancata" })]} />,
    );
    expect(screen.getByLabelText("Inefficienza")).toBeInTheDocument();
    expect(screen.queryByText("+72 h")).not.toBeInTheDocument();
  });

  it("l'articolo su un'alluvione cita Copernicus e dice che non è un avviso", () => {
    window.location.hash = "#/verifiche/2026-10-10-incendio-matera";
    render(<VerifichePage verifiche={[verifica({ pericolo: "flood" })]} />);
    expect(
      screen.getByText(
        /Copernicus Emergency Management Service, 2026.*non sono un avviso di piena/,
      ),
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
    expect(
      screen.getByRole("link", { name: "Incendio a Matera" }),
    ).toHaveAttribute("href", "https://example.org/articolo");
  });
});
