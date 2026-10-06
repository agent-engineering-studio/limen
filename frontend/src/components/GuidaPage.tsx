// La guida unica: tutto il motore in una pagina, dal testo di
// `docs/guida/limen.md`. Ogni sezione ha un indirizzo suo
// (`#/come-funziona/<sezione>`), perché l'hash è già la rotta della SPA e
// un'ancora nuda `#sezione` porterebbe sulla home.

import { useEffect, useMemo, useState } from "react";
import type { JSX } from "react";

import { GUIDA_FILE, GUIDA_MARKDOWN } from "../content/guida";
import type { Block, Inline } from "../lib/markdown";
import { parseInline, parseMarkdown, slugify } from "../lib/markdown";
import RiskFlowDiagram from "./RiskFlowDiagram";
import Simulatore from "./Simulatore";

const ROUTE = "#/come-funziona";

/** La sezione chiesta dall'hash: `#/come-funziona/<sezione>`, o nessuna. */
export function sezioneDaHash(hash: string): string | null {
  if (!hash.startsWith(`${ROUTE}/`)) return null;
  return hash.slice(ROUTE.length + 1) || null;
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

const COMPONENTI: Record<string, () => JSX.Element> = {
  simulatore: Simulatore,
};

function renderBlock(block: Block, index: number): JSX.Element | null {
  const key = `b${index}`;
  switch (block.kind) {
    case "heading": {
      const content = inline(block.text, key);
      const id = `guida-${slugify(block.text)}`;
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

export default function GuidaPage(): JSX.Element {
  const blocks = useMemo(() => parseMarkdown(GUIDA_MARKDOWN), []);
  const indice = useMemo<Voce[]>(
    () =>
      blocks.flatMap((b) =>
        b.kind === "heading" && b.level === 2 ? [{ slug: slugify(b.text), title: b.text }] : [],
      ),
    [blocks],
  );
  const [attiva, setAttiva] = useState<string | null>(() =>
    sezioneDaHash(window.location.hash),
  );

  // L'hash porta alla sezione: all'apertura di un link condiviso e a ogni
  // clic sull'indice.
  useEffect(() => {
    const vai = (): void => {
      const slug = sezioneDaHash(window.location.hash);
      if (slug === null) return;
      setAttiva(slug);
      document.getElementById(`guida-${slug}`)?.scrollIntoView({ block: "start" });
    };
    vai();
    window.addEventListener("hashchange", vai);
    return () => window.removeEventListener("hashchange", vai);
  }, []);

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
      <nav className="guida-indice" aria-label="Indice della guida">
        <p className="guida-indice-titolo">In questa pagina</p>
        <ol>
          {indice.map((voce) => (
            <li key={voce.slug}>
              <a
                href={`${ROUTE}/${voce.slug}`}
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
        {blocks.map(renderBlock)}
        <h2 id="guida-approfondimenti">Approfondimenti</h2>
        <ul>
          <li>
            <a href="#/modello">Il modello delle frane</a> — le curve della soglia di
            pioggia, del terremoto e del fuoco, con i parametri letti dal sistema in
            esercizio.
          </li>
          <li>
            <a href="#/diagnostica-ml">Diagnostica ML</a> — campione e sfidante a
            confronto, quando lo sfidante è acceso.
          </li>
          <li>
            <a href="#/integrazioni">Integrazioni</a> — le API REST, MCP e A2A per
            usare i dati di Limen da un altro sistema.
          </li>
        </ul>
        <p className="docs-source">
          Questa pagina è il file{" "}
          <a
            href={`https://github.com/agent-engineering-studio/limen/blob/main/${GUIDA_FILE}`}
            target="_blank"
            rel="noreferrer"
          >
            {GUIDA_FILE}
          </a>{" "}
          del repository: stesso testo, nessuna copia.
        </p>
      </article>
    </div>
  );
}
