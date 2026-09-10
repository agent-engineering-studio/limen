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

import { defaultApiClient } from "../lib/api-client";
import type { JobStatusResponse } from "../types";

/** Ora locale in HH:MM, o null se il timestamp non è leggibile. */
export function formatSweepTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

export default function FreshnessBadge(): JSX.Element {
  const [status, setStatus] = useState<JobStatusResponse | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getJobStatus(ctrl.signal)
      .then(setStatus)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);

  const when = formatSweepTime(status?.sweep?.finished_at);
  const regions = status?.per_aoi.length ?? 0;
  if (!when) {
    return <span className="header-meta">agg. 1h · 20 regioni</span>;
  }
  return (
    <span className="header-meta" title="Fine dell'ultimo sweep nazionale">
      aggiornato alle {when}
      {regions > 0 ? ` · ${regions} regioni` : ""}
    </span>
  );
}
