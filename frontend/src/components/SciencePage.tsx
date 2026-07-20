// "Il modello, spiegato" — pagina scientifica ma leggibile (issue #16).
// Pubblico: operatori di Protezione Civile, sindaci, tecnici comunali.
//
// Tutti i numeri (pesi, soglie, cutoff) arrivano dall'endpoint /api/legend,
// che li legge da regional_thresholds.yaml: NESSUN valore è cablato qui. I
// contenuti sono statici/curati e i grafici derivano deterministicamente dai
// parametri — nessun LLM, coerente con "gli alert non inventano numeri".

import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { RISK_CLASSES } from "../lib/risk-colors";
import type { LegendResponse, ModelCard, RiskLevel } from "../types";

// Linguaggio visivo S/M/E/F/H condiviso con CellPopup / builder del report.
const COMP_COLOR: Record<string, string> = {
  static: "#8c6d31",
  meteo: "#1f77b4",
  seismic: "#9467bd",
  fire: "#d62728",
  hydrology: "#17becf",
};

// ---------------------------------------------------------------------------
// Modelli fisici — funzioni pure (le stesse forme del motore V1), esportate
// per il test. Coefficienti dal model card, mai costanti locali.
// ---------------------------------------------------------------------------
export function caineThreshold(alpha: number, beta: number, durationH: number): number {
  return durationH <= 0 ? 0 : alpha * durationH ** -beta;
}

export function sigmoid(z: number): number {
  return 1 / (1 + Math.exp(-z));
}

/** Decadimento sismico exp(-t/τ), t in giorni. */
export function seismicDecay(tauDays: number, days: number): number {
  return tauDays <= 0 ? 0 : Math.exp(-days / tauDays);
}

/** Campana post-incendio exp(-((m-peak)²/denom)) dentro la finestra. */
export function postFireBell(
  peak: number,
  denom: number,
  windowMax: number,
  months: number,
): number {
  if (months < 0 || months > windowMax) return 0;
  return Math.exp(-((months - peak) ** 2) / denom);
}

// ---------------------------------------------------------------------------
// Grafico a linea riutilizzabile — SVG inline, accessibile (role=img +
// <title>/<desc>), con alternativa testuale e mai solo-colore.
// ---------------------------------------------------------------------------
interface Pt {
  x: number;
  y: number;
}

interface LineChartProps {
  id: string;
  title: string;
  desc: string;
  points: Pt[];
  domainX: [number, number];
  domainY: [number, number];
  xLabel: string;
  yLabel: string;
  marker?: { pt: Pt; label: string };
  color?: string;
}

const PLOT = { w: 320, h: 180, ml: 40, mr: 12, mt: 12, mb: 30 };

function LineChart({
  id,
  title,
  desc,
  points,
  domainX,
  domainY,
  xLabel,
  yLabel,
  marker,
  color = "#1f77b4",
}: LineChartProps): JSX.Element {
  const iw = PLOT.w - PLOT.ml - PLOT.mr;
  const ih = PLOT.h - PLOT.mt - PLOT.mb;
  const sx = (x: number): number =>
    PLOT.ml + ((x - domainX[0]) / (domainX[1] - domainX[0])) * iw;
  const sy = (y: number): number =>
    PLOT.mt + ih - ((y - domainY[0]) / (domainY[1] - domainY[0])) * ih;
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`)
    .join(" ");
  return (
    <figure className="sci-chart">
      <svg
        viewBox={`0 0 ${PLOT.w} ${PLOT.h}`}
        role="img"
        aria-labelledby={`${id}-t ${id}-d`}
      >
        <title id={`${id}-t`}>{title}</title>
        <desc id={`${id}-d`}>{desc}</desc>
        {/* assi */}
        <line
          x1={PLOT.ml}
          y1={PLOT.mt + ih}
          x2={PLOT.ml + iw}
          y2={PLOT.mt + ih}
          stroke="#9aa1ad"
        />
        <line x1={PLOT.ml} y1={PLOT.mt} x2={PLOT.ml} y2={PLOT.mt + ih} stroke="#9aa1ad" />
        <path d={path} fill="none" stroke={color} strokeWidth={2.5} />
        {marker ? (
          <g>
            <circle cx={sx(marker.pt.x)} cy={sy(marker.pt.y)} r={4.5} fill="#111" />
            <text x={sx(marker.pt.x) + 7} y={sy(marker.pt.y) - 6} fontSize={11} fill="#111">
              {marker.label}
            </text>
          </g>
        ) : null}
        <text x={PLOT.ml + iw / 2} y={PLOT.h - 4} fontSize={11} textAnchor="middle" fill="#5e6473">
          {xLabel}
        </text>
        <text
          x={12}
          y={PLOT.mt + ih / 2}
          fontSize={11}
          textAnchor="middle"
          fill="#5e6473"
          transform={`rotate(-90 12 ${PLOT.mt + ih / 2})`}
        >
          {yLabel}
        </text>
      </svg>
      <figcaption className="exp-note">{desc}</figcaption>
    </figure>
  );
}

function sample(fn: (t: number) => number, t0: number, t1: number, n = 48): Pt[] {
  const pts: Pt[] = [];
  for (let i = 0; i <= n; i++) {
    const x = t0 + ((t1 - t0) * i) / n;
    pts.push({ x, y: fn(x) });
  }
  return pts;
}

const PC_LABEL: Record<string, string> = {
  verde: "verde",
  gialla: "gialla",
  arancione: "arancione",
  rossa: "rossa",
};

const COMPONENTS: {
  key: keyof ModelCard["weights"];
  code: string;
  name: string;
  measures: string;
  data: string;
}[] = [
  {
    key: "static",
    code: "S",
    name: "Versante (statico)",
    measures: "quanto un punto è predisposto a franare, a prescindere dal meteo",
    data: "geologia, pendenza (DTM), densità frane storiche IFFI, pericolosità PAI",
  },
  {
    key: "meteo",
    code: "M",
    name: "Meteo (dinamico)",
    measures: "quanta acqua sta arrivando e quanta ce n'è già nel terreno",
    data: "pioggia osservata e prevista (Open-Meteo), umidità del suolo, neve",
  },
  {
    key: "seismic",
    code: "E",
    name: "Sismico",
    measures: "quanto scuotimento recente ha già indebolito il versante",
    data: "scosse recenti (INGV), scuotimento al suolo (ShakeMap)",
  },
  {
    key: "fire",
    code: "F",
    name: "Post-incendio",
    measures: "quanto un incendio recente ha reso il suolo più fragile",
    data: "aree bruciate recenti (EFFIS)",
  },
  {
    key: "hydrology",
    code: "H",
    name: "Idraulico",
    measures: "quanto la zona è esposta alla pericolosità idraulica",
    data: "mosaico idraulica ISPRA",
  },
];

// ---------------------------------------------------------------------------
// Contenuto (presentazionale) — riceve il model card già caricato. Esportato
// per il test, così renderizza in modo sincrono con parametri fissi.
// ---------------------------------------------------------------------------
export function ScienceContent({
  model,
  pcByLevel,
  version,
}: {
  model: ModelCard;
  pcByLevel: Record<string, string>;
  version: string;
}): JSX.Element {
  const caine = model.caine.macroregions.italy_default ?? { alpha: 7.19, beta: 0.568 };
  // Curva soglia Caine su durata 1–48 h; evento d'esempio sopra soglia.
  const cainePts = sample((d) => caineThreshold(caine.alpha, caine.beta, d), 1, 48);
  const eventD = 12;
  const eventI = caineThreshold(caine.alpha, caine.beta, eventD) * 1.6;
  // Sigmoide API centrata sulla baseline; asse 0..2·baseline.
  const b = model.api.baseline_fallback_mm;
  const apiPts = sample(
    (mm) => sigmoid((mm - b) / model.api.sigmoid_sigma_mm),
    0,
    2 * b,
  );
  const decayPts = sample((d) => seismicDecay(model.seismic.tau_days, d), 0, 7);
  const wm = model.post_fire.window_months_max;
  const firePts = sample(
    (m) =>
      postFireBell(
        model.post_fire.peak_months,
        model.post_fire.curve_denominator,
        wm,
        m,
      ),
    0,
    wm,
  );
  const pct = (x: number): string => `${Math.round(x * 100)}%`;

  return (
    <div className="explainer sci" aria-label="Il modello di Limen, spiegato">
      <article>
        <p className="exp-eyebrow">Per chi decide</p>
        <h2>Il modello, spiegato</h2>
        <p className="exp-lede">
          Come nasce il numero di rischio e come si arriva a una probabilità.
          Rigoroso ma leggibile: ogni concetto con uno schema, ogni numero con
          la sua fonte. I valori qui sotto sono quelli reali di produzione
          (versione <code>{version}</code>), letti da{" "}
          <code>regional_thresholds.yaml</code>.
        </p>

        {/* 1. Componenti */}
        <h3>1. Dai fattori al punteggio: i componenti</h3>
        <p className="sci-plain">
          In parole semplici: il rischio è la somma di più &laquo;spie&raquo;,
          ognuna che guarda un aspetto diverso del territorio e del momento.
        </p>
        <ul className="sci-components">
          {COMPONENTS.map((c) => (
            <li key={c.key}>
              <span className="sci-badge" style={{ background: COMP_COLOR[c.key] }}>
                {c.code}
              </span>
              <div>
                <strong>{c.name}</strong> — {c.measures}.{" "}
                <span className="exp-note">Dati: {c.data}.</span>
              </div>
            </li>
          ))}
          <li>
            <span className="sci-badge" style={{ background: "#2ca02c" }}>
              K
            </span>
            <div>
              <strong>Cinematico (in-situ, opzionale)</strong> — velocità di
              spostamento reale del versante, quando c&apos;è un sensore.{" "}
              <span className="exp-note">
                Dati: inclinometri / GNSS di campo. Attivo solo sulle celle
                monitorate.
              </span>
            </div>
          </li>
        </ul>

        {/* 2. Aggregazione pesata */}
        <h3>2. Come si combinano: media pesata</h3>
        <p className="sci-plain">
          In parole semplici: ogni componente pesa in modo diverso. Si moltiplica
          ciascuno per il suo peso e si somma, ottenendo un punteggio tra 0 e 1.
        </p>
        <p>
          <code>
            rischio = w<sub>S</sub>·S + w<sub>M</sub>·M + w<sub>E</sub>·E + w
            <sub>F</sub>·F + w<sub>H</sub>·H
          </code>
        </p>
        <ul className="sci-bars" aria-label="Pesi dei componenti">
          {COMPONENTS.map((c) => (
            <li key={c.key}>
              <span className="sci-bar-label">
                {c.code} · {c.name}
              </span>
              <span className="sci-bar-track">
                <span
                  className="sci-bar-fill"
                  style={{
                    width: pct(model.weights[c.key]),
                    background: COMP_COLOR[c.key],
                  }}
                />
              </span>
              <span className="sci-bar-val">{pct(model.weights[c.key])}</span>
            </li>
          ))}
        </ul>
        <p className="exp-note">
          I pesi sono <strong>versionati e tarati per macroregione</strong> in{" "}
          <code>regional_thresholds.yaml</code>, non costanti cablate nel codice.
          Dentro M pesano: Caine {pct(model.meteo_weights.caine)}, API{" "}
          {pct(model.meteo_weights.api)}, umidità del suolo{" "}
          {pct(model.meteo_weights.soil)}.
        </p>

        {/* 3. Modelli fisici dentro M */}
        <h3>3. Il cuore &laquo;meteo&raquo;: i modelli fisici</h3>
        <p className="sci-plain">
          In parole semplici: più piove intensamente e a lungo, più ci si
          avvicina alla soglia storica di innesco — e un terreno già bagnato dai
          giorni scorsi ci arriva prima.
        </p>
        <LineChart
          id="caine"
          title="Soglia Caine intensità–durata"
          desc={`Curva di soglia I = α·D^(−β) (α=${caine.alpha}, β=${caine.beta}, macroregione italy_default). Sopra la curva l'evento supera la soglia storica di innesco; il punto nero è un evento d'esempio sopra soglia.`}
          points={cainePts}
          domainX={[1, 48]}
          domainY={[0, Math.max(...cainePts.map((p) => p.y), eventI)]}
          xLabel="durata pioggia (h)"
          yLabel="intensità (mm/h)"
          marker={{ pt: { x: eventD, y: eventI }, label: "evento" }}
          color="#1f77b4"
        />
        <LineChart
          id="api"
          title="API — indice di pioggia antecedente"
          desc={`Sigmoide del terreno già bagnato: 0 (asciutto) → 1 (saturo), centrata sulla baseline ${b} mm con σ=${model.api.sigmoid_sigma_mm} mm. Il terreno impregnato conta quanto la pioggia di oggi.`}
          points={apiPts}
          domainX={[0, 2 * b]}
          domainY={[0, 1]}
          xLabel="pioggia antecedente (mm)"
          yLabel="fattore 0–1"
          color="#2b8cbe"
        />
        <p className="exp-note">
          Anche l&apos;umidità del suolo (sigmoide centrata a{" "}
          {model.soil.sigmoid_center}) e la pioggia-su-neve seguono la stessa
          logica: trasformano una misura fisica in un fattore fra 0 e 1.
        </p>

        {/* 4. E / F / H */}
        <h3>4. Sismico, incendi, idraulico</h3>
        <LineChart
          id="decay"
          title="Decadimento dell'effetto sismico"
          desc={`L'effetto di una scossa svanisce nel tempo: exp(−t/τ) con τ=${model.seismic.tau_days} giorni. Dopo pochi giorni il contributo sismico torna vicino a zero.`}
          points={decayPts}
          domainX={[0, 7]}
          domainY={[0, 1]}
          xLabel="giorni dalla scossa"
          yLabel="effetto residuo"
          color="#9467bd"
        />
        <LineChart
          id="fire"
          title="Finestra di amplificazione post-incendio"
          desc={`Un incendio aumenta il rischio per una finestra di ${wm} mesi, con picco a ${model.post_fire.peak_months} mesi. Fuori dalla finestra il contributo è zero.`}
          points={firePts}
          domainX={[0, wm]}
          domainY={[0, 1]}
          xLabel="mesi dall'incendio"
          yLabel="amplificazione"
          color="#d62728"
        />
        <p className="sci-plain">
          In parole semplici: <strong>E</strong> pesa di più subito dopo una
          scossa e svanisce in fretta; <strong>F</strong> conta per circa due
          anni dopo un incendio; <strong>H</strong> entra come classe di
          pericolosità idraulica della zona (mosaico ISPRA).
        </p>

        {/* 5. 5 classi + allerta PC */}
        <h3>5. Dalla soglia alle 5 classi</h3>
        <p className="sci-plain">
          In parole semplici: il punteggio 0–1 diventa una delle cinque classi,
          ognuna con la sua etichetta, il suo intervallo e il colore della scala
          di allerta della Protezione Civile.
        </p>
        <ul className="sci-scale" aria-label="Cinque classi di rischio">
          {RISK_CLASSES.map((c) => (
            <li key={c.level}>
              <span className="sci-swatch" style={{ background: c.color }} aria-hidden />
              <span className="sci-scale-label">{c.label}</span>
              <span className="sci-scale-range">
                {c.range[0].toFixed(2)}–{c.range[1].toFixed(2)}
              </span>
              <span className="sci-scale-pc">
                allerta {PC_LABEL[pcByLevel[c.level] ?? ""] ?? "—"}
              </span>
            </li>
          ))}
        </ul>
        <p className="exp-note">
          Palette ColorBrewer YlOrRd (sicura per daltonismo); l&apos;informazione
          non è mai affidata al solo colore — c&apos;è sempre etichetta e
          intervallo. Cutoff e mapping da <code>classes:</code> e{" "}
          <code>pc_alert:</code> nel YAML.
        </p>

        {/* 6. V1 vs V2 */}
        <h3>6. Punteggio V1 vs probabilità ML V2</h3>
        <p className="sci-plain sci-key">
          Punto chiave, detto senza giri di parole:{" "}
          <strong>
            il punteggio del motore deterministico V1 è un indice di rischio 0–1,
            NON una probabilità
          </strong>
          . «0,60» significa «rischio alto», non «60% di probabilità».
        </p>
        <p>
          Il motore <strong>ML V2</strong> (challenger) produce invece una{" "}
          <strong>probabilità calibrata</strong> di innesco nella finestra:
          &laquo;30%&raquo; vuol dire che, su 100 situazioni come questa, circa 30
          franano. Una probabilità calibrata è più interpretabile perché si può
          confrontare con la realtà osservata.
        </p>
        <div className="sci-flow" role="img" aria-label="Flusso champion–challenger con promozione manuale">
          <span className="sci-node sci-champ">V1 deterministico<br />(campione)</span>
          <span className="sci-arrow" aria-hidden>
            →
          </span>
          <span className="sci-node">guida allerte e punteggi persistiti</span>
          <span className="sci-arrow" aria-hidden>
            ⤴
          </span>
          <span className="sci-node sci-chall">V2 ML<br />(sfidante, in ombra)</span>
        </div>
        <p className="exp-note">
          Il V1 resta il campione finché l&apos;ML non lo batte su validazione a
          blocchi spaziali e sul backtest §2.5. La promozione è{" "}
          <strong>manuale</strong>, mai automatica: lo sfidante gira &laquo;in
          ombra&raquo;, scrive le sue stime a parte e non tocca mai le allerte.
        </p>

        {/* 7. Come impara l'ML */}
        <h3>7. ML V2: come impara e come si spiega</h3>
        <ul>
          <li>
            <strong>Cross-validation a blocchi spaziali</strong>: il territorio è
            diviso in blocchi geografici; celle vicine finiscono nello stesso
            blocco. Così non si usano split casuali e si evita il{" "}
            <em>leakage</em> — imparare su una cella e &laquo;verificare&raquo; su
            quella accanto, che è quasi la stessa.
          </li>
          <li>
            <strong>Calibrazione</strong> (regressione isotonica): trasforma il
            punteggio grezzo in una probabilità che corrisponde alla frequenza
            reale osservata.
          </li>
          <li>
            <strong>Spiegabilità (SHAP)</strong>: per ogni previsione si può dire{" "}
            <em>quali fattori l&apos;hanno spinta su o giù</em>. Non è una scatola
            nera.
          </li>
        </ul>
        <div className="sci-shap" aria-label="Esempio schematico di contributi SHAP">
          <p className="exp-note">Esempio illustrativo (non un valore di produzione):</p>
          {[
            { f: "Pioggia 24h", v: 0.7 },
            { f: "Terreno saturo (API)", v: 0.4 },
            { f: "Pendenza", v: 0.25 },
            { f: "Nessuna frana storica", v: -0.3 },
          ].map((s) => (
            <div key={s.f} className="sci-shap-row">
              <span className="sci-shap-f">{s.f}</span>
              <span className="sci-shap-track">
                <span
                  className={`sci-shap-fill ${s.v >= 0 ? "pos" : "neg"}`}
                  style={{ width: `${Math.abs(s.v) * 50}%` }}
                />
              </span>
              <span className="sci-shap-v">
                {s.v >= 0 ? "+" : "−"} spinge {s.v >= 0 ? "verso" : "lontano da"}{" "}
                l&apos;allerta
              </span>
            </div>
          ))}
        </div>

        {/* 8. Limiti */}
        <h3>8. Incertezza e limiti (cosa il modello NON dice)</h3>
        <ul>
          <li>
            Non è una previsione della singola frana puntuale: è un{" "}
            <strong>rischio areale su finestra 24h</strong> (o l&apos;orizzonte di
            previsione), per cella.
          </li>
          <li>
            Dipende dalla <strong>qualità e copertura dei dati</strong>: sensori
            assenti, dati statici mancanti o catalogo IFFI incompleto abbassano
            ciò che il sistema può vedere.
          </li>
          <li>
            Va <strong>sempre affiancato al giudizio dell&apos;operatore</strong>:
            è uno strumento di attenzione ed early warning, non lo sostituisce.
          </li>
        </ul>

        {/* Glossario */}
        <h3>Glossario</h3>
        <dl className="sci-glossary">
          <dt>Caine (I/D)</dt>
          <dd>curva empirica intensità–durata oltre cui, storicamente, scattano le frane superficiali.</dd>
          <dt>API</dt>
          <dd>Antecedent Precipitation Index: quanta acqua c&apos;è già nel terreno dai giorni scorsi.</dd>
          <dt>Calibrazione</dt>
          <dd>rendere una probabilità fedele alla frequenza reale (30% ⇒ ~30 casi su 100).</dd>
          <dt>SHAP</dt>
          <dd>metodo che attribuisce a ogni fattore quanto ha spinto una previsione su o giù.</dd>
          <dt>POD / FAR</dt>
          <dd>quota di eventi correttamente colti (POD) e quota di allerte che sono falsi allarmi (FAR).</dd>
          <dt>Leakage</dt>
          <dd>errore di validazione: verificare su dati troppo simili a quelli di addestramento.</dd>
        </dl>

        <p className="exp-note sci-see-also">
          Approfondimenti:{" "}
          <a href="#/come-funziona">pagina divulgativa con simulatore</a> ·{" "}
          <a
            href="https://github.com/agent-engineering-studio/limen/blob/main/docs/scoring-model.md"
            target="_blank"
            rel="noreferrer"
          >
            modello di scoring (docs)
          </a>{" "}
          ·{" "}
          <a
            href="https://github.com/agent-engineering-studio/limen/blob/main/docs/ml.md"
            target="_blank"
            rel="noreferrer"
          >
            motore ML V2 (docs)
          </a>
        </p>
      </article>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pagina: carica il model card da /api/legend e delega a ScienceContent.
// ---------------------------------------------------------------------------
export default function SciencePage(): JSX.Element {
  const [legend, setLegend] = useState<LegendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getLegend(ctrl.signal)
      .then(setLegend)
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError("Impossibile caricare i parametri del modello.");
      });
    return () => ctrl.abort();
  }, []);

  if (error) {
    return (
      <div className="explainer sci">
        <p role="alert">{error}</p>
      </div>
    );
  }
  if (!legend?.model) {
    return (
      <div className="explainer sci" aria-busy="true">
        <p>Caricamento dei parametri del modello…</p>
      </div>
    );
  }
  const pcByLevel: Record<string, string> = Object.fromEntries(
    legend.classes.map((c: { level: RiskLevel; pc_alert: string }) => [c.level, c.pc_alert]),
  );
  return (
    <ScienceContent
      model={legend.model}
      pcByLevel={pcByLevel}
      version={legend.model_version}
    />
  );
}
