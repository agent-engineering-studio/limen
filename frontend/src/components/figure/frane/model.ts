// Il motore frane V1 su una cella senza sensori (`core/scoring/engine.py`,
// ramo «Pure V1 path»): una somma pesata dei cinque componenti, ognuno in
// [0, 1]. Pesi e classi da `config/hazards/landslide.yaml`.

import type { RiskLevel } from "../../../types";

export const COMPONENTI = ["s", "m", "e", "f", "h"] as const;
export type Componente = (typeof COMPONENTI)[number];

export const PESI: Record<Componente, number> = {
  s: 0.35, // weights.static
  m: 0.4, // weights.meteo
  e: 0.15, // weights.seismic
  f: 0.07, // weights.fire
  h: 0.03, // weights.hydrology
};

// classes: none < 0,15 ≤ low < 0,35 ≤ moderate < 0,55 ≤ high < 0,75 ≤ very_high
export const CLASSI: readonly { level: RiskLevel; da: number; a: number }[] = [
  { level: "None", da: 0, a: 0.15 },
  { level: "Low", da: 0.15, a: 0.35 },
  { level: "Moderate", da: 0.35, a: 0.55 },
  { level: "High", da: 0.55, a: 0.75 },
  { level: "VeryHigh", da: 0.75, a: 1 },
];

export type Valori = Record<Componente, number>;

export interface Stato {
  valori: Valori;
  contributi: Valori;
  punteggio: number;
  livello: RiskLevel;
}

export function livelloDi(punteggio: number): RiskLevel {
  for (let i = CLASSI.length - 1; i >= 0; i--) if (punteggio >= CLASSI[i]!.da) return CLASSI[i]!.level;
  return "None";
}

export function statoDi(valori: Valori): Stato {
  const contributi = Object.fromEntries(COMPONENTI.map((c) => [c, PESI[c] * valori[c]])) as Valori;
  const totale = COMPONENTI.reduce((somma, c) => somma + contributi[c], 0);
  const punteggio = Math.min(1, Math.max(0, totale));
  return { valori, contributi, punteggio, livello: livelloDi(punteggio) };
}

// Il giro: un versante franoso (S alto) sotto una pioggia che cresce, poi un
// terremoto, poi la pioggia su un versante bruciato.
export const GIRO: readonly (Valori & { secondi: number })[] = [
  { secondi: 2.8, s: 0.7, m: 0.15, e: 0, f: 0, h: 0.2 },
  { secondi: 3.2, s: 0.7, m: 0.85, e: 0, f: 0, h: 0.2 },
  { secondi: 3, s: 0.7, m: 0.85, e: 0.9, f: 0, h: 0.2 },
  { secondi: 3, s: 0.4, m: 0.6, e: 0, f: 1, h: 0.6 },
];

export const RIPOSO: Valori = { s: 0.7, m: 0.15, e: 0, f: 0, h: 0.2 };
