import { useEffect, useMemo, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { AlertItem } from "../types";
import CellTrendSparkline from "./CellTrendSparkline";

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

export interface ComuneGroup {
  place: string | null; // null = cells without a municipality
  label: string;
  cells: AlertItem[];
  minScore: number;
  maxScore: number;
  worstLevel: AlertItem["level"]; // level of the highest-scoring cell
  exposedCount: number;
}

/** Sub-group a region's cells by comune, worst first — pure, unit-tested.
 * Cells without a `place` land in a single "fuori comune" bucket. */
export function groupByComune(cells: AlertItem[]): ComuneGroup[] {
  const prio = (c: AlertItem): number => c.priority ?? c.score;
  const by = new Map<string, AlertItem[]>();
  for (const c of cells) {
    const key = c.place ?? "";
    const list = by.get(key) ?? [];
    list.push(c);
    by.set(key, list);
  }
  const groups: ComuneGroup[] = [];
  for (const [key, list] of by) {
    list.sort((a, b) => prio(b) - prio(a));
    const top = [...list].sort((a, b) => b.score - a.score)[0]!;
    const scores = list.map((c) => c.score);
    groups.push({
      place: key === "" ? null : key,
      label: key === "" ? "Fuori comune / griglia" : key,
      cells: list,
      minScore: Math.min(...scores),
      maxScore: Math.max(...scores),
      worstLevel: top.level,
      exposedCount: list.filter((c) => c.exposure).length,
    });
  }
  const maxPrio = (cg: ComuneGroup): number => Math.max(...cg.cells.map(prio));
  groups.sort((a, b) => maxPrio(b) - maxPrio(a));
  return groups;
}

export interface RegionAccordionProps {
  readonly onCellSelect?: (sel: CellSelection) => void;
  readonly selectedCellId?: string | null;
}

/** One comune: collapsed summary; cells (with 72h trend) render only when open
 * so the per-cell history fetch is lazy. */
function ComuneSection({
  cg,
  selectedCellId,
  onCellSelect,
}: {
  cg: ComuneGroup;
  selectedCellId?: string | null;
  onCellSelect?: (sel: CellSelection) => void;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="comune-group"
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>
        <span
          className="cell-dot"
          style={{ background: RISK_COLOR_BY_LEVEL[cg.worstLevel] }}
          aria-hidden
        />
        <span className="comune-name">{cg.label}</span>
        <span className="comune-headline">{RISK_LABEL_IT_BY_LEVEL[cg.worstLevel]}</span>
        <span className="comune-meta">
          {cg.cells.length} {cg.cells.length === 1 ? "cella" : "celle"} ·{" "}
          {cg.minScore.toFixed(2)}–{cg.maxScore.toFixed(2)}
          {cg.exposedCount > 0 ? ` · ${cg.exposedCount} 🏠🛣` : ""}
        </span>
      </summary>
      {open ? (
        <ul>
          {cg.cells.map((it) => (
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
                  riquadro {cellIndex(it.cell_id)[0]}·{cellIndex(it.cell_id)[1]}
                  {(it.exposure ?? "").split(", ").filter(Boolean).map((tag) => (
                    <span key={tag} className="exposure-chip">
                      {/^(infrastrutture|statale|autostrada)/.test(tag) ? "🛣" : tag.startsWith("ferrovia") ? "🚆" : "🏠"} {tag}
                    </span>
                  ))}
                </span>
                <span className="mono cell-score">{it.score.toFixed(2)}</span>
                <span className="cell-level">{RISK_LABEL_IT_BY_LEVEL[it.level]}</span>
              </button>
              <CellTrendSparkline cellId={it.cell_id} />
            </li>
          ))}
        </ul>
      ) : null}
    </details>
  );
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
        Prima le celle il cui eventuale movimento toccherebbe case o strade
        (🏠 🛣), poi le altre. Il numero è il rischio della legenda.
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
        groups.map((g, i) => {
          const comuni = groupByComune(g.cells);
          const esposte = g.cells.filter((c) => c.exposure).length;
          return (
            <details key={g.aoiId} className="region-group" open={i === 0}>
              <summary>
                <span
                  className="alert-level-bar"
                  style={{ background: RISK_COLOR_BY_LEVEL[g.maxLevel] }}
                  aria-hidden
                />
                <span className="region-name">{g.name}</span>
                <span className="region-meta">
                  {comuni.length} {comuni.length === 1 ? "comune" : "comuni"} ·{" "}
                  {g.cells.length} {g.cells.length === 1 ? "cella" : "celle"}
                  {esposte > 0 ? ` · ${esposte} presso abitati/strade` : ""}
                </span>
              </summary>
              {comuni.map((cg) => (
                <ComuneSection
                  key={cg.label}
                  cg={cg}
                  selectedCellId={selectedCellId}
                  onCellSelect={onCellSelect}
                />
              ))}
              <RegionalAnalysis aoiId={g.aoiId} />
            </details>
          );
        })
      )}
    </section>
  );
}

export default RegionAccordion;
