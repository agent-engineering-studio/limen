// «Come nasce questo numero»: chi ha fatto cosa dietro una cella.
//
// La formula calcola, il meteo arriva da un modello, il machine learning
// oggi non tocca la mappa, l'AI racconta le regioni. La spiegazione dell'AI
// non sta qui: è per regione, e ripetuta nell'ispettore di ogni cella si
// leggeva come se parlasse di quel punto. Vive in «Regioni da monitorare».

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import type {
  HazardType,
  ProvenienzaResponse,
  RainModelsResponse,
} from "../types";

/** La provenienza, chiesta una volta per pagina: non cambia fra due clic. */
let provenienzaInVolo: Promise<ProvenienzaResponse> | null = null;
export function useProvenienza(): ProvenienzaResponse | null {
  const [p, setP] = useState<ProvenienzaResponse | null>(null);
  useEffect(() => {
    let vivo = true;
    provenienzaInVolo ??= defaultApiClient.getProvenienza().catch((e: unknown) => {
      provenienzaInVolo = null;
      throw e;
    });
    provenienzaInVolo.then((r) => vivo && setP(r)).catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, []);
  return p;
}

/** Una riga per il pannello della previsione: cosa c'è dietro i numeri futuri. */
export function RigaProvenienza(): JSX.Element | null {
  const p = useProvenienza();
  if (!p) return null;
  return (
    <p className="riga-provenienza">
      Calcolata dalle <strong>formule</strong> sul meteo previsto.{" "}
      <strong>Machine learning</strong>:{" "}
      {p.sfidante_ml_attivo ? "un modello di confronto gira in parallelo, senza decidere" : "non entra nel numero"}
      . <strong>AI</strong>: racconta le regioni, non cambia i numeri.{" "}
      <a href="#/come-funziona/la-previsione">Come funziona</a>
    </p>
  );
}

function Forbice({ dati }: { dati: RainModelsResponse }): JSX.Element | null {
  const modelli = dati.modelli;
  if (modelli.length < 2) return null;
  const max = Math.max(...modelli.map((m) => m.mm), 1);
  const primo = modelli[0];
  const ultimo = modelli[modelli.length - 1];
  if (!primo || !ultimo) return null;
  const rapporto = primo.mm > 0.5 ? ultimo.mm / primo.mm : null;
  return (
    <div className="cn-blocco">
      <span className="eyebrow">I modelli meteo · pioggia nelle prossime 72 h</span>
      <ul className="cn-forbice">
        {modelli.map((m) => (
          <li key={m.id}>
            <span className="cn-modello">{m.nome}</span>
            <span className="cn-barra" aria-hidden>
              <span style={{ width: `${(m.mm / max) * 100}%` }} />
            </span>
            <span className="mono">{m.mm.toFixed(0)} mm</span>
          </li>
        ))}
      </ul>
      <p className="cn-nota">
        {rapporto !== null && rapporto >= 2
          ? `I modelli meteo non concordano: da ${primo.mm.toFixed(0)} a ${ultimo.mm.toFixed(0)} mm. Più la forbice è larga, più il numero sulla mappa va letto con cautela.`
          : `I modelli meteo concordano: da ${primo.mm.toFixed(0)} a ${ultimo.mm.toFixed(0)} mm.`}{" "}
        Il numero sulla mappa usa la previsione di riferimento per questo punto.
      </p>
    </div>
  );
}

/** Il blocco in fondo all'ispettore della cella. */
export default function ComeNasce({
  cellId,
  hazard,
}: {
  cellId: string;
  hazard: HazardType;
}): JSX.Element {
  const provenienza = useProvenienza();
  const aoiId = cellId.split("|")[0] ?? "";
  const [modelli, setModelli] = useState<RainModelsResponse | null>(null);
  const conPioggia = hazard !== "wildfire";

  useEffect(() => {
    setModelli(null);
    if (!conPioggia) return;
    const ctrl = new AbortController();
    defaultApiClient
      .getCellRainModels(cellId, ctrl.signal)
      .then(setModelli)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [cellId, conPioggia]);


  return (
    <section className="come-nasce" aria-label="Come nasce questo numero">
      <span className="eyebrow">Come nasce questo numero</span>
      <dl className="cn-chi">
        <dt>Il numero</dt>
        <dd>una formula scritta e verificabile, la stessa per ogni cella</dd>
        <dt>Il meteo</dt>
        <dd>
          previsto da Open-Meteo
          {provenienza && provenienza.meteo_modello !== "best_match"
            ? ` (${provenienza.meteo_modello})`
            : ", modello scelto per il punto"}
        </dd>
        <dt>Machine learning</dt>
        <dd>
          {provenienza?.sfidante_ml_attivo
            ? "un modello di confronto gira in parallelo, senza decidere"
            : "non entra nel numero"}
        </dd>
        <dt>AI</dt>
        <dd>
          racconta la regione, non cambia i numeri:{" "}
          <a href={`#/regioni/${aoiId}`}>la spiegazione è in «Regioni da monitorare»</a>
        </dd>
      </dl>
      {modelli ? <Forbice dati={modelli} /> : null}
    </section>
  );
}
