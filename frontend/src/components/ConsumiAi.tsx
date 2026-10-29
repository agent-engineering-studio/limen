// Quanti token hanno consumato questo mese le spiegazioni dell'AI, per
// modello. Pubblico come il resto della diagnostica, ma solo token e
// richieste: la spesa in dollari resta a `limen llm-spesa`.

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { testi, useLocale, useTesti } from "../lib/i18n";
import type { LlmStatusResponse } from "../types";

const T = testi(
  {
    titolo: "L'AI che scrive le spiegazioni, questo mese",
    intro:
      "Ogni chiamata a un modello linguistico, locale o in cloud, lascia i suoi token: quelli che legge " +
      "(i dati della valutazione) e quelli che scrive (la spiegazione). C'è un tetto mensile di spesa: " +
      "quando è raggiunto le chiamate al cloud si fermano fino al mese dopo, e le spiegazioni tornano al " +
      "testo deterministico.",
    caricamento: "Carico i consumi…",
    nessuno: "Nessuna chiamata questo mese.",
    totale: (r: string, i: string, o: string) => `${r} richieste · ${i} token letti · ${o} token scritti`,
    modello: "Modello",
    richieste: "Richieste",
    letti: "Token letti",
    scritti: "Token scritti",
    pausa: "In pausa: il tetto mensile è raggiunto.",
  },
  {
    titolo: "The AI writing the explanations, this month",
    intro:
      "Every call to a language model, local or cloud, leaves its tokens: those it reads (the assessment " +
      "data) and those it writes (the explanation). There is a monthly spending cap: once reached, cloud " +
      "calls stop until next month and explanations fall back to deterministic text.",
    caricamento: "Loading usage…",
    nessuno: "No calls this month.",
    totale: (r: string, i: string, o: string) => `${r} requests · ${i} tokens read · ${o} tokens written`,
    modello: "Model",
    richieste: "Requests",
    letti: "Tokens read",
    scritti: "Tokens written",
    pausa: "Paused: the monthly cap has been reached.",
  },
);

export default function ConsumiAi(): JSX.Element {
  const t = useTesti(T);
  const loc = useLocale();
  const [stato, setStato] = useState<LlmStatusResponse | null>(null);
  const [errore, setErrore] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getLlmStatus(ctrl.signal)
      .then(setStato)
      .catch(() => setErrore(true));
    return () => ctrl.abort();
  }, []);

  const n = (v: number): string => v.toLocaleString(loc);
  return (
    <section aria-label={t.titolo}>
      <h3>{t.titolo}</h3>
      <p>{t.intro}</p>
      {errore ? null : !stato ? (
        <p className="shadow-muted">{t.caricamento}</p>
      ) : stato.richieste === 0 ? (
        <p className="shadow-muted">{t.nessuno}</p>
      ) : (
        <>
          <p className="shadow-headline">
            {t.totale(n(stato.richieste), n(stato.input_tokens), n(stato.output_tokens))}
          </p>
          {stato.in_pausa ? <p className="shadow-muted">{t.pausa}</p> : null}
          <table className="shadow-table">
            <thead>
              <tr>
                <th>{t.modello}</th>
                <th>{t.richieste}</th>
                <th>{t.letti}</th>
                <th>{t.scritti}</th>
              </tr>
            </thead>
            <tbody>
              {stato.per_modello.map((m) => (
                <tr key={m.chiave}>
                  <td>{m.chiave}</td>
                  <td>{n(m.richieste)}</td>
                  <td>{n(m.input_tokens)}</td>
                  <td>{n(m.output_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
