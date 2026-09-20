# L'intelligenza artificiale gira in casa

**Il modello linguistico che scrive le spiegazioni di Limen sta su un
computer che possiamo indicare col dito, non in un servizio a consumo dove
ogni frase costa qualche centesimo e ogni dato fa un viaggio.** Non è una
posa ideologica: è la condizione perché un Comune possa ospitare questo
sistema sapendo in anticipo quanto spenderà, e perché il sistema continui a
funzionare quando internet non c'è.

<!-- schema-fase: avviso -->

```mermaid
flowchart LR
  D["I dati<br/>il posto e il momento"] --> P["Il punteggio<br/>un numero fra 0 e 1"]
  P --> C["La classe<br/>cinque livelli"]
  C --> A["L'avviso<br/>a chi, quando"]
```

Come nelle altre pagine: Limen affianca e non sostituisce l'allertamento
ufficiale, e nessun suo avviso ha valore legale.

## Cosa fa il modello linguistico, esattamente

Due cose, entrambe alla fine della catena, entrambe dopo che il numero è già
stato calcolato.

**Scrive il briefing.** È il paragrafo in italiano che accompagna una
situazione di rischio: cosa sta succedendo su quell'area, quali celle sono
messe peggio, quale ingrediente sta pesando di più. Prende in ingresso la
valutazione già fatta — punteggi, classi, componenti — e la mette in prosa.
Il prompt che riceve è un file di testo versionato nel repository, non una
stringa nascosta nel codice: chiunque può leggerlo e vedere esattamente cosa
gli viene chiesto.

**Compila la scheda dell'analista.** È un output **strutturato**, non prosa:
campi predefiniti con valori ammessi — la causa prevalente scelta da un
elenco chiuso, il livello di fiducia, gli elementi esposti. Il modello non
può inventare una causa che non sia nell'elenco: la risposta viene forzata a
rispettare lo schema, e se non lo rispetta viene scartata.

## Cosa non fa, e come lo sappiamo

Non calcola il rischio. Non modifica il punteggio, la classe o i fattori. Non
decide se mandare un avviso. Non sceglie le soglie. Non ha accesso al
database.

Il modo in cui questo è garantito non è una dichiarazione d'intenti ma un
**test automatico**: fa girare la catena con un modello linguistico
sostituito da uno finto che restituisce risposte arbitrarie, e verifica che i
numeri siano identici a quelli ottenuti senza modello. Se una modifica futura
permettesse al testo di spostare un punteggio, quel test fallirebbe e
bloccherebbe la modifica.

C'è anche una regola meno ovvia e più interessante: **se per un pericolo non
esiste un prompt scritto apposta, quel pericolo non riceve narrazione
affatto.** I prompt italiani di Limen sono scritti per le frane — parlano di
versanti, di soglie di pioggia, di cause di scivolamento. Far raccontare un
incendio a una voce addestrata a spiegare le frane produrrebbe testo
plausibile e sbagliato, che è la cosa peggiore. Quindi, in mancanza del
prompt giusto, la scheda resta con la spiegazione deterministica e basta. Il
silenzio è un'opzione ammessa.

E, più in generale: se il modello è spento, lento o rotto, **tutto il resto
funziona**. I punteggi si calcolano, le classi si assegnano, gli avvisi
partono con il riassunto deterministico. Gli avvisi non contengono mai testo
generato: il loro riassunto è costruito meccanicamente dai numeri, perché un
avviso è il posto meno adatto del mondo per una frase inventata.

## Perché in casa e non in un servizio a consumo

**Perché il costo diventa prevedibile.** Un servizio a consumo si paga per
quantità di testo. Limen, a regime nazionale, valuta trecentomila celle
all'ora: se ogni situazione di rischio generasse una chiamata a pagamento, il
conto dipenderebbe dal maltempo. Un autunno piovoso costerebbe dieci volte un
autunno asciutto, e nessun ufficio comunale può mettere a bilancio una voce
del genere. Un server che sta lì costa uguale che piova o no.

**Perché i dati restano dove sono.** Limen non tratta dati personali — non
c'è registrazione, non c'è login, non c'è un elenco di utenti. Ma tratta
valutazioni di rischio su territori identificabili, e la posizione del
problema è già un'informazione sensibile per l'amministrazione che la
possiede. Tenerla su una macchina propria significa non doversi porre il
problema.

**Perché il sistema resta indipendente.** Un servizio esterno può cambiare
prezzo, cambiare condizioni, ritirare un modello, chiudere. Se la parte che
scrive le spiegazioni dipendesse da quello, ogni cambiamento altrui
diventerebbe un problema nostro.

**Perché funziona anche isolato.** Un sistema di protezione civile che
richiede internet per completare il proprio lavoro ha un problema di fondo,
visto che gli eventi estremi sono esattamente le occasioni in cui le linee
cadono.

## Come è fatta, concretamente, la parte locale

Il sistema parla a **un solo indirizzo**: un instradatore che sta sulla
macchina e che decide quale modello deve rispondere a quale richiesta,
applica un tetto di spesa se qualche modello a pagamento è configurato, e
gestisce l'eventuale ripiego. Limen non conosce i modelli: conosce i ruoli.

Dietro l'instradatore stanno i motori veri, e sono di due tipi.

**Modelli piccoli, residenti sulla scheda grafica.** Uno da circa **4
miliardi di parametri** per i compiti che non richiedono bella prosa, uno da
**8 miliardi** per il testo italiano del briefing, e un profilo dedicato alle
risposte strutturate, dove la generazione viene vincolata a rispettare lo
schema richiesto. Sono i modelli che rispondono in tempi compatibili con una
richiesta web.

**Un modello grande, lento, per il lavoro che può aspettare.** Occupa
centinaia di gigabyte e produce testo di qualità superiore, ma a una velocità
che va detta senza addolcirla: **una richiesta con tre parole di risposta ha
richiesto 40 secondi**. Poche centinaia di parole sono decine di minuti.

Quella misura ha prodotto una regola rigida, e il programma **si rifiuta di
avviarsi** se qualcuno la viola: il modello lento può essere assegnato
soltanto al briefing, che è l'unico compito asincrono del sistema. Tutti gli
altri ruoli stanno su percorsi dove qualcuno aspetta — una richiesta web, uno
strumento invocato da un agente esterno, il ciclo orario — e un modello lento
lì non è "un po' più lento": blocca il monitoraggio senza generare nessun
errore, il che è il modo peggiore di rompersi.

Il briefing, infatti, è stato spostato **fuori** dal ciclo orario: viene
scritto dopo, su valutazioni già salvate, una zona alla volta, e aggiunge
solo la propria frase alla riga esistente senza toccare né il punteggio né la
classe. Finché non arriva, la mappa mostra la spiegazione deterministica.

Il motore locale predefinito è **llama.cpp** (nella forma `llama-swap`, che
carica e scarica i modelli a richiesta). **Ollama**, che molti conoscono
perché è il modo più semplice di far girare un modello sul proprio computer,
resta pienamente supportato: si seleziona dichiarandolo esplicitamente nella
configurazione (`LLM__PROVIDER=ollama`, con il nome del modello in
`LLM__OLLAMA_MODEL`). Fino a poco tempo fa era Ollama il motore di ripiego
implicito; oggi non lo è più, e un'installazione che ci contava deve
dichiararlo.

## E se qualcuno vuole usare il cloud?

Può. La regola di precedenza è scritta e semplice: se in configurazione è
presente una chiave di un servizio esterno — Anthropic, OpenAI, Azure AI
Foundry, in quest'ordine — quel servizio vince sul motore locale, salvo che
la configurazione dica esplicitamente il contrario. Senza nessuna chiave, si
usa il motore in casa.

La scelta quindi è del gestore, e si esprime con una variabile
d'ambiente. Il punto non è vietare il cloud: è che **il cloud non sia
obbligatorio**, e che un'installazione senza connessione verso l'esterno
funzioni comunque.

## Quanto hardware serve a un Comune

Qui la risposta onesta è che **non l'abbiamo misurata**, e quindi non la
inventiamo: un dimensionamento raccomandato per un ente che voglia ospitare
Limen sul proprio territorio è `TODO(verificare)` — nella documentazione
tecnica di installazione non c'è una tabella di requisiti, e scriverne una a
naso sarebbe la cosa meno utile che questa pagina possa fare.

Quello che possiamo dire, perché è misurato e sta scritto nel repository:

- La parte che **calcola il rischio** non ha bisogno di scheda grafica né di
  intelligenza artificiale: è una somma pesata. Su diecimila celle ha
  impiegato **0,88 secondi**.
- La parte pesante, in quel ciclo da 156 secondi, erano i **140 secondi** dei
  due passaggi di scrittura — che infatti sono stati spostati fuori dal ciclo.
- Il carico serio è il **database geografico**: trecentomila celle con la
  loro storia sono decine di gigabyte, e la velocità del disco conta più
  della potenza del processore.
- Un modello locale da qualche miliardo di parametri **sta su una scheda
  grafica di fascia consumer**; il modello grande da centinaia di gigabyte è
  un'altra categoria, ed è opzionale.
- Il tempo massimo di attesa verso il motore locale è impostato a **600
  secondi** di default, e non è sovradimensionato: quando il sistema deve
  scambiare due modelli, un file da 17,7 gigabyte impiega da solo circa due
  minuti a salire in memoria video.

Un ente interessato a un dimensionamento serio dovrebbe partire da tre
domande: quante celle (cioè quanto territorio), se vuole la narrazione
generata o gli basta quella deterministica, e se il database sta su dischi
veloci. Le prime due incidono poco, la terza moltissimo.

## In sintesi

L'intelligenza artificiale, in Limen, è l'ultimo anello e il meno potente: fa
un lavoro di traduzione fra numeri e italiano, sotto vincoli verificati
automaticamente, su una macchina di cui chi gestisce il sistema ha le chiavi.
Se domani la si spegnesse del tutto, la mappa continuerebbe a colorarsi, gli
avvisi continuerebbero a partire, e l'unica cosa che si perderebbe sarebbe la
frase di accompagnamento.

È esattamente il posto che le compete.
