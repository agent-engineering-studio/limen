// I dati di base della cella con la fonte accanto (#422).

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DatiDiBase from "../components/DatiDiBase";
import { render } from "../test-utils";
import type { DatoDiBase } from "../types";

const DATI: DatoDiBase[] = [
  {
    id: "impermeabilizzazione",
    nome: "suolo impermeabilizzato (CLMS)",
    colonna: "imperviousness_norm",
    stato: "presente",
    valore: 0.42,
    classe: null,
    lettura: "suolo impermeabilizzato al 42 %",
    fonte: "Copernicus Land Monitoring Service — Imperviousness Density 2018 (EEA)",
    licenza: "Copernicus, accesso libero",
    attribuzione: "Generated using European Union's Copernicus Land Monitoring Service information",
    url: "https://land.copernicus.eu",
  },
  {
    id: "idraulica",
    nome: "pericolosità idraulica ISPRA",
    colonna: "flood_hazard_norm",
    stato: "assente_qui",
    valore: null,
    classe: null,
    lettura: "fuori dalle aree a pericolosità idraulica",
    fonte: "ISPRA IdroGEO",
    licenza: "CC BY-SA 4.0",
    attribuzione: null,
    url: null,
  },
];

describe("DatiDiBase", () => {
  it("mostra la lettura con l'attribuzione accanto", () => {
    render(<DatiDiBase dati={DATI} />);
    expect(screen.getByText("Dati di base")).toBeInTheDocument();
    expect(screen.getByText("suolo impermeabilizzato al 42 %")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Copernicus Land Monitoring Service/ });
    expect(link).toHaveAttribute("href", "https://land.copernicus.eu");
    expect(screen.getByText("fuori dalle aree a pericolosità idraulica")).toHaveClass("is-vuoto");
    // Senza attribuzione si cita la fonte, mai niente.
    expect(screen.getByText(/ISPRA IdroGEO/)).toBeInTheDocument();
  });

  it("non disegna niente senza dati", () => {
    const { container } = render(<DatiDiBase dati={[]} />);
    expect(container.querySelector(".dati-di-base")).toBeNull();
  });
});

describe("DatiDiBase in inglese", () => {
  it("ricompone la lettura dal valore grezzo", () => {
    render(<DatiDiBase dati={DATI} />, { lingua: "en" });
    expect(screen.getByText("Base data")).toBeInTheDocument();
    expect(screen.getByText("42 % sealed soil")).toBeInTheDocument();
    expect(screen.getByText("outside the flood-hazard areas")).toBeInTheDocument();
  });
});

describe("DatiDiBase, CORINE (#470)", () => {
  const CORINE: DatoDiBase = {
    id: "corine",
    nome: "copertura del suolo (CORINE)",
    colonna: "landuse_code",
    stato: "presente",
    valore: "312",
    classe: null,
    nome_classe_en: "Coniferous forest",
    lettura: "Boschi di conifere (CORINE 312)",
    fonte: "CORINE Land Cover 2018 (SINAnet / ISPRA)",
    licenza: "Copernicus, accesso libero",
    attribuzione: null,
    url: null,
  };

  it("mostra il nome della classe, non solo il codice", () => {
    render(<DatiDiBase dati={[CORINE]} />);
    expect(screen.getByText("Boschi di conifere (CORINE 312)")).toBeInTheDocument();
  });

  it("in inglese usa il nome inglese della legenda", () => {
    render(<DatiDiBase dati={[CORINE]} />, { lingua: "en" });
    expect(screen.getByText("Coniferous forest (CORINE 312)")).toBeInTheDocument();
  });
});

describe("DatiDiBase, completezza (#484)", () => {
  const C = {
    presenti: 7,
    totali: 9,
    dati_mancanti: ["dtm"],
    segnali_mancanti: ["portata"],
    lettura: "7 ingredienti su 9; mancano: pendenza (DTM), portata del fiume (GloFAS)",
  };

  it("dice a parole su quanti ingredienti poggia il punteggio", () => {
    render(<DatiDiBase dati={DATI} completezza={C} />);
    expect(screen.getByText(C.lettura)).toHaveClass("is-vuoto");
  });

  it("in inglese ricompone i nomi", () => {
    render(<DatiDiBase dati={DATI} completezza={C} />, { lingua: "en" });
    expect(
      screen.getByText("7 of 9 inputs; missing: slope (DTM), river discharge (GloFAS)"),
    ).toBeInTheDocument();
  });

  it("tutto presente non è scritto in grigio", () => {
    const pieno = { ...C, presenti: 9, dati_mancanti: [], segnali_mancanti: [], lettura: "9 ingredienti su 9, tutti presenti" };
    render(<DatiDiBase dati={DATI} completezza={pieno} />);
    expect(screen.getByText(pieno.lettura)).not.toHaveClass("is-vuoto");
  });
});
