import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import DocsPage, { slugFromHash } from "../components/DocsPage";

afterEach(() => {
  window.location.hash = "";
});

describe("slugFromHash", () => {
  it("senza sotto-rotta apre l'indice", () => {
    expect(slugFromHash("#/documentazione")).toBe("indice");
  });

  it("uno slug inesistente non lascia la pagina vuota", () => {
    expect(slugFromHash("#/documentazione/non-esiste")).toBe("indice");
  });

  it("riconosce una pagina vera", () => {
    expect(slugFromHash("#/documentazione/glossario")).toBe("glossario");
  });
});

describe("DocsPage", () => {
  it("mostra l'indice con il collegamento a ogni pagina", () => {
    window.location.hash = "#/documentazione";
    render(<DocsPage />);
    const nav = screen.getByRole("navigation", { name: /pagine della documentazione/i });
    expect(nav.querySelectorAll("a").length).toBeGreaterThanOrEqual(8);
  });

  it("apre la pagina chiesta dall'hash e ne rende il titolo", () => {
    window.location.hash = "#/documentazione/glossario";
    render(<DocsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Glossario" })).toBeTruthy();
  });

  it("rende lo schema del flusso evidenziando la fase della pagina", () => {
    window.location.hash = "#/documentazione/02-come-si-calcola-il-rischio";
    const { container } = render(<DocsPage />);
    const highlighted = container.querySelectorAll(".flow-step.on");
    expect(highlighted.length).toBeGreaterThan(0);
    expect([...highlighted].some((el) => el.getAttribute("data-phase") === "punteggio")).toBe(
      true,
    );
  });

  it("non lascia in pagina il codice grezzo dei blocchi mermaid", () => {
    window.location.hash = "#/documentazione/03-cosa-fanno-ml-e-ai";
    const { container } = render(<DocsPage />);
    expect(container.textContent).not.toContain("flowchart");
  });

  it("l'indice non pubblica le parentesi quadre al posto dei link", () => {
    window.location.hash = "#/documentazione/indice";
    const { container } = render(<DocsPage />);
    expect(container.textContent).not.toContain("](./");
    const inStrong = container.querySelectorAll("strong a");
    expect(inStrong.length).toBeGreaterThan(5);
  });

  it("i rimandi fra pagine restano dentro l'applicazione", () => {
    window.location.hash = "#/documentazione/indice";
    const { container } = render(<DocsPage />);
    const internal = [...container.querySelectorAll("a")].filter((a) =>
      a.getAttribute("href")?.startsWith("#/documentazione/"),
    );
    expect(internal.length).toBeGreaterThan(5);
  });
});
