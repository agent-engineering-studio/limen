import { useEffect, useState } from "react";

import { defaultApiClient, ApiClientError } from "../lib/api-client";
import { RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { CellBreakdownResponse, RiskLevel } from "../types";

export interface CellPopupProps {
  readonly cellId: string | null;
  readonly onDismiss?: () => void;
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
  const briefing = (data.explanation["briefing_it"] as string | undefined) ?? null;
  const level = asLevel(data.level);

  return (
    <aside className="popup-card" role="dialog" aria-labelledby="cell-id">
      <h3 id="cell-id">
        Cella {data.cell_id} —{" "}
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {data.score.toFixed(2)}
        </span>{" "}
        ({RISK_LABEL_IT_BY_LEVEL[level]})
      </h3>
      <p style={{ fontSize: 11, color: "#5e6473", margin: 0 }}>
        modello {data.pipeline_version} · orizzonte {data.horizon} ·{" "}
        {new Date(data.computed_at).toLocaleString("it-IT")}
      </p>
      <dl className="popup-grid" style={{ margin: "8px 0 0 0" }}>
        <dt>S (statico)</dt>
        <dd>{breakdown.s.toFixed(3)}</dd>
        <dt>M (meteo)</dt>
        <dd>{breakdown.m.toFixed(3)}</dd>
        <dt>E (sismico)</dt>
        <dd>{breakdown.e.toFixed(3)}</dd>
        <dt>F (post-incendio)</dt>
        <dd>{breakdown.f.toFixed(3)}</dd>
        <dt>H (idrologico)</dt>
        <dd>{breakdown.h.toFixed(3)}</dd>
      </dl>
      {briefing ? (
        <p className="popup-briefing">{briefing}</p>
      ) : (
        <p className="popup-briefing" style={{ color: "#5e6473" }}>
          Briefing non ancora generato per questa cella.
        </p>
      )}
      {onDismiss ? (
        <button type="button" onClick={onDismiss} style={{ marginTop: 8 }}>
          chiudi
        </button>
      ) : null}
    </aside>
  );
}

export default CellPopup;
