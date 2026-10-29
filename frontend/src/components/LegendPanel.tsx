import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useHazard, useNomePericolo } from "../lib/hazard";
import { testi, useLocale, useTesti } from "../lib/i18n";
import { useMapStateOpzionale } from "../lib/map-state";
import { useMotivoSenzaRilievo } from "../lib/rilievo";
import {
  HAZARD_HUE,
  COLORE_IGNOTO,
  RISK_CLASSES,
  riskClassesFor,
  riskColorsFor,
  useEtichetteRischio,
} from "../lib/risk-colors";
import type { HazardType, LegendClass, RiskLevel } from "../types";

const T = testi(
  {
    legenda: "Legenda classi di rischio",
    sommarioTutti: "Pericolo stimato · tutti i pericoli · non è l'allerta",
    sommario: "Pericolo stimato · non è l'allerta",
    nonAllerta: (
      <>
        Questi colori sono il <strong>pericolo stimato</strong> da Limen, non un
        livello di allerta: una cella rossa non è un&apos;allerta rossa.
        L&apos;allerta ufficiale è nel livello «Allerte Protezione Civile» e nella
        riga di ogni comune.
      </>
    ),
    nonMisurato: "Non misurato",
    nessunDato: "nessun dato",
    notaNonMisurato: (
      <>
        <strong>Non misurato</strong> non vuol dire tranquillo: il dato che
        quel pericolo richiede non è arrivato, e il punteggio varrebbe zero
        per assenza di misura. Una cella grigia è una cella su cui il
        sistema non si pronuncia.
      </>
    ),
    notaColore: (
      <>
        Il colore dice <strong>quanto</strong>: è la classe del pericolo
        peggiore in quel punto. <strong>Quale</strong> pericolo lo dicono la
        lettera dentro la cella (<strong>A</strong> allagamento,{" "}
        <strong>F</strong> frana, <strong>I</strong> incendio, da vicino) e il
        bordo, sulle sole celle in classe Alta o superiore.
      </>
    ),
    notaSoglie:
      "Le soglie numeriche cambiano da un pericolo all'altro: quelle qui sopra sono delle frane. Scegli un pericolo per vedere le sue.",
    notaListe:
      "Le liste mettono prima le celle vicine a centri abitati e strade (🏠 🛣): stesso rischio, più conseguenze. Colori e numeri seguono sempre la scala qui sopra. ",
    comeSiCalcola: "Come si calcola il rischio",
    esagerato: (x: string) => `Rilievo esagerato ×${x}: i versanti sembrano più ripidi di quanto sono.`,
  },
  {
    legenda: "Risk class legend",
    sommarioTutti: "Estimated hazard · all hazards · not a warning",
    sommario: "Estimated hazard · not a warning",
    nonAllerta: (
      <>
        These colours are the <strong>estimated hazard</strong> from Limen, not
        a warning level: a red cell is not a red warning. The official warning
        is in the «Civil Protection warnings» layer and in each
        municipality&apos;s row.
      </>
    ),
    nonMisurato: "Not measured",
    nessunDato: "no data",
    notaNonMisurato: (
      <>
        <strong>Not measured</strong> does not mean calm: the data this hazard
        needs has not arrived, and the score would be zero for lack of a
        measurement. A grey cell is a cell on which the system makes no call.
      </>
    ),
    notaColore: (
      <>
        The colour says <strong>how much</strong>: it is the class of the worst
        hazard at that point. <strong>Which</strong> hazard is shown by the
        letter inside the cell (<strong>F</strong> flood,{" "}
        <strong>L</strong> landslide, <strong>W</strong> wildfire, close up) and
        by the outline, only on cells in the High class or above.
      </>
    ),
    notaSoglie:
      "The numeric thresholds differ from one hazard to another: those above are for landslides. Pick a hazard to see its own.",
    notaListe:
      "Lists put first the cells near towns and roads (🏠 🛣): same risk, more consequences. Colours and numbers always follow the scale above. ",
    comeSiCalcola: "How the risk is computed",
    esagerato: (x: string) => `Relief exaggerated ×${x}: slopes look steeper than they are.`,
  },
);

/** I cinque colori in una riga: resta visibile anche con la legenda chiusa. */
/** La scala di riferimento della vista d'insieme: quella del pericolo di
 *  default. Nominata una volta perché è una scelta, non un dettaglio. */
const SCALA_RIFERIMENTO = "landslide" as const;

function ScalaColori({
  levels,
  hazard,
}: {
  levels: RiskLevel[];
  hazard: HazardType;
}): JSX.Element {
  const colori = riskColorsFor(hazard);
  return (
    <span className="legend-scale" aria-hidden>
      {levels.map((l) => (
        <span key={l} style={{ background: colori[l] }} />
      ))}
    </span>
  );
}

/**
 * Five-class risk legend.
 *
 * Each row pairs the colour swatch with the Italian class label **and**
 * the [lo, hi) score range, so the map stays interpretable without
 * relying on colour alone (accessibility, §6 acceptance criterion).
 * When the backend is reachable, each class also shows its Protezione
 * Civile alert colour (presentation-only mapping from /api/legend).
 */
/** La scala segue l'ordine dei colori delle allerte per farsi leggere, ed è
 *  proprio per questo che va detto: una cella rossa non è un'allerta rossa.
 *  Un operatore della Protezione civile legge quei colori come livelli di
 *  allerta, e davanti a «rosso» e a un bollettino verde non sa a chi credere. */
function NonEAllerta(): JSX.Element {
  const t = useTesti(T);
  return <p className="legend-note legend-non-allerta">{t.nonAllerta}</p>;
}

/** «Non misurato» sta in legenda perché sulla mappa è un colore come gli
 *  altri, e senza la riga resterebbe un grigio senza nome (#143). */
function RigaNonMisurato(): JSX.Element {
  const t = useTesti(T);
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      <li className="legend-row">
        <span
          className="legend-swatch"
          role="presentation"
          aria-hidden
          style={{ background: COLORE_IGNOTO }}
        />
        <span>
          {t.nonMisurato} <small style={{ color: "var(--muted)" }}>(—)</small>
        </span>
        <span className="legend-range">{t.nessunDato}</span>
      </li>
    </ul>
  );
}

/** In «Rilievo» l'altezza è un canale in più, e se è esagerata va detto
 *  (#322): un versante ×1,5 sembra più pericoloso di quanto è. */
function NotaRilievo(): JSX.Element | null {
  const t = useTesti(T);
  const loc = useLocale();
  const stato = useMapStateOpzionale();
  const disponibile = useMotivoSenzaRilievo() === null;
  if (!stato || stato.vista !== "rilievo" || !disponibile || stato.esagerazione === 1) return null;
  return <p className="legend-note">{t.esagerato(stato.esagerazione.toLocaleString(loc))}</p>;
}

export function LegendPanel(): JSX.Element {
  // I cutoff arrivano dal backend perché sono **per pericolo** (#84): quelli
  // statici in RISK_CLASSES sono le soglie delle frane, e mostrarli per un
  // altro pericolo etichetterebbe male i suoi colori. Restano solo come
  // ripiego finché la prima risposta non arriva, o se l'API è irraggiungibile.
  const [ranges, setRanges] = useState<Record<string, [number, number]>>({});
  const { selected, multi, available } = useHazard();
  const t = useTesti(T);
  const etichette = useEtichetteRischio();
  const nomePericolo = useNomePericolo();

  useEffect(() => {
    // I cutoff sono per pericolo: senza azzerarli, una legenda che fallisce
    // dopo un cambio lascerebbe quelli del pericolo precedente.
    setRanges({});
    const controller = new AbortController();
    defaultApiClient
      .getLegend(controller.signal, selected)
      .then((legend) => {
        const bounds: Record<string, [number, number]> = {};
        legend.classes.forEach((c: LegendClass) => {
          bounds[c.level] = [c.lo, c.hi];
        });
        setRanges(bounds);
      })
      .catch(() => {
        // La legenda statica resta: le soglie del backend sono un di più.
      });
    return () => controller.abort();
  }, [selected]);

  // In vista d'insieme i cutoff sono diversi per pericolo, quindi la colonna
  // dei numeri non esiste: quello che serve leggere è la corrispondenza fra
  // tinta e pericolo, che nella vista d'insieme è l'unico modo di sapere
  // *cosa* colora una cella.
  if (multi) {
    // Una scala sola, non una matrice 5×3. La vista d'insieme portava due
    // informazioni in un colore — la tinta il pericolo, l'intensità la
    // gravità — e per decodificarla serviva questa tabella accanto: quindici
    // caselle per leggere una cella. Ora il colore dice quanto, e quale
    // pericolo lo dice il bordo delle celle in classe alta.
    return (
      <details className="legend-panel" aria-label={t.legenda}>
        <summary>
          <ScalaColori
            levels={RISK_CLASSES.map((c) => c.level)}
            hazard={SCALA_RIFERIMENTO}
          />
          {t.sommarioTutti}
        </summary>
        <NonEAllerta />
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {riskClassesFor(SCALA_RIFERIMENTO).map((c) => (
            <li key={c.level} className="legend-row">
              <span
                className="legend-swatch"
                role="presentation"
                aria-hidden
                style={{ background: c.color }}
              />
              <span>
                {etichette[c.level]} <small style={{ color: "var(--muted)" }}>({c.short})</small>
              </span>
              <span className="legend-range">
                {`${c.range[0].toFixed(2)}-${c.range[1].toFixed(2)}`}
              </span>
            </li>
          ))}
        </ul>
        <RigaNonMisurato />
        <p className="legend-note">{t.notaNonMisurato}</p>
        <NotaRilievo />
        <p className="legend-note">{t.notaColore}</p>
        <ul className="legend-hazards">
          {available.map((h) => (
            <li key={h.hazard}>
              <span
                className="legend-outline"
                aria-hidden
                style={{ borderColor: HAZARD_HUE[h.hazard] }}
              />
              {nomePericolo(h.hazard)}
            </li>
          ))}
        </ul>
        <p className="legend-note">{t.notaSoglie}</p>
      </details>
    );
  }

  return (
    <details className="legend-panel" aria-label={t.legenda}>
      <summary>
        <ScalaColori levels={riskClassesFor(selected).map((c) => c.level)} hazard={selected} />
        {t.sommario}
      </summary>
      <NonEAllerta />
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {riskClassesFor(selected).map((c) => (
          <li key={c.level} className="legend-row">
            <span
              className="legend-swatch"
              role="presentation"
              aria-hidden
              style={{ background: c.color }}
            />
            <span>
              {etichette[c.level]}{" "}
              <small style={{ color: "var(--muted)" }}>({c.short})</small>
            </span>
            <span className="legend-range">
              {((r) => `${r[0].toFixed(2)}-${r[1].toFixed(2)}`)(
                ranges[c.level] ?? c.range,
              )}
            </span>
          </li>
        ))}
      </ul>
      <RigaNonMisurato />
      <p className="legend-note">{t.notaNonMisurato}</p>
      <NotaRilievo />
      <p className="legend-note">
        {t.notaListe}
        <a href="#/come-funziona/i-tre-motori">{t.comeSiCalcola}</a>
      </p>
    </details>
  );
}

export default LegendPanel;
