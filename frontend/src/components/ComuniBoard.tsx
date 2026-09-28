import { useCallback, useEffect, useMemo, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { PanelFailure } from "../lib/panel-state";
import { describeFailure } from "../lib/panel-state";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { ComuneRisk, RiskLevel } from "../types";
import { PanelDegraded, PanelEmpty, PanelLoading } from "./PanelState";

// Il comune è l'unità di lettura, la cella è il dettaglio.
//
// A scala nazionale una cella da 1 km² non è leggibile: con un quarto del
// paese in classe Moderata la mappa diventa una coperta, e la colonna a
// fianco era un albero a tre livelli (regione → comune → celle) che chiedeva
// tre espansioni per arrivare a un nome di posto. Il comune invece è l'unità
// su cui si decide qualcosa: c'è un piano comunale, un ufficio tecnico, una
// persona che sa dove sono le case.
//
// I tre pericoli stanno sulla stessa riga, sempre tutti. Prima la classifica
// era fissata sulle frane e lo dichiarava con un badge: scegliendo
// «Alluvione» metà colonna continuava a parlare d'altro.

/** Ordine di lettura delle colonne, stabile a prescindere dai dati. */
const ORDINE = ["landslide", "flood", "wildfire"] as const;

const ABBREVIAZIONE: Record<string, string> = {
  None: "—",
  Low: "BAS",
  Moderate: "MOD",
  High: "ALTO",
  VeryHigh: "MOLTO ALTO",
};

function Indicatore({
  etichetta,
  classe,
  celle,
}: {
  etichetta: string;
  classe: RiskLevel;
  celle: number;
}): JSX.Element {
  const vuoto = classe === "None";
  return (
    <span className={`cb-haz ${vuoto ? "is-quiet" : ""}`}>
      <span
        className="cb-chip"
        style={{ background: RISK_COLOR_BY_LEVEL[classe] }}
        aria-hidden
      />
      <span className="cb-haz-label">{etichetta}</span>
      <span className="cb-haz-class">{ABBREVIAZIONE[classe] ?? classe}</span>
      <span className="sr-only">
        {etichetta}: {RISK_LABEL_IT_BY_LEVEL[classe]}
        {vuoto ? "" : `, ${celle} celle`}
      </span>
    </span>
  );
}

export function ComuniBoard(): JSX.Element {
  const [comuni, setComuni] = useState<ComuneRisk[] | null>(null);
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  const [cerca, setCerca] = useState("");
  const [tentativo, setTentativo] = useState(0);
  const { available } = useHazard();
  const riprova = useCallback(() => setTentativo((n) => n + 1), []);

  // La ricerca aspetta che chi scrive si fermi: una richiesta per tasto
  // premuto sono otto richieste per «Avezzano».
  const [termine, setTermine] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setTermine(cerca.trim()), 300);
    return () => clearTimeout(t);
  }, [cerca]);

  useEffect(() => {
    const ctrl = new AbortController();
    setComuni(null);
    setFailure(null);
    defaultApiClient
      .getTopComuni(undefined, 30, ctrl.signal, termine || undefined)
      .then((r) => setComuni(r.comuni))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        console.error("comuni", err);
        setFailure(describeFailure(err));
      });
    return () => ctrl.abort();
  }, [termine, tentativo]);

  // Le etichette vengono dal backend; l'ordine no, perché una colonna che si
  // sposta fra un aggiornamento e l'altro non si legge.
  const colonne = useMemo(
    () =>
      ORDINE.map((h) => ({
        hazard: h,
        label: available.find((a) => a.hazard === h)?.label_it ?? h,
      })),
    [available],
  );

  return (
    <section className="comuni-board" aria-label="Rischio per comune">
      <h2>Comuni · dal peggiore</h2>
      <input
        type="search"
        className="cb-search"
        placeholder="Cerca il tuo comune"
        aria-label="Cerca il tuo comune"
        value={cerca}
        onChange={(e) => setCerca(e.target.value)}
      />
      {failure ? (
        <PanelDegraded failure={failure} onRetry={riprova} />
      ) : comuni === null ? (
        <PanelLoading label="Carico i comuni" />
      ) : comuni.length === 0 ? (
        <PanelEmpty
          title={
            termine
              ? `Nessun comune trovato per «${termine}»`
              : "Nessun comune sopra la soglia"
          }
          detail={
            termine
              ? "Controlla il nome: la ricerca è sul nome ufficiale del comune."
              : "Nessun comune ha celle in classe Moderata o superiore, per nessuno dei pericoli sorvegliati."
          }
        />
      ) : (
        <ol className="cb-list">
          {comuni.map((c) => (
            <li key={c.istat_code}>
              <div className="cb-head">
                <span className="cb-name">{c.name}</span>
                <span className="cb-meta">
                  {c.n_cells.toLocaleString("it-IT")} celle
                  {c.n_alert > 0 ? ` · ${c.n_alert} in allerta` : ""}
                </span>
              </div>
              <div className="cb-hazards">
                {colonne.map((col) => {
                  const h = c.hazards[col.hazard];
                  return (
                    <Indicatore
                      key={col.hazard}
                      etichetta={col.label}
                      classe={h?.class ?? "None"}
                      celle={h?.n_cells ?? 0}
                    />
                  );
                })}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default ComuniBoard;
