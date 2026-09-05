// Selettore del pericolo nell'header.
//
// **Non rende nulla con meno di due pericoli disponibili.** È il requisito
// che tiene la Fase 1 invisibile all'utente: oggi il deployment ne valuta uno
// solo, quindi un controllo con una sola scelta sarebbe rumore.

import { useHazard } from "../lib/hazard";

export function HazardSelector(): JSX.Element | null {
  const { available, selected, select } = useHazard();

  if (available.length < 2) {
    return null;
  }

  return (
    <div
      className="hazard-selector"
      role="group"
      aria-label="Tipo di pericolo"
    >
      {available.map((h) => (
        <button
          key={h.hazard}
          type="button"
          className={h.hazard === selected ? "on" : ""}
          aria-pressed={h.hazard === selected}
          onClick={() => select(h.hazard)}
        >
          {h.label_it}
        </button>
      ))}
    </div>
  );
}

export default HazardSelector;
