import { useCallback, useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { PanelFailure } from "../lib/panel-state";
import { describeFailure } from "../lib/panel-state";
import { PanelDegraded, PanelEmpty, PanelLoading } from "./PanelState";
import { RISK_COLOR_BY_LEVEL } from "../lib/risk-colors";
import type { ForecastAlertItem, RiskLevel } from "../types";

/**
 * PREVISIONE dispatches from the scheduled forecast sweep (+48h with
 * forecast rain). Empty is the healthy state: it means no region is
 * predicted to reach the alert threshold in the window.
 */
export function ForecastList(): JSX.Element {
  const [items, setItems] = useState<ForecastAlertItem[] | null>(null);
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  const [tentativo, setTentativo] = useState(0);
  const { selected: hazard } = useHazard();
  const riprova = useCallback(() => setTentativo((n) => n + 1), []);

  useEffect(() => {
    setFailure(null);
    setItems(null);
    const ctrl = new AbortController();
    defaultApiClient
      .getForecastAlerts({ sinceHours: 72, hazard }, ctrl.signal)
      .then((resp) => setItems(resp.items))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        console.error("forecast alerts", err);
        setFailure(describeFailure(err));
      });
    return () => ctrl.abort();
  }, [hazard, tentativo]);

  return (
    <section className="alert-list" aria-label="Previsioni">
      <h2>Previsioni</h2>
      {failure ? (
        <PanelDegraded failure={failure} onRetry={riprova} />
      ) : items === null ? (
        <PanelLoading label="Carico le previsioni" />
      ) : items.length === 0 ? (
        <PanelEmpty
          title="Nessuna regione prevista sopra soglia"
          detail="A +48 ore, nelle ultime 72. Il calcolo previsionale gira ogni 6 ore sulla pioggia prevista."
        />
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
