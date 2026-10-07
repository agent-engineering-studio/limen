# Come funziona Limen

**Limen guarda il territorio italiano un chilometro quadrato alla volta e,
per ciascuno, stima ogni ora quanto è esposto a tre pericoli: frane,
allagamenti e incendi.** Lo fa con dati pubblici, con formule scritte e
leggibili, e con una previsione fino a 72 ore. Questa pagina spiega tutto il
motore — i dati, i calcoli, la previsione, l'apprendimento automatico,
l'intelligenza artificiale, la geografia — perché solo chi sa come nasce un
numero può leggerlo bene, e usarlo per anticipare un disastro invece di
inseguirlo.

> Limen **affianca** l'allertamento ufficiale della Protezione Civile e non
> lo sostituisce: l'allerta che ha valore legale è quella del bollettino. Ma
> un bollettino dà un colore per zona e per due giorni; Limen dice **dove**
> dentro la zona, **perché**, e **cosa arriva dopo**. La mappa li mostra uno
> accanto all'altro, e quando Limen vede qualcosa che il bollettino non ha
> lo dice: è il suo lavoro.

<!-- schema-fase: tutte -->

```mermaid
flowchart LR
  D["I dati<br/>il posto e il momento"] --> P["Il punteggio<br/>un numero fra 0 e 1"]
  P --> C["La classe<br/>cinque livelli"]
  C --> A["L'avviso<br/>a chi, quando"]
```

## Cosa aggiunge al bollettino

| | Bollettino di criticità | Limen |
|---|---|---|
| **Dove** | Una zona di allerta: decine di comuni insieme (187 in Italia) | Ogni chilometro quadrato: quale versante, quale tratto di pianura |
| **Quando** | Oggi e domani, emesso una volta al giorno entro le 16 | Ogni ora, e la previsione fino a 72 ore |
| **Cosa** | Rischio idrogeologico, idraulico, temporali | Frane, allagamenti **e incendi** |
| **Perché** | Un colore | I numeri che lo producono: pioggia contro soglia, portata del fiume, siccità, pendenza, frane del passato |
| **Valore legale** | Sì: è l'allerta | No: è un'anticipazione da verificare |

Il confronto nella lista dei comuni è per tipo di rischio — frane contro
idrogeologico, allagamenti contro idraulico — e ha tre esiti:

- **Limen vede prima**: un pericolo alto, o previsto alto, dove la zona non ha
  allerta. La riga dice su quante celle, con che pioggia e quando arriva il
  picco, anche se cade oltre i due giorni del bollettino. È il caso per cui
  Limen esiste: un segnale locale da tenere d'occhio prima che diventi
  un'allerta.
- **Limen conferma e dice dove**: entrambi segnalano; Limen indica le celle.
- **Il bollettino è più severo**: si segue il bollettino. Spesso è un
  temporale, che il bollettino prevede a scala di zona e una griglia meteo
  non vede ancora.

Per gli incendi il bollettino idrogeologico non dice niente: lì il segnale è
solo di Limen.

## In breve

| Domanda | Risposta |
|---|---|
| Che cosa misura | Il **pericolo** di frana, allagamento e incendio, cella per cella, adesso e fino a 72 ore |
| Su cosa | **312.550 celle** da 1 km² in tutte le **20 regioni**, raggruppate nei **7.901 comuni** ISTAT |
| Ogni quanto | Ogni **ora** l'adesso; ogni **notte** la previsione a +24, +48, +72 ore |
| Con quali dati | Solo **open data** pubblici: ISPRA, Protezione Civile, INGV, Copernicus, ECMWF, NASA, ISTAT, OpenStreetMap |
| Chi decide il numero | Una **formula deterministica** per ogni pericolo, scritta in file di configurazione leggibili |
| Che ruolo ha l'AI | **Spiega** i numeri a parole e li controlla; **non li cambia mai** |
| Che ruolo ha il machine learning | **Sfida** la formula in ombra e la sostituisce solo se la batte su eventi reali, per decisione umana |

## Come leggere la mappa

### Il colore dice quanto, la lettera dice cosa

La mappa usa **una sola scala di colori** per i tre pericoli, dal quasi
invisibile al rosso: nessuno, basso (verde petrolio), moderato (giallo), alto
(arancio), molto alto (rosso). È l'ordine delle allerte della Protezione
Civile, che chi legge conosce già. La scala è scelta perché **ogni coppia di
classi resti distinguibile anche per chi non vede i colori** (deuteranopia,
protanopia, tritanopia): un test automatico lo verifica a ogni modifica.

Il colore dice **quanto**; il pericolo lo dicono le lettere **A** (allagamento),
**F** (frana), **I** (incendio) dentro le celle in classe alta (da zoom 10),
il bordo colorato delle stesse celle e l'intestazione «Livello attivo» in
alto a sinistra. Nella vista «Tutti i pericoli» ogni cella mostra il peggiore
dei tre: la lettera è il modo di sapere quale.

| Classe | Significato operativo |
|---|---|
| Nessuno | Condizioni ordinarie. Non vuol dire «sicuro»: vuol dire «nessun segnale» |
| Basso | Qualche ingrediente è attivo, ma non insieme |
| Moderato | Il sistema comincia a dire qualcosa: un innesco su un posto predisposto |
| Alto | Più ingredienti pesanti insieme |
| Molto alto | La condizione peggiore che il modello sa riconoscere |

> **Una cella rossa non è un'allerta rossa.** I colori seguono l'ordine di
> quelli delle allerte perché si leggono senza legenda, ma dicono il
> **pericolo stimato** da Limen in quel chilometro quadrato. L'allerta, con il
> suo colore, è solo quella del bollettino: sulla mappa nel livello «Allerte
> Protezione Civile», nella lista nella riga di ogni comune.

Ogni pericolo ha le sue soglie fra le classi, perché i numeri non hanno lo
stesso significato: sono nella sezione dei motori.

### Grigio non vuol dire tranquillo

Una cella **grigia** non è stata misurata: il dato che serviva (il meteo per
l'incendio, la pioggia o la portata per gli allagamenti) non è arrivato. Per un
motore che moltiplica, l'assenza di dato darebbe zero — indistinguibile da
una cella davvero calma. È l'unico modo in cui un sistema di allerta
sbaglierebbe **in direzione rassicurante**, e Limen lo impedisce: il grigio è
lo stesso delle celle mai valutate, e queste celle non entrano in nessun
conteggio.

### Gli strumenti sopra la mappa

| Strumento | A cosa serve |
|---|---|
| **Quadro nazionale** (colonna) | Una riga per pericolo con il numero di aree e la classe; cliccandola si filtra la mappa. «Tutti i pericoli» mostra il peggiore in ogni cella |
| **Solo sopra soglia** | Nasconde le celle sotto Moderato: un quarto d'Italia è in classe bassa e coprirebbe la mappa. Le celle non misurate restano visibili |
| **Livelli** | Contesto da sovrapporre: allerte ufficiali di oggi, frane censite (IFFI), pericolosità PAI, pericolosità idraulica, alluvioni osservate, aree bruciate |
| **Timeline** Ora / +24 / +48 / +72 h | Scorre la previsione per cella; sotto ogni scadenza c'è il momento vero, e una scadenza già passata lo dice |
| **Ispettore** (clic su una cella) | Il punteggio di ogni pericolo, le sue componenti, la pioggia prevista; sul futuro mostra il valore previsto e dichiara che il resto è di adesso. In fondo, **«Come nasce questo numero»**: chi ha fatto cosa (formula, meteo, ML, AI), la pioggia secondo cinque modelli meteo e il link al racconto della regione in «Regioni da monitorare» |
| **Ricerca** (⌘K) | Porta la mappa sul comune e ne evidenzia il confine |
| **Regioni da monitorare** (menu) | Le venti regioni in ordine di pericolo stimato, con l'allerta ufficiale, i comuni da guardare e il racconto dell'AI di ciascuna |

### La lista dei comuni

Il comune è l'unità su cui si decide qualcosa, e la colonna li ordina dal più
esposto. Per ognuno:

- il **numero in testa** è il **pericolo peggiore** del comune, da 0 a 1, con
  il suo nome. Non è una media: un incendio alto non diventa basso perché oggi
  non piove;
- i chip **F / A / I** danno i tre valori affiancati, sempre tutti. Accanto
  agli allagamenti, la pioggia prevista contro la soglia; accanto all'incendio,
  l'FWI e **quanto è insolito per il mese** in quel punto («insolito per
  ottobre (96°)», «nella norma per ottobre»);
- la **freccia** dice il verso verso le 72 ore, confrontando solo i pericoli
  che hanno una previsione;
- la riga **Allerta ufficiale** riporta il bollettino della Protezione Civile
  per la zona del comune, oggi e domani, e dice quando Limen ne diverge.

L'**ordine** della lista non è solo il punteggio: un comune sale se il
pericolo peggiore è vicino a case, strade e ferrovie (l'**esposizione**), e
prende un incremento del 15% per ogni pericolo in più oltre la soglia nello
stesso momento. La riga «In cima per» dice il perché, a parole.

## Il territorio in celle

### Perché una griglia da 1 km

L'Italia è divisa in **312.550 quadrati da un chilometro di lato**. Una frana
o un'esondazione non conoscono i confini comunali: un comune di montagna può
contenere un versante instabile e un pianoro stabile, e dargli un colore solo
vorrebbe dire allarmare metà comune o rassicurare l'altra metà a torto. Il
chilometro è la risoluzione a cui arrivano davvero i dati: i modelli
meteorologici lavorano a maglie di chilometri, e una griglia più fine
darebbe l'apparenza di un dettaglio che il dato sotto non ha.

### Dalle celle ai comuni e alle zone di allerta

| Livello geografico | Come si costruisce | A cosa serve |
|---|---|---|
| **Cella** (1 km²) | Griglia regolare per regione | Il calcolo |
| **Comune** (7.901) | Confini ISTAT; ogni cella appartiene ai comuni che interseca | La lista, la ricerca, il confine evidenziato |
| **Regione** (20) | Unità di calcolo e di previsione | Il quadro a piccola scala |
| **Zona di allerta** DPC (187) | Poligoni del bollettino nazionale | Il confronto con l'allerta ufficiale: un comune prende la zona del suo punto interno |
| **Nodo meteo** | Reticolo regolare: 0,1° per la pioggia degli allagamenti, 0,25° per l'indice incendi | Ogni cella legge il nodo più vicino: un numero per regione copiato su tutte le celle sbaglierebbe di decine di millimetri |

Le geometrie sono conservate in coordinate geografiche (EPSG:4326); distanze
e aree si calcolano nella proiezione equivalente europea (EPSG:3035), dove un
chilometro è un chilometro in tutta Italia.

### Cosa si vede a che zoom

A scala nazionale una cella è più piccola di un pixel: la mappa mostra le
**regioni** finché non compaiono le celle, i **comuni** fra gli zoom 7 e 11,
le **celle** da zoom 8 (da 7 per allagamenti, incendio e previsione). La previsione per cella
compare da zoom 7: più lontano, una sola richiesta peserebbe megabyte.

## Il layer dati: gli open data

Ogni numero di Limen viene da un dato pubblico che chiunque può scaricare
senza contratti e senza abbonamenti. Nessuna fonte commerciale, nessuna
chiave a pagamento necessaria.

### I dati lenti: com'è fatto il posto

| Dato | Fonte | Uso | Copertura |
|---|---|---|---|
| Frane già avvenute (IFFI) | ISPRA | Quante frane cadono entro 500 m dalla cella: l'indicatore più predittivo che esista | tutte le celle |
| Pericolosità da frana (PAI) | ISPRA, mosaico dei Piani di Assetto Idrogeologico | La classificazione ufficiale P1-P4 | 167.693 celle (dentro le aree perimetrate) |
| Pericolosità idraulica | ISPRA, mosaico PGRA | Quanto è allagabile la cella | 132.535 celle (bacini studiati) |
| Forma del terreno | Modello digitale TINITALY (INGV) | Pendenza media della cella | 99,7% |
| Tipo di roccia | Carta geologica ISPRA | Peso litologico (argille e flysch franano più dei calcari) | 99,8% |
| Uso del suolo | CORINE Land Cover (Copernicus) | Combustibile per l'incendio, tessuto urbano per l'esposizione | tutte |
| Suolo impermeabile | Copernicus Imperviousness | Amplifica la pioggia degli allagamenti in città | tutte |
| Strade, ferrovie | OpenStreetMap | Esposizione: quanto conta allertare una cella | tutte |
| Confini | ISTAT | Comuni e regioni | 7.901 comuni |

### I dati veloci: cosa sta succedendo

| Dato | Fonte | Cadenza | Uso |
|---|---|---|---|
| Pioggia, umidità del suolo, temperatura, vento | Open-Meteo (modelli ECMWF e ICON), **istanza ospitata su questo server** | ogni ora | Innesco delle frane, pioggia degli allagamenti, indice incendi |
| Portata dei fiumi | GloFAS (Copernicus), via Open-Meteo pubblico | ogni 6 ore | Ramo fluviale degli allagamenti |
| Onde e mareggiate | Open-Meteo Marine | ogni ora | Componente idrologica delle frane costiere |
| Terremoti | INGV (catalogo e ShakeMap) | ogni ora | Componente sismica delle frane |
| Fuochi attivi | NASA FIRMS | ogni 45 minuti | Apre la finestra post-incendio in poche ore |
| Aree bruciate | Copernicus EFFIS | a ogni sincronizzazione | Perimetri degli incendi passati: aprono la finestra post-incendio |
| Pioggia vista dal radar | Protezione Civile (mosaico radar nazionale, 1 km, 5 minuti) | ogni 15 minuti | Sveglia: ricalcola subito la regione dove il radar vede un nubifragio |
| Bollettino di criticità | Protezione Civile | ogni ora (esce entro le 16) | L'allerta ufficiale accanto alla nostra |

Perché un'istanza meteo propria: l'interfaccia pubblica di Open-Meteo ha un
tetto di 10.000 richieste al giorno, e il calcolo orario di tutta Italia ne
chiede diecimila a ogni giro. Quando il tetto è saltato, allagamenti e
incendio hanno dato zero su tutta l'Italia per **mancanza di dato**, non per
quiete. Oggi previsioni e archivio vengono da un'istanza sul server; solo la
portata dei fiumi (GloFAS) resta pubblica, perché non si può ospitare.

### I dati di verità: per sapere se funziona

| Dato | Fonte | Uso |
|---|---|---|
| Frane innescate da pioggia, datate | Catalogo e-ITALICA, CNR-IRPI (6.312 frane, 1996-2021) | Tarare le soglie di pioggia e verificare il motore frane |
| Alluvioni osservate da satellite | Copernicus Emergency Management Service | Verificare il motore degli allagamenti |
| Perimetri degli incendi | Copernicus EFFIS | Verificare il motore incendio |
| Rianalisi meteo | ERA5 e CERRA (Copernicus) | Rigiocare il passato, costruire le climatologie |

## I tre motori

Ogni pericolo ha la sua formula, perché ogni pericolo ha la sua fisica. Tutte
e tre sono **funzioni pure**: dati gli stessi ingredienti restituiscono lo
stesso numero, su qualunque computer, senza consultare la rete né un modello
linguistico. Ogni peso e ogni soglia stanno in un file di configurazione
leggibile (`config/hazards/<pericolo>.yaml`), e dei test verificano che nel
codice non ce ne sia nessuno nascosto.

### Frane: una somma pesata

```
punteggio = 0,35 × il posto (S)
          + 0,40 × la pioggia (M)
          + 0,15 × il terremoto (E)
          + 0,07 × il fuoco (F)
          + 0,03 × l'acqua (H)
```

| Componente | Cosa contiene |
|---|---|
| **S** — il posto (35%) | Frane IFFI entro 500 m (37,5%, satura a 8), pendenza (30%, satura a 45°), classe PAI (22,5%), litologia (10%) |
| **M** — la pioggia (40%) | Eccesso sulla soglia d'innesco di Caine (45%), pioggia dei giorni prima (30%), umidità del suolo (25%); bonus per pioggia su neve |
| **E** — il terremoto (15%) | Scuotimento al suolo degli eventi di magnitudo ≥ 3,5 negli ultimi 7 giorni, che decade col tempo |
| **F** — il fuoco (7%) | Una campana con picco a 6 mesi da un incendio che ha toccato la cella, nulla oltre 24 mesi |
| **H** — l'acqua (3%) | Pericolosità idraulica, spinta da pioggia prevista, piena dei fiumi e mareggiate |

La **soglia di Caine** dice, per ogni durata, l'intensità oltre la quale le
frane cominciano davvero ad accadere: 7,2 mm bastano se cadono in un'ora, ne
servono 28,4 in un giorno. Le soglie sono state ricalcolate sul catalogo
e-ITALICA (5.974 eventi di pioggia con frana): sopra la soglia sta il 95%
delle frane vere.

Classi: nessuno sotto 0,15, basso fino a 0,35, moderato fino a 0,55, alto
fino a 0,75, molto alto oltre.

<!-- componente: simulatore -->

### Allagamenti: il posto per la spinta più forte

Il pericolo si chiama **allagamento** e non alluvione: il motore stima acqua
che si accumula dove la zona è allagabile — pioggia forte su suolo che non
la beve, o un fiume sopra la sua piena ordinaria — non un'alluvione in
corso.

```
punteggio = suscettibilità idraulica × max(pioggia, fiume)
```

- **Suscettibilità**: quanto la cella è allagabile secondo il mosaico ISPRA.
  Moltiplica, non somma, perché l'acqua scende: un crinale non si allaga per
  quanto forte piova a valle. Una cella fuori dalle zone studiate prende un
  valore prudente (0,15), non zero: «non studiato» non è «non allagabile».
- **Pioggia**: la pioggia **prevista nelle prossime 72 ore** sul nodo della
  cella, oltre la soglia di 40 mm, fino alla saturazione a 120 mm; smorzata
  se il suolo è asciutto, amplificata dove il suolo è cementato.
- **Fiume**: la portata prevista da GloFAS divisa per la **piena ordinaria di
  quel corso d'acqua** (non per un valore regionale: il Po e un torrente non
  si confrontano). Un fiume senza riferimento è «non so», non «basso».
- È un **massimo**, non una somma: pioggia e fiume sono due modi diversi di
  finire sott'acqua, e sommare due segnali moderati ne inventerebbe uno
  severo.
- **Cascata post-incendio**: un versante bruciato da pochi mesi fa scorrere
  la pioggia invece di assorbirla. Il ramo pluviale cresce fino a 1,6 volte,
  con picco a 4 mesi e nulla oltre 18, **solo nelle celle davvero toccate**
  da un perimetro EFFIS o da fuochi FIRMS.

**Quanto è rara quella pioggia lì.** Le soglie della pioggia sono le stesse
in tutta Italia, e il clima no: 105 mm in tre giorni a Trieste capitano circa
una volta l'anno, a Bari mai nel decennio 2016-2025. Limen tiene per ogni nodo
la distribuzione delle piogge a 72 ore di dieci anni (ERA5), e nella lista dei
comuni scrive accanto ai millimetri quanto spesso capitano in quel punto: «qui
capita circa una volta l'anno», oppure «qui capita una volta ogni ~8 anni».

Abbiamo anche provato a usare questa distribuzione per **spostare le soglie**
nei climi piovosi. Misurato sulle alluvioni osservate da satellite, toglieva
segnali a vuoto ma perdeva alluvioni vere: in Lombardia il 73 % degli eventi
segnalati scendeva al 64 %. Per un sistema che serve ad anticipare, perdere
eventi è il difetto peggiore, quindi le soglie restano quelle tarate e la
rarità resta un'informazione accanto al numero.

> Il numero degli allagamenti **guarda avanti**: può essere alto sotto un cielo
> sereno, se il peggioramento è atteso nei prossimi tre giorni. Per questo la
> mappa scrive «prossime 72 h» e non «adesso».

Classi: nessuno sotto 0,10, basso fino a 0,25, moderato fino a 0,45, alto
fino a 0,70, molto alto oltre.

### Incendio: il tempo, modulato dal terreno

```
punteggio = FWI normalizzato × (0,25 + 0,60 × combustibile + 0,15 × pendenza)
```

- **FWI** (Fire Weather Index, Van Wagner 1987) è l'indice meteorologico
  degli incendi usato da Copernicus EFFIS. Combina tre codici di umidità dei
  combustibili — dalla lettiera (FFMC) al suolo profondo (DC) — con il vento.
  È calcolato una volta al giorno sulle condizioni di mezzogiorno, per nodo
  meteo da 0,25°, come una catena: ogni giorno parte da quello prima.
- Il **codice di siccità DC** è la memoria lunga: sopra 500 il suolo e i
  combustibili grossi sono molto secchi, come a fine estate, e si abbassano
  solo con piogge abbondanti. È il motivo per cui il pericolo può restare
  alto in un ottobre mite, se non piove da settimane.
- Il **terreno modula il tempo, non si somma**: sotto un acquazzone di
  gennaio nessuna pineta deve risultare pericolosa. La quota fissa del 25% è
  il pericolo di un fuoco che arriva da fuori: la roccia nuda in condizioni
  estreme non vale zero.

> È il pericolo **potenziale**: quanto si propagherebbe un incendio se
> partisse. **Non** è la probabilità che parta, e non dice che c'è un fuoco
> in corso.

Classi, allineate alle bande EFFIS: nessuno sotto 0,12 (FWI 6), basso fino a
0,24 (FWI 12), moderato fino a 0,42 (FWI 21), alto fino a 0,76 (FWI 38),
molto alto oltre.

**Rispetto al solito.** Le classi sono assolute: FWI 36 è «alto» ad agosto
come a ottobre. Per questo Limen tiene anche una **climatologia**: per ogni
nodo e ogni mese, la distribuzione dell'FWI su dieci anni di archivio
(2016-2025). L'ispettore la usa per dire, per esempio, «più alto del 98% dei
giorni di ottobre in questo punto»: lo stesso valore ad agosto sarebbe
ordinario. Lo stesso confronto compare nella lista dei comuni, accanto al
valore dell'incendio.

**Perché le classi non si abbassano in autunno.** Si potrebbe pensare che un
«alto» di ottobre valga meno di uno d'agosto, visto che a ottobre brucia l'1 %
dell'area dell'anno. Lo abbiamo misurato: rigiocando l'indice su 300 nodi dal
2016 al 2024 e confrontandolo con i fuochi osservati da satellite (NASA FIRMS)
su vegetazione naturale, in un giorno di classe alta la probabilità di un
fuoco è 1,18 % in luglio-agosto e 0,97 % a ottobre. Ottobre brucia poco perché
ha pochi giorni alti — il 7 % contro il 38 % — non perché «alto» valga meno.
Le classi restano quelle di EFFIS, e il confronto col mese serve a dire quando
un giorno alto è raro, non a ridimensionarlo.

| Mese | Fuoco in un giorno «alto» | In un giorno «molto alto» | Giorni alti o più |
|---|---|---|---|
| Luglio-agosto | 1,18 % | 3,49 % | 38 % |
| Settembre | 0,78 % | 1,66 % | 21 % |
| Ottobre | 0,97 % | 1,92 % | 7 % |
| Novembre | 0,81 % | 0,85 % | 2 % |

Una cautela sul confronto col mese: la climatologia è calcolata sulla
rianalisi ERA5, il valore di oggi sui modelli di previsione, che sugli stessi
giorni danno un FWI più alto di circa il 10 % (qualche km/h di vento in più).
Il percentile mostrato è quindi un po' gonfiato: «96°» va letto come «fra i
giorni più secchi del mese», non come una cifra esatta.

## La previsione

### Tre cadenze

| Cadenza | Cosa fa | Perché così |
|---|---|---|
| **Ogni ora** | Calcola l'adesso di tutti e tre i pericoli su tutta Italia, salva le celle cambiate, manda gli avvisi | Deve stare dentro l'ora: niente modelli linguistici, niente sfidanti |
| **Ogni 10 minuti** (asincrono) | Scrive le spiegazioni a parole delle regioni che sono cambiate | Nessuno le aspetta: la mappa mostra il testo deterministico finché non arrivano |
| **Ogni notte** (02:00 UTC) | Previsione per cella a +24, +48, +72 ore; misure del machine learning; manutenzione | La notte misura, il giorno opera |

### Come nasce un numero previsto

La previsione usa **le stesse formule** dell'adesso, con al posto del meteo
osservato quello **previsto** dai modelli (pioggia, umidità, temperatura,
vento). Per ogni cella si salvano le scadenze sopra Moderato; per ogni
comune tutte. Due conseguenze:

- una cella senza riga prevista, per un pericolo la cui previsione è girata,
  è **prevista sotto Moderato**: una risposta, non un vuoto;
- se la corsa notturna salta (un riavvio, un guasto), la timeline segna le
  scadenze **passate** invece di presentarle come futuro.

Una seconda previsione, **per regione**, gira ogni 6 ore su 48 ore e manda
gli avvisi previsionali.

### Il limite di ogni previsione: i modelli non sono d'accordo

Su Trieste, il 6 ottobre 2026, la pioggia prevista in 72 ore andava da 29 mm
(GFS) a 93 mm (ECMWF IFS) secondo il modello meteorologico. Il punteggio legge
un modello solo; l'ispettore della cella mostra la forbice di tutti e cinque,
così si vede quanto quel numero è incerto. Pesarli bene è il primo lavoro del
machine learning, descritto qui sotto.

## Il layer machine learning

### Il campione e gli sfidanti

Il punteggio operativo viene sempre dalla **formula deterministica**, il
*campione*. Accanto può girare un modello di apprendimento automatico, lo
*sfidante* (LightGBM), che vede gli stessi dati, calcola la sua probabilità
e la scrive in una tabella a parte: non colora niente, non manda niente. Le
regole sono scritte nel codice:

- la validazione è **per blocchi geografici**: interi riquadri di territorio
  stanno o nell'addestramento o nella verifica, mai a cavallo, perché un
  modello verificato su celle vicine riconosce il posto invece di imparare il
  fenomeno;
- per essere promosso deve battere la formula **e** superare soglie assolute
  su frane trovate, falsi allarmi, anticipo e calibrazione;
- la promozione è **un comando che una persona digita**: nessun modello si
  promuove da solo.

Durante lo sviluppo lo sfidante delle frane ha misurato un AUC-PR di 0,60
contro 0,28 della formula, e quello degli incendi 0,35 contro 0,24. Sono
misure di sviluppo, non riprodotte su questo server: **in produzione oggi lo
sfidante è spento** (`champion_only`) e decide la formula.

### Il correttore multi-modello della pioggia (in costruzione)

Un modello che impara, dai casi passati, quanto pesare ciascun modello
meteorologico — ICON, Météo-France, ECMWF, GFS e **AIFS**, il modello a reti
neurali di ECMWF — e quanto è larga l'incertezza. Restituisce la pioggia
probabile e una forbice (10°-90° percentile) invece di un numero solo. Il
dataset si raccoglie di notte (previsioni dal 2024 con il loro anticipo,
pioggia osservata ERA5); sarà adottato solo se riduce l'errore sulle piogge
forti, misurato insieme al tasso di base.

### Come si misura una previsione di disastri

Un sistema che dice «pericolo» ogni giorno d'estate trova tutti gli incendi e
non serve a niente. Per questo ogni verifica riporta **due numeri insieme**:
quante volte l'evento vero era stato segnalato (*hit rate*) e quante volte
il sistema segnala in generale (*tasso di base*). Esempio misurato in
Basilicata sugli incendi del 2025: segnalati il 79% dei giorni con incendio
vero, contro un tasso di base del 43%.

## Il layer AI

### Cosa fa e cosa non può fare

I modelli linguistici **riformulano**: trasformano il risultato numerico in
un testo che un operatore di turno capisce alla prima lettura, e ne
estraggono una diagnosi strutturata (causa dominante, anomalie, finestra di
attenzione, confidenza). **Non toccano mai i numeri**: punteggi, classi e
avvisi sono deterministici, e un test automatico fallisce se una risposta
del modello cambia un solo valore. Gli avvisi non contengono testo generato.

### Le spiegazioni per pericolo

Ogni pericolo ha il suo prompt, scritto per la sua fisica: quello
degli allagamenti dice che il numero guarda avanti e che un fiume «n.d.» non è
un fiume basso; quello dell'incendio che è un pericolo potenziale, non la
probabilità di un fuoco. Un pericolo senza prompt resta senza spiegazione:
una voce che racconta le frane parlando di un incendio è peggio del
silenzio. Una regione si rispiega solo quando la sua classe dominante cambia,
o dopo 12 ore. La spiegazione si legge nella pagina **Regioni da monitorare**, una
volta per regione e accanto ai numeri da cui nasce, con l'ora in cui è stata
scritta; il marchio di chi fornisce il modello sta in testata. L'ordine delle regioni lo decidono i numeri — la classe più
alta, adesso o prevista, poi le aree in classe alta —: l'AI racconta una
regione, non la sceglie. Se il modello non ha risposto, il testo non viene
attribuito all'AI.

### I modelli e dove girano

| Nome nel gateway | Modello | Dove | Uso |
|---|---|---|---|
| `fast`, `chat`, `extract` | Qwen3 4B e 8B | GPU del server (llama.cpp) | Compiti brevi, estrazione per il knowledge graph |
| `embed` | Qwen3-Embedding 0,6B | CPU del server | Ricerca semantica nei documenti |
| `quality-local` | GLM-5.2 (colibrì) | server, dal disco | Solo lavori notturni: genera a decine di secondi per parola |
| `quality-cloud` | Claude Sonnet 5.5 (Anthropic) | API, con tetto di spesa | Spiegazioni e diagnosi delle regioni |

Tutto il traffico passa da **un solo gateway** (LiteLLM), che sceglie il
modello per nome, applica il tetto di spesa e passa a un modello di riserva
se uno non risponde. I modelli lenti girano solo di notte, perché il server
è uno solo e di giorno serve la mappa.

## Leggere i dati per prevedere un disastro

Una sequenza che usa tutto quello che Limen sa fare:

1. **Allerta ufficiale prima di tutto.** Il livello «Allerte Protezione
   Civile (oggi)» e la riga nella lista dei comuni: è l'allerta che vale.
2. **Quadro nazionale.** Quale pericolo ha aree in classe alta, e da quanto
   è aggiornato il dato (accanto a ogni riga).
3. **Comuni più esposti, adesso e fra 72 ore.** Il secondo ordinamento trova
   il comune tranquillo oggi e in salita domani: è quello per cui esiste la
   previsione.
4. **Timeline.** Far scorrere +24, +48, +72 sulla regione; controllare che
   le scadenze non siano «passate».
5. **Ispettore.** Da cosa nasce il numero: pioggia oltre soglia o terreno
   predisposto? FWI con siccità di fondo o una giornata ventosa isolata? Per
   l'incendio, quanto è insolito per il mese.
6. **Contesto.** Frane censite, aree PAI, aree bruciate di recente,
   alluvioni passate: spesso dicono più del numero.
7. **Divergenze.** Quando Limen vede prima del bollettino, la riga dice
   cosa, dove e quando: è il preavviso che un bollettino di zona non può
   dare, da verificare sul territorio. Quando il bollettino è più severo, si
   segue il bollettino.

## Limiti dichiarati

- **Il motore frane non ha ancora superato i suoi controlli** su eventi
  reali (issue #122): finché non li supera, la mappa delle frane va letta in
  modo **relativo** — quali celle sono più scure delle vicine — più che per il
  nome della classe.
- **Terremoto e fuoco** valgono insieme il 22% del punteggio frane e in
  condizioni ordinarie sono zero: la classe alta è difficile da raggiungere
  con la sola pioggia.
- **La previsione dipende da un modello meteorologico**, e su un temporale
  localizzato può sbagliare parecchio; la pioggia dei controlli (ERA5) non è
  quella con cui il sistema lavora ogni giorno.
- **Un chilometro è grande** per una frana larga trenta metri; la scarpata
  scalzata dallo scavo del mese scorso, il fosso ostruito, la frana mai
  censita non stanno in nessun dato.
- **Cinque comuni minuscoli** non contengono il centro di nessuna cella
  (issue #152) e non hanno numeri propri.

## La tecnologia

| Strato | Componenti |
|---|---|
| Dati | PostgreSQL 16 con PostGIS; tabelle calde partizionate per giorno; viste materializzate per le mappe |
| Calcolo | Python 3.12; un processo *worker* con lo scheduler (una sola istanza); motori puri e testati |
| Meteo | Istanza Open-Meteo propria (previsione e archivio) |
| Servizi | API REST (FastAPI); server MCP per gli agenti; protocollo A2A |
| Mappe | pg_tileserv (tile vettoriali dalle viste e dalle funzioni SQL); MapLibre |
| Interfaccia | React 19, Mantine 9, TypeScript, Vite |
| Inferenza | Gateway LiteLLM, llama.cpp/llama-swap su GPU, colibrì (GLM-5.2), Claude via API |
| Esercizio | Docker Compose su un solo server, porte sul loopback dietro un reverse proxy; nessun cloud provider |

Tutto è riproducibile: codice Apache-2.0, dati pubblici, configurazioni
leggibili. Lo stack d'inferenza ha un suo Compose per replicarlo su un altro
computer. Le API sono documentate nella pagina **Integrazioni**.

## Glossario

| Termine | Significato |
|---|---|
| **Cella** | Quadrato di 1 km² su cui si calcola tutto |
| **Punteggio** | Numero fra 0 e 1 che riassume il pericolo di una cella |
| **Classe** | Fascia del punteggio, da «nessuno» a «molto alto» |
| **Esposizione** | Quanto conta allertare una cella: case, strade, ferrovie vicine |
| **Non misurato** | Il dato che serviva non è arrivato: grigio, mai «tranquillo» |
| **Soglia di Caine** | Intensità di pioggia oltre la quale le frane cominciano ad accadere, per ogni durata |
| **Pioggia antecedente (API)** | La pioggia dei giorni prima, che il terreno ricorda |
| **FWI** | Fire Weather Index: l'indice meteorologico degli incendi |
| **DC** | Drought Code: la siccità profonda nell'indice incendi |
| **GloFAS** | Il sistema europeo di previsione delle piene fluviali |
| **IFFI** | L'inventario nazionale delle frane di ISPRA |
| **PAI** | Piani di Assetto Idrogeologico: le aree perimetrate come pericolose |
| **Campione / sfidante** | La formula che decide / il modello che la sfida in ombra |
| **Tasso di base** | Quanto spesso il sistema segnala in generale: senza, il tasso di successo non si legge |
| **Bollettino di criticità** | L'allerta ufficiale della Protezione Civile, per zona, oggi e domani |
