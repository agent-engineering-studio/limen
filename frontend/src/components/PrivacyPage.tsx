// "Dati personali" (#494): l'informativa pubblica, dal testo di
// `docs/guida/privacy.md` (e `.en.md`).

import type { JSX } from "react";

import {
  PRIVACY_FILE,
  PRIVACY_FILE_EN,
  PRIVACY_MARKDOWN,
  PRIVACY_MARKDOWN_EN,
} from "../content/privacy";
import { testi, useTesti } from "../lib/i18n";
import DocPage from "./DocPage";

const T = testi(
  { indice: "Indice dei dati personali" },
  { indice: "Personal data contents" },
);

export function PrivacyPage(): JSX.Element {
  const t = useTesti(T);
  return (
    <DocPage
      markdown={{ it: PRIVACY_MARKDOWN, en: PRIVACY_MARKDOWN_EN }}
      file={{ it: PRIVACY_FILE, en: PRIVACY_FILE_EN }}
      route="#/privacy"
      indice={t.indice}
    />
  );
}

export default PrivacyPage;
