import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient, ApiClientError } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import ComeNasce from "./ComeNasce";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL, RISK_SCURE } from "../lib/risk-colors";
import type {
  CellBreakdownResponse,
  CellMultiHazardResponse,
  CellRainOutlookResponse,
  FwiNormale,
  HazardType,
  RiskLevel,
} from "../types";

export interface CellPopupProps {
  readonly cellId: string | null;
  /** Cell centroid — enables the 48h forecast strip (Open-Meteo). */
  readonly lon?: number | null;
  readonly lat?: number | null;
  /** Dalla lista: priorità operativa, tag esposizione, comune. */
  readonly priority?: number | null;
  readonly exposure?: string | null;
  readonly place?: string | null;
  readonly onDismiss?: () => void;
}

const NOME_SCHEDA: Record<HazardType, string> = {
  landslide: "Frana",
  flood: "Alluvione",
  wildfire: "Incendio",
};

const EXPOSURE_PHRASE: Record<string, string> = {
  abitato: "un centro abitato",
  "vicino abitato": "case nelle vicinanze",
  infrastrutture: "strade o ferrovie principali",
  "infrastrutture vicine": "strade o ferrovie nelle vicinanze",
};

/** I tag con distanza OSM ("statale a 250 m") arrivano già in italiano
 * dal backend: qui serve solo l'articolo per la frase discorsiva. */
function phraseFor(tag: string): string {
  if (EXPOSURE_PHRASE[tag]) return EXPOSURE_PHRASE[tag];
  if (tag.startsWith("autostrada")) return `un'${tag}`;
  if (tag.startsWith("statale") || tag.startsWith("ferrovia")) return `una ${tag}`;
  return tag;
}

function exposureText(exposure?: string | null): string | null {
  if (!exposure) return null;
  const parts = exposure
    .split(", ")
    .map(phraseFor)
    .filter(Boolean);
  if (parts.length === 0) return null;
  return parts.length === 1
    ? parts[0]!
    : `${parts.slice(0, -1).join(", ")} e ${parts[parts.length - 1]}`;
}

/** Verdetto operativo — deterministico da livello + esposizione:
 * risponde a "devo preoccuparmi? devo monitorare questa cella?". */
function verdict(
  level: RiskLevel,
  exposure?: string | null,
): { text: string; tone: "ok" | "watch" | "warn" } {
  const exposed = Boolean(exposure);
  if (level === "VeryHigh" || level === "High") {
    return {
      text: exposed
        ? "Da attenzionare subito: rischio alto vicino a case o strade."
        : "Da attenzionare: rischio alto, versante isolato.",
      tone: "warn",
    };
  }
  if (level === "Moderate") {
    return exposed
      ? {
          text:
            "Da tenere sotto osservazione: rischio moderato, ma la zona è " +
            "abitata o attraversata da infrastrutture.",
          tone: "watch",
        }
      : {
          text:
            "Controlli di routine: rischio moderato su versante isolato, " +
            "nessuna azione immediata.",
          tone: "ok",
        };
  }
  return {
    text: exposed
      ? "Nessuna preoccupazione immediata: il rischio è basso — la cella è " +
        "in lista solo perché vicina ad abitazioni o strade."
      : "Nessuna preoccupazione: rischio basso.",
    tone: "ok",
  };
}

const DRIVER_PROSE: Record<string, string> = {
  s: "dalla natura del versante: geologia, pendenza e frane del passato",
  m: "dalla spinta della pioggia recente",
  e: "dalle scosse sismiche recenti",
  f: "dall'effetto di incendi recenti",
  h: "dalla pericolosità idraulica della zona",
  fwi_norm: "dalle condizioni meteo: caldo, secco e vento",
  fuel: "da quanto è infiammabile la vegetazione qui",
  slope: "dalla pendenza, che fa correre il fuoco verso l'alto",
  susceptibility: "da dove si trova: è una zona che l'acqua raggiunge",
  pluvial: "dalla pioggia prevista, più di quanta il terreno ne assorba",
  fluvial: "dalla portata prevista del fiume, sopra la sua normale",
};

/** Le classi FWI di Copernicus EFFIS, le stesse della sua legenda. */
const CLASSI_EFFIS: readonly [number, string][] = [
  [11.2, "Low (sotto 11,2)"],
  [21.3, "Moderate (11,2–21,3)"],
  [38.0, "High (21,3–38)"],
  [50.0, "Very High (38–50)"],
  [70.0, "Extreme (50–70)"],
  [Infinity, "Very Extreme (oltre 70)"],
];

function cifra(n: number, decimali = 1): string {
  return n.toLocaleString("it-IT", { minimumFractionDigits: decimali, maximumFractionDigits: decimali });
}

/** Come leggere il numero dell'incendio: cosa misura, a quale classe EFFIS
 *  corrisponde e quanto è secco il suolo sotto.
 *
 *  Senza questo, uno 0,69 «Alto» in un ottobre mite si leggeva come un
 *  allarme. È un pericolo **potenziale** — quanto si propagherebbe un fuoco
 *  se partisse — e lo dice anche la scala ufficiale: a Montegiordano il 2
 *  ottobre EFFIS dava la stessa classe. Il numero era giusto; mancava cosa
 *  vuol dire. `null` quando il breakdown non porta il meteo. */
export function letturaIncendio(
  factors: Record<string, unknown>,
  normale: FwiNormale | null = null,
): string[] | null {
  const fw = factors["fire_weather"];
  if (typeof fw !== "object" || fw === null) return null;
  const meteo = fw as Record<string, unknown>;
  const fwi = typeof meteo["fwi"] === "number" ? meteo["fwi"] : null;
  const dc = typeof meteo["dc"] === "number" ? meteo["dc"] : null;
  if (fwi === null) return null;
  const righe = [
    "È il pericolo meteorologico potenziale: quanto si propagherebbe un " +
      "incendio se partisse, non la probabilità che parta.",
  ];
  const classe = CLASSI_EFFIS.find(([max]) => fwi < max)?.[1] ?? "";
  const giorno =
    typeof meteo["day"] === "string"
      ? ` · meteo del ${new Date(meteo["day"]).toLocaleDateString("it-IT", { day: "numeric", month: "long" })}`
      : "";
  righe.push(
    `Indice meteo FWI ${cifra(fwi)}: classe ${classe} sulla scala di Copernicus EFFIS${giorno}.`,
  );
  if (normale !== null && typeof meteo["day"] === "string") {
    // Rispetto al solito: la classe è assoluta, uguale ad agosto e a
    // ottobre; questa riga dice dove cade il valore fra i giorni dello
    // stesso mese, nello stesso punto, negli anni dell'archivio.
    const mese = new Date(meteo["day"]).toLocaleDateString("it-IT", { month: "long" });
    const p = normale.percentile;
    const giudizio =
      p >= 90 ? "Molto sopra il solito" : p >= 75 ? "Sopra il solito" : p > 25 ? "Nella norma" : "Sotto il solito";
    righe.push(
      `${giudizio} per ${mese}: più alto del ${cifra(p, 0)} % dei giorni di ${mese} ` +
        `${normale.anni[0]}–${normale.anni[1]} in questo punto, dove la mediana è FWI ${cifra(normale.mediana)}.`,
    );
  }
  if (dc !== null) {
    // Il DC scende solo con piogge vere (sopra 2,8 mm in un giorno): è la
    // memoria lunga della siccità, ed è lui che tiene alto l'indice dopo
    // un'estate secca anche quando le giornate si fanno miti.
    const lettura =
      dc >= 500
        ? "suolo e combustibili grossi molto secchi, come a fine estate: si abbassa solo con piogge abbondanti"
        : dc >= 350
          ? "siccità marcata, che una pioggia leggera non cancella"
          : dc >= 200
            ? "siccità moderata"
            : "nessuna siccità di fondo";
    righe.push(`Codice di siccità DC ${cifra(dc, 0)}: ${lettura}.`);
  }
  return righe;
}

/** Spiegazione della cella in linguaggio piano — deterministica, dal
 * breakdown: niente LLM, niente numeri inventati. */
function plainSummary(
  hazard: HazardType,
  components: Component[],
  factors: Record<string, unknown>,
  exposure?: string | null,
): string {
  const parts: string[] = [];
  const top = [...components].sort((x, y) => y.value - x.value)[0];
  if (top && top.value > 0.05 && DRIVER_PROSE[top.key]) {
    parts.push(`Il punteggio nasce soprattutto ${DRIVER_PROSE[top.key]}.`);
  }

  if (hazard === "flood") {
    const pluvial = pickScalar(factors, "pluvial");
    const fluvial = pickScalar(factors, "fluvial");
    const pioggia = factors["rain_mm"];
    parts.push(
      "Questo numero guarda avanti: è calcolato sulla pioggia prevista nelle " +
        "prossime 72 ore" +
        (typeof pioggia === "number" ? ` (${Math.round(pioggia)} mm)` : "") +
        ", non su quella che cade adesso.",
    );
    if (pluvial === 0 && fluvial === 0) {
      parts.push(
        "Nessun segnale in corso: il punteggio riflette solo dove si trova " +
          "la cella, non un pericolo in atto.",
      );
    } else if (fluvial > pluvial) {
      parts.push("Il segnale viene dal fiume, non dalla pioggia che cade qui.");
    } else {
      parts.push("Il segnale viene dalla pioggia locale, non da un fiume in piena.");
    }
    if (factors["mapped"] === false) {
      // Il mosaico ISPRA copre i bacini ufficialmente studiati: dirlo è più
      // onesto che presentare un valore di ripiego come una perimetrazione.
      parts.push(
        "Questa cella è fuori dalle zone idrauliche mappate: il valore di " +
          "base è prudenziale, non una perimetrazione ufficiale.",
      );
    }
  } else if (hazard === "wildfire") {
    const fwi = pickScalar(factors, "fwi_norm");
    if (fwi < 0.05) {
      parts.push(
        "Le condizioni meteo non favoriscono il fuoco: combustibile umido " +
          "o aria fresca.",
      );
    } else if (fwi < 0.42) {
      parts.push("Il tempo è secco ma non estremo.");
    } else {
      parts.push("Caldo, siccità e vento stanno spingendo il pericolo in alto.");
    }
    if (factors["spinup"] === true) {
      // I tre codici di umidità sono ricorsivi: dirlo è più onesto che
      // presentare un indice appena avviato come uno consolidato.
      parts.push(
        "L'indice è in avviamento: si basa su pochi giorni di storia meteo " +
          "e va letto con prudenza.",
      );
    }
  } else {
    const m = pickScalar(factors, "m");
    if (m < 0.05) {
      parts.push(
        "Non c'è pioggia in corso: il punteggio riflette la fragilità " +
          "storica del versante, non un pericolo in atto.",
      );
    } else if (m < 0.2) {
      parts.push("La pioggia recente incide poco.");
    } else if (m < 0.5) {
      parts.push("La pioggia recente contribuisce in modo moderato.");
    } else {
      parts.push("La pioggia recente sta spingendo il rischio verso l'alto.");
    }
  }

  const exp = exposureText(exposure);
  if (exp) {
    parts.push(`Nelle vicinanze: ${exp}.`);
  }
  return parts.join(" ");
}

interface Component {
  key: string;
  label: string;
  color: string;
  value: number;
}

function pickScalar(factors: Record<string, unknown>, key: string): number {
  const value = factors[key];
  return typeof value === "number" ? value : 0;
}

// I componenti hanno nomi diversi per pericolo perché descrivono cose
// diverse: S/M/E/F/H dicono come cede un versante e non significano nulla per
// un incendio. Prima il popup leggeva solo i primi, quindi una cella
// d'incendio mostrava cinque barre a 0.000 accanto a un punteggio non nullo.
const COMPONENTS_BY_HAZARD: Record<
  string,
  readonly { key: string; label: string; color: string }[]
> = {
  landslide: [
    { key: "s", label: "S statico", color: "#7fa7e8" },
    { key: "m", label: "M meteo", color: "#ff8a1f" },
    { key: "e", label: "E sismico", color: "#c6a8ff" },
    { key: "f", label: "F post-incendio", color: "#ffa552" },
    { key: "h", label: "H idrologico", color: "#6fd3ee" },
  ],
  wildfire: [
    { key: "fwi_norm", label: "FWI (tempo)", color: "#ff9ad5" },
    { key: "fuel", label: "Combustibile", color: "#6fcf97" },
    { key: "slope", label: "Pendenza", color: "#c6a8ff" },
  ],
  flood: [
    { key: "susceptibility", label: "Suscettibilità", color: "#7fa7e8" },
    { key: "pluvial", label: "Pioggia", color: "#6fd3ee" },
    { key: "fluvial", label: "Fiume", color: "#a8dff0" },
  ],
};

function readComponents(
  hazard: HazardType,
  factors: Record<string, unknown>,
): Component[] {
  const spec = COMPONENTS_BY_HAZARD[hazard] ?? COMPONENTS_BY_HAZARD["landslide"] ?? [];
  return spec.map((c) => ({ ...c, value: pickScalar(factors, c.key) }));
}

function asLevel(level: string): RiskLevel {
  return (
    ["None", "Low", "Moderate", "High", "VeryHigh"].includes(level)
      ? (level as RiskLevel)
      : "None"
  );
}

/**
 * Side panel showing the deterministic engine's per-component
 * contributions plus the LLM briefing for the currently-selected cell.
 *
 * Never invents numbers — the displayed values come straight from
 * ``GET /api/cell/{cell_id}/breakdown``.
 */
export function CellPopup(props: CellPopupProps): JSX.Element | null {
  const cellId = props.cellId;
  const onDismiss = props.onDismiss;
  const [data, setData] = useState<CellBreakdownResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outlook, setOutlook] = useState<CellRainOutlookResponse["outlook"]>(null);
  const [fwiNormale, setFwiNormale] = useState<FwiNormale | null>(null);

  // Dalla nostra API e non dall'API pubblica di Open-Meteo dal browser
  // (#159): ogni clic consumava il tetto giornaliero che l'istanza propria
  // esiste per non consumare, e leggeva una fonte diversa da quella del
  // punteggio.
  useEffect(() => {
    setOutlook(null);
    if (!cellId) return;
    const ctrl = new AbortController();
    defaultApiClient
      .getCellRainOutlook(cellId, ctrl.signal)
      .then((r) => setOutlook(r.outlook))
      .catch(() => {
        // Il popup resta utile anche senza il meteo.
      });
    return () => ctrl.abort();
  }, [cellId]);

  const { selected } = useHazard();
  // Tutti e tre i pericoli della cella, per le schede in testa al popup.
  // Prima il popup chiedeva un pericolo solo — quello del selettore, che in
  // vista d'insieme vale «frane» — e una cella con incendio alto mostrava le
  // barre delle frane senza dire che ce n'era un altro peggiore.
  const [quadro, setQuadro] = useState<CellMultiHazardResponse | null>(null);
  const [scheda, setScheda] = useState<HazardType | null>(null);

  useEffect(() => {
    setQuadro(null);
    setScheda(null);
    if (!cellId) return;
    const ctrl = new AbortController();
    defaultApiClient
      .getCellMultiHazard(cellId, ctrl.signal)
      .then((q) => {
        setQuadro(q);
        // Si apre sul pericolo **peggiore della cella**, non su quello del
        // selettore. La mappa di default è sulle frane, e aprire lì voleva
        // dire che una cella con l'incendio alto mostrava le barre delle
        // frane: il popup serve a dire cosa minaccia questo punto, e gli
        // altri pericoli restano a un clic nelle schede.
        setScheda(q.worst_hazard ?? selected);
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setScheda(selected);
      });
    return () => ctrl.abort();
  }, [cellId, selected]);

  const hazard: HazardType = scheda ?? selected;

  useEffect(() => {
    if (!cellId || scheda === null) {
      setData(null);
      setError(null);
      return;
    }
    const ctrl = new AbortController();
    setData(null);
    setError(null);
    defaultApiClient
      .getCellBreakdown(cellId, ctrl.signal, hazard)
      .then(setData)
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        if (err instanceof ApiClientError && err.status === 404) {
          setError(
            "Questa cella non è ancora stata rivalutata dal ciclo di " +
              "monitoraggio (le regioni vengono aggiornate a rotazione). " +
              "Riprova tra qualche ora.",
          );
        } else if (err instanceof ApiClientError) {
          setError(`Errore ${err.status}: ${err.message}`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("errore sconosciuto");
        }
      });
    return () => ctrl.abort();
  }, [cellId, hazard, scheda]);

  // Le schede: sempre tutte e tre, nello stesso ordine, con il loro numero.
  // Una scheda si legge senza aprirla — «Incendio 0,67» accanto a «Frana
  // 0,38» dice già dove guardare.
  const schede =
    quadro === null ? null : (
      <div className="popup-schede" role="tablist" aria-label="Pericolo">
        {(["landslide", "flood", "wildfire"] as HazardType[]).map((h) => {
          const v = quadro.per_hazard.find((x) => x.hazard === h);
          const livello = (v?.level ?? "None") as RiskLevel;
          return (
            <button
              key={h}
              type="button"
              role="tab"
              aria-selected={h === hazard}
              className={`popup-scheda ${h === hazard ? "on" : ""}`}
              onClick={() => setScheda(h)}
            >
              <span
                className="popup-scheda-chip"
                style={{ background: RISK_COLOR_BY_LEVEL[livello] }}
                aria-hidden
              />
              {NOME_SCHEDA[h]}{" "}
              <strong>
                {v?.score == null
                  ? "—"
                  : v.score.toLocaleString("it-IT", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
              </strong>
            </button>
          );
        })}
      </div>
    );

  // Il normale del mese per l'incendio: chiesto solo quando il breakdown
  // porta il meteo, cioè quando c'è un FWI da confrontare.
  const meteoIncendio =
    data?.factors && typeof data.factors["fire_weather"] === "object"
      ? (data.factors["fire_weather"] as Record<string, unknown>)
      : null;
  const fwiOggi = typeof meteoIncendio?.["fwi"] === "number" ? meteoIncendio["fwi"] : null;
  const giornoMeteo = typeof meteoIncendio?.["day"] === "string" ? meteoIncendio["day"] : null;
  useEffect(() => {
    setFwiNormale(null);
    if (!cellId || hazard !== "wildfire" || fwiOggi === null || giornoMeteo === null) return;
    const ctrl = new AbortController();
    defaultApiClient
      .getCellFwiNormale(cellId, fwiOggi, new Date(giornoMeteo).getMonth() + 1, ctrl.signal)
      .then((r) => setFwiNormale(r.normale))
      .catch(() => {
        // Senza climatologia la lettura resta quella assoluta.
      });
    return () => ctrl.abort();
  }, [cellId, hazard, fwiOggi, giornoMeteo]);

  if (!cellId) return null;

  if (error) {
    return (
      <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
        <h3 id="cell-id">Cella {cellId}</h3>
        <p style={{ color: "var(--warn)" }}>{error}</p>
        {onDismiss ? (
          <button type="button" onClick={onDismiss}>
            chiudi
          </button>
        ) : null}
      </aside>
    );
  }
  if (!data) {
    return (
      <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
        {schede}
        <h3 id="cell-id">Cella {cellId}</h3>
        <p>caricamento…</p>
      </aside>
    );
  }

  const factors = data.factors;
  // Il pericolo lo dice la riga letta, non il selettore: se la fetch è
  // arrivata mentre l'utente cambiava, le due cose divergono per un istante e
  // le etichette seguirebbero il selettore invece dei numeri.
  const rowHazard: HazardType = data.hazard_type ?? hazard;
  const components = readComponents(rowHazard, factors);
  const level = asLevel(data.level);

  // Una cella non misurata è grigia sulla mappa, e questo è il posto dove si
  // viene a chiedere perché (#143). Il punteggio non si mostra: varrebbe zero
  // per assenza di dato, e uno zero accanto a «nessun pericolo» è la bugia
  // che questa modifica toglie.
  if (data.measured === false) {
    return (
      <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
        {schede}
        <h3 id="cell-id" style={{ margin: 0 }}>
          <span className="level-chip is-unknown">non misurato</span>
        </h3>
        <p className="alert-meta" style={{ margin: "2px 0 0" }}>
          {props.place ? `${props.place} · ` : ""}cella {data.cell_id} · modello{" "}
          {data.pipeline_version} · {new Date(data.computed_at).toLocaleString("it-IT")}
        </p>
        <p className="verdict verdict-neutral" role="status">
          Il dato che questo pericolo richiede non è arrivato. Il punteggio
          varrebbe zero per assenza di misura, non perché non ci sia pericolo:
          per questo la cella è grigia e non verde.
        </p>
      </aside>
    );
  }

  return (
    <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
      {schede}
      <h3 id="cell-id" style={{ margin: 0 }}>
        <span className="popup-score">{data.score.toFixed(2)}</span>
        <span
          className={`level-chip ${RISK_SCURE.has(level) ? "on-dark" : ""}`}
          style={{ background: RISK_COLOR_BY_LEVEL[level] }}
        >
          {RISK_LABEL_IT_BY_LEVEL[level]}
        </span>
      </h3>
      <p className="alert-meta" style={{ margin: "2px 0 0" }}>
        {props.place ? `${props.place} · ` : ""}cella {data.cell_id} · modello{" "}
        {data.pipeline_version} · {new Date(data.computed_at).toLocaleString("it-IT")}
      </p>
      {(() => {
        const v = verdict(level, props.exposure);
        return (
          <p className={`verdict verdict-${v.tone}`} role="status">
            {v.text}
          </p>
        );
      })()}
      <p className="plain-summary">{plainSummary(rowHazard, components, factors, props.exposure)}</p>
      {rowHazard === "wildfire"
        ? ((righe) =>
            righe ? (
              <div className="lettura-incendio">
                <span className="eyebrow">Come leggere questo numero</span>
                {righe.map((r) => (
                  <p key={r}>{r}</p>
                ))}
              </div>
            ) : null)(letturaIncendio(factors, fwiNormale))
        : null}
      {props.priority != null && props.exposure ? (
        <p className="priority-line">
          <span className="eyebrow" style={{ marginBottom: 2 }}>
            Perché è in alto in lista
          </span>
          Non perché il versante sia più instabile di altri, ma perché un
          eventuale movimento toccherebbe {exposureText(props.exposure)}.
        </p>
      ) : null}
      <div className="comp-bars">
        {components.map((c) => (
          <div className="comp-bar" key={c.key}>
            <span>{c.label}</span>
            <span className="track">
              <span
                className="fill"
                style={{
                  width: `${Math.min(100, c.value * 100)}%`,
                  background: c.color,
                }}
              />
            </span>
            <span className="val">{c.value.toFixed(3)}</span>
          </div>
        ))}
      </div>
      {outlook ? (
        <p className="rain-outlook">
          <span className="eyebrow" style={{ marginBottom: 2 }}>
            Meteo previsto · 48h
          </span>
          pioggia <span className="mono">{outlook.total_mm.toFixed(1)} mm</span>
          {" · "}picco{" "}
          <span className="mono">{outlook.peak_mmh.toFixed(1)} mm/h</span>
        </p>
      ) : null}
      <ComeNasce cellId={data.cell_id} hazard={rowHazard} />

      {onDismiss ? (
        <button type="button" onClick={onDismiss} style={{ marginTop: 8 }}>
          chiudi
        </button>
      ) : null}
    </aside>
  );
}

export default CellPopup;
