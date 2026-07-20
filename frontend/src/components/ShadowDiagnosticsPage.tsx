// Area di diagnostica ML (#26) — rotta #/diagnostica-ml, riservata al ruolo
// ml-ops. Contenuto più ricco del pannellino operatore, ma sempre in
// linguaggio piano. NON autoritativo: il motore V1 guida le allerte.
//
// Slice attuale: recall sugli eventi reali + accordo per regione (dati già in
// /api/shadow/summary). Mappa divergenza e reliability plot restano in #26.

import { useEffect, useState } from "react";

import { RISK_CLASSES } from "../lib/risk-colors";
import { defaultApiClient } from "../lib/api-client";
import type { ShadowSummaryResponse } from "../types";
import DivergenceMap from "./DivergenceMap";
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

export default function ShadowDiagnosticsPage(): JSX.Element {
  const [data, setData] = useState<ShadowSummaryResponse | null>(null);
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
    return () => ctrl.abort();
  }, []);

  const agreement = data ? nationalAgreement(data.regions) : null;
  const events = data?.truth_events ?? [];
  const officialCaught = events.filter(
    (e) => e.champion_score !== null && championWouldAlert(e.champion_score),
  ).length;

  return (
    <div className="explainer sci" aria-label="Diagnostica ML (shadow)">
      <article>
        <p className="exp-eyebrow">Riservato · ml-ops</p>
        <h2>Diagnostica del modello sperimentale (IA)</h2>
        <p className="shadow-note" role="note">
          Confronto tra il <strong>sistema ufficiale (V1)</strong>, che guida le
          allerte, e il <strong>modello IA in valutazione</strong>, che gira in
          ombra. <strong>Nessuna promozione avviene da qui</strong>: è una
          decisione manuale, presa fuori dall&apos;interfaccia.
        </p>

        {error ? (
          <p role="alert">{error}</p>
        ) : !data ? (
          <p className="shadow-muted">Caricamento…</p>
        ) : (
          <>
            <h3>Accordo complessivo</h3>
            <p className="shadow-headline">
              Su <strong>{data.total_pairs.toLocaleString("it-IT")}</strong>{" "}
              valutazioni osservate, l&apos;IA concorda col sistema ufficiale
              sulla classe di rischio nel{" "}
              <strong>{agreement !== null ? pct(agreement) : "—"}</strong> dei
              casi.
            </p>

            <h3>Eventi reali nella finestra</h3>
            {events.length === 0 ? (
              <p className="shadow-muted">
                Nessun evento di frana datato (catalogo ITALICA) nella finestra
                di osservazione. Il confronto sul <em>recall</em> — quante frane
                reali ciascun motore avrebbe segnalato — sarà possibile quando se
                ne accumuleranno. È l&apos;evidenza che conta di più per decidere
                la promozione.
              </p>
            ) : (
              <>
                <p>
                  Su <strong>{events.length}</strong> event
                  {events.length === 1 ? "o" : "i"} reale, il sistema ufficiale
                  ne aveva già <strong>{officialCaught}</strong> ad almeno
                  «Moderato» nelle 48 h precedenti. La probabilità dell&apos;IA è
                  mostrata a fianco, ancora <em>in valutazione</em> (senza una
                  soglia di allerta definita).
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
                        <td>{e.aoi_id}</td>
                        <td>{e.event_time.slice(0, 16).replace("T", " ")}</td>
                        <td>
                          {e.champion_score !== null
                            ? `${RISK_CLASSES[championClassIndex(e.champion_score)]!.label} (${e.champion_score.toFixed(2)})`
                            : "—"}
                        </td>
                        <td>
                          {e.ml_probability !== null
                            ? e.ml_probability.toFixed(2)
                            : "—"}
                        </td>
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
                        <td>{r.aoi_id}</td>
                        <td>{pct(r.class_agreement)}</td>
                        <td>{r.n.toLocaleString("it-IT")}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}

            <h3>Mappa della divergenza</h3>
            <p className="shadow-muted">
              Dove l&apos;IA vede <em>più</em> o <em>meno</em> rischio del sistema
              ufficiale. Colori neutri, non la scala del rischio: qui il colore
              significa «disaccordo tra modelli», non «pericolo».
            </p>
            <DivergenceMap />

            <p className="exp-note">
              Finestra dal {data.since.slice(0, 10)} · modello IA:{" "}
              {data.model_versions.join(", ") || "n/d"}. Grafico di calibrazione
              (reliability) in arrivo quando gli eventi reali bastano — vedi
              issue #26.
            </p>
          </>
        )}
      </article>
    </div>
  );
}
