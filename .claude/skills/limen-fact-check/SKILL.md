---
name: limen-fact-check
description: Verifica sui principali quotidiani online italiani le notizie di frane, alluvioni e incendi boschivi, le confronta con le previsioni che Limen aveva calcolato prima dell'evento (ore di anticipo, classe, dati, perché) e crea o aggiorna la verifica corrispondente nella pagina blog «Verifiche» del sito (`#/verifiche`), con fonti e foto a licenza libera. Usala quando l'utente chiede di "fare il fact check", "verificare le notizie", "aggiornare le verifiche", "quanto prima Limen aveva visto la frana/alluvione/incendio di …", o invoca /limen-fact-check. Argomenti opzionali: pericolo (frana|alluvione|incendio), giorni all'indietro (default 3, max 13), un evento preciso ("incendio di Matera del 10 ottobre").
---

# limen-fact-check

Per ogni evento reale riportato dalla stampa: **è successo davvero? Limen l'aveva previsto? Con quante ore di anticipo, su quali dati, perché?** Il risultato è un articolo nella pagina «Verifiche» della SPA.

La regola che governa tutto: **si pubblica anche quando Limen non l'ha visto.** Un blog che racconta solo i successi misura la fortuna, non il modello (vedi la memoria `hit-rate-needs-base-rate`). L'esito `mancata` è un esito legittimo e va scritto con la stessa cura di `anticipata`.

## Dove vive la pagina

| Cosa | Dove |
|---|---|
| Una verifica = un file JSON | `frontend/src/content/verifiche/<slug>.json` |
| Le foto della verifica | `frontend/public/verifiche/<slug>/<nome>.jpg` → `src: "/verifiche/<slug>/<nome>.jpg"` |
| Tipi (lo schema del JSON) | `frontend/src/content/verifiche.ts` (`Verifica`) |
| Pagina (indice + articolo) | `frontend/src/components/VerifichePage.tsx`, rotta `#/verifiche` e `#/verifiche/<slug>` |
| Query dell'anticipo | `.claude/skills/limen-fact-check/scripts/anticipo.sql` |

Il contenuto entra nel bundle a build time (`import.meta.glob`): **niente migrazioni, niente endpoint**. Se `VerifichePage.tsx` o `verifiche.ts` mancassero (repo vecchio), fermati e dillo: non ricrearli a memoria.

## Vincolo duro: la retention

`risk_assessments` tiene **14 giorni** (`ASSESSMENTS_RETENTION_DAYS`), poi la partizione viene cancellata. Un evento più vecchio di ~13 giorni non è più verificabile: lo storico delle previsioni non esiste più. La query restituisce `storico_dal`; se l'evento è precedente, l'esito è `non_verificabile` — non `mancata`.

## Procedura

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

Scarta e non pubblicare:

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

Gli omonimi esistono (es. *Castro*, *Peglio*, *Samone*): scegli per `aoi_id` (la regione). Un evento su più comuni → passa tutti i codici separati da virgola. Se il comune non è in `comuni` (regione non coperta), esito `non_verificabile`.

### 4. Calcolare l'anticipo

```bash
docker exec -i limen-postgres psql -U limen -d limen -At \
  -v istat=077014 -v hazard=wildfire -v event_at='2026-10-10 15:00+02' -v tol=12 \
  < .claude/skills/limen-fact-check/scripts/anticipo.sql
```

`hazard`: `landslide` | `flood` | `wildfire`. `tol` (ore) è l'intorno dell'evento in cui una previsione si considera «puntata lì»: 12 di default; 6 se l'ora è precisa e l'evento breve (una colata), 24 se l'ora è ignota. Su questo disco una chiamata dura 10-60 s: **lanciale in sequenza**, non in parallelo, e non togliere il filtro su `computed_at` (la tabella è partizionata per giorno).

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

1. **`non_verificabile`** — evento prima di `storico_dal`; comune fuori copertura; oppure nessuna corsa di quel pericolo girata nei giorni prima; oppure `adesso_non_misurato` > 0 e nessun'altra riga misurata (il dato non c'era: «non misurato» non è «nessun pericolo»).
2. **`anticipata`** — `anticipo_ore_moderato` ≥ 6 **e** `classe_prevista_max` è sopra `fondo_classe_max`. Se la classe prevista è la stessa che il comune aveva tutti i giorni prima, l'anticipo è lo sfondo, non un segnale: in quel caso l'anticipo che conta è `anticipo_ore_alto` (se il fondo è Moderato) e, se è `null`, si passa alle regole sotto.
3. **`contemporanea`** — nessuna previsione utile, ma lo sweep orario era salito sopra il fondo prima dell'evento (`adesso_classe_max` sopra `fondo_classe_max`, con `adesso_primo_moderato` prima dell'evento).
4. **`mancata`** — tutto il resto.

Esempio vero (frana di Melito di Porto Salvo, 10 ottobre 2026): 71 ore di «anticipo ≥ Moderato», ma Melito aveva celle in Moderato ogni giorno dal 29 settembre e la previsione non è mai salita ad Alto → `mancata`, con l'anticipo riportato e spiegato nel testo.

Non arrotondare a favore di Limen: un anticipo «≥ Moderato» non è un allarme; se è arrivato solo Moderato e mai Alto, scrivilo.

### 6. Il «perché»: tradurre i fattori

Prendi i `fattori` della corsa che ha dato l'anticipo (o di `adesso_picco`) e traducili in 2-5 voci `perche` (`nome`, `valore`, `spiegazione`), in italiano piano:

- **incendio** (`score = fwi_norm × (base + fuel·f + slope·s)`): `fire_weather.fwi` (indice meteo incendi, Van Wagner; > 30 alto, > 50 estremo), `ffmc` (umidità del combustibile fine, > 85 = secco e infiammabile), `dmc`/`dc` (siccità dello strato organico/profondo), `isi` (velocità di propagazione col vento), `bui`; `fuel` (0-1, vegetazione da CORINE), `slope` (pendenza). `spinup: true` = catena FWI ancora in assestamento: dillo.
- **frana**: componenti `s` (suscettibilità statica: PAI, IFFI, pendenza, litologia in `static_terms`), `m` (innesco meteo: `meteo_terms.api_factor` pioggia antecedente, `caine_norm`/`caine_excess` soglia intensità-durata di Caine, `soil_factor` umidità del suolo, `snow_factor`), `e` (sisma), `f` (post-incendio), `h` (idrologia: pioggia prevista/portata).
- **alluvione** (`susceptibility × max(pluvial, fluvial)`): `rain_mm` contro `rain_threshold_mm`/`rain_saturation_mm`, `pluvial`, `fluvial`/`discharge_ratio` (portata GloFAS rispetto alla piena ordinaria del nodo), `susceptibility` (mosaico ISPRA; `mapped: false` = area non studiata).

Una spiegazione per mancata è altrettanto importante: quale fattore era basso (es. pioggia locale sottostimata dal nodo meteo a 9 km, temporale convettivo non risolto, `fuel` nullo per CORINE mancante, `susc_ispra` 0 in area non mappata).

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
  "perche": [{ "nome": "Indice meteo incendi (FWI)", "valore": "48,3", "spiegazione": "…" }]
}
```

`previsione.corse` riporta le righe di `corse` senza `fattori`/`cella`/`celle_sopra_soglia` (se sono molte, tieni la prima per ogni orizzonte più quelle in cui la classe cambia). `allerta_prima` = `allerte.prima` o `null`.

**Come scrivere**: italiano, registro giornalistico sobrio, stile dei testi di Limen (frasi concrete, numeri esatti, niente enfasi). Ogni cifra di Limen viene dalla query; ogni cifra sull'evento è attribuita alla testata («secondo ANSA, 40 ettari»). Niente citazioni lunghe degli articoli: parafrasi breve + link. Dichiara sempre i limiti: celle da 1 km², nodo meteo a ~9 km, classe ≥ Moderato non è un'allerta ufficiale (quella è della Protezione Civile). Mai suggerire che Limen sostituisca il bollettino ufficiale.

### 9. Controllare e pubblicare

1. JSON valido e con l'a capo finale (il pre-commit della CI lo pretende): `python3 -m json.tool frontend/src/content/verifiche/<slug>.json > /dev/null && tail -c1 frontend/src/content/verifiche/<slug>.json | od -c`.
2. Gate del frontend (Node non è sull'host — memoria `frontend-needs-docker-node`):
   ```bash
   cd frontend && docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v "$PWD":/app -w /app node:22 \
     sh -c "npx vitest run src/__tests__/VerifichePage.test.tsx && npm run lint && npm run build"
   ```
   Il `build` (`tsc -b`) controlla che ogni JSON rispetti il tipo `Verifica`.
3. Riepiloga all'utente, per ogni evento: esito, anticipo, fonti, foto e licenza; e gli eventi **scartati** con il motivo.
4. **Pubblicare richiede conferma esplicita** (è il sito pubblico): solo dopo il sì, ricostruisci il frontend statico
   ```bash
   docker compose --env-file .env -f infra/docker/docker-compose.demo.yml \
     -f infra/docker/docker-compose.geoserver.yml -p limen \
     --profile frontend-static up -d --build frontend-static
   ```
   e, se l'utente lo chiede, commit su un branch `verifiche/<data>` + PR (push via token HTTPS — memoria `git-push-needs-https-token`).

## Cosa non fare

- Non pubblicare eventi con una sola fonte non istituzionale.
- Non chiamare `mancata` un evento fuori retention o fuori copertura: è `non_verificabile`.
- Non togliere dalla pagina una verifica `mancata` per migliorare il bilancio.
- Non modificare numeri di Limen nel testo per renderli più leggibili oltre l'arrotondamento (punteggi a due decimali, ore intere).
- Non scrivere nel database: la skill legge soltanto.
