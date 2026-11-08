# Appendice A. Glossario

Le parole del libro che non sono ovvie, in ordine alfabetico. Ogni voce è
spiegata in una o due frasi semplici, senza dare niente per scontato, e
dice in quale capitolo la parola compare. Dove serve c'è un esempio.

Il glossario parte da quello delle [schede divulgative](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/glossario.md)
e dai capitoli del libro. L'elenco dei capitoli è nell'[introduzione](index.md).

## A

**A parità di carico** — Il modo giusto di confrontare due versioni di una
ricetta: con la *stessa* quantità di territorio in allerta, quale prende più
eventi? Senza questa regola vince sempre la più allarmista. *Cap. [5](05-misurare.md).*

**A2A** (*agent to agent*) — Un modo standard con cui due programmi di
intelligenza artificiale si scambiano richieste. Limen lo offre accanto a
*MCP*. *Cap. [6](06-ml-e-ai.md).*

**Agente AI** — Un programma che usa un modello linguistico (vedi *LLM*) per
leggere informazioni e usare strumenti, per esempio chiedere a Limen il
rischio di un Comune. *Cap. [2](02-le-librerie.md), [10](10-partecipare.md).*

**Allertamento ufficiale** — Il sistema con cui il Dipartimento della
Protezione Civile e i Centri Funzionali delle Regioni pubblicano ogni giorno
un colore (verde, giallo, arancione, rosso) per ogni *zona di allerta*. È
l'unico che ha valore legale; Limen lo affianca e non lo sostituisce.
*Cap. [1](01-il-problema.md), [10](10-partecipare.md).*

**Anticipo** — Quante ore prima di un evento Limen aveva già acceso
l'allerta. Segnalare una frana dieci minuti prima è giusto ma inutile.
*Esempio:* sulle alluvioni dell'Emilia-Romagna l'anticipo misurato è di circa
50 ore. *Cap. [1](01-il-problema.md), [5](05-misurare.md).*

**API** — Lo «sportello» attraverso cui un programma chiede dati a un altro
programma. *Esempio:* la mappa di Limen chiede all'API il colore di ogni
Comune. *Cap. [7](07-come-gira.md), [9](09-cosa-manca.md).*

**Apprendimento automatico** (in inglese *machine learning*, ML) — Un modo di
far «imparare» a un programma dagli esempi del passato invece di scrivergli
le regole a mano. In Limen guarda e viene misurato, ma non decide i colori
della mappa. *Cap. [1](01-il-problema.md), [6](06-ml-e-ai.md).*

**Area di interesse** (in inglese *AOI*) — Il pezzo di territorio che Limen
calcola in un giro: di solito una regione. *Cap. [7](07-come-gira.md).*

**ARPA** — Le Agenzie Regionali per la Protezione dell'Ambiente: in molte
Regioni gestiscono pluviometri e idrometri. *Cap. [9](09-cosa-manca.md).*

**Attribuzione** — La frase con cui si cita la fonte di un dato, come chiede
la sua licenza. *Esempio:* «© OpenStreetMap contributors» sotto la mappa.
*Cap. [8](08-trasparenza.md).*

**AUC** — Un voto fra 0 e 1 a quanto bene un modello mette in cima alla
lista i casi veri. 0,5 è come tirare a caso, 1 è perfetto. La variante
*AUC-PR* è più severa quando i casi veri sono rari, come le frane.
*Cap. [1](01-il-problema.md), [5](05-misurare.md), [6](06-ml-e-ai.md).*

**Avviso** — Il messaggio che Limen manda (per email, Telegram o ad altri
sistemi) quando una cella supera una soglia. Non viene ripetuto ogni ora per
la stessa cella e non ha valore legale. *Cap. [1](01-il-problema.md), [7](07-come-gira.md).*

## B

**Backtest** — Rigiocare il passato: far girare Limen giorno per giorno su un
periodo già avvenuto, come se non si sapesse come è andata, e contare quanti
eventi veri aveva visto prima. È il modo onesto di dire se un sistema
funziona. *Cap. [1](01-il-problema.md), [5](05-misurare.md), [8](08-trasparenza.md).*

**Briefing** — Il breve testo in italiano che accompagna la situazione di una
regione, scritto da un modello linguistico *dopo* che i numeri sono stati
calcolati. Non può cambiarli. *Cap. [1](01-il-problema.md), [6](06-ml-e-ai.md).*

## C

**Calibrazione** — Controllare che un modello che dice «70 %» abbia ragione
davvero circa 7 volte su 10, e correggerlo se no. *Cap. [6](06-ml-e-ai.md).*

**Campione e sfidante** — Il campione è il calcolo che decide davvero i
colori della mappa (in Limen, la formula scritta). Lo sfidante è un modello
che gira accanto, viene misurato e non decide nulla finché una persona non lo
promuove. *Cap. [1](01-il-problema.md), [6](06-ml-e-ai.md).*

**CAP** (*Common Alerting Protocol*) — Il formato internazionale con cui i
sistemi di emergenza si scambiano gli avvisi: chi avvisa, di che cosa, dove,
con quale urgenza. Limen non lo usa ancora. *Cap. [9](09-cosa-manca.md).*

**CARG** — Il progetto nazionale di ISPRA, con Regioni e università, che
disegna le carte geologiche d'Italia in grande dettaglio (1:50.000). Non copre
ancora tutto il Paese. *Cap. [3](03-i-dati.md), [9](09-cosa-manca.md).*

**Carico** — Quanta parte del territorio è in allerta in un giorno qualunque.
Va letto sempre accanto agli eventi presi: accendere tutta la mappa prende
tutti gli eventi, ma non serve a niente. *Cap. [5](05-misurare.md), [10](10-partecipare.md).*

**Cascata** — Quando un pericolo ne prepara un altro. *Esempio:* un versante
bruciato d'estate frana più facilmente con le piogge d'autunno. *Cap. [4](04-i-motori.md).*

**Catalogo dei dati** — L'elenco, dentro Limen, di tutti i dati che servono:
che cosa sono, da dove vengono, con quale licenza e cosa succede se mancano.
*Cap. [3](03-i-dati.md), [8](08-trasparenza.md).*

**Catena FWI** — Vedi *FWI*. Si chiama catena perché il valore di oggi dipende
da quello di ieri. *Cap. [2](02-le-librerie.md), [4](04-i-motori.md).*

**Cella** — Uno dei 312.550 quadrati di un chilometro di lato in cui Limen
divide l'Italia. È la più piccola zona a cui dà un punteggio. *Esempio:* «la
tua cella» è il quadrato che contiene casa tua. *Cap. [1](01-il-problema.md).*

**CEMS** (*Copernicus Emergency Management Service*) — Vedi *Copernicus
EMS*. *Cap. [3](03-i-dati.md), [8](08-trasparenza.md), [9](09-cosa-manca.md).*

**Centro Funzionale** — L'ufficio della Regione che, con la Protezione civile
nazionale, valuta ogni giorno il pericolo meteo e idrogeologico e dirama le
allerte ufficiali. *Cap. [1](01-il-problema.md), [10](10-partecipare.md).*

**Classe di rischio** — Una delle cinque fasce in cui Limen traduce il
punteggio: nessuno, basso, moderato, alto, molto alto. Usa la stessa scala
di colori della Protezione civile. *Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

**Cloud** — Server affittati da grandi aziende (Amazon, Microsoft, Google) e
usati a distanza. Limen sceglie di non usarli e gira su un server proprio.
*Cap. [1](01-il-problema.md), [8](08-trasparenza.md).*

**CNR-IRPI** — L'Istituto di Ricerca per la Protezione Idrogeologica del
Consiglio Nazionale delle Ricerche. Ha prodotto il catalogo delle frane
datate e il modello del terreno a 5 metri che Limen usa. *Cap. [1](01-il-problema.md), [2](02-le-librerie.md), [3](03-i-dati.md), [4](04-i-motori.md).*

**Codice libero** (o *open source*) — Un programma il cui testo è pubblico e
che chiunque può usare, studiare, modificare e ridistribuire, alle condizioni
della sua licenza. *Cap. [1](01-il-problema.md), [8](08-trasparenza.md).*

**Combustibile** — Nel pericolo incendio, la vegetazione che può bruciare:
erba secca, macchia, bosco. Limen la ricava dalla mappa dell'uso del suolo.
*Cap. [4](04-i-motori.md), [5](05-misurare.md).*

**Comune-giorno** — Un Comune in un giorno. Serve a contare il *carico*:
100 Comuni per 10 giorni sono 1.000 comuni-giorno. *Cap. [10](10-partecipare.md).*

**Contenitore** (Docker) — Una «scatola» che racchiude un pezzo del sistema
(il database, la mappa) con tutto ciò che gli serve, così che giri uguale su
qualunque server. *Cap. [2](02-le-librerie.md), [8](08-trasparenza.md).*

**Copernicus** — Il programma europeo di osservazione della Terra. Fornisce a
Limen l'uso del suolo, la portata dei fiumi, le aree allagate e bruciate
viste dai satelliti. *Cap. [1](01-il-problema.md), [3](03-i-dati.md), [8](08-trasparenza.md).*

**Copernicus EMS** (*Emergency Management Service*) — Il servizio europeo per
le emergenze. Il suo *Rapid Mapping* disegna dal satellite le aree allagate
poche ore dopo un disastro; Limen le usa per misurarsi. *Cap. [2](02-le-librerie.md), [5](05-misurare.md).*

**CORINE Land Cover** — La mappa europea dell'uso del suolo: dove ci sono
boschi, campi, città, acqua. *Cap. [3](03-i-dati.md), [4](04-i-motori.md).*

**Creative Commons** — Una famiglia di licenze per opere e dati. *CC BY*
chiede solo di citare la fonte; *CC BY-SA* chiede anche di ripubblicare con la
stessa licenza ciò che se ne ricava. *Cap. [8](08-trasparenza.md).*

**CSI** (*critical success index*) — Un voto unico che mette insieme eventi
presi, mancati e falsi allarmi, cella per cella. È severo; lo usano i servizi
meteo. *Cap. [5](05-misurare.md).*

**CSV** — Il formato più semplice per una tabella: un file di testo con una
riga per record e i valori separati da virgole. Si apre con qualunque foglio
di calcolo. *Cap. [9](09-cosa-manca.md).*

## D

**Database** — L'archivio ordinato in cui Limen tiene celle, punteggi, eventi
e storia. Limen usa PostgreSQL con l'estensione per i dati geografici
PostGIS. *Cap. [2](02-le-librerie.md), [7](07-come-gira.md), [8](08-trasparenza.md).*

**Dati aperti** — Dati pubblicati da un ente perché chiunque li possa usare,
con una licenza che lo permette. Limen usa solo dati aperti. *Cap. [1](01-il-problema.md), [3](03-i-dati.md).*

**Dati di base** — La sezione della scheda di una cella che mostra, per ogni
ingrediente del calcolo, il valore, la fonte e la licenza. *Esempio:* «suolo
impermeabilizzato 42 %», con accanto la frase di Copernicus. *Cap. [8](08-trasparenza.md).*

**DCAT-AP_IT** — Il modo comune, italiano ed europeo, di descrivere un
insieme di dati (chi lo pubblica, che cosa contiene, con quale licenza)
perché compaia nei cataloghi pubblici, come dati.gov.it. *Cap. [9](09-cosa-manca.md).*

**Deriva** (in inglese *drift*) — Quando il mondo cambia rispetto ai dati su
cui un modello ha imparato (un'estate molto più calda, un dato che cambia
fonte), e il modello rischia di sbagliare senza accorgersene. Limen la
controlla ogni notte. *Cap. [6](06-ml-e-ai.md).*

**Deterministico** — Un calcolo che, con gli stessi ingressi, dà sempre lo
stesso risultato. Per questo il punteggio di Limen si può ricontrollare a
mano. *Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

**Discriminazione** — Quanto un sistema distingue i giorni o i posti
pericolosi da quelli tranquilli, invece di dare l'allarme ovunque. Si misura
confrontando gli eventi presi con il *tasso di base*. *Cap. [5](05-misurare.md).*

**DOI** — Un identificativo permanente per un articolo o un insieme di dati,
che continua a funzionare anche se il sito cambia indirizzo. *Cap. [2](02-le-librerie.md), [8](08-trasparenza.md).*

**Doppia licenza** — Lo stesso codice offerto con due licenze: una libera per
tutti e, su richiesta, una diversa per chi non può usare la prima. Il *patto
per chi contribuisce* la rende possibile. *Cap. [8](08-trasparenza.md).*

**DTM e pendenza** — Il DTM (*modello digitale del terreno*) è la quota del
suolo punto per punto. Da qui si ricava la **pendenza**, quanto è ripido un
versante. *Cap. [3](03-i-dati.md), [4](04-i-motori.md).*

**DWD** — Il servizio meteorologico nazionale tedesco. Il suo modello di
previsione (ICON) è uno di quelli che Limen usa tramite *Open-Meteo*.
*Cap. [3](03-i-dati.md), [7](07-come-gira.md).*

## E

**e-ITALICA** — Il catalogo del CNR delle frane italiane innescate dalla
pioggia, con data e luogo. Limen lo usa per misurare il motore delle frane.
*Cap. [2](02-le-librerie.md), [5](05-misurare.md).*

**ECMWF** — Il Centro europeo per le previsioni meteorologiche a medio
termine. Le sue previsioni aperte alimentano l'archivio meteo che Limen tiene
in casa. *Cap. [8](08-trasparenza.md).*

**EFAS** — Il sistema europeo di allerta per le piene di Copernicus, fratello
di *GloFAS* ma solo per l'Europa. Limen non lo usa ancora. *Cap. [9](09-cosa-manca.md).*

**EFFIS** — Il sistema europeo d'informazione sugli incendi boschivi:
disegna dal satellite le aree bruciate. Limen le usa per misurare il motore
incendio. *Cap. [1](01-il-problema.md), [2](02-le-librerie.md), [5](05-misurare.md).*

**EGMS** — Il servizio europeo che misura dal satellite di quanti millimetri
all'anno si muove il suolo. *Cap. [2](02-le-librerie.md), [10](10-partecipare.md).*

**Epica** (*epic*) — Una issue grande che raccoglie altre issue più piccole
verso un unico obiettivo. *Esempio:* l'epica #345, l'obiettivo del 90 %.
*Cap. [10](10-partecipare.md).*

**ERA5** — La *rianalisi* del meteo passato prodotta da *ECMWF* per
Copernicus: il tempo di ogni ora dal 1940 a oggi, su tutta la Terra. Limen la
usa per le prove sugli eventi passati. *Cap. [3](03-i-dati.md).*

**EUPL** — La licenza libera della Commissione europea, valida in tutte le
lingue dell'Unione, usata da Limen dall'11 ottobre 2026. Chi modifica il
codice, anche solo offrendolo come servizio, deve pubblicare le modifiche.
*Cap. [1](01-il-problema.md), [8](08-trasparenza.md).*

## F

**Falso allarme** — Un'allerta non seguita da un evento. Attenzione: a volte
l'evento c'è stato, ma nessuno l'ha registrato. *Cap. [1](01-il-problema.md), [5](05-misurare.md).*

**FESR** — Il Fondo Europeo di Sviluppo Regionale: i soldi europei che le
Regioni distribuiscono con bandi, anche per l'adattamento ai cambiamenti
climatici. *Cap. [10](10-partecipare.md).*

**FIRMS** — Il servizio della NASA che pubblica i fuochi attivi visti dai
satelliti. Limen distingue un incendio di bosco da una fonte di calore fissa,
come un'acciaieria. *Cap. [2](02-le-librerie.md).*

**Fonte** — L'ente o il progetto da cui viene un dato: ISPRA, Copernicus,
ISTAT, OpenStreetMap e così via. *Cap. [3](03-i-dati.md), [8](08-trasparenza.md).*

**Fuori campione** — Provare una regola su eventi che non ha visto mentre
veniva tarata. *Esempio:* tarata sugli incendi 2021-2023, provata su quelli
del 2024-2025. Altrimenti è come dare a uno studente il compito con le
soluzioni. *Cap. [5](05-misurare.md).*

**FWI** (*Fire Weather Index*) — L'indice meteo degli incendi, nato in
Canada e usato in tutto il mondo: dice quanto il tempo (caldo, secco,
vento) favorisce un incendio. *Cap. [1](01-il-problema.md), [2](02-le-librerie.md), [4](04-i-motori.md).*

## G

**GloFAS** — Il sistema globale di previsione delle piene di Copernicus: dice
quanta acqua porteranno i fiumi. La sua licenza vieta di presentarlo come
avviso di piena. *Cap. [1](01-il-problema.md), [3](03-i-dati.md), [8](08-trasparenza.md).*

## H

**HAND** (in inglese *Height Above Nearest Drainage*) — Di quanti metri un
posto sta più in alto del corso d'acqua più vicino. Chi sta pochi metri sopra
il fiume si allaga, chi sta trenta metri sopra no. Limen non lo calcola
ancora: è il dato che ridurrebbe i falsi allarmi dell'alluvione. *Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

**HTTPS** — Il modo protetto (con il lucchetto nel browser) con cui un sito
scambia dati con chi lo visita. *Cap. [7](07-come-gira.md), [8](08-trasparenza.md).*

## I

**IFFI** — L'Inventario dei Fenomeni Franosi in Italia, curato da ISPRA con
le Regioni: più di 721.000 frane censite. Dove la terra è già franata, tende
a franare di nuovo. *Cap. [1](01-il-problema.md), [2](02-le-librerie.md), [3](03-i-dati.md).*

**Impronta digitale** — Un codice calcolato dal contenuto di un file, che
cambia se nel file cambia anche una virgola. Limen la usa per accorgersi se
qualcosa è stato modificato. *Cap. [8](08-trasparenza.md).*

**INGV** — L'Istituto Nazionale di Geofisica e Vulcanologia: pubblica i
terremoti e le mappe di quanto ha tremato il suolo (ShakeMap). *Cap. [1](01-il-problema.md), [2](02-le-librerie.md), [3](03-i-dati.md), [4](04-i-motori.md).*

**Installazione** — Mettere Limen su un server nuovo e caricarci i dati.
Oggi si fa con un comando e poi dal browser. *Cap. [8](08-trasparenza.md), [10](10-partecipare.md).*

**Intelligenza artificiale** (AI) — In questo libro, quasi sempre un *LLM*
che scrive testi. In Limen scrive parole, mai numeri. *Cap. [1](01-il-problema.md), [6](06-ml-e-ai.md).*

**ISPRA** — L'Istituto Superiore per la Protezione e la Ricerca Ambientale.
Pubblica i dati nazionali su frane e aree a pericolo. *Cap. [1](01-il-problema.md), [3](03-i-dati.md).*

**Issue** — Una scheda pubblica sul sito del progetto (GitHub) in cui si
descrive un problema, un'idea o un lavoro da fare, con un numero. *Esempio:*
la issue #406 è il pacchetto rapido dei dati. *Cap. [8](08-trasparenza.md), [10](10-partecipare.md).*

**IT-Alert** — Il sistema nazionale che manda messaggi di allerta ai
telefoni nelle aree colpite da un'emergenza. Limen non lo sostituisce.
*Cap. [10](10-partecipare.md).*

## L

**Libreria** — Un pezzo di programma riusabile che fa una cosa sola, per
esempio scaricare i perimetri degli incendi. Limen ne ha pubblicate undici.
*Cap. [2](02-le-librerie.md).*

**Licenza** — Il testo che dice che cosa si può fare con un programma o un
dato, e a quali condizioni. *Cap. [2](02-le-librerie.md), [8](08-trasparenza.md).*

**LLM** (*large language model*, modello linguistico) — Un programma che
scrive testi dopo aver letto moltissimi esempi. In Limen riassume i
risultati in italiano; può girare in casa o in cloud (per esempio Claude).
*Cap. [1](01-il-problema.md), [6](06-ml-e-ai.md), [8](08-trasparenza.md).*

## M

**MCP** (*Model Context Protocol*) — Un modo standard con cui gli assistenti
AI chiedono dati a un programma. Limen lo usa per rispondere, per esempio,
«qual è il rischio in questo Comune?». *Cap. [2](02-le-librerie.md), [10](10-partecipare.md).*

**Migrazione** — Un file numerato che descrive un cambiamento nella
struttura del database. Una volta applicato non si tocca più: per correggere
se ne aggiunge un altro. *Cap. [8](08-trasparenza.md).*

**Misurato e non misurato** — Se una fonte non risponde, Limen non scrive
«zero pericolo» ma «non misurato», e sulla mappa colora la cella di grigio.
Un dato mancante non deve mai sembrare una giornata tranquilla. *Cap. [1](01-il-problema.md).*

**Modalità ombra** — Vedi *modello in ombra*. *Cap. [6](06-ml-e-ai.md).*

**Modello in ombra** — Vedi *campione e sfidante*: un modello che gira sugli
stessi dati, scrive i suoi risultati a parte e non tocca mappa né avvisi.
*Cap. [1](01-il-problema.md), [6](06-ml-e-ai.md).*

**Motore** — La parte di Limen che trasforma i dati in un punteggio. Ce n'è
uno per pericolo: frana, alluvione, incendio. *Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

**MQTT** — Un modo leggero con cui piccoli sensori mandano le loro misure in
rete. Limen lo usa per ricevere i dati dei sensori. *Cap. [7](07-come-gira.md).*

## N

**Nodo meteo** — Un punto di una griglia regolare (ogni 9-10 km circa) in
cui Limen legge il meteo. Ogni cella usa il nodo più vicino. *Cap. [2](02-le-librerie.md), [4](04-i-motori.md).*

## O

**ODbL** — La licenza di OpenStreetMap. Come *CC BY-SA*, chiede che ciò che si
ricava dalla banca dati resti con la stessa licenza. *Cap. [8](08-trasparenza.md).*

**OGC** (*Open Geospatial Consortium*) — L'organizzazione internazionale che
scrive le regole comuni per scambiare mappe e dati geografici, come *WMS*,
*WFS* e *SensorThings*. *Cap. [9](09-cosa-manca.md).*

**Open-Meteo** — Un servizio meteo aperto. Limen ne tiene una copia sul
proprio server, perché il servizio pubblico ha un limite di chiamate al
giorno. *Cap. [1](01-il-problema.md), [2](02-le-librerie.md).*

**OpenStreetMap** — La mappa del mondo fatta dai volontari. Limen ne usa
strade e ferrovie, e lo sfondo della mappa. *Cap. [3](03-i-dati.md), [8](08-trasparenza.md).*

## P

**P1, P2, P3** — Le tre classi delle aree allagabili dei Piani di bacino:
P3 alta probabilità (un'alluvione ogni 20-50 anni circa), P2 media (ogni
100-200 anni), P1 bassa (eventi rari ed estremi). *Cap. [3](03-i-dati.md).*

**Pacchetto rapido** — I dati del territorio già calcolati per tutta Italia,
in tre file con tre licenze (circa 22 MB in tutto), per installare Limen in
minuti invece che in ore. *Cap. [8](08-trasparenza.md).*

**PAI** (Piano di Assetto Idrogeologico) — Il piano con cui le autorità di
bacino disegnano le aree pericolose per frana e alluvione. ISPRA ne pubblica
un mosaico nazionale, che però non ha valore legale. *Cap. [1](01-il-problema.md), [3](03-i-dati.md), [8](08-trasparenza.md).*

**Patto per chi contribuisce** (in inglese *CLA*) — L'accordo che si accetta
alla prima modifica proposta: resti autore, il lavoro resta libero, e il
curatore può offrirlo anche con un'altra licenza. *Cap. [8](08-trasparenza.md), [10](10-partecipare.md).*

**Pendenza** — Vedi *DTM e pendenza*.

**Perimetro** — Il contorno disegnato di un'area bruciata o allagata. *Cap. [2](02-le-librerie.md), [5](05-misurare.md).*

**Periodo di ritorno** — Ogni quanti anni, in media, ci si aspetta un evento
di quella grandezza. «Piena con periodo di ritorno di cento anni» non vuol
dire che arriva ogni cento anni esatti, ma che ogni anno ha circa una
possibilità su cento. *Cap. [3](03-i-dati.md), [9](09-cosa-manca.md).*

**Piena ordinaria** — La portata che un fiume raggiunge in una piena normale,
di quelle che capitano ogni anno. Limen giudica un fiume «alto» confrontando
la portata prevista con la piena ordinaria *di quel tratto*: dieci metri cubi
al secondo sono tanti per un torrente e niente per il Po. *Cap. [3](03-i-dati.md), [4](04-i-motori.md).*

**Pioggia antecedente** — La pioggia dei giorni e delle settimane prima. Un
versante già zuppo reagisce in modo molto diverso allo stesso temporale.
*Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

**Pluviometro** — Lo strumento che misura quanta pioggia cade, in millimetri.
Un cittadino può costruirne uno e collegarlo a Limen. *Cap. [10](10-partecipare.md).*

**PMTiles** — Un modo di mettere un'intera mappa, divisa in quadratini, in
un solo file che si può pubblicare su qualunque server. Limen lo usa per il
rilievo e gli strati fissi della mappa. *Cap. [2](02-le-librerie.md), [9](09-cosa-manca.md).*

**PNRR** — Il Piano Nazionale di Ripresa e Resilienza, il programma di
investimenti finanziato dall'Unione europea dopo la pandemia. *Cap. [10](10-partecipare.md).*

**Porta** (di un server) — Un ingresso numerato attraverso cui un servizio
riceve richieste. Limen tiene chiuse verso l'esterno tutte le porte tranne
quella del sito. *Cap. [8](08-trasparenza.md).*

**Portata** — Quanta acqua passa in un fiume in un secondo, in metri cubi.
*Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

**Preavviso** — Vedi *anticipo*. *Cap. [5](05-misurare.md).*

**Previsione a 72 ore** — Lo stesso calcolo rifatto con il meteo previsto
invece di quello osservato, per vedere come cambierà la mappa nei tre giorni
successivi. *Cap. [1](01-il-problema.md), [4](04-i-motori.md), [7](07-come-gira.md).*

**Protezione civile** — Il sistema pubblico che previene e gestisce le
emergenze: il Dipartimento nazionale, le Regioni, i Comuni, i volontari.
*Cap. [1](01-il-problema.md), [10](10-partecipare.md).*

**Punteggio** — Il numero fra 0 e 1 che riassume quanto una cella è esposta a
un pericolo in un dato momento. Diventa una delle cinque *classi*. *Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

**PyPI** — L'archivio pubblico dei pacchetti per il linguaggio Python, da cui
chiunque può scaricare le librerie di Limen. *Cap. [2](02-le-librerie.md).*

## R

**Radar meteo** — Lo strumento che vede la pioggia mentre cade, su tutta
Italia. Quello della Protezione civile è uno degli ingredienti di Limen.
*Cap. [1](01-il-problema.md), [3](03-i-dati.md).*

**README** — Il file di presentazione di un progetto, il primo che si legge
quando lo si apre sulla piattaforma GitHub. *Cap. [1](01-il-problema.md), [2](02-le-librerie.md), [6](06-ml-e-ai.md), [10](10-partecipare.md).*

**Rianalisi** — Una ricostruzione del meteo passato, fatta con modelli e
osservazioni. È precisa a grandi linee, ma può perdere un temporale
localizzato. *Cap. [1](01-il-problema.md), [5](05-misurare.md).*

**Riproducibilità** — La possibilità, per chiunque, di rifare un calcolo con
gli stessi ingredienti e ottenere lo stesso risultato. *Cap. [8](08-trasparenza.md).*

**Rodaggio** (in inglese *spin-up*) — Il tempo che un calcolo «a catena» ha
bisogno di girare prima di dare valori affidabili. *Esempio:* l'indice meteo
degli incendi ricorda l'umidità dei giorni prima, quindi dopo un'installazione
nuova serve circa un mese. Nelle prove quei giorni non si contano. *Cap. [3](03-i-dati.md), [5](05-misurare.md).*

## S

**Sensore cittadino** — Uno strumento (per esempio un pluviometro) costruito
e installato da un privato. In Limen entra con un *livello di fiducia*:
all'inizio solo per confronto, mai per far scattare un avviso. *Cap. [10](10-partecipare.md).*

**SensorThings** — La regola comune dell'*OGC* per descrivere un sensore,
che cosa misura e le sue misure. Limen la usa come modello per i sensori di
enti e cittadini. *Cap. [9](09-cosa-manca.md).*

**Server** — Un computer sempre acceso che offre servizi in rete. Un *VPS* è
un server virtuale affittato. Limen gira su uno solo. *Cap. [1](01-il-problema.md), [8](08-trasparenza.md).*

**Sfondo** — Il livello di pericolo che un posto ha in un giorno qualunque.
Un'allerta conta come previsione solo se supera il proprio sfondo. *Cap. [5](05-misurare.md), [10](10-partecipare.md).*

**SHAP** — Un metodo per dire quanto ogni ingrediente ha spinto in su o in
giù la risposta di un modello di apprendimento automatico: «la pendenza ha
alzato, la roccia ha abbassato». *Cap. [6](06-ml-e-ai.md).*

**Soglia di pioggia** — Quanta pioggia, in quanto tempo, serve perché le frane
comincino. Più dura la pioggia, più ne serve in totale, ma meno all'ora.
*Esempio:* 7,2 mm in un'ora, oppure 28,4 mm in un giorno. *Cap. [2](02-le-librerie.md), [4](04-i-motori.md).*

**Somma pesata** — Un conto in cui ogni ingrediente vale una parte diversa
del totale. *Esempio:* il punteggio della frana somma il posto, la pioggia, i
terremoti, gli incendi passati e i fiumi, ognuno con il suo peso. *Cap. [4](04-i-motori.md).*

**Spin-up** — Vedi *rodaggio*. *Cap. [3](03-i-dati.md), [5](05-misurare.md).*

**STAC** — Un catalogo standard delle immagini da satellite: che cosa c'è,
dove, quando. Limen lo usa per cercare le immagini radar delle alluvioni.
*Cap. [9](09-cosa-manca.md).*

**Suolo impermeabilizzato** — Terreno coperto da asfalto, cemento, edifici:
l'acqua non entra e scorre via. *Cap. [3](03-i-dati.md), [8](08-trasparenza.md).*

**Sweep** — Il giro di calcolo orario su tutte le celle d'Italia. *Cap. [1](01-il-problema.md), [7](07-come-gira.md).*

## T

**Tasso di base** — Quanto spesso Limen avrebbe dato l'allarme comunque, a
prescindere dagli eventi. Va letto accanto agli eventi presi: 79 % di incendi
presi contro un 43 % di giorni in allerta vuol dire che il sistema distingue;
79 % contro 78 % non vorrebbe dire niente. *Cap. [1](01-il-problema.md), [5](05-misurare.md).*

**Testo di riserva** — Il testo scritto a regole, senza intelligenza
artificiale, che Limen mostra quando il modello linguistico non risponde o il
tetto di spesa è raggiunto. Dice le stesse cose con meno parole. *Cap. [6](06-ml-e-ai.md).*

**Tetto di spesa** — Il limite di 10 dollari al mese per i modelli
linguistici in cloud. Limen lo controlla prima di ogni richiesta. *Cap. [2](02-le-librerie.md), [8](08-trasparenza.md).*

**Token** — Due significati. Per i modelli linguistici è un pezzetto di
parola, l'unità con cui si conta il testo (e il costo). Il *token
d'installazione* è invece una parola segreta che serve solo a chi installa
Limen per avviare i download. *Cap. [8](08-trasparenza.md).*

## U

**Umidità del suolo** — Quanto è bagnato il terreno. Un suolo già zuppo
non assorbe altra pioggia: l'acqua scorre via e il versante si appesantisce.
*Cap. [3](03-i-dati.md), [4](04-i-motori.md).*

**UTC** — L'ora di riferimento mondiale. In Italia è un'ora avanti d'inverno
e due d'estate: le 9:00 UTC di novembre sono le 10:00 italiane. *Cap. [1](01-il-problema.md), [4](04-i-motori.md).*

## V

**Validazione a blocchi geografici** — Vedi *validazione spaziale*.
*Cap. [5](05-misurare.md), [6](06-ml-e-ai.md).*

**Validazione spaziale** (o prova *a blocchi geografici*) — Un modo di
provare un modello su zone d'Italia che non ha mai visto mentre imparava,
per evitare che «ricordi» le celle vicine invece di capire. *Cap. [1](01-il-problema.md), [5](05-misurare.md), [6](06-ml-e-ai.md).*

**Verifiche** — La pagina della mappa che confronta le notizie di frane,
alluvioni e incendi con ciò che Limen aveva previsto prima. *Cap. [5](05-misurare.md), [10](10-partecipare.md).*

**Verità** — L'elenco di eventi veri contro cui si misura il sistema: aree
bruciate EFFIS per gli incendi, aree allagate Copernicus per le alluvioni,
il catalogo CNR per le frane, più gli eventi verificati dalla cronaca.
*Cap. [5](05-misurare.md), [10](10-partecipare.md).*

**Versione del modello** — Il numero che identifica una ricetta di calcolo.
Ogni punteggio salvato dice con quale versione è stato fatto. *Cap. [8](08-trasparenza.md).*

## Z

**Zenodo** — Un archivio pubblico e gratuito, gestito dal CERN, dove
ricercatori ed enti depositano dati e articoli con un *DOI*. *Cap. [8](08-trasparenza.md), [10](10-partecipare.md).*

**Zona di allerta** — L'area, di solito di decine di Comuni, a cui il
bollettino ufficiale dà un colore. Limen scende al chilometro quadrato.
*Cap. [1](01-il-problema.md).*
