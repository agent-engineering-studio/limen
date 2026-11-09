// "Partecipare" (#511): che cosa può fare chi non sviluppa — segnalare un
// evento, contestare un punteggio, proporre un dato — dal testo di
// `docs/guida/partecipare.md` (e `.en.md`).

import type { JSX } from "react";

import {
  PARTECIPARE_FILE,
  PARTECIPARE_FILE_EN,
  PARTECIPARE_MARKDOWN,
  PARTECIPARE_MARKDOWN_EN,
} from "../content/partecipare";
import { testi, useTesti } from "../lib/i18n";
import DocPage from "./DocPage";

const T = testi(
  { indice: "Indice della pagina Partecipare" },
  { indice: "Take part contents" },
);

export function PartecipaPage(): JSX.Element {
  const t = useTesti(T);
  return (
    <DocPage
      markdown={{ it: PARTECIPARE_MARKDOWN, en: PARTECIPARE_MARKDOWN_EN }}
      file={{ it: PARTECIPARE_FILE, en: PARTECIPARE_FILE_EN }}
      route="#/partecipare"
      indice={t.indice}
    />
  );
}

export default PartecipaPage;
