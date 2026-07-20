// Capitolo 3 del percorso «Capire Limen» — la diagnostica del modello ML in
// ombra (#26). L'INTRO didattica (cos'è lo shadow, perché due modelli, come si
// legge la mappa) è per tutti; i DATI LIVE (numeri, tabelle, mappa) sono
// riservati al ruolo ml-ops. NON autoritativo: il V1 guida sempre le allerte.

import { useEffect, useState } from "react";

import { RISK_CLASSES } from "../lib/risk-colors";
import { defaultApiClient } from "../lib/api-client";
import { useMlOps } from "../lib/roles";
import type { ReliabilityResponse, ShadowSummaryResponse } from "../types";
import { ChapterFooter, CourseHeader } from "./Course";
import DivergenceMap from "./DivergenceMap";
import ReliabilityChart from "./ReliabilityChart";
import { nationalAgreement } from "./ShadowPanel";

const pct = (x: number): string => `${Math.round(x * 100)}%`;

/** Indice di classe (0=None … 4=VeryHigh) per un punteggio champion. */
export function championClassIndex(score: number): number {
  for (let i = RISK_CLASSES.length - 1; i >= 0; i--) {
    const c = RISK_CLASSES[i];
    if (c && score >= c.range[0]) return i;
  }
  return 0;
}

/** Il sistema ufficiale avrebbe segnalato l'evento (classe ≥ Moderato)? */
export function championWouldAlert(score: number): boolean {
  return championClassIndex(score) >= 2; // Moderate è indice 2
}

// --- Dati live, riservati a ml-ops -----------------------------------------
function LiveDiagnostics(): JSX.Element {
  const [data, setData] = useState<ShadowSummaryResponse | null>(null);
  const [reliability, setReliability] = useState<ReliabilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getShadowSummary(ctrl.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError("Impossibile caricare la diagnostica shadow.");
      });
    // Reliability is optional/gated — its failure must not break the panel.
    defaultApiClient
      .getShadowReliability(ctrl.signal)
      .then(setReliability)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (!data) return <p className="shadow-muted">Caricamento dei dati…</p>;

  const agreement = nationalAgreement(data.regions);
  const events = data.truth_events;
  const officialCaught = events.filter(
    (e) => e.champion_score !== null && championWouldAlert(e.champion_score),
  ).length;

  return (
    <>
      <h3>Accordo complessivo</h3>
      <p className="shadow-headline">
        Su <strong>{data.total_pairs.toLocaleString("it-IT")}</strong>{" "}
        valutazioni osservate, l&apos;IA concorda col sistema ufficiale sulla
        classe di rischio nel{" "}
        <strong>{agreement !== null ? pct(agreement) : "—"}</strong> dei casi.
      </p>

      <h3>Eventi reali nella finestra</h3>
      {events.length === 0 ? (
        <p className="shadow-muted">
          Nessun evento di frana datato (catalogo ITALICA) nella finestra di
          osservazione. Il confronto sul <em>recall</em> — quante frane reali
          ciascun motore avrebbe segnalato — sarà possibile quando se ne
          accumuleranno. È l&apos;evidenza che conta di più per decidere la
          promozione.
        </p>
      ) : (
        <>
          <p>
            Su <strong>{events.length}</strong> event
            {events.length === 1 ? "o" : "i"} reale, il sistema ufficiale ne
            aveva già <strong>{officialCaught}</strong> ad almeno «Moderato»
            nelle 48 h precedenti. La probabilità dell&apos;IA è a fianco, ancora
            <em> in valutazione</em>.
          </p>
          <table className="shadow-table">
            <thead>
              <tr>
                <th>Regione</th>
                <th>Evento (UTC)</th>
                <th>Sistema ufficiale</th>
                <th>IA (in prova)</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={`${e.cell_id}-${e.event_time}`}>
                  <td>{e.aoi_name}</td>
                  <td>{e.event_time.slice(0, 16).replace("T", " ")}</td>
                  <td>
                    {e.champion_score !== null
                      ? `${RISK_CLASSES[championClassIndex(e.champion_score)]!.label} (${e.champion_score.toFixed(2)})`
                      : "—"}
                  </td>
                  <td>{e.ml_probability !== null ? e.ml_probability.toFixed(2) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>Accordo per regione</h3>
      {data.regions.length === 0 ? (
        <p className="shadow-muted">Nessuna regione con dati nella finestra.</p>
      ) : (
        <table className="shadow-table">
          <thead>
            <tr>
              <th>Regione</th>
              <th>Accordo sulle classi</th>
              <th>Valutazioni</th>
            </tr>
          </thead>
          <tbody>
            {[...data.regions]
              .sort((a, b) => b.n - a.n)
              .map((r) => (
                <tr key={r.aoi_id}>
                  <td>{r.aoi_name}</td>
                  <td>{pct(r.class_agreement)}</td>
                  <td>{r.n.toLocaleString("it-IT")}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}

      <h3>Mappa della divergenza</h3>
      <p className="shadow-muted">
        Ogni cella colorata per <em>quanto</em> l&apos;IA si discosta dal sistema
        ufficiale (vedi la legenda della mappa). Colori neutri, non la scala del
        rischio: qui il colore significa «disaccordo tra modelli», non «pericolo».
      </p>
      <DivergenceMap />

      <h3>Calibrazione (reliability)</h3>
      <p className="shadow-muted">
        Quando l&apos;IA stima una probabilità, quella percentuale corrisponde
        alla frequenza reale? Più i punti stanno sulla diagonale, meglio è
        calibrata.
      </p>
      {reliability ? (
        <ReliabilityChart data={reliability} />
      ) : (
        <p className="shadow-muted">Caricamento della calibrazione…</p>
      )}

      <p className="exp-note">
        Finestra dal {data.since.slice(0, 10)} · modello IA:{" "}
        {data.model_versions.join(", ") || "n/d"}.
      </p>
    </>
  );
}

// --- Pagina: intro pubblica + dati gated -----------------------------------
export default function ShadowDiagnosticsPage(): JSX.Element {
  const { allowed } = useMlOps();
  return (
    <div className="explainer sci" aria-label="Diagnostica ML (shadow)">
      <article>
        <CourseHeader
          current={3}
          learn="cos'è il «modello in ombra», perché confrontiamo due modelli, e come leggere la mappa della divergenza."
        />
        <p className="exp-eyebrow">Capitolo avanzato</p>
        <h2>La diagnostica del modello sperimentale (IA)</h2>

        <p className="exp-lede">
          Accanto al sistema ufficiale ne gira un secondo, un&apos;
          <strong>intelligenza artificiale in prova</strong>. Questa pagina
          spiega com&apos;è tenuto d&apos;occhio prima di decidere se fidarsi.
        </p>

        <h3>Cos&apos;è il «modello in ombra»</h3>
        <p>
          Il sistema ufficiale (lo chiamiamo <strong>V1</strong>) calcola le
          allerte, come descritto nei capitoli precedenti. In parallelo, senza
          mai toccare le allerte, un modello di <strong>machine learning</strong>{" "}
          (V2) fa la sua stima sugli stessi dati e la registra a parte. Gira «in
          ombra»: osserviamo come se la caverebbe, ma le decisioni restano al V1.
        </p>

        <h3>Perché due modelli</h3>
        <p>
          Per capire, con mesi di prove alla mano, <em>se</em> l&apos;IA sia
          davvero più brava — <strong>prima</strong> di affidarle qualcosa. Il
          passaggio di consegne (la «promozione») è una scelta{" "}
          <strong>manuale</strong>, mai automatica, e non avviene da questa
          pagina.
        </p>

        <h3>Cosa guardiamo</h3>
        <ul>
          <li>
            <strong>Accordo</strong>: quanto spesso i due modelli assegnano la
            stessa classe di rischio alla stessa cella. Un accordo basso, per un
            modello ancora in prova, è normale.
          </li>
          <li>
            <strong>Recall sugli eventi reali</strong>: prendendo le frane
            davvero avvenute, quale dei due le avrebbe segnalate prima. È la prova
            che conta di più.
          </li>
          <li>
            <strong>Mappa della divergenza</strong>: dove l&apos;IA vede{" "}
            <em>più</em> o <em>meno</em> rischio del sistema ufficiale — in
            <span className="dv-inline dv-less"> blu</span> vede meno,
            <span className="dv-inline dv-eq"> grigio</span> sono d&apos;accordo,
            <span className="dv-inline dv-more"> viola</span> vede più. Colori
            neutri di proposito: qui il colore è «disaccordo», non «pericolo».
          </li>
        </ul>

        {allowed ? (
          <LiveDiagnostics />
        ) : (
          <p className="shadow-note" role="note">
            I <strong>dati live</strong> (numeri, tabelle e mappa aggiornati)
            sono riservati agli operatori con ruolo <code>ml-ops</code>. La
            spiegazione qui sopra vale per tutti.
          </p>
        )}

        <ChapterFooter current={3} />
      </article>
    </div>
  );
}
