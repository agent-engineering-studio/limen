import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
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

const PERICOLI = [
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
];

const VELOCITA = [
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
];

const FONTI = [
  ["Le frane già avvenute", "L'inventario nazionale IFFI di ISPRA: dove è già franato, franerà ancora."],
  ["Le mappe ufficiali di pericolosità", "Le aree che i piani di assetto idrogeologico (PAI) e la mosaicatura idraulica ISPRA già classificano."],
  ["Il meteo, cella per cella", "Pioggia, umidità del suolo e tempo da un'istanza propria di Open-Meteo; le soglie di pioggia tarate sul catalogo e-ITALICA del CNR-IRPI."],
  ["I fiumi", "La portata prevista dal sistema europeo GloFAS, confrontata con la piena ordinaria di ciascun corso d'acqua."],
  ["Terremoti e incendi", "Gli eventi INGV, le aree bruciate EFFIS e i fuochi attivi FIRMS."],
] as const;

export function HomePage(): JSX.Element {
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

  const cells = stats ? stats.totals.cells.toLocaleString("it-IT") : "312.000+";
  const regions = stats ? String(stats.totals.regions) : "20";

  return (
    <div className="home">
      <section className="hero">
        <GrigliaCelle />
        <div className="hero-velo" aria-hidden />
        <div className="hero-inner">
          <p className="hero-eyebrow">Frane · allagamenti · incendi — Italia</p>
          <h1>Il rischio del territorio, cella per cella.</h1>
          <p className="hero-sub">
            Limen unisce dati geologici, meteo, sismici e di pericolosità
            idraulica in un punteggio di rischio per frane, allagamenti e incendi,
            aggiornato ogni ora su una griglia di 1 km² che copre tutto il
            territorio nazionale. Deterministico e spiegabile: ogni numero si
            scompone fino alla fonte che lo ha prodotto.
          </p>
          <div className="hero-actions">
            <a className="btn-primary" href="#/dashboard">
              Apri la dashboard <span aria-hidden>→</span>
            </a>
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
              <dt>cadenza di aggiornamento</dt>
              <dd>1 ora</dd>
            </div>
            <div>
              <dt>risoluzione della griglia</dt>
              <dd>1 km²</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="home-sezione" aria-labelledby="home-formule">
        <div className="home-testa">
          <p className="hero-eyebrow">Nessuna scatola nera</p>
          <h2 id="home-formule">Tre pericoli, tre formule aperte.</h2>
          <p className="home-lede">
            Ogni peso e ogni soglia stanno in un file di configurazione
            leggibile. Nessun modello linguistico partecipa al calcolo.
          </p>
        </div>
        <div className="home-carte">
          {PERICOLI.map((p) => (
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
            <p className="hero-eyebrow">Una pipeline, tre velocità</p>
            <h2 id="home-velocita">Da adesso alle prossime 72 ore.</h2>
          </div>
          <ol className="home-linea">
            {VELOCITA.map((v) => (
              <li key={v.quando} className={`tono-${v.tono}`}>
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
          <p className="hero-eyebrow">Da dove vengono i dati</p>
          <h2 id="home-fonti">Fonti pubbliche, metodo aperto.</h2>
          <p className="home-lede">
            Quello che il calcolo non sa fare è scritto anch&apos;esso:{" "}
            <a href="#/come-funziona/limiti-dichiarati">
              cosa questo calcolo non può sapere
            </a>
            .
          </p>
        </div>
        <ol className="home-elenco">
          {FONTI.map(([titolo, testo], i) => (
            <li key={titolo}>
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
            <h2>Guarda il tuo comune, adesso.</h2>
            <p>
              Limen affianca e non sostituisce l&apos;allertamento della
              Protezione Civile. Segui sempre le indicazioni del tuo Comune.
            </p>
          </div>
          <a className="home-cta-bottone" href="#/dashboard">
            Apri la dashboard →
          </a>
        </div>
      </section>

      <footer className="home-footer">
        <p>
          Dati: ISPRA IdroGEO (CC-BY 4.0) · e-ITALICA CNR-IRPI (CC-BY 4.0) ·
          Copernicus / Open-Meteo · GloFAS · INGV (CC-BY 4.0) · EFFIS · NASA
          FIRMS · CORINE Land Cover · © OpenStreetMap contributors (ODbL).
          Codice Apache-2.0.
        </p>
        <p>
          Limen è sviluppato con Claude Code fin dal primo commit, e i racconti
          delle regioni sono scritti con Claude. Progetto indipendente, non
          affiliato ad Anthropic.
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
