# Figure anatomy nella SPA di Limen

La skill `anatomy` (vendorizzata in `.claude/skills/anatomy/`, MIT,
upstream e commit in `UPSTREAM`) è la regola per *come* si disegna. Questo
file dice *dove* le figure vivono in Limen, *quali* meccanismi meritano
una figura, e *come* si verificano su questa macchina.

## L'idea, applicata a Limen

Anatomy non disegna riquadri e frecce: inventa un oggetto fisico il cui
funzionamento **è** il concetto. In Limen il vantaggio è doppio: le formule
dei motori hanno una forma (somma, prodotto, massimo, soglia, ricorsione)
e ogni forma ha un meccanismo che la fa davvero — un mixer somma, una
valvola a navetta prende il massimo, un nottolino scatta a una soglia, un
contachilometri porta avanti uno stato. Se l'oggetto non *fa* la formula,
è un'illustrazione, non una figura: cambia oggetto.

## Catalogo

Proposte, non vincoli: prima di costruire, rileggi la sezione e lo YAML, e
se l'oggetto non mappa uno a uno la formula vera, cambialo. Le chiavi YAML
indicano da dove il `model.ts` prende i numeri.

| Nome (marcatore) | Sezione | Concetto | Oggetto | Cosa si muove, e cosa vuol dire | Numeri da |
|---|---|---|---|---|---|
| `figura-frane` | I tre motori | Somma pesata S·M·E·F·H → punteggio → classe | Banco di cinque cursori (fader) con corsa proporzionale al peso, che spingono un'unica cremagliera sotto un comparatore a quadrante con la scala a cinque settori | Alzi un cursore, la cremagliera avanza del suo peso; l'ago entra nel settore della classe | `landslide.yaml`: `weights`, `classes` |
| `figura-soglia-caine` | I tre motori | Soglia intensità-durata: sopra la curva, innesco | Pluviometro a vaschetta basculante con tamburo contatore e una camma sagomata sulla curva di Caine; un nottolino scatta quando l'accumulo supera la camma per quella durata | Ogni basculata è 1 tick di pioggia; il nottolino scatta = soglia superata | `landslide.yaml`: `caine`, `rain_floor` |
| `figura-alluvione` | I tre motori | `suscettibilità × max(pluviale, fluviale)`, sotto `floor` zero | Due condotte (pioggia, fiume) in una **valvola a navetta** (passa la pressione più alta: è un massimo fisico), poi una paratoia la cui apertura è la suscettibilità; sotto `floor` la paratoia è chiusa a fine corsa | La navetta si sposta verso il ramo più forte; la paratoia scala il flusso; il manometro a valle è il punteggio | `flood.yaml`: `susceptibility`, `pluvial`, `fluvial` |
| `figura-incendio` | I tre motori | `fwi_norm × (base + fuel·f + slope·s)`, pesi a somma 1 | Lampada da banco: un reostato principale (FWI) a monte di tre trimmer in parallelo (base, combustibile, pendenza) | Il reostato a zero spegne tutto qualunque sia il terreno: il tempo **comanda**, il terreno modula | `wildfire.yaml`: `weights`, `fwi` |
| `figura-catena-fwi` | I tre motori | Catena ricorsiva FFMC/DMC/DC per nodo meteo, reset oltre `max_gap_days` | Contatore meccanico a tre tamburi con manovella giornaliera; un fermo libera i tamburi a zero se la manovella salta troppi giorni | Ogni giro di manovella è un giorno; i tamburi portano lo stato di ieri | `wildfire.yaml`: `fwi.max_gap_days`, `fwi.node_spacing_deg` |
| `figura-non-misurato` | Come leggere la mappa | «Non misurato» ≠ «nessun pericolo» | Strumento di bordo con **bandierina OFF** (quella degli strumenti aeronautici): senza segnale cade la bandiera e l'ago si ferma, ma la bandiera copre la scala | Togli il segnale: la bandierina grigia copre il quadrante invece di lasciare l'ago a zero | `CLAUDE.md` «Non misurato» |
| `figura-griglia` | Il territorio in celle | Celle da 1 km → comuni → zone di allerta | Cassa tipografica: una griglia di scomparti (celle) divisa da listelli (comuni) dentro cassetti più grandi (zone di allerta) | Il puntatore accende uno scomparto, poi il suo comune, poi la sua zona; il readout dice quante celle | seed + `comuni` (conteggi letti dal DB o da `CLAUDE.md`) |
| `figura-fonti` | Il layer dati | Fonti lente e veloci, ognuna con cadenza e licenza; una fonte degradata dà un risultato neutro | Schedario a cassetti: in basso i dati lenti (IFFI, PAI, DEM, CORINE, geologia), in alto un alimentatore a nastro perforato per quelli veloci (meteo, radar, INGV, FIRMS) | Apri un cassetto: il readout dice fonte, cadenza, licenza; un cassetto con la spia spenta è una fonte degradata | `docs/divulgazione/04-*`, `integrations/` |
| `figura-tre-cadenze` | La previsione | Orario (solo V1), asincrono (spiegazioni), notturno (shadow, drift, retrain), previsione per cella 4 volte al giorno | Movimento d'orologio con tre treni di ingranaggi: una ruota veloce oraria, uno scappamento che libera un dente alla volta (le spiegazioni, una AOI per volta), una camma lenta delle 24 h | Le ruote girano a velocità vere in scala; il readout dice quale job scatta | `SCHEDULER__*` in `config/settings.py`, `CLAUDE.md` «Three cadences» |
| `figura-campione-sfidante` | Il layer machine learning | Il campione decide, lo sfidante registra e basta | Due strumenti sullo stesso collettore d'ingresso: solo l'ago del campione è collegato alla leva d'uscita; lo sfidante scrive su un registratore a carta | Cambia l'ingresso: si muovono entrambi, ma solo uno muove la leva | `docs/ml.md`, `shadow_challenger.py` |
| `figura-ai-non-autoritativa` | Il layer AI | L'LLM riformula i numeri, non li cambia | Una macchina per scrivere che legge uno strumento sigillato attraverso un oblò: c'è un passaggio di luce, nessun leveraggio di ritorno | Batti un tasto: il testo esce, l'ago non si muove | `CLAUDE.md` «LLM is non-authoritative» |
| `figura-pannello` | Integrazioni (panoramica) | REST, tile, MCP, A2A, notifiche — tutti in sola lettura sul punteggio; scrittura dietro `MCP_ADMIN_TOKEN`, fail-closed | Centralino a spine (patch panel): una presa per superficie; le prese di scrittura stanno dietro un interruttore a chiave, e senza chiave l'interruttore non c'è | Inserisci una spina: il readout dice protocollo, endpoint, lettura/scrittura | `api/endpoints/`, `mcp/server.py`, `a2a/skills.py` |
| `figura-a2a-stream` | Integrazioni (A2A) | Ciclo di vita del task: submitted → working → artifact-update → completed | Stazione di posta pneumatica: una capsula attraversa quattro stazioni, ogni stazione un evento SSE | La capsula avanza a ogni evento; il readout mostra il JSON dell'evento | `a2a/service.py` |

Ordine consigliato (valore per ora di lavoro): `figura-alluvione`,
`figura-frane`, `figura-non-misurato`, `figura-pannello`,
`figura-incendio`. Le figure sono tutte **Figure** (40-80 parti) nella
scala di anatomy; nessuna richiede WebGL (la pioggia e l'acqua possono
restare SVG); una Hero va concordata con l'utente.

## Dove vivono

Il layout React di anatomy (`references/react.md`), adattato a Vite: qui
non ci sono server component, quindi tutto è client, ma la regola resta —
la geometria si calcola **una volta al caricamento del modulo**, solo le
parti che cambiano forma si ricostruiscono per frame.

```
frontend/src/components/iso/            il kit, copiato una volta e non modificato
  iso-kit.ts  iso.css  react/draw.tsx  react/live.tsx  LICENSE (MIT, upstream)
frontend/src/components/figure/<nome>/
  model.ts      modello puro: numeri veri (con la chiave YAML accanto), readout
  view.ts       costanti di mondo e proiezione (fitProjection)
  geometry.ts   tutti i path statici, calcolati al load
  frame.ts      solo se una parte cambia forma
  art.tsx       le parti statiche come JSX, con key stabili
  live.tsx      ref, loop, puntatore e tastiera, aria, readout
  <nome>.css    token della figura, scoped (.fig-<nome> { … })
  index.tsx     <Plate fig title hint readout keys caption> … — export default
frontend/src/__tests__/figura-<nome>.test.tsx   il modello e il rendering
```

**Il kit c'è già** (dalla prima figura, `figura-alluvione`); ricopialo solo per aggiornarlo:

1. Copia `iso-kit.ts`, `iso.css`, `react/draw.tsx`, `react/live.tsx` e
   `LICENSE` da `.claude/skills/anatomy/kit/` in
   `frontend/src/components/iso/`; aggiusta l'import di `draw.tsx`
   (`"../iso-kit"` resta valido con questo layout).
2. Aggiungi `"src/components/iso"` agli `ignores` di
   `frontend/eslint.config.js`: è codice vendorizzato, si aggiorna
   ricopiandolo, non si riformatta.
3. Se `tsc -b` segnala errori dentro `iso/` per flag più severi del
   `tsconfig` della SPA, correggi il minimo indispensabile e annota in
   testa al file cosa è stato toccato rispetto all'upstream.

**Registrazione**: in `DocPage.tsx`, `COMPONENTI` riceve
`"figura-<nome>": Figura<Nome>`. Importa la figura con `React.lazy` e
avvolgila in `<Suspense fallback={null}>`: la guida è già un bundle grosso
e un utente su telefono non deve scaricare dieci figure per leggere il
primo paragrafo.

## Regole Limen sopra quelle di anatomy

- **Solo tema scuro.** La SPA è la «sala operativa» (fondo scuro, accento
  `#ff8a1f`): wrapper `className="iso"` senza `data-theme`. Il tono `lit`
  di anatomy resta bianco; l'accento arancio è riservato a ciò che si può
  premere, come nel resto della SPA.
- **Il colore entra solo quando è il soggetto**: le classi di rischio da
  `RISK_COLOR_BY_LEVEL`/`riskColorsFor()` di `risk-colors.ts`, le identità
  di pericolo da `HAZARD_HUE`, il grigio di «non misurato» è `COLORE_IGNOTO`
  (lo stesso delle celle non valutate).
- **Parole fuori dal disegno, in due lingue**: titolo, hint, readout e
  didascalia nel cartiglio, dichiarati con `testi(it, en)` e letti con
  `useTesti` (`frontend/src/lib/i18n.tsx`); il readout formatta i numeri
  con `useLocale()`. La didascalia è vera e cita la sorgente dei numeri.
  Il test della figura la monta in tutte e due le lingue
  (`render(..., { lingua: "en" })` di `test-utils.tsx`).
- **390 px**: la guida si legge soprattutto da telefono (vedi il commento
  in `RiskFlowDiagram.tsx`). La figura deve leggersi a quella larghezza o
  non entra.
- **Accessibilità**: `aria-label` sul cartiglio con quello che la figura
  dimostra; readout in `aria-live="polite"`; tastiera come in anatomy;
  movimento fermo sotto `prefers-reduced-motion`.
- **Un test per figura**: il `model.ts` è puro, quindi si testa con
  Vitest — almeno un caso che rifà a mano la formula del motore con i
  numeri dello YAML (es. alluvione: con pluviale 0,6 e fluviale 0,3 la
  navetta sta sul pluviale e il punteggio è `susc × 0,6`). Se il motore
  cambia formula, quel test è il punto in cui la figura se ne accorge.

## Verifica su questa macchina

Sull'host non ci sono né Node né Chrome (memoria `frontend-needs-docker-node`).

- **Gate della SPA**: `node:22` con `--user`, come in SKILL.md § 5.
- **Catture e controlli anatomy**: un container con Node e Chromium, la
  SPA servita da Vite dentro lo stesso container:

```bash
# Chrome dentro il container gira solo senza sandbox: un wrapper lo aggiunge
# senza toccare gli script vendorizzati di anatomy.
printf '#!/bin/sh\nexec $(ls -d /ms-playwright/chromium-*/chrome-linux/chrome | head -1) --no-sandbox "$@"\n' > "$SCRATCH/chrome.sh"
chmod +x "$SCRATCH/chrome.sh"
docker run --rm --user "$(id -u):$(id -g)" --ipc=host -e HOME=/tmp \
  -v "$SCRATCH/fe":/fe -v "$SCRATCH/shots":/shots -v "$SCRATCH/chrome.sh":/chrome.sh \
  -v /srv/appdata/git/limen/.claude/skills/anatomy:/anatomy:ro \
  mcr.microsoft.com/playwright:v1.55.0-noble sh -c '
    export CHROME_PATH=/chrome.sh
    cd /fe && ./node_modules/.bin/vite --port 5173 --strictPort --host 127.0.0.1 >/tmp/vite.log 2>&1 &
    sleep 4
    S=/anatomy/scripts
    U="http://127.0.0.1:5173/#/come-funziona/i-tre-motori"
    SEL=".fig-alluvione .iso-plate"
    node $S/capture.mjs "$U" --select "$SEL" --out /shots/desk.png --wait 3500 --times 3000,6000
    node $S/capture.mjs "$U" --select "$SEL" --zoom 250,250,120,90 --out /shots/zoom.png
    node $S/capture.mjs "$U" --select "$SEL" --out /shots/still.png --reduced
    node $S/lines.mjs "$U" --select "$SEL" --wait 4000 --out /shots/lines.png'
```

`$SCRATCH/fe` è una copia di `frontend/` con `npm ci` fatto (il
`node_modules` del repository non ha `@mantine/*`): `rsync -a --exclude
node_modules --exclude dist frontend/ $SCRATCH/fe/` prima di ogni giro. Le
figure sono `React.lazy`: dai a `lines.mjs` almeno `--wait 4000`, o non trova
la tavola. Per il telefono, la guida oggi esce dallo schermo a 390 px anche
senza figure (la colonna del testo è più larga del viewport): verifica la
figura restringendo `.guida-testo` a 342 px con un `["eval", …]` di
`drive.mjs`, finché quel layout non è corretto.

Le catture vanno nello scratchpad (`$SCRATCH/shots`), mai nel repository, e
si **leggono tutte** con Read, più i close-up a 4× di ogni giunto (`--zoom`),
come chiede `references/verify.md` di anatomy. Se Chrome esce con SIGABRT,
manca il wrapper `--no-sandbox` o `--ipc=host`; se l'immagine Playwright non
c'è, `docker image ls | grep playwright` dice quale versione è già sulla
macchina.
