import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
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
  // I cutoff arrivano dal backend perché sono **per pericolo** (#84): quelli
  // statici in RISK_CLASSES sono le soglie delle frane, e mostrarli per un
  // altro pericolo etichetterebbe male i suoi colori. Restano solo come
  // ripiego finché la prima risposta non arriva, o se l'API è irraggiungibile.
  const [ranges, setRanges] = useState<Record<string, [number, number]>>({});
  const { selected } = useHazard();

  useEffect(() => {
    // I chip di allerta sono per pericolo: senza azzerarli, una legenda che
    // fallisce dopo un cambio lascerebbe quelli del pericolo precedente.
    setPcByLevel({});
    setRanges({});
    const controller = new AbortController();
    defaultApiClient
      .getLegend(controller.signal, selected)
      .then((legend) => {
        const map: Record<string, string> = {};
        const bounds: Record<string, [number, number]> = {};
        legend.classes.forEach((c: LegendClass) => {
          map[c.level] = c.pc_alert;
          bounds[c.level] = [c.lo, c.hi];
        });
        setPcByLevel(map);
        setRanges(bounds);
      })
      .catch(() => {
        // Static legend still renders — the PC chips are additive.
      });
    return () => controller.abort();
  }, [selected]);

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
              {((r) => `${r[0].toFixed(2)}-${r[1].toFixed(2)}`)(
                ranges[c.level] ?? c.range,
              )}
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
