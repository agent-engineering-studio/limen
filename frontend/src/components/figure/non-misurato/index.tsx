import { useCallback } from "react";

import "../../iso/iso.css";
import "./non-misurato.css";
import { testi, useLingua, useLocale, useTesti } from "../../../lib/i18n";
import { RISK_LABEL_BY_LEVEL } from "../../../lib/risk-colors";
import { Plate } from "../../iso/react/draw";
import { NonMisuratoLive } from "./live";
import type { Lettura } from "./model";
import { GIRO, letturaDi } from "./model";

const T = testi(
  {
    titolo: "Non misurato",
    suggerimento: "Clic: stacca il cavo",
    etichetta:
      "Due strumenti identici collegati alla stessa centralina meteo. Al secondo si stacca il cavo: invece di lasciare l'ago a zero, come per una cella calma, cade una bandierina grigia che copre il quadrante.",
    chiavi: ["La bandierina: «non misurato», il grigio della mappa", "L'ago: il punteggio, quando il dato c'è"],
    nonMisurato: "non misurato",
    detto: { si: "Il secondo strumento riceve il dato.", no: "Il secondo strumento non riceve il dato: bandierina giù, cella grigia, fuori dai conteggi." },
    didascalia:
      "Per un motore che moltiplica, un dato mancante vale zero, esattamente come una cella calma: sulla mappa le due sarebbero identiche, ed è l'unico errore che un sistema di allerta farebbe in direzione rassicurante. Limen tiene accanto al punteggio un segnale «misurato» (il meteo per l'incendio, pioggia o portata per gli allagamenti): quando manca, la cella si dipinge con lo stesso grigio di quelle mai valutate ed esce dall'indice di attenzione del comune, invece di abbassarlo.",
  },
  {
    titolo: "Not measured",
    suggerimento: "Click: pull the cable",
    etichetta:
      "Two identical instruments wired to the same weather box. The second one loses its cable: instead of leaving the needle at zero, as for a calm cell, a grey flag drops over the dial.",
    chiavi: ["The flag: «not measured», the map's grey", "The needle: the score, when the data is there"],
    nonMisurato: "not measured",
    detto: { si: "The second instrument receives the data.", no: "The second instrument receives no data: flag down, grey cell, out of the counts." },
    didascalia:
      "For an engine that multiplies, missing data is worth zero, exactly like a calm cell: on the map the two would look the same, and it is the one mistake an alert system would make in the reassuring direction. Limen keeps a «measured» signal next to the score (the weather for wildfire, rain or river flow for flooding): when it is missing, the cell is painted the same grey as cells never assessed and leaves the municipality's attention index instead of lowering it.",
  },
);

export default function FiguraNonMisurato() {
  const t = useTesti(T);
  const { lingua } = useLingua();
  const locale = useLocale();
  const etichette = RISK_LABEL_BY_LEVEL[lingua];
  const n = useCallback((v: number) => v.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }), [locale]);

  const parola = useCallback(
    (l: Lettura) => (l.misurato && l.livello ? `${n(l.punteggio)} ${etichette[l.livello].toLowerCase()}` : `— ${t.nonMisurato}`),
    [etichette, n, t],
  );
  const readoutOf = useCallback((a: Lettura, b: Lettura) => `A ${parola(a)} · B ${parola(b)}`, [parola]);
  const spokenOf = useCallback((b: Lettura) => (b.misurato ? t.detto.si : t.detto.no), [t]);

  const primo = GIRO[0]!;
  return (
    <div className="iso fig-nm">
      <Plate
        fig="Fig 3"
        title={t.titolo}
        hint={t.suggerimento}
        readout={readoutOf(letturaDi({ segnale: primo.a }), letturaDi({ segnale: primo.b }))}
        keys={[
          { mark: "lit", label: t.chiavi[0]! },
          { mark: "raised", label: t.chiavi[1]! },
        ]}
        caption={t.didascalia}
      >
        <NonMisuratoLive label={t.etichetta} readoutOf={readoutOf} spokenOf={spokenOf} />
      </Plate>
    </div>
  );
}
