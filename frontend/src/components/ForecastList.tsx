import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL } from "../lib/risk-colors";
import type { ForecastAlertItem, RiskLevel } from "../types";

/**
 * PREVISIONE dispatches from the scheduled forecast sweep (+48h with
 * forecast rain). Empty is the healthy state: it means no region is
 * predicted to reach the alert threshold in the window.
 */
export function ForecastList(): JSX.Element {
  const [items, setItems] = useState<ForecastAlertItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getForecastAlerts({ sinceHours: 72 }, ctrl.signal)
      .then((resp) => setItems(resp.items))
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted)
          setError(err instanceof Error ? err.message : String(err));
      });
    return () => ctrl.abort();
  }, []);

  return (
    <section className="alert-list" aria-label="Previsioni">
      <h2>Previsioni</h2>
      {error ? (
        <p className="panel-error">{error}</p>
      ) : items === null ? (
        <p>caricamento…</p>
      ) : items.length === 0 ? (
        <p className="alert-meta">
          Nessuna regione prevista sopra soglia a +48h nelle ultime 72 ore —
          la sweep previsionale gira ogni 6 ore sulla pioggia prevista.
        </p>
      ) : (
        <ul>
          {items.map((it) => (
            <li key={`${it.aoi_id}-${it.dispatched_at}`}>
              <span className="alert-body">
                <span
                  className="alert-level-bar"
                  style={{
                    background:
                      RISK_COLOR_BY_LEVEL[it.max_level as RiskLevel] ?? "#888",
                  }}
                  aria-hidden
                />
                <span className="alert-content">
                  <span className="alert-row">
                    <strong>
                      {it.aoi_id.replace(/^it-/, "").replace(/-/g, " ")}
                    </strong>
                    <span className="alert-score">
                      +{it.horizon_h}h · {it.max_score.toFixed(2)}
                    </span>
                  </span>
                  <span className="alert-meta">
                    {it.cells_alerted} celle previste ≥ {it.max_level} ·{" "}
                    {new Date(it.dispatched_at).toLocaleString("it-IT")}
                  </span>
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default ForecastList;
