// La guida «Partecipare» (#511): una sezione per chi legge, con i moduli per
// segnalare un evento e contestare un punteggio, e l'avviso di emergenza.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PartecipaPage } from "../components/PartecipaPage";
import {
  PARTECIPARE_MARKDOWN,
  PARTECIPARE_MARKDOWN_EN,
} from "../content/partecipare";
import { render as renderLingua } from "../test-utils";

describe("PartecipaPage", () => {
  it("ha una sezione per chi vede un evento, chi fa ricerca e gli enti", () => {
    render(<PartecipaPage />);
    expect(screen.getByText("Partecipare")).toBeInTheDocument();
    for (const titolo of [
      "Chi vede un evento: segnalarlo",
      "Chi fa ricerca: rifare i conti e contestarli",
      "Enti locali e Protezione civile: eventi, prove pilota, pareri",
    ]) {
      expect(screen.getAllByText(titolo).length).toBeGreaterThan(0);
    }
  });

  it("porta ai due moduli e dice che non è un canale di emergenza", () => {
    for (const testo of [PARTECIPARE_MARKDOWN, PARTECIPARE_MARKDOWN_EN]) {
      expect(testo).toContain("template=evento.yml");
      expect(testo).toContain("template=contesta-punteggio.yml");
      expect(testo).toMatch(/\*\*112\*\*/);
    }
  });

  it("in inglese tiene le stesse ancore", () => {
    const { container } = renderLingua(<PartecipaPage />, { lingua: "en" });
    expect(screen.getByText("Take part")).toBeInTheDocument();
    const hrefs = [...container.querySelectorAll(".guida-indice a")].map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).toContain("#/partecipare/chi-vede-un-evento-segnalarlo");
  });
});
