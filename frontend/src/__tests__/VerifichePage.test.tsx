import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import VerifichePage, { anticipo, verificaDaHash } from "../components/VerifichePage";
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
    perche: [{ nome: "FWI", valore: "48,3", spiegazione: "tempo secco e ventoso" }],
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

  it("l'indice elenca le verifiche, anche quelle mancate", () => {
    render(
      <VerifichePage
        verifiche={[verifica(), verifica({ slug: "m", titolo: "Frana a Pisticci", esito: "mancata" })]}
      />,
    );
    expect(screen.getByText("Incendio sulle colline di Matera")).toBeInTheDocument();
    expect(screen.getByText("Frana a Pisticci")).toBeInTheDocument();
    expect(screen.getByText("Non prevista")).toBeInTheDocument();
  });

  it("l'indice vuoto lo dice", () => {
    render(<VerifichePage verifiche={[]} />);
    expect(screen.getByText(/Nessuna verifica pubblicata/)).toBeInTheDocument();
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
});
