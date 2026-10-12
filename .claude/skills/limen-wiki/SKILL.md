---
name: limen-wiki
description: Aggiorna le due pagine di documentazione della SPA, in italiano e in inglese — «Come funziona» (`#/come-funziona`, fonti `docs/guida/limen.md` + `limen.en.md`) e «Integrazioni» (`#/integrazioni`, fonti `docs/guida/integrazioni.md` + `integrazioni.en.md`) — con una documentazione molto dettagliata di come funziona Limen, ricavata da tutto quello che il repository già scrive (docs/, docs/divulgazione/, README.md, CLAUDE.md, YAML dei pericoli, codice delle API/MCP/A2A) e arricchita di figure isometriche interattive costruite con la skill `anatomy`. Usala quando l'utente chiede di "aggiornare la wiki", "tradurre la guida in inglese", "aggiornare come funziona", "aggiornare le integrazioni", "documentare Limen nella SPA", "allineare la guida al codice", "aggiungere una figura/un disegno alla guida", o invoca /limen-wiki. Argomenti opzionali: `guida` | `integrazioni` | `tutte` (default), `figure=N` (quante figure nuove costruire, default: le propone senza costruirle), `solo-testo`, il nome di una figura del catalogo (`figura-alluvione`).
---

# limen-wiki

Due pagine, una regola: **la pagina è il Markdown in `docs/guida/`**. La SPA
lo incorpora a build time, GitHub lo mostra così com'è; una sola fonte,
nessuna copia. Questa skill tiene quelle due pagine allineate a quello che
Limen fa *oggi* — non a quello che un documento di tre mesi fa diceva che
avrebbe fatto.

## Dove vivono le pagine

| Cosa | Dove |
|---|---|
| Testo di «Come funziona» | `docs/guida/limen.md` (IT, fonte) + `limen.en.md` (EN, traduzione) |
| Testo di «Integrazioni» | `docs/guida/integrazioni.md` (IT, fonte) + `integrazioni.en.md` (EN) |
| Lingua attiva, testi dei componenti | `frontend/src/lib/i18n.tsx` (`useLingua`, `testi(it, en)`/`useTesti`) |
| Generati per la SPA (**mai a mano**) | `frontend/src/content/guida.ts`, `integrazioni.ts` (costanti `*_MARKDOWN` e `*_MARKDOWN_EN`) ← `make docs-bundle` |
| Renderer comune (indice, sotto-rotte, componenti incorporati) | `frontend/src/components/DocPage.tsx` |
| Le due pagine | `GuidaPage.tsx`, `IntegrationsPage.tsx` (istanze di `DocPage`) |
| Componenti incorporabili (simulatore, figure) | registro `COMPONENTI` in `DocPage.tsx`, marcatore `<!-- componente: nome -->` nel Markdown |
| Figure anatomy | `frontend/src/components/figure/<nome>/` + kit in `frontend/src/components/iso/` |
| Inventario (cosa è cambiato, cosa manca) | `.claude/skills/limen-wiki/scripts/inventario.py` |
| Mappa fonti → sezioni | `references/fonti.md` |
| Catalogo figure + integrazione anatomy nella SPA | `references/figure.md` |

Il Markdown supportato è quello di `frontend/src/lib/markdown.ts`: titoli
`#`-`####`, paragrafi, liste, tabelle (niente `\|` nelle celle: il parser
non lo gestisce), citazioni `>`, blocchi di codice, link, `**`/`*`/`` ` ``,
e Mermaid **solo** come catena lineare `flowchart LR A[...] --> B[...]`
(diventa la catena di riquadri; qualunque altro grafo Mermaid si perde).
Ogni `##` diventa una voce d'indice e un indirizzo `#/<pagina>/<slug>`.

## Regole che governano tutto

1. **Il codice vince sul documento.** Ordine di autorità: codice e YAML
   (`src/limen/config/hazards/*.yaml`) → invarianti di `CLAUDE.md` →
   `docs/*.md` → `docs/divulgazione/`. I documenti in `docs/` sono spesso
   più vecchi del codice (l'inventario lo dice con le date). Quando un
   documento e il codice non sono d'accordo, la pagina scrive quello che
   fa il codice, e la discrepanza va **nel riepilogo all'utente** con
   `file:riga` di entrambi — non si corregge in silenzio `docs/*.md`, che
   ha il suo proprietario.
2. **Ogni numero ha una fonte che si può aprire.** Pesi, soglie, cutoff,
   cadenze, conteggi: letti dallo YAML, dal codice o da un report misurato
   (`docs/artifacts/`, `reports/`), mai ricordati. Se un numero non si
   trova, non si scrive. Una metrica di successo va con il suo tasso di
   base (memoria `hit-rate-needs-base-rate`).
3. **Gli indirizzi esistenti non si rompono.** Prima di rinominare o
   togliere un `##`, cerca chi ci punta:
   `grep -rn "#/come-funziona/\|#/integrazioni/" frontend/src docs README.md`.
   `GuidaPage.test.tsx` esige i titoli dei layer (dati, motori, previsione,
   ML, AI, territorio) e le ancore `limiti-dichiarati`, `i-tre-motori`;
   `IntegrationsPage.test.tsx` esige il titolo e i nomi degli strumenti.
   Un rename che serve davvero aggiorna i link e i test nello stesso giro.
4. **Il registro è quello della guida.** Italiano, divulgativo ma preciso:
   ogni sezione apre con la frase che dice l'essenziale (in grassetto), poi
   il *perché*, poi il *come*, poi i numeri. Si scrive per chi deve
   *decidere* con quel numero (un sindaco, un tecnico comunale, un
   volontario), non per chi l'ha programmato: i nomi di tabelle, job e
   variabili d'ambiente stanno in «Integrazioni» o in un inciso, non nel
   filo del discorso della guida. Niente marketing, niente «rivoluzionario».
5. **I limiti si dichiarano.** Limen *affianca* l'allerta ufficiale e non
   la sostituisce; «non misurato» non è «nessun pericolo»; l'LLM riformula
   e non decide; il V1 deterministico è il campione. Ogni nuova capacità
   descritta porta con sé il suo limite noto (vedi «Limiti dichiarati» e le
   avvertenze di `CLAUDE.md` § Phase boundary).
6. **Licenze e attribuzioni restano.** Ogni sezione che parla di alluvione
   o mostra dati CEMS porta la dicitura Copernicus («Contains modified
   Copernicus Emergency Management Service information [Anno]») e non
   presenta l'output come un allerta alluvione ufficiale.
7. **«Integrazioni» non pubblica segreti né topologia interna.** Nomi delle
   variabili sì (`MCP_ADMIN_TOKEN`), valori mai; porte solo come default su
   loopback, mai IP o hostname del server; nessun percorso di `.env`.
8. **Due lingue, una struttura.** L'italiano è la fonte; l'inglese è la
   sua traduzione e si aggiorna **nello stesso giro**, mai dopo. I due file
   hanno la stessa sequenza di titoli, marcatori, blocchi di codice e
   colonne di tabella: le ancore inglesi sono quelle italiane prese per
   posizione (`DocPage.tsx`), quindi un titolo in più da una parte sola
   sposta tutti i link condivisi. `test_english_has_the_same_structure`
   lo verifica. Nell'inglese (en-GB): virgola decimale → punto, nessun
   valore cambiato, nomi istituzionali italiani tenuti con una glossa alla
   prima occorrenza («Protezione Civile (Italy's civil-protection
   department)», «municipality (comune)»), classi none/low/moderate/high/
   very high, link interni con lo slug italiano.
9. **Colori: solo quelli del sistema.** Una figura o tabella che mostra le
   classi usa `frontend/src/lib/risk-colors.ts`; le identità dei pericoli
   usano `HAZARD_HUE`. Mai un esadecimale ricopiato.

## Procedura

### 1. Inventario

```bash
python3 .claude/skills/limen-wiki/scripts/inventario.py
```

Dice: quali fonti sono più recenti della pagina che le racconta (`NUOVO`);
quali rotte REST, strumenti MCP e skill A2A esistono nel codice e
`integrazioni.md` non nomina (`✗`); quali figure sono marcate nel Markdown
e quali registrate. Con `guida` o `integrazioni` lavora solo su quella.

### 2. Leggere

Leggi per intero la pagina da aggiornare, poi le fonti che la mappa in
`references/fonti.md` associa alle sezioni toccate — tutte le `NUOVO`, e per
le altre almeno i paragrafi che contengono numeri. Per le superfici `✗`
leggi il codice (endpoint + modello di risposta in `src/limen/api/schemas.py`,
firma e docstring dello strumento MCP, `skills.py` per A2A), non la doc.
Con molte fonti, lancia agenti `Explore` in parallelo, uno per area
(motori, dati, previsione/ML/AI, API), chiedendo **fatti con `file:riga`**,
non riassunti.

### 3. Scrivere il Markdown

- Aggiorna in posto, sezione per sezione; non riscrivere da zero ciò che è
  già giusto. La struttura di riferimento delle due pagine è in
  `references/fonti.md`.
- «Molto dettagliata» vuol dire: per ogni meccanismo, *cosa entra* (quali
  dati, da dove, con che cadenza), *cosa succede* (formula leggibile, con i
  pesi veri), *cosa esce* (classe, avviso, dove si vede), *cosa può andare
  storto* (degrado, limiti). Un esempio numerico seguito fino in fondo vale
  più di tre paragrafi generici.
- Poi porta ogni modifica in `*.en.md`, sezione per sezione: traduci
  il paragrafo cambiato, non riscrivere la pagina. Se il file inglese
  manca o è molto indietro, traducilo per intero con un agente dedicato
  (le regole sono al punto 8) e verifica la struttura prima di andare avanti.
- Ogni figura entra con un marcatore `<!-- componente: figura-<nome> -->`
  subito dopo il paragrafo che spiega lo stesso meccanismo: su GitHub il
  marcatore non si vede, quindi **il testo deve reggersi da solo**. Lo
  stesso marcatore va nella stessa posizione del file inglese.

### 4. Figure (anatomy)

Leggi `references/figure.md` e poi carica la skill `anatomy`
(`Skill("anatomy")`): le sue regole valgono per intero (oggetto reale,
modello puro, ≥ 40 parti, ordine del pittore, verifica a 4×).

- Senza `figure=N`: **non costruire**. Proponi all'utente le 2-3 figure del
  catalogo che rendono di più per le sezioni toccate, con taglia e tempo
  stimati (regola anatomy: Figure 30-90 min, Hero 2-4 h).
- Con `figure=N` o il nome di una figura: costruiscine al massimo N, una
  alla volta, ciascuna verificata prima della successiva. Comunica taglia e
  tempo prima di iniziare e `date` a ogni passo, come chiede anatomy.
- Il modello della figura (`model.ts`) prende i numeri dallo YAML o dal
  codice e scrive accanto a ogni costante la chiave da cui viene
  (`// landslide.yaml: weights.meteo`). Il readout mostra solo numeri di
  quel modello.

### 5. Rigenerare e verificare

```bash
make docs-bundle
uv run pytest tests/unit/test_docs_bundle.py -q
uv run python scripts/check_doc_links.py
docker run --rm --user "$(id -u):$(id -g)" \
  -v /srv/appdata/git/limen/frontend:/app -w /app -e HOME=/tmp node:22 \
  sh -c "./node_modules/.bin/eslint . && ./node_modules/.bin/vitest run"
```

`tsc -b` in quel container oggi fallisce per i moduli `@mantine/*` assenti
dal `node_modules` locale (non per questa skill): filtra il suo output sui
file toccati (`| grep -E 'DocPage|figure/|iso/|content/'`) e riportalo.
Per le figure, le catture e i controlli di anatomy girano in un container
con Chromium — comandi in `references/figure.md` § Verifica. Leggi ogni PNG.

### 6. Riepilogo all'utente

- sezioni aggiornate/aggiunte, per pagina e lingua, con una riga su cosa è cambiato;
- **discrepanze documento ↔ codice** trovate (con `file:riga`), da
  correggere a parte;
- figure costruite (con l'esito delle verifiche) e figure proposte;
- esito dei gate, con l'output se qualcosa è rosso.

Non committare e non pushare se l'utente non lo chiede; quando lo chiede,
branch dedicato e push via token HTTPS (memoria `git-push-needs-https-token`).
