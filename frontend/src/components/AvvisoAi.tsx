// L'avviso discreto nell'header quando il tetto mensile di spesa ha messo in
// pausa l'AI. Silenzioso di proposito: niente importi (la spesa non è
// pubblica), niente colore d'allarme — mappa, punteggi e allerte non
// dipendono dall'LLM, e cambiano solo le spiegazioni, che tornano al testo
// deterministico. Se lo stato non arriva non mostra niente.

import { useEffect, useState } from "react";
import type { JSX } from "react";
import { useInterval } from "@mantine/hooks";

import { defaultApiClient } from "../lib/api-client";
import { testi, useLocale, useTesti } from "../lib/i18n";
import type { LlmStatusResponse } from "../types";

const T = testi(
  {
    etichetta: "AI in pausa",
    titolo: (quando: string) =>
      `Le spiegazioni scritte dall'AI tornano il ${quando}: è stato raggiunto il limite mensile. ` +
      "Mappa, punteggi e allerte non cambiano.",
  },
  {
    etichetta: "AI paused",
    titolo: (quando: string) =>
      `AI-written explanations resume on ${quando}: the monthly limit has been reached. ` +
      "Map, scores and alerts are unaffected.",
  },
);

export default function AvvisoAi(): JSX.Element | null {
  const t = useTesti(T);
  const loc = useLocale();
  const [stato, setStato] = useState<LlmStatusResponse | null>(null);
  const [giro, setGiro] = useState(0);
  useInterval(() => setGiro((n) => n + 1), 10 * 60_000, { autoInvoke: true });

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getLlmStatus(ctrl.signal)
      .then(setStato)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [giro]);

  if (!stato?.in_pausa) return null;
  const quando = stato.ripresa
    ? new Date(`${stato.ripresa}T00:00:00Z`).toLocaleDateString(loc, {
        day: "numeric",
        month: "long",
        timeZone: "UTC",
      })
    : "1";
  return (
    <span className="header-meta avviso-ai" title={t.titolo(quando)}>
      {t.etichetta}
    </span>
  );
}
