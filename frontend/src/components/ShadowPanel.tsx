// Pannello "Modello sperimentale (IA)" — diagnostica shadow champion vs
// challenger (issue #4/#26). Vive nella dashboard autenticata.
//
// Vincolo di chiarezza (operatori NON informatici): il pannello NON è un
// cruscotto da data analyst. Mostra UNA frase in linguaggio piano + un
// indicatore d'accordo; le metriche tecniche (divergenza, correlazione)
// restano nel report CLI, non qui. Etichetta esplicita: non-autoritativo.

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { testi, useLocale, useTesti } from "../lib/i18n";
import { useEtichetteRischio } from "../lib/risk-colors";
import { RISK_LEVELS } from "../types";
import type { ShadowRegion, ShadowSummaryResponse } from "../types";

/** Accordo nazionale sulle classi, pesato per numero di celle. null se vuoto. */
export function nationalAgreement(regions: ShadowRegion[]): number | null {
  const n = regions.reduce((acc, r) => acc + r.n, 0);
  if (n === 0) return null;
  const agree = regions.reduce((acc, r) => acc + r.class_agreement * r.n, 0);
  return agree / n;
}

const pct = (x: number): string => `${Math.round(x * 100)}%`;

const T = testi(
  {
    titolo: "Modello sperimentale (IA)",
    inProva: "in prova",
    nota: (
      <>
        Accanto al sistema ufficiale proviamo <strong>in sottofondo</strong> un secondo modello
        basato su intelligenza artificiale, per capire se un giorno potrà fare meglio. È un{" "}
        <strong>esperimento</strong>: <strong>non decide le allerte</strong> e non è ancora usato.
      </>
    ),
    caricamento: "Caricamento…",
    vuoto: "Nessun dato ancora nella finestra di osservazione.",
    sintesi: (n: string, accordo: string) => (
      <>
        Su <strong>{n}</strong> valutazioni, l&apos;IA ha dato la{" "}
        <strong>stessa classe di rischio</strong> del sistema ufficiale nel{" "}
        <strong>{accordo}</strong> dei casi.
      </>
    ),
    barra: (accordo: string) => `Coincidenza col sistema ufficiale ${accordo}`,
    spiegazione: (classi: string) => (
      <>
        Questa percentuale è quanto spesso i due modelli assegnano la stessa classe ({classi})
        alla stessa zona. Un valore basso è <strong>normale</strong> per un modello ancora in
        prova — non è un errore del sistema ufficiale.
      </>
    ),
    perRegione: "Dettaglio per regione",
    celle: (n: string) => `${n} celle`,
  },
  {
    titolo: "Experimental model (AI)",
    inProva: "on trial",
    nota: (
      <>
        Alongside the official system we are testing, <strong>in the background</strong>, a second
        model based on artificial intelligence, to find out whether it could one day do better.
        It is an <strong>experiment</strong>: <strong>it does not decide warnings</strong> and is
        not used yet.
      </>
    ),
    caricamento: "Loading…",
    vuoto: "No data yet in the observation window.",
    sintesi: (n: string, accordo: string) => (
      <>
        Out of <strong>{n}</strong> assessments, the AI gave the{" "}
        <strong>same risk class</strong> as the official system in <strong>{accordo}</strong> of
        cases.
      </>
    ),
    barra: (accordo: string) => `Agreement with the official system ${accordo}`,
    spiegazione: (classi: string) => (
      <>
        This percentage is how often the two models assign the same class ({classi}) to the same
        area. A low value is <strong>normal</strong> for a model still on trial — it is not an
        error of the official system.
      </>
    ),
    perRegione: "Breakdown by region",
    celle: (n: string) => `${n} cells`,
  },
);

export default function ShadowPanel(): JSX.Element | null {
  const t = useTesti(T);
  const loc = useLocale();
  const etichette = useEtichetteRischio();
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
    <section className="shadow-panel" aria-label={t.titolo}>
      <div className="shadow-head">
        <h2>{t.titolo}</h2>
        <span className="shadow-pill">{t.inProva}</span>
      </div>
      <p className="shadow-note" role="note">
        {t.nota}
      </p>

      {!data ? (
        <p className="shadow-muted">{t.caricamento}</p>
      ) : data.total_pairs === 0 ? (
        <p className="shadow-muted">{t.vuoto}</p>
      ) : (
        <>
          <p className="shadow-headline">
            {t.sintesi(
              data.total_pairs.toLocaleString(loc),
              agreement !== null ? pct(agreement) : "—",
            )}
          </p>
          {agreement !== null ? (
            <div
              className="shadow-bar"
              role="img"
              aria-label={t.barra(pct(agreement))}
            >
              <span className="shadow-bar-fill" style={{ width: pct(agreement) }} />
            </div>
          ) : null}
          <p className="shadow-muted">
            {t.spiegazione(RISK_LEVELS.map((l) => etichette[l]).join(" / "))}
          </p>
          {data.regions.length > 0 ? (
            <details className="shadow-details">
              <summary>{t.perRegione}</summary>
              <ul>
                {[...data.regions]
                  .sort((a, b) => b.n - a.n)
                  .map((r) => (
                    <li key={r.aoi_id}>
                      <span>{r.aoi_name}</span>
                      <span className="shadow-region-val">
                        {pct(r.class_agreement)} · {t.celle(r.n.toLocaleString(loc))}
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
