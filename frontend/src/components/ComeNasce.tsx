// «Come nasce questo numero»: chi ha fatto cosa dietro una cella.
//
// La formula calcola, il meteo arriva da un modello, il machine learning
// oggi non tocca la mappa, l'AI racconta le regioni. La spiegazione dell'AI
// non sta qui: è per regione, e ripetuta nell'ispettore di ogni cella si
// leggeva come se parlasse di quel punto. Vive in «Regioni da monitorare».

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { testi, useTesti } from "../lib/i18n";
import type {
  HazardType,
  ProvenienzaResponse,
  RainModelsResponse,
} from "../types";

const T = testi(
  {
    rigaFormule: "Calcolata dalle ",
    formule: "formule",
    rigaMeteo: " sul meteo previsto.",
    ml: "Machine learning",
    mlAttivo: "un modello di confronto gira in parallelo, senza decidere",
    mlSpento: "non entra nel numero",
    rigaAi: ": racconta le regioni, non cambia i numeri.",
    comeFunziona: "Come funziona",
    modelliMeteo: "I modelli meteo · pioggia nelle prossime 72 h",
    discordi: (da: string, a: string) =>
      `I modelli meteo non concordano: da ${da} a ${a} mm. Più la forbice è larga, più il numero sulla mappa va letto con cautela.`,
    concordi: (da: string, a: string) => `I modelli meteo concordano: da ${da} a ${a} mm.`,
    riferimento: "Il numero sulla mappa usa la previsione di riferimento per questo punto.",
    titolo: "Come nasce questo numero",
    numero: "Il numero",
    numeroDd: "una formula scritta e verificabile, la stessa per ogni cella",
    meteo: "Il meteo",
    meteoDd: "previsto da Open-Meteo",
    meteoScelto: ", modello scelto per il punto",
    aiDd: "racconta la regione, non cambia i numeri:",
    aiLink: "la spiegazione è in «Regioni da monitorare»",
  },
  {
    rigaFormule: "Computed by the ",
    formule: "formulas",
    rigaMeteo: " on the forecast weather.",
    ml: "Machine learning",
    mlAttivo: "a comparison model runs in parallel, without deciding",
    mlSpento: "does not enter the number",
    rigaAi: ": summarises the regions, does not change the numbers.",
    comeFunziona: "How it works",
    modelliMeteo: "Weather models · rainfall over the next 72 h",
    discordi: (da: string, a: string) =>
      `The weather models disagree: from ${da} to ${a} mm. The wider the spread, the more cautiously the number on the map should be read.`,
    concordi: (da: string, a: string) => `The weather models agree: from ${da} to ${a} mm.`,
    riferimento: "The number on the map uses the reference forecast for this point.",
    titolo: "How this number is made",
    numero: "The number",
    numeroDd: "a written, verifiable formula, the same for every cell",
    meteo: "The weather",
    meteoDd: "forecast by Open-Meteo",
    meteoScelto: ", model chosen for the point",
    aiDd: "summarises the region, does not change the numbers:",
    aiLink: "the explanation is in «Regions to watch»",
  },
);

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
  const t = useTesti(T);
  const p = useProvenienza();
  if (!p) return null;
  return (
    <p className="riga-provenienza">
      {t.rigaFormule}
      <strong>{t.formule}</strong>
      {t.rigaMeteo} <strong>{t.ml}</strong>: {p.sfidante_ml_attivo ? t.mlAttivo : t.mlSpento}.{" "}
      <strong>AI</strong>
      {t.rigaAi} <a href="#/come-funziona/la-previsione">{t.comeFunziona}</a>
    </p>
  );
}

function Forbice({ dati }: { dati: RainModelsResponse }): JSX.Element | null {
  const t = useTesti(T);
  const modelli = dati.modelli;
  if (modelli.length < 2) return null;
  const max = Math.max(...modelli.map((m) => m.mm), 1);
  const primo = modelli[0];
  const ultimo = modelli[modelli.length - 1];
  if (!primo || !ultimo) return null;
  const rapporto = primo.mm > 0.5 ? ultimo.mm / primo.mm : null;
  return (
    <div className="cn-blocco">
      <span className="eyebrow">{t.modelliMeteo}</span>
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
          ? t.discordi(primo.mm.toFixed(0), ultimo.mm.toFixed(0))
          : t.concordi(primo.mm.toFixed(0), ultimo.mm.toFixed(0))}{" "}
        {t.riferimento}
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
  const t = useTesti(T);
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
    <section className="come-nasce" aria-label={t.titolo}>
      <span className="eyebrow">{t.titolo}</span>
      <dl className="cn-chi">
        <dt>{t.numero}</dt>
        <dd>{t.numeroDd}</dd>
        <dt>{t.meteo}</dt>
        <dd>
          {t.meteoDd}
          {provenienza && provenienza.meteo_modello !== "best_match"
            ? ` (${provenienza.meteo_modello})`
            : t.meteoScelto}
        </dd>
        <dt>{t.ml}</dt>
        <dd>{provenienza?.sfidante_ml_attivo ? t.mlAttivo : t.mlSpento}</dd>
        <dt>AI</dt>
        <dd>
          {t.aiDd} <a href={`#/regioni/${aoiId}`}>{t.aiLink}</a>
        </dd>
      </dl>
      {modelli ? <Forbice dati={modelli} /> : null}
    </section>
  );
}
