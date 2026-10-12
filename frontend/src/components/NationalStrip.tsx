import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard, useNomePericolo } from "../lib/hazard";
import { locale, testi, useLingua, useTesti } from "../lib/i18n";
import { describeFailure, isStale, relativeTime } from "../lib/panel-state";
import { verdictFromHazards } from "../lib/verdict";
import type { HazardType, NationalReportResponse } from "../types";
import HazardSelector from "./HazardSelector";
import type { RigaPericolo } from "./HazardSelector";
import { PanelDegraded, PanelLoading } from "./PanelState";

const T = testi(
  {
    titolo: "Quadro nazionale",
    celle: (n: string) => `${n} celle · 1 km²`,
    carico: "Carico il quadro nazionale",
    maiCalcolato: "mai calcolato",
    fermi: "Dati fermi da più di tre ore: il calcolo dovrebbe girare ogni ora.",
    aggiornato: (quando: string, regioni: number) =>
      `Quadro aggiornato ${quando} · ${regioni} regioni. Limen affianca e non ` +
      "sostituisce l'allertamento della Protezione Civile. ",
    cosaVuolDire: "Cosa vuol dire",
    dettaglio: "Dettaglio: allerte, cascate e modello ML",
    allerte: " allerte nelle 24 ore · ",
    previsioni: " previsioni sopra soglia",
    bruciate: (n: number) => `${n} aree bruciate con rischio allagamento più alto`,
    congiunte: (n: number) => `${n} aree sopra soglia per più di un pericolo`,
    cascate: "Cascate attive",
    topMl: "Top ML ",
    nonGuida: " — non guida gli alert:",
  },
  {
    titolo: "National overview",
    celle: (n: string) => `${n} cells · 1 km²`,
    carico: "Loading the national overview",
    maiCalcolato: "never computed",
    fermi: "Data stale for more than three hours: the computation should run every hour.",
    aggiornato: (quando: string, regioni: number) =>
      `Overview updated ${quando} · ${regioni} regions. Limen supports, and does not ` +
      "replace, Civil Protection warnings. ",
    cosaVuolDire: "What this means",
    dettaglio: "Details: alerts, cascades and ML model",
    allerte: " alerts in the last 24 hours · ",
    previsioni: " forecasts above threshold",
    bruciate: (n: number) => `${n} burnt areas with higher flood risk`,
    congiunte: (n: number) => `${n} areas above threshold for more than one hazard`,
    cascate: "Active cascades",
    topMl: "Top ML ",
    nonGuida: " — does not drive alerts:",
  },
);

/**
 * Compact national picture for the dashboard sidebar — absorbs the old
 * "Situazione Italia" page: headline stats always visible, deterministic
 * report + ML shadow top behind a native <details>.
 */
export function NationalStrip(): JSX.Element {
  const [report, setReport] = useState<NationalReportResponse | null>(null);
  const [errore, setErrore] = useState<{ err: unknown } | null>(null);
  const t = useTesti(T);
  const { lingua } = useLingua();
  const loc = locale(lingua);
  const nome = useNomePericolo();
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
    setErrore(null);
    defaultApiClient
      .getNationalReport(ctrl.signal, selected)
      .then(setReport)
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        // Il messaggio tecnico resta dove serve a chi ripara; in pagina va
        // quello che una persona può leggere.
        console.error("national report", err);
        setErrore({ err });
      });
    return () => ctrl.abort();
  }, [selected, tentativo]);

  const testa = (
    <div className="rail-testa">
      <h2>{t.titolo}</h2>
      {report ? (
        <span className="rail-meta mono">{t.celle(report.totals.cells.toLocaleString(loc))}</span>
      ) : null}
    </div>
  );

  if (errore) {
    return (
      <section className="national-strip rail-sezione" aria-label={t.titolo}>
        {testa}
        <PanelDegraded failure={describeFailure(errore.err, lingua)} onRetry={riprova} />
      </section>
    );
  }
  if (!report) {
    return (
      <section className="national-strip rail-sezione" aria-label={t.titolo}>
        {testa}
        <HazardSelector />
        <PanelLoading label={t.carico} />
      </section>
    );
  }

  // I tre indici insieme, non uno alla volta: sapere che l'incendio ha aree
  // in classe Alta mentre le frane non ne hanno richiedeva due clic e la
  // memoria del numero visto prima. Ora sono le righe del selettore stesso.
  const verdetto = verdictFromHazards(
    report.hazards.map((h) => ({
      hazard: h.hazard,
      label_it: lingua === "it" ? h.label_it : nome(h.hazard),
      totals: h.totals,
      computed_at: h.computed_at,
    })),
    lingua,
  );
  const righe: Partial<Record<HazardType, RigaPericolo>> = {};
  for (const l of verdetto.lines) {
    const tot = report.hazards.find((h) => h.hazard === l.hazard)?.totals;
    if (!tot) continue;
    righe[l.hazard as HazardType] = {
      cifra: (l.tone === "alert" ? tot.high_or_above : tot.moderate).toLocaleString(loc),
      dettaglio: l.text,
      tono: l.tone,
      // L'età per pericolo: con l'alluvione ferma da due giorni accanto
      // all'incendio di un'ora fa, un solo «aggiornato» per tutta la sezione
      // diceva una cosa falsa su una delle due.
      eta: l.computed_at ? relativeTime(l.computed_at, undefined, lingua) : t.maiCalcolato,
      vecchio: l.computed_at ? isStale(l.computed_at) : true,
    };
  }
  const vecchio = isStale(report.generated_at);

  return (
    <section className="national-strip rail-sezione" aria-label={t.titolo}>
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
          {t.fermi}
        </p>
      ) : null}
      <p className="rail-nota">
        {t.aggiornato(relativeTime(report.generated_at, undefined, lingua), report.totals.regions)}
        <a href="#/come-funziona">{t.cosaVuolDire}</a>
      </p>
      {/* Tutto il resto sta dietro un pannello a scomparsa. Sono numeri che
          si consultano, non che si sorvegliano: tenerli aperti allungava la
          colonna di tre schermate e spingeva i comuni — che è la lista su cui
          si decide qualcosa — sotto la piega. */}
      <details className="strip-more">
        <summary>{t.dettaglio}</summary>
        <p className="strip-allerte">
          <span className="mono">{report.alerts_24h}</span>
          {t.allerte}
          <span className="mono">{report.forecast_alerts_24h}</span>
          {t.previsioni}
        </p>
        {report.hazards.length > 1 ? (
          <ul className="strip-hazards">
            {report.hazards.map((b) => (
              <li key={b.hazard}>
                <span className={`hazard-dot ${b.hazard}`} aria-hidden />
                {lingua === "it" ? b.label_it : nome(b.hazard)}:{" "}
                <span className="mono">{b.totals.high_or_above}</span> High+,{" "}
                <span className="mono">
                  {b.totals.moderate.toLocaleString(loc)}
                </span>{" "}
                Moderate
              </li>
            ))}
          </ul>
        ) : null}
        {((c) => {
          const righe: string[] = [];
          if (c.post_fire_flood && c.post_fire_flood.cells > 0) {
            righe.push(t.bruciate(c.post_fire_flood.cells));
          }
          if (c.joint_rain && c.joint_rain.cells > 0) {
            righe.push(t.congiunte(c.joint_rain.cells));
          }
          return righe.length > 0 ? (
            <p className="strip-cascades" aria-label={t.cascate}>
              ⛓ {righe.join(" · ")}
            </p>
          ) : null;
        })(report.cascades)}
        <p className="strip-report">{report.report_it}</p>
        {report.ml_top_cells.length > 0 ? (
          <>
            <p className="alert-meta" style={{ marginBottom: 4 }}>
              {t.topMl}
              <span className="shadow-badge">shadow</span>
              {t.nonGuida}
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
