// "Integrazioni" — pagina tecnica per sviluppatori e gateway agentici, dal
// testo di `docs/guida/integrazioni.md` (e di `integrazioni.en.md`).

import type { JSX } from "react";

import {
  INTEGRAZIONI_FILE,
  INTEGRAZIONI_FILE_EN,
  INTEGRAZIONI_MARKDOWN,
  INTEGRAZIONI_MARKDOWN_EN,
} from "../content/integrazioni";
import { testi, useTesti } from "../lib/i18n";
import DocPage from "./DocPage";

const T = testi({ indice: "Indice delle integrazioni" }, { indice: "Integrations contents" });

export function IntegrationsPage(): JSX.Element {
  const t = useTesti(T);
  return (
    <DocPage
      markdown={{ it: INTEGRAZIONI_MARKDOWN, en: INTEGRAZIONI_MARKDOWN_EN }}
      file={{ it: INTEGRAZIONI_FILE, en: INTEGRAZIONI_FILE_EN }}
      route="#/integrazioni"
      indice={t.indice}
    />
  );
}

export default IntegrationsPage;
