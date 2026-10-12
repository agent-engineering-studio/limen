// Il motore alluvione per una cella dentro la mappa ISPRA, su suolo saturo e
// senza cemento: lì i due rami hanno la stessa suscettibilità e il motore
// (`core/scoring/flood/engine.py`) si riduce a
//
//     punteggio = s × max(pioggia, fiume),  0 se s < floor
//
// Ogni costante porta accanto la chiave di `config/hazards/flood.yaml` da cui
// viene: se lo YAML cambia, il test della figura lo dice.

import type { RiskLevel } from "../../../types";

export const SOGLIA_MM = 40; // pluvial.threshold_mm
export const SATURAZIONE_MM = 120; // pluvial.saturation_mm
export const FINESTRA_ORE = 72; // pluvial.window_hours
export const PIENA_ORDINARIA = 1.6; // fluvial.normal_ratio
export const PIENA_SATURA = 10; // fluvial.saturation_ratio
export const FLOOR = 0.05; // susceptibility.floor

// classes: none < 0,10 ≤ low < 0,25 ≤ moderate < 0,45 ≤ high < 0,70 ≤ very_high
export const CLASSI: readonly { level: RiskLevel; da: number; a: number }[] = [
  { level: "None", da: 0, a: 0.1 },
  { level: "Low", da: 0.1, a: 0.25 },
  { level: "Moderate", da: 0.25, a: 0.45 },
  { level: "High", da: 0.45, a: 0.7 },
  { level: "VeryHigh", da: 0.7, a: 1 },
];

export const PIOGGIA_MAX_MM = 160;
export const RAPPORTO_MAX = 12;

export interface Ingressi {
  pioggiaMm: number;
  rapporto: number;
  suscettibilita: number;
}

export interface Stato extends Ingressi {
  pluviale: number;
  fluviale: number;
  spinta: number;
  ramo: "pioggia" | "fiume" | "nessuno";
  chiusa: boolean;
  punteggio: number;
  livello: RiskLevel;
}

const rampa = (valore: number, da: number, a: number) => Math.min(1, Math.max(0, (valore - da) / (a - da)));

export function livelloDi(punteggio: number): RiskLevel {
  for (let i = CLASSI.length - 1; i >= 0; i--) if (punteggio >= CLASSI[i]!.da) return CLASSI[i]!.level;
  return "None";
}

export function statoDi(ingressi: Ingressi): Stato {
  const pluviale = rampa(ingressi.pioggiaMm, SOGLIA_MM, SATURAZIONE_MM);
  const fluviale = rampa(ingressi.rapporto, PIENA_ORDINARIA, PIENA_SATURA);
  const spinta = Math.max(pluviale, fluviale);
  const ramo = spinta === 0 ? "nessuno" : pluviale >= fluviale ? "pioggia" : "fiume";
  const chiusa = ingressi.suscettibilita < FLOOR;
  const punteggio = chiusa ? 0 : Math.min(1, ingressi.suscettibilita * spinta);
  return { ...ingressi, pluviale, fluviale, spinta, ramo, chiusa, punteggio, livello: livelloDi(punteggio) };
}

// Il giro che la figura fa da sola: un nubifragio, poi una piena di fiume con
// la pioggia passata, poi la stessa piena su una cella sopra il crinale.
export const GIRO: readonly (Ingressi & { secondi: number })[] = [
  { secondi: 3.2, pioggiaMm: 96, rapporto: 1.3, suscettibilita: 0.8 },
  { secondi: 3.2, pioggiaMm: 30, rapporto: 7.5, suscettibilita: 0.8 },
  { secondi: 2.6, pioggiaMm: 30, rapporto: 7.5, suscettibilita: 0.03 },
  { secondi: 2.4, pioggiaMm: 60, rapporto: 2.4, suscettibilita: 0.45 },
];

export const RIPOSO: Ingressi = GIRO[0]!;
