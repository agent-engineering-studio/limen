import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { NationalReportResponse } from "../types";

/**
 * Compact national picture for the dashboard sidebar — absorbs the old
 * "Situazione Italia" page: headline stats always visible, deterministic
 * report + ML shadow top behind a native <details>.
 */
export function NationalStrip(): JSX.Element {
  const [report, setReport] = useState<NationalReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { selected, multi } = useHazard();

  useEffect(() => {
    const ctrl = new AbortController();
    // Il report si azzera al cambio pericolo: le testate sono per pericolo,
    // e lasciare quelle di prima mentre arriva la risposta le attribuirebbe
    // al pericolo appena scelto.
    setReport(null);
    setError(null);
    defaultApiClient
      .getNationalReport(ctrl.signal, selected)
      .then(setReport)
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted)
          setError(err instanceof Error ? err.message : String(err));
      });
    return () => ctrl.abort();
  }, [selected]);

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
      {multi ? (
        // In vista d'insieme le testate restano quelle di *un* pericolo (le
        // celle non si sommano fra pericoli: sono le stesse celle). Dirlo è
        // l'unico modo di non farle leggere come un totale nazionale.
        <p className="alert-meta">
          testate:{" "}
          {report.hazards.find((h) => h.hazard === report.hazard)?.label_it ??
            report.hazard}
        </p>
      ) : null}
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
      {multi && report.hazards.length > 1 ? (
        <ul className="strip-hazards">
          {report.hazards.map((b) => (
            <li key={b.hazard}>
              <span className={`hazard-dot ${b.hazard}`} aria-hidden />
              {b.label_it}:{" "}
              <span className="mono">{b.totals.high_or_above}</span> High+,{" "}
              <span className="mono">
                {b.totals.moderate.toLocaleString("it-IT")}
              </span>{" "}
              Moderate
            </li>
          ))}
        </ul>
      ) : null}
      {((c) => {
        const righe: string[] = [];
        if (c.post_fire_flood && c.post_fire_flood.cells > 0) {
          righe.push(
            `${c.post_fire_flood.cells} aree bruciate con rischio allagamento più alto`,
          );
        }
        if (c.joint_rain && c.joint_rain.cells > 0) {
          righe.push(
            `${c.joint_rain.cells} aree sopra soglia per più di un pericolo`,
          );
        }
        return righe.length > 0 ? (
          <p className="strip-cascades" aria-label="Cascate attive">
            ⛓ {righe.join(" · ")}
          </p>
        ) : null;
      })(report.cascades)}
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
                  {c.place ?? c.cell_id} (
                  {c.aoi_id.replace(/^it-/, "").replace(/-/g, " ")}) ·{" "}
                  <span className="mono">
                    {Math.round(c.probability * 100)}%
                  </span>
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
