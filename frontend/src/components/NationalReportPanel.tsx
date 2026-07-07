import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_CLASSES } from "../lib/risk-colors";
import type { NationalReportResponse } from "../types";

const PC_COLOR: Record<string, string> = {
  verde: "#2e8540",
  gialla: "#c9a20a",
  arancione: "#d9730d",
  rossa: "#c92a2a",
};

function levelColor(level: string): string {
  return RISK_CLASSES.find((c) => c.level === level)?.color ?? "#888";
}

/**
 * "Situazione Italia" — the national daily picture, same payload the
 * morning report and the `tool_national_report` MCP tool use.
 */
export function NationalReportPanel(): JSX.Element {
  const [report, setReport] = useState<NationalReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    defaultApiClient
      .getNationalReport(controller.signal)
      .then(setReport)
      .catch((err: unknown) => {
        if (!controller.signal.aborted)
          setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, []);

  if (error) {
    return (
      <section className="national-panel" aria-label="Situazione Italia">
        <h2>Situazione Italia</h2>
        <p role="alert" className="panel-error">
          Report non disponibile al momento: {error}
        </p>
      </section>
    );
  }
  if (!report) {
    return (
      <section className="national-panel" aria-label="Situazione Italia">
        <h2>Situazione Italia</h2>
        <p aria-busy="true">Caricamento del quadro nazionale…</p>
      </section>
    );
  }

  const regions = [...report.regions].sort(
    (a, b) => b.high_or_above - a.high_or_above || b.max_score - a.max_score,
  );
  const generated = new Date(report.generated_at);

  return (
    <section className="national-panel" aria-label="Situazione Italia">
      <p className="eyebrow">Quadro nazionale · aggiornamento orario</p>
      <h2>Situazione Italia</h2>
      <p className="panel-meta">
        Aggiornato al {generated.toLocaleString("it-IT")} ·{" "}
        {report.totals.cells.toLocaleString("it-IT")} celle in{" "}
        {report.totals.regions} regioni
      </p>

      <div className="stat-cards">
        <div className="stat-card">
          <strong>{report.totals.high_or_above}</strong>
          <span>celle High o superiori</span>
        </div>
        <div className="stat-card">
          <strong>{report.totals.moderate.toLocaleString("it-IT")}</strong>
          <span>celle Moderate</span>
        </div>
        <div className="stat-card">
          <strong>{report.alerts_24h}</strong>
          <span>alert operativi 24h</span>
        </div>
        <div className="stat-card">
          <strong>{report.forecast_alerts_24h}</strong>
          <span>alert previsionali 24h</span>
        </div>
      </div>

      <p className="report-text">{report.report_it}</p>

      <h3>Regioni per esposizione</h3>
      <div className="table-scroll">
        <table className="regions-table">
          <thead>
            <tr>
              <th>Regione</th>
              <th>Celle</th>
              <th>High+</th>
              <th>Moderate</th>
              <th>Score max</th>
            </tr>
          </thead>
          <tbody>
            {regions.map((r) => (
              <tr key={r.aoi_id}>
                <td>{r.aoi_id.replace(/^it-/, "").replace(/-/g, " ")}</td>
                <td>{r.cells_scored.toLocaleString("it-IT")}</td>
                <td>{r.high_or_above}</td>
                <td>{r.moderate.toLocaleString("it-IT")}</td>
                <td>{r.max_score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="top-cells-grid">
        <div>
          <h3>Top celle — motore deterministico</h3>
          <ul className="top-cells">
            {report.top_cells.slice(0, 5).map((c) => (
              <li key={c.cell_id}>
                <span
                  className="legend-swatch"
                  style={{ background: levelColor(c.level) }}
                  aria-hidden
                />
                <code>{c.cell_id}</code> {c.score.toFixed(2)} ({c.level})
              </li>
            ))}
          </ul>
        </div>
        {report.ml_top_cells.length > 0 ? (
          <div>
            <h3>
              Top celle — modello ML
              <span className="shadow-badge">shadow</span>
            </h3>
            <p className="panel-meta">
              Probabilità del challenger in osservazione: non guida gli
              alert.
            </p>
            <ul className="top-cells">
              {report.ml_top_cells.slice(0, 5).map((c) => (
                <li key={c.cell_id}>
                  <code>{c.cell_id}</code> P={c.probability.toFixed(2)}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
      <p className="panel-meta">
        Scala allerta Protezione Civile:{" "}
        {Object.entries(PC_COLOR).map(([name, color]) => (
          <span key={name} className="pc-chip" style={{ background: color }}>
            {name}
          </span>
        ))}
      </p>
    </section>
  );
}

export default NationalReportPanel;
