// Marchio "solo frane" per i pannelli che non seguono il selettore.
//
// Mappa, rollup comunale e quadro nazionale leggono viste SQL fissate sul
// pericolo di default (migrazione 028: una sorgente di tile deve dare una
// geometria per cella, e `mv_comune_risk` classifica per esposizione con una
// chiave che solo il breakdown delle frane ha). Con un secondo pericolo
// abilitato resterebbero fermi mentre il selettore dice altro: peggio che
// mostrare numeri vecchi, perché sembrerebbero del pericolo scelto.
//
// Invisibile finché il pericolo scelto è quello su cui la vista è fissata —
// cioè sempre, in Fase 1. La superficie multi-pericolo è #58.

import { useHazard } from "../lib/hazard";

const PINNED = "landslide";

export function LandslideOnlyBadge(): JSX.Element | null {
  const { selected, available } = useHazard();
  if (selected === PINNED) return null;

  const label = available.find((h) => h.hazard === PINNED)?.label_it ?? "frane";
  return (
    <span className="pinned-badge" title={`Questo pannello mostra solo: ${label}`}>
      solo {label.toLowerCase()}
    </span>
  );
}

export default LandslideOnlyBadge;
