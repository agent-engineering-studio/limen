import { useEffect, useState } from "react";

import { defaultApiClient, ApiClientError } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { CellBreakdownResponse, HazardType, RiskLevel } from "../types";

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
};

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

  if (hazard === "wildfire") {
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

interface RainOutlook {
  total48h: number;
  peakMmh: number;
}

async function fetchRainOutlook(
  lon: number,
  lat: number,
  signal: AbortSignal,
): Promise<RainOutlook> {
  const url =
    "https://api.open-meteo.com/v1/forecast" +
    `?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}` +
    "&hourly=precipitation&forecast_days=2&timezone=UTC";
  const resp = await fetch(url, { signal });
  if (!resp.ok) throw new Error(`open-meteo ${resp.status}`);
  const data = (await resp.json()) as {
    hourly?: { precipitation?: (number | null)[] };
  };
  const rain = (data.hourly?.precipitation ?? []).map((v) => v ?? 0);
  return {
    total48h: rain.reduce((a, b) => a + b, 0),
    peakMmh: rain.reduce((a, b) => Math.max(a, b), 0),
  };
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
    { key: "s", label: "S statico", color: "#2456a3" },
    { key: "m", label: "M meteo", color: "#e8720c" },
    { key: "e", label: "E sismico", color: "#7a5cc0" },
    { key: "f", label: "F post-incendio", color: "#b34a04" },
    { key: "h", label: "H idrologico", color: "#2a8fb5" },
  ],
  wildfire: [
    { key: "fwi_norm", label: "FWI (tempo)", color: "#d95f0e" },
    { key: "fuel", label: "Combustibile", color: "#238b45" },
    { key: "slope", label: "Pendenza", color: "#7a5cc0" },
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
  const [outlook, setOutlook] = useState<RainOutlook | null>(null);

  useEffect(() => {
    setOutlook(null);
    if (props.lon == null || props.lat == null || !cellId) return;
    const ctrl = new AbortController();
    fetchRainOutlook(props.lon, props.lat, ctrl.signal)
      .then(setOutlook)
      .catch(() => {
        // Il popup resta utile anche senza il meteo.
      });
    return () => ctrl.abort();
  }, [cellId, props.lon, props.lat]);

  const { selected: hazard } = useHazard();

  useEffect(() => {
    if (!cellId) {
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
  }, [cellId, hazard]);

  if (!cellId) return null;

  if (error) {
    return (
      <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
        <h3 id="cell-id">Cella {cellId}</h3>
        <p style={{ color: "#a72020" }}>{error}</p>
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

  return (
    <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
      <h3 id="cell-id" style={{ margin: 0 }}>
        <span className="popup-score">{data.score.toFixed(2)}</span>
        <span
          className={`level-chip ${level === "VeryHigh" ? "on-dark" : ""}`}
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
          pioggia <span className="mono">{outlook.total48h.toFixed(1)} mm</span>
          {" · "}picco{" "}
          <span className="mono">{outlook.peakMmh.toFixed(1)} mm/h</span>
        </p>
      ) : null}

      {onDismiss ? (
        <button type="button" onClick={onDismiss} style={{ marginTop: 8 }}>
          chiudi
        </button>
      ) : null}
    </aside>
  );
}

export default CellPopup;
