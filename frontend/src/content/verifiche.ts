// Le verifiche: un evento riportato dai giornali, messo accanto a quello che
// Limen aveva previsto prima. Una verifica è un file JSON in
// `content/verifiche/`, scritto dalla skill `limen-fact-check`: niente
// database, niente endpoint — il contenuto entra nel bundle a build time,
// come la guida, e una verifica nuova è un file in più.

import type { HazardType, RiskLevel } from "../types";

/**
 * Sulla pagina vanno solo gli eventi che Limen aveva previsto in anticipo:
 * l'unico esito che una verifica può avere.
 */
export type Esito = "anticipata";

export interface Fonte {
  testata: string;
  titolo: string;
  url: string;
  data: string;
}

/** Solo immagini con una licenza che ne consente la pubblicazione. */
export interface Foto {
  src: string;
  didascalia: string;
  autore: string;
  licenza: string;
  fonte_url: string;
}

export interface Corsa {
  run_at: string;
  horizon_h: number;
  target_at: string;
  classe: RiskLevel;
  score: number;
}

export interface Previsione {
  anticipo_ore_moderato: number | null;
  anticipo_ore_alto: number | null;
  classe_max: RiskLevel | null;
  allerta_prima: string | null;
  corse: Corsa[];
}

export interface Fattore {
  nome: string;
  valore: string;
  spiegazione: string;
}

export interface Verifica {
  slug: string;
  titolo: string;
  pericolo: HazardType;
  esito: Esito;
  evento: {
    quando: string;
    luogo: string;
    regione: string;
    comuni: { istat: string; nome: string }[];
  };
  pubblicato: string;
  aggiornato: string;
  sommario: string;
  corpo: string[];
  fonti: Fonte[];
  foto: Foto[];
  previsione: Previsione;
  perche: Fattore[];
  en: VerificaInglese;
}

/** La traduzione inglese, campo per campo, con lo stesso numero di
 *  paragrafi, fattori e foto dell'italiano. Numeri, date, fonti e licenze
 *  non si traducono. */
export interface VerificaInglese {
  titolo: string;
  luogo: string;
  sommario: string;
  corpo: string[];
  perche: Fattore[];
  foto: { didascalia: string }[];
}

const FILE = import.meta.glob<Verifica>("./verifiche/*.json", {
  eager: true,
  import: "default",
});

/** Dalla più recente: è un blog, l'ultimo evento sta in cima. */
export function ordina(verifiche: readonly Verifica[]): Verifica[] {
  return [...verifiche].sort((a, b) => b.evento.quando.localeCompare(a.evento.quando));
}

/**
 * Solo gli eventi previsti in anticipo, con la traduzione completa. Il glob
 * non controlla il tipo dei JSON: un file con un altro esito, o senza
 * inglese, resta fuori qui invece di finire sulla pagina.
 */
export function verificate(verifiche: readonly Verifica[]): Verifica[] {
  return verifiche.filter(
    (v) =>
      v.esito === "anticipata" &&
      v.en !== undefined &&
      v.en.corpo.length === v.corpo.length &&
      v.en.perche.length === v.perche.length &&
      v.en.foto.length === v.foto.length,
  );
}

export const VERIFICHE: readonly Verifica[] = ordina(
  verificate(Object.values(FILE)),
);
