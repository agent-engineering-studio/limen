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

import type { Hazard, HazardType } from "../types";
import { defaultApiClient } from "./api-client";

interface HazardContextValue {
  /** Pericoli disponibili. Vuoto finché la prima fetch non risponde. */
  available: Hazard[];
  selected: HazardType;
  select: (hazard: HazardType) => void;
}

// Il default statico serve solo per il primo render e per un backend
// irraggiungibile: la mappa pubblica deve disegnarsi comunque.
const FALLBACK: HazardType = "landslide";

const HazardContext = createContext<HazardContextValue | null>(null);

export function HazardProvider({ children }: { children: ReactNode }): JSX.Element {
  const [available, setAvailable] = useState<Hazard[]>([]);
  // I consumatori partono subito con il ripiego invece di aspettare
  // `/api/hazards`: la mappa pubblica si disegna senza attendere una lista
  // che oggi ha un solo elemento. Se il backend annuncia un default diverso,
  // l'effetto si ri-esegue con quello — una richiesta in più, non un errore.
  const [selected, setSelected] = useState<HazardType>(FALLBACK);

  useEffect(() => {
    const controller = new AbortController();
    defaultApiClient
      .getHazards(controller.signal)
      .then((res) => {
        setAvailable(res.items);
        // Il default lo decide il backend, non questa costante. Se il
        // backend ne annuncia uno che non è nell'elenco, si ripiega sul
        // primo disponibile invece di selezionare qualcosa di inesistente.
        const first = res.items[0];
        if (first) {
          setSelected(
            res.items.some((h) => h.hazard === res.default) ? res.default : first.hazard,
          );
        }
      })
      .catch(() => {
        // Backend giù: si resta sul default e la dashboard funziona.
      });
    return () => controller.abort();
  }, []);

  const select = useCallback((hazard: HazardType) => setSelected(hazard), []);

  const value = useMemo(
    () => ({ available, selected, select }),
    [available, selected, select],
  );
  return <HazardContext.Provider value={value}>{children}</HazardContext.Provider>;
}

export function useHazard(): HazardContextValue {
  const ctx = useContext(HazardContext);
  if (ctx === null) {
    // Fuori dal provider (pagine statiche, test di un singolo componente):
    // il default, invece di far esplodere un albero che non ha bisogno del
    // pericolo per rendersi.
    return { available: [], selected: FALLBACK, select: () => {} };
  }
  return ctx;
}
