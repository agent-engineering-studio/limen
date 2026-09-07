// Selettore del pericolo nell'header.
//
// **Non rende nulla con meno di due pericoli disponibili.** Con uno solo la
// scelta non esiste: né fra i pericoli, né fra un pericolo e la vista
// d'insieme, che di un solo pericolo sarebbe quel pericolo.

import { useHazard } from "../lib/hazard";

export function HazardSelector(): JSX.Element | null {
  const { available, view, select } = useHazard();

  if (available.length < 2) {
    return null;
  }

  return (
    <div className="hazard-selector" role="group" aria-label="Tipo di pericolo">
      {available.map((h) => (
        <button
          key={h.hazard}
          type="button"
          className={h.hazard === view ? "on" : ""}
          aria-pressed={h.hazard === view}
          onClick={() => select(h.hazard)}
        >
          {h.label_it}
        </button>
      ))}
      <button
        type="button"
        className={view === "multi" ? "on" : ""}
        aria-pressed={view === "multi"}
        onClick={() => select("multi")}
        title="Classe peggiore fra tutti i pericoli, in ogni cella"
      >
        tutti
      </button>
    </div>
  );
}

export default HazardSelector;
