import { useCallback } from "react";

import "../../iso/iso.css";
import "./alluvione.css";
import { testi, useLingua, useLocale, useTesti } from "../../../lib/i18n";
import { RISK_LABEL_BY_LEVEL } from "../../../lib/risk-colors";
import { Plate } from "../../iso/react/draw";
import { AlluvioneLive } from "./live";
import type { Stato } from "./model";
import { FINESTRA_ORE, FLOOR, PIENA_ORDINARIA, PIENA_SATURA, RIPOSO, SATURAZIONE_MM, SOGLIA_MM, statoDi } from "./model";

const T = testi(
  {
    titolo: "Allagamento",
    suggerimento: "Su e giù sopra una parte",
    etichetta:
      "Un banco idraulico: un pluviometro e un idrometro spingono in una valvola a navetta, che lascia passare solo la spinta più forte; una paratoia la riduce secondo la suscettibilità della cella, e un manometro segna il punteggio sulle cinque classi.",
    chiavi: ["La spinta che passa", "Il punteggio, sulle classi dell'allagamento"],
    vince: { pioggia: "passa la pioggia", fiume: "passa il fiume", nessuno: "nessuna spinta" },
    chiusa: "paratoia chiusa",
    didascalia: (n: (v: number, d?: number) => string) =>
      `Una cella dentro la mappa ISPRA, su suolo saturo e senza cemento. Il pluviometro alza la sua asta da 0 a 1 fra ${n(SOGLIA_MM, 0)} e ${n(SATURAZIONE_MM, 0)} mm di pioggia in ${FINESTRA_ORE} ore; l'idrometro fra ${n(PIENA_ORDINARIA, 1)} e ${n(PIENA_SATURA, 0)} volte la piena ordinaria del suo fiume. La valvola a navetta lascia passare solo la spinta più forte — un massimo, non una somma — e la paratoia la riduce in proporzione alla suscettibilità; sotto ${n(FLOOR, 2)} resta chiusa, perché un crinale non si allaga. Il manometro segna le classi a 0,10 · 0,25 · 0,45 · 0,70. Numeri da config/hazards/flood.yaml.`,
  },
  {
    titolo: "Flooding",
    suggerimento: "Up and down over a part",
    etichetta:
      "A hydraulic bench: a rain gauge and a river gauge push into a shuttle valve that lets only the stronger push through; a sluice gate scales it by the cell's susceptibility, and a pressure gauge shows the score on the five classes.",
    chiavi: ["The push that gets through", "The score, on the flooding classes"],
    vince: { pioggia: "rain gets through", fiume: "river gets through", nessuno: "no push" },
    chiusa: "gate closed",
    didascalia: (n: (v: number, d?: number) => string) =>
      `A cell inside the ISPRA map, on saturated soil with no sealed ground. The rain gauge raises its rod from 0 to 1 between ${n(SOGLIA_MM, 0)} and ${n(SATURAZIONE_MM, 0)} mm of rain in ${FINESTRA_ORE} hours; the river gauge between ${n(PIENA_ORDINARIA, 1)} and ${n(PIENA_SATURA, 0)} times its river's ordinary high flow. The shuttle valve lets only the stronger push through — a maximum, not a sum — and the gate scales it by the susceptibility; below ${n(FLOOR, 2)} it stays shut, because a ridge does not flood. The gauge marks the classes at 0.10 · 0.25 · 0.45 · 0.70. Numbers from config/hazards/flood.yaml.`,
  },
);

export default function FiguraAlluvione() {
  const t = useTesti(T);
  const { lingua } = useLingua();
  const locale = useLocale();
  const n = useCallback(
    (v: number, d = 2) => v.toLocaleString(locale, { minimumFractionDigits: d, maximumFractionDigits: d }),
    [locale],
  );
  const etichette = RISK_LABEL_BY_LEVEL[lingua];

  const readoutOf = useCallback(
    (s: Stato) =>
      `${n(s.pioggiaMm, 0)} mm · ${n(s.rapporto, 1)}× · s ${n(s.suscettibilita)} → ${n(s.punteggio)} ${etichette[s.livello].toLowerCase()}`,
    [etichette, n],
  );
  const spokenOf = useCallback(
    (s: Stato) =>
      `${s.chiusa ? t.chiusa : t.vince[s.ramo]}: ${etichette[s.livello].toLowerCase()}.`,
    [etichette, t],
  );

  return (
    <div className="iso fig-alluvione">
      <Plate
        fig="Fig 1"
        title={t.titolo}
        hint={t.suggerimento}
        readout={readoutOf(statoDi(RIPOSO))}
        keys={[
          { mark: "raised", label: t.chiavi[0]! },
          { mark: "lit", label: t.chiavi[1]! },
        ]}
        caption={t.didascalia(n)}
      >
        <AlluvioneLive label={t.etichetta} readoutOf={readoutOf} spokenOf={spokenOf} />
      </Plate>
    </div>
  );
}
