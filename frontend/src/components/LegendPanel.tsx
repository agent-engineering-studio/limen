import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import {
  HAZARD_HUE,
  RISK_CLASSES,
  riskClassesFor,
  riskColorsFor,
} from "../lib/risk-colors";
import type { HazardType, LegendClass, RiskLevel } from "../types";

const PC_COLOR: Record<string, string> = {
  verde: "#2e8540",
  gialla: "#c9a20a",
  arancione: "#d9730d",
  rossa: "#c92a2a",
};

/** I cinque colori in una riga: resta visibile anche con la legenda chiusa. */
/** La scala di riferimento della vista d'insieme: quella del pericolo di
 *  default. Nominata una volta perché è una scelta, non un dettaglio. */
const SCALA_RIFERIMENTO = "landslide" as const;

function ScalaColori({
  levels,
  hazard,
}: {
  levels: RiskLevel[];
  hazard: HazardType;
}): JSX.Element {
  const colori = riskColorsFor(hazard);
  return (
    <span className="legend-scale" aria-hidden>
      {levels.map((l) => (
        <span key={l} style={{ background: colori[l] }} />
      ))}
    </span>
  );
}

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
  const { selected, multi, available } = useHazard();

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

  // In vista d'insieme i cutoff sono diversi per pericolo, quindi la colonna
  // dei numeri non esiste: quello che serve leggere è la corrispondenza fra
  // tinta e pericolo, che nella vista d'insieme è l'unico modo di sapere
  // *cosa* colora una cella.
  if (multi) {
    // Una scala sola, non una matrice 5×3. La vista d'insieme portava due
    // informazioni in un colore — la tinta il pericolo, l'intensità la
    // gravità — e per decodificarla serviva questa tabella accanto: quindici
    // caselle per leggere una cella. Ora il colore dice quanto, e quale
    // pericolo lo dice il bordo delle celle in classe alta.
    return (
      <details className="legend-panel" aria-label="Legenda classi di rischio">
        <summary>
          <ScalaColori
            levels={RISK_CLASSES.map((c) => c.level)}
            hazard={SCALA_RIFERIMENTO}
          />
          Classi di rischio · tutti i pericoli
        </summary>
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {riskClassesFor(SCALA_RIFERIMENTO).map((c) => (
            <li key={c.level} className="legend-row">
              <span
                className="legend-swatch"
                role="presentation"
                aria-hidden
                style={{ background: c.color }}
              />
              <span>
                {c.label} <small style={{ color: "#5e6473" }}>({c.short})</small>
              </span>
              <span className="legend-range">
                {`${c.range[0].toFixed(2)}-${c.range[1].toFixed(2)}`}
              </span>
            </li>
          ))}
        </ul>
        <p className="legend-note">
          Il colore dice <strong>quanto</strong>: è la classe del pericolo
          peggiore in quel punto. <strong>Quale</strong> pericolo lo dice il
          bordo, sulle sole celle in classe Alta o superiore — dove la domanda
          nasce davvero.
        </p>
        <ul className="legend-hazards">
          {available.map((h) => (
            <li key={h.hazard}>
              <span
                className="legend-outline"
                aria-hidden
                style={{ borderColor: HAZARD_HUE[h.hazard] }}
              />
              {h.label_it}
            </li>
          ))}
        </ul>
        <p className="legend-note">
          Le soglie numeriche cambiano da un pericolo all&apos;altro: quelle
          qui sopra sono delle frane. Scegli un pericolo per vedere le sue.
        </p>
      </details>
    );
  }

  return (
    <details className="legend-panel" aria-label="Legenda classi di rischio">
      <summary>
        <ScalaColori levels={riskClassesFor(selected).map((c) => c.level)} hazard={selected} />
        Classi di rischio
      </summary>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {riskClassesFor(selected).map((c) => (
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
        sempre la scala qui sopra.{" "}
        <a href="#/documentazione/02-come-si-calcola-il-rischio">
          Come si calcola il rischio
        </a>
      </p>
    </details>
  );
}

export default LegendPanel;
