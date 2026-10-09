import { describe, expect, it } from "vitest";

import { sullOrigine } from "../lib/env";

describe("sullOrigine", () => {
  it("un percorso diventa un URL sul dominio della pagina", () => {
    expect(sullOrigine("/", "https://limen.agentengineering.it")).toBe(
      "https://limen.agentengineering.it",
    );
    expect(sullOrigine("/tiles", "https://office-gdc.w3pro.it")).toBe(
      "https://office-gdc.w3pro.it/tiles",
    );
  });

  it("un URL assoluto resta com'è", () => {
    expect(sullOrigine("https://office-gdc.w3pro.it", "https://altro.it")).toBe(
      "https://office-gdc.w3pro.it",
    );
  });
});
