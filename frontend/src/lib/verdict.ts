// La frase che risponde alla domanda con cui si apre la pagina: «c'è
// qualcosa di cui preoccuparsi, adesso?».
//
// Prima la colonna si apriva con quattro riquadri di pari peso — quadro
// nazionale, previsioni, celle sopra soglia, legenda — e nessuno dei quattro
// rispondeva. Chi guarda una mappa di rischio non vuole un archivio: vuole
// sapere se oggi è un giorno qualunque.

import { locale, testi, type Lingua } from "./i18n";

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

const T = testi(
  {
    aree: (n: string, uno: boolean) => `${n} ${uno ? "area" : "aree"}`,
    alta: (aree: string) => `${aree} in classe Alta o superiore`,
    notaAlta: "Segui le indicazioni della Protezione Civile del tuo Comune.",
    moderata: (aree: string) => `${aree} in classe Moderata`,
    notaModerata:
      "Nessuna area in classe Alta. Vale la pena tenere d'occhio la zona se continua a piovere.",
    quieto: "Nessuna area sopra la soglia di attenzione",
    rigaQuieta: "nessuna area sopra la soglia",
    nessunPericolo: (n: number) => `Per nessuno dei ${n} pericoli sorvegliati.`,
  },
  {
    aree: (n: string, uno: boolean) => `${n} ${uno ? "area" : "areas"}`,
    alta: (aree: string) => `${aree} in High class or above`,
    notaAlta: "Follow the guidance of your municipality's Civil Protection.",
    moderata: (aree: string) => `${aree} in Moderate class`,
    notaModerata:
      "No area in High class. Worth keeping an eye on the area if the rain continues.",
    quieto: "No area above the attention threshold",
    rigaQuieta: "no area above the threshold",
    nessunPericolo: (n: number) => `For none of the ${n} monitored hazards.`,
  },
);

const plurale = (n: number, lingua: Lingua): string =>
  T[lingua].aree(n.toLocaleString(locale(lingua)), n === 1);

/**
 * Tre esiti e non cinque: le classi del rischio sono per la mappa, dove si
 * confrontano celle vicine. Qui serve sapere se agire, e le azioni sono
 * tre — niente, tieni d'occhio, segui il piano comunale.
 */
export function verdictFromTotals(totals: VerdictTotals, lingua: Lingua = "it"): Verdict {
  const t = T[lingua];
  if (totals.high_or_above > 0) {
    return {
      tone: "alert",
      text: t.alta(plurale(totals.high_or_above, lingua)),
      note: t.notaAlta,
    };
  }
  if (totals.moderate > 0) {
    return {
      tone: "watch",
      text: t.moderata(plurale(totals.moderate, lingua)),
      note: t.notaModerata,
    };
  }
  return {
    tone: "quiet",
    // «Nessuna area sopra soglia» e non «nessun rischio»: il rischio di
    // fondo di un territorio franoso non va a zero perché oggi non piove, e
    // scriverlo sarebbe la rassicurazione sbagliata.
    text: t.quieto,
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
export function verdictFromHazards(
  blocchi: HazardTotals[],
  lingua: Lingua = "it",
): MultiVerdict {
  const t = T[lingua];
  const lines: HazardLine[] = blocchi.map((b) => {
    const v = verdictFromTotals(b.totals, lingua);
    return {
      hazard: b.hazard,
      label: b.label_it,
      text: v.tone === "quiet" ? t.rigaQuieta : v.text.toLowerCase(),
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
        text: t.quieto,
        note: blocchi.length > 1 ? t.nessunPericolo(blocchi.length) : undefined,
      },
      lines: ordinate,
    };
  }
  const base = verdictFromTotals(
    blocchi.find((b) => b.hazard === peggiore.hazard)?.totals ?? {
      high_or_above: 0,
      moderate: 0,
    },
    lingua,
  );
  return {
    headline: { ...base, text: `${peggiore.label}: ${base.text}` },
    lines: ordinate,
  };
}
