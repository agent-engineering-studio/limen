---
name: limen-fact-check
description: Verifica sui principali quotidiani online italiani le notizie di frane, alluvioni e incendi boschivi, le confronta con le previsioni che Limen aveva calcolato prima dell'evento (ore di anticipo, classe, dati, perché) e crea o aggiorna la verifica corrispondente nella pagina blog «Verifiche» del sito (`#/verifiche`), con fonti e foto a licenza libera. Usala quando l'utente chiede di "fare il fact check", "verificare le notizie", "aggiornare le verifiche", "quanto prima Limen aveva visto la frana/alluvione/incendio di …", o invoca /limen-fact-check. Argomenti opzionali: pericolo (frana|alluvione|incendio), giorni all'indietro (default 3, max 13), un evento preciso ("incendio di Matera del 10 ottobre").
---

# limen-fact-check

Per ogni evento reale riportato dalla stampa: **è successo davvero? Limen l'aveva previsto? Con quante ore di anticipo, su quali dati, perché?** Il risultato, quando Limen l'aveva previsto, è un articolo in italiano e in inglese nella pagina «Verifiche» della SPA.

Le regole che governano tutto:

1. **Sulla pagina vanno solo gli eventi previsti in anticipo, con le ore di anticipo.** Diventa un file JSON — e quindi un articolo — **solo** l'evento con esito `anticipata` (§5). Tutto il resto non ha file e non compare in nessun punto della pagina, né come voce né come conteggio: gli eventi scartati al fact check (§2), i `non_verificabile`, le `contemporanea` e le `mancata`. Questi si riportano soltanto all'utente, nel riepilogo finale, con esito e motivo. La pagina non mostra riquadri d'inefficienza: è una scelta dell'utente, da non rimettere in discussione.
2. **Ogni articolo dichiara le ore di anticipo** (`previsione.anticipo_ore_moderato` e, se c'è, `anticipo_ore_alto`) e le dice nel titolo o nel sommario. Un articolo senza ore di anticipo non esiste: se manca il numero, l'evento non è `anticipata`.
3. **Ogni articolo è bilingue: italiano e inglese.** I campi in italiano restano dove sono; la traduzione inglese sta nel blocco `en` (§8). Un file senza `en` completo non è finito.
4. **Ogni evento verificato entra nel registro, qualunque sia l'esito** (§8b). La pagina mostra solo gli `anticipata`; il registro `verifiche_eventi` (migrazione 074) tiene anche `contemporanea`, `mancata` e `non_verificabile`, con la misura di Limen congelata prima che la retention la cancelli. Sono i mancati a dire dove il modello sbaglia. Le frane verificate vanno anche in `landslide_events` (`source = 'stampa'`), il truth set del backtest. Restano fuori solo gli eventi scartati al fact check (§2): non sono verità.

## Dove vive la pagina

| Cosa | Dove |
|---|---|
| Una verifica = un file JSON | `frontend/src/content/verifiche/<slug>.json` |
| Le foto della verifica | `frontend/public/verifiche/<slug>/<nome>.jpg` → `src: "/verifiche/<slug>/<nome>.jpg"` |
| Tipi (lo schema del JSON) | `frontend/src/content/verifiche.ts` (`Verifica`) |
| Pagina (indice + articolo) | `frontend/src/components/VerifichePage.tsx`, rotta `#/verifiche` e `#/verifiche/<slug>`; la lingua è quella del selettore in testata (`lib/i18n`, anche `?lang=en`): l'italiano dalla radice del JSON, l'inglese dal blocco `en` |
| Query dell'anticipo | `src/limen/data/repos/anticipo.sql`, lanciata con `uv run limen anticipo` (§4) |
| Raccolta automatica | job `limen-raccolta-eventi` (#347): ogni mattina Google News → estrattore Claude → due testate → registro; candidati in `candidati_eventi` (084) |
| Registro degli eventi verificati | tabella `verifiche_eventi` (migrazione 074), scritta da `limen registra-verifica` (`src/limen/cli/registra_verifica.py`) |

Il contenuto della pagina entra nel bundle a build time (`import.meta.glob`): per la pagina **niente migrazioni, niente endpoint**. Se `VerifichePage.tsx` o `verifiche.ts` mancassero (repo vecchio), fermati e dillo: non ricrearli a memoria.

## Vincolo duro: la retention

`risk_assessments` tiene **14 giorni** (`ASSESSMENTS_RETENTION_DAYS`), poi la partizione viene cancellata. Un evento più vecchio di ~13 giorni non è più verificabile: lo storico delle previsioni non esiste più. La query restituisce `storico_dal`; se l'evento è precedente, l'esito è `non_verificabile` — non `mancata` — e l'evento **non ha articolo** (resta nel riepilogo all'utente e nel registro, §8b). Per la stessa ragione il registro va scritto **nella stessa passata** del fact check: due settimane dopo, la misura da congelare non esiste più.

## Procedura

### 0. Prima, cosa ha già raccolto il job

Dal #347 la raccolta gira da sola ogni mattina. Prima di cercare, guarda cosa c'è già: gli eventi verificati in `verifiche_eventi`, e in `candidati_eventi` quelli rimasti con `stato = 'una_testata'` (una fonte sola) o `'comune_ignoto'`. Il lavoro a mano serve soprattutto qui: trovare la seconda fonte o il comune per un candidato, e scrivere gli articoli degli `anticipata`, che il job non pubblica.

### 1. Trovare le notizie

Carica WebSearch/WebFetch con `ToolSearch("select:WebSearch,WebFetch")`. Cerca nella finestra richiesta (default: ultimi 3 giorni), per ogni pericolo, lanciando le ricerche in parallelo:

- **frana**: `frana`, `smottamento`, `colata di fango`, `movimento franoso`, `strada chiusa per frana`
- **alluvione**: `alluvione`, `esondazione`, `allagamenti`, `bomba d'acqua`, `fiume esondato`
- **incendio**: `incendio boschivo`, `incendio di vegetazione`, `Canadair`, `ettari bruciati`

Testate nazionali: ANSA, Corriere della Sera, la Repubblica, La Stampa, Il Sole 24 Ore, Il Messaggero, Il Fatto Quotidiano, Rai News, Sky TG24, TGCom24, Il Post. Regionali per la zona dell'evento (es. La Gazzetta del Mezzogiorno, Il Mattino, Il Resto del Carlino, La Nazione, Il Secolo XIX, Il Gazzettino, L'Unione Sarda, Giornale di Sicilia, La Nuova del Sud, TRM). Fonti istituzionali come conferma: Protezione Civile (nazionale e regionale), Vigili del Fuoco (`@emergenzavvf`), Regioni, Comuni, Copernicus EMS.

### 2. Verificare la notizia (il fact check vero)

Un evento entra solo se:

- **almeno due fonti indipendenti** (due testate che non si limitano a ribattere la stessa ANSA), **oppure** una testata + una fonte istituzionale;
- il **luogo** è risolvibile a uno o più comuni;
- l'**ora** è ricostruibile almeno alla mezza giornata (mattina/pomeriggio/notte). Se l'ora è ignota, usa il mezzogiorno locale e scrivilo nel testo.

Un evento che non soddisfa tutte e tre le condizioni **non è verificato: nessun file**, solo una riga nel riepilogo all'utente. Scarta e non pubblicare:

- un'**allerta meteo** (è una previsione, non un evento);
- incendi di edifici, auto, rifiuti, capannoni: non sono incendi boschivi, e Limen non li modella;
- buche, crolli di edifici, cedimenti di condotte: non sono frane;
- notizie in cui le testate si contraddicono su luogo o giorno senza che una fonte istituzionale chiarisca.

Annota per ogni evento: cosa, comune/i, data e ora **con fuso** (l'ora italiana: `+02` d'estate, `+01` d'inverno), danni/vittime/evacuati come riportati, e gli URL. Le cifre dei giornali (ettari, sfollati) vanno attribuite alla testata, mai fatte proprie.

### 3. Risolvere i comuni

```bash
docker exec limen-postgres psql -U limen -d limen -At -c \
  "SELECT istat_code, name, aoi_id FROM comuni WHERE name ILIKE 'Pisticci'"
```

Gli omonimi esistono (es. *Castro*, *Peglio*, *Samone*): scegli per `aoi_id` (la regione). Un evento su più comuni → passa tutti i codici separati da virgola. Se il comune non è in `comuni` (regione non coperta), esito `non_verificabile`: nessun file.

### 4. Calcolare l'anticipo

```bash
DB__CONNECTION_STRING=$(docker exec limen-worker printenv DB__CONNECTION_STRING | sed 's/@postgres:/@127.0.0.1:/') \
  uv run limen anticipo 077014 wildfire 2026-10-10T15:00+02:00 --tolleranza 12
```

È la stessa query della raccolta automatica (`anticipo_repo`), e le regole del §5 sono in codice in `limen.core.verifiche.esito`: il fact check a mano e il job decidono allo stesso modo. Il comando non scrive niente e non applica migrazioni. Codici ISTAT separati da virgola; pericolo `landslide` | `flood` | `wildfire`. `--tolleranza` (ore) è l'intorno dell'evento in cui una previsione si considera «puntata lì»: 12 di default; 6 se l'ora è precisa e l'evento breve (una colata), 24 se l'ora è ignota. Su questo disco una chiamata dura 10-60 s: **lanciale in sequenza**, non in parallelo, e non togliere il filtro su `computed_at` (la tabella è partizionata per giorno).

L'output è un oggetto JSON:

| Campo | Significato |
|---|---|
| `storico_dal` | da quando esiste lo storico previsionale — se l'evento è prima, `non_verificabile` |
| `anticipo_ore_moderato` / `_alto` | evento − **prima** corsa previsionale (+24/+48/+72 h) che metteva una cella del comune ≥ Moderato / ≥ Alto con obiettivo nell'intorno. `null` = mai |
| `classe_prevista_max` | la classe più alta prevista per quell'intorno |
| `corse` | ogni corsa: `run_at`, `horizon_h`, `target_at`, classe e punteggio della cella peggiore, quante celle sopra soglia, i `fattori` di quella cella |
| `adesso_primo_moderato`, `adesso_classe_max`, `adesso_picco` | lo sweep orario («adesso», `horizon='24h'`) nelle 72 h prima |
| `adesso_non_misurato` | righe con `measured = false`: il dato meteo mancava |
| `allerte` | alert davvero spediti: primo invio, celle, livelli. `null` = nessuno |
| `fondo_classe_max`, `fondo_giorni_moderato` | la classe più alta dello sweep orario da 10 a 4 giorni prima, e in quanti di quei giorni il comune era ≥ Moderato: lo **sfondo** contro cui leggere la previsione |

Le righe dello sweep orario sono **sparse** (#135: una riga solo a cambio di classe o al battito di 24 ore): poche righe con punteggio basso vogliono dire che la classe non è mai cambiata, non che mancano dati.

Lo storico previsionale tiene solo le celle ≥ Moderato: `corse` vuoto vuol dire **previsto sotto Moderato**, non «non calcolato» (a meno che l'evento sia prima di `storico_dal`, o che la corsa di quel pericolo non sia girata — controlla che esistano corse dello stesso pericolo nei giorni attorno con `SELECT max(computed_at) FROM risk_assessments WHERE hazard_type=… AND horizon='+24h' AND computed_at BETWEEN …`).

### 5. Decidere l'esito

Nell'ordine, il primo che vale:

1. **`non_verificabile`** (nessun file, solo nel riepilogo) — evento prima di `storico_dal`; comune fuori copertura; oppure nessuna corsa di quel pericolo girata nei giorni prima; oppure `adesso_non_misurato` > 0 e nessun'altra riga misurata (il dato non c'era: «non misurato» non è «nessun pericolo»).
2. **`anticipata`** — `anticipo_ore_moderato` ≥ 6 **e** `classe_prevista_max` è sopra `fondo_classe_max`. Se la classe prevista è la stessa che il comune aveva tutti i giorni prima, l'anticipo è lo sfondo, non un segnale: in quel caso l'anticipo che conta è `anticipo_ore_alto` (se il fondo è Moderato) e, se è `null`, si passa alle regole sotto.
3. **`contemporanea`** — nessuna previsione utile, ma lo sweep orario era salito sopra il fondo prima dell'evento (`adesso_classe_max` sopra `fondo_classe_max`, con `adesso_primo_moderato` prima dell'evento).
4. **`mancata`** — tutto il resto.

Esempio vero (frana di Melito di Porto Salvo, 10 ottobre 2026): 71 ore di «anticipo ≥ Moderato», ma Melito aveva celle in Moderato ogni giorno dal 29 settembre e la previsione non è mai salita ad Alto → `mancata`: niente file, solo il riepilogo all'utente con l'anticipo apparente e perché non conta.

Solo `anticipata` arriva al §6; per gli altri esiti si passa al registro (§8b) e al riepilogo (§9.3).

Non arrotondare a favore di Limen: un anticipo «≥ Moderato» non è un allarme; se è arrivato solo Moderato e mai Alto, scrivilo.

### 6. Il «perché»: tradurre i fattori

Prendi i `fattori` della corsa che ha dato l'anticipo (o di `adesso_picco`) e traducili in 2-5 voci `perche` (`nome`, `valore`, `spiegazione`), in italiano piano:

- **incendio** (`score = fwi_norm × (base + fuel·f + slope·s)`): `fire_weather.fwi` (indice meteo incendi, Van Wagner; > 30 alto, > 50 estremo), `ffmc` (umidità del combustibile fine, > 85 = secco e infiammabile), `dmc`/`dc` (siccità dello strato organico/profondo), `isi` (velocità di propagazione col vento), `bui`; `fuel` (0-1, vegetazione da CORINE), `slope` (pendenza). `spinup: true` = catena FWI ancora in assestamento: dillo.
- **frana**: componenti `s` (suscettibilità statica: PAI, IFFI, pendenza, litologia in `static_terms`), `m` (innesco meteo: `meteo_terms.api_factor` pioggia antecedente, `caine_norm`/`caine_excess` soglia intensità-durata di Caine, `soil_factor` umidità del suolo, `snow_factor`), `e` (sisma), `f` (post-incendio), `h` (idrologia: pioggia prevista/portata).
- **alluvione** (`susceptibility × max(pluvial, fluvial)`): `rain_mm` contro `rain_threshold_mm`/`rain_saturation_mm`, `pluvial`, `fluvial`/`discharge_ratio` (portata GloFAS rispetto alla piena ordinaria del nodo), `susceptibility` (mosaico ISPRA; `mapped: false` = area non studiata).

Per gli eventi non anticipati il «perché» va nel riepilogo all'utente, non sulla pagina: quale fattore era basso (es. pioggia locale sottostimata dal nodo meteo a 9 km, temporale convettivo non risolto, `fuel` nullo per CORINE mancante, `susc_ispra` 0 in area non mappata).

### 7. Foto: solo con licenza

**Mai** scaricare o linkare come immagine le foto dei giornali: sono protette da diritto d'autore. Si linka l'articolo, non si ripubblica la foto. Fonti ammesse, in ordine:

1. Wikimedia Commons (CC0, CC BY, CC BY-SA, PD) — con autore e licenza;
2. Copernicus EMS (mappe di attivazione: «© European Union, Copernicus Emergency Management Service»), immagini Sentinel/Copernicus;
3. foto di Vigili del Fuoco / Protezione Civile **solo** se la pagina dichiara una licenza di riuso;
4. uno screenshot della mappa di Limen sulla zona: autore «Limen», licenza «EUPL-1.2; sfondo © OpenStreetMap contributors (ODbL)». Lo sfondo non è nostro, e l'attribuzione OSM è un obbligo di licenza, non una cortesia.

Se non trovi niente di pubblicabile, `foto: []`: l'articolo regge senza. Salva in `frontend/public/verifiche/<slug>/`, JPEG ≤ 300 KB (ridimensiona con `python3 -c` + Pillow o `convert` se disponibile), `alt`/`didascalia` descrittivi.

### 8. Creare o aggiornare la verifica

**Slug**: `AAAA-MM-GG-<frana|alluvione|incendio>-<comune-in-minuscolo-con-trattini>` (data dell'evento, ora locale).

**Prima cerca se esiste già**: stesso pericolo, uno dei comuni in comune, data entro ±1 giorno (`grep -l` su `frontend/src/content/verifiche/*.json`). Se esiste: aggiorna — mantieni `slug` e `pubblicato`, imposta `aggiornato` ad adesso, unisci `fonti` (senza duplicati per URL), ricalcola `previsione` se la nuova informazione cambia ora o comuni, riscrivi testo ed esito se cambiano. Altrimenti crealo.

**Solo l'evento `anticipata` ha il suo file.** Nessun file per `contemporanea`, `mancata`, `non_verificabile` o per un evento scartato al fact check; se ne esiste uno da una passata precedente, cancellalo. Se un aggiornamento porta un evento già pubblicato fuori da `anticipata` (nuove fonti spostano ora o comune), il file si cancella e lo si dice all'utente.

Schema (vedi `Verifica` in `frontend/src/content/verifiche.ts` — il tipo è la fonte di verità):

```json
{
  "slug": "2026-10-10-incendio-matera",
  "titolo": "Incendio sulle colline di Matera: Limen lo vedeva da tre giorni",
  "pericolo": "wildfire",
  "esito": "anticipata",
  "evento": {
    "quando": "2026-10-10T15:00:00+02:00",
    "luogo": "Matera (MT)",
    "regione": "Basilicata",
    "comuni": [{ "istat": "077014", "nome": "Matera" }]
  },
  "pubblicato": "2026-10-11T10:00:00+02:00",
  "aggiornato": "2026-10-11T10:00:00+02:00",
  "sommario": "Una o due frasi: cosa è successo e cosa diceva Limen.",
  "corpo": ["Paragrafo 1: l'evento secondo le fonti.", "Paragrafo 2: la previsione.", "Paragrafo 3: limiti e cosa non torna."],
  "fonti": [{ "testata": "ANSA", "titolo": "…", "url": "https://…", "data": "2026-10-10" }],
  "foto": [{ "src": "/verifiche/2026-10-10-incendio-matera/mappa.jpg", "didascalia": "…", "autore": "…", "licenza": "CC BY-SA 4.0", "fonte_url": "https://commons.wikimedia.org/…" }],
  "previsione": {
    "anticipo_ore_moderato": 83,
    "anticipo_ore_alto": 83,
    "classe_max": "VeryHigh",
    "allerta_prima": "2026-10-07T17:57:33+02:00",
    "corse": [{ "run_at": "…", "horizon_h": 72, "target_at": "…", "classe": "VeryHigh", "score": 0.855 }]
  },
  "perche": [{ "nome": "Indice meteo incendi (FWI)", "valore": "48,3", "spiegazione": "…" }],
  "en": {
    "titolo": "Wildfire on the hills of Matera: Limen saw it three days ahead",
    "luogo": "Matera (MT)",
    "sommario": "One or two sentences: what happened and what Limen said.",
    "corpo": ["Paragraph 1: the event according to the sources.", "Paragraph 2: the forecast.", "Paragraph 3: limits and what does not add up."],
    "perche": [{ "nome": "Fire Weather Index (FWI)", "valore": "48.3", "spiegazione": "…" }],
    "foto": [{ "didascalia": "…" }]
  }
}
```

`en` è la traduzione inglese, campo per campo, di `titolo`, `evento.luogo`, `sommario`, `corpo` (stesso numero di paragrafi, stesso ordine), `perche` (stesso numero di voci, stesso ordine) e delle didascalie di `foto` (stesso ordine). Non si traducono: numeri della `previsione`, date, `fonti` (titoli degli articoli restano in italiano, sono citazioni), `licenza`, `autore`, nomi di comuni. Nei valori di `perche` l'inglese usa il punto decimale («48.3»), l'italiano la virgola.

`previsione.corse` riporta le righe di `corse` senza `fattori`/`cella`/`celle_sopra_soglia` (se sono molte, tieni la prima per ogni orizzonte più quelle in cui la classe cambia). `allerta_prima` = `allerte.prima` o `null`.

**Come scrivere**: prima l'italiano, poi l'inglese tradotto da quello — stessi fatti, stesse cifre, nessuna frase in più o in meno. Registro giornalistico sobrio, stile dei testi di Limen (frasi concrete, numeri esatti, niente enfasi). Ogni cifra di Limen viene dalla query; ogni cifra sull'evento è attribuita alla testata («secondo ANSA, 40 ettari»). Niente citazioni lunghe degli articoli: parafrasi breve + link. Dichiara sempre i limiti: celle da 1 km², nodo meteo a ~9 km, classe ≥ Moderato non è un'allerta ufficiale (quella è della Protezione Civile). Mai suggerire che Limen sostituisca il bollettino ufficiale. In inglese: classi «Low / Moderate / High / Very high», «Civil Protection» per la Protezione Civile, «1 km² cells», «weather node ~9 km away»; un «≥ Moderate» non è «an alert».

### 8b. Registrare ogni evento verificato

Per **ogni** evento che ha superato il §2 — `anticipata`, `contemporanea`, `mancata` o `non_verificabile` — scrivi un file nello scratchpad (non nel repo) e registralo. Gli eventi scartati al §2 non si registrano.

```json
{
  "slug": "2026-10-10-frana-san-lorenzo",
  "pericolo": "landslide",
  "esito": "mancata",
  "motivo": "Moderato in 6 giorni di fondo su 7; previsione mai sopra Moderato (0,42 contro 0,38 di fondo)",
  "evento": {
    "quando": "2026-10-10T12:00:00+02:00",
    "precisione_ora": "T3",
    "luogo": "San Lorenzo Marina (RC)",
    "regione": "Calabria",
    "comuni": ["080073"],
    "lon": 15.835, "lat": 37.915, "precisione_luogo": "P1"
  },
  "fonti": [{ "testata": "DIRE", "titolo": "…", "url": "https://…", "data": "2026-10-13" }],
  "misura": { "…": "l'uscita di anticipo.sql così com'è, corse e fattori compresi" }
}
```

- `slug`: come al §8, anche per gli eventi che non avranno un articolo.
- `precisione_ora` è la scala di ITALICA: `T1` ora nota, `T2` mezza giornata, `T3` solo il giorno (ora ignota, mezzogiorno convenzionale).
- `lon`/`lat` solo se la notizia nomina una località precisa (frazione, strada, ponte) di cui conosci le coordinate da una fonte, con `precisione_luogo` `P1` (entro ~1 km). Altrimenti omettili: il comando usa il centroide dei comuni a `P10` (uno) o `P100` (più d'uno). Non inventare coordinate, e **non** usare la cella peggiore della query: renderebbe la verità figlia della previsione.
- `misura` è l'oggetto JSON di anticipo.sql **intero**: è il motivo per cui il registro esiste.

```bash
DB__CONNECTION_STRING=$(docker exec limen-worker printenv DB__CONNECTION_STRING | sed 's/@postgres:/@127.0.0.1:/') \
  uv run limen registra-verifica <scratchpad>/<slug>.registro.json [altri file…]
```

Idempotente (la chiave è lo slug): rilanciarlo dopo un aggiornamento riscrive la riga e conserva `verificato_at`. Per vedere il conto per pericolo — anticipate, quota con previsione ≥ Moderato e il suo tasso di base — `uv run limen verifiche-report` (stessa `DB__CONNECTION_STRING`; `LIMEN_VERIFICHE_DAL`/`_AL` per una finestra): è il metro delle alluvioni dalla stampa, che non hanno perimetro e non entrano in `flood_events`. Una frana va anche in `landslide_events` con id `stampa:<slug>`; un'alluvione o un incendio restano solo nel registro (`flood_events` vuole il perimetro osservato, non un comune). Un file non valido fa uscire il comando con codice 2 senza scrivere niente: correggi e rilancia.

### 9. Controllare e pubblicare

1. JSON valido e con l'a capo finale (il pre-commit della CI lo pretende): `python3 -m json.tool frontend/src/content/verifiche/<slug>.json > /dev/null && tail -c1 frontend/src/content/verifiche/<slug>.json | od -c`.
2. Gate del frontend (Node non è sull'host — memoria `frontend-needs-docker-node`):
   ```bash
   cd frontend && docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v "$PWD":/app -w /app node:22 \
     sh -c "npx vitest run src/__tests__/VerifichePage.test.tsx && npm run lint && npm run build"
   ```
   Il `build` (`tsc -b`) **non** controlla i JSON (`import.meta.glob` li tipizza senza verificarli): controlla tu che ogni file sia `anticipata`, abbia l'anticipo e il blocco `en` completo:
   ```bash
   for f in frontend/src/content/verifiche/*.json; do python3 - "$f" <<'PY'
   import json, sys
   v = json.load(open(sys.argv[1])); en = v.get("en") or {}
   errori = [m for m, ok in [
       ("esito non anticipata", v["esito"] == "anticipata"),
       ("anticipo mancante", isinstance(v["previsione"]["anticipo_ore_moderato"], int)),
       ("en incompleto", all(en.get(k) for k in ("titolo", "luogo", "sommario", "corpo"))),
       ("en.corpo disallineato", len(en.get("corpo", [])) == len(v["corpo"])),
       ("en.perche disallineato", len(en.get("perche", [])) == len(v["perche"])),
       ("en.foto disallineato", len(en.get("foto", [])) == len(v["foto"])),
   ] if not ok]
   print(sys.argv[1], "OK" if not errori else errori)
   PY
   done
   ```
   `verificate()` in `verifiche.ts` scarta comunque un file non conforme, ma in silenzio: l'articolo semplicemente non appare. Il controllo qui sopra è quello che te lo dice.
3. Riepiloga all'utente, per ogni evento trovato: esito, anticipo (≥ Moderato e ≥ Alto), fonti, foto e licenza. In due gruppi: gli **articoli** (`anticipata`, con file) e gli **esclusi** (`contemporanea`, `mancata`, `non_verificabile`, scartati al fact check) con il motivo e, per i non anticipati, il fattore che è mancato. Gli esclusi non stanno sulla pagina; quelli verificati (tutti tranne gli scartati al fact check) stanno nel registro: di' quanti ne hai registrati e quante frane sono entrate in `landslide_events`.
4. **Pubblicare richiede conferma esplicita** (è il sito pubblico): solo dopo il sì, ricostruisci il frontend statico
   ```bash
   docker compose --env-file .env -f infra/docker/docker-compose.demo.yml \
     -f infra/docker/docker-compose.geoserver.yml -p limen \
     --profile frontend-static up -d --build frontend-static
   ```
   e, se l'utente lo chiede, commit su un branch `verifiche/<data>` + PR (push via token HTTPS — memoria `git-push-needs-https-token`).

## Cosa non fare

- Non pubblicare eventi con una sola fonte non istituzionale.
- Non scrivere un file per un evento che non sia `anticipata`, e non mostrarne il conteggio sulla pagina: sulla pagina vanno solo gli eventi previsti, con le ore di anticipo.
- Non pubblicare un articolo senza il blocco `en` completo.
- Non chiamare `mancata` un evento fuori retention o fuori copertura: è `non_verificabile`.
- Non modificare numeri di Limen nel testo per renderli più leggibili oltre l'arrotondamento (punteggi a due decimali, ore intere).
- Non scrivere nel database se non con `limen registra-verifica` (§8b): mai `INSERT`/`UPDATE` a mano, mai su `risk_assessments` o sulle tabelle del modello.
