# Trasparenza e riproducibilità

**Se non ti fidi di un numero che hai letto su questa mappa, puoi
ricalcolarlo.** Non "puoi chiedere spiegazioni": puoi scaricare il codice,
scaricare gli stessi dati pubblici, rifare il conto e confrontarlo. Questa
pagina spiega come, e cosa fare se il conto non torna.

<!-- schema-fase: tutte -->

```mermaid
flowchart LR
  D["I dati<br/>il posto e il momento"] --> P["Il punteggio<br/>un numero fra 0 e 1"]
  P --> C["La classe<br/>cinque livelli"]
  C --> A["L'avviso<br/>a chi, quando"]
```

Anche qui, e per l'ultima volta: Limen affianca e non sostituisce
l'allertamento ufficiale, e nessun suo avviso ha valore legale.

## La licenza: Apache 2.0

Tutto il codice di Limen è pubblicato con licenza **Apache 2.0**. In parole
non giuridiche significa che chiunque può usarlo, studiarlo, modificarlo e
ridistribuirlo — anche per attività commerciali — a condizione di mantenere
l'attribuzione e di dichiarare le modifiche fatte. Non c'è una versione
"professionale" a pagamento con dentro le parti buone: quello che vedi è
tutto quello che c'è.

La licenza sta in [LICENSE](../../LICENSE) nella radice del progetto.

## Verificare un singolo punteggio

Questa è la verifica più utile e la più semplice, perché non richiede di
installare niente.

Ogni cella ha un identificativo. Lo trovi cliccando la cella sulla mappa: la
scheda che si apre lo mostra insieme al punteggio. Con quell'identificativo,
un indirizzo web restituisce **la scomposizione completa** dell'ultimo
calcolo:

```
GET /api/cell/{identificativo}/breakdown
```

La risposta contiene, separati, tutti i numeri che hai visto nella
[pagina 2](./02-come-si-calcola-il-rischio.md): il valore della componente
statica e dei suoi quattro ingredienti, il valore della componente meteo con
l'eccesso di pioggia sopra soglia, il fattore di pioggia antecedente e quello
di umidità del suolo, la componente sismica, quella post-incendio, quella
idraulica, il punteggio finale e la classe.

A quel punto la verifica è aritmetica: prendi i pesi (0,35 il posto, 0,40 la
pioggia, 0,15 il terremoto, 0,07 il fuoco, 0,03 l'acqua), moltiplica, somma,
e confronta. Se il totale non torna, hai trovato un errore, e ci interessa
molto saperlo.

Altri due indirizzi utili per capire il contesto di quel numero:

- `GET /api/cell/{identificativo}/history` — come è andato il punteggio di
  quella cella nel tempo, che è il modo migliore per distinguere una cella
  strutturalmente esposta da una che ha avuto una brutta giornata.
- `GET /api/legend` — le classi e i loro confini come il sistema li ha
  caricati in quel momento, così puoi verificare che corrispondano a quelli
  documentati qui.

L'elenco completo degli indirizzi è pubblicato dal sistema stesso su
`/docs`, in una pagina navigabile che permette di provare ogni chiamata dal
browser.

## Rifare tutto da zero

Se vuoi ricostruire l'intero sistema sulla tua macchina, la procedura è
pensata per essere **un comando solo**:

```
make init
```

che esegue in ordine: applica le migrazioni del database, carica la griglia e
le aree di interesse, scarica il catalogo storico delle frane, carica i dati
statici del territorio, e precalcola i fattori del posto.

Due proprietà rendono questa procedura affidabile, e sono scritte nelle
regole del progetto:

**È idempotente.** Eseguirla due volte non produce un risultato diverso da
eseguirla una volta. Le migrazioni già applicate vengono riconosciute e
saltate; i caricamenti già fatti non si ripetono. Puoi interromperla e
riprenderla.

**Le migrazioni non si riscrivono.** Ogni modifica alla struttura del
database è un file numerato che, una volta applicato da qualcuno, **non può
più essere toccato** — nemmeno per correggere un commento: il sistema ne
verifica l'impronta digitale e si ferma se è cambiata. Una modifica si fa
aggiungendo un file nuovo. Sembra una pignoleria, ed è la ragione per cui due
installazioni diverse hanno con certezza la stessa struttura dati.

## Rifare le misure

I tre numeri di verifica della [pagina 3](./03-cosa-fanno-ml-e-ai.md) si
riproducono con un comando ciascuno, e ognuno scrive un report leggibile
nella cartella `reports/`:

```
limen backtest             # frane, contro il catalogo e-ITALICA
limen backtest-flood       # alluvioni, contro i perimetri Copernicus EMS
limen backtest-wildfire    # incendi, contro i perimetri EFFIS
```

Le finestre temporali, l'area e la soglia si scelgono con variabili
d'ambiente documentate. I report che trovi nel repository sono stati
prodotti così, e la issue #122 contiene i comandi esatti per riprodurre la
misura sulle frane che oggi fallisce i tre obiettivi — inclusi i suoi numeri
scomodi.

Un'avvertenza tecnica importante per chi vuole confrontare i propri risultati
con i nostri: la pioggia usata nei backtest viene dagli archivi di rianalisi
(maglie di 5,5 chilometri), mentre il sistema in esercizio usa le previsioni
Open-Meteo. Sono due sorgenti diverse, e su eventi molto localizzati possono
non coincidere.

## Come è tenuto insieme il codice

Non serve saperlo per usare Limen, ma serve per giudicare quanto fidarsi.

Ogni modifica deve passare quattro controlli automatici prima di poter
entrare: lo stile, la coerenza dei tipi verificata in modo severo, la suite
di test, e una soglia di copertura dei test. Non è una raccomandazione: è un
comando (`make check`) che deve dare esito verde, e la stessa verifica gira
automaticamente a ogni proposta di modifica sul repository pubblico.

Alcuni di quei test esistono solo per proteggere le promesse fatte in queste
pagine. Uno verifica che il modello linguistico non riesca a spostare un
punteggio. Un altro modifica i pesi nel file di configurazione e verifica che
il risultato cambi di conseguenza — cioè dimostra che non esistono costanti
nascoste nel codice. Un altro ancora verifica che un servizio esterno
irraggiungibile produca un risultato neutro e non un errore.

## Segnalare un errore

Il posto giusto è il **tracciatore di problemi** del repository pubblico:

<https://github.com/agent-engineering-studio/limen/issues>

Le segnalazioni più utili, in ordine:

**"Questo numero è sbagliato".** Indica l'identificativo della cella, il
momento, e cosa ti aspettavi. Se hai già confrontato la scomposizione con la
formula, allega il conto: è la segnalazione che si risolve più in fretta.

**"Qui è franato e non l'avevate segnalato".** È la segnalazione più preziosa
in assoluto, perché è esattamente il dato che manca ai cataloghi — un evento
che nessuno ha registrato. Indica dove e quando, con la massima precisione
che hai.

**"Avete segnalato e non è successo niente".** Utile quasi quanto la
precedente: aiuta a distinguere un falso allarme vero da un evento non
registrato.

**"Questa pagina non si capisce".** Vale per la documentazione che stai
leggendo. È scritta perché sia comprensibile a chi non fa questo mestiere, e
se non ci riesce è un difetto come gli altri.

Se la segnalazione riguarda un rischio immediato per la sicurezza di
qualcuno, il posto giusto **non** è questo: è il numero unico di emergenza e
il sistema di protezione civile del tuo Comune. Un tracciatore di problemi su
internet non è un canale di emergenza, e nessuno lo presidia di notte.

## L'ultima cosa

Un sistema che stima rischi ha una responsabilità in più di un sistema che
consiglia film: se sbaglia per difetto, qualcuno non è stato avvisato; se
sbaglia per eccesso, la prossima volta nessuno guarderà. L'unica difesa
onesta contro entrambe è rendere tutto controllabile: la formula, i dati, le
misure, e anche i fallimenti.

È il motivo per cui in queste sei pagine hai letto tanto di quello che Limen
non sa fare quanto di quello che fa.
