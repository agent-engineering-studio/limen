import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { PanelFailure } from "../lib/panel-state";
import { describeFailure, isStale, relativeTime } from "../lib/panel-state";
import { verdictFromHazards } from "../lib/verdict";
import type { NationalReportResponse } from "../types";
import { PanelDegraded, PanelLoading } from "./PanelState";

/**
 * Compact national picture for the dashboard sidebar — absorbs the old
 * "Situazione Italia" page: headline stats always visible, deterministic
 * report + ML shadow top behind a native <details>.
 */
export function NationalStrip(): JSX.Element {
  const [report, setReport] = useState<NationalReportResponse | null>(null);
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  // Cambiare questo numero rilancia l'effetto: è il «Riprova» del pannello
  // degradato, che senza un modo per richiedere i dati sarebbe un bottone
  // che invita a ricaricare la pagina intera.
  const [tentativo, setTentativo] = useState(0);
  const { selected } = useHazard();
  const riprova = useCallback(() => setTentativo((n) => n + 1), []);

  useEffect(() => {
    const ctrl = new AbortController();
    // Il report si azzera al cambio pericolo: le testate sono per pericolo,
    // e lasciare quelle di prima mentre arriva la risposta le attribuirebbe
    // al pericolo appena scelto.
    setReport(null);
    setFailure(null);
    defaultApiClient
      .getNationalReport(ctrl.signal, selected)
      .then(setReport)
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        // Il messaggio tecnico resta dove serve a chi ripara; in pagina va
        // quello che una persona può leggere.
        console.error("national report", err);
        setFailure(describeFailure(err));
      });
    return () => ctrl.abort();
  }, [selected, tentativo]);

  if (failure) {
    return (
      <section className="national-strip" aria-label="Quadro nazionale">
        <h2>Italia · quadro nazionale</h2>
        <PanelDegraded failure={failure} onRetry={riprova} />
      </section>
    );
  }
  if (!report) {
    return (
      <section className="national-strip" aria-label="Quadro nazionale">
        <h2>Italia · quadro nazionale</h2>
        <PanelLoading label="Carico il quadro nazionale" />
      </section>
    );
  }

  // I tre indici insieme, non uno alla volta: sapere che l'incendio ha aree
  // in classe Alta mentre le frane non ne hanno richiedeva due clic e la
  // memoria del numero visto prima.
  const verdetto = verdictFromHazards(
    report.hazards.map((h) => ({
      hazard: h.hazard,
      label_it: h.label_it,
      totals: h.totals,
      computed_at: h.computed_at,
    })),
  );
  const vecchio = isStale(report.generated_at);

  return (
    <section className="national-strip" aria-label="Quadro nazionale">
      <div className={`verdict tone-${verdetto.headline.tone}`}>
        <p className="verdict-text">{verdetto.headline.text}</p>
        {verdetto.headline.note ? (
          <p className="verdict-note">{verdetto.headline.note}</p>
        ) : null}
        {verdetto.lines.length > 1 ? (
          <ul className="verdict-hazards">
            {verdetto.lines.map((l) => (
              <li key={l.hazard} className={`tone-${l.tone}`}>
                <span className={`hazard-dot ${l.hazard}`} aria-hidden />
                <span className="vh-label">{l.label}</span>
                <span className="vh-text">{l.text}</span>
                {/* L'età per pericolo: con l'alluvione ferma da due giorni
                    accanto all'incendio di un'ora fa, un solo «aggiornato»
                    per tutta la sezione diceva una cosa falsa su una delle
                    due. */}
                <span className={`vh-age ${l.computed_at && isStale(l.computed_at) ? "is-stale" : ""}`}>
                  {l.computed_at ? relativeTime(l.computed_at) : "mai calcolato"}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        <p className="verdict-meta">
          quadro aggiornato {relativeTime(report.generated_at)} ·{" "}
          {report.totals.regions} regioni
        </p>
        {vecchio ? (
          // Numeri fermi da ore mostrati senza dirlo sono peggio di nessun
          // numero: chi guarda li legge come «adesso».
          <p className="verdict-stale">
            Dati fermi da più di tre ore: il calcolo dovrebbe girare ogni ora.
          </p>
        ) : null}
        <p className="verdict-disclaimer">
          Limen affianca e non sostituisce l&apos;allertamento della Protezione
          Civile. <a href="#/documentazione/01-limen-in-una-pagina">Cosa vuol dire</a>
        </p>
      </div>
      {/* Le quattro caselle sono di **un** pericolo, non di tutti: le celle
          non si sommano fra pericoli, sono le stesse celle. Il nome del
          pericolo sta ora sopra le caselle e non in una riga staccata sotto
          — con la testata che dice «Incendio: 5024 aree in classe Alta» e le
          caselle che dicono «0 High+», la distanza fra le due cose era il
          modo più facile di leggere un numero per un altro. */}
      <p className="strip-stats-head">
        {report.hazards.find((h) => h.hazard === report.hazard)?.label_it ??
          report.hazard}
        <span> · su {report.totals.cells.toLocaleString("it-IT")} celle</span>
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
      {/* Tutto il resto sta dietro un pannello a scomparsa. Sono numeri che
          si consultano, non che si sorvegliano: tenerli aperti allungava la
          colonna di tre schermate e spingeva i comuni — che è la lista su cui
          si decide qualcosa — sotto la piega. */}
      <details className="strip-more">
        <summary>Dettaglio per pericolo, cascate e modello ML</summary>
        {report.hazards.length > 1 ? (
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
