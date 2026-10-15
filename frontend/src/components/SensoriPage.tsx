// "Sensori" — i due broker MQTT (allerte e sensori) e le regole della rete dei
// sensori dei cittadini, dal testo di `docs/guida/sensori.md` (e `.en.md`).

import type { JSX } from "react";

import {
  SENSORI_FILE,
  SENSORI_FILE_EN,
  SENSORI_MARKDOWN,
  SENSORI_MARKDOWN_EN,
} from "../content/sensori";
import { testi, useTesti } from "../lib/i18n";
import DocPage from "./DocPage";

const T = testi({ indice: "Indice della pagina sensori" }, { indice: "Sensors contents" });

export function SensoriPage(): JSX.Element {
  const t = useTesti(T);
  return (
    <DocPage
      markdown={{ it: SENSORI_MARKDOWN, en: SENSORI_MARKDOWN_EN }}
      file={{ it: SENSORI_FILE, en: SENSORI_FILE_EN }}
      route="#/sensori"
      indice={t.indice}
    />
  );
}

export default SensoriPage;
