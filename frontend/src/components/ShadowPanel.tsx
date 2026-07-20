// Pannello "Modello sperimentale (IA)" — diagnostica shadow champion vs
// challenger (issue #4/#26). Vive nella dashboard autenticata.
//
// Vincolo di chiarezza (operatori NON informatici): il pannello NON è un
// cruscotto da data analyst. Mostra UNA frase in linguaggio piano + un
// indicatore d'accordo; le metriche tecniche (divergenza, correlazione)
// restano nel report CLI, non qui. Etichetta esplicita: non-autoritativo.

import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import type { ShadowRegion, ShadowSummaryResponse } from "../types";

/** Accordo nazionale sulle classi, pesato per numero di celle. null se vuoto. */
export function nationalAgreement(regions: ShadowRegion[]): number | null {
  const n = regions.reduce((acc, r) => acc + r.n, 0);
  if (n === 0) return null;
  const agree = regions.reduce((acc, r) => acc + r.class_agreement * r.n, 0);
  return agree / n;
}

const pct = (x: number): string => `${Math.round(x * 100)}%`;

export default function ShadowPanel(): JSX.Element | null {
  const [data, setData] = useState<ShadowSummaryResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getShadowSummary(ctrl.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setFailed(true);
      });
    return () => ctrl.abort();
  }, []);

  // La diagnostica ML è opzionale: se l'endpoint non c'è o fallisce, il
  // pannello sparisce invece di mostrare un errore all'operatore.
  if (failed) return null;

  const agreement = data ? nationalAgreement(data.regions) : null;

  return (
    <section className="shadow-panel" aria-label="Modello sperimentale (IA)">
      <div className="shadow-head">
        <h2>Modello sperimentale (IA)</h2>
        <span className="shadow-pill">in prova</span>
      </div>
      <p className="shadow-note" role="note">
        Accanto al sistema ufficiale proviamo <strong>in sottofondo</strong> un
        secondo modello basato su intelligenza artificiale, per capire se un
        giorno potrà fare meglio. È un <strong>esperimento</strong>:{" "}
        <strong>non decide le allerte</strong> e non è ancora usato.
      </p>

      {!data ? (
        <p className="shadow-muted">Caricamento…</p>
      ) : data.total_pairs === 0 ? (
        <p className="shadow-muted">
          Nessun dato ancora nella finestra di osservazione.
        </p>
      ) : (
        <>
          <p className="shadow-headline">
            Su <strong>{data.total_pairs.toLocaleString("it-IT")}</strong>{" "}
            valutazioni, l&apos;IA ha dato la <strong>stessa classe di rischio</strong>{" "}
            del sistema ufficiale nel{" "}
            <strong>{agreement !== null ? pct(agreement) : "—"}</strong> dei casi.
          </p>
          {agreement !== null ? (
            <div
              className="shadow-bar"
              role="img"
              aria-label={`Coincidenza col sistema ufficiale ${pct(agreement)}`}
            >
              <span className="shadow-bar-fill" style={{ width: pct(agreement) }} />
            </div>
          ) : null}
          <p className="shadow-muted">
            Questa percentuale è quanto spesso i due modelli assegnano la stessa
            classe (Nessuno / Basso / Moderato / Alto / Molto alto) alla stessa
            zona. Un valore basso è <strong>normale</strong> per un modello ancora
            in prova — non è un errore del sistema ufficiale.
          </p>
          {data.regions.length > 0 ? (
            <details className="shadow-details">
              <summary>Dettaglio per regione</summary>
              <ul>
                {[...data.regions]
                  .sort((a, b) => b.n - a.n)
                  .map((r) => (
                    <li key={r.aoi_id}>
                      <span>{r.aoi_name}</span>
                      <span className="shadow-region-val">
                        {pct(r.class_agreement)} · {r.n.toLocaleString("it-IT")} celle
                      </span>
                    </li>
                  ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </section>
  );
}
