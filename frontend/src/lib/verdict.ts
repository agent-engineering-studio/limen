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

export interface HazardTotals {
  hazard: string;
  label_it: string;
  totals: VerdictTotals;
  computed_at: string | null;
}

export interface HazardLine {
  hazard: string;
  label: string;
  /** Cosa dice questo pericolo, in una riga. */
  text: string;
  tone: VerdictTone;
  computed_at: string | null;
}

export interface MultiVerdict {
  /** Il peggiore fra i tre: è la riga grande. */
  headline: Verdict;
  /** Tutti e tre, nell'ordine in cui vanno letti: prima chi ha qualcosa da
   *  dire. Sono la lettura unica che prima richiedeva due clic e la memoria
   *  del numero visto prima. */
  lines: HazardLine[];
}

const PESO: Record<VerdictTone, number> = { alert: 2, watch: 1, quiet: 0 };

/**
 * I tre indici letti insieme.
 *
 * Il titolo nomina il pericolo, che con un pericolo solo non serviva: «1.085
 * aree in classe Alta» senza dire di cosa è la metà di un'informazione, e a
 * chi legge la metà mancante è quella che decide cosa fare.
 */
export function verdictFromHazards(blocchi: HazardTotals[]): MultiVerdict {
  const lines: HazardLine[] = blocchi.map((b) => {
    const v = verdictFromTotals(b.totals);
    return {
      hazard: b.hazard,
      label: b.label_it,
      text: v.tone === "quiet" ? "nessuna area sopra la soglia" : v.text.toLowerCase(),
      tone: v.tone,
      computed_at: b.computed_at,
    };
  });

  // Prima chi ha qualcosa da dire, poi in ordine stabile: senza lo spareggio
  // sul nome due pericoli a pari tono si scambierebbero di posto a ogni
  // aggiornamento e la colonna sembrerebbe muoversi da sola.
  const ordinate = [...lines].sort(
    (a, b) => PESO[b.tone] - PESO[a.tone] || a.hazard.localeCompare(b.hazard),
  );

  const peggiore = ordinate[0];
  if (peggiore === undefined || peggiore.tone === "quiet") {
    return {
      headline: {
        tone: "quiet",
        text: "Nessuna area sopra la soglia di attenzione",
        note:
          blocchi.length > 1
            ? `Per nessuno dei ${blocchi.length} pericoli sorvegliati.`
            : undefined,
      },
      lines: ordinate,
    };
  }
  const base = verdictFromTotals(
    blocchi.find((b) => b.hazard === peggiore.hazard)?.totals ?? {
      high_or_above: 0,
      moderate: 0,
    },
  );
  return {
    headline: { ...base, text: `${peggiore.label}: ${base.text}` },
    lines: ordinate,
  };
}
