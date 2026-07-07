import { useEffect, useMemo, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { AlertItem } from "../types";

export interface CellSelection {
  cellId: string;
  lon: number | null;
  lat: number | null;
}

export interface RegionGroup {
  aoiId: string;
  name: string;
  maxScore: number;
  maxLevel: AlertItem["level"];
  cells: AlertItem[];
}

/** (row, col) della griglia dal cell_id "aoi|row|col" — per l'ordinamento. */
function cellIndex(cellId: string): [number, number] {
  const parts = cellId.split("|");
  return [Number(parts[1] ?? 0), Number(parts[2] ?? 0)];
}

/** Group per-cell alerts by region, worst first — pure, unit-tested. */
export function groupByRegion(items: AlertItem[]): RegionGroup[] {
  const by = new Map<string, AlertItem[]>();
  for (const it of items) {
    const key = it.aoi_id ?? "—";
    const list = by.get(key) ?? [];
    list.push(it);
    by.set(key, list);
  }
  const groups: RegionGroup[] = [];
  for (const [aoiId, cells] of by) {
    const worst = [...cells].sort((a, b) => b.score - a.score)[0];
    // Dentro la regione le celle sono in ordine di indice di griglia
    // (riga, colonna): stabile e prevedibile da un giro all'altro.
    cells.sort((a, b) => {
      const [ra, ca] = cellIndex(a.cell_id);
      const [rb, cb] = cellIndex(b.cell_id);
      return ra - rb || ca - cb;
    });
    if (!worst) continue;
    groups.push({
      aoiId,
      name: aoiId.replace(/^it-/, "").replace(/-/g, " "),
      maxScore: worst.score,
      maxLevel: worst.level,
      cells,
    });
  }
  groups.sort((a, b) => b.maxScore - a.maxScore);
  return groups;
}

export interface RegionAccordionProps {
  readonly onCellSelect?: (sel: CellSelection) => void;
  readonly selectedCellId?: string | null;
}

/**
 * Region-grouped view of the latest per-cell alerts (deduped, worst
 * first). Native <details> keeps the sidebar scannable: the region row
 * is the summary, the cells expand on demand.
 */
export function RegionAccordion(props: RegionAccordionProps): JSX.Element {
  const { onCellSelect, selectedCellId } = props;
  const [items, setItems] = useState<AlertItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getAlerts({ threshold: "Moderate", sinceHours: 72, limit: 500 }, ctrl.signal)
      .then((resp) => setItems(resp.items))
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted)
          setError(err instanceof Error ? err.message : String(err));
      });
    return () => ctrl.abort();
  }, []);

  const groups = useMemo(() => (items ? groupByRegion(items) : []), [items]);

  return (
    <section className="alert-list region-accordion" aria-label="Celle per regione">
      <h2>Celle sopra soglia · 72h</h2>
      {error ? (
        <p className="panel-error">{error}</p>
      ) : items === null ? (
        <p>caricamento…</p>
      ) : groups.length === 0 ? (
        <p className="alert-meta">
          Nessuna cella Moderate o superiore nelle ultime 72 ore.
        </p>
      ) : (
        groups.map((g, i) => (
          <details key={g.aoiId} className="region-group" open={i === 0}>
            <summary>
              <span
                className="alert-level-bar"
                style={{ background: RISK_COLOR_BY_LEVEL[g.maxLevel] }}
                aria-hidden
              />
              <span className="region-name">{g.name}</span>
              <span className="region-meta">
                {g.cells.length} {g.cells.length === 1 ? "cella" : "celle"} ·
                max <span className="mono">{g.maxScore.toFixed(2)}</span>
              </span>
            </summary>
            <ul>
              {g.cells.slice(0, 30).map((it) => (
                <li key={it.cell_id}>
                  <button
                    type="button"
                    className={`cell-row ${selectedCellId === it.cell_id ? "on" : ""}`}
                    onClick={() =>
                      onCellSelect?.({
                        cellId: it.cell_id,
                        lon: it.lon ?? null,
                        lat: it.lat ?? null,
                      })
                    }
                  >
                    <span
                      className="cell-dot"
                      style={{ background: RISK_COLOR_BY_LEVEL[it.level] }}
                      aria-hidden
                    />
                    <span
                      className="cell-place"
                      title={`riquadro di griglia 1 km — riga ${cellIndex(it.cell_id)[0]}, colonna ${cellIndex(it.cell_id)[1]}`}
                    >
                      {it.place ?? `riquadro ${it.cell_id.split("|").slice(1).join("·")}`}
                      {it.exposure ? (
                        <span className="exposure-chip">🏠 {it.exposure}</span>
                      ) : null}
                    </span>
                    <span className="mono cell-score">
                      {it.score.toFixed(2)}
                    </span>
                    <span className="cell-level">
                      {RISK_LABEL_IT_BY_LEVEL[it.level]}
                    </span>
                  </button>
                </li>
              ))}
              {g.cells.length > 30 ? (
                <li className="alert-meta cell-more">
                  … e altre {g.cells.length - 30} celle
                </li>
              ) : null}
            </ul>
          </details>
        ))
      )}
    </section>
  );
}

export default RegionAccordion;
