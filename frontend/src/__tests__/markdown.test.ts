import { describe, expect, it } from "vitest";

import {
  parseInline,
  parseMarkdown,
  parseMermaidFlow,
  resolveHref,
} from "../lib/markdown";

const SLUGS = ["indice", "02-come-si-calcola-il-rischio", "glossario"];

describe("parseMarkdown", () => {
  it("riconosce titoli, paragrafi ed elenchi", () => {
    const blocks = parseMarkdown(
      "# Titolo\n\nUn paragrafo\nsu due righe.\n\n- primo\n- secondo\n",
    );
    expect(blocks).toEqual([
      { kind: "heading", level: 1, text: "Titolo" },
      { kind: "paragraph", text: "Un paragrafo su due righe." },
      { kind: "list", ordered: false, items: ["primo", "secondo"] },
    ]);
  });

  it("attacca le righe rientrate alla voce di elenco precedente", () => {
    const blocks = parseMarkdown("- una voce\n  che continua qui\n");
    expect(blocks).toEqual([
      { kind: "list", ordered: false, items: ["una voce che continua qui"] },
    ]);
  });

  it("trasforma il marcatore piu il blocco mermaid in uno schema con fase", () => {
    const blocks = parseMarkdown(
      "<!-- schema-fase: punteggio -->\n\n```mermaid\nflowchart LR\n  A[\"x\"]\n```\n",
    );
    expect(blocks).toEqual([{ kind: "diagram", phase: "punteggio" }]);
  });

  it("un mermaid senza marcatore diventa una catena leggibile, non codice", () => {
    const blocks = parseMarkdown(
      '```mermaid\nflowchart TD\n  A["AreaResolver<br/>quali celle"] --> B["MeteoFetch<br/>che tempo fa"]\n```\n',
    );
    expect(blocks).toEqual([
      {
        kind: "flow",
        steps: [
          { label: "AreaResolver", detail: "quali celle" },
          { label: "MeteoFetch", detail: "che tempo fa" },
        ],
      },
    ]);
  });

  it("tiene i blocchi di codice non mermaid come codice", () => {
    const blocks = parseMarkdown("```\nmake init\n```\n");
    expect(blocks).toEqual([{ kind: "code", text: "make init" }]);
  });

  it("una fase sconosciuta non diventa uno schema muto", () => {
    const blocks = parseMarkdown(
      '<!-- schema-fase: inesistente -->\n\n```mermaid\nflowchart LR\n  A["x"]\n```\n',
    );
    expect(blocks[0]?.kind).toBe("flow");
  });
});

describe("parseInline", () => {
  it("separa grassetto, codice e link", () => {
    expect(parseInline("il **peso** è `0,35` — vedi [pagina](./02.md)")).toEqual([
      { kind: "text", text: "il " },
      { kind: "strong", parts: [{ kind: "text", text: "peso" }] },
      { kind: "text", text: " è " },
      { kind: "code", text: "0,35" },
      { kind: "text", text: " — vedi " },
      { kind: "link", text: "pagina", href: "./02.md" },
    ]);
  });

  it("riconosce i link automatici fra parentesi angolari", () => {
    expect(parseInline("portale <https://idrogeo.isprambiente.it/>")).toEqual([
      { kind: "text", text: "portale " },
      {
        kind: "link",
        text: "https://idrogeo.isprambiente.it/",
        href: "https://idrogeo.isprambiente.it/",
      },
    ]);
  });
});

describe("parseInline, link dentro il grassetto", () => {
  // L'indice scrive ogni voce come `**[titolo](path)**`: se il grassetto non
  // guarda dentro, la pagina pubblica le parentesi quadre invece del link.
  it("tiene il link cliccabile quando è dentro il grassetto", () => {
    expect(parseInline("**[Limen in una pagina](./01-limen-in-una-pagina.md)**")).toEqual([
      {
        kind: "strong",
        parts: [
          {
            kind: "link",
            text: "Limen in una pagina",
            href: "./01-limen-in-una-pagina.md",
          },
        ],
      },
    ]);
  });

  it("non confonde due grassetti separati con uno solo", () => {
    const parts = parseInline("**uno** e **due**");
    expect(parts.filter((p) => p.kind === "strong")).toHaveLength(2);
  });
});

describe("resolveHref", () => {
  it("manda i rimandi fra pagine sulla rotta interna", () => {
    expect(resolveHref("./02-come-si-calcola-il-rischio.md", SLUGS)).toBe(
      "#/documentazione/02-come-si-calcola-il-rischio",
    );
  });

  it("tiene l'ancora quando c'è", () => {
    expect(resolveHref("./glossario.md#backtest", SLUGS)).toBe(
      "#/documentazione/glossario#backtest",
    );
  });

  it("manda al repository quello che non è una pagina della sezione", () => {
    expect(resolveHref("../../src/limen/config/hazards/landslide.yaml", SLUGS)).toBe(
      "https://github.com/agent-engineering-studio/limen/blob/main/src/limen/config/hazards/landslide.yaml",
    );
  });

  it("lascia stare gli indirizzi assoluti", () => {
    expect(resolveHref("https://example.org", SLUGS)).toBe("https://example.org");
  });
});

describe("parseMermaidFlow", () => {
  it("non ripete un nodo citato due volte", () => {
    expect(parseMermaidFlow('A["Uno"] --> B["Due"]\n  B["Due"] --> C["Tre"]')).toHaveLength(
      3,
    );
  });
});
