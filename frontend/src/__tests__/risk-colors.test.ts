import { describe, expect, it } from "vitest";

import { COLORE_IGNOTO, RISK_CLASSES, maplibreColorMatch } from "../lib/risk-colors";

/** L'espressione di classe, dentro il `case` che la protegge. */
function scala(expr: unknown[]): unknown[] {
  return expr[3] as unknown[];
}

describe("maplibreColorMatch", () => {
  it("defaults to the risk_level property (cell/region tiles)", () => {
    const expr = maplibreColorMatch() as unknown[];
    expect(scala(expr)[0]).toBe("match");
    expect(scala(expr)[1]).toEqual(["get", "risk_level"]);
  });

  it("binds to worst_class for the comune rollup layer", () => {
    const expr = maplibreColorMatch("worst_class") as unknown[];
    expect(scala(expr)[1]).toEqual(["get", "worst_class"]);
    // still maps every class to a colour + a neutral fallback at the end
    const inner = scala(expr);
    expect(typeof inner[inner.length - 1]).toBe("string");
  });

  it("una cella non misurata è neutra, non in fondo alla scala", () => {
    // Uno zero per assenza di dato, dipinto nella classe più tranquilla, si
    // legge come una buona notizia: è l'unico posto in cui questo sistema
    // sbaglierebbe in direzione rassicurante (#143).
    const expr = maplibreColorMatch() as unknown[];
    expect(expr[0]).toBe("case");
    expect(expr[1]).toEqual(["==", ["get", "measured"], false]);
    expect(expr[2]).toBe(COLORE_IGNOTO);
  });

  it("le tile senza l'attributo restano colorate", () => {
    // `measured` manca sulle tile scritte prima che la colonna esistesse, e
    // `["==", ["get", "measured"], false]` su un attributo assente è falso:
    // si cade sulla scala, che è il comportamento giusto per «non lo so».
    const expr = maplibreColorMatch() as unknown[];
    expect(expr[1]).toEqual(["==", ["get", "measured"], false]);
    expect(scala(expr)[0]).toBe("match");
  });
});

// Machado, Oliveira, Fernandes 2009, severità 1, su RGB lineare.
const CVD: Record<string, number[][]> = {
  deuteranopia: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  protanopia: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  tritanopia: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
};

function lineare(hex: string): number[] {
  return [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
}

function luminanza(v: number[]): number {
  return 0.2126 * v[0]! + 0.7152 * v[1]! + 0.0722 * v[2]!;
}

function contrasto(a: number[], b: number[]): number {
  const [x, y] = [luminanza(a), luminanza(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

describe("la scala del rischio sul fondo scuro", () => {
  it("ogni coppia di classi resta distinguibile anche per chi non vede i colori", () => {
    // La scala del design aveva alta e molto alta a 1,36:1, 1,25:1 per un
    // deuteranope (#155). Le celle sono dipinte al 70 % sopra la base: è lì
    // che vanno distinte, non sul campione pieno della legenda.
    const base = lineare("#10161d");
    const dipinte = RISK_CLASSES.map((c) => lineare(c.color).map((v, i) => 0.7 * v + 0.3 * base[i]!));
    const viste: Record<string, number[][]> = { normale: dipinte };
    for (const [nome, m] of Object.entries(CVD)) {
      viste[nome] = dipinte.map((v) =>
        m.map((riga) => Math.min(1, Math.max(0, riga[0]! * v[0]! + riga[1]! * v[1]! + riga[2]! * v[2]!))),
      );
    }
    for (const [nome, colori] of Object.entries(viste)) {
      for (let i = 0; i < colori.length; i++) {
        for (let j = i + 1; j < colori.length; j++) {
          expect(contrasto(colori[i]!, colori[j]!), `${nome}: ${i} vs ${j}`).toBeGreaterThanOrEqual(1.5);
        }
      }
    }
  });
});
