// Capitolo 3 del percorso «Capire Limen» — la diagnostica del modello ML in
// ombra (#26). Intro didattica e dati live sono entrambi **pubblici** (#71):
// la mappa è pubblica in sola lettura, e le API che alimentano questa pagina
// lo erano già — il gating viveva solo nel frontend, quindi proteggeva la
// pagina e non i dati. NON autoritativo: il V1 guida sempre le allerte, ed è
// ciò che il disclaimer qui sotto continua a dire.

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { RISK_CLASSES, useEtichetteRischio } from "../lib/risk-colors";
import { defaultApiClient } from "../lib/api-client";
import { testi, useLocale, useTesti } from "../lib/i18n";
import type { ReliabilityResponse, ShadowSummaryResponse } from "../types";
import ConsumiAi from "./ConsumiAi";
import { ChapterFooter, CourseHeader } from "./Course";
import DivergenceMap from "./DivergenceMap";
import ReliabilityChart from "./ReliabilityChart";
import { nationalAgreement } from "./ShadowPanel";

const pct = (x: number): string => `${Math.round(x * 100)}%`;

/** Indice di classe (0=None … 4=VeryHigh) per un punteggio champion. */
export function championClassIndex(score: number): number {
  for (let i = RISK_CLASSES.length - 1; i >= 0; i--) {
    const c = RISK_CLASSES[i];
    if (c && score >= c.range[0]) return i;
  }
  return 0;
}

/** Il sistema ufficiale avrebbe segnalato l'evento (classe ≥ Moderato)? */
export function championWouldAlert(score: number): boolean {
  return championClassIndex(score) >= 2; // Moderate è indice 2
}

const T = testi(
  {
    errore: "Impossibile caricare la diagnostica shadow.",
    caricamento: "Caricamento dei dati…",
    accordoTitolo: "Accordo complessivo",
    accordo: (n: string, perc: string) => (
      <>
        Su <strong>{n}</strong> valutazioni osservate, l&apos;IA concorda col sistema ufficiale
        sulla classe di rischio nel <strong>{perc}</strong> dei casi.
      </>
    ),
    eventiTitolo: "Eventi reali nella finestra",
    nessunEvento: (
      <>
        Nessun evento di frana datato (catalogo ITALICA) nella finestra di osservazione. Il
        confronto sul <em>recall</em> — quante frane reali ciascun motore avrebbe segnalato — sarà
        possibile quando se ne accumuleranno. È l&apos;evidenza che conta di più per decidere la
        promozione.
      </>
    ),
    eventi: (n: number, presi: number, soglia: string) => (
      <>
        Su <strong>{n}</strong> event{n === 1 ? "o" : "i"} reale, il sistema ufficiale ne aveva
        già <strong>{presi}</strong> ad almeno «{soglia}» nelle 48 h precedenti. La probabilità
        dell&apos;IA è a fianco, ancora<em> in valutazione</em>.
      </>
    ),
    regione: "Regione",
    evento: "Evento (UTC)",
    ufficiale: "Sistema ufficiale",
    iaInProva: "IA (in prova)",
    perRegioneTitolo: "Accordo per regione",
    nessunaRegione: "Nessuna regione con dati nella finestra.",
    accordoClassi: "Accordo sulle classi",
    valutazioni: "Valutazioni",
    divergenzaTitolo: "Mappa della divergenza",
    divergenza: (
      <>
        Ogni cella colorata per <em>quanto</em> l&apos;IA si discosta dal sistema ufficiale (vedi
        la legenda della mappa). Colori neutri, non la scala del rischio: qui il colore significa
        «disaccordo tra modelli», non «pericolo».
      </>
    ),
    calibrazioneTitolo: "Calibrazione (reliability)",
    calibrazione: (
      <>
        Quando l&apos;IA stima una probabilità, quella percentuale corrisponde alla frequenza
        reale? Più i punti stanno sulla diagonale, meglio è calibrata. I punti vengono dal
        confronto <strong>notturno</strong>: il modello in ombra gira una volta al giorno, non a
        ogni valutazione oraria, quindi un giorno di dati è un giro di confronto, non
        ventiquattro.
      </>
    ),
    caricamentoCalibrazione: "Caricamento della calibrazione…",
    finestra: (dal: string, modelli: string) =>
      `Finestra dal ${dal} · confronto notturno · modello IA: ${modelli}.`,
    nd: "n/d",
    pagina: "Diagnostica ML (shadow)",
    learn:
      "cos'è il «modello in ombra», perché confrontiamo due modelli, e come leggere la mappa della divergenza.",
    eyebrow: "Capitolo avanzato",
    titolo: "La diagnostica del modello sperimentale (IA)",
    lede: (
      <>
        Accanto al sistema ufficiale ne gira un secondo, un&apos;
        <strong>intelligenza artificiale in prova</strong>. Questa pagina spiega com&apos;è tenuto
        d&apos;occhio prima di decidere se fidarsi.
      </>
    ),
    ombraTitolo: "Cos'è il «modello in ombra»",
    ombra: (
      <>
        Il sistema ufficiale (lo chiamiamo <strong>V1</strong>) calcola le allerte, come descritto
        nei capitoli precedenti. In parallelo, senza mai toccare le allerte, un modello di{" "}
        <strong>machine learning</strong> (V2) fa la sua stima sugli stessi dati e la registra a
        parte. Gira «in ombra»: osserviamo come se la caverebbe, ma le decisioni restano al V1.
      </>
    ),
    dueTitolo: "Perché due modelli",
    due: (
      <>
        Per capire, con mesi di prove alla mano, <em>se</em> l&apos;IA sia davvero più brava —{" "}
        <strong>prima</strong> di affidarle qualcosa. Il passaggio di consegne (la «promozione») è
        una scelta <strong>manuale</strong>, mai automatica, e non avviene da questa pagina.
      </>
    ),
    guardiamoTitolo: "Cosa guardiamo",
    guardiamo: [
      <>
        <strong>Accordo</strong>: quanto spesso i due modelli assegnano la stessa classe di rischio
        alla stessa cella. Un accordo basso, per un modello ancora in prova, è normale.
      </>,
      <>
        <strong>Recall sugli eventi reali</strong>: prendendo le frane davvero avvenute, quale dei
        due le avrebbe segnalate prima. È la prova che conta di più.
      </>,
      <>
        <strong>Mappa della divergenza</strong>: dove l&apos;IA vede <em>più</em> o <em>meno</em>{" "}
        rischio del sistema ufficiale — in
        <span className="dv-inline dv-less"> blu</span> vede meno,
        <span className="dv-inline dv-eq"> grigio</span> sono d&apos;accordo,
        <span className="dv-inline dv-more"> viola</span> vede più. Colori neutri di proposito:
        qui il colore è «disaccordo», non «pericolo».
      </>,
    ],
  },
  {
    errore: "Could not load the shadow diagnostics.",
    caricamento: "Loading data…",
    accordoTitolo: "Overall agreement",
    accordo: (n: string, perc: string) => (
      <>
        Out of <strong>{n}</strong> observed assessments, the AI agrees with the official system on
        the risk class in <strong>{perc}</strong> of cases.
      </>
    ),
    eventiTitolo: "Real events in the window",
    nessunEvento: (
      <>
        No dated landslide event (ITALICA catalogue) in the observation window. The comparison on{" "}
        <em>recall</em> — how many real landslides each engine would have flagged — will be
        possible once some accumulate. It is the evidence that matters most for deciding on
        promotion.
      </>
    ),
    eventi: (n: number, presi: number, soglia: string) => (
      <>
        Out of <strong>{n}</strong> real event{n === 1 ? "" : "s"}, the official system already had{" "}
        <strong>{presi}</strong> at «{soglia}» or above in the previous 48 h. The AI probability
        is shown alongside, still <em>under evaluation</em>.
      </>
    ),
    regione: "Region",
    evento: "Event (UTC)",
    ufficiale: "Official system",
    iaInProva: "AI (on trial)",
    perRegioneTitolo: "Agreement by region",
    nessunaRegione: "No region with data in the window.",
    accordoClassi: "Class agreement",
    valutazioni: "Assessments",
    divergenzaTitolo: "Divergence map",
    divergenza: (
      <>
        Each cell is coloured by <em>how much</em> the AI departs from the official system (see the
        map legend). Neutral colours, not the risk scale: here colour means «disagreement between
        models», not «hazard».
      </>
    ),
    calibrazioneTitolo: "Calibration (reliability)",
    calibrazione: (
      <>
        When the AI estimates a probability, does that percentage match the real frequency? The
        closer the points are to the diagonal, the better calibrated it is. The points come from
        the <strong>nightly</strong> comparison: the shadow model runs once a day, not at every
        hourly assessment, so one day of data is one comparison run, not twenty-four.
      </>
    ),
    caricamentoCalibrazione: "Loading calibration…",
    finestra: (dal: string, modelli: string) =>
      `Window from ${dal} · nightly comparison · AI model: ${modelli}.`,
    nd: "n/a",
    pagina: "ML diagnostics (shadow)",
    learn:
      "what the «shadow model» is, why we compare two models, and how to read the divergence map.",
    eyebrow: "Advanced chapter",
    titolo: "Diagnostics of the experimental model (AI)",
    lede: (
      <>
        Alongside the official system a second one runs: an{" "}
        <strong>artificial intelligence on trial</strong>. This page explains how it is monitored
        before deciding whether to trust it.
      </>
    ),
    ombraTitolo: "What the «shadow model» is",
    ombra: (
      <>
        The official system (we call it <strong>V1</strong>) computes the warnings, as described in
        the previous chapters. In parallel, without ever touching the warnings, a{" "}
        <strong>machine learning</strong> model (V2) makes its own estimate on the same data and
        records it separately. It runs «in shadow»: we watch how it would do, but decisions stay
        with V1.
      </>
    ),
    dueTitolo: "Why two models",
    due: (
      <>
        To find out, with months of evidence in hand, <em>whether</em> the AI is really better —{" "}
        <strong>before</strong> entrusting it with anything. The handover (the «promotion») is a{" "}
        <strong>manual</strong> decision, never automatic, and it does not happen from this page.
      </>
    ),
    guardiamoTitolo: "What we look at",
    guardiamo: [
      <>
        <strong>Agreement</strong>: how often the two models assign the same risk class to the same
        cell. Low agreement is normal for a model still on trial.
      </>,
      <>
        <strong>Recall on real events</strong>: taking the landslides that actually happened, which
        of the two would have flagged them first. It is the test that matters most.
      </>,
      <>
        <strong>Divergence map</strong>: where the AI sees <em>more</em> or <em>less</em> risk than
        the official system — in
        <span className="dv-inline dv-less"> blue</span> it sees less,
        <span className="dv-inline dv-eq"> grey</span> they agree,
        <span className="dv-inline dv-more"> purple</span> it sees more. Neutral colours on
        purpose: here colour means «disagreement», not «hazard».
      </>,
    ],
  },
);

// --- Dati live -------------------------------------------------------------
function LiveDiagnostics(): JSX.Element {
  const t = useTesti(T);
  const loc = useLocale();
  const etichette = useEtichetteRischio();
  const [data, setData] = useState<ShadowSummaryResponse | null>(null);
  const [reliability, setReliability] = useState<ReliabilityResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getShadowSummary(ctrl.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(true);
      });
    // Reliability is optional/gated — its failure must not break the panel.
    defaultApiClient
      .getShadowReliability(ctrl.signal)
      .then(setReliability)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);

  if (error) return <p role="alert">{t.errore}</p>;
  if (!data) return <p className="shadow-muted">{t.caricamento}</p>;

  const agreement = nationalAgreement(data.regions);
  const events = data.truth_events;
  const officialCaught = events.filter(
    (e) => e.champion_score !== null && championWouldAlert(e.champion_score),
  ).length;

  return (
    <>
      <h3>{t.accordoTitolo}</h3>
      <p className="shadow-headline">
        {t.accordo(data.total_pairs.toLocaleString(loc), agreement !== null ? pct(agreement) : "—")}
      </p>

      <h3>{t.eventiTitolo}</h3>
      {events.length === 0 ? (
        <p className="shadow-muted">{t.nessunEvento}</p>
      ) : (
        <>
          <p>{t.eventi(events.length, officialCaught, etichette.Moderate)}</p>
          <table className="shadow-table">
            <thead>
              <tr>
                <th>{t.regione}</th>
                <th>{t.evento}</th>
                <th>{t.ufficiale}</th>
                <th>{t.iaInProva}</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={`${e.cell_id}-${e.event_time}`}>
                  <td>{e.aoi_name}</td>
                  <td>{e.event_time.slice(0, 16).replace("T", " ")}</td>
                  <td>
                    {e.champion_score !== null
                      ? `${etichette[RISK_CLASSES[championClassIndex(e.champion_score)]!.level]} (${e.champion_score.toFixed(2)})`
                      : "—"}
                  </td>
                  <td>{e.ml_probability !== null ? e.ml_probability.toFixed(2) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>{t.perRegioneTitolo}</h3>
      {data.regions.length === 0 ? (
        <p className="shadow-muted">{t.nessunaRegione}</p>
      ) : (
        <table className="shadow-table">
          <thead>
            <tr>
              <th>{t.regione}</th>
              <th>{t.accordoClassi}</th>
              <th>{t.valutazioni}</th>
            </tr>
          </thead>
          <tbody>
            {[...data.regions]
              .sort((a, b) => b.n - a.n)
              .map((r) => (
                <tr key={r.aoi_id}>
                  <td>{r.aoi_name}</td>
                  <td>{pct(r.class_agreement)}</td>
                  <td>{r.n.toLocaleString(loc)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}

      <h3>{t.divergenzaTitolo}</h3>
      <p className="shadow-muted">{t.divergenza}</p>
      <DivergenceMap />

      <h3>{t.calibrazioneTitolo}</h3>
      <p className="shadow-muted">{t.calibrazione}</p>
      {reliability ? (
        <ReliabilityChart data={reliability} />
      ) : (
        <p className="shadow-muted">{t.caricamentoCalibrazione}</p>
      )}

      <p className="exp-note">
        {t.finestra(data.since.slice(0, 10), data.model_versions.join(", ") || t.nd)}
      </p>
    </>
  );
}

// --- Pagina: intro e dati live, entrambi pubblici --------------------------
export default function ShadowDiagnosticsPage(): JSX.Element {
  const t = useTesti(T);
  return (
    <div className="explainer sci" aria-label={t.pagina}>
      <article>
        <CourseHeader current={3} learn={t.learn} />
        <p className="exp-eyebrow">{t.eyebrow}</p>
        <h2>{t.titolo}</h2>

        <p className="exp-lede">{t.lede}</p>

        <h3>{t.ombraTitolo}</h3>
        <p>{t.ombra}</p>

        <h3>{t.dueTitolo}</h3>
        <p>{t.due}</p>

        <h3>{t.guardiamoTitolo}</h3>
        <ul>
          {t.guardiamo.map((voce, i) => (
            <li key={i}>{voce}</li>
          ))}
        </ul>

        <LiveDiagnostics />

        <ConsumiAi />

        <ChapterFooter current={3} />
      </article>
    </div>
  );
}
