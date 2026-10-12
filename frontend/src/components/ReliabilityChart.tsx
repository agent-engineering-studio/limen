import type { JSX } from "react";
// Curva di calibrazione (reliability diagram) del challenger ML (#30).
// Gated sui dati: finché non ci sono abbastanza eventi reali mostra uno stato
// esplicito "dati insufficienti". Non autoritativo — solo diagnostica.

import { testi, useTesti } from "../lib/i18n";
import type { ReliabilityResponse } from "../types";

const P = { w: 240, h: 240, m: 34 };

const T = testi(
  {
    insufficienti: (min: number, n: number) => (
      <>
        Dati insufficienti per la curva di calibrazione: servono almeno <strong>{min}</strong>{" "}
        frane reali nella finestra, finora <strong>{n}</strong>. Il grafico comparirà quando se ne
        accumuleranno — è ciò che dice se «quando l&apos;IA stima 30%, franano davvero ~30 casi su
        100».
      </>
    ),
    titolo: "Curva di calibrazione del modello IA",
    desc:
      "Probabilità prevista (asse X) contro frequenza reale osservata (asse Y). La diagonale " +
      "tratteggiata è la calibrazione perfetta: più i punti le stanno vicino, meglio l'IA è " +
      "calibrata.",
    punto: (previsto: string, osservato: string, n: number) =>
      `previsto ${previsto}% → osservato ${osservato}% (${n} celle)`,
    asseX: "probabilità prevista",
    asseY: "frequenza osservata",
    didascalia: (n: number) =>
      `Diagonale = calibrazione perfetta. Punti sopra la diagonale: l'IA sottostima; sotto: ` +
      `sovrastima. (${n} frane reali nella finestra.)`,
  },
  {
    insufficienti: (min: number, n: number) => (
      <>
        Not enough data for the calibration curve: at least <strong>{min}</strong> real landslides
        are needed in the window, so far <strong>{n}</strong>. The chart will appear once enough
        accumulate — it is what tells whether «when the AI estimates 30%, about 30 cases in 100
        actually fail».
      </>
    ),
    titolo: "Calibration curve of the AI model",
    desc:
      "Predicted probability (X axis) against observed real frequency (Y axis). The dashed " +
      "diagonal is perfect calibration: the closer the points are to it, the better calibrated " +
      "the AI is.",
    punto: (previsto: string, osservato: string, n: number) =>
      `predicted ${previsto}% → observed ${osservato}% (${n} cells)`,
    asseX: "predicted probability",
    asseY: "observed frequency",
    didascalia: (n: number) =>
      `Diagonal = perfect calibration. Points above the diagonal: the AI underestimates; below: ` +
      `it overestimates. (${n} real landslides in the window.)`,
  },
);

export default function ReliabilityChart({
  data,
}: {
  data: ReliabilityResponse;
}): JSX.Element {
  const t = useTesti(T);
  if (!data.sufficient) {
    return (
      <p className="shadow-muted" role="note">
        {t.insufficienti(data.min_positives, data.n_positives)}
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
        <title id="rel-t">{t.titolo}</title>
        <desc id="rel-d">{t.desc}</desc>
        {/* assi */}
        <line x1={P.m} y1={P.m} x2={P.m} y2={P.m + ih} stroke="#3a4655" />
        <line x1={P.m} y1={P.m + ih} x2={P.m + iw} y2={P.m + ih} stroke="#3a4655" />
        {/* diagonale = calibrazione perfetta */}
        <line
          x1={sx(0)}
          y1={sy(0)}
          x2={sx(1)}
          y2={sy(1)}
          stroke="#c6a8ff"
          strokeDasharray="4 4"
        />
        {/* punti (predetto, osservato) */}
        {data.bins.map((b) => (
          <circle
            key={`${b.lo}-${b.hi}`}
            cx={sx(b.predicted_mean)}
            cy={sy(b.observed_freq)}
            r={4}
            fill="#7fa7e8"
          >
            <title>
              {t.punto(
                (b.predicted_mean * 100).toFixed(0),
                (b.observed_freq * 100).toFixed(0),
                b.count,
              )}
            </title>
          </circle>
        ))}
        <text x={P.m + iw / 2} y={P.h - 6} fontSize={11} textAnchor="middle" fill="#94a3b4">
          {t.asseX}
        </text>
        <text
          x={12}
          y={P.m + ih / 2}
          fontSize={11}
          textAnchor="middle"
          fill="#94a3b4"
          transform={`rotate(-90 12 ${P.m + ih / 2})`}
        >
          {t.asseY}
        </text>
      </svg>
      <figcaption className="exp-note">{t.didascalia(data.n_positives)}</figcaption>
    </figure>
  );
}
