import type { JSX } from "react";

import { testi, useTesti } from "../lib/i18n";

// "Capire Limen" — chrome condiviso che lega le tre pagine in un percorso
// (corso/libro): indice in cima con evidenza del capitolo corrente, riga
// «Capitolo N di 3 · livello», «in questo capitolo», e avanti/indietro in
// fondo. Difficoltà crescente: 1 base → 2 intermedio → 3 avanzato.

export interface Chapter {
  n: number;
  hash: string;
}

export const CHAPTERS: readonly Chapter[] = [
  { n: 1, hash: "#/come-funziona" },
  { n: 2, hash: "#/modello" },
  { n: 3, hash: "#/diagnostica-ml" },
] as const;

const T = testi(
  {
    capitoli: [
      { titolo: "Come funziona", livello: "base" },
      { titolo: "Il modello", livello: "intermedio" },
      { titolo: "Diagnostica ML", livello: "avanzato" },
    ],
    percorso: "Percorso «Capire Limen»",
    kicker: (n: number) => `Capire Limen · un percorso in ${n} capitoli`,
    dove: (n: number, di: number) => `Capitolo ${n} di ${di}`,
    livello: (l: string) => ` · livello ${l}`,
    inQuesto: "In questo capitolo:",
    naviga: "Naviga tra i capitoli",
    cap: "Cap.",
  },
  {
    capitoli: [
      { titolo: "How it works", livello: "basic" },
      { titolo: "The model", livello: "intermediate" },
      { titolo: "ML diagnostics", livello: "advanced" },
    ],
    percorso: "«Understanding Limen» course",
    kicker: (n: number) => `Understanding Limen · a course in ${n} chapters`,
    dove: (n: number, di: number) => `Chapter ${n} of ${di}`,
    livello: (l: string) => ` · ${l} level`,
    inQuesto: "In this chapter:",
    naviga: "Navigate between chapters",
    cap: "Ch.",
  },
);

export function CourseHeader({
  current,
  learn,
}: {
  current: number;
  learn: string;
}): JSX.Element {
  const t = useTesti(T);
  const chapter = t.capitoli[current - 1];
  return (
    <nav className="course-head" aria-label={t.percorso}>
      <p className="course-kicker">{t.kicker(CHAPTERS.length)}</p>
      <ol className="course-toc">
        {CHAPTERS.map((c) => (
          <li key={c.n}>
            <a
              href={c.hash}
              className={c.n === current ? "on" : ""}
              aria-current={c.n === current ? "step" : undefined}
            >
              <span className="course-num">{c.n}</span>
              {t.capitoli[c.n - 1]?.titolo}
            </a>
          </li>
        ))}
      </ol>
      <p className="course-where">
        {t.dove(current, CHAPTERS.length)}
        {chapter ? t.livello(chapter.livello) : ""}
      </p>
      <p className="course-learn">
        <strong>{t.inQuesto}</strong> {learn}
      </p>
    </nav>
  );
}

export function ChapterFooter({ current }: { current: number }): JSX.Element {
  const t = useTesti(T);
  const prev = current > 1 ? CHAPTERS[current - 2] : undefined;
  const next = current < CHAPTERS.length ? CHAPTERS[current] : undefined;
  return (
    <nav className="course-foot" aria-label={t.naviga}>
      {prev ? (
        <a href={prev.hash} className="course-prev">
          ← {t.cap} {prev.n} · {t.capitoli[prev.n - 1]?.titolo}
        </a>
      ) : (
        <span />
      )}
      {next ? (
        <a href={next.hash} className="course-next">
          {t.cap} {next.n} · {t.capitoli[next.n - 1]?.titolo} →
        </a>
      ) : (
        <span />
      )}
    </nav>
  );
}
