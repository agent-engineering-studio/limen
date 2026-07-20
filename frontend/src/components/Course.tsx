// "Capire Limen" — chrome condiviso che lega le tre pagine in un percorso
// (corso/libro): indice in cima con evidenza del capitolo corrente, riga
// «Capitolo N di 3 · livello», «in questo capitolo», e avanti/indietro in
// fondo. Difficoltà crescente: 1 base → 2 intermedio → 3 avanzato.

export interface Chapter {
  n: number;
  hash: string;
  title: string;
  level: string;
}

export const CHAPTERS: readonly Chapter[] = [
  { n: 1, hash: "#/come-funziona", title: "Come funziona", level: "base" },
  { n: 2, hash: "#/modello", title: "Il modello", level: "intermedio" },
  { n: 3, hash: "#/diagnostica-ml", title: "Diagnostica ML", level: "avanzato" },
] as const;

export function CourseHeader({
  current,
  learn,
}: {
  current: number;
  learn: string;
}): JSX.Element {
  const chapter = CHAPTERS[current - 1];
  return (
    <nav className="course-head" aria-label="Percorso «Capire Limen»">
      <p className="course-kicker">Capire Limen · un percorso in {CHAPTERS.length} capitoli</p>
      <ol className="course-toc">
        {CHAPTERS.map((c) => (
          <li key={c.n}>
            <a
              href={c.hash}
              className={c.n === current ? "on" : ""}
              aria-current={c.n === current ? "step" : undefined}
            >
              <span className="course-num">{c.n}</span>
              {c.title}
            </a>
          </li>
        ))}
      </ol>
      <p className="course-where">
        Capitolo {current} di {CHAPTERS.length}
        {chapter ? ` · livello ${chapter.level}` : ""}
      </p>
      <p className="course-learn">
        <strong>In questo capitolo:</strong> {learn}
      </p>
    </nav>
  );
}

export function ChapterFooter({ current }: { current: number }): JSX.Element {
  const prev = current > 1 ? CHAPTERS[current - 2] : undefined;
  const next = current < CHAPTERS.length ? CHAPTERS[current] : undefined;
  return (
    <nav className="course-foot" aria-label="Naviga tra i capitoli">
      {prev ? (
        <a href={prev.hash} className="course-prev">
          ← Cap. {prev.n} · {prev.title}
        </a>
      ) : (
        <span />
      )}
      {next ? (
        <a href={next.hash} className="course-next">
          Cap. {next.n} · {next.title} →
        </a>
      ) : (
        <span />
      )}
    </nav>
  );
}
