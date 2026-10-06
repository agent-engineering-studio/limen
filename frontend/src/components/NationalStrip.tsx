import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { PanelFailure } from "../lib/panel-state";
import { describeFailure, isStale, relativeTime } from "../lib/panel-state";
import { verdictFromHazards } from "../lib/verdict";
import type { HazardType, NationalReportResponse } from "../types";
import HazardSelector from "./HazardSelector";
import type { RigaPericolo } from "./HazardSelector";
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
  const { selected, available } = useHazard();
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

  const testa = (
    <div className="rail-testa">
      <h2>Quadro nazionale</h2>
      {report ? (
        <span className="rail-meta mono">
          {report.totals.cells.toLocaleString("it-IT")} celle · 1 km²
        </span>
      ) : null}
    </div>
  );

  if (failure) {
    return (
      <section className="national-strip rail-sezione" aria-label="Quadro nazionale">
        {testa}
        <PanelDegraded failure={failure} onRetry={riprova} />
      </section>
    );
  }
  if (!report) {
    return (
      <section className="national-strip rail-sezione" aria-label="Quadro nazionale">
        {testa}
        <HazardSelector />
        <PanelLoading label="Carico il quadro nazionale" />
      </section>
    );
  }

  // I tre indici insieme, non uno alla volta: sapere che l'incendio ha aree
  // in classe Alta mentre le frane non ne hanno richiedeva due clic e la
  // memoria del numero visto prima. Ora sono le righe del selettore stesso.
  const verdetto = verdictFromHazards(
    report.hazards.map((h) => ({
      hazard: h.hazard,
      label_it: h.label_it,
      totals: h.totals,
      computed_at: h.computed_at,
    })),
  );
  const righe: Partial<Record<HazardType, RigaPericolo>> = {};
  for (const l of verdetto.lines) {
    const t = report.hazards.find((h) => h.hazard === l.hazard)?.totals;
    if (!t) continue;
    righe[l.hazard as HazardType] = {
      cifra: (l.tone === "alert" ? t.high_or_above : t.moderate).toLocaleString("it-IT"),
      dettaglio: l.text,
      tono: l.tone,
      // L'età per pericolo: con l'alluvione ferma da due giorni accanto
      // all'incendio di un'ora fa, un solo «aggiornato» per tutta la sezione
      // diceva una cosa falsa su una delle due.
      eta: l.computed_at ? relativeTime(l.computed_at) : "mai calcolato",
      vecchio: l.computed_at ? isStale(l.computed_at) : true,
    };
  }
  const vecchio = isStale(report.generated_at);

  return (
    <section className="national-strip rail-sezione" aria-label="Quadro nazionale">
      {testa}
      {available.length >= 2 ? (
        <HazardSelector righe={righe} />
      ) : (
        // Senza scelta da fare — un pericolo solo, o la lista che non è
        // arrivata — il selettore non c'è, e la risposta resta a parole.
        <div className={`verdict tone-${verdetto.headline.tone}`}>
          <p className="verdict-text">{verdetto.headline.text}</p>
          {verdetto.headline.note ? (
            <p className="verdict-note">{verdetto.headline.note}</p>
          ) : null}
        </div>
      )}
      {vecchio ? (
        // Numeri fermi da ore mostrati senza dirlo sono peggio di nessun
        // numero: chi guarda li legge come «adesso».
        <p className="verdict-stale">
          Dati fermi da più di tre ore: il calcolo dovrebbe girare ogni ora.
        </p>
      ) : null}
      <p className="rail-nota">
        Quadro aggiornato {relativeTime(report.generated_at)} · {report.totals.regions}{" "}
        regioni. Limen affianca e non sostituisce l&apos;allertamento della
        Protezione Civile.{" "}
        <a href="#/come-funziona">Cosa vuol dire</a>
      </p>
      {/* Tutto il resto sta dietro un pannello a scomparsa. Sono numeri che
          si consultano, non che si sorvegliano: tenerli aperti allungava la
          colonna di tre schermate e spingeva i comuni — che è la lista su cui
          si decide qualcosa — sotto la piega. */}
      <details className="strip-more">
        <summary>Dettaglio: allerte, cascate e modello ML</summary>
        <p className="strip-allerte">
          <span className="mono">{report.alerts_24h}</span> allerte nelle 24 ore ·{" "}
          <span className="mono">{report.forecast_alerts_24h}</span> previsioni sopra
          soglia
        </p>
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
