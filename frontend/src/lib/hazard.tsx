import type { JSX } from "react";
// Il pericolo selezionato, risolto da GET /api/hazards.
//
// Un contesto e non una proprietà passata a mano: sei componenti della
// dashboard ne hanno bisogno, e infilarla attraverso tutti renderebbe
// l'aggiunta del secondo pericolo un refactor invece di un cambio di stato.
//
// L'endpoint elenca solo i pericoli che questo deployment sa davvero valutare
// (motore registrato + file di soglie), quindi ciò che il selettore offre è
// sempre qualcosa per cui esistono dati.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Hazard, HazardType, HazardView } from "../types";
import { defaultApiClient } from "./api-client";
import { useLingua, type Lingua } from "./i18n";

/**
 * Il nome del pericolo nelle due lingue. In italiano vince l'etichetta del
 * database (`label_it`), che è la fonte; questa tabella è il ripiego e
 * l'inglese, che il database non ha.
 */
export const NOMI_PERICOLO: Record<Lingua, Record<HazardType, string>> = {
  it: { landslide: "Frana", flood: "Allagamento", wildfire: "Incendio" },
  en: { landslide: "Landslide", flood: "Flood", wildfire: "Wildfire" },
};

/** Il nome di un pericolo nella lingua attiva, con l'iniziale maiuscola. */
export function useNomePericolo(): (hazard: string) => string {
  const { lingua } = useLingua();
  const { available } = useHazard();
  return useCallback(
    (hazard: string) => {
      if (lingua === "it") {
        const db = available.find((h) => h.hazard === hazard)?.label_it;
        if (db) return db;
      }
      return NOMI_PERICOLO[lingua][hazard as HazardType] ?? hazard;
    },
    [lingua, available],
  );
}

interface HazardContextValue {
  /** Pericoli disponibili. Vuoto finché la prima fetch non risponde. */
  available: Hazard[];
  /**
   * Il pericolo per cui i pannelli chiedono dati. Sempre un pericolo vero,
   * anche in vista multi: i pannelli per pericolo continuano a mostrare
   * qualcosa invece di svuotarsi, e nessuno di loro ha bisogno di sapere
   * che esiste una vista d'insieme.
   */
  selected: HazardType;
  /** Cosa mostra il selettore: un pericolo, oppure tutti insieme. */
  view: HazardView;
  multi: boolean;
  select: (view: HazardView) => void;
}

// Il default statico serve solo per il primo render e per un backend
// irraggiungibile: la mappa pubblica deve disegnarsi comunque.
const FALLBACK: HazardType = "landslide";

const HazardContext = createContext<HazardContextValue | null>(null);

export function HazardProvider({
  children,
  iniziale,
}: {
  children: ReactNode;
  /** La vista di un link (`#/mappa?hazard=…`), che vince sul default del
   *  backend se il pericolo è fra quelli disponibili. */
  iniziale?: HazardView;
}): JSX.Element {
  const richiesto = iniziale === "multi" ? undefined : iniziale;
  const [available, setAvailable] = useState<Hazard[]>([]);
  // I consumatori partono subito con il ripiego invece di aspettare
  // `/api/hazards`: la mappa pubblica si disegna senza attendere una lista
  // che oggi ha un solo elemento. Se il backend annuncia un default diverso,
  // l'effetto si ri-esegue con quello — una richiesta in più, non un errore.
  const [selected, setSelected] = useState<HazardType>(richiesto ?? FALLBACK);
  // Si apre su tutti i pericoli (#155): la domanda con cui si arriva è «dove
  // va male», non «dove va male per le frane». Il pericolo singolo è un
  // filtro che si sceglie dal quadro nazionale.
  const [multi, setMulti] = useState(richiesto === undefined);

  useEffect(() => {
    const controller = new AbortController();
    defaultApiClient
      .getHazards(controller.signal)
      .then((res) => {
        setAvailable(res.items);
        // Con un pericolo solo la vista d'insieme sarebbe quel pericolo con
        // un altro nome.
        if (res.items.length < 2) setMulti(false);
        // Il default lo decide il backend, non questa costante. Se il
        // backend ne annuncia uno che non è nell'elenco, si ripiega sul
        // primo disponibile invece di selezionare qualcosa di inesistente.
        const first = res.items[0];
        if (first) {
          if (richiesto && res.items.some((h) => h.hazard === richiesto)) return;
          // Un link a un pericolo che qui non c'è riapre la vista di default.
          if (richiesto && res.items.length >= 2) setMulti(true);
          setSelected(
            res.items.some((h) => h.hazard === res.default) ? res.default : first.hazard,
          );
        }
      })
      .catch(() => {
        // Backend giù: si resta sul default e la dashboard funziona.
      });
    return () => controller.abort();
  }, [richiesto]);

  // Passando a "multi" il pericolo scelto **non** si azzera: è quello che i
  // pannelli per pericolo continuano a leggere, e tornare indietro dalla
  // vista d'insieme riporta alla scelta di prima invece che al default.
  const select = useCallback((next: HazardView) => {
    if (next === "multi") {
      setMulti(true);
      return;
    }
    setMulti(false);
    setSelected(next);
  }, []);

  const value = useMemo(
    () => ({
      available,
      selected,
      view: multi ? ("multi" as const) : selected,
      multi,
      select,
    }),
    [available, selected, multi, select],
  );
  return <HazardContext.Provider value={value}>{children}</HazardContext.Provider>;
}

export function useHazard(): HazardContextValue {
  const ctx = useContext(HazardContext);
  if (ctx === null) {
    // Fuori dal provider (pagine statiche, test di un singolo componente):
    // il default, invece di far esplodere un albero che non ha bisogno del
    // pericolo per rendersi.
    return {
      available: [],
      selected: FALLBACK,
      view: FALLBACK,
      multi: false,
      select: () => {},
    };
  }
  return ctx;
}
