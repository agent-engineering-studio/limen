// Come si racconta a chi legge che un pannello non ha numeri da mostrare.
//
// Finora ogni pannello stampava `err.message`, cioè la stringa che
// l'api-client costruisce per il registro: «request to /api/report/national
// failed with 500». Chi non ha scritto quel codice non sa cosa farne, e
// soprattutto quella riga non distingue i due casi che per chi legge sono
// opposti: «il sistema ha un problema» e «oggi non c'è niente da segnalare».
// Il secondo è una buona notizia.

import { ApiClientError } from "./api-client";
import { testi, type Lingua } from "./i18n";

export interface PanelFailure {
  /** Cosa non c'è, in una riga. */
  title: string;
  /** Perché, e cosa può farci chi legge. */
  detail: string;
  /** Falso quando riprovare non ha senso (la richiesta era sbagliata). */
  retryable: boolean;
}

const T = testi(
  {
    servizio: {
      title: "Il servizio non risponde",
      detail:
        "Il calcolo del rischio non è raggiungibile in questo momento. " +
        "Non vuol dire che non ci sia rischio: vuol dire che non lo sappiamo.",
    },
    assente: {
      title: "Dato non disponibile",
      detail: "Per questa selezione non c'è ancora nulla di calcolato.",
    },
    troppe: {
      title: "Troppe richieste",
      detail: "Il servizio sta limitando le chiamate. Riprova fra poco.",
    },
    nonValida: {
      title: "Richiesta non valida",
      detail: "La pagina ha chiesto qualcosa che il servizio non riconosce.",
    },
    rete: {
      title: "Connessione assente",
      detail:
        "Il browser non è riuscito a contattare il servizio. Controlla la " +
        "connessione e riprova.",
    },
    sconosciuta: "data sconosciuta",
    fraPoco: "fra poco",
    adesso: "adesso",
    minuti: (n: number) => `${n} minut${n === 1 ? "o" : "i"} fa`,
    ore: (n: number) => `${n} or${n === 1 ? "a" : "e"} fa`,
    giorni: (n: number) => `${n} giorn${n === 1 ? "o" : "i"} fa`,
  },
  {
    servizio: {
      title: "The service is not responding",
      detail:
        "The risk computation cannot be reached right now. " +
        "That does not mean there is no risk: it means we do not know.",
    },
    assente: {
      title: "Data not available",
      detail: "Nothing has been computed for this selection yet.",
    },
    troppe: {
      title: "Too many requests",
      detail: "The service is rate-limiting calls. Try again shortly.",
    },
    nonValida: {
      title: "Invalid request",
      detail: "The page asked for something the service does not recognise.",
    },
    rete: {
      title: "No connection",
      detail:
        "The browser could not reach the service. Check your " +
        "connection and try again.",
    },
    sconosciuta: "unknown date",
    fraPoco: "shortly",
    adesso: "just now",
    minuti: (n: number) => `${n} minute${n === 1 ? "" : "s"} ago`,
    ore: (n: number) => `${n} hour${n === 1 ? "" : "s"} ago`,
    giorni: (n: number) => `${n} day${n === 1 ? "" : "s"} ago`,
  },
);

/**
 * Traduce un errore in qualcosa che una persona può leggere.
 *
 * Il messaggio tecnico non si perde: resta nella console, dove serve a chi
 * deve ripararlo. Qui esce la versione per chi guarda la mappa.
 */
export function describeFailure(err: unknown, lingua: Lingua = "it"): PanelFailure {
  const t = T[lingua];
  if (err instanceof ApiClientError) {
    if (err.status >= 500) return { ...t.servizio, retryable: true };
    if (err.status === 404) return { ...t.assente, retryable: false };
    if (err.status === 429) return { ...t.troppe, retryable: true };
    return { ...t.nonValida, retryable: false };
  }
  // `fetch` fallisce con TypeError quando la rete non c'è, il DNS non
  // risolve o il certificato è rifiutato: da qui non si distinguono, e per
  // chi legge sono la stessa cosa.
  return { ...t.rete, retryable: true };
}

/** «12 minuti fa», nella lingua scelta, senza dipendenze. */
export function relativeTime(iso: string, now: Date = new Date(), lingua: Lingua = "it"): string {
  const t = T[lingua];
  const then = new Date(iso);
  const secondi = Math.round((now.getTime() - then.getTime()) / 1000);
  if (!Number.isFinite(secondi)) return t.sconosciuta;
  if (secondi < 0) return t.fraPoco;
  if (secondi < 60) return t.adesso;
  const minuti = Math.round(secondi / 60);
  if (minuti < 60) return t.minuti(minuti);
  const ore = Math.round(minuti / 60);
  if (ore < 24) return t.ore(ore);
  const giorni = Math.round(ore / 24);
  return t.giorni(giorni);
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
