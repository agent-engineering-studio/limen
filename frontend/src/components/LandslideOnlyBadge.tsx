import type { JSX } from "react";
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

import { NOMI_PERICOLO, useHazard } from "../lib/hazard";
import { testi, useLingua, useTesti } from "../lib/i18n";

const PINNED = "landslide";

const T = testi(
  {
    titolo: (l: string) => `Questo pannello mostra solo: ${l}`,
    marchio: (l: string) => `solo ${l.toLowerCase()}`,
  },
  {
    titolo: (l: string) => `This panel shows only: ${l}`,
    marchio: (l: string) => `${l.toLowerCase()} only`,
  },
);

export function LandslideOnlyBadge(): JSX.Element | null {
  const { selected, available } = useHazard();
  const { lingua } = useLingua();
  const t = useTesti(T);
  if (selected === PINNED) return null;

  const label =
    lingua === "it"
      ? (available.find((h) => h.hazard === PINNED)?.label_it ?? "frane")
      : NOMI_PERICOLO.en[PINNED];
  return (
    <span className="pinned-badge" title={t.titolo(label)}>
      {t.marchio(label)}
    </span>
  );
}

export default LandslideOnlyBadge;
