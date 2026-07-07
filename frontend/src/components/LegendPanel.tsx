import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_CLASSES } from "../lib/risk-colors";
import type { LegendClass } from "../types";

const PC_COLOR: Record<string, string> = {
  verde: "#2e8540",
  gialla: "#c9a20a",
  arancione: "#d9730d",
  rossa: "#c92a2a",
};

/**
 * Five-class risk legend.
 *
 * Each row pairs the colour swatch with the Italian class label **and**
 * the [lo, hi) score range, so the map stays interpretable without
 * relying on colour alone (accessibility, §6 acceptance criterion).
 * When the backend is reachable, each class also shows its Protezione
 * Civile alert colour (presentation-only mapping from /api/legend).
 */
export function LegendPanel(): JSX.Element {
  const [pcByLevel, setPcByLevel] = useState<Record<string, string>>({});

  useEffect(() => {
    const controller = new AbortController();
    defaultApiClient
      .getLegend(controller.signal)
      .then((legend) => {
        const map: Record<string, string> = {};
        legend.classes.forEach((c: LegendClass) => {
          map[c.level] = c.pc_alert;
        });
        setPcByLevel(map);
      })
      .catch(() => {
        // Static legend still renders — the PC chips are additive.
      });
    return () => controller.abort();
  }, []);

  return (
    <section className="legend-panel" aria-label="Legenda classi di rischio">
      <h2>Classi di rischio</h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {RISK_CLASSES.map((c) => (
          <li key={c.level} className="legend-row">
            <span
              className="legend-swatch"
              role="presentation"
              aria-hidden
              style={{ background: c.color }}
            />
            <span>
              {c.label}{" "}
              <small style={{ color: "#5e6473" }}>({c.short})</small>
              {((pc) =>
                pc ? (
                  <span
                    className="pc-chip"
                    title={`Allerta Protezione Civile: ${pc}`}
                    style={{ background: PC_COLOR[pc] ?? "#888" }}
                  >
                    {pc}
                  </span>
                ) : null)(pcByLevel[c.level])}
            </span>
            <span className="legend-range">
              {c.range[0].toFixed(2)}-{c.range[1].toFixed(2)}
            </span>
          </li>
        ))}
      </ul>
      <p className="legend-note">
        Le liste mettono prima le celle vicine a centri abitati e strade
        (🏠 🛣): stesso rischio, più conseguenze. Colori e numeri seguono
        sempre la scala qui sopra.
      </p>
    </section>
  );
}

export default LegendPanel;
