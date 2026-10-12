// La guida unica: tutto il motore in una pagina, dal testo di
// `docs/guida/limen.md` (e della sua traduzione `limen.en.md`).

import type { JSX } from "react";

import { GUIDA_FILE, GUIDA_FILE_EN, GUIDA_MARKDOWN, GUIDA_MARKDOWN_EN } from "../content/guida";
import { testi, useTesti } from "../lib/i18n";
import DocPage, { sezioneDa } from "./DocPage";

const ROUTE = "#/come-funziona";

/** La sezione chiesta dall'hash: `#/come-funziona/<sezione>`, o nessuna. */
export function sezioneDaHash(hash: string): string | null {
  return sezioneDa(ROUTE, hash);
}

const T = testi(
  {
    indice: "Indice della guida",
    approfondimenti: "Approfondimenti",
    modello: "Il modello delle frane",
    modelloTesto:
      "le curve della soglia di pioggia, del terremoto e del fuoco, con i parametri letti dal sistema in esercizio.",
    ml: "Diagnostica ML",
    mlTesto: "campione e sfidante a confronto, quando lo sfidante è acceso.",
    integrazioni: "Integrazioni",
    integrazioniTesto: "le API REST, MCP e A2A per usare i dati di Limen da un altro sistema.",
  },
  {
    indice: "Guide contents",
    approfondimenti: "Further reading",
    modello: "The landslide model",
    modelloTesto:
      "the rainfall-threshold, earthquake and fire curves, with the parameters read from the running system.",
    ml: "ML diagnostics",
    mlTesto: "champion and challenger side by side, when the challenger is on.",
    integrazioni: "Integrations",
    integrazioniTesto: "the REST, MCP and A2A APIs to use Limen's data from another system.",
  },
);

export default function GuidaPage(): JSX.Element {
  const t = useTesti(T);
  return (
    <DocPage
      markdown={{ it: GUIDA_MARKDOWN, en: GUIDA_MARKDOWN_EN }}
      file={{ it: GUIDA_FILE, en: GUIDA_FILE_EN }}
      route={ROUTE}
      indice={t.indice}
      coda={
        <>
          <h2 id="guida-approfondimenti">{t.approfondimenti}</h2>
          <ul>
            <li>
              <a href="#/modello">{t.modello}</a> — {t.modelloTesto}
            </li>
            <li>
              <a href="#/diagnostica-ml">{t.ml}</a> — {t.mlTesto}
            </li>
            <li>
              <a href="#/integrazioni">{t.integrazioni}</a> — {t.integrazioniTesto}
            </li>
          </ul>
        </>
      }
    />
  );
}
