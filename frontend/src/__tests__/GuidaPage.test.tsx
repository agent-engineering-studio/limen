import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import GuidaPage, { sezioneDaHash } from "../components/GuidaPage";
import { ALPINE, PLAIN, simulate } from "../components/Simulatore";

afterEach(() => {
  window.location.hash = "";
});

describe("sezioneDaHash", () => {
  it("senza sotto-rotta non chiede nessuna sezione", () => {
    expect(sezioneDaHash("#/come-funziona")).toBeNull();
    expect(sezioneDaHash("#/come-funziona/")).toBeNull();
  });

  it("legge la sezione", () => {
    expect(sezioneDaHash("#/come-funziona/i-tre-motori")).toBe("i-tre-motori");
  });

  it("ignora le altre rotte", () => {
    expect(sezioneDaHash("#/documentazione/glossario")).toBeNull();
  });
});

describe("GuidaPage", () => {
  it("l'indice ha una voce per sezione, e ogni voce porta a un titolo vero", () => {
    const { container } = render(<GuidaPage />);
    const nav = screen.getByRole("navigation", { name: /indice della guida/i });
    const voci = [...nav.querySelectorAll("a")];
    expect(voci.length).toBeGreaterThanOrEqual(10);
    for (const voce of voci) {
      const slug = sezioneDaHash(voce.getAttribute("href") ?? "");
      expect(container.querySelector(`#guida-${slug ?? ""}`)).not.toBeNull();
    }
  });

  it("copre i layer chiesti: dati, motori, previsione, ML, AI, geografia", () => {
    render(<GuidaPage />);
    for (const titolo of [
      /Il layer dati/,
      /I tre motori/,
      /La previsione/,
      /Il layer machine learning/,
      /Il layer AI/,
      /Il territorio in celle/,
    ]) {
      expect(screen.getByRole("heading", { level: 2, name: titolo })).toBeTruthy();
    }
  });

  it("rende le tabelle come tabelle, non come righe con le barre", () => {
    const { container } = render(<GuidaPage />);
    expect(container.querySelectorAll("table").length).toBeGreaterThan(8);
    expect(container.textContent).not.toContain("|---|");
  });

  it("incorpora il simulatore al posto del marcatore", () => {
    const { container } = render(<GuidaPage />);
    expect(screen.getByLabelText(/Pioggia nelle ultime 24 ore/)).toBeInTheDocument();
    expect(container.textContent).not.toContain("componente:");
  });

  it("non lascia in pagina il codice grezzo dei blocchi mermaid", () => {
    const { container } = render(<GuidaPage />);
    expect(container.textContent).not.toContain("flowchart");
  });

  it("i link dei vecchi indirizzi delle sezioni portano ad ancore esistenti", () => {
    const { container } = render(<GuidaPage />);
    for (const slug of ["limiti-dichiarati", "i-tre-motori"]) {
      expect(container.querySelector(`#guida-${slug}`)).not.toBeNull();
    }
  });
});

describe("simulate (formula di produzione)", () => {
  it("la pioggia forte alza il rischio sul versante predisposto", () => {
    const dry = simulate(ALPINE, 0, 60, 0.2, 0);
    const wet = simulate(ALPINE, 120, 200, 0.45, 0);
    expect(wet.risk).toBeGreaterThan(dry.risk);
    expect(wet.classIndex).toBeGreaterThanOrEqual(3);
  });

  it("la stessa tempesta in pianura quasi non si sente", () => {
    const wet = simulate(PLAIN, 120, 200, 0.45, 0);
    expect(wet.risk).toBeLessThan(0.55);
  });

  it("la pioggia su neve aggiunge a M, la neve senza pioggia no", () => {
    const ros = simulate(ALPINE, 40, 120, 0.35, 0.5);
    const noSnow = simulate(ALPINE, 40, 120, 0.35, 0);
    const drySnow = simulate(ALPINE, 0, 120, 0.35, 0.5);
    expect(ros.m).toBeGreaterThan(noSnow.m);
    expect(drySnow.snow).toBe(0);
  });
});
