import { useEffect, useState } from "react";

import { defaultApiClient, ApiClientError } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { CellBreakdownResponse, RiskLevel } from "../types";

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

function exposureText(exposure?: string | null): string | null {
  if (!exposure) return null;
  const parts = exposure
    .split(", ")
    .map((t) => EXPOSURE_PHRASE[t] ?? t)
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

/** Spiegazione della cella in linguaggio piano — deterministica, dal
 * breakdown: niente LLM, niente numeri inventati. */
function plainSummary(b: BreakdownView, exposure?: string | null): string {
  const drivers: [keyof BreakdownView, string][] = [
    ["s", "dalla natura del versante: geologia, pendenza e frane del passato"],
    ["m", "dalla spinta della pioggia recente"],
    ["e", "dalle scosse sismiche recenti"],
    ["f", "dall'effetto di incendi recenti"],
    ["h", "dalla pericolosità idraulica della zona"],
  ];
  const sorted = [...drivers].sort((x, y) => b[y[0]] - b[x[0]]);
  const top = sorted[0];
  const parts: string[] = [];
  if (top && b[top[0]] > 0.05) {
    parts.push(`Il punteggio nasce soprattutto ${top[1]}.`);
  }
  if (b.m < 0.05) {
    parts.push(
      "Non c'è pioggia in corso: il punteggio riflette la fragilità " +
        "storica del versante, non un pericolo in atto.",
    );
  } else if (b.m < 0.2) {
    parts.push("La pioggia recente incide poco.");
  } else if (b.m < 0.5) {
    parts.push("La pioggia recente contribuisce in modo moderato.");
  } else {
    parts.push("La pioggia recente sta spingendo il rischio verso l'alto.");
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

interface BreakdownView {
  s: number;
  m: number;
  e: number;
  f: number;
  h: number;
}

function pickScalar(
  factors: Record<string, unknown>,
  key: keyof BreakdownView,
): number {
  const value = factors[key];
  return typeof value === "number" ? value : 0;
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
      .getCellBreakdown(cellId, ctrl.signal)
      .then(setData)
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        if (err instanceof ApiClientError) {
          setError(`Errore ${err.status}: ${err.message}`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("errore sconosciuto");
        }
      });
    return () => ctrl.abort();
  }, [cellId]);

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
  const breakdown: BreakdownView = {
    s: pickScalar(factors, "s"),
    m: pickScalar(factors, "m"),
    e: pickScalar(factors, "e"),
    f: pickScalar(factors, "f"),
    h: pickScalar(factors, "h"),
  };
  const level = asLevel(data.level);

  const COMP_COLORS: Record<keyof BreakdownView, string> = {
    s: "#2456a3",
    m: "#e8720c",
    e: "#7a5cc0",
    f: "#b34a04",
    h: "#2a8fb5",
  };
  const COMP_LABELS: Record<keyof BreakdownView, string> = {
    s: "S statico",
    m: "M meteo",
    e: "E sismico",
    f: "F post-incendio",
    h: "H idrologico",
  };

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
      <p className="plain-summary">{plainSummary(breakdown, props.exposure)}</p>
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
        {(Object.keys(COMP_LABELS) as (keyof BreakdownView)[]).map((k) => (
          <div className="comp-bar" key={k}>
            <span>{COMP_LABELS[k]}</span>
            <span className="track">
              <span
                className="fill"
                style={{
                  width: `${Math.min(100, breakdown[k] * 100)}%`,
                  background: COMP_COLORS[k],
                }}
              />
            </span>
            <span className="val">{breakdown[k].toFixed(3)}</span>
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
