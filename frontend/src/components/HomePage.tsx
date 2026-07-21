import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { useAuth } from "../lib/auth";
import type { NationalReportResponse } from "../types";

/** Subtle topographic-contour backdrop for the hero (generated curves). */
function Contours(): JSX.Element {
  const paths: string[] = [];
  for (let i = 0; i < 7; i += 1) {
    const y = 40 + i * 38;
    const a = 18 + i * 6;
    paths.push(
      `M -40 ${y} C 240 ${y - a}, 420 ${y + a}, 720 ${y - a / 2} S 1240 ${y + a}, 1480 ${y - a / 3}`,
    );
  }
  return (
    <svg
      className="hero-contours"
      viewBox="0 0 1440 320"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}

const FEATURES = [
  {
    title: "Punteggio multi-fattore",
    body:
      "Morfologia, geologia, piogge, umidità del suolo, sismicità e incendi " +
      "combinati in un punteggio interpretabile per ogni cella di 1 km² — " +
      "formula aperta, nessuna scatola nera.",
    tag: "S · M · E · F · H · K",
  },
  {
    title: "Machine learning in shadow",
    body:
      "Un modello LightGBM addestrato su 6.300 frane storiche datate corre in " +
      "parallelo al motore deterministico, con incertezza dichiarata per ogni " +
      "predizione. Promozione solo dopo verifica sul campo.",
    tag: "AUC-PR 0.60 vs 0.31",
  },
  {
    title: "Previsioni a 48 ore",
    body:
      "La stessa pipeline valuta il rischio con la pioggia prevista: sweep " +
      "previsionale ogni 6 ore e scenari what-if per la pianificazione.",
    tag: "Open-Meteo forecast",
  },
  {
    title: "Trigger radar in tempo reale",
    body:
      "La rete radar nazionale della Protezione Civile (1 km, 5 minuti) " +
      "accelera il monitoraggio: pioggia intensa vista dal radar significa " +
      "scoring immediato della regione colpita.",
    tag: "SRI · nowcast",
  },
  {
    title: "Allerte multi-canale",
    body:
      "Telegram, MQTT, email e webhook verso gateway agentici. Riassunti " +
      "deterministici — mai un numero inventato — con dedup e scala di " +
      "allerta Protezione Civile.",
    tag: "verde → rossa",
  },
  {
    title: "Dati aperti, stack aperto",
    body:
      "ISPRA IdroGEO, e-ITALICA, Copernicus, INGV, radar DPC. Python + " +
      "PostGIS + MapLibre, Apache-2.0: replicabile su qualsiasi nazione con " +
      "gli opendata disponibili.",
    tag: "Apache-2.0",
  },
];

export function HomePage(): JSX.Element {
  const [stats, setStats] = useState<NationalReportResponse | null>(null);
  const { user } = useAuth();

  useEffect(() => {
    const controller = new AbortController();
    defaultApiClient
      .getNationalReport(controller.signal)
      .then(setStats)
      .catch(() => {
        // Static fallback numbers below keep the hero meaningful.
      });
    return () => controller.abort();
  }, []);

  const cells = stats ? stats.totals.cells.toLocaleString("it-IT") : "312.000+";
  const regions = stats ? String(stats.totals.regions) : "20";
  const alerts = stats ? String(stats.alerts_24h) : "—";

  return (
    <div className="home">
      <section className="hero">
        <Contours />
        <div className="hero-inner">
          <p className="hero-eyebrow">
            Monitoraggio del rischio frane e inondazioni · Italia
          </p>
          <h1>
            Rischio frana e inondazione,
            <br />
            cella per cella.
          </h1>
          <p className="hero-sub">
            Limen unisce dati geologici, meteo, sismici, radar e{" "}
            <strong>pericolosità idraulica</strong> (fiumi, coste, laghi) in un
            punteggio di rischio aggiornato ogni ora su una griglia di 1 km² che
            copre tutto il territorio nazionale. Deterministico, spiegabile,
            verificato su vent&rsquo;anni di frane reali.
          </p>
          <div className="hero-actions">
            {user ? (
              <a className="btn-primary" href="#/dashboard">
                Apri la dashboard
              </a>
            ) : (
              <a className="btn-primary" href="#/accedi">
                Accedi alla dashboard
              </a>
            )}
            <a className="btn-ghost" href="#/come-funziona">
              Cos&apos;è Limen
            </a>
          </div>
          <dl className="hero-stats">
            <div>
              <dt>celle monitorate</dt>
              <dd>{cells}</dd>
            </div>
            <div>
              <dt>regioni coperte</dt>
              <dd>{regions}</dd>
            </div>
            <div>
              <dt>alert nelle 24h</dt>
              <dd>{alerts}</dd>
            </div>
            <div>
              <dt>cadenza</dt>
              <dd>1 ora</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="features" aria-label="Cosa fa Limen">
        <h2>Un sistema, tre orizzonti</h2>
        <p className="features-lede">
          Dal radar che vede la pioggia in atto, alla previsione a due giorni,
          al quadro nazionale di ogni mattina: la stessa pipeline, tre
          velocità.
        </p>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <article key={f.title} className="feature-card">
              <span className="feature-tag">{f.tag}</span>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="method" aria-label="Il metodo">
        <div className="method-inner">
          <h2>Prima la fisica, poi il modello</h2>
          <p>
            Il punteggio di ogni cella nasce da una combinazione lineare pesata
            di componenti fisiche — suscettibilità del versante, innesco
            meteorico sulla soglia intensità-durata di Caine, scuotimento
            sismico, effetto post-incendio, pericolosità idraulica. Ogni peso e
            soglia è dichiarato in un file di configurazione aperto e tarato su
            <strong> e-ITALICA</strong>, il catalogo CNR-IRPI delle frane
            innescate da pioggia. Il machine learning osserva, impara le
            interazioni che la formula non può esprimere, e viene promosso solo
            quando batte il motore deterministico sul campo.
          </p>
          <a className="btn-ghost dark" href="#/come-funziona">
            Leggi la spiegazione completa →
          </a>
        </div>
      </section>

      <footer className="home-footer">
        <p>
          Dati: ISPRA IdroGEO (CC-BY 4.0) · e-ITALICA CNR-IRPI (CC-BY 4.0) ·
          Copernicus / Open-Meteo · INGV (CC-BY 4.0) · Radar DPC (CC-BY-SA
          4.0) · CORINE Land Cover · © OpenStreetMap contributors (ODbL).
          Codice Apache-2.0.
        </p>
        <p className="footer-disclaimer">
          Limen è uno strumento di supporto al monitoraggio: non sostituisce le
          valutazioni delle autorità di protezione civile.
        </p>
      </footer>
    </div>
  );
}

export default HomePage;
