import { useEffect, useState } from "react";

import { DOC_PAGES } from "../content/divulgazione";
import type { Block, Inline } from "../lib/markdown";
import { parseInline, parseMarkdown, resolveHref } from "../lib/markdown";
import RiskFlowDiagram from "./RiskFlowDiagram";

const SLUGS = DOC_PAGES.map((page) => page.slug);

/** Slug richiesto dall'hash: `#/documentazione/<slug>`, altrimenti l'indice. */
export function slugFromHash(hash: string): string {
  const wanted = hash.replace(/^#\/documentazione\/?/, "").split("#")[0] ?? "";
  return SLUGS.includes(wanted) ? wanted : DOC_PAGES[0].slug;
}

function renderInline(parts: Inline[], keyPrefix: string): JSX.Element[] {
  return parts.map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    switch (part.kind) {
      case "strong":
        return <strong key={key}>{part.text}</strong>;
      case "em":
        return <em key={key}>{part.text}</em>;
      case "code":
        return <code key={key}>{part.text}</code>;
      case "link": {
        const href = resolveHref(part.href, SLUGS);
        const external = href.startsWith("http");
        return (
          <a
            key={key}
            href={href}
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

function renderBlock(block: Block, index: number): JSX.Element {
  const key = `b${index}`;
  switch (block.kind) {
    case "heading": {
      const inline = renderInline(parseInline(block.text), key);
      if (block.level <= 1) return <h1 key={key}>{inline}</h1>;
      if (block.level === 2) return <h2 key={key}>{inline}</h2>;
      if (block.level === 3) return <h3 key={key}>{inline}</h3>;
      return <h4 key={key}>{inline}</h4>;
    }
    case "paragraph":
      return <p key={key}>{renderInline(parseInline(block.text), key)}</p>;
    case "quote":
      return (
        <blockquote key={key}>{renderInline(parseInline(block.text), key)}</blockquote>
      );
    case "code":
      return (
        <pre key={key}>
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
        <li key={`${key}-${i}`}>{renderInline(parseInline(item), `${key}-${i}`)}</li>
      ));
      return block.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
    }
  }
}

export function DocsPage(): JSX.Element {
  const [slug, setSlug] = useState(() => slugFromHash(window.location.hash));

  useEffect(() => {
    const onHash = (): void => setSlug(slugFromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Cambiare pagina senza tornare in cima lascia il lettore a metà di un
  // testo che non ha ancora visto.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [slug]);

  const page = DOC_PAGES.find((candidate) => candidate.slug === slug) ?? DOC_PAGES[0];
  const blocks = parseMarkdown(page.markdown);

  return (
    <div className="explainer docs">
      <nav className="docs-nav" aria-label="Pagine della documentazione">
        {DOC_PAGES.map((candidate) => (
          <a
            key={candidate.slug}
            href={`#/documentazione/${candidate.slug}`}
            className={candidate.slug === page.slug ? "on" : ""}
            aria-current={candidate.slug === page.slug ? "page" : undefined}
          >
            {candidate.title}
          </a>
        ))}
      </nav>
      <article className="docs-body">{blocks.map(renderBlock)}</article>
      <p className="docs-source">
        Questa pagina è il file{" "}
        <a
          href={`https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/${page.file}`}
          target="_blank"
          rel="noreferrer"
        >
          docs/divulgazione/{page.file}
        </a>{" "}
        del repository: stesso testo, nessuna copia.
      </p>
    </div>
  );
}

export default DocsPage;
