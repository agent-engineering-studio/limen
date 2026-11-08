import { describe, expect, it } from "vitest";

import { sullOrigine } from "../lib/env";

describe("sullOrigine", () => {
  it("un percorso diventa un URL sul dominio della pagina", () => {
    expect(sullOrigine("/", "https://limen.example.org")).toBe(
      "https://limen.example.org",
    );
    expect(sullOrigine("/tiles", "https://rischio.example.it")).toBe(
      "https://rischio.example.it/tiles",
    );
  });

  it("un URL assoluto resta com'è", () => {
    expect(sullOrigine("https://rischio.example.it", "https://altro.it")).toBe(
      "https://rischio.example.it",
    );
  });
});
