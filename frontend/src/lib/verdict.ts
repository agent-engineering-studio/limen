// La frase che risponde alla domanda con cui si apre la pagina: «c'è
// qualcosa di cui preoccuparsi, adesso?».
//
// Prima la colonna si apriva con quattro riquadri di pari peso — quadro
// nazionale, previsioni, celle sopra soglia, legenda — e nessuno dei quattro
// rispondeva. Chi guarda una mappa di rischio non vuole un archivio: vuole
// sapere se oggi è un giorno qualunque.

export type VerdictTone = "quiet" | "watch" | "alert";

export interface Verdict {
  tone: VerdictTone;
  /** La riga grande. */
  text: string;
  /** La riga piccola sotto, quando serve un'avvertenza. */
  note?: string;
}

export interface VerdictTotals {
  high_or_above: number;
  moderate: number;
}

const plurale = (n: number, uno: string, molti: string): string =>
  `${n.toLocaleString("it-IT")} ${n === 1 ? uno : molti}`;

/**
 * Tre esiti e non cinque: le classi del rischio sono per la mappa, dove si
 * confrontano celle vicine. Qui serve sapere se agire, e le azioni sono
 * tre — niente, tieni d'occhio, segui il piano comunale.
 */
export function verdictFromTotals(totals: VerdictTotals): Verdict {
  if (totals.high_or_above > 0) {
    return {
      tone: "alert",
      text: `${plurale(totals.high_or_above, "area", "aree")} in classe Alta o superiore`,
      note: "Segui le indicazioni della Protezione Civile del tuo Comune.",
    };
  }
  if (totals.moderate > 0) {
    return {
      tone: "watch",
      text: `${plurale(totals.moderate, "area", "aree")} in classe Moderata`,
      note: "Nessuna area in classe Alta. Vale la pena tenere d'occhio la zona se continua a piovere.",
    };
  }
  return {
    tone: "quiet",
    // «Nessuna area sopra soglia» e non «nessun rischio»: il rischio di
    // fondo di un territorio franoso non va a zero perché oggi non piove, e
    // scriverlo sarebbe la rassicurazione sbagliata.
    text: "Nessuna area sopra la soglia di attenzione",
  };
}
