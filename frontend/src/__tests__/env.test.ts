import { describe, expect, it } from "vitest";

import { bool, num } from "../lib/env";

// Docker passa `${VAR:-}` come stringa **vuota**, non come variabile assente:
// e' la trappola che ha aperto la mappa a 0°,0° in mezzo all'Atlantico e le ha
// tolto i caratteri lasciandola bianca. Vuoto significa "non impostato".
describe("lettura delle variabili d'ambiente", () => {
  it("una stringa vuota non vale zero", () => {
    expect(num("", 16.6)).toBe(16.6);
    expect(num("   ", 40.5)).toBe(40.5);
    expect(num(undefined, 7)).toBe(7);
  });

  it("un numero valido vince sul default", () => {
    expect(num("12.4964", 16.6)).toBe(12.4964);
    expect(num("0", 16.6)).toBe(0);
  });

  it("un valore non numerico ricade sul default", () => {
    expect(num("roma", 16.6)).toBe(16.6);
  });

  it("una stringa vuota non spegne un default acceso", () => {
    expect(bool("", true)).toBe(true);
    expect(bool("   ", true)).toBe(true);
    expect(bool("false", true)).toBe(false);
    expect(bool("1", false)).toBe(true);
  });
});
