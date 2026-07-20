// "Come funziona" — spiegazione divulgativa del punteggio di rischio, con un
// simulatore che usa la stessa formula del motore (regional_thresholds.yaml).
// Linguaggio per non addetti: niente termine tecnico senza spiegazione.

import { useState } from "react";

import { RISK_CLASSES } from "../lib/risk-colors";
import { ChapterFooter, CourseHeader } from "./Course";

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
    return `Rischio ${cls}: terreno predisposto E pioggia sufficiente insieme. È la combinazione che fa scattare l'allerta, in media con ~55 ore di preavviso.`;
  }
  if (r.classIndex === 2) {
    return `Rischio ${cls}: la condizione di base di un versante così fragile — sorveglianza ordinaria. È la pioggia a spingerlo più su.`;
  }
  return `Rischio ${cls}: il versante è predisposto, ma senza abbastanza pioggia resta tranquillo. Serve l'innesco.`;
}

export default function ExplainerPage(): JSX.Element {
  const [cellId, setCellId] = useState("alpine");
  const [rain, setRain] = useState(40);
  const [api, setApi] = useState(120);
  const [soil, setSoil] = useState(35);
  const [snow, setSnow] = useState(0);

  const cell = SIM_CELLS.find((c) => c.id === cellId) ?? ALPINE;
  const r = simulate(cell, rain, api, soil / 100, snow / 100);

  return (
    <div className="explainer" aria-label="Come funziona Limen">
      <article>
        <CourseHeader
          current={1}
          learn="cosa fa Limen, le due domande (dove e quando), e un simulatore per provarlo tu."
        />
        <p className="exp-eyebrow">Guida per tutti</p>
        <h2>Come fa Limen a dire dove può franare?</h2>
        <p className="exp-lede">
          Nessuna magia e nessuna scatola nera: Limen risponde, ogni ora e per
          ogni chilometro quadrato d&apos;Italia, a due domande semplici. Qui
          le spieghiamo con parole di tutti i giorni e un esempio vero.
        </p>

        <h3>Le due domande</h3>
        <p>
          <strong>1. Questo versante è fragile?</strong> Alcuni terreni sono
          predisposti a franare da sempre: sono ripidi, fatti di rocce che si
          sbriciolano o di argille che diventano sapone quando si bagnano, e
          spesso lì è <em>già</em> franato in passato. Questa è la parte che
          non cambia da un giorno all&apos;altro: la chiamiamo{" "}
          <strong>predisposizione</strong> (la lettera <code>S</code> nei
          rapporti tecnici). È come la carta d&apos;identità del versante.
        </p>
        <p>
          <strong>2. Sta succedendo qualcosa che può svegliarlo?</strong> Un
          versante fragile può restare fermo per decenni. Quasi sempre a
          svegliarlo è l&apos;acqua: una pioggia intensa, giorni di pioggia
          che hanno inzuppato il terreno come una spugna, la neve che si
          scioglie sotto la pioggia. Più raramente un terremoto, o un incendio
          recente che ha tolto la vegetazione che teneva ferma la terra.
          Questa è la parte che cambia ora per ora: l&apos;
          <strong>innesco</strong> (la <code>M</code> di meteo, più sismi,
          incendi e neve).
        </p>
        <p>
          Il punteggio di rischio nasce mettendo insieme le due risposte:{" "}
          <em>
            un versante fragile sotto una pioggia importante è pericoloso; lo
            stesso versante col sole non lo è; la stessa pioggia in pianura
            nemmeno.
          </em>
        </p>

        <h3>Da dove vengono i dati</h3>
        <ul>
          <li>
            <strong>La forma del terreno</strong> — un modello 3D
            dell&apos;Italia con un punto ogni 5 metri, per misurare le
            pendenze.
          </li>
          <li>
            <strong>La memoria storica</strong> — l&apos;inventario nazionale
            ISPRA di oltre un milione di frane già avvenute: dove è successo,
            tende a risuccedere.
          </li>
          <li>
            <strong>Le mappe ufficiali di pericolosità</strong> — le zone che
            i piani di assetto del territorio (PAI) classificano già a
            rischio.
          </li>
          <li>
            <strong>Il tipo di roccia</strong> — argille e rocce fratturate
            franano più volentieri di graniti compatti.
          </li>
          <li>
            <strong>Il meteo, ora per ora</strong> — pioggia, umidità del
            suolo e neve, cella per cella, non un valore unico per tutta la
            regione.
          </li>
        </ul>

        <h3>Chi fa i calcoli: tre livelli, tre lavori diversi</h3>
        <p>
          <strong>① Oggi decide una formula, non un&apos;intelligenza
          artificiale.</strong> Il punteggio è una somma pesata trasparente:
          la predisposizione conta per il 35%, il meteo per il 40%, il resto
          si divide tra sismi, incendi e zone alluvionabili. I pesi vengono
          da decenni di studi scientifici sulle frane italiane e sono stati
          ritarati confrontandoli con migliaia di frane realmente avvenute.
          Chiunque può ricontrollare il conto a mano — e più sotto lo facciamo
          davvero, insieme.
        </p>
        <p>
          <strong>② Un modello che studia il passato si sta allenando a fare
          meglio.</strong> Abbiamo dato in pasto a un algoritmo di{" "}
          <em>machine learning</em> l&apos;archivio di 6.312 frane italiane
          documentate (dove, quando, con quanta pioggia). L&apos;algoritmo
          impara da solo le combinazioni pericolose — anche quelle troppo
          sottili per una formula fissa. Ma non comanda: lavora in parallelo,
          &laquo;in ombra&raquo;, e prenderà il posto della formula solo se
          dimostrerà, sui dati storici, di prevedere meglio. La decisione
          finale di promuoverlo spetta comunque a una persona.
        </p>
        <p>
          <strong>③ L&apos;AI che scrive… scrive e basta.</strong> Quando una
          zona si accende, un&apos;intelligenza artificiale linguistica
          trasforma i numeri in un breve rapporto in italiano per chi deve
          intervenire. Non può cambiare un punteggio, né inventare
          un&apos;allerta: riceve i risultati già decisi e li racconta. Se
          l&apos;AI fosse spenta, mappe e allerte uscirebbero comunque.
        </p>

        <h3>Un esempio vero: un chilometro quadrato di Valle d&apos;Aosta</h3>
        <p>
          Prendiamo una cella reale del sistema, su un versante alpino. La sua
          &laquo;carta d&apos;identità&raquo; dice: pendenza di quasi 48 gradi
          (ripidissimo — una pista nera da sci arriva a ~30), otto frane
          storiche censite entro 500 metri, zona classificata alla massima
          pericolosità dai piani territoriali, rocce metamorfiche di media
          fragilità. Messo tutto in fila, la predisposizione risulta{" "}
          <strong>0.95 su 1</strong>: difficile immaginare un versante più
          predisposto.
        </p>
        <p>
          Un versante così non scende quasi mai sotto il livello
          &laquo;moderato&raquo;, nemmeno col sole: è la sua condizione di
          base, la sorveglianza ordinaria. È la pioggia a spingerlo verso i
          livelli d&apos;allerta veri — e puoi verificarlo tu stesso qui
          sotto.
        </p>
      </article>

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

      <article>
        <h3>Quanto è affidabile?</h3>
        <p>
          Non lo chiediamo alla fiducia: lo misuriamo contro le frane vere.
          Abbiamo &laquo;riavvolto il nastro&raquo; di tempeste del passato e
          controllato se il sistema, con i soli dati disponibili{" "}
          <em>prima</em> dell&apos;evento, avrebbe indicato i punti giusti.
          Oggi riconosce circa <strong>7 frane storiche su 10</strong> almeno
          al livello &laquo;moderato&raquo;, e nella tempesta di marzo 2009 in
          Puglia avrebbe segnalato le zone colpite con{" "}
          <strong>circa due giorni di anticipo</strong>.
        </p>
        <h3>Cosa non sa ancora fare (e lo diciamo)</h3>
        <ul>
          <li>
            <strong>I temporali-lampo</strong>: un nubifragio di mezz&apos;ora
            su un solo paese è troppo piccolo e veloce per i dati meteo
            attuali. Servono i radar meteorologici — è il prossimo cantiere.
          </li>
          <li>
            <strong>Le sorprese in pianura</strong>: la griglia ragiona per
            chilometri quadrati; una scarpata isolata dentro una cella
            pianeggiante può sfuggire alla media.
          </li>
          <li>
            <strong>Prevedere il futuro</strong>: Limen stima dove le
            condizioni somigliano a quelle che hanno già causato frane. È un
            sistema di attenzione ed early warning, non una sfera di
            cristallo.
          </li>
        </ul>
        <p className="exp-note">
          Dati: ISPRA (inventario IFFI, mosaici PAI), CNR-IRPI (catalogo
          ITALICA), Copernicus, INGV — tutti dati pubblici aperti. I parametri
          mostrati sono quelli reali di produzione.
        </p>
        <p className="exp-note">
          Vuoi capire <em>come nasce un&apos;allerta</em>, passo per passo e con
          schemi?{" "}
          <a
            href="https://github.com/agent-engineering-studio/limen/blob/main/docs/warning-logic.md"
            target="_blank"
            rel="noreferrer"
          >
            Come si innesca un&apos;allerta frana
          </a>{" "}
          spiega la logica di innesco senza bisogno di leggere il codice.
        </p>
        <ChapterFooter current={1} />
      </article>
    </div>
  );
}
