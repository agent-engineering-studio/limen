// Curva di calibrazione (reliability diagram) del challenger ML (#30).
// Gated sui dati: finché non ci sono abbastanza eventi reali mostra uno stato
// esplicito "dati insufficienti". Non autoritativo — solo diagnostica.

import type { ReliabilityResponse } from "../types";

const P = { w: 240, h: 240, m: 34 };

export default function ReliabilityChart({
  data,
}: {
  data: ReliabilityResponse;
}): JSX.Element {
  if (!data.sufficient) {
    return (
      <p className="shadow-muted" role="note">
        Dati insufficienti per la curva di calibrazione: servono almeno{" "}
        <strong>{data.min_positives}</strong> frane reali nella finestra, finora{" "}
        <strong>{data.n_positives}</strong>. Il grafico comparirà quando se ne
        accumuleranno — è ciò che dice se «quando l&apos;IA stima 30%, franano
        davvero ~30 casi su 100».
      </p>
    );
  }

  const iw = P.w - 2 * P.m;
  const ih = P.h - 2 * P.m;
  const sx = (v: number): number => P.m + v * iw;
  const sy = (v: number): number => P.m + ih - v * ih; // 0 in basso, 1 in alto

  return (
    <figure className="sci-chart">
      <svg viewBox={`0 0 ${P.w} ${P.h}`} role="img" aria-labelledby="rel-t rel-d">
        <title id="rel-t">Curva di calibrazione del modello IA</title>
        <desc id="rel-d">
          Probabilità prevista (asse X) contro frequenza reale osservata (asse
          Y). La diagonale tratteggiata è la calibrazione perfetta: più i punti
          le stanno vicino, meglio l&apos;IA è calibrata.
        </desc>
        {/* assi */}
        <line x1={P.m} y1={P.m} x2={P.m} y2={P.m + ih} stroke="#9aa1ad" />
        <line x1={P.m} y1={P.m + ih} x2={P.m + iw} y2={P.m + ih} stroke="#9aa1ad" />
        {/* diagonale = calibrazione perfetta */}
        <line
          x1={sx(0)}
          y1={sy(0)}
          x2={sx(1)}
          y2={sy(1)}
          stroke="#9467bd"
          strokeDasharray="4 4"
        />
        {/* punti (predetto, osservato) */}
        {data.bins.map((b) => (
          <circle
            key={`${b.lo}-${b.hi}`}
            cx={sx(b.predicted_mean)}
            cy={sy(b.observed_freq)}
            r={4}
            fill="#1f77b4"
          >
            <title>{`previsto ${(b.predicted_mean * 100).toFixed(0)}% → osservato ${(b.observed_freq * 100).toFixed(0)}% (${b.count} celle)`}</title>
          </circle>
        ))}
        <text x={P.m + iw / 2} y={P.h - 6} fontSize={11} textAnchor="middle" fill="#5e6473">
          probabilità prevista
        </text>
        <text
          x={12}
          y={P.m + ih / 2}
          fontSize={11}
          textAnchor="middle"
          fill="#5e6473"
          transform={`rotate(-90 12 ${P.m + ih / 2})`}
        >
          frequenza osservata
        </text>
      </svg>
      <figcaption className="exp-note">
        Diagonale = calibrazione perfetta. Punti sopra la diagonale: l&apos;IA
        sottostima; sotto: sovrastima. ({data.n_positives} frane reali nella
        finestra.)
      </figcaption>
    </figure>
  );
}
