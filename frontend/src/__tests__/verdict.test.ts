import { describe, expect, it } from "vitest";

import { verdictFromTotals } from "../lib/verdict";

describe("verdictFromTotals", () => {
  it("la classe alta domina anche con molte moderate", () => {
    const v = verdictFromTotals({ high_or_above: 2, moderate: 900 });
    expect(v.tone).toBe("alert");
    expect(v.text).toContain("2 aree");
  });

  it("accorda il singolare", () => {
    expect(verdictFromTotals({ high_or_above: 1, moderate: 0 }).text).toContain("1 area in classe Alta");
  });

  it("senza alte ma con moderate invita a tenere d'occhio", () => {
    const v = verdictFromTotals({ high_or_above: 0, moderate: 12 });
    expect(v.tone).toBe("watch");
    expect(v.note).toContain("Nessuna area in classe Alta");
  });

  it("a zero non promette che non ci sia rischio", () => {
    const v = verdictFromTotals({ high_or_above: 0, moderate: 0 });
    expect(v.tone).toBe("quiet");
    expect(v.text).toContain("sopra la soglia");
    expect(v.text).not.toContain("nessun rischio");
  });
});

import { verdictFromHazards } from "../lib/verdict";

const blocco = (
  hazard: string,
  label: string,
  high: number,
  moderate: number,
  computed_at: string | null = "2026-09-28T12:00:00Z",
) => ({ hazard, label_it: label, totals: { high_or_above: high, moderate }, computed_at });

describe("verdictFromHazards", () => {
  it("il titolo nomina il pericolo peggiore", () => {
    const v = verdictFromHazards([
      blocco("landslide", "Frana", 0, 77021),
      blocco("flood", "Alluvione", 0, 0),
      blocco("wildfire", "Incendio", 1085, 18179),
    ]);
    expect(v.headline.tone).toBe("alert");
    // Il separatore delle migliaia dipende dai dati di localizzazione, che
    // nel runner non ci sono sempre: qui conta che il pericolo sia nominato
    // e il numero sia quello.
    expect(v.headline.text).toMatch(/^Incendio: 1\.?085 aree in classe Alta o superiore$/);
  });

  it("mette per primo chi ha qualcosa da dire", () => {
    const v = verdictFromHazards([
      blocco("flood", "Alluvione", 0, 0),
      blocco("wildfire", "Incendio", 3, 0),
      blocco("landslide", "Frana", 0, 12),
    ]);
    expect(v.lines.map((l) => l.hazard)).toEqual(["wildfire", "landslide", "flood"]);
  });

  it("restituisce sempre una riga per pericolo, anche a zero", () => {
    const v = verdictFromHazards([
      blocco("landslide", "Frana", 0, 0),
      blocco("flood", "Alluvione", 0, 0),
      blocco("wildfire", "Incendio", 0, 0),
    ]);
    expect(v.lines).toHaveLength(3);
    expect(v.headline.tone).toBe("quiet");
    expect(v.headline.note).toContain("3 pericoli");
  });

  it("a parità di tono l'ordine non balla fra un aggiornamento e l'altro", () => {
    const uno = verdictFromHazards([blocco("wildfire", "Incendio", 1, 0), blocco("flood", "Alluvione", 1, 0)]);
    const due = verdictFromHazards([blocco("flood", "Alluvione", 1, 0), blocco("wildfire", "Incendio", 1, 0)]);
    expect(uno.lines.map((l) => l.hazard)).toEqual(due.lines.map((l) => l.hazard));
  });

  it("porta con sé l'età del dato di ciascuno", () => {
    const v = verdictFromHazards([
      blocco("landslide", "Frana", 0, 1, "2026-09-28T12:00:00Z"),
      blocco("flood", "Alluvione", 0, 0, "2026-09-26T09:00:00Z"),
    ]);
    expect(v.lines.find((l) => l.hazard === "flood")?.computed_at).toBe("2026-09-26T09:00:00Z");
  });
});
