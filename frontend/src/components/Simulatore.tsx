// Il simulatore delle frane: la stessa formula del motore, con quattro
// cursori, dentro la guida (marcatore `<!-- componente: simulatore -->`).

import { useState } from "react";
import type { JSX } from "react";

import { RISK_CLASSES } from "../lib/risk-colors";

// Parametri di produzione (YAML 2026-07): pesi top-level, sotto-pesi di M,
// sigmoidi API/suolo, bonus pioggia-su-neve, soglie Caine per macroregione.
const W = { s: 0.35, m: 0.4, h: 0.03 };
const MW = { caine: 0.45, api: 0.3, soil: 0.25 };
const SNOW = { minDepthM: 0.05, scaleMm: 30, weight: 0.15 };

export interface SimCell {
  id: string;
  name: string;
  detail: string;
  s: number;
  caine: { alpha: number; beta: number };
  flood: number;
}

export const ALPINE: SimCell = {
    id: "alpine",
    name: "⛰ Versante alpino (Valle d'Aosta)",
    detail: "pendenza 47.9° · 8 frane storiche vicine · zona PAI P4",
    s: 0.95,
    caine: { alpha: 6.37, beta: 0.512 }, // nord Italia
    flood: 0.8,
};

export const PLAIN: SimCell = {
    id: "plain",
    name: "🌾 Pianura (Puglia, Tavoliere)",
    detail: "pendenza 1.5° · nessuna frana storica · fuori zone PAI",
    s: 0.06,
    caine: { alpha: 8.75, beta: 0.645 }, // sud Italia
    flood: 0,
};

export const SIM_CELLS: readonly SimCell[] = [ALPINE, PLAIN];

const sigmoid = (z: number): number => 1 / (1 + Math.exp(-z));

export interface SimResult {
  caine: number;
  api: number;
  soil: number;
  snow: number;
  m: number;
  risk: number;
  classIndex: number;
}

// La stessa aggregazione del motore, per un evento di pioggia uniforme di 24h.
export function simulate(
  cell: SimCell,
  rain24Mm: number,
  api30Mm: number,
  soilMoisture: number,
  snowDepthM: number,
): SimResult {
  const intensity = rain24Mm / 24;
  const threshold = cell.caine.alpha * Math.pow(24, -cell.caine.beta);
  const caine =
    rain24Mm > 0
      ? Math.min(1, Math.max(0, Math.log10(intensity / threshold)))
      : 0;
  const api = sigmoid((api30Mm - 80) / 60);
  const soil = sigmoid(12 * (soilMoisture - 0.3));
  const snow =
    snowDepthM >= SNOW.minDepthM ? Math.min(1, rain24Mm / SNOW.scaleMm) : 0;
  const m = Math.min(
    1,
    MW.caine * caine + MW.api * api + MW.soil * soil + SNOW.weight * snow,
  );
  const risk = Math.min(1, W.s * cell.s + W.m * m + W.h * cell.flood);
  const classIndex = RISK_CLASSES.filter(
    (c, i) => i > 0 && risk >= c.range[0],
  ).length;
  return { caine, api, soil, snow, m, risk, classIndex };
}

function verdict(cell: SimCell, r: SimResult): string {
  const cls = (RISK_CLASSES[r.classIndex]?.label ?? "").toLowerCase();
  if (cell.id === "plain" && r.classIndex >= 2) {
    return `Rischio ${cls}: in pianura succede solo con eventi davvero estremi.`;
  }
  if (cell.id === "plain") {
    return `Rischio ${cls}. Stessa pioggia del versante, ma qui il terreno non è predisposto: l'acqua da sola non basta a fare una frana. Questo è il cuore del metodo.`;
  }
  if (r.classIndex >= 3) {
    return `Rischio ${cls}: terreno predisposto E pioggia sufficiente insieme. È la combinazione che fa scattare l'allerta.`;
  }
  if (r.classIndex === 2) {
    return `Rischio ${cls}: la condizione di base di un versante così fragile — sorveglianza ordinaria. È la pioggia a spingerlo più su.`;
  }
  return `Rischio ${cls}: il versante è predisposto, ma senza abbastanza pioggia resta tranquillo. Serve l'innesco.`;
}

export default function Simulatore(): JSX.Element {
  const [cellId, setCellId] = useState("alpine");
  const [rain, setRain] = useState(40);
  const [api, setApi] = useState(120);
  const [soil, setSoil] = useState(35);
  const [snow, setSnow] = useState(0);

  const cell = SIM_CELLS.find((c) => c.id === cellId) ?? ALPINE;
  const r = simulate(cell, rain, api, soil / 100, snow / 100);

  return (
      <section className="sim" aria-label="Simulatore del rischio">
        <h3>🌧 Prova tu: la stessa pioggia su due Italie diverse</h3>
        <p className="exp-note">
          Questo simulatore usa la stessa identica formula del sistema in
          produzione. Scegli il terreno, regola la pioggia, guarda cosa
          succede al rischio.
        </p>
        <div className="sim-cells" role="group" aria-label="Scegli il terreno">
          {SIM_CELLS.map((c) => (
            <button
              key={c.id}
              className={c.id === cellId ? "sel" : ""}
              onClick={() => setCellId(c.id)}
            >
              {c.name}
              <small>{c.detail}</small>
            </button>
          ))}
        </div>

        <div className="sim-ctrl">
          <label htmlFor="sim-rain">Pioggia nelle ultime 24 ore</label>
          <input
            id="sim-rain"
            type="range"
            min={0}
            max={150}
            value={rain}
            onChange={(e) => setRain(Number(e.target.value))}
          />
          <output>{rain} mm</output>
        </div>
        <div className="sim-ctrl">
          <label htmlFor="sim-api">Pioggia caduta nell&apos;ultimo mese</label>
          <input
            id="sim-api"
            type="range"
            min={0}
            max={300}
            value={api}
            onChange={(e) => setApi(Number(e.target.value))}
          />
          <output>{api} mm</output>
        </div>
        <div className="sim-ctrl">
          <label htmlFor="sim-soil">Quanto è già bagnato il terreno</label>
          <input
            id="sim-soil"
            type="range"
            min={0}
            max={60}
            value={soil}
            onChange={(e) => setSoil(Number(e.target.value))}
          />
          <output>{(soil / 100).toFixed(2)}</output>
        </div>
        <div className="sim-ctrl">
          <label htmlFor="sim-snow">Neve al suolo</label>
          <input
            id="sim-snow"
            type="range"
            min={0}
            max={100}
            value={snow}
            onChange={(e) => setSnow(Number(e.target.value))}
          />
          <output>{snow} cm</output>
        </div>

        <div className="sim-kpis">
          <div>
            <span>Innesco meteo (M)</span>
            <b>{r.m.toFixed(2)}</b>
          </div>
          <div>
            <span>Predisposizione (S)</span>
            <b>{cell.s.toFixed(2)}</b>
          </div>
          <div className="sim-risk">
            <span>Rischio</span>
            <b>{r.risk.toFixed(2)}</b>
          </div>
        </div>

        <div className="sim-ladder" role="img" aria-label="Classe di rischio">
          {RISK_CLASSES.map((c, i) => (
            <div
              key={c.level}
              className={i === r.classIndex ? "on" : ""}
              style={{ background: c.color }}
            >
              {c.label}
            </div>
          ))}
        </div>
        <p className="sim-verdict">{verdict(cell, r)}</p>
      </section>
  );
}
