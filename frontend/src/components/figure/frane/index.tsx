import { useCallback } from "react";

import "../../iso/iso.css";
import "./frane.css";
import { testi, useLingua, useLocale, useTesti } from "../../../lib/i18n";
import { RISK_LABEL_BY_LEVEL } from "../../../lib/risk-colors";
import { Plate } from "../../iso/react/draw";
import { FraneLive } from "./live";
import type { Componente, Stato } from "./model";
import { COMPONENTI, PESI, RIPOSO, statoDi } from "./model";

const LETTERA: Record<Componente, string> = { s: "S", m: "M", e: "E", f: "F", h: "H" };

const T = testi(
  {
    titolo: "Frane",
    suggerimento: "Destra e sinistra su un carrello",
    etichetta:
      "Una slitta composta: cinque carrelli impilati, ciascuno scorre sopra quello sotto per una corsa lunga quanto il suo peso. L'indice del carrello in cima legge la somma pesata sulla scala delle classi.",
    chiavi: ["Un componente: la sua corsa è il suo peso", "L'indice: la somma, sulle classi delle frane"],
    nomi: { s: "il posto", m: "la pioggia", e: "il terremoto", f: "il fuoco", h: "l'acqua" } as Record<Componente, string>,
    didascalia: (pesi: string) =>
      `Il motore frane è una somma pesata, e una slitta composta la fa da sé: ogni carrello scorre sopra quello sotto per al più il suo peso, quindi l'ultimo si trova esattamente alla somma. Dal basso: ${pesi}. Una pioggia forte sposta più di un terremoto perché il suo carrello ha più corsa. La scala segna le classi a 0,15 · 0,35 · 0,55 · 0,75. Su una cella con sensori in situ entra anche K, e i cinque pesi si riducono: la figura mostra il caso senza sensori. Numeri da config/hazards/landslide.yaml.`,
  },
  {
    titolo: "Landslides",
    suggerimento: "Left and right on a carriage",
    etichetta:
      "A compound slide: five stacked carriages, each sliding on the one below it by a travel as long as its weight. The pointer on the top carriage reads the weighted sum on the class scale.",
    chiavi: ["A component: its travel is its weight", "The pointer: the sum, on the landslide classes"],
    nomi: { s: "the place", m: "the rain", e: "the earthquake", f: "the fire", h: "the water" } as Record<Componente, string>,
    didascalia: (pesi: string) =>
      `The landslide engine is a weighted sum, and a compound slide does it by itself: each carriage slides on the one below by at most its weight, so the last one sits exactly at the sum. From the bottom: ${pesi}. Heavy rain moves it more than an earthquake because its carriage has more travel. The scale marks the classes at 0.15 · 0.35 · 0.55 · 0.75. On a cell with in-situ sensors K joins in and the five weights shrink: the figure shows the case without sensors. Numbers from config/hazards/landslide.yaml.`,
  },
);

export default function FiguraFrane() {
  const t = useTesti(T);
  const { lingua } = useLingua();
  const locale = useLocale();
  const n = useCallback((v: number, d = 2) => v.toLocaleString(locale, { minimumFractionDigits: d, maximumFractionDigits: d }), [locale]);
  const etichette = RISK_LABEL_BY_LEVEL[lingua];

  const readoutOf = useCallback(
    (s: Stato) => `${COMPONENTI.map((c) => `${LETTERA[c]} ${n(s.valori[c], 1)}`).join(" ")} → ${n(s.punteggio)} ${etichette[s.livello].toLowerCase()}`,
    [etichette, n],
  );
  const spokenOf = useCallback(
    (s: Stato, scelta: Componente) => `${LETTERA[scelta]}, ${t.nomi[scelta]}: ${etichette[s.livello].toLowerCase()}.`,
    [etichette, t],
  );
  const pesi = COMPONENTI.map((c) => `${LETTERA[c]} ${t.nomi[c]} ${n(PESI[c])}`).join(", ");

  return (
    <div className="iso fig-frane">
      <Plate
        fig="Fig 2"
        title={t.titolo}
        hint={t.suggerimento}
        readout={readoutOf(statoDi(RIPOSO))}
        keys={[
          { mark: "raised", label: t.chiavi[0]! },
          { mark: "lit", label: t.chiavi[1]! },
        ]}
        caption={t.didascalia(pesi)}
      >
        <FraneLive label={t.etichetta} readoutOf={readoutOf} spokenOf={spokenOf} />
      </Plate>
    </div>
  );
}
