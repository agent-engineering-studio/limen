// «Come nasce questo numero»: chi ha fatto cosa dietro una cella.
//
// La formula calcola, il meteo arriva da un modello, il machine learning
// oggi non tocca la mappa, l'AI scrive la spiegazione della regione. Prima
// nessuna di queste cose si vedeva, e chi guardava la mappa non poteva
// sapere quanto di quel numero fosse «intelligenza artificiale» — la
// risposta onesta è: niente del numero, tutto il racconto.

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import type {
  HazardType,
  ProvenienzaResponse,
  RainModelsResponse,
  SpiegazioneResponse,
} from "../types";

/** Il nome di un modello del gateway per chi legge la mappa. */
export function modelloLeggibile(alias: string): string {
  switch (alias) {
    case "quality-cloud":
      return "Claude (Anthropic)";
    case "quality-local":
    case "glm52":
      return "GLM-5.2, sul nostro server";
    case "fast":
    case "chat":
    case "extract":
      return "Qwen3, sul nostro server";
    default:
      return alias;
  }
}

const CAUSA: Record<string, string> = {
  static_susceptibility: "la fragilità del terreno",
  meteo_trigger: "la pioggia",
  seismic_event: "le scosse recenti",
  post_fire_destabilization: "gli incendi recenti",
  human_activity: "l'attività umana",
  pluvial_rain: "la pioggia prevista",
  river_discharge: "la portata dei fiumi",
  hydraulic_susceptibility: "quanto la zona è allagabile",
  fire_weather: "il tempo secco e ventoso",
  fuel_load: "la vegetazione che brucia",
  terrain_slope: "la pendenza",
};

function nomeRegione(aoiId: string): string {
  return aoiId
    .replace(/^it-/, "")
    .split("-")
    .map((p) => (p.length > 2 ? p.charAt(0).toUpperCase() + p.slice(1) : p))
    .join(" ");
}

function oraBreve(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

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
  const c = p.correttore_pioggia;
  return (
    <p className="riga-provenienza">
      Calcolata dalla <strong>formula</strong> sul meteo previsto da un solo modello.{" "}
      <strong>Machine learning</strong>:{" "}
      {p.sfidante_ml_attivo ? "uno sfidante gira in ombra, senza decidere" : "non ancora attivo"}
      {c.stato === "raccolta_dati"
        ? ` — il correttore della pioggia sta raccogliendo i dati (${c.nodi_raccolti} punti su ${c.nodi_obiettivo})`
        : ""}
      . <strong>AI</strong>: scrive le spiegazioni, non i numeri.{" "}
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
          ? `I modelli non sono d'accordo: da ${primo.mm.toFixed(0)} a ${ultimo.mm.toFixed(0)} mm. `
          : `I modelli sono abbastanza d'accordo: da ${primo.mm.toFixed(0)} a ${ultimo.mm.toFixed(0)} mm. `}
        Il punteggio oggi ne legge uno solo; pesarli tutti è il lavoro del
        correttore della pioggia, ancora in addestramento. AIFS è il modello di
        ECMWF fatto con una rete neurale.
      </p>
    </div>
  );
}

function SpiegazioneAI({
  dati,
  aoiId,
}: {
  dati: SpiegazioneResponse;
  aoiId: string;
}): JSX.Element {
  const s = dati.spiegazione;
  if (!s) {
    return (
      <div className="cn-blocco">
        <span className="eyebrow">Spiegazione dell&apos;AI · {nomeRegione(aoiId)}</span>
        <p className="cn-nota">
          Non ancora scritta per questo pericolo: l&apos;AI racconta una regione
          quando la sua classe peggiore cambia, e al più ogni 12 ore.
        </p>
      </div>
    );
  }
  const a = s.analisi;
  return (
    <details className="cn-blocco cn-ai">
      <summary>
        <span className="eyebrow">Spiegazione dell&apos;AI · {nomeRegione(aoiId)}</span>
        <span className="cn-firma">
          scritta da {modelloLeggibile(s.modello)} · {oraBreve(s.scritta)}
        </span>
      </summary>
      {a ? (
        <p className="cn-analisi">
          Causa principale secondo l&apos;AI: <strong>{CAUSA[a.driver] ?? a.driver}</strong>
          {" · "}finestra di attenzione {a.attention_window_hours} h{" · "}
          confidenza {Math.round(a.confidence * 100)}%
        </p>
      ) : null}
      {s.testo.split(/\n{2,}/).map((par) => (
        <p key={par.slice(0, 40)}>{par}</p>
      ))}
      <p className="cn-nota">
        L&apos;AI legge i numeri già calcolati e li racconta: non può cambiarne
        nessuno, e gli avvisi non contengono testo suo.
      </p>
    </details>
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
  const [spiegazione, setSpiegazione] = useState<SpiegazioneResponse | null>(null);
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

  useEffect(() => {
    setSpiegazione(null);
    if (!aoiId) return;
    const ctrl = new AbortController();
    defaultApiClient
      .getAoiSpiegazione(aoiId, hazard, ctrl.signal)
      .then(setSpiegazione)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [aoiId, hazard]);

  const c = provenienza?.correttore_pioggia;
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
            ? "uno sfidante gira in ombra e non decide"
            : "non ancora nel numero"}
          {c && c.stato === "raccolta_dati"
            ? ` · correttore della pioggia in raccolta dati (${c.nodi_raccolti}/${c.nodi_obiettivo} punti)`
            : ""}
        </dd>
        <dt>AI</dt>
        <dd>
          {spiegazione?.spiegazione
            ? `ha scritto la spiegazione qui sotto (${modelloLeggibile(spiegazione.spiegazione.modello)})`
            : "scrive le spiegazioni, mai i numeri"}
        </dd>
      </dl>
      {modelli ? <Forbice dati={modelli} /> : null}
      {spiegazione ? <SpiegazioneAI dati={spiegazione} aoiId={aoiId} /> : null}
    </section>
  );
}
