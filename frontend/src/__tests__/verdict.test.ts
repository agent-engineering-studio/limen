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
