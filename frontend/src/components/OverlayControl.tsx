import type { JSX } from "react";

import { NOME_GRUPPO, OVERLAYS } from "../lib/overlays";
import type { GruppoOverlay } from "../lib/overlays";

export interface OverlayControlProps {
  readonly attivi: ReadonlySet<string>;
  readonly onToggle: (id: string) => void;
}

const GRUPPI: GruppoOverlay[] = ["landslide", "flood", "wildfire"];

/** Gli interruttori dei livelli di contesto, per pericolo.
 *
 *  Controllato: lo stato sta in `App`, che lo passa anche alla mappa. Qui
 *  si disegna e basta — è ciò che impedisce alla casella di dire «acceso»
 *  mentre la mappa, appena ricostruita, l'ha spento. */
export function OverlayControl(props: OverlayControlProps): JSX.Element {
  return (
    <div className="overlay-control" role="group" aria-label="Livelli di contesto">
      <span className="eyebrow" style={{ marginBottom: 4 }}>
        Livelli
      </span>
      {GRUPPI.map((g) => (
        <div key={g} className="overlay-gruppo">
          <span className="overlay-gruppo-nome">{NOME_GRUPPO[g]}</span>
          {OVERLAYS.filter((o) => o.gruppo === g).map((o) => (
            <label key={o.id} title={`Fonte: ${o.fonte}`}>
              <input
                type="checkbox"
                checked={props.attivi.has(o.id)}
                onChange={() => props.onToggle(o.id)}
              />{" "}
              {o.label}
              {o.minzoom !== undefined && o.minzoom > 6 ? (
                <small className="overlay-zoom"> · da zoom {o.minzoom}</small>
              ) : null}
              {o.classi && props.attivi.has(o.id) ? (
                <span className="overlay-classi">
                  {o.classi.map((c) => (
                    <span key={c.label}>
                      <i style={{ background: c.colore }} aria-hidden /> {c.label}
                    </span>
                  ))}
                </span>
              ) : null}
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

export default OverlayControl;
