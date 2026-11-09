// L'informativa sui dati personali (#494): titolare, conservazione, diritti,
// in entrambe le lingue, e i link dai moduli che chiedono dati.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PrivacyPage } from "../components/PrivacyPage";
import { PRIVACY_MARKDOWN, PRIVACY_MARKDOWN_EN } from "../content/privacy";
import { render as renderLingua } from "../test-utils";

describe("PrivacyPage", () => {
  it("dice chi è il titolare, quanto si conserva e quali sono i diritti", () => {
    render(<PrivacyPage />);
    expect(screen.getByText("Dati personali")).toBeInTheDocument();
    for (const titolo of [
      "Chi è il titolare",
      "Che cosa entra, perché, per quanto",
      "I tuoi diritti",
    ]) {
      expect(screen.getAllByText(titolo).length).toBeGreaterThan(0);
    }
  });

  it("dichiara i tempi di conservazione dei registri e delle mail", () => {
    expect(PRIVACY_MARKDOWN).toMatch(/14 giorni/);
    expect(PRIVACY_MARKDOWN).toMatch(/un'ora; mai scritto su disco/);
    expect(PRIVACY_MARKDOWN).toMatch(/cancellata dopo 12 mesi/);
    expect(PRIVACY_MARKDOWN_EN).toMatch(/14 days/);
    expect(PRIVACY_MARKDOWN_EN).toMatch(/deleted after 12 months/);
  });

  it("in inglese tiene le stesse ancore", () => {
    const { container } = renderLingua(<PrivacyPage />, { lingua: "en" });
    expect(screen.getByText("Personal data")).toBeInTheDocument();
    const hrefs = [...container.querySelectorAll(".guida-indice a")].map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).toContain("#/privacy/chi-e-il-titolare");
  });
});
