import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import type { NationalReportResponse } from "../types";

/**
 * Compact national picture for the dashboard sidebar — absorbs the old
 * "Situazione Italia" page: headline stats always visible, deterministic
 * report + ML shadow top behind a native <details>.
 */
export function NationalStrip(): JSX.Element {
  const [report, setReport] = useState<NationalReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getNationalReport(ctrl.signal)
      .then(setReport)
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted)
          setError(err instanceof Error ? err.message : String(err));
      });
    return () => ctrl.abort();
  }, []);

  if (error) {
    return (
      <section className="national-strip" aria-label="Quadro nazionale">
        <h2>Italia · quadro nazionale</h2>
        <p className="panel-error">{error}</p>
      </section>
    );
  }
  if (!report) {
    return (
      <section className="national-strip" aria-label="Quadro nazionale">
        <h2>Italia · quadro nazionale</h2>
        <p>caricamento…</p>
      </section>
    );
  }

  return (
    <section className="national-strip" aria-label="Quadro nazionale">
      <h2>Italia · quadro nazionale</h2>
      <p className="alert-meta">
        {new Date(report.generated_at).toLocaleString("it-IT")} ·{" "}
        {report.totals.cells.toLocaleString("it-IT")} celle ·{" "}
        {report.totals.regions} regioni
      </p>
      <div className="strip-stats">
        <div>
          <strong className="mono">{report.totals.high_or_above}</strong>
          <span>High+</span>
        </div>
        <div>
          <strong className="mono">
            {report.totals.moderate.toLocaleString("it-IT")}
          </strong>
          <span>Moderate</span>
        </div>
        <div>
          <strong className="mono">{report.alerts_24h}</strong>
          <span>alert 24h</span>
        </div>
        <div>
          <strong className="mono">{report.forecast_alerts_24h}</strong>
          <span>previsioni</span>
        </div>
      </div>
      <details>
        <summary>Report e modello ML</summary>
        <p className="strip-report">{report.report_it}</p>
        {report.ml_top_cells.length > 0 ? (
          <>
            <p className="alert-meta" style={{ marginBottom: 4 }}>
              Top ML <span className="shadow-badge">shadow</span> — non guida
              gli alert:
            </p>
            <ul className="top-cells">
              {report.ml_top_cells.slice(0, 3).map((c) => (
                <li key={c.cell_id}>
                  <code>{c.cell_id}</code>{" "}
                  <span className="mono">P={c.probability.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </details>
    </section>
  );
}

export default NationalStrip;
