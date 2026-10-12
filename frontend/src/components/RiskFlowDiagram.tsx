import type { JSX } from "react";
import { testi, useTesti } from "../lib/i18n";
import type { FlowPhase } from "../lib/markdown";

// Lo schema che ricorre in ogni pagina divulgativa: la stessa catena, con
// evidenziato il pezzo di cui quella pagina parla.
//
// Non è un SVG a larghezza fissa ma una catena di riquadri che va a capo:
// su un telefono un disegno vettoriale orizzontale si rimpicciolisce finché
// le etichette diventano illeggibili, e queste pagine si leggono soprattutto
// da telefono.

type Fase = Exclude<FlowPhase, "tutte">;

const FASI: readonly Fase[] = ["dati", "punteggio", "classe", "avviso"];

const T = testi(
  {
    passi: {
      dati: { label: "I dati", detail: "il posto e il momento" },
      punteggio: { label: "Il punteggio", detail: "un numero fra 0 e 1" },
      classe: { label: "La classe", detail: "cinque livelli" },
      avviso: { label: "L'avviso", detail: "a chi, quando" },
    } as Record<Fase, { label: string; detail: string }>,
    aria: "Dai dati al punteggio, dal punteggio alla classe, dalla classe all'avviso",
  },
  {
    passi: {
      dati: { label: "The data", detail: "the place and the moment" },
      punteggio: { label: "The score", detail: "a number between 0 and 1" },
      classe: { label: "The class", detail: "five levels" },
      avviso: { label: "The alert", detail: "to whom, when" },
    },
    aria: "From the data to the score, from the score to the class, from the class to the alert",
  },
);

export interface RiskFlowDiagramProps {
  /** Fase evidenziata; `tutte` accende l'intera catena. */
  phase?: FlowPhase;
}

export function RiskFlowDiagram({ phase = "tutte" }: RiskFlowDiagramProps): JSX.Element {
  const t = useTesti(T);
  return (
    <figure
      className="flow-diagram"
      aria-label={t.aria}
    >
      {FASI.map((fase, index) => (
        <div className="flow-step-wrap" key={fase}>
          <div
            className={`flow-step ${phase === "tutte" || phase === fase ? "on" : ""}`}
            data-phase={fase}
          >
            <span className="flow-label">{t.passi[fase].label}</span>
            <span className="flow-detail">{t.passi[fase].detail}</span>
          </div>
          {index < FASI.length - 1 ? (
            <span className="flow-arrow" aria-hidden="true">
              →
            </span>
          ) : null}
        </div>
      ))}
    </figure>
  );
}

export default RiskFlowDiagram;
