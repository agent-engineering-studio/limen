import type { JSX } from "react";
// Il quadro nazionale come selettore (#155): una riga per pericolo, con il
// suo conteggio e la sua classe, e la vista d'insieme in cima. Scegliere una
// riga è filtrare la mappa su quel pericolo; il numero che si legge prima di
// scegliere è il motivo per cui la si sceglie.
//
// **Non rende nulla con meno di due pericoli disponibili.** Con uno solo la
// scelta non esiste: né fra i pericoli, né fra un pericolo e la vista
// d'insieme, che di un solo pericolo sarebbe quel pericolo.

import { useHazard } from "../lib/hazard";
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

/** F/A/I: le stesse lettere dei chip nella lista dei comuni. */
export const LETTERA: Record<HazardType, string> = {
  landslide: "F",
  flood: "A",
  wildfire: "I",
};

const BADGE: Record<TonoPericolo, string> = {
  alert: "alta+",
  watch: "moderata",
  quiet: "nessuna",
};

/** Ordine fisso: una riga che cambia posto a ogni aggiornamento non si
 *  ritrova, e la gravità la dice già il badge. */
const ORDINE: HazardType[] = ["landslide", "flood", "wildfire"];

export function HazardSelector({
  righe = {},
}: {
  righe?: Partial<Record<HazardType, RigaPericolo>>;
} = {}): JSX.Element | null {
  const { available, view, select } = useHazard();

  if (available.length < 2) {
    return null;
  }
  const pericoli = [...available].sort(
    (a, b) => ORDINE.indexOf(a.hazard) - ORDINE.indexOf(b.hazard),
  );

  return (
    <div className="hazard-selector" role="group" aria-label="Tipo di pericolo">
      <button
        type="button"
        className={`hz-riga ${view === "multi" ? "on" : ""}`}
        aria-pressed={view === "multi"}
        aria-label="Tutti i pericoli"
        onClick={() => select("multi")}
        title="Classe peggiore fra tutti i pericoli, in ogni cella"
      >
        <span className="hz-lettera is-tutti" aria-hidden>
          ∑
        </span>
        <span className="hz-testo">
          <span className="hz-nome">Tutti i pericoli</span>
          <span className="hz-dettaglio">il peggiore in ogni cella</span>
        </span>
      </button>
      {pericoli.map((h) => {
        const r = righe[h.hazard];
        return (
          <button
            key={h.hazard}
            type="button"
            className={`hz-riga ${h.hazard === view ? "on" : ""}`}
            aria-pressed={h.hazard === view}
            aria-label={h.label_it}
            onClick={() => select(h.hazard)}
          >
            <span className={`hz-lettera hz-${h.hazard}`} aria-hidden>
              {LETTERA[h.hazard] ?? h.label_it.charAt(0)}
            </span>
            <span className="hz-testo">
              <span className="hz-nome">{h.label_it}</span>
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
                <span className={`hz-badge tone-${r.tono}`}>{BADGE[r.tono]}</span>
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export default HazardSelector;
