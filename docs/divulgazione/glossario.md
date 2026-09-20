# Glossario

Le parole che in queste pagine compaiono senza essere ovvie, in ordine
alfabetico. Ognuna con un esempio, perché una definizione senza esempio si
dimentica in trenta secondi.

<!-- schema-fase: tutte -->

```mermaid
flowchart LR
  D["I dati<br/>il posto e il momento"] --> P["Il punteggio<br/>un numero fra 0 e 1"]
  P --> C["La classe<br/>cinque livelli"]
  C --> A["L'avviso<br/>a chi, quando"]
```

**Anticipo** (in inglese *lead time*) — Quante ore prima di un evento la
segnalazione era già attiva. È il numero che dice se un avviso è servito a
qualcosa: segnalare una frana dieci minuti prima è corretto e inutile.
L'obiettivo che Limen si è dato è **almeno 18 ore**. *Esempio:* nel backtest
delle alluvioni in Emilia-Romagna l'anticipo medio misurato è stato di 50
ore.

**AOI** (*area of interest*, area di interesse) — Il territorio che il
sistema valuta in un singolo giro di calcolo. In Limen coincide di norma con
una regione. *Esempio:* `it-basilicata` è un'AOI, e contiene alcune migliaia
di celle.

**Backtest** — Rigiocare il passato: prendere una finestra storica, far
girare il sistema giorno per giorno come se non si sapesse cosa è successo, e
confrontare i suoi avvisi con gli eventi realmente avvenuti. È l'unico modo
onesto di dire se un sistema di allerta funziona. *Esempio:* la Liguria dal
1° novembre al 5 dicembre 2019, 5.884 celle, 131 frane datate.

**Briefing** — Il paragrafo in italiano che accompagna una situazione di
rischio, scritto dal modello linguistico *dopo* che i numeri sono già stati
calcolati e salvati. Non può modificarli. Se il modello è spento, al suo
posto compare la spiegazione deterministica. *Esempio:* «Su tre celle del
versante orientale la pioggia delle ultime 24 ore supera la soglia locale; il
terreno era già prossimo alla saturazione.»

**Campione e sfidante** (*champion* e *challenger*) — Il campione è il motore
che decide davvero: in Limen è la formula deterministica. Lo sfidante è un
modello candidato che gira in parallelo, viene misurato, e non decide niente
finché una persona non lo promuove. *Esempio:* lo sfidante delle frane
ottiene 0,60 di AUC-PR contro 0,28 del campione, e resta comunque sfidante.

**Cella** — Il quadrato di un chilometro di lato in cui è divisa l'Italia:
circa 312.000 in tutto. È l'unità minima a cui Limen assegna un punteggio.
Non corrisponde a nessun confine amministrativo, perché le frane non li
rispettano. *Esempio:* «la tua cella» è il quadrato di un chilometro che
contiene casa tua.

**Deterministico** — Un calcolo che, a parità di ingressi, restituisce sempre
esattamente lo stesso risultato, ovunque e in qualunque momento. Non impara,
non si adatta, non varia. È la proprietà per cui il punteggio di Limen si può
ricontrollare a mano. *Esempio:* la somma pesata delle sei componenti.

**DTM e pendenza** — Il DTM (*digital terrain model*) è il modello digitale
del terreno: la quota del suolo punto per punto. Dalla quota si ricava la
**pendenza** in gradi, che è uno degli ingredienti del punteggio, saturata a
45°. *Esempio:* una cella a 27 gradi di pendenza media contribuisce 0,6 su 1
al termine di pendenza.

**Falso allarme** (e il suo tasso, in inglese *FAR*) — Una segnalazione non
seguita da alcun evento. Il tasso di falsi allarmi è la quota di segnalazioni
di questo tipo; l'obiettivo di Limen è non superare il 30%. Attenzione a
leggerlo: un "falso" allarme può essere un evento realmente accaduto che
nessun catalogo ha registrato. *Esempio:* una frana in un bosco, senza danni,
spesso non entra in nessun inventario.

**IFFI** — L'Inventario dei Fenomeni Franosi in Italia, curato da ISPRA con
le Regioni: il censimento nazionale delle frane. In Limen è la fonte del
fattore più pesante fra quelli statici, cioè quante frane sono già avvenute
entro 500 metri dalla cella. È incompleto per costruzione, e il sistema ne
tiene conto. *Esempio:* quattro frane censite nel raggio di 500 metri danno
0,5 su una saturazione di otto.

**PAI** — Piano di Assetto Idrogeologico: lo strumento con cui le Autorità di
bacino perimetrano le aree pericolose, classificandole da P1 (moderata) a P4
(molto elevata). ISPRA ne pubblica un mosaico nazionale. *Esempio:* una cella
classificata a pericolosità elevata entra nel calcolo con 0,75 su 1.

**Pioggia antecedente** — La pioggia caduta nei giorni e nelle settimane
precedenti, che conta perché un versante già carico d'acqua reagisce in modo
molto diverso allo stesso temporale. Limen la calcola con un contatore che
ogni giorno sconta del 5% il passato. *Esempio:* 95 mm accumulati contro una
normale stagionale di 80 danno un fattore di 0,56.

**Previsione** — Il ciclo che rifà lo stesso calcolo usando la pioggia
*prevista* invece di quella caduta, tipicamente a 48 ore. Gli avvisi che ne
derivano sono etichettati **PREVISIONE** e tracciati separatamente. Non è una
previsione di frana: è il punteggio che la cella avrebbe se la pioggia
prevista cadesse davvero.

**Punteggio** — Il numero fra 0 e 1 che riassume l'esposizione di una cella
in un dato momento. Diventa una delle cinque classi di colore attraverso
soglie fisse e dichiarate (0,15 / 0,35 / 0,55 / 0,75). *Esempio:* 0,411 è
classe Moderata.

**Shadow** (modalità ombra) — Il regime in cui un modello gira sugli stessi
dati del motore ufficiale, scrive i propri risultati in una tabella separata,
e non influenza in alcun modo mappa e avvisi. Serve a misurarlo in condizioni
reali senza rischiare nulla. *Esempio:* lo sfidante ML gira in ombra una
volta per notte.

**Soglia di pioggia** (curva di Caine) — La curva che dice, per ogni durata
di pioggia, l'intensità oltre la quale le frane cominciano davvero ad
accadere. Sale con la durata molto più lentamente del tempo, perché il
terreno assorbe se gli si dà tempo. In Limen è stata ritarata sulle frane
italiane realmente avvenute. *Esempio:* bastano 7,2 mm in un'ora, ma ne
servono 28,4 in un giorno.

**Tasso di base** — Quanto spesso il sistema segnala in generale, a
prescindere dagli eventi. Va sempre letto accanto alla quota di eventi
anticipati, perché un sistema che segnala sempre anticipa il 100% degli
eventi senza distinguere nulla. *Esempio:* 79% di incendi anticipati contro
un tasso di base del 43% significa che il sistema discrimina; 79% contro 78%
non significherebbe niente.

**Verità** (o *truth set*) — L'elenco di eventi realmente avvenuti contro cui
si misura il sistema. Per le frane è il catalogo e-ITALICA, per le alluvioni
i perimetri allagati osservati dai satelliti europei, per gli incendi i
perimetri EFFIS. Senza una verità, un sistema di allerta non è valutabile:
può solo essere creduto.
