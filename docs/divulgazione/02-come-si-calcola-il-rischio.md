# Come si calcola il rischio della tua cella

**Il numero che colora la tua cella sulla mappa non esce da una scatola
nera: è una somma pesata di sei ingredienti, ognuno dei quali puoi leggere
separatamente.** Questa pagina fa il conto per intero, con i pesi veri presi
dal file di configurazione, e finisce con un esempio seguito passo per passo
fino al colore.

<!-- schema-fase: punteggio -->

```mermaid
flowchart LR
  D["I dati<br/>il posto e il momento"] --> P["Il punteggio<br/>un numero fra 0 e 1"]
  P --> C["La classe<br/>cinque livelli"]
  C --> A["L'avviso<br/>a chi, quando"]
```

Prima il promemoria che vale per tutte queste pagine: quello che segue è uno
strumento di supporto, non l'allertamento ufficiale della Protezione Civile,
e **nessun suo risultato ha valore legale**.

## La cella da un chilometro quadrato

Il territorio italiano è diviso in una griglia di quadrati di **un chilometro
di lato** — circa **312.000 celle** per le venti regioni. Ogni cella ha un
suo identificativo, i suoi numeri, la sua storia. Quando parliamo di "rischio
della tua cella" parliamo del quadrato di un chilometro che contiene casa
tua.

Perché una griglia, e non i confini comunali o le zone di allerta? Perché una
frana non conosce i confini amministrativi. Un comune di montagna può
contenere un versante che scarica acqua da sempre e un pianoro
sostanzialmente stabile: dargli un colore solo significa o allarmare metà
comune senza motivo, o rassicurare l'altra metà a torto. La griglia dà lo
stesso trattamento a tutti i punti del territorio.

Perché un chilometro e non cento metri? Perché è la risoluzione a cui
arrivano i dati che ci sono. La pioggia di un modello meteo europeo è nota
con maglie di diversi chilometri; la portata dei fiumi ancora meno fitta. Una
griglia più fine darebbe *l'apparenza* di un dettaglio che il dato sotto non
ha. È anche uno dei limiti dichiarati del sistema: un chilometro quadrato è
grande per un fenomeno di versante, che può interessare poche decine di
metri.

Ogni cella porta con sé due famiglie di numeri: quelli che cambiano una volta
all'anno o mai — i **fattori lenti**, cioè com'è fatto il posto — e quelli che
cambiano ogni ora — i **fattori veloci**, cioè cosa sta succedendo adesso.

## I fattori lenti: la storia e la forma del posto

Nel codice questo pezzo si chiama `S` (statico) e vale **il 35% del
punteggio finale**. È il numero che risponde alla domanda: *se non piovesse
mai, quanto sarebbe predisposto questo posto a franare?*

Dentro `S` ci sono quattro ingredienti, con questi pesi:

- **Le frane già avvenute lì intorno — peso 37,5%.** Contiamo quante frane
  censite nell'inventario nazionale IFFI cadono entro **500 metri** dalla
  cella (non dal suo centro: da tutto il suo bordo). Il numero viene
  normalizzato con una rampa che arriva al massimo a **otto frane**: da lì in
  su il fattore è 1, perché fra otto e quaranta frane la differenza non
  aggiunge informazione utile. Il criterio non è estetico: a otto la
  capacità del sistema di ritrovare le frane vere si mantiene sopra
  l'obiettivo del 70%, mentre con il vecchio valore fissato a tre quasi ogni
  cella con una frana saturava e smetteva di distinguersi dalle altre.
  *Perché conta:* dove è già franato, franerà ancora. È l'indicatore più
  predittivo che esista in questo campo, ed è anche il più ingiusto, per il
  motivo detto più avanti.
- **La pendenza — peso 30%.** Ricavata dal modello digitale del terreno, in
  gradi, normalizzata su una rampa che satura a **45°**. Una cella a 27° vale
  0,6; una a 45° o più vale 1.
  *Perché conta:* senza pendenza non c'è caduta.
- **La pericolosità dei piani di assetto idrogeologico — peso 22,5%.** È la
  classificazione ufficiale (le classi da P1 a P4) con cui le Autorità di
  bacino hanno già perimetrato le aree pericolose. Riportata su una scala da
  0 a 1.
  *Perché conta:* è il giudizio di chi quel territorio l'ha studiato sul
  campo, e sarebbe assurdo ignorarlo.
- **Il tipo di roccia — peso 10%.** Dalla carta geolitologica: argille,
  flysch, calcari e sabbie non si comportano allo stesso modo quando si
  riempiono d'acqua. Ogni classe litologica ha un suo peso in una tabella di
  conversione.

Manca un quinto ingrediente che nel file c'è ma **pesa zero**: la
suscettibilità calcolata da ISPRA. Non è una svista — è che la sorgente da
cui il sistema legge i dati statici non la serve, e un peso applicato a un
dato assente è un modo silenzioso di sbagliare. Il suo 30% originario è stato
ridistribuito sugli altri tre ingredienti geografici. Questo è il genere di
cosa che preferiamo scrivere che nascondere: il file di configurazione
riporta lo zero e la ragione.

Il risultato di questa somma si chiama `s_static` e si può riassumere così:
**la storia e la forma del posto**, un numero fra 0 e 1 che non cambia finché
non cambia il territorio o l'inventario delle frane.

### Un'onestà necessaria sull'inventario

L'inventario IFFI è la cosa migliore che l'Italia abbia, ed è incompleto. Una
frana avvenuta in un bosco, senza case né strade coinvolte, spesso non entra
in nessun catalogo. Una cella "pulita", quindi, può essere pulita perché è
stabile o perché nessuno è mai andato a guardare.

Il sistema ha una difesa esplicita contro questo errore, chiamata **soglia di
recupero**: una cella con pioggia eccezionale viene comunque valutata, anche
se la sua suscettibilità è bassa, purché il terreno sia già umido. La regola
non è "salta le celle tranquille", ma "salta una cella solo se è tranquilla
**e** la pioggia è sotto la soglia permissiva". È una differenza che vale i
casi rari, cioè esattamente quelli per cui esiste un sistema di allerta.

## I fattori veloci: cosa sta succedendo adesso

### La pioggia — il 40% del punteggio

La componente meteo, `M`, è l'ingrediente più pesante di tutti: **40%**. È
composta a sua volta da tre pezzi.

**Primo pezzo, l'eccesso sopra la soglia di pioggia (45% della componente
meteo).** Qui sta l'idea centrale di tutta la letteratura sulle frane da
pioggia: *non conta quanta acqua cade, conta quanto in fretta cade, e per
quanto tempo*. Venti millimetri sono una pioggia insignificante se cadono in
un giorno, e un problema serio se cadono in un'ora.

La soglia si chiama **curva di Caine**, dal nome del ricercatore che la
propose nel 1980: dice, per ogni durata, l'intensità oltre la quale in quella
zona le frane cominciano davvero ad accadere. Ha questa forma:

```
durata    pioggia totale che raggiunge la soglia (Italia, curva generica)
  1 h     ######  7,2 mm
  3 h     ##########  11,6 mm
  6 h     #############  15,6 mm
 12 h     ##################  21,0 mm
 24 h     ########################  28,4 mm
 48 h     ################################  38,3 mm
 72 h     ######################################  45,6 mm
```

Si legge così: per far scattare la soglia bastano 7,2 mm se cadono in un'ora,
ma ne servono 28,4 se il sistema ha un giorno intero per assorbirli. La curva
sale, ma molto più lentamente del tempo: è il modo matematico di dire che il
terreno, se il tempo glielo concede, l'acqua se la beve.

Gli esempi promessi, con i numeri veri:

- **20 mm in un'ora** — intensità 20 mm/h contro una soglia di 7,2: siamo
  quasi tre volte sopra. Il contributo alla componente pioggia è **0,44** su
  un massimo di 1.
- **20 mm in un giorno** — intensità 0,83 mm/h contro una soglia di 1,18:
  siamo *sotto*. Il contributo è **zero**.
- **60 mm in un giorno** — intensità 2,5 mm/h, il doppio abbondante della
  soglia: contributo **0,33**.

La distanza dalla soglia è misurata in decadi (logaritmi), e una decade piena
— cioè dieci volte la soglia — porta il contributo al massimo. È una scelta
conservativa: significa che anche una pioggia molto violenta non satura da
sola l'intera componente meteo.

Le soglie non sono le stesse in tutta Italia, e questa è la parte del sistema
su cui è stato fatto il lavoro di taratura più importante. Le curve in uso
prima erano quelle pubblicate per l'Italia nel 2010, e rigiocandole contro le
frane realmente avvenute si scopriva che **il 36% delle frane vere era caduto
sotto soglia**: per più di un terzo degli eventi reali il sistema avrebbe
detto "non sta succedendo niente". Le curve attuali sono state ricalcolate
sul catalogo nazionale e-ITALICA — **5.974 eventi di pioggia con frana
misurati dai pluviometri** — cercando, per ogni macroregione, l'inviluppo
sotto cui sta circa il **5% degli eventi**: sopra la nuova soglia sta quindi
il **95% delle frane vere**. L'effetto misurato sulla validazione è che la
quota di frane classificate almeno "Moderata" è salita dal **46,6% al 63,0%**
e quella in classe "Alta" dallo **0,2% al 2,7%**.

Le quattro curve (nord, centro, sud, generica) differiscono come ci si
aspetta: al nord servono **51,3 mm in 72 ore** per raggiungere la soglia, al
sud ne bastano **39,9**. È il segno che al sud piove meno spesso e, quando
piove, il terreno è meno abituato.

Una cosa va detta subito, perché è un difetto aperto e documentato: **oggi la
macroregione non viene assegnata**, e tutto il paese gira sulla curva
generica. Le tre curve regionali sono configurazione scritta e mai usata. In
Puglia e Basilicata questo significa che il sistema pretende 45,6 mm in 72 ore
dove la sua stessa taratura ne chiederebbe 39,9: allerta **meno** di quanto
dovrebbe. È registrato nella issue #122 del progetto insieme alle altre cose
che non funzionano.

**Secondo pezzo, la pioggia dei giorni prima (30% della componente meteo).**
Un versante che ha preso pioggia per tre settimane e uno asciutto reagiscono
in modo opposto allo stesso temporale. Il sistema tiene un contatore che ogni
giorno somma la pioggia caduta e sconta del **5%** quella dei giorni
precedenti: dopo un mese, un millimetro di pioggia vecchia conta per circa un
quinto. È l'indice di pioggia antecedente, in uso in idrologia dagli anni
Cinquanta. Il valore accumulato viene confrontato con quanto è normale per
quella cella in quel mese, e la differenza passa in una curva a S che la
schiaccia fra 0 e 1. Quando non conosciamo la normale stagionale, il
confronto avviene con un valore di riferimento di **80 mm**; quando non
conosciamo proprio nulla, il fattore vale **0,5**, cioè il centro esatto —
così un dato mancante non fa né alzare né abbassare il punteggio.

**Terzo pezzo, l'umidità del suolo misurata (25% della componente meteo).**
Il modello meteo europeo pubblica quanta acqua c'è nei primi 7 centimetri di
terreno e fra 7 e 28. Il primo strato entra in una curva a S centrata su
**0,30** di contenuto d'acqua e ripida: sotto quel valore il fattore crolla
verso zero, sopra sale in fretta verso 1. Un terreno al 38% di umidità dà
0,72; uno al 30% dà esattamente 0,5.

C'è anche un quarto pezzo che compare solo d'inverno: la **pioggia su neve**.
Pioggia calda su un manto nevoso esistente libera in poche ore l'acqua di
giorni di precipitazioni, e il sistema aggiunge un piccolo bonus (fino al
15%) quando trova insieme neve al suolo e pioggia in corso.

### Il terremoto — il 15% del punteggio

La componente `E` si accende quando c'è stato un terremoto vicino. Guarda gli
eventi di **magnitudo 3,5 o superiore** degli ultimi **sette giorni**, prende
per ciascuno la scuotimento stimato al suolo — dalla mappa ufficiale INGV
quando c'è, altrimenti da una formula di stima a partire dalla magnitudo — e
lo fa **decadere con il tempo**: l'effetto si dimezza ogni paio di giorni,
perché un versante scosso si riassesta.

Il valore risultante entra in una curva a S centrata su **0,05 g** di
accelerazione, che è la soglia sotto la quale un terremoto non lascia tracce
meccaniche su un pendio.

Il peso è alto — 15% — perché quando un terremoto conta, conta moltissimo. Ma
in condizioni ordinarie questa componente è **zero**, e questo ha una
conseguenza importante sulla lettura dei colori, spiegata più sotto.

### Il fuoco — il 7% del punteggio

Un versante percorso dal fuoco perde le radici che lo tenevano e sviluppa
una crosta che respinge l'acqua invece di assorbirla: piove uguale, ma
l'acqua scivola invece di infiltrarsi. Il fenomeno non è immediato e non è
eterno. La componente `F` è una **campana centrata a sei mesi dall'incendio**
e nulla fuori dalla finestra **0–24 mesi**: subito dopo il rogo la cenere
tappa ancora i pori, dopo due anni la vegetazione è tornata.

L'altezza della campana — non la sua forma — dipende da quanto è stato severo
l'incendio, misurato attraverso la **densità** di energia rilasciata rilevata
dai satelliti. Densità, non totale: misurando su 2.419 perimetri italiani dal
2012 al 2024, l'energia totale correla con l'area bruciata a 0,63 e la
densità solo a 0,26 — segno che il totale misura soprattutto *quanto era
grande* l'incendio, non quanto era intenso. Usare il totale avrebbe detto che
un incendio grande è per definizione severo.

Per costruzione il moltiplicatore di severità **non può superare 1**: può
solo attenuare un allarme, mai inventarne uno.

### L'acqua — il 3% del punteggio (ma è una storia più lunga)

La componente `H` parte dalla mosaicatura idraulica ISPRA: la mappa
ufficiale delle aree a pericolosità di alluvione, che copre circa **132.000
celle** italiane. Il suo peso nel punteggio *frana* è deliberatamente
piccolo, **3%**: un'area allagabile non è un'area franosa, e confondere le
due cose sarebbe un errore concettuale.

Quello che `H` fa in più è ricevere una **spinta** quando un'alluvione è
prevista: pioggia prevista a 72 ore, portata dei fiumi dal sistema europeo
GloFAS, mareggiate. La spinta è proporzionale alla pericolosità statica del
posto — un colle non si allaga per quanto forte piova a valle — e in assenza
di previsioni vale zero, lasciando la componente identica a prima.

L'alluvione, come pericolo a sé, ha un suo motore separato con la sua
configurazione: la spinta descritta qui riguarda solo il punteggio delle
frane.

### I sensori sul posto — quando ci sono

Se una cella è coperta da strumenti in campo (inclinometri, piezometri,
pluviometri), le loro letture **sostituiscono** le stime del modello per
quella cella, e si aggiunge una componente cinematica che pesa il **20%** del
punteggio finale: quanto si sta muovendo il versante, e se il movimento sta
accelerando. Una velocità intorno ai **5 mm al giorno** è il centro della
curva; un'accelerazione sostenuta fa scattare direttamente l'allarme, secondo
un criterio classico della meccanica dei versanti. Il dato misurato vince
sempre sul dato modellato, e il sistema annota quali input ha sostituito.

## Come si mettono insieme

La somma è questa, e non c'è niente di più:

```
punteggio = 0,35 × il posto
          + 0,40 × la pioggia
          + 0,15 × il terremoto
          + 0,07 × il fuoco
          + 0,03 × l'acqua
```

I cinque pesi sommano a 1, e il programma **si rifiuta di partire** se
qualcuno li modifica in modo che non sommino più a 1. Il risultato è un
numero fra 0 e 1.

Tre cose meritano di essere sottolineate, perché sono scelte e non dettagli:

**Nessuna costante è nascosta nel codice.** Tutti i numeri che hai letto in
questa pagina — i pesi, le soglie, i centri delle curve, i confini delle
classi — stanno in un unico file di testo leggibile,
[`landslide.yaml`](../../src/limen/config/hazards/landslide.yaml). Cambiarne
uno cambia il risultato del sistema; non esiste da nessuna parte un numero
scritto nel programma che il file non dichiari. Ci sono test automatici il cui
solo scopo è dimostrarlo: modificano il file e verificano che l'esito cambi.

**Nessun modello linguistico partecipa al calcolo.** La funzione che calcola
il punteggio non accede alla rete, non legge il database, non chiama nessuna
intelligenza artificiale. Dati gli stessi ingredienti, restituisce sempre lo
stesso numero, su qualsiasi computer.

**La somma è lineare apposta.** Un modello più sofisticato potrebbe cogliere
interazioni che una somma pesata non vede. Ma una somma pesata si spiega a
voce in due minuti e si ricalcola su un foglio di carta, e per un sistema che
dovrebbe aiutare qualcuno a decidere se evacuare una strada questa è una
proprietà che vale più di qualche punto di accuratezza. Il modello più
sofisticato esiste e sta girando accanto a questo: la
[pagina 3](./03-cosa-fanno-ml-e-ai.md) racconta perché non comanda.

## Dal numero al colore: le cinque classi

<!-- schema-fase: classe -->

```mermaid
flowchart LR
  D["I dati<br/>il posto e il momento"] --> P["Il punteggio<br/>un numero fra 0 e 1"]
  P --> C["La classe<br/>cinque livelli"]
  C --> A["L'avviso<br/>a chi, quando"]
```

Il numero viene tagliato in cinque fasce, che sulla mappa usano la scala di
colori dal giallo chiaro al rosso scuro (la tavolozza si chiama YlOrRd ed è
scelta perché resta leggibile anche a chi ha una comune forma di daltonismo;
il colore non è mai l'unica informazione, accanto c'è sempre l'etichetta
scritta e l'intervallo numerico).

- **Nessuna, da 0 a 0,15** — colore chiarissimo, corrispondenza verde. Le
  condizioni ordinarie. Non vuol dire "sicuro": vuol dire "nessun segnale".
  *Cosa fare:* niente di diverso dal solito.
- **Bassa, da 0,15 a 0,35** — giallo tenue, corrispondenza verde. Qualche
  ingrediente è attivo: di solito il posto è predisposto ma il tempo è
  tranquillo, oppure piove su un posto tranquillo.
  *Cosa fare:* niente, ma se abiti in una cella che sta stabilmente qui vale
  la pena sapere perché — guarda il dettaglio della cella.
- **Moderata, da 0,35 a 0,55** — arancio chiaro, corrispondenza allerta
  gialla. Qui il sistema sta dicendo qualcosa: la pioggia ha superato la
  soglia su un posto che ha già una predisposizione.
  *Cosa fare:* tenere d'occhio l'allerta ufficiale della tua regione, evitare
  i sottopassi e le strade di fondovalle se la pioggia continua, non
  parcheggiare sotto una scarpata.
- **Alta, da 0,55 a 0,75** — arancio scuro, corrispondenza allerta arancione.
  Più ingredienti pesanti sono attivi insieme.
  *Cosa fare:* è il momento di seguire il piano di protezione civile
  comunale, non la mappa di Limen. Evitare gli spostamenti non necessari
  nelle aree in pendenza, stare lontani da versanti e argini.
- **Molto alta, da 0,75 a 1** — rosso, corrispondenza allerta rossa.
  *Cosa fare:* vale integralmente quanto dispone la Protezione Civile. Limen
  a quel punto non aggiunge niente a quello che ti stanno già dicendo.

La distribuzione a cui il sistema mira, dichiarata nella configurazione, è:
circa il 70% delle celle in "Nessuna", il 20% in "Bassa", il 7% in
"Moderata", il 2,5% in "Alta" e lo 0,5% in "Molto alta". Serve a evitare il
difetto tipico di questi strumenti, cioè colorare tutto di rosso e rendersi
inutili.

C'è una conseguenza aritmetica di cui è giusto essere consapevoli. Terremoto
e fuoco valgono insieme il 22% della scala, e in condizioni ordinarie sono
entrambi zero: senza un sisma recente e senza un incendio recente, **il 22%
del punteggio è irraggiungibile**, e il massimo praticamente ottenibile con
la sola pioggia su un posto molto predisposto si ferma poco sopra 0,6. La
classe "Alta" è quindi strutturalmente difficile da raggiungere. È una delle
ipotesi in verifica nella issue #122, e finché non è risolta il modo corretto
di leggere la mappa delle frane è **relativo**: guarda quali celle sono più
scure delle vicine, più che il nome della classe.

## Un esempio seguito fino in fondo

Prendiamo una cella in Basilicata, in un giorno di pioggia autunnale. Tutti i
numeri che seguono sono calcolati con le formule e i pesi appena descritti.

**Il posto.** Nella cella e nei 500 metri intorno l'inventario registra
**quattro frane**: quattro su una saturazione di otto fa 0,5. La pendenza
media è **27 gradi**: su una saturazione di 45° fa 0,6. Il piano di bacino la
classifica in pericolosità elevata: 0,75. La litologia è argillosa: 0,6.

    il posto = 0,375×0,5 + 0,30×0,6 + 0,225×0,75 + 0,10×0,6 = 0,596

**La pioggia.** Sono caduti **60 mm nelle ultime 24 ore**, cioè un'intensità
media di 2,5 mm/h. La soglia a 24 ore è 1,13 mm/h: siamo sopra di un fattore
2,2, che in decadi fa 0,35 — il contributo dell'eccesso di pioggia. Il
contatore della pioggia antecedente segna 95 mm contro una normale di 80: il
fattore vale 0,56. L'umidità del primo strato di suolo è 0,38, sopra il
centro di 0,30: il fattore vale 0,72.

    la pioggia = 0,45×0,35 + 0,30×0,56 + 0,25×0,72 = 0,505

**Il resto.** Nessun terremoto negli ultimi sette giorni: 0. Nessun incendio
negli ultimi due anni: 0. La cella non è in zona di pericolosità idraulica: 0.

**Il totale.**

    punteggio = 0,35×0,596 + 0,40×0,505 + 0,15×0 + 0,07×0 + 0,03×0
              = 0,209 + 0,202
              = 0,411

**0,411 cade nella fascia 0,35–0,55: classe Moderata, corrispondenza allerta
gialla.**

Ed ecco, in un solo esempio, tutto quello che c'è da capire su questo
sistema: una pioggia decisamente sopra soglia, su un versante con una storia
franosa documentata e in pendenza, produce una classe *moderata*. Non è
timidezza: è che il posto e la pioggia insieme, senza terremoti e senza
incendi, arrivano lì. Se ti aspettavi il rosso, la parte precedente spiega
perché non arriva — ed è esattamente il motivo per cui questi numeri vanno
letti confrontando le celle fra loro.

**Provalo tu.** Nell'applicazione, alla voce «Come funziona»
(`#/come-funziona`), c'è un simulatore con i cursori: muovi la pioggia, la
pendenza, l'umidità, e guarda il punteggio cambiare. Non è una
dimostrazione con numeri finti — usa la stessa formula descritta in questa
pagina.

E per una cella vera, il dettaglio completo è a un indirizzo web:
`GET /api/cell/{identificativo}/breakdown` restituisce ognuno dei numeri che
hai visto qui, per quella cella, nell'ultimo calcolo effettuato. La
[pagina 6](./06-trasparenza-e-riproducibilita.md) spiega come usarlo.

## Cosa questo calcolo non può sapere

Chiudiamo dove abbiamo aperto, perché un elenco di limiti vale quanto la
formula.

Non sa che quella scarpata è stata scalzata da uno scavo il mese scorso. Non
sa che il fosso di guardia è ostruito dalle foglie. Non sa se la casa ha le
fondazioni su roccia o su riporto. Non vede le frane che nessuno ha censito.
Usa la pioggia di un modello a maglie di chilometri, che su un temporale
localizzato può sbagliare parecchio. E lavora su quadrati di un chilometro di
lato, quando molte frane sono larghe trenta metri.

Ognuno di questi limiti è una ragione in più per leggere Limen accanto agli
avvisi ufficiali, mai al loro posto.
