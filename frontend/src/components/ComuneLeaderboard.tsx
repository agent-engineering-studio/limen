// Classifica dei comuni a maggior rischio (rollup amministrativo, C).
// Ordinati lato server per esposizione; mostrati solo se ci sono comuni con
// celle in allerta. Non autoritativo — riflette l'ultimo assessment per cella.

import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { ComuneRisk } from "../types";

export default function ComuneLeaderboard(): JSX.Element | null {
  const [comuni, setComuni] = useState<ComuneRisk[]>([]);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getTopComuni(undefined, 20, ctrl.signal)
      .then((r) => setComuni(r.comuni))
      .catch(() => setComuni([]));
    return () => ctrl.abort();
  }, []);

  if (comuni.length === 0) return null;

  return (
    <section className="comuni-board" aria-label="Comuni a maggior rischio">
      <h3>Comuni a maggior rischio</h3>
      <ol>
        {comuni.map((c) => (
          <li key={c.istat_code}>
            <span
              className="cb-dot"
              style={{ background: RISK_COLOR_BY_LEVEL[c.worst_class] }}
              title={RISK_LABEL_IT_BY_LEVEL[c.worst_class]}
            />
            <span className="cb-name">{c.name}</span>
            <span className="cb-meta">{c.n_alert} in allerta</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
