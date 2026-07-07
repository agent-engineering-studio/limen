import { useEffect, useMemo, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { AlertItem } from "../types";

export interface CellSelection {
  cellId: string;
  lon: number | null;
  lat: number | null;
  score?: number;
  priority?: number | null;
  exposure?: string | null;
  place?: string | null;
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
  const prio = (c: AlertItem): number => c.priority ?? c.score;
  for (const [aoiId, cells] of by) {
    // Ordinamento per PRIORITÀ (rischio x esposizione): la cella che
    // minaccia un abitato o una strada viene prima di una identica su
    // un versante isolato. L'indice di griglia resta nel tooltip.
    cells.sort((a, b) => prio(b) - prio(a));
    const worst = cells[0];
    if (!worst) continue;
    groups.push({
      aoiId,
      name: aoiId.replace(/^it-/, "").replace(/-/g, " "),
      maxScore: prio(worst),
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
/** Analisi AI della regione, caricata solo quando l'operatore la apre. */
function RegionalAnalysis({ aoiId }: { aoiId: string }): JSX.Element {
  const [text, setText] = useState<string | null | undefined>(undefined);

  const load = (): void => {
    if (text !== undefined) return;
    setText(null);
    defaultApiClient
      .getLatestRisk(aoiId)
      .then((resp) => setText(resp.briefing_it ?? ""))
      .catch(() => setText(""));
  };

  return (
    <details className="regional-analysis" onToggle={load}>
      <summary>Analisi regionale (AI)</summary>
      {text === null || text === undefined ? (
        <p className="alert-meta">caricamento…</p>
      ) : text === "" ? (
        <p className="alert-meta">
          Nessuna analisi disponibile per questa regione (viene generata
          quando ci sono celle sopra soglia).
        </p>
      ) : (
        <>
          <p className="regional-analysis-text">{text}</p>
          <p className="popup-note">
            Testo generato da un modello linguistico sull'intera regione; i
            numeri citati vengono dalla valutazione deterministica.
          </p>
        </>
      )}
    </details>
  );
}

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
      <p className="alert-meta" style={{ margin: "0 0 6px" }}>
        Ordinate per priorità <span className="mono">P</span> = rischio ×
        esposizione (abitati, strade). Il colore segue il rischio della
        legenda.
      </p>
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
                priorità max <span className="mono">{g.maxScore.toFixed(2)}</span>
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
                        score: it.score,
                        priority: it.priority,
                        exposure: it.exposure,
                        place: it.place,
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
                      {(it.exposure ?? "").split(", ").filter(Boolean).map((tag) => (
                        <span key={tag} className="exposure-chip">
                          {tag.startsWith("infrastrutture") ? "🛣" : "🏠"} {tag}
                        </span>
                      ))}
                    </span>
                    <span className="mono cell-score">
                      {it.score.toFixed(2)}
                    </span>
                    <span
                      className="mono cell-prio"
                      title="priorità = rischio × esposizione: ordina la lista, può superare 1"
                    >
                      P {(it.priority ?? it.score).toFixed(2)}
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
            <RegionalAnalysis aoiId={g.aoiId} />
          </details>
        ))
      )}
    </section>
  );
}

export default RegionAccordion;
