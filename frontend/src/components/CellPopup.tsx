import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient, ApiClientError } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import { locale, testi, useLingua, useTesti, type Lingua } from "../lib/i18n";
import ComeNasce from "./ComeNasce";
import ContributoEsperto from "./ContributoEsperto";
import { RISK_COLOR_BY_LEVEL, RISK_SCURE, useEtichetteRischio } from "../lib/risk-colors";
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

/** I tag con distanza OSM ("statale a 250 m") arrivano in italiano dal
 * backend: in italiano serve solo l'articolo, in inglese si ricompongono. */
const TAG_OSM = /^(autostrada|statale|ferrovia) a (.+)$/;

const STRADA_EN: Record<string, string> = {
  autostrada: "a motorway",
  statale: "a main road",
  ferrovia: "a railway",
};

function distanzaEn(d: string): string {
  return d.replace(/^meno di /, "less than ").replace(/(\d),(\d)/, "$1.$2");
}

const T = testi(
  {
    schede: { landslide: "Frana", flood: "Allagamento", wildfire: "Incendio" } as Record<
      HazardType,
      string
    >,
    esposizione: {
      abitato: "un centro abitato",
      "vicino abitato": "case nelle vicinanze",
      infrastrutture: "strade o ferrovie principali",
      "infrastrutture vicine": "strade o ferrovie nelle vicinanze",
    } as Record<string, string>,
    frase: (tag: string): string => {
      if (tag.startsWith("autostrada")) return `un'${tag}`;
      if (tag.startsWith("statale") || tag.startsWith("ferrovia")) return `una ${tag}`;
      return tag;
    },
    e: " e ",
    verdetto: {
      altoEsposto: "Da attenzionare subito: rischio alto vicino a case o strade.",
      altoIsolato: "Da attenzionare: rischio alto, versante isolato.",
      moderatoEsposto:
        "Da tenere sotto osservazione: rischio moderato, ma la zona è " +
        "abitata o attraversata da infrastrutture.",
      moderatoIsolato:
        "Controlli di routine: rischio moderato su versante isolato, " +
        "nessuna azione immediata.",
      bassoEsposto:
        "Nessuna preoccupazione immediata: il rischio è basso — la cella è " +
        "in lista solo perché vicina ad abitazioni o strade.",
      basso: "Nessuna preoccupazione: rischio basso.",
    },
    driver: {
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
    } as Record<string, string>,
    nasce: (d: string) => `Il punteggio nasce soprattutto ${d}.`,
    // Le classi FWI di Copernicus EFFIS, le stesse della sua legenda.
    classiEffis: [
      [11.2, "Low (sotto 11,2)"],
      [21.3, "Moderate (11,2–21,3)"],
      [38.0, "High (21,3–38)"],
      [50.0, "Very High (38–50)"],
      [70.0, "Extreme (50–70)"],
      [Infinity, "Very Extreme (oltre 70)"],
    ] as readonly (readonly [number, string])[],
    potenziale:
      "È il pericolo meteorologico potenziale: quanto si propagherebbe un " +
      "incendio se partisse, non la probabilità che parta.",
    meteoDel: (giorno: string) => ` · meteo del ${giorno}`,
    indiceFwi: (fwi: string, classe: string, giorno: string) =>
      `Indice meteo FWI ${fwi}: classe ${classe} sulla scala di Copernicus EFFIS${giorno}.`,
    giudizio: {
      moltoSopra: "Molto sopra il solito",
      sopra: "Sopra il solito",
      norma: "Nella norma",
      sotto: "Sotto il solito",
    },
    rispetto: (giudizio: string, mese: string, p: string, a0: number, a1: number, med: string) =>
      `${giudizio} per ${mese}: più alto del ${p} % dei giorni di ${mese} ` +
      `${a0}–${a1} in questo punto, dove la mediana è FWI ${med}.`,
    dc: {
      molto:
        "suolo e combustibili grossi molto secchi, come a fine estate: si abbassa solo con piogge abbondanti",
      marcata: "siccità marcata, che una pioggia leggera non cancella",
      moderata: "siccità moderata",
      nessuna: "nessuna siccità di fondo",
    },
    codiceDc: (dc: string, lettura: string) => `Codice di siccità DC ${dc}: ${lettura}.`,
    alluvione: {
      avanti: (mm: string) =>
        "Questo numero guarda avanti: è calcolato sulla pioggia prevista nelle " +
        "prossime 72 ore" +
        mm +
        ", non su quella che cade adesso.",
      nessunSegnale:
        "Nessun segnale in corso: il punteggio riflette solo dove si trova " +
        "la cella, non un pericolo in atto.",
      fiume: "Il segnale viene dal fiume, non dalla pioggia che cade qui.",
      locale: "Il segnale viene dalla pioggia locale, non da un fiume in piena.",
      nonMappata:
        "Questa cella è fuori dalle zone idrauliche mappate: il valore di " +
        "base è prudenziale, non una perimetrazione ufficiale.",
    },
    incendio: {
      umido:
        "Le condizioni meteo non favoriscono il fuoco: combustibile umido " + "o aria fresca.",
      secco: "Il tempo è secco ma non estremo.",
      estremo: "Caldo, siccità e vento stanno spingendo il pericolo in alto.",
      avviamento:
        "L'indice è in avviamento: si basa su pochi giorni di storia meteo " +
        "e va letto con prudenza.",
    },
    frana: {
      asciutto:
        "Non c'è pioggia in corso: il punteggio riflette la fragilità " +
        "storica del versante, non un pericolo in atto.",
      poco: "La pioggia recente incide poco.",
      moderato: "La pioggia recente contribuisce in modo moderato.",
      alto: "La pioggia recente sta spingendo il rischio verso l'alto.",
    },
    vicinanze: (exp: string) => `Nelle vicinanze: ${exp}.`,
    componenti: {
      s: "S statico",
      m: "M meteo",
      e: "E sismico",
      f: "F post-incendio",
      h: "H idrologico",
      fwi_norm: "FWI (tempo)",
      fuel: "Combustibile",
      slope: "Pendenza",
      susceptibility: "Suscettibilità",
      pluvial: "Pioggia",
      fluvial: "Fiume",
    } as Record<string, string>,
    nonRivalutata:
      "Questa cella non è ancora stata rivalutata dal ciclo di " +
      "monitoraggio (le regioni vengono aggiornate a rotazione). " +
      "Riprova tra qualche ora.",
    errore: (status: number, msg: string) => `Errore ${status}: ${msg}`,
    sconosciuto: "errore sconosciuto",
    pericolo: "Pericolo",
    cella: (id: string) => `Cella ${id}`,
    caricamento: "caricamento…",
    chiudi: "chiudi",
    nonMisurato: "non misurato",
    meta: (cella: string, modello: string, quando: string) =>
      `cella ${cella} · modello ${modello} · ${quando}`,
    spiegaNonMisurato:
      "Il dato che questo pericolo richiede non è arrivato. Il punteggio " +
      "varrebbe zero per assenza di misura, non perché non ci sia pericolo: " +
      "per questo la cella è grigia e non verde.",
    comeLeggere: "Come leggere questo numero",
    percheInAlto: "Perché è in alto in lista",
    perche: (exp: string) =>
      "Non perché il versante sia più instabile di altri, ma perché un " +
      `eventuale movimento toccherebbe ${exp}.`,
    meteoPrevisto: "Meteo previsto · 48h",
    pioggia: "pioggia",
    picco: "picco",
  },
  {
    schede: { landslide: "Landslide", flood: "Flood", wildfire: "Wildfire" },
    esposizione: {
      abitato: "a built-up area",
      "vicino abitato": "houses nearby",
      infrastrutture: "major roads or railways",
      "infrastrutture vicine": "roads or railways nearby",
    },
    frase: (tag: string): string => {
      const m = TAG_OSM.exec(tag);
      if (m) return `${STRADA_EN[m[1]!]} ${distanzaEn(m[2]!)} away`;
      return tag;
    },
    e: " and ",
    verdetto: {
      altoEsposto: "Needs attention now: high risk near houses or roads.",
      altoIsolato: "Needs attention: high risk, isolated slope.",
      moderatoEsposto:
        "Keep under observation: moderate risk, but the area is " +
        "inhabited or crossed by infrastructure.",
      moderatoIsolato:
        "Routine checks: moderate risk on an isolated slope, " + "no immediate action.",
      bassoEsposto:
        "No immediate concern: the risk is low — the cell is " +
        "listed only because it is close to homes or roads.",
      basso: "No concern: low risk.",
    },
    driver: {
      s: "from the nature of the slope: geology, gradient and past landslides",
      m: "from the push of recent rain",
      e: "from recent earthquakes",
      f: "from the effect of recent wildfires",
      h: "from the hydraulic hazard of the area",
      fwi_norm: "from the weather: heat, dryness and wind",
      fuel: "from how flammable the vegetation is here",
      slope: "from the slope, which drives fire uphill",
      susceptibility: "from where it lies: an area that water reaches",
      pluvial: "from the forecast rain, more than the ground can absorb",
      fluvial: "from the forecast river discharge, above its normal level",
    },
    nasce: (d: string) => `The score comes mainly ${d}.`,
    classiEffis: [
      [11.2, "Low (below 11.2)"],
      [21.3, "Moderate (11.2–21.3)"],
      [38.0, "High (21.3–38)"],
      [50.0, "Very High (38–50)"],
      [70.0, "Extreme (50–70)"],
      [Infinity, "Very Extreme (above 70)"],
    ],
    potenziale:
      "This is the potential fire-weather hazard: how far a fire would " +
      "spread if one started, not the probability that one starts.",
    meteoDel: (giorno: string) => ` · weather of ${giorno}`,
    indiceFwi: (fwi: string, classe: string, giorno: string) =>
      `FWI weather index ${fwi}: ${classe} class on the Copernicus EFFIS scale${giorno}.`,
    giudizio: {
      moltoSopra: "Well above normal",
      sopra: "Above normal",
      norma: "Normal",
      sotto: "Below normal",
    },
    rispetto: (giudizio: string, mese: string, p: string, a0: number, a1: number, med: string) =>
      `${giudizio} for ${mese}: higher than ${p}% of ${mese} days ` +
      `${a0}–${a1} at this location, where the median is FWI ${med}.`,
    dc: {
      molto:
        "soil and heavy fuels very dry, as at the end of summer: only heavy rain brings it down",
      marcata: "marked drought, which light rain does not erase",
      moderata: "moderate drought",
      nessuna: "no underlying drought",
    },
    codiceDc: (dc: string, lettura: string) => `Drought Code DC ${dc}: ${lettura}.`,
    alluvione: {
      avanti: (mm: string) =>
        "This number looks ahead: it is computed on the rain forecast for the " +
        "next 72 hours" +
        mm +
        ", not on the rain falling now.",
      nessunSegnale:
        "No active signal: the score only reflects where the cell lies, " +
        "not a hazard in progress.",
      fiume: "The signal comes from the river, not from the rain falling here.",
      locale: "The signal comes from local rain, not from a river in flood.",
      nonMappata:
        "This cell is outside the mapped hydraulic zones: the base value " +
        "is precautionary, not an official delineation.",
    },
    incendio: {
      umido: "The weather does not favour fire: damp fuel or cool air.",
      secco: "The weather is dry but not extreme.",
      estremo: "Heat, drought and wind are pushing the hazard up.",
      avviamento:
        "The index is still spinning up: it rests on only a few days of " +
        "weather history and should be read with caution.",
    },
    frana: {
      asciutto:
        "No rain in progress: the score reflects the slope's historical " +
        "fragility, not a hazard in progress.",
      poco: "Recent rain has little effect.",
      moderato: "Recent rain contributes moderately.",
      alto: "Recent rain is pushing the risk up.",
    },
    vicinanze: (exp: string) => `Nearby: ${exp}.`,
    componenti: {
      s: "S static",
      m: "M weather",
      e: "E seismic",
      f: "F post-fire",
      h: "H hydrological",
      fwi_norm: "FWI (weather)",
      fuel: "Fuel",
      slope: "Slope",
      susceptibility: "Susceptibility",
      pluvial: "Rain",
      fluvial: "River",
    },
    nonRivalutata:
      "This cell has not yet been reassessed by the monitoring cycle " +
      "(regions are updated in rotation). Try again in a few hours.",
    errore: (status: number, msg: string) => `Error ${status}: ${msg}`,
    sconosciuto: "unknown error",
    pericolo: "Hazard",
    cella: (id: string) => `Cell ${id}`,
    caricamento: "loading…",
    chiudi: "close",
    nonMisurato: "not measured",
    meta: (cella: string, modello: string, quando: string) =>
      `cell ${cella} · model ${modello} · ${quando}`,
    spiegaNonMisurato:
      "The data this hazard needs has not arrived. The score would be zero " +
      "for lack of a measurement, not because there is no hazard: that is " +
      "why the cell is grey and not green.",
    comeLeggere: "How to read this number",
    percheInAlto: "Why it is high on the list",
    perche: (exp: string) =>
      "Not because the slope is less stable than others, but because any " +
      `movement would affect ${exp}.`,
    meteoPrevisto: "Forecast weather · 48h",
    pioggia: "rain",
    picco: "peak",
  },
);

type Testi = (typeof T)["it"];

function phraseFor(tag: string, t: Testi): string {
  return t.esposizione[tag] ?? t.frase(tag);
}

function exposureText(t: Testi, exposure?: string | null): string | null {
  if (!exposure) return null;
  const parts = exposure
    .split(", ")
    .map((tag) => phraseFor(tag, t))
    .filter(Boolean);
  if (parts.length === 0) return null;
  return parts.length === 1
    ? parts[0]!
    : `${parts.slice(0, -1).join(", ")}${t.e}${parts[parts.length - 1]}`;
}

/** Verdetto operativo — deterministico da livello + esposizione:
 * risponde a "devo preoccuparmi? devo monitorare questa cella?". */
function verdict(
  t: Testi,
  level: RiskLevel,
  exposure?: string | null,
): { text: string; tone: "ok" | "watch" | "warn" } {
  const exposed = Boolean(exposure);
  const v = t.verdetto;
  if (level === "VeryHigh" || level === "High") {
    return { text: exposed ? v.altoEsposto : v.altoIsolato, tone: "warn" };
  }
  if (level === "Moderate") {
    return exposed
      ? { text: v.moderatoEsposto, tone: "watch" }
      : { text: v.moderatoIsolato, tone: "ok" };
  }
  return { text: exposed ? v.bassoEsposto : v.basso, tone: "ok" };
}

function cifra(n: number, loc: string, decimali = 1): string {
  return n.toLocaleString(loc, { minimumFractionDigits: decimali, maximumFractionDigits: decimali });
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
  lingua: Lingua = "it",
): string[] | null {
  const t = T[lingua];
  const loc = locale(lingua);
  const fw = factors["fire_weather"];
  if (typeof fw !== "object" || fw === null) return null;
  const meteo = fw as Record<string, unknown>;
  const fwi = typeof meteo["fwi"] === "number" ? meteo["fwi"] : null;
  const dc = typeof meteo["dc"] === "number" ? meteo["dc"] : null;
  if (fwi === null) return null;
  const righe = [t.potenziale];
  const classe = t.classiEffis.find(([max]) => fwi < max)?.[1] ?? "";
  const giorno =
    typeof meteo["day"] === "string"
      ? t.meteoDel(new Date(meteo["day"]).toLocaleDateString(loc, { day: "numeric", month: "long" }))
      : "";
  righe.push(t.indiceFwi(cifra(fwi, loc), classe, giorno));
  if (normale !== null && typeof meteo["day"] === "string") {
    // Rispetto al solito: la classe è assoluta, uguale ad agosto e a
    // ottobre; questa riga dice dove cade il valore fra i giorni dello
    // stesso mese, nello stesso punto, negli anni dell'archivio.
    const mese = new Date(meteo["day"]).toLocaleDateString(loc, { month: "long" });
    const p = normale.percentile;
    const g = t.giudizio;
    const giudizio = p >= 90 ? g.moltoSopra : p >= 75 ? g.sopra : p > 25 ? g.norma : g.sotto;
    righe.push(
      t.rispetto(
        giudizio,
        mese,
        cifra(p, loc, 0),
        normale.anni[0],
        normale.anni[1],
        cifra(normale.mediana, loc),
      ),
    );
  }
  if (dc !== null) {
    // Il DC scende solo con piogge vere (sopra 2,8 mm in un giorno): è la
    // memoria lunga della siccità, ed è lui che tiene alto l'indice dopo
    // un'estate secca anche quando le giornate si fanno miti.
    const lettura =
      dc >= 500 ? t.dc.molto : dc >= 350 ? t.dc.marcata : dc >= 200 ? t.dc.moderata : t.dc.nessuna;
    righe.push(t.codiceDc(cifra(dc, loc, 0), lettura));
  }
  return righe;
}

/** Spiegazione della cella in linguaggio piano — deterministica, dal
 * breakdown: niente LLM, niente numeri inventati. */
function plainSummary(
  t: Testi,
  hazard: HazardType,
  components: Component[],
  factors: Record<string, unknown>,
  exposure?: string | null,
): string {
  const parts: string[] = [];
  const top = [...components].sort((x, y) => y.value - x.value)[0];
  const driver = top ? t.driver[top.key] : undefined;
  if (top && top.value > 0.05 && driver) {
    parts.push(t.nasce(driver));
  }

  if (hazard === "flood") {
    const pluvial = pickScalar(factors, "pluvial");
    const fluvial = pickScalar(factors, "fluvial");
    const pioggia = factors["rain_mm"];
    parts.push(t.alluvione.avanti(typeof pioggia === "number" ? ` (${Math.round(pioggia)} mm)` : ""));
    if (pluvial === 0 && fluvial === 0) {
      parts.push(t.alluvione.nessunSegnale);
    } else if (fluvial > pluvial) {
      parts.push(t.alluvione.fiume);
    } else {
      parts.push(t.alluvione.locale);
    }
    if (factors["mapped"] === false) {
      // Il mosaico ISPRA copre i bacini ufficialmente studiati: dirlo è più
      // onesto che presentare un valore di ripiego come una perimetrazione.
      parts.push(t.alluvione.nonMappata);
    }
  } else if (hazard === "wildfire") {
    const fwi = pickScalar(factors, "fwi_norm");
    if (fwi < 0.05) {
      parts.push(t.incendio.umido);
    } else if (fwi < 0.42) {
      parts.push(t.incendio.secco);
    } else {
      parts.push(t.incendio.estremo);
    }
    if (factors["spinup"] === true) {
      // I tre codici di umidità sono ricorsivi: dirlo è più onesto che
      // presentare un indice appena avviato come uno consolidato.
      parts.push(t.incendio.avviamento);
    }
  } else {
    const m = pickScalar(factors, "m");
    if (m < 0.05) {
      parts.push(t.frana.asciutto);
    } else if (m < 0.2) {
      parts.push(t.frana.poco);
    } else if (m < 0.5) {
      parts.push(t.frana.moderato);
    } else {
      parts.push(t.frana.alto);
    }
  }

  const exp = exposureText(t, exposure);
  if (exp) {
    parts.push(t.vicinanze(exp));
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
const COMPONENTS_BY_HAZARD: Record<string, readonly { key: string; color: string }[]> = {
  landslide: [
    { key: "s", color: "#7fa7e8" },
    { key: "m", color: "#ff8a1f" },
    { key: "e", color: "#c6a8ff" },
    { key: "f", color: "#ffa552" },
    { key: "h", color: "#6fd3ee" },
  ],
  wildfire: [
    { key: "fwi_norm", color: "#ff9ad5" },
    { key: "fuel", color: "#6fcf97" },
    { key: "slope", color: "#c6a8ff" },
  ],
  flood: [
    { key: "susceptibility", color: "#7fa7e8" },
    { key: "pluvial", color: "#6fd3ee" },
    { key: "fluvial", color: "#a8dff0" },
  ],
};

function readComponents(
  t: Testi,
  hazard: HazardType,
  factors: Record<string, unknown>,
): Component[] {
  const spec = COMPONENTS_BY_HAZARD[hazard] ?? COMPONENTS_BY_HAZARD["landslide"] ?? [];
  return spec.map((c) => ({
    ...c,
    label: t.componenti[c.key] ?? c.key,
    value: pickScalar(factors, c.key),
  }));
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
  // L'errore si salva come motivo e non come frase: cambiando lingua il
  // messaggio si riscrive senza rifare la richiesta.
  const [error, setError] = useState<
    | { tipo: "404" }
    | { tipo: "api"; status: number; message: string }
    | { tipo: "msg"; message: string }
    | { tipo: "ignoto" }
    | null
  >(null);
  const [outlook, setOutlook] = useState<CellRainOutlookResponse["outlook"]>(null);
  const [fwiNormale, setFwiNormale] = useState<FwiNormale | null>(null);
  const t = useTesti(T);
  const { lingua } = useLingua();
  const loc = locale(lingua);
  const etichetteRischio = useEtichetteRischio();

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
          setError({ tipo: "404" });
        } else if (err instanceof ApiClientError) {
          setError({ tipo: "api", status: err.status, message: err.message });
        } else if (err instanceof Error) {
          setError({ tipo: "msg", message: err.message });
        } else {
          setError({ tipo: "ignoto" });
        }
      });
    return () => ctrl.abort();
  }, [cellId, hazard, scheda]);

  // Le schede: sempre tutte e tre, nello stesso ordine, con il loro numero.
  // Una scheda si legge senza aprirla — «Incendio 0,67» accanto a «Frana
  // 0,38» dice già dove guardare.
  const schede =
    quadro === null ? null : (
      <div className="popup-schede" role="tablist" aria-label={t.pericolo}>
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
              {t.schede[h]}{" "}
              <strong>
                {v?.score == null
                  ? "—"
                  : v.score.toLocaleString(loc, {
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
        <h3 id="cell-id">{t.cella(cellId)}</h3>
        <p style={{ color: "var(--warn)" }}>
          {error.tipo === "404"
            ? t.nonRivalutata
            : error.tipo === "api"
              ? t.errore(error.status, error.message)
              : error.tipo === "msg"
                ? error.message
                : t.sconosciuto}
        </p>
        {onDismiss ? (
          <button type="button" onClick={onDismiss}>
            {t.chiudi}
          </button>
        ) : null}
      </aside>
    );
  }
  if (!data) {
    return (
      <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
        {schede}
        <h3 id="cell-id">{t.cella(cellId)}</h3>
        <p>{t.caricamento}</p>
      </aside>
    );
  }

  const factors = data.factors;
  // Il pericolo lo dice la riga letta, non il selettore: se la fetch è
  // arrivata mentre l'utente cambiava, le due cose divergono per un istante e
  // le etichette seguirebbero il selettore invece dei numeri.
  const rowHazard: HazardType = data.hazard_type ?? hazard;
  const components = readComponents(t, rowHazard, factors);
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
          <span className="level-chip is-unknown">{t.nonMisurato}</span>
        </h3>
        <p className="alert-meta" style={{ margin: "2px 0 0" }}>
          {props.place ? `${props.place} · ` : ""}
          {t.meta(data.cell_id, data.pipeline_version, new Date(data.computed_at).toLocaleString(loc))}
        </p>
        <p className="verdict verdict-neutral" role="status">
          {t.spiegaNonMisurato}
        </p>
        <ContributoEsperto key={`${data.cell_id}|${rowHazard}`} cellId={data.cell_id} hazard={rowHazard} />
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
          {etichetteRischio[level]}
        </span>
      </h3>
      <p className="alert-meta" style={{ margin: "2px 0 0" }}>
        {props.place ? `${props.place} · ` : ""}
        {t.meta(data.cell_id, data.pipeline_version, new Date(data.computed_at).toLocaleString(loc))}
      </p>
      {(() => {
        const v = verdict(t, level, props.exposure);
        return (
          <p className={`verdict verdict-${v.tone}`} role="status">
            {v.text}
          </p>
        );
      })()}
      <p className="plain-summary">{plainSummary(t, rowHazard, components, factors, props.exposure)}</p>
      {rowHazard === "wildfire"
        ? ((righe) =>
            righe ? (
              <div className="lettura-incendio">
                <span className="eyebrow">{t.comeLeggere}</span>
                {righe.map((r) => (
                  <p key={r}>{r}</p>
                ))}
              </div>
            ) : null)(letturaIncendio(factors, fwiNormale, lingua))
        : null}
      {props.priority != null && props.exposure ? (
        <p className="priority-line">
          <span className="eyebrow" style={{ marginBottom: 2 }}>
            {t.percheInAlto}
          </span>
          {t.perche(exposureText(t, props.exposure) ?? "")}
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
            {t.meteoPrevisto}
          </span>
          {t.pioggia} <span className="mono">{outlook.total_mm.toFixed(1)} mm</span>
          {" · "}
          {t.picco}{" "}
          <span className="mono">{outlook.peak_mmh.toFixed(1)} mm/h</span>
        </p>
      ) : null}
      <ComeNasce cellId={data.cell_id} hazard={rowHazard} />
      <ContributoEsperto key={`${data.cell_id}|${rowHazard}`} cellId={data.cell_id} hazard={rowHazard} />

      {onDismiss ? (
        <button type="button" onClick={onDismiss} style={{ marginTop: 8 }}>
          {t.chiudi}
        </button>
      ) : null}
    </aside>
  );
}

export default CellPopup;
