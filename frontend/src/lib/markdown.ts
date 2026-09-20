// Un renderer Markdown minimo, invece di una dipendenza.
//
// Il contenuto non arriva dall'utente: sono i file di `docs/divulgazione/`,
// scritti da noi e inclusi nel bundle a build time. Il problema che una
// libreria risolve — sanificare HTML ostile — qui non esiste, mentre quello
// che resta (titoli, elenchi, grassetto, link, blocchi di codice) sta in
// poche decine di righe. Il frontend ha quattro dipendenze a runtime: la
// quinta deve valere il suo peso.
//
// Il parsing produce una struttura, non HTML: React la rende, quindi non
// serve `dangerouslySetInnerHTML` da nessuna parte.

/** Fase del flusso «dati → punteggio → classe → avviso» evidenziata. */
export type FlowPhase = "dati" | "punteggio" | "classe" | "avviso" | "tutte";

const PHASES: readonly FlowPhase[] = ["dati", "punteggio", "classe", "avviso", "tutte"];

export interface FlowStep {
  label: string;
  detail: string;
}

export type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; text: string }
  | { kind: "diagram"; phase: FlowPhase }
  | { kind: "flow"; steps: FlowStep[] };

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "strong"; text: string }
  | { kind: "em"; text: string }
  | { kind: "code"; text: string }
  | { kind: "link"; text: string; href: string };

const MARKER = /^<!--\s*schema-fase:\s*([a-z]+)\s*-->$/;
const HEADING = /^(#{1,4})\s+(.*)$/;
const UL = /^[-*]\s+(.*)$/;
const OL = /^\d+[.)]\s+(.*)$/;

function isPhase(value: string): value is FlowPhase {
  return (PHASES as readonly string[]).includes(value);
}

/** Estrae i passi da un `flowchart` Mermaid: `A["Testo<br/>dettaglio"] --> B[...]`. */
export function parseMermaidFlow(code: string): FlowStep[] {
  const steps: FlowStep[] = [];
  const seen = new Set<string>();
  const node = /\[\s*"([^"]+)"\s*\]/g;
  let match: RegExpExecArray | null;
  while ((match = node.exec(code)) !== null) {
    const [label, ...rest] = (match[1] ?? "").split(/<br\s*\/?>/);
    const step = { label: (label ?? "").trim(), detail: rest.join(" ").trim() };
    if (!seen.has(step.label)) {
      seen.add(step.label);
      steps.push(step);
    }
  }
  return steps;
}

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  // La fase resta in sospeso fino al blocco Mermaid che la segue: su GitHub
  // il commento è invisibile e il diagramma si vede lo stesso.
  let pendingPhase: FlowPhase | null = null;
  let i = 0;

  while (i < lines.length) {
    const trimmed = (lines[i] ?? "").trim();

    if (trimmed === "") {
      i += 1;
      continue;
    }

    const marker = MARKER.exec(trimmed);
    if (marker) {
      const named = marker[1] ?? "";
      pendingPhase = isPhase(named) ? named : null;
      i += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !(lines[i] ?? "```").trim().startsWith("```")) {
        body.push(lines[i] ?? "");
        i += 1;
      }
      i += 1; // la riga di chiusura
      if (language === "mermaid") {
        if (pendingPhase !== null) {
          blocks.push({ kind: "diagram", phase: pendingPhase });
        } else {
          blocks.push({ kind: "flow", steps: parseMermaidFlow(body.join("\n")) });
        }
      } else {
        blocks.push({ kind: "code", text: body.join("\n") });
      }
      pendingPhase = null;
      continue;
    }

    const heading = HEADING.exec(trimmed);
    if (heading) {
      blocks.push({
        kind: "heading",
        level: (heading[1] ?? "#").length,
        text: heading[2] ?? "",
      });
      i += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && (lines[i] ?? "").trim().startsWith(">")) {
        body.push((lines[i] ?? "").trim().replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ kind: "quote", text: body.join(" ").trim() });
      continue;
    }

    if (UL.test(trimmed) || OL.test(trimmed)) {
      const ordered = OL.test(trimmed);
      const items: string[] = [];
      while (i < lines.length) {
        const current = lines[i] ?? "";
        const inner = current.trim();
        const item = ordered ? OL.exec(inner) : UL.exec(inner);
        if (item?.[1] !== undefined) {
          items.push(item[1]);
          i += 1;
          continue;
        }
        // Riga di continuazione: rientrata e non vuota.
        const last = items.length - 1;
        if (inner !== "" && /^\s+/.test(current) && last >= 0) {
          items[last] = `${items[last] ?? ""} ${inner}`;
          i += 1;
          continue;
        }
        break;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length) {
      const inner = (lines[i] ?? "").trim();
      if (
        inner === "" ||
        inner.startsWith("```") ||
        inner.startsWith(">") ||
        HEADING.test(inner) ||
        MARKER.test(inner) ||
        UL.test(inner) ||
        OL.test(inner)
      ) {
        break;
      }
      paragraph.push(inner);
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|<[^ >]+@?[^ >]+>|\*[^*]+\*)/;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let rest = text;
  while (rest.length > 0) {
    const match = INLINE.exec(rest);
    if (!match || match.index === undefined) {
      out.push({ kind: "text", text: rest });
      break;
    }
    if (match.index > 0) {
      out.push({ kind: "text", text: rest.slice(0, match.index) });
    }
    const token = match[0];
    if (token.startsWith("**")) {
      out.push({ kind: "strong", text: token.slice(2, -2) });
    } else if (token.startsWith("`")) {
      out.push({ kind: "code", text: token.slice(1, -1) });
    } else if (token.startsWith("[")) {
      const close = token.indexOf("](");
      out.push({
        kind: "link",
        text: token.slice(1, close),
        href: token.slice(close + 2, -1),
      });
    } else if (token.startsWith("<")) {
      // Link automatico stile Markdown: <https://…>
      const href = token.slice(1, -1);
      out.push({ kind: "link", text: href, href });
    } else {
      out.push({ kind: "em", text: token.slice(1, -1) });
    }
    rest = rest.slice(match.index + token.length);
  }
  return out.filter((part) => part.kind !== "text" || part.text !== "");
}

const REPO_BLOB = "https://github.com/agent-engineering-studio/limen/blob/main";

/**
 * Traduce un link relativo dei Markdown in qualcosa di cliccabile nella SPA.
 *
 * Le pagine si citano a vicenda con percorsi di file: dentro l'applicazione
 * devono diventare rotte, e tutto il resto (codice, LICENSE, altri documenti)
 * deve puntare al repository, altrimenti il link è morto.
 */
export function resolveHref(href: string, knownSlugs: readonly string[]): string {
  if (/^(https?:|mailto:|#)/.test(href)) {
    return href;
  }
  const [rawPath, anchor] = href.split("#");
  const path = rawPath ?? "";
  const file = path.split("/").pop() ?? "";
  if (file.endsWith(".md")) {
    const stem = file.slice(0, -3);
    const slug = stem === "README" && !path.includes("..") ? "indice" : stem;
    if (knownSlugs.includes(slug) && !path.startsWith("../..")) {
      return `#/documentazione/${slug}${anchor ? `#${anchor}` : ""}`;
    }
  }
  // Percorso relativo a docs/divulgazione/, normalizzato senza `..`.
  const parts = "docs/divulgazione".split("/");
  for (const segment of path.split("/")) {
    if (segment === "." || segment === "") continue;
    if (segment === "..") parts.pop();
    else parts.push(segment);
  }
  return `${REPO_BLOB}/${parts.join("/")}`;
}
