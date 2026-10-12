// "Aggiornato alle" nell'header (#75).
//
// Prima diceva "agg. 1h" a prescindere: una promessa, non una misura. Su una
// dashboard pubblica di protezione civile un punteggio di rischio senza la sua
// ora è un numero di cui non si conosce la validità — e lo sweep nazionale
// dura più del tick orario (misurato: 156 s per una sola regione), quindi la
// promessa era anche falsa.
//
// Degrada al testo statico se `/api/status/jobs` non risponde: meglio la
// vecchia etichetta generica che un buco nell'header.

import { useEffect, useState } from "react";
import type { JSX } from "react";
import { useInterval } from "@mantine/hooks";

import { defaultApiClient } from "../lib/api-client";
import { testi, useLocale, useTesti } from "../lib/i18n";
import type { JobStatusResponse } from "../types";

const T = testi(
  {
    statico: "agg. 1h · 20 regioni",
    titolo: "Fine dell'ultimo sweep nazionale",
    fermo: "FERMO",
    aggiornato: (ora: string) => `aggiornato alle ${ora}`,
    regioni: (n: number) => ` · ${n} regioni`,
  },
  {
    statico: "upd. 1h · 20 regions",
    titolo: "End of the last national sweep",
    fermo: "STALE",
    aggiornato: (ora: string) => `updated at ${ora}`,
    regioni: (n: number) => ` · ${n} ${n === 1 ? "region" : "regions"}`,
  },
);

/** Ora locale in HH:MM, o null se il timestamp non è leggibile. */
export function formatSweepTime(
  iso: string | null | undefined,
  loc: string = "it-IT",
): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
}

export default function FreshnessBadge(): JSX.Element {
  const t = useTesti(T);
  const loc = useLocale();
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  // Un monitor lasciato aperto deve passare da LIVE a FERMO da solo: si
  // richiede lo stato ogni cinque minuti, e il confronto con l'ora si rifà
  // a ogni risposta.
  const [giro, setGiro] = useState(0);
  useInterval(() => setGiro((n) => n + 1), 5 * 60_000, { autoInvoke: true });

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getJobStatus(ctrl.signal)
      .then(setStatus)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [giro]);

  const when = formatSweepTime(status?.sweep?.finished_at, loc);
  const regions = status?.per_aoi.length ?? 0;
  if (!when) {
    return (
      <span className="header-meta">
        <span className="live-dot is-unknown" aria-hidden />
        {t.statico}
      </span>
    );
  }
  // «LIVE» solo se lo è: lo sweep gira ogni ora, e oltre due ore dalla fine
  // dell'ultimo il pallino verde direbbe una cosa falsa.
  const fine = new Date(status?.sweep?.finished_at ?? "").getTime();
  const fresco = Date.now() - fine < 2 * 3600_000;
  return (
    <span className="header-meta" title={t.titolo}>
      <span className={`live-dot ${fresco ? "" : "is-stale"}`} aria-hidden />
      <span className="live-label">{fresco ? "LIVE" : t.fermo}</span>
      <span>
        {t.aggiornato(when)}
        {regions > 0 ? t.regioni(regions) : ""}
      </span>
    </span>
  );
}
