// Una pagina di documentazione scritta in Markdown sotto `docs/guida/`:
// indice laterale, una sotto-rotta per sezione (`#/<pagina>/<sezione>`),
// perché l'hash è già la rotta della SPA e un'ancora nuda `#sezione`
// porterebbe sulla home. La guida e le integrazioni sono due istanze.
//
// Ogni pagina esiste in italiano e in inglese (`docs/guida/*.en.md`). Le
// ancore restano quelle italiane, prese per posizione: un link condiviso
// `#/come-funziona/i-tre-motori` deve aprire la stessa sezione in entrambe
// le lingue. Un test Python tiene uguale la struttura dei due file.

import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import type { ComponentType, JSX, ReactNode } from "react";

import type { Lingua } from "../lib/i18n";
import { testi, useLingua, useTesti } from "../lib/i18n";
import type { Block, Inline } from "../lib/markdown";
import { parseInline, parseMarkdown, slugify } from "../lib/markdown";
import RiskFlowDiagram from "./RiskFlowDiagram";
import Simulatore from "./Simulatore";

// Le figure pesano: si scaricano solo quando la pagina le incontra.
const FiguraAlluvione = lazy(() => import("./figure/alluvione"));
const FiguraFrane = lazy(() => import("./figure/frane"));

const pigra = (Figura: ComponentType) => () => (
  <Suspense fallback={null}>
    <Figura />
  </Suspense>
);

/** La sezione chiesta dall'hash: `<route>/<sezione>`, o nessuna. */
export function sezioneDa(route: string, hash: string): string | null {
  if (!hash.startsWith(`${route}/`)) return null;
  return hash.slice(route.length + 1) || null;
}

function renderInline(parts: Inline[], keyPrefix: string): JSX.Element[] {
  return parts.map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    switch (part.kind) {
      case "strong":
        return <strong key={key}>{renderInline(part.parts, key)}</strong>;
      case "em":
        return <em key={key}>{renderInline(part.parts, key)}</em>;
      case "code":
        return <code key={key}>{part.text}</code>;
      case "link": {
        const external = part.href.startsWith("http");
        return (
          <a
            key={key}
            href={part.href}
            {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
          >
            {part.text}
          </a>
        );
      }
      default:
        return <span key={key}>{part.text}</span>;
    }
  });
}

function inline(text: string, key: string): JSX.Element[] {
  return renderInline(parseInline(text), key);
}

// I componenti che il Markdown incorpora con `<!-- componente: nome -->`:
// su GitHub il commento non si vede, nella SPA diventa il componente.
const COMPONENTI: Record<string, () => JSX.Element> = {
  simulatore: Simulatore,
  "figura-alluvione": pigra(FiguraAlluvione),
  "figura-frane": pigra(FiguraFrane),
};

function renderBlock(block: Block, index: number, ancora: string): JSX.Element | null {
  const key = `b${index}`;
  switch (block.kind) {
    case "heading": {
      const content = inline(block.text, key);
      const id = `guida-${ancora}`;
      if (block.level <= 1) return <h1 key={key}>{content}</h1>;
      if (block.level === 2)
        return (
          <h2 key={key} id={id}>
            {content}
          </h2>
        );
      if (block.level === 3)
        return (
          <h3 key={key} id={id}>
            {content}
          </h3>
        );
      return <h4 key={key}>{content}</h4>;
    }
    case "paragraph":
      return <p key={key}>{inline(block.text, key)}</p>;
    case "quote":
      return <blockquote key={key}>{inline(block.text, key)}</blockquote>;
    case "code":
      return (
        <pre key={key} className="guida-formula">
          <code>{block.text}</code>
        </pre>
      );
    case "diagram":
      return <RiskFlowDiagram key={key} phase={block.phase} />;
    case "flow":
      return (
        <ol className="docs-chain" key={key}>
          {block.steps.map((step) => (
            <li key={step.label}>
              <strong>{step.label}</strong>
              {step.detail ? <span> — {step.detail}</span> : null}
            </li>
          ))}
        </ol>
      );
    case "list": {
      const items = block.items.map((item, i) => (
        <li key={`${key}-${i}`}>{inline(item, `${key}-${i}`)}</li>
      ));
      return block.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
    }
    case "table":
      // Il contenitore scorre da solo: su un telefono una tabella larga non
      // deve far scorrere di lato tutta la pagina.
      return (
        <div className="guida-tabella" key={key}>
          <table>
            <thead>
              <tr>
                {block.header.map((cell, c) => (
                  <th key={c} scope="col">
                    {inline(cell, `${key}-h${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c}>{inline(cell, `${key}-${r}-${c}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "component": {
      const Componente = COMPONENTI[block.name];
      return Componente ? <Componente key={key} /> : null;
    }
  }
}

interface Voce {
  slug: string;
  title: string;
}

const T = testi(
  {
    indice: "In questa pagina",
    fonte: "Questa pagina è il file",
    fonteCoda: "del repository: stesso testo, nessuna copia.",
  },
  {
    indice: "On this page",
    fonte: "This page is the file",
    fonteCoda: "in the repository: same text, no copy.",
  },
);

/** Le ancore dei titoli (`##` e oltre), nell'ordine: quelle della versione
 *  italiana, che valgono per tutte le lingue. */
function ancore(blocks: Block[]): string[] {
  return blocks.flatMap((b) => (b.kind === "heading" && b.level >= 2 ? [slugify(b.text)] : []));
}

export interface DocPageProps {
  markdown: Record<Lingua, string>;
  /** Il percorso del Markdown nel repository, per il link alla fonte. */
  file: Record<Lingua, string>;
  /** La rotta della pagina, es. `#/come-funziona`. */
  route: string;
  /** Il nome accessibile dell'indice laterale. */
  indice: string;
  /** Quello che segue il testo, prima del link alla fonte. */
  coda?: ReactNode;
}

export default function DocPage({
  markdown,
  file,
  route,
  indice: nomeIndice,
  coda,
}: DocPageProps): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  const ancoreIt = useMemo(() => ancore(parseMarkdown(markdown.it)), [markdown.it]);
  const blocks = useMemo(() => parseMarkdown(markdown[lingua]), [markdown, lingua]);
  // Per ogni blocco titolo, la sua ancora italiana; il resto non ne ha.
  const ancoraDi = useMemo(() => {
    let k = 0;
    return blocks.map((b) => {
      if (b.kind !== "heading" || b.level < 2) return "";
      const slug = ancoreIt[k] ?? slugify(b.text);
      k += 1;
      return slug;
    });
  }, [blocks, ancoreIt]);
  const indice = useMemo<Voce[]>(
    () =>
      blocks.flatMap((b, i) =>
        b.kind === "heading" && b.level === 2 ? [{ slug: ancoraDi[i] ?? "", title: b.text }] : [],
      ),
    [blocks, ancoraDi],
  );
  const [attiva, setAttiva] = useState<string | null>(() =>
    sezioneDa(route, window.location.hash),
  );

  // L'hash porta alla sezione: all'apertura di un link condiviso e a ogni
  // clic sull'indice.
  useEffect(() => {
    const vai = (): void => {
      const slug = sezioneDa(route, window.location.hash);
      if (slug === null) return;
      setAttiva(slug);
      document.getElementById(`guida-${slug}`)?.scrollIntoView({ block: "start" });
    };
    vai();
    window.addEventListener("hashchange", vai);
    return () => window.removeEventListener("hashchange", vai);
  }, [route]);

  // Mentre si legge, l'indice segue la sezione in vista.
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visibile = entries.find((e) => e.isIntersecting);
        if (visibile) setAttiva(visibile.target.id.replace(/^guida-/, ""));
      },
      { rootMargin: "0px 0px -75% 0px" },
    );
    for (const voce of indice) {
      const el = document.getElementById(`guida-${voce.slug}`);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [indice]);

  return (
    <div className="guida">
      <nav className="guida-indice" aria-label={nomeIndice}>
        <p className="guida-indice-titolo">{t.indice}</p>
        <ol>
          {indice.map((voce) => (
            <li key={voce.slug}>
              <a
                href={`${route}/${voce.slug}`}
                className={voce.slug === attiva ? "on" : ""}
                aria-current={voce.slug === attiva ? "location" : undefined}
              >
                {voce.title}
              </a>
            </li>
          ))}
        </ol>
      </nav>
      <article className="explainer docs guida-testo">
        {blocks.map((b, i) => renderBlock(b, i, ancoraDi[i] ?? ""))}
        {coda}
        <p className="docs-source">
          {t.fonte}{" "}
          <a
            href={`https://github.com/agent-engineering-studio/limen/blob/main/${file[lingua]}`}
            target="_blank"
            rel="noreferrer"
          >
            {file[lingua]}
          </a>{" "}
          {t.fonteCoda}
        </p>
      </article>
    </div>
  );
}
