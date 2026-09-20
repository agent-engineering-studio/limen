import type { FlowPhase } from "../lib/markdown";

// Lo schema che ricorre in ogni pagina divulgativa: la stessa catena, con
// evidenziato il pezzo di cui quella pagina parla.
//
// Non è un SVG a larghezza fissa ma una catena di riquadri che va a capo:
// su un telefono un disegno vettoriale orizzontale si rimpicciolisce finché
// le etichette diventano illeggibili, e queste pagine si leggono soprattutto
// da telefono.

const STEPS: { phase: Exclude<FlowPhase, "tutte">; label: string; detail: string }[] = [
  { phase: "dati", label: "I dati", detail: "il posto e il momento" },
  { phase: "punteggio", label: "Il punteggio", detail: "un numero fra 0 e 1" },
  { phase: "classe", label: "La classe", detail: "cinque livelli" },
  { phase: "avviso", label: "L'avviso", detail: "a chi, quando" },
];

export interface RiskFlowDiagramProps {
  /** Fase evidenziata; `tutte` accende l'intera catena. */
  phase?: FlowPhase;
}

export function RiskFlowDiagram({ phase = "tutte" }: RiskFlowDiagramProps): JSX.Element {
  return (
    <figure
      className="flow-diagram"
      aria-label="Dai dati al punteggio, dal punteggio alla classe, dalla classe all'avviso"
    >
      {STEPS.map((step, index) => (
        <div className="flow-step-wrap" key={step.phase}>
          <div
            className={`flow-step ${phase === "tutte" || phase === step.phase ? "on" : ""}`}
            data-phase={step.phase}
          >
            <span className="flow-label">{step.label}</span>
            <span className="flow-detail">{step.detail}</span>
          </div>
          {index < STEPS.length - 1 ? (
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
