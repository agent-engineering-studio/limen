import type { JSX } from "react";

import { testi, useLingua, useTesti } from "../lib/i18n";
import { NOME_GRUPPO, OVERLAYS, testoOverlay } from "../lib/overlays";
import type { GruppoOverlay } from "../lib/overlays";

export interface OverlayControlProps {
  readonly attivi: ReadonlySet<string>;
  readonly onToggle: (id: string) => void;
}

const GRUPPI: GruppoOverlay[] = ["ufficiale", "landslide", "flood", "wildfire", "cittadini"];

const T = testi(
  {
    gruppo: "Livelli di contesto",
    livelli: "Livelli",
    fonte: (f: string) => `Fonte: ${f}`,
    daZoom: (z: number) => ` · da zoom ${z}`,
  },
  {
    gruppo: "Context layers",
    livelli: "Layers",
    fonte: (f: string) => `Source: ${f}`,
    daZoom: (z: number) => ` · from zoom ${z}`,
  },
);

/** Gli interruttori dei livelli di contesto, per pericolo.
 *
 *  Controllato: lo stato sta in `App`, che lo passa anche alla mappa. Qui
 *  si disegna e basta — è ciò che impedisce alla casella di dire «acceso»
 *  mentre la mappa, appena ricostruita, l'ha spento. */
export function OverlayControl(props: OverlayControlProps): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  return (
    <div className="overlay-control" role="group" aria-label={t.gruppo}>
      <span className="eyebrow" style={{ marginBottom: 4 }}>
        {t.livelli}
      </span>
      {GRUPPI.map((g) => (
        <div key={g} className="overlay-gruppo">
          <span className="overlay-gruppo-nome">{NOME_GRUPPO[lingua][g]}</span>
          {OVERLAYS.filter((o) => o.gruppo === g).map((o) => {
            const testo = testoOverlay(o, lingua);
            return (
              <label key={o.id} title={t.fonte(testo.fonte)}>
                <input
                  type="checkbox"
                  checked={props.attivi.has(o.id)}
                  onChange={() => props.onToggle(o.id)}
                />{" "}
                {testo.label}
                {o.minzoom !== undefined && o.minzoom > 6 ? (
                  <small className="overlay-zoom">{t.daZoom(o.minzoom)}</small>
                ) : null}
                {testo.classi.length > 0 && props.attivi.has(o.id) ? (
                  <span className="overlay-classi">
                    {testo.classi.map((c) => (
                      <span key={c.colore}>
                        <i style={{ background: c.colore }} aria-hidden /> {c.label}
                      </span>
                    ))}
                  </span>
                ) : null}
              </label>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default OverlayControl;
