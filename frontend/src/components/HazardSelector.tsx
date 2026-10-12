import type { JSX } from "react";
// Il quadro nazionale come selettore (#155): una riga per pericolo, con il
// suo conteggio e la sua classe, e la vista d'insieme in cima. Scegliere una
// riga è filtrare la mappa su quel pericolo; il numero che si legge prima di
// scegliere è il motivo per cui la si sceglie.
//
// **Non rende nulla con meno di due pericoli disponibili.** Con uno solo la
// scelta non esiste: né fra i pericoli, né fra un pericolo e la vista
// d'insieme, che di un solo pericolo sarebbe quel pericolo.

import { useHazard, useNomePericolo } from "../lib/hazard";
import { testi, useLingua, useTesti, type Lingua } from "../lib/i18n";
import type { HazardType } from "../types";

/** Il tono della riga: lo stesso del verdetto, che decide se agire. */
export type TonoPericolo = "quiet" | "watch" | "alert";

export interface RigaPericolo {
  /** Il conteggio da mostrare, già formattato. */
  cifra: string;
  /** Cosa conta: «aree in classe alta o superiore». */
  dettaglio: string;
  tono: TonoPericolo;
  /** Da quanto è fermo il dato, se lo si sa. */
  eta?: string;
  vecchio?: boolean;
}

/** F/A/I: le stesse lettere dei chip nella lista dei comuni. In inglese
 *  L/F/W, le iniziali di Landslide, Flood, Wildfire. */
export const LETTERE: Record<Lingua, Record<HazardType, string>> = {
  it: { landslide: "F", flood: "A", wildfire: "I" },
  en: { landslide: "L", flood: "F", wildfire: "W" },
};

export const LETTERA: Record<HazardType, string> = LETTERE.it;

const T = testi(
  {
    gruppo: "Tipo di pericolo",
    tutti: "Tutti i pericoli",
    tuttiTitolo: "Classe peggiore fra tutti i pericoli, in ogni cella",
    tuttiDettaglio: "il peggiore in ogni cella",
    badge: { alert: "alta+", watch: "moderata", quiet: "nessuna" } as Record<TonoPericolo, string>,
  },
  {
    gruppo: "Hazard type",
    tutti: "All hazards",
    tuttiTitolo: "Worst class across all hazards, in each cell",
    tuttiDettaglio: "the worst in each cell",
    badge: { alert: "high+", watch: "moderate", quiet: "none" },
  },
);

/** Ordine fisso: una riga che cambia posto a ogni aggiornamento non si
 *  ritrova, e la gravità la dice già il badge. */
const ORDINE: HazardType[] = ["landslide", "flood", "wildfire"];

export function HazardSelector({
  righe = {},
}: {
  righe?: Partial<Record<HazardType, RigaPericolo>>;
} = {}): JSX.Element | null {
  const { available, view, select } = useHazard();
  const { lingua } = useLingua();
  const t = useTesti(T);
  const nome = useNomePericolo();

  if (available.length < 2) {
    return null;
  }
  const pericoli = [...available].sort(
    (a, b) => ORDINE.indexOf(a.hazard) - ORDINE.indexOf(b.hazard),
  );

  return (
    <div className="hazard-selector" role="group" aria-label={t.gruppo}>
      <button
        type="button"
        className={`hz-riga ${view === "multi" ? "on" : ""}`}
        aria-pressed={view === "multi"}
        aria-label={t.tutti}
        onClick={() => select("multi")}
        title={t.tuttiTitolo}
      >
        <span className="hz-lettera is-tutti" aria-hidden>
          ∑
        </span>
        <span className="hz-testo">
          <span className="hz-nome">{t.tutti}</span>
          <span className="hz-dettaglio">{t.tuttiDettaglio}</span>
        </span>
      </button>
      {pericoli.map((h) => {
        const r = righe[h.hazard];
        const etichetta = nome(h.hazard);
        return (
          <button
            key={h.hazard}
            type="button"
            className={`hz-riga ${h.hazard === view ? "on" : ""}`}
            aria-pressed={h.hazard === view}
            aria-label={etichetta}
            onClick={() => select(h.hazard)}
          >
            <span className={`hz-lettera hz-${h.hazard}`} aria-hidden>
              {LETTERE[lingua][h.hazard] ?? etichetta.charAt(0)}
            </span>
            <span className="hz-testo">
              <span className="hz-nome">{etichetta}</span>
              {r ? (
                <span className="hz-dettaglio">
                  {r.dettaglio}
                  {r.eta ? (
                    <span className={r.vecchio ? "hz-eta is-stale" : "hz-eta"}>
                      {" "}
                      · {r.eta}
                    </span>
                  ) : null}
                </span>
              ) : null}
            </span>
            {r ? (
              <span className="hz-cifre">
                <span className={`hz-cifra mono ${r.tono === "quiet" ? "is-quiet" : ""}`}>
                  {r.cifra}
                </span>
                <span className={`hz-badge tone-${r.tono}`}>{t.badge[r.tono]}</span>
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export default HazardSelector;
