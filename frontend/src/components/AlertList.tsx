import { useEffect, useState } from "react";

import { defaultApiClient, ApiClientError } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { AlertItem } from "../types";

export interface AlertListProps {
  /** Minimum class to include in the list. */
  readonly threshold?: "Moderate" | "High" | "VeryHigh";
  /** Trailing window in hours (default 72). */
  readonly sinceHours?: number;
  /** Called when the user clicks an alert — typically a "fly-to" callback. */
  readonly onAlertClick?: (alert: AlertItem) => void;
}

export function AlertList(props: AlertListProps): JSX.Element {
  const threshold = props.threshold ?? "High";
  const sinceHours = props.sinceHours ?? 72;
  const onAlertClick = props.onAlertClick;
  const [items, setItems] = useState<AlertItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setItems(null);
    setError(null);
    defaultApiClient
      .getAlerts({ threshold, sinceHours }, ctrl.signal)
      .then((resp) => setItems(resp.items))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        if (err instanceof ApiClientError) {
          setError(`Errore ${err.status}: ${err.message}`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("errore sconosciuto");
        }
      });
    return () => ctrl.abort();
  }, [threshold, sinceHours]);

  if (error) {
    return (
      <section className="alert-list" aria-label="Allerte recenti">
        <h2>Allerte recenti</h2>
        <p style={{ color: "#a72020" }}>{error}</p>
      </section>
    );
  }
  if (items === null) {
    return (
      <section className="alert-list" aria-label="Allerte recenti">
        <h2>Allerte recenti</h2>
        <p>caricamento…</p>
      </section>
    );
  }
  if (items.length === 0) {
    return (
      <section className="alert-list" aria-label="Allerte recenti">
        <h2>Allerte recenti</h2>
        <p style={{ color: "#5e6473" }}>
          Nessuna allerta {RISK_LABEL_IT_BY_LEVEL[threshold].toLowerCase()} o
          superiore nelle ultime {sinceHours} ore.
        </p>
      </section>
    );
  }

  return (
    <section className="alert-list" aria-label="Allerte recenti">
      <h2>Allerte recenti</h2>
      <ul>
        {items.map((it) => (
          <li key={`${it.cell_id}-${it.computed_at}`}>
            <button
              type="button"
              className="alert-item"
              style={{ width: "100%", textAlign: "left" }}
              onClick={() => onAlertClick?.(it)}
            >
              <span className="alert-body">
                <span
                  className="alert-level-bar"
                  style={{ background: RISK_COLOR_BY_LEVEL[it.level] }}
                  aria-hidden
                />
                <span className="alert-content">
                  <span className="alert-row">
                    <strong>{(it.aoi_id ?? "—").replace(/^it-/, "").replace(/-/g, " ")}</strong>
                    <span className="alert-score">
                      {it.score.toFixed(2)} {RISK_LABEL_IT_BY_LEVEL[it.level]}
                    </span>
                  </span>
                  <span className="alert-meta">
                    cella {it.cell_id} ·{" "}
                    {new Date(it.computed_at).toLocaleString("it-IT")}
                  </span>
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default AlertList;
