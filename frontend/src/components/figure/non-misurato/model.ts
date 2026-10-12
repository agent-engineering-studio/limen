// «Non misurato» non è «nessun pericolo» (CLAUDE.md, e `measured()` in
// `core/models/risk.py`). Un'integrazione degradata restituisce un valore
// neutro, e per un motore che moltiplica il neutro è zero: una cella senza
// dato e una cella calma valgono entrambe 0. Le distingue solo `measured`,
// che sulla mappa diventa il grigio delle celle non valutate.

import type { RiskLevel } from "../../../types";
import { RISK_CLASSES } from "../../../lib/risk-colors";

export interface Cella {
  // Il segnale dinamico già normalizzato; `null` = non è arrivato.
  segnale: number | null;
}

export interface Lettura {
  misurato: boolean;
  punteggio: number;
  livello: RiskLevel | null;
}

export function livelloDi(punteggio: number): RiskLevel {
  for (let i = RISK_CLASSES.length - 1; i >= 0; i--) if (punteggio >= RISK_CLASSES[i]!.range[0]) return RISK_CLASSES[i]!.level;
  return "None";
}

export function letturaDi({ segnale }: Cella): Lettura {
  const misurato = segnale !== null;
  const punteggio = segnale ?? 0;
  return { misurato, punteggio, livello: misurato ? livelloDi(punteggio) : null };
}

// Il giro: due celle sotto lo stesso cielo; alla seconda si stacca il dato.
export const GIRO: readonly { secondi: number; a: number; b: number | null }[] = [
  { secondi: 2.6, a: 0.46, b: 0.46 },
  { secondi: 3, a: 0.46, b: null },
  { secondi: 3, a: 0, b: null },
  { secondi: 2.6, a: 0, b: 0 },
];
