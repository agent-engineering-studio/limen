// Sparkline dell'andamento rischio di una cella (#41): passato 72h (solido) +
// previsione 72h (tratteggiato), con marcatore «ora». Fetch lazy (montata solo
// quando il comune è aperto) + cache per cella. role=img + alt, mai solo-colore.

import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { CellHistoryPoint, CellHistoryResponse } from "../types";

// Cache per (cella, pericolo): riaprire un comune non rifà la fetch. La
// chiave include il pericolo perché la cache è di modulo e sopravvive allo
// smontaggio: senza, un cambio di pericolo mostrerebbe per sempre la serie
// dell'altro.
const _cache = new Map<string, CellHistoryResponse>();
const cacheKey = (cellId: string, hazard: string): string => `${cellId}|${hazard}`;

const W = 200;
const H = 40;
const PAD = 4;

interface Pt {
  x: number;
  y: number;
}

function toPixels(points: CellHistoryPoint[], t0: number, t1: number): Pt[] {
  const span = t1 - t0 || 1;
  return points.map((p) => {
    const tx = new Date(p.t).getTime();
    return {
      x: PAD + ((tx - t0) / span) * (W - 2 * PAD),
      y: PAD + (1 - Math.min(1, Math.max(0, p.score))) * (H - 2 * PAD),
    };
  });
}

function path(pts: Pt[]): string {
  return pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

export default function CellTrendSparkline({ cellId }: { cellId: string }): JSX.Element {
  const { selected: hazard } = useHazard();
  const cached = _cache.get(cacheKey(cellId, hazard)) ?? null;
  const [data, setData] = useState<CellHistoryResponse | null>(cached);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const hit = _cache.get(cacheKey(cellId, hazard)) ?? null;
    setData(hit);
    setFailed(false);
    if (hit) return;
    const ctrl = new AbortController();
    defaultApiClient
      .getCellHistory(cellId, 72, ctrl.signal, hazard)
      .then((resp) => {
        _cache.set(cacheKey(cellId, hazard), resp);
        setData(resp);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setFailed(true);
      });
    return () => ctrl.abort();
  }, [cellId, hazard]);

  if (failed) return <span className="trend-note">andamento non disponibile</span>;
  if (!data) return <span className="trend-note">andamento…</span>;

  const all = [...data.observed, ...data.forecast];
  if (all.length === 0) {
    return <span className="trend-note">storico non ancora disponibile</span>;
  }
  const times = all.map((p) => new Date(p.t).getTime());
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const obs = toPixels(data.observed, t0, t1);
  const fc = toPixels(data.forecast, t0, t1);
  // «ora» = confine tra osservato e previsione (ultimo osservato, o primo forecast).
  const nowX =
    obs.length > 0 ? obs[obs.length - 1]!.x : fc.length > 0 ? fc[0]!.x : null;

  const lastObs = data.observed[data.observed.length - 1];
  const lastFc = data.forecast[data.forecast.length - 1];
  const alt =
    `Andamento rischio: ${data.observed.length} punti osservati` +
    (lastObs ? ` (ultimo ${lastObs.score.toFixed(2)})` : "") +
    `, ${data.forecast.length} previsti` +
    (lastFc ? ` (a +72h ${lastFc.score.toFixed(2)})` : "");

  return (
    <svg className="cell-trend" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={alt}>
      <title>{alt}</title>
      {nowX !== null ? (
        <line x1={nowX} y1={0} x2={nowX} y2={H} stroke="#c3c7cf" strokeDasharray="2 2" />
      ) : null}
      {obs.length > 0 ? <path d={path(obs)} fill="none" stroke="#5e6473" strokeWidth={1.5} /> : null}
      {fc.length > 0 ? (
        <path
          d={path(fc)}
          fill="none"
          stroke="#1f77b4"
          strokeWidth={1.5}
          strokeDasharray="3 2"
        />
      ) : null}
    </svg>
  );
}
