# Appendice D. Registro dei gap

Un **gap** è una distanza fra quello che Limen fa oggi e quello che dovrebbe
fare per essere uno strumento affidabile di protezione del territorio: un
dato che manca, una prova non fatta, un documento sbagliato. Ogni capitolo si
chiude con i suoi; qui stanno tutti insieme, divisi per capitolo.

Un gap si chiude in tre passi:

1. **la issue**: una scheda di lavoro pubblica sulla piattaforma GitHub, dove
   si scrive il dettaglio e si discute (la colonna «Issue» porta lì);
2. **la correzione**, provata prima con una misura sugli eventi veri, come
   dice il [capitolo 5](05-misurare.md): un gap si chiude con un numero, non
   con una promessa;
3. **l'aggiornamento del libro**: la riga resta qui, con la correzione che
   l'ha chiusa, finché il capitolo non viene riscritto.

La colonna **«Proposta di open data»** dice, quando c'è, quale dato pubblico
colmerebbe il gap. È la parte in cui enti, ricercatori e cittadini possono
fare la differenza anche senza scrivere una riga di programma: pubblicando o
aggiornando quel dato, con una licenza aperta. Un trattino vuol dire che quel
gap si chiude dentro Limen.

## Capitolo 1. [Il problema e cosa fa Limen](01-il-problema.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 1 | La classe alta della frana si raggiunge quasi mai: la pioggia, come Limen la legge oggi, raramente basta. | piogge orarie dei pluviometri regionali pubblicate con continuità (es. [Dext3r, ARPAE Emilia-Romagna](https://simc.arpae.it/dext3r/); condizioni d'uso da verificare regione per regione) | [#345](https://github.com/agent-engineering-studio/limen/issues/345) |
| 1 | Pochi eventi veri, con data e luogo, per misurare l'affidabilità. | aggiornamento dopo il 2021 di [e-ITALICA, CNR-IRPI](https://doi.org/10.5281/zenodo.14204473) (CC BY 4.0); registri degli eventi di Comuni e Regioni con data, ora e luogo | [#345](https://github.com/agent-engineering-studio/limen/issues/345) |
| 1 | Troppi falsi allarmi per l'alluvione: Limen non sa abbastanza dove va l'acqua. | c'è già: il [modello del terreno a 5 m del CNR-IRPI](https://zenodo.org/records/18921767) (CC BY 4.0), da cui calcolare quanto ogni cella sta sopra il corso d'acqua più vicino | [#474](https://github.com/agent-engineering-studio/limen/issues/474) |

## Capitolo 2. [I mattoni: le librerie](02-le-librerie.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 2 | La piena ordinaria dei fiumi viene da due archivi che non danno gli stessi numeri. | — | [#448](https://github.com/agent-engineering-studio/limen/issues/448) |
| 2 | Il terreno che si muove entra solo nel modello in prova, e solo come velocità media. | accelerazione e stagionalità già pubblicate da [EGMS](https://egms.land.copernicus.eu) (Copernicus, gratuito) | [#380](https://github.com/agent-engineering-studio/limen/issues/380) |
| 2 | Nessun controllo automatico segnala versioni nuove o correzioni di sicurezza delle librerie. | — | [#465](https://github.com/agent-engineering-studio/limen/issues/465) |

## Capitolo 3. [I dati](03-i-dati.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 3 | Le aree allagabili risultano «gonfiate» (Calabria, Valle d'Aosta) perché vale l'area più grave che tocca la cella. Correzione col terreno pronta, spenta in attesa di una verifica sulle fiumare. | mappe dell'acqua osservata dal satellite, [Copernicus GFM](https://global-flood.emergency.copernicus.eu/general-information/data-and-services) (licenza da verificare) | [#469](https://github.com/agent-engineering-studio/limen/issues/469) |
| 3 | ~~La vicinanza a centri abitati e strade non è mai stata ricalcolata per tutta Italia.~~ Chiuso: si ricalcola a ogni caricamento di CORINE. | — | [#473](https://github.com/agent-engineering-studio/limen/issues/473) |
| 3 | Gli incendi passati visti dal satellite non sono nel catalogo dei dati. | l'archivio storico [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov) 2000-2024, libero con citazione | [#472](https://github.com/agent-engineering-studio/limen/issues/472) |
| 3 | ~~La tabella delle rocce non riconosce il 30 % delle celle.~~ Chiuso: pesi in `landslide.yaml`, tutte le classi per intero, il neutro motivato da una misura. | le carte geologiche CARG 1:50.000 di ISPRA (copertura e licenza da verificare) | [#471](https://github.com/agent-engineering-studio/limen/issues/471) |
| 3 | La licenza della carta delle rocce è ambigua. | — | [#495](https://github.com/agent-engineering-studio/limen/issues/495), [#406](https://github.com/agent-engineering-studio/limen/issues/406) |
| 3 | Manca la chiave per i dati ufficiali dei fiumi: il confronto fra le due serie della piena ordinaria è fermo. | — | [#448](https://github.com/agent-engineering-studio/limen/issues/448) |
| 3 | ~~Bosco e città compaiono come codici, non come nomi.~~ Chiuso: il riquadro della cella mostra il nome della classe CORINE, in italiano e in inglese. | la legenda ufficiale CORINE in italiano (Copernicus, ISPRA) | [#470](https://github.com/agent-engineering-studio/limen/issues/470) |
| 3 | **Corretto.** Le pagine sulle fonti non erano allineate al catalogo (licenze e fonti vecchie); ora un controllo automatico le confronta. | — | [#491](https://github.com/agent-engineering-studio/limen/issues/491) |
| 3 | ~~Il controllo di prontezza conta anche gli zeri: una regione senza frane sembra a posto.~~ Chiuso: le regioni quasi tutte a zero sono «da verificare». | — | [#467](https://github.com/agent-engineering-studio/limen/issues/467) |
| 3 | Popolazione, edifici, umidità dalla forma del versante e distanza dalle faglie hanno un posto ma nessun calcolo. | griglia europea della popolazione a 1 km ([Eurostat GEOSTAT](https://ec.europa.eu/eurostat/web/gisco/geodata/population-distribution/geostat)) o [GHSL del JRC](https://human-settlement.emergency.copernicus.eu/), licenze da verificare | [#466](https://github.com/agent-engineering-studio/limen/issues/466) |
| 3 | È uscita una versione nuova del modello del terreno: va misurato quanto cambiano le pendenze. | [HR-DTM 5 m del CNR-IRPI](https://zenodo.org/records/18921767), versione 1.3 | [#468](https://github.com/agent-engineering-studio/limen/issues/468) |

## Capitolo 4. [Dal dato al punteggio](04-i-motori.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 4 | La frana arriva di rado ad «alto»: al motore arriva circa il 60 % della pioggia dei pluviometri. | frane datate dei servizi geologici regionali, nello stesso formato di [e-ITALICA](https://doi.org/10.5281/zenodo.14204473) (CC BY 4.0) | [#345](https://github.com/agent-engineering-studio/limen/issues/345) |
| 4 | Dopo un terremoto forte la soglia di pioggia non scende. | — | [#441](https://github.com/agent-engineering-studio/limen/issues/441) |
| 4 | L'alluvione non sa dove l'acqua si incanala. | il reticolo idrografico europeo [EU-Hydro](https://land.copernicus.eu/en/products/eu-hydro) di Copernicus, con un modello del terreno | [#474](https://github.com/agent-engineering-studio/limen/issues/474) |
| 4 | La «piena ordinaria» del fiume viene da due fonti diverse. | — | [#448](https://github.com/agent-engineering-studio/limen/issues/448) |
| 4 | Pochi dati sui nubifragi in città. | un catalogo aperto e datato degli allagamenti urbani (Comuni, vigili del fuoco), oggi non disponibile a livello nazionale | [#475](https://github.com/agent-engineering-studio/limen/issues/475) |
| 4 | L'incendio al Nord e d'inverno è poco misurato. | — | [#476](https://github.com/agent-engineering-studio/limen/issues/476) |
| 4 | Una soglia unica, mai misurata, per gli avvisi sotto «alto». | — | [#477](https://github.com/agent-engineering-studio/limen/issues/477) |
| 4 | ~~La documentazione tecnica del motore frana non è aggiornata.~~ Chiuso: `scoring-model.md` e `warning-logic.md` seguono `landslide.yaml`, e un test confronta i pesi di S scritti nel documento con quelli del file. | — | [#493](https://github.com/agent-engineering-studio/limen/issues/493) |

## Capitolo 5. [Misurare prima di cambiare](05-misurare.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 5 | La frana non supera la prova: 49 % dei comuni colpiti con il 10 % di carico, contro il 90 %. | frane datate dai servizi geologici regionali e dai Comuni, nel formato di [e-ITALICA](https://doi.org/10.5281/zenodo.14204473) (CC BY 4.0) | [#345](https://github.com/agent-engineering-studio/limen/issues/345) |
| 5 | Pochi eventi verificati dalla cronaca: con otto non si misura niente. | segnalazioni di enti e cittadini | [#345](https://github.com/agent-engineering-studio/limen/issues/345) |
| 5 | Alluvione: troppi falsi allarmi (78 % in Emilia-Romagna, obiettivo 30 %). | vedi capitolo 4 | [#474](https://github.com/agent-engineering-studio/limen/issues/474) |
| 5 | Il ramo dei fiumi non si misura nei backtest quando finisce la quota del servizio delle portate. | — | [#478](https://github.com/agent-engineering-studio/limen/issues/478) |
| 5 | I report delle prove non sono nel repository. | — | [#481](https://github.com/agent-engineering-studio/limen/issues/481) |
| 5 | Le misure veloci sui dati nuovi non sono riproducibili. | — | [#480](https://github.com/agent-engineering-studio/limen/issues/480) |
| 5 | L'incendio è misurato su poche regioni e solo d'estate. | — | [#479](https://github.com/agent-engineering-studio/limen/issues/479) |

## Capitolo 6. [Machine learning e AI](06-ml-e-ai.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 6 | L'esame di promozione del modello che impara non si può superare. | — | [#483](https://github.com/agent-engineering-studio/limen/issues/483) |
| 6 | Gli esempi e i modelli addestrati non hanno fatto il trasloco sulla macchina attuale. | — | [#486](https://github.com/agent-engineering-studio/limen/issues/486) |
| 6 | Il modello incendio è rimasto ai vecchi pesi del combustibile. | — | [#485](https://github.com/agent-engineering-studio/limen/issues/485) |
| 6 | Agli esempi del modello mancano i dati più nuovi (terremoti, radar, movimento del suolo). | [EGMS](https://egms.land.copernicus.eu) (Copernicus, gratuito) | [#380](https://github.com/agent-engineering-studio/limen/issues/380), [#482](https://github.com/agent-engineering-studio/limen/issues/482) |
| 6 | Le frane con data sono poche e incomplete. | [e-ITALICA](https://doi.org/10.5281/zenodo.14204473) aggiornato oltre il 2021; registri degli interventi di Comuni e Province | [#500](https://github.com/agent-engineering-studio/limen/issues/500) |
| 6 | Il piccolo modello sulla pioggia non si può addestrare qui e non è collegato a niente. | — | [#487](https://github.com/agent-engineering-studio/limen/issues/487) |
| 6 | Oggi nessun testo è scritto dall'AI: sono tutti testi di riserva. | — | [#488](https://github.com/agent-engineering-studio/limen/issues/488) |
| 6 | Il numero sulla mappa non dice quanto è sicuro. | — | [#484](https://github.com/agent-engineering-studio/limen/issues/484) |

## Capitolo 7. [Come gira](07-come-gira.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 7 | La copia di sicurezza resta sullo stesso computer. | — | [#490](https://github.com/agent-engineering-studio/limen/issues/490) |
| 7 | Il ripristino non è mai stato provato su una macchina pulita. | — | [#307](https://github.com/agent-engineering-studio/limen/issues/307) |
| 7 | Un solo ufficio calcoli: ogni riavvio interrompe il lavoro. | — | [#308](https://github.com/agent-engineering-studio/limen/issues/308) |
| 7 | Gli avvisi di previsione slittano a ogni riavvio. *Corretto: ora partono a orari fissi.* | — | [#489](https://github.com/agent-engineering-studio/limen/issues/489) |
| 7 | Il pacchetto rapido non è pubblicato né proposto dalla pagina di installazione. | pubblicarlo su [Zenodo](https://zenodo.org) con un identificativo permanente | [#406](https://github.com/agent-engineering-studio/limen/issues/406) |
| 7 | La macchina di oggi non è un server. | — | [#308](https://github.com/agent-engineering-studio/limen/issues/308) |
| 7 | ~~Alcuni documenti tecnici descrivono il sistema di prima.~~ Chiuso: la guida operativa elenca i lavori a orario come sono registrati, e la vista della mappa è descritta come vista normale. | — | [#493](https://github.com/agent-engineering-studio/limen/issues/493) |

## Capitolo 8. [Trasparenza, licenze, costi](08-trasparenza.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 8 | **Corretto.** Alcune attribuzioni sulla mappa erano sbagliate o mancavano, compresa la frase di non responsabilità di ECMWF. | — | [#491](https://github.com/agent-engineering-studio/limen/issues/491) |
| 8 | La licenza dei tipi di roccia è ambigua. | — | [#495](https://github.com/agent-engineering-studio/limen/issues/495), [#406](https://github.com/agent-engineering-studio/limen/issues/406) |
| 8 | Il pacchetto rapido non è ancora provato su un server pulito. | — | [#406](https://github.com/agent-engineering-studio/limen/issues/406), [#307](https://github.com/agent-engineering-studio/limen/issues/307) |
| 8 | Le misure non sono sempre archiviate con i loro ingredienti. | depositare ogni rapporto di misura su [Zenodo](https://zenodo.org), con un DOI | [#481](https://github.com/agent-engineering-studio/limen/issues/481) |
| 8 | ~~Alcuni documenti hanno informazioni superate (licenza, cloud, tetto di spesa).~~ Chiuso: EUPL 1.2 con il patto per chi contribuisce, tetto unico di 10 $ al mese, flusso di pubblicazione su Azure tolto. | — | [#493](https://github.com/agent-engineering-studio/limen/issues/493) |
| 8 | Il costo di oggi non è misurato. | — | [#492](https://github.com/agent-engineering-studio/limen/issues/492) |
| 8 | Una porta del monitoraggio era aperta verso l'esterno. **Corretto**: le porte ora si aprono solo verso il server, e una prova automatica le controlla tutte. | — | [#496](https://github.com/agent-engineering-studio/limen/issues/496) |
| 8 | Manca un'informativa privacy unica e pubblica. | — | [#494](https://github.com/agent-engineering-studio/limen/issues/494) |

## Capitolo 9. [Cosa manca](09-cosa-manca.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 9 | La pioggia che arriva al motore della frana è troppo poca. | pluviometri dei Centri Funzionali in tempo reale, con licenza aperta e formato comune (SensorThings o CSV con metadati) | [#505](https://github.com/agent-engineering-studio/limen/issues/505) |
| 9 | Le soglie di pioggia regionali non sono leggibili da un programma. | le soglie dei Centri Funzionali come tabella aperta (durata, intensità, area) | [#506](https://github.com/agent-engineering-studio/limen/issues/506) |
| 9 | Il catalogo delle frane datate si ferma al 2021. | inventari regionali delle frane recenti, con data e posizione | [#500](https://github.com/agent-engineering-studio/limen/issues/500) |
| 9 | La carta delle rocce è troppo grossolana. | carte geologiche CARG 1:50.000 di ISPRA (copertura e licenza da verificare) | [#497](https://github.com/agent-engineering-studio/limen/issues/497) |
| 9 | Gli incendi piccoli sfuggono ai satelliti. | catasti comunali delle aree percorse dal fuoco (legge 353/2000) in un formato comune | [#498](https://github.com/agent-engineering-studio/limen/issues/498) |
| 9 | I fiumi minori non hanno misure. | idrometri regionali con la serie storica di ogni stazione; idrometri dei cittadini | [#501](https://github.com/agent-engineering-studio/limen/issues/501), [#259](https://github.com/agent-engineering-studio/limen/issues/259) |
| 9 | Il movimento del suolo è usato solo in parte. | accelerazione e stagionalità da [EGMS](https://egms.land.copernicus.eu) | [#380](https://github.com/agent-engineering-studio/limen/issues/380) |
| 9 | L'umidità del suolo a 1 km non è mai stata provata. | umidità del suolo da radar Sentinel-1, [Copernicus Land](https://land.copernicus.eu/en/products/soil-moisture) (licenza da verificare) | [#507](https://github.com/agent-engineering-studio/limen/issues/507) |
| 9 | Le reti di pluviometri dei cittadini non sono acquisibili. | [MeteoNetwork](https://www.meteonetwork.it) (CC BY 4.0), se concede l'accesso per regione | [#249](https://github.com/agent-engineering-studio/limen/issues/249), [#250](https://github.com/agent-engineering-studio/limen/issues/250) |
| 9 | I periodi di ritorno delle piene europee (EFAS) non sono usati. | [EFAS](https://www.efas.eu), Copernicus (licenza CEMS); soglie di piena GloFAS aperte | [#522](https://github.com/agent-engineering-studio/limen/issues/522) |
| 9 | Limen non esporta i suoi avvisi in un formato standard. | — | [#499](https://github.com/agent-engineering-studio/limen/issues/499) |
| 9 | Le interfacce di Limen non seguono gli standard OGC moderni. | — | [#503](https://github.com/agent-engineering-studio/limen/issues/503) |
| 9 | Il pacchetto dei dati non è nel catalogo nazionale. | — | [#504](https://github.com/agent-engineering-studio/limen/issues/504) |
| 9 | Non c'è un modo guidato per proporre un dato. | — | [#502](https://github.com/agent-engineering-studio/limen/issues/502) |

## Capitolo 10. [Partecipare](10-partecipare.md)

| Capitolo | Gap | Proposta di open data | Issue |
|---|---|---|---|
| 10 | Manca una guida per chi non sviluppa. | — | [#511](https://github.com/agent-engineering-studio/limen/issues/511) |
| 10 | Manca un canale di contatto pubblico. | — | [#508](https://github.com/agent-engineering-studio/limen/issues/508) |
| 10 | Nessun primo lavoro facile è segnalato. | — | [#510](https://github.com/agent-engineering-studio/limen/issues/510) |
| 10 | Un solo curatore. | — | [#514](https://github.com/agent-engineering-studio/limen/issues/514) |
| 10 | La roadmap scritta nel repository è vecchia. | — | [#513](https://github.com/agent-engineering-studio/limen/issues/513) |
| 10 | Non c'è un modo semplice per un ente di consegnare i propri eventi. | eventi datati di Regioni e Centri Funzionali come tabella aperta CC BY 4.0, sul modello di [e-ITALICA](https://doi.org/10.5281/zenodo.14204473) | [#509](https://github.com/agent-engineering-studio/limen/issues/509) |
| 10 | Manca un piano di finanziamento scritto. | — | [#512](https://github.com/agent-engineering-studio/limen/issues/512) |

??? note "Per chi sviluppa: come si aggiorna questo registro"
    - Una riga per gap, nell'ordine dei capitoli. Il testo è lo stesso
      riassunto della sezione «Gap e come chiuderli» del capitolo, in una
      frase.
    - Una issue nuova si apre con il dettaglio tecnico (file, numeri, come
      misurare, criteri di accettazione) e la riga «Aggiornare il libro»;
      il numero va qui e nel capitolo.
    - Quando un gap si chiude: la riga resta, con il numero della PR e la
      misura che l'ha chiuso, finché il capitolo non viene riscritto.
