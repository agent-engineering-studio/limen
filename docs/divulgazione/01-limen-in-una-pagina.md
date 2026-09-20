# Limen in una pagina

**Se vivi, lavori o coltivi in un posto in pendenza, vicino a un corso
d'acqua o accanto al bosco, Limen ti dice ogni ora quanto quel posto è
esposto oggi** — non in generale, non in media: oggi, con la pioggia che sta
cadendo e con quella prevista. Lo fa per ogni quadrato di un chilometro di
lato del territorio italiano, e mostra apertamente il conto che ha fatto per
arrivarci.

<!-- schema-fase: avviso -->

```mermaid
flowchart LR
  D["I dati<br/>il posto e il momento"] --> P["Il punteggio<br/>un numero fra 0 e 1"]
  P --> C["La classe<br/>cinque livelli"]
  C --> A["L'avviso<br/>a chi, quando"]
```

## Prima di tutto: cosa Limen non è

Mettiamo i limiti all'inizio, perché metterli in fondo sarebbe un modo
elegante di nasconderli.

**Limen non è il sistema di allertamento ufficiale.** In Italia le allerte
che contano — quelle che chiudono le scuole, vietano l'accesso a una strada,
attivano i centri operativi comunali — le emettono il Dipartimento della
Protezione Civile e i Centri Funzionali regionali. Limen usa la stessa scala
di colori (verde, gialla, arancione, rossa) perché è la scala che le persone
riconoscono, ma **i suoi avvisi non hanno alcun valore legale** e non
sostituiscono in nessun caso quelli ufficiali. Se le due cose non coincidono,
vale l'ufficiale.

**Limen non è una previsione di frana.** Nessuno al mondo sa dire "domani
alle 15 quel versante cede". Limen stima un'esposizione: quanto quel posto,
fatto com'è fatto, sollecitato com'è sollecitato oggi, somiglia alle
condizioni in cui in Italia le frane sono davvero avvenute. È una probabilità
relativa, non un appuntamento.

**Limen non è un chatbot.** Non c'è niente con cui conversare, e
l'intelligenza artificiale non decide nulla di quello che vedi colorato sulla
mappa. Il colore lo decide una formula scritta, leggibile e ricalcolabile a
mano; l'AI, quando interviene, scrive solo la frase che lo accompagna. La
[pagina 3](./03-cosa-fanno-ml-e-ai.md) lo spiega nel dettaglio, perché è il
punto su cui è più facile fraintendere.

**Limen non vede sotto terra.** Non sa se quel muro di sostegno è stato
costruito bene, se la rete di drenaggio è intasata, se un cantiere ha tagliato
il piede di un versante la settimana scorsa. Vede la forma del terreno, la
sua storia franosa censita, e il tempo che fa.

## Cos'è, allora

Limen è un sistema che ogni ora prende tre cose:

- **com'è fatto il posto** — la pendenza, le frane già avvenute lì intorno e
  registrate negli inventari nazionali, le zone che i piani di assetto
  idrogeologico classificano come pericolose, il tipo di roccia;
- **cosa sta succedendo adesso** — quanta pioggia è caduta e con che
  intensità, quanto è già zuppo il terreno, se c'è stato un terremoto vicino
  negli ultimi giorni, se il bosco è bruciato nei mesi scorsi, se sta per
  arrivare una piena;
- **cosa dice la storia** — oltre seimila frane italiane datate, con la
  pioggia che le ha innescate, contro cui il sistema viene rigiocato per
  vedere se avrebbe funzionato.

Da queste tre cose calcola un numero fra 0 e 1 per ogni cella da un
chilometro quadrato, lo traduce in una delle cinque classi di colore, e — se
la classe è alta — manda un avviso sui canali configurati.

La copertura è **nazionale: tutte le venti regioni**, circa **312.000 celle**
da un chilometro quadrato (il conteggio esatto e la griglia stanno nel
[README del progetto](../../README.md)). Il pilota su cui il sistema è stato
validato per primo è Puglia e Basilicata.

## A chi serve

**A chi abita un posto in pendenza.** La domanda pratica è sempre la stessa —
"stanotte piove forte, devo preoccuparmi?" — e la risposta onesta oggi è
difficile da trovare: l'allerta regionale copre una zona vasta e omogenea,
mentre due versanti della stessa vallata possono comportarsi in modo molto
diverso. Limen scende al chilometro quadrato e, soprattutto, ti fa vedere
*perché*: quanto pesa la pioggia, quanto pesa il posto.

**Ai Comuni e alla Protezione Civile locale.** Un ufficio tecnico comunale
deve decidere dove mandare la squadra quando le segnalazioni arrivano tutte
insieme. Limen produce una classifica per comune e per cella, con il motivo
accanto a ogni riga: non "zona rossa", ma "pioggia molto sopra la soglia su
un versante con frane censite a poche centinaia di metri".

**A chi coltiva un terreno in pendio.** Il danno arriva raramente di sorpresa:
arriva dopo settimane in cui il terreno si è caricato d'acqua e nessuno lo ha
notato. Limen tiene il conto di quel carico giorno per giorno — è la
componente che chiamiamo *pioggia antecedente* — e lo mostra prima che
l'evento intenso ci arrivi sopra.

**A chi vuole controllare.** Ricercatori, giornalisti, studenti, tecnici
comunali: tutto quello che Limen calcola è ricostruibile. C'è un indirizzo
web che restituisce, per una singola cella, ognuno dei numeri che hanno
composto il punteggio. La [pagina 6](./06-trasparenza-e-riproducibilita.md)
spiega come usarlo.

## Cosa fa, in concreto, quando piove forte

Il ciclo normale è **ogni ora**: il sistema scarica il meteo aggiornato,
ricalcola le celle, salva i punteggi, e manda avvisi solo per le celle che
superano la soglia e per cui non ha già avvisato di recente (lo stesso avviso
ripetuto ogni ora è rumore, e il rumore fa smettere di guardare).

Ma un temporale non aspetta lo scoccare dell'ora. Perciò ci sono due
scorciatoie:

- **il radar meteo della Protezione Civile**, letto ogni pochi minuti: se la
  pioggia vista dal radar supera una soglia di intensità su una regione,
  quella regione viene ricalcolata subito, senza aspettare il turno;
- **i punti caldi dei satelliti NASA**, letti a ciclo continuo: quando un
  incendio viene rilevato, il fattore "terreno percorso dal fuoco" si accende
  in poche ore anziché attendere la mappa ufficiale del perimetro bruciato,
  che arriva molto dopo.

C'è poi uno sguardo in avanti: un ciclo **previsionale a 48 ore** che rifà lo
stesso identico calcolo usando la pioggia *prevista* invece di quella caduta.
Gli avvisi che ne nascono sono etichettati **PREVISIONE**, perché una cosa è
dire "sta succedendo", un'altra è dire "potrebbe succedere".

## Dove si guarda

- **La mappa** — l'applicazione web: le celle colorate, la classifica dei
  comuni, il quadro nazionale delle venti regioni, le allerte recenti. Si
  apre senza registrarsi e senza login: i dati sono pubblici, e mettere una
  porta davanti a una pagina pubblica serve solo a dare l'impressione di una
  sicurezza che non c'è.
- **Il simulatore** — nella sezione «Come funziona» dell'applicazione
  (`#/come-funziona`) si muovono i cursori della pioggia e della pendenza e
  si vede il punteggio cambiare. Non è una demo con numeri finti: usa la
  formula di produzione.
- **Questa documentazione** — nell'applicazione alla voce Documentazione
  (`#/documentazione`) trovi esattamente le pagine che stai leggendo.

## Da qui in poi

Se vuoi capire il calcolo, la prossima pagina è
[Come si calcola il rischio della tua cella](./02-come-si-calcola-il-rischio.md).
Se invece la domanda che ti sta a cuore è "quanto mi posso fidare",
salta a [Cosa fanno ML e AI, e cosa no](./03-cosa-fanno-ml-e-ai.md): la parte
finale racconta le misure di verifica, comprese quelle che oggi il sistema
non supera.
