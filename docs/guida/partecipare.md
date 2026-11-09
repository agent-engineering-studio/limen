# Partecipare

**I contributi più utili a Limen non sono codice: sono eventi veri, misure e
pareri.** Limen si misura contro le frane, le alluvioni e gli incendi
realmente accaduti, e il 29 ottobre 2026 gli eventi verificati erano otto:
troppo pochi per dire se la mappa funziona. Ogni evento datato con un luogo e
una fonte diventa una riga del registro su cui Limen si mette alla prova.
Questa pagina dice, per ciascuno, che cosa può fare, con un esempio, e che
cosa succede dopo.

> **Limen non è un servizio di emergenza.** Se sei in pericolo chiama il
> **112** e segui le indicazioni della Protezione civile e del tuo Comune.
> Una segnalazione a Limen serve a misurare la mappa, non a far arrivare
> soccorsi.

## Chi vede un evento: segnalarlo

Hai visto una frana, una strada allagata, un incendio, o ne hai letto in un
giornale locale? Segnalalo con il modulo
[«Segnala un evento»](https://github.com/agent-engineering-studio/limen/issues/new?template=evento.yml).
Servono quattro cose:

- **il pericolo**: frana, alluvione o incendio;
- **quando**: il giorno, e l'ora se la conosci;
- **dove**: il Comune, e se puoi il punto sulla mappa;
- **la fonte**: un articolo, un comunicato, una foto con la sua licenza.

**Un esempio.** «Frana sulla strada provinciale per Bagaladi (RC), 10 ottobre
2026 verso le 15, la riporta la Gazzetta del Sud a questo link.» Basta questo.

**Che cosa succede dopo.** Il curatore controlla l'evento su almeno due fonti
indipendenti, guarda che cosa diceva Limen nelle 72 ore prima e lo registra.
L'evento compare nella pagina [Verifiche](#/verifiche) con l'esito, anche
quando Limen non l'aveva visto: un evento mancato è l'informazione più utile.

## Chi fa ricerca: rifare i conti e contestarli

Ogni numero della mappa si può ricalcolare. Clicca una cella: la scheda
mostra l'identificativo. Con quello, un indirizzo restituisce tutti gli
ingredienti dell'ultimo calcolo:

```
GET /api/cell/{identificativo}/breakdown?hazard=landslide
```

(`hazard` è `landslide`, `flood` o `wildfire`; nell'indirizzo il carattere `|`
dell'identificativo si scrive `%7C`.) Pesi e soglie stanno nei file di
configurazione di ogni pericolo, pubblici nel repository. Se il conto non
torna, o se pensi che un peso sia sbagliato, apri
[«Contesta un punteggio»](https://github.com/agent-engineering-studio/limen/issues/new?template=contesta-punteggio.yml)
con la cella, l'istante, il valore che ti aspettavi e il conto che hai fatto.

**Un esempio.** «Cella `it-toscana|156|158`, frana, 9 novembre 2026 alle 10:
il punteggio è 0,41, ma con i pesi di `landslide.yaml` e i componenti della
risposta mi viene 0,38.»

**Che cosa succede dopo.** Si risponde nella issue. Se è un errore di calcolo
si corregge con un test. Se è una proposta di peso o di soglia, si prova sugli
eventi passati con e senza la modifica, e si adotta solo se coglie più eventi
senza più allarmi a vuoto. In entrambi i casi la misura resta scritta nella
issue.

**Per una collaborazione di ricerca** (una tesi, un confronto con il vostro
modello, un dataset di eventi) scrivi nelle
[discussioni del progetto](https://github.com/agent-engineering-studio/limen/discussions)
o a gzileni@agentengineering.it.

## Enti locali e Protezione civile: eventi, prove pilota, pareri

- **Gli eventi della vostra stagione.** Un elenco di frane datate, di aree
  allagate o di interventi, anche in un foglio di calcolo, vale più di qualunque
  modifica al codice: molti eventi piccoli non entrano in nessun catalogo
  nazionale. Mandatelo per email; ogni riga con data, luogo e fonte diventa
  un evento del registro.
- **Una prova sul vostro territorio.** La mappa pubblica copre già tutte le
  regioni; una copia sui vostri server si installa con un comando, poi tutto
  dal browser.
- **Un parere.** «Questa informazione la userei, quest'altra no» è la cosa che
  serve di più a decidere che cosa fare dopo.

**Un esempio.** Un ufficio tecnico comunale manda le 23 frane del 2025 sulle
strade comunali, con giorno e località: entrano nel registro e Limen dice,
per ognuna, se l'aveva vista e quante ore prima.

Limen **non è un sistema di allertamento ufficiale** e non sostituisce i
Centri Funzionali né IT-Alert: è uno strumento di supporto alle decisioni.
Scrivete a **gzileni@agentengineering.it**.

### Il formato del file degli eventi

Va bene un foglio di calcolo salvato in CSV (con la virgola o con il punto e
virgola, come lo salva Excel in italiano) o un GeoJSON di punti. Una riga per
evento, con queste colonne; quelle in grassetto sono obbligatorie:

| Colonna | Che cosa contiene | Esempio |
|---|---|---|
| **`id`** | il vostro identificativo dell'evento, unico nel file | `2025-017` |
| **`pericolo`** | `frana`, `alluvione` o `incendio` | `frana` |
| **`data`** | il giorno, AAAA-MM-GG | `2025-11-14` |
| `ora` | l'ora locale, se nota | `07:30` |
| `precisione_ora` | `T1` ora nota, `T2` mezza giornata, `T3` solo il giorno (di default `T1` se c'è l'ora, altrimenti `T3`) | `T2` |
| **`comuni`** | codici ISTAT a sei cifre, separati da punto e virgola | `080006` |
| **`luogo`** | la località come la scrivete voi | `SP 22 per Bagaladi, km 4` |
| `regione` | la regione | `Calabria` |
| `lon`, `lat` | il punto in gradi decimali (WGS84), se noto | `15.8312`, `38.0251` |
| `precisione_luogo` | obbligatoria con il punto: `P0` esatto, `P1` entro ~1 km, `P10` il comune, `P100` più comuni | `P1` |
| `tipo` | il tipo di evento, con le vostre parole | `colata di detrito` |
| **`fonte`** | da dove viene: un verbale, un rapporto, un link | `verbale 112/2025` |
| `note` | qualunque altra cosa | |

Un [file di esempio](https://github.com/agent-engineering-studio/limen/blob/main/docs/guida/eventi-ente-esempio.csv) ha tre righe: una frana datata al solo giorno, una
con ora e punto, un allagamento di mattina. Diteci anche **con quale licenza**
ce li date: consigliamo la CC BY 4.0, che permette a chiunque di riusarli
citando la fonte. Le date e i luoghi degli eventi non sono dati personali: non
mettete nel file nomi di persone.

## Chi conosce un dato utile: proporlo

Un pluviometro regionale, un inventario di frane, una carta più precisa:
proponilo con il modulo
[«Proposta di dato»](https://github.com/agent-engineering-studio/limen/issues/new?template=proposta-dato.yml).
Servono licenza, link, copertura e come misurarlo; la pagina [Fonti](#/fonti)
spiega come Limen decide se usarlo.

## Chi ha un sensore

Un pluviometro o una stazione meteo costruiti in casa possono diventare una
fonte di Limen, con regole chiare su dove installarli e su chi vede i dati:
le trovi nella pagina [Sensori](#/sensori).

## Chi sviluppa

Il punto di partenza è
[`CONTRIBUTING.md`](https://github.com/agent-engineering-studio/limen/blob/main/CONTRIBUTING.md);
i primi lavori piccoli sono etichettati
[`good first issue`](https://github.com/agent-engineering-studio/limen/labels/good%20first%20issue).

## Quanto si aspetta una risposta

Limen ha **un solo curatore**: di solito rispondiamo entro una settimana, non
sempre in giornata. I dati personali che ci mandi sono trattati come spiega la
pagina [Dati personali](#/privacy).

## Per chi cura il progetto

Il file di un ente entra con `limen importa-eventi FILE --ente «Nome» --licenza
«CC BY 4.0»`: controlla prima tutte le righe e i codici ISTAT, e se una è
sbagliata non scrive niente; poi misura ogni evento come la raccolta della
stampa. Rilanciarlo è sicuro: lo stesso file non si rilegge, e di un file che
cresce entrano solo le righe nuove.

Una segnalazione accettata diventa un file del fact-check e poi una riga del
registro con `limen registra-verifica FILE`. I campi del modulo «Segnala un
evento» corrispondono a quelli del file:

| Modulo | File del fact-check |
|---|---|
| pericolo | `pericolo` (`landslide`, `flood`, `wildfire`) |
| data e ora, precisione dell'ora | `evento.quando` (con il fuso), `evento.precisione_ora` (`T1` ora nota, `T2` mezza giornata, `T3` solo il giorno) |
| Comune, luogo | `evento.comuni`, `evento.luogo`, `evento.regione` |
| coordinate, precisione del luogo | `evento.lon`, `evento.lat`, `evento.precisione_luogo` (`P0`, `P1`, `P10`, `P100`) |
| fonti | `fonti` (almeno una, con `url`) |

`esito` e `misura` non li scrive chi segnala: li calcola il fact-check
confrontando l'evento con quello che Limen diceva nelle 72 ore prima.
