// Come si racconta a chi legge che un pannello non ha numeri da mostrare.
//
// Finora ogni pannello stampava `err.message`, cioè la stringa che
// l'api-client costruisce per il registro: «request to /api/report/national
// failed with 500». Chi non ha scritto quel codice non sa cosa farne, e
// soprattutto quella riga non distingue i due casi che per chi legge sono
// opposti: «il sistema ha un problema» e «oggi non c'è niente da segnalare».
// Il secondo è una buona notizia.

import { ApiClientError } from "./api-client";

export interface PanelFailure {
  /** Cosa non c'è, in una riga. */
  title: string;
  /** Perché, e cosa può farci chi legge. */
  detail: string;
  /** Falso quando riprovare non ha senso (la richiesta era sbagliata). */
  retryable: boolean;
}

/**
 * Traduce un errore in qualcosa che una persona può leggere.
 *
 * Il messaggio tecnico non si perde: resta nella console, dove serve a chi
 * deve ripararlo. Qui esce la versione per chi guarda la mappa.
 */
export function describeFailure(err: unknown): PanelFailure {
  if (err instanceof ApiClientError) {
    if (err.status >= 500) {
      return {
        title: "Il servizio non risponde",
        detail:
          "Il calcolo del rischio non è raggiungibile in questo momento. " +
          "Non vuol dire che non ci sia rischio: vuol dire che non lo sappiamo.",
        retryable: true,
      };
    }
    if (err.status === 404) {
      return {
        title: "Dato non disponibile",
        detail: "Per questa selezione non c'è ancora nulla di calcolato.",
        retryable: false,
      };
    }
    if (err.status === 429) {
      return {
        title: "Troppe richieste",
        detail: "Il servizio sta limitando le chiamate. Riprova fra poco.",
        retryable: true,
      };
    }
    return {
      title: "Richiesta non valida",
      detail: "La pagina ha chiesto qualcosa che il servizio non riconosce.",
      retryable: false,
    };
  }
  // `fetch` fallisce con TypeError quando la rete non c'è, il DNS non
  // risolve o il certificato è rifiutato: da qui non si distinguono, e per
  // chi legge sono la stessa cosa.
  return {
    title: "Connessione assente",
    detail:
      "Il browser non è riuscito a contattare il servizio. Controlla la " +
      "connessione e riprova.",
    retryable: true,
  };
}

/** «12 minuti fa», in italiano, senza dipendenze. */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const secondi = Math.round((now.getTime() - then.getTime()) / 1000);
  if (!Number.isFinite(secondi)) return "data sconosciuta";
  if (secondi < 0) return "fra poco";
  if (secondi < 60) return "adesso";
  const minuti = Math.round(secondi / 60);
  if (minuti < 60) return `${minuti} minut${minuti === 1 ? "o" : "i"} fa`;
  const ore = Math.round(minuti / 60);
  if (ore < 24) return `${ore} or${ore === 1 ? "a" : "e"} fa`;
  const giorni = Math.round(ore / 24);
  return `${giorni} giorn${giorni === 1 ? "o" : "i"} fa`;
}

/**
 * Da quante ore un dato è fermo, oltre le quali va detto che è vecchio.
 *
 * Lo sweep è orario: tre ore sono tre giri saltati, cioè un guasto che la
 * pagina deve dichiarare invece di mostrare numeri vecchi come se fossero
 * di adesso.
 */
export const STALE_AFTER_HOURS = 3;

export function isStale(iso: string, now: Date = new Date()): boolean {
  const eta = now.getTime() - new Date(iso).getTime();
  return Number.isFinite(eta) && eta > STALE_AFTER_HOURS * 3600 * 1000;
}
