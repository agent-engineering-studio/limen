import { useEffect, useState } from "react";
import type { JSX } from "react";

import { NON_E_UN_AVVISO_DI_PIENA, copernicusModificato } from "../lib/attribuzioni";
import { defaultApiClient } from "../lib/api-client";
import { BMC_PAGINA } from "../lib/buymeacoffee";
import { testi, useLocale, useTesti } from "../lib/i18n";
import { RISK_CLASSES } from "../lib/risk-colors";
import type { NationalReportResponse } from "../types";

// La home della sala operativa (#155, fase 4).
//
// Ogni frase di questa pagina deve essere vera **oggi**, non quando il
// lavoro aperto sarà chiuso. Il design proponeva tre affermazioni che non lo
// sono e che qui non compaiono: «verificato su vent'anni di frane reali» (il
// motore delle frane non passa ancora i controlli del backtest, #122), un
// modello di machine learning che «corre accanto» con i suoi numeri (in
// produzione è spento: `champion_only`), e il rischio come «S × M» (per le
// frane è una somma pesata di cinque componenti, non un prodotto).

/** La griglia di celle dietro il titolo: un'Italia stilizzata, non dati.
 *  Deterministica, così la pagina è la stessa a ogni visita. */
function GrigliaCelle(): JSX.Element {
  const colonne = 44;
  const righe = 46;
  const scala = RISK_CLASSES.slice(1).map((c) => c.color);
  const celle: string[] = [];
  for (let y = 0; y < righe; y += 1) {
    const costa = colonne * (0.05 + 0.4 * (y / righe)) + 2 * Math.sin(y * 0.35);
    for (let x = 0; x < colonne; x += 1) {
      if (x < costa) {
        celle.push("transparent");
        continue;
      }
      const v =
        0.42 +
        0.16 * Math.sin(x * 0.23 + 1.3) * Math.cos(y * 0.19 - 0.6) +
        0.12 * Math.sin((x + y) * 0.1 + 2.4) +
        0.08 * Math.sin(x * 0.55) * Math.sin(y * 0.47);
      const c = v > 0.74 ? 3 : v > 0.64 ? 2 : v > 0.54 ? 1 : v > 0.44 ? 0 : -1;
      celle.push(c < 0 ? "#141b24" : (scala[c] ?? "#141b24"));
    }
  }
  return (
    <div className="hero-griglia" aria-hidden>
      {celle.map((bg, i) => (
        <span key={i} style={{ background: bg }} />
      ))}
    </div>
  );
}

const T = testi(
  {
    pericoli: [
      {
        lettera: "F",
        classe: "hz-landslide",
        titolo: "Frane",
        testo:
          "Una somma pesata di cinque componenti: quanto è predisposto il versante, " +
          "la pioggia rispetto alla soglia d'innesco, i terremoti e gli incendi " +
          "recenti, l'acqua. Il peso più alto ce l'ha la pioggia.",
        formula: "0,35 S + 0,40 M + 0,15 E + 0,07 F + 0,03 H",
      },
      {
        lettera: "A",
        classe: "hz-flood",
        titolo: "Allagamenti",
        testo:
          "La suscettibilità idraulica del posto moltiplicata per il peggiore fra " +
          "la pioggia attesa e la piena dei fiumi. Un crinale non si allaga, " +
          "comunque piova a valle.",
        formula: "suscettibilità × max(pioggia, fiume)",
      },
      {
        lettera: "I",
        classe: "hz-wildfire",
        titolo: "Incendi",
        testo:
          "L'indice meteo degli incendi (FWI, Van Wagner) modulato dal " +
          "combustibile e dalla pendenza: il tempo decide, il terreno corregge.",
        formula: "FWI × (0,25 + 0,60 combustibile + 0,15 pendenza)",
      },
    ],
    velocita: [
      {
        quando: "Adesso",
        tono: "adesso",
        titolo: "Il punteggio, ogni ora",
        testo:
          "Per ogni cella da 1 km² e per ciascuno dei tre pericoli, con una formula " +
          "deterministica: dati gli stessi ingredienti, sempre lo stesso numero.",
        nota: "motore deterministico",
      },
      {
        quando: "+24 · +48 · +72 ore",
        tono: "futuro",
        titolo: "La previsione, ogni notte",
        testo:
          "La stessa formula con la pioggia e il tempo attesi, cella per cella, per " +
          "i tre pericoli. Sulla mappa si scorre con la timeline.",
        nota: "Open-Meteo · GloFAS",
      },
      {
        quando: "In prova",
        tono: "prova",
        titolo: "Il machine learning, in disparte",
        testo:
          "Un modello addestrato sulle frane storiche può girare in ombra accanto " +
          "alla formula, senza mai guidare gli avvisi. Oggi in produzione è spento: " +
          "decide la formula, e la promozione richiede di batterla sul campo.",
        nota: "non guida gli avvisi",
      },
    ],
    fonti: [
      ["Le frane già avvenute", "L'inventario nazionale IFFI di ISPRA: dove è già franato, franerà ancora."],
      ["Le mappe ufficiali di pericolosità", "Le aree che i piani di assetto idrogeologico (PAI) e la mosaicatura idraulica ISPRA già classificano."],
      ["Il meteo, cella per cella", "Pioggia, umidità del suolo e tempo da un'istanza propria di Open-Meteo; le soglie di pioggia tarate sul catalogo e-ITALICA del CNR-IRPI."],
      ["I fiumi", "La portata prevista dal sistema europeo GloFAS, confrontata con la piena ordinaria di ciascun corso d'acqua."],
      ["Terremoti e incendi", "Gli eventi INGV, le aree bruciate EFFIS e i fuochi attivi FIRMS."],
    ] as [string, string][],
    celleRiserva: "312.000+",
    eyebrow: "Frane · allagamenti · incendi — Italia",
    titolo: "Il rischio del territorio, cella per cella.",
    sottotitolo:
      "Limen unisce dati geologici, meteo, sismici e di pericolosità " +
      "idraulica in un punteggio di rischio per frane, allagamenti e incendi, " +
      "aggiornato ogni ora su una griglia di 1 km² che copre tutto il " +
      "territorio nazionale. Deterministico e spiegabile: ogni numero si " +
      "scompone fino alla fonte che lo ha prodotto.",
    apriDashboard: "Apri la dashboard",
    cosaE: "Cos'è Limen",
    celleMonitorate: "celle monitorate",
    regioniCoperte: "regioni coperte",
    cadenza: "cadenza di aggiornamento",
    unOra: "1 ora",
    risoluzione: "risoluzione della griglia",
    formuleEyebrow: "Nessuna scatola nera",
    formuleTitolo: "Tre pericoli, tre formule aperte.",
    formuleLede:
      "Ogni peso e ogni soglia stanno in un file di configurazione " +
      "leggibile. Nessun modello linguistico partecipa al calcolo.",
    velocitaEyebrow: "Una pipeline, tre velocità",
    velocitaTitolo: "Da adesso alle prossime 72 ore.",
    fontiEyebrow: "Da dove vengono i dati",
    fontiTitolo: "Fonti pubbliche, metodo aperto.",
    limitiPrima: "Quello che il calcolo non sa fare è scritto anch'esso: ",
    limitiLink: "cosa questo calcolo non può sapere",
    ctaTitolo: "Guarda il tuo comune, adesso.",
    ctaTesto:
      "Limen affianca e non sostituisce l'allertamento della " +
      "Protezione Civile. Segui sempre le indicazioni del tuo Comune.",
    ctaBottone: "Apri la dashboard →",
    crediti:
      "Dati: ISPRA IdroGEO (CC-BY 4.0) · e-ITALICA CNR-IRPI (CC-BY 4.0) · " +
      "Open-Meteo (CC-BY 4.0) · GloFAS e CEMS Fire · INGV (CC-BY 4.0) · " +
      "EFFIS · NASA FIRMS · CORINE Land Cover · © OpenStreetMap contributors " +
      "(ODbL). Codice EUPL-1.2.",
    copernicus: (): string => copernicusModificato(),
    nonAvviso: NON_E_UN_AVVISO_DI_PIENA,
    claude:
      "Limen è sviluppato con Claude Code fin dal primo commit, e i racconti " +
      "delle regioni sono scritti con Claude. Progetto indipendente, non " +
      "affiliato ad Anthropic.",
    sostieni:
      "Limen è gratuito e aperto a tutti. Se ti è utile, aiutaci a tenere " +
      "acceso il server.",
    disclaimer:
      "Limen è uno strumento di supporto al monitoraggio: non sostituisce le " +
      "valutazioni delle autorità di protezione civile.",
  },
  {
    pericoli: [
      {
        lettera: "L",
        classe: "hz-landslide",
        titolo: "Landslides",
        testo:
          "A weighted sum of five components: how prone the slope is, rainfall " +
          "against the triggering threshold, recent earthquakes and wildfires, " +
          "water. Rainfall carries the highest weight.",
        formula: "0.35 S + 0.40 M + 0.15 E + 0.07 F + 0.03 H",
      },
      {
        lettera: "F",
        classe: "hz-flood",
        titolo: "Floods",
        testo:
          "The hydraulic susceptibility of the place multiplied by the worse of " +
          "expected rainfall and river flooding. A ridge does not flood, however " +
          "hard it rains in the valley below.",
        formula: "susceptibility × max(rain, river)",
      },
      {
        lettera: "W",
        classe: "hz-wildfire",
        titolo: "Wildfires",
        testo:
          "The Fire Weather Index (FWI, Van Wagner) modulated by fuel and " +
          "slope: the weather decides, the terrain adjusts.",
        formula: "FWI × (0.25 + 0.60 fuel + 0.15 slope)",
      },
    ],
    velocita: [
      {
        quando: "Now",
        tono: "adesso",
        titolo: "The score, every hour",
        testo:
          "For every 1 km² cell and for each of the three hazards, with a " +
          "deterministic formula: same inputs, always the same number.",
        nota: "deterministic engine",
      },
      {
        quando: "+24 · +48 · +72 hours",
        tono: "futuro",
        titolo: "The forecast, every night",
        testo:
          "The same formula fed with expected rainfall and weather, cell by cell, " +
          "for the three hazards. On the map you scroll through it with the timeline.",
        nota: "Open-Meteo · GloFAS",
      },
      {
        quando: "On trial",
        tono: "prova",
        titolo: "Machine learning, on the sidelines",
        testo:
          "A model trained on past landslides can run in shadow next to the " +
          "formula, without ever driving the warnings. In production it is " +
          "switched off today: the formula decides, and promotion requires " +
          "beating it in the field.",
        nota: "does not drive warnings",
      },
    ],
    fonti: [
      ["Landslides that already happened", "ISPRA's national IFFI inventory: where the ground has failed before, it will fail again."],
      ["Official hazard maps", "The areas already classified by the hydrogeological plans (PAI) and the ISPRA hydraulic hazard mosaic."],
      ["Weather, cell by cell", "Rainfall, soil moisture and weather from a self-hosted Open-Meteo instance; rainfall thresholds calibrated on the CNR-IRPI e-ITALICA catalogue."],
      ["Rivers", "Discharge forecast by the European GloFAS system, compared with each watercourse's ordinary high flow."],
      ["Earthquakes and wildfires", "INGV events, EFFIS burnt areas and FIRMS active fires."],
    ],
    celleRiserva: "312,000+",
    eyebrow: "Landslides · floods · wildfires — Italy",
    titolo: "Territorial risk, cell by cell.",
    sottotitolo:
      "Limen combines geological, weather, seismic and hydraulic hazard data " +
      "into a risk score for landslides, floods and wildfires, updated every " +
      "hour on a 1 km² grid covering the whole of Italy. Deterministic and " +
      "explainable: every number breaks down to the source that produced it.",
    apriDashboard: "Open the dashboard",
    cosaE: "What Limen is",
    celleMonitorate: "cells monitored",
    regioniCoperte: "regions covered",
    cadenza: "update interval",
    unOra: "1 hour",
    risoluzione: "grid resolution",
    formuleEyebrow: "No black box",
    formuleTitolo: "Three hazards, three open formulas.",
    formuleLede:
      "Every weight and every threshold lives in a readable configuration " +
      "file. No language model takes part in the calculation.",
    velocitaEyebrow: "One pipeline, three speeds",
    velocitaTitolo: "From now to the next 72 hours.",
    fontiEyebrow: "Where the data comes from",
    fontiTitolo: "Public sources, open method.",
    limitiPrima: "What the calculation cannot do is written down too: ",
    limitiLink: "what this calculation cannot know",
    ctaTitolo: "Look at your municipality, now.",
    ctaTesto:
      "Limen supports, and does not replace, the warnings issued by Civil " +
      "Protection. Always follow the instructions of your municipality.",
    ctaBottone: "Open the dashboard →",
    crediti:
      "Data: ISPRA IdroGEO (CC-BY 4.0) · e-ITALICA CNR-IRPI (CC-BY 4.0) · " +
      "Open-Meteo (CC-BY 4.0) · GloFAS and CEMS Fire · INGV (CC-BY 4.0) · " +
      "EFFIS · NASA FIRMS · CORINE Land Cover · © OpenStreetMap contributors " +
      "(ODbL). Code EUPL-1.2.",
    // La formula inglese è quella che la licenza CEMS-Floods chiede alla lettera.
    copernicus: (): string =>
      `Contains modified Copernicus Emergency Management Service information, ${new Date().getFullYear()}`,
    nonAvviso:
      "GloFAS data are not a flood warning: warnings are the responsibility of national and regional authorities.",
    claude:
      "Limen has been built with Claude Code since the first commit, and the " +
      "regional summaries are written with Claude. An independent project, " +
      "not affiliated with Anthropic.",
    sostieni:
      "Limen is free and open to everyone. If you find it useful, help us " +
      "keep the server running.",
    disclaimer:
      "Limen is a monitoring support tool: it does not replace the " +
      "assessments of the civil protection authorities.",
  },
);

export function HomePage(): JSX.Element {
  const t = useTesti(T);
  const loc = useLocale();
  const [stats, setStats] = useState<NationalReportResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    defaultApiClient
      .getNationalReport(controller.signal)
      .then(setStats)
      .catch(() => {
        // I numeri statici sotto tengono il titolo leggibile.
      });
    return () => controller.abort();
  }, []);

  const cells = stats ? stats.totals.cells.toLocaleString(loc) : t.celleRiserva;
  const regions = stats ? String(stats.totals.regions) : "20";

  return (
    <div className="home">
      <section className="hero">
        <GrigliaCelle />
        <div className="hero-velo" aria-hidden />
        <div className="hero-inner">
          <p className="hero-eyebrow">{t.eyebrow}</p>
          <h1>{t.titolo}</h1>
          <p className="hero-sub">{t.sottotitolo}</p>
          <div className="hero-actions">
            <a className="btn-primary" href="#/dashboard">
              {t.apriDashboard} <span aria-hidden>→</span>
            </a>
            <a className="btn-ghost" href="#/come-funziona">
              {t.cosaE}
            </a>
          </div>
          <dl className="hero-stats">
            <div>
              <dt>{t.celleMonitorate}</dt>
              <dd>{cells}</dd>
            </div>
            <div>
              <dt>{t.regioniCoperte}</dt>
              <dd>{regions}</dd>
            </div>
            <div>
              <dt>{t.cadenza}</dt>
              <dd>{t.unOra}</dd>
            </div>
            <div>
              <dt>{t.risoluzione}</dt>
              <dd>1 km²</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="home-sezione" aria-labelledby="home-formule">
        <div className="home-testa">
          <p className="hero-eyebrow">{t.formuleEyebrow}</p>
          <h2 id="home-formule">{t.formuleTitolo}</h2>
          <p className="home-lede">{t.formuleLede}</p>
        </div>
        <div className="home-carte">
          {t.pericoli.map((p) => (
            <article key={p.lettera} className="home-carta">
              <span className={`hz-lettera ${p.classe}`} aria-hidden>
                {p.lettera}
              </span>
              <h3>{p.titolo}</h3>
              <p>{p.testo}</p>
              <code className="home-formula">{p.formula}</code>
            </article>
          ))}
        </div>
      </section>

      <section className="home-fascia" aria-labelledby="home-velocita">
        <div className="home-sezione">
          <div className="home-testa">
            <p className="hero-eyebrow">{t.velocitaEyebrow}</p>
            <h2 id="home-velocita">{t.velocitaTitolo}</h2>
          </div>
          <ol className="home-linea">
            {t.velocita.map((v) => (
              <li key={v.tono} className={`tono-${v.tono}`}>
                <span className="home-tappa mono">
                  <span className="home-punto" aria-hidden />
                  {v.quando}
                </span>
                <h3>{v.titolo}</h3>
                <p>{v.testo}</p>
                <span className="home-nota mono">{v.nota}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="home-sezione home-fonti" aria-labelledby="home-fonti">
        <div className="home-testa">
          <p className="hero-eyebrow">{t.fontiEyebrow}</p>
          <h2 id="home-fonti">{t.fontiTitolo}</h2>
          <p className="home-lede">
            {t.limitiPrima}
            <a href="#/come-funziona/limiti-dichiarati">{t.limitiLink}</a>
            .
          </p>
        </div>
        <ol className="home-elenco">
          {t.fonti.map(([titolo, testo], i) => (
            <li key={i}>
              <span className="mono">{String(i + 1).padStart(2, "0")}</span>
              <span>
                <b>{titolo}</b>
                <span>{testo}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section className="home-sezione">
        <div className="home-cta">
          <div>
            <h2>{t.ctaTitolo}</h2>
            <p>{t.ctaTesto}</p>
          </div>
          <a className="home-cta-bottone" href="#/dashboard">
            {t.ctaBottone}
          </a>
        </div>
      </section>

      <footer className="home-footer">
        <p>{t.crediti}</p>
        <p>
          {t.copernicus()}. {t.nonAvviso}
        </p>
        <p>{t.claude}</p>
        <p className="home-sostieni">
          {t.sostieni}
          <a href={BMC_PAGINA} target="_blank" rel="noopener noreferrer">
            <img
              src={`${import.meta.env.BASE_URL}brand/buymeacoffee.svg`}
              alt="Buy me a coffee"
              width={188}
              height={40}
            />
          </a>
        </p>
        <p className="footer-disclaimer">{t.disclaimer}</p>
      </footer>
    </div>
  );
}

export default HomePage;
