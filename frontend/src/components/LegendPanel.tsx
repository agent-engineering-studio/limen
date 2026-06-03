import { RISK_CLASSES } from "../lib/risk-colors";

/**
 * Five-class risk legend.
 *
 * Each row pairs the colour swatch with the Italian class label **and**
 * the [lo, hi) score range, so the map stays interpretable without
 * relying on colour alone (accessibility, §6 acceptance criterion).
 */
export function LegendPanel(): JSX.Element {
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
            </span>
            <span className="legend-range">
              {c.range[0].toFixed(2)}-{c.range[1].toFixed(2)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default LegendPanel;
