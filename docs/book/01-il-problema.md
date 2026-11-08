# 1. Il problema e cosa fa Limen

!!! abstract "In breve"
    - L'Italia ha più di 721.000 frane censite, milioni di persone in aree che
      possono allagarsi e incendi ogni estate. Le allerte ufficiali danno un
      colore per zona, e una zona sono decine di Comuni.
    - Limen scende al chilometro quadrato: 312.550 celle, ricalcolate ogni ora,
      tre pericoli (frana, alluvione, incendio), cinque classi, una previsione a
      72 ore.
    - Non sostituisce la Protezione civile. Dice *dove dentro la zona*, *perché*
      e *cosa arriva*, accanto al bollettino ufficiale.
    - Regge su pochi principi: dati aperti, un server proprio, una formula
      scritta che decide, il machine learning che guarda e non decide,
      l'intelligenza artificiale che scrive parole e mai numeri.
    - Pubblica le misure, anche quelle andate male: l'incendio e l'alluvione
      funzionano bene, la frana ancora no.

## Un Paese fragile, misurato a grana grossa

L'Italia è uno dei Paesi europei più esposti al dissesto. L'Inventario dei
Fenomeni Franosi in Italia (IFFI), curato da ISPRA con le Regioni, censisce
**721.365 frane**[^iffi]. Il rapporto ISPRA sul dissesto idrogeologico conta
circa **6,8 milioni di persone** che vivono in aree a pericolosità idraulica
media, cioè dove un fiume può uscire con un tempo di ritorno di cento-duecento
anni[^ispra]. Ogni estate gli incendi bruciano decine di migliaia di ettari, e
il servizio europeo EFFIS ne disegna i perimetri dal satellite[^effis].

Questi rischi hanno due metà. Una è **il posto**: un versante ripido di
argille che è già franato, una piana accanto a un argine, una pineta su un
pendio esposto a sud. L'altra è **il momento**: tre giorni di pioggia su un
terreno già zuppo, un fiume che sale, una settimana di caldo secco e vento.
Il posto cambia in decenni, il momento in ore.

Il sistema ufficiale di allertamento italiano, gestito dal Dipartimento della
Protezione Civile e dai Centri Funzionali regionali, pubblica ogni giorno un
bollettino con un colore (verde, giallo, arancione, rosso) per **zona di
allerta**. Una zona è un'area omogenea per il meteo e comprende di solito
decine di Comuni. È la scelta giusta per l'obiettivo che ha, cioè attivare la
macchina dei soccorsi su un'area. Ma lascia aperta una domanda che chi abita,
lavora o amministra un territorio si fa ogni volta: *dentro la zona gialla,
dove?*

## Cosa fa Limen

Limen prova a rispondere a quella domanda. In concreto:

- **Divide l'Italia in 312.550 celle** quadrate da un chilometro di lato, in
  tutte le venti regioni.
- **Ogni ora**, per ogni cella, si fa tre domande, una per pericolo:
    - **frana**: *questo versante è fragile, e sta ricevendo troppa pioggia?*
    - **alluvione**: *l'acqua può arrivare qui, e sta arrivando?*
    - **incendio**: *se qui partisse un fuoco oggi, attecchirebbe e
      correrebbe?*
- Risponde con un **punteggio fra 0 e 1**, che diventa una di **cinque
  classi**: nessuno, basso, moderato, alto, molto alto. È la stessa scala di
  colori della Protezione civile, perché è quella che le persone conoscono.
- Calcola anche il **futuro**: con la pioggia e il meteo previsti, mostra come
  cambierà la mappa nelle prossime **72 ore**.
- Quando una cella supera una soglia, manda un **avviso** sui canali
  configurati (Telegram, email, MQTT, webhook), senza ripeterlo ogni ora per la
  stessa cella.
- Mette tutto su una **mappa pubblica**, senza registrazione, dove ogni cella
  si apre e mostra *perché* ha quel colore: quanto pesa la pioggia, quanto la
  pendenza, quanto il fiume.

Tre esempi, presi dalle misure e dagli eventi registrati nel repository,
danno l'idea di che cosa vuol dire.

**Faenza, settembre 2024.** Fra il 17 e il 19 settembre sono caduti 208,7 mm
di pioggia. La previsione emessa il giorno prima ne dava 157,1, quella di tre
giorni prima 101,3. Con la soglia originale del motore alluvione (80 mm in 72
ore) è la differenza fra un allarme e un silenzio: per questo il backtest
dell'alluvione rigioca la previsione **come fu emessa**, non la pioggia poi
caduta, che sarebbe una previsione perfetta che nessuno ha davvero[^faenza].

**Melito di Porto Salvo, 10 ottobre 2026.** La mattina la previsione dava
20 mm, il radar della Protezione civile ne aveva già misurati 152 nelle 24
ore. Un sistema che guarda solo il futuro non vede il nubifragio mentre cade.
Da allora Limen usa il massimo fra la pioggia prevista e quella già caduta più
quella prevista per le ore che restano: la cella di Melito passa da 0,00 a
0,79[^melito].

**Gli incendi in Sicilia, estati 2024 e 2025.** Il motore incendio unisce
l'indice meteo canadese FWI (*Fire Weather Index*, quanto il tempo favorisce un
incendio) con il combustibile a terra e la pendenza. A novembre 2026 i pesi
del combustibile sono stati ricalibrati sugli incendi veri: nella classe «molto
alto» la Sicilia passa dall'8,0 all'11,4 % degli incendi presi nel 2024 e dal
6,2 al 9,0 % nel 2025, senza peggiorare la classe «alto»[^sicilia]. Il
capitolo 5 racconta come si è arrivati a quel cambio, e perché un'altra
versione, più ambiziosa, è stata scartata.

## A chi serve

**A un Comune e alla sua Protezione civile.** Quando le segnalazioni arrivano
tutte insieme, l'ufficio tecnico deve decidere dove mandare la squadra.
Limen ordina comuni e celle per pericolo e mette il motivo accanto a ogni
riga: non «zona arancione», ma «pioggia molto sopra la soglia su un versante
con frane censite a poche centinaia di metri».

**A chi abita o lavora in un posto esposto.** La domanda è sempre la stessa:
«stanotte piove forte, devo preoccuparmi qui?». Il bollettino risponde per
una zona vasta; due versanti della stessa valle possono comportarsi in modo
molto diverso. Limen scende al chilometro e fa vedere quanto pesa la pioggia e
quanto il posto.

**A chi coltiva un terreno in pendio o gestisce un bosco.** Il danno arriva
raramente di sorpresa: arriva dopo settimane in cui il terreno si è caricato
d'acqua, o dopo un'estate secca che ha seccato il sottobosco. Limen tiene il
conto di quel carico giorno per giorno, con la pioggia antecedente per la
frana e la catena FWI per l'incendio.

**A chi fa ricerca o informazione.** Ogni punteggio è ricostruibile: un
indirizzo dell'API restituisce, per una cella, ogni numero che lo ha composto.
I backtest si rifanno con un comando. Ricercatori, giornalisti, studenti e
tecnici possono controllare, contestare e proporre correzioni in pubblico.

**A chi vuole replicarlo.** Il codice è libero, i dati sono aperti, il sistema
gira su un solo server. Una Regione, un consorzio di bonifica o un Paese
vicino può installarne una copia sul proprio territorio: la griglia si
costruisce dai confini delle aree caricate, non da una costante sull'Italia.

## Cosa Limen non fa

Mettiamo i limiti qui, all'inizio, perché in fondo sarebbero un modo elegante
di nasconderli.

- **Non è un'allerta ufficiale.** Nessun avviso di Limen ha valore legale. Se
  Limen e il bollettino regionale non coincidono, vale il bollettino.
- **Non è una previsione di frana.** Nessuno sa dire «domani alle 15 quel
  versante cede». Limen stima un'esposizione: quanto quel posto, oggi,
  somiglia alle condizioni in cui in Italia le frane sono davvero avvenute.
- **Non è un avviso di piena.** La portata dei fiumi viene dal sistema europeo
  GloFAS, e la sua licenza chiede di dirlo accanto ai dati e di non
  presentarli mai come un avviso di piena[^cems]. Limen rispetta entrambe le
  cose su ogni pagina che mostra l'alluvione.
- **Non vede sotto terra.** Non sa se un muro di sostegno è fatto bene, se un
  tombino è intasato, se un cantiere ha tagliato il piede di un versante.
- **Non è un chatbot.** L'intelligenza artificiale non decide nessun colore
  sulla mappa: scrive solo il breve riassunto che lo accompagna.

## I principi

Sette scelte attraversano tutto il progetto. Tornano in ogni capitolo, quindi
conviene fissarle subito.

**1. Dati aperti.** Ogni dato viene da una fonte pubblica: ISPRA, Copernicus,
la Protezione civile, INGV, NASA, il CNR, OpenStreetMap, Open-Meteo. Nessun
dato a pagamento, nessun accordo riservato. Il capitolo 3 li elenca uno per
uno, con la licenza.

**2. Un server proprio.** Limen gira in container Docker su un server dedicato
(un VPS, *virtual private server*). Niente AWS, Azure o Google Cloud. Il meteo
viene da un'istanza di Open-Meteo ospitata accanto, perché il servizio
pubblico ha un tetto di diecimila chiamate al giorno e lo sweep orario ne
chiedeva molte di più[^openmeteo]. Anche il modello linguistico può girare in
casa.

**3. Una formula scritta decide.** Il punteggio che colora la mappa viene da
un **motore deterministico**: una formula con pesi e soglie scritti in file di
configurazione leggibili (`src/limen/config/hazards/*.yaml`), uguale ogni
volta che la si rifà. È il «campione» in produzione, e non si toglie né si
indebolisce.

**4. Il machine learning guarda, non decide.** Accanto al campione gira ogni
notte un modello di apprendimento automatico, lo «sfidante». Calcola il suo
punteggio e lo salva da parte, ma non tocca la mappa né gli avvisi. Prende il
posto del campione solo se lo batte su due prove (una validazione spaziale e
il backtest sugli eventi veri) e solo per decisione di una persona. Il
capitolo 6 spiega perché.

**5. L'intelligenza artificiale scrive parole, mai numeri.** Un modello
linguistico (LLM, *large language model*) trasforma il risultato in un breve
testo per regione. Non può cambiare un punteggio: c'è un test automatico che
lo verifica a ogni modifica del codice. Gli avvisi non passano mai da un LLM.

**6. «Non misurato» non è «nessun pericolo».** Se una fonte non risponde, il
motore di un pericolo moltiplicativo darebbe zero, che sulla mappa sembra una
cella calma. È successo davvero il 29 settembre 2026: esaurita la quota
meteo, alluvione e incendio valevano zero su tutta Italia. Da allora ogni
punteggio dice se il dato è arrivato, e una cella non misurata si disegna in
grigio, come una cella non valutata[^nonmisurato].

**7. Misurare prima di cambiare.** Nessun peso, nessuna soglia cambia senza una
misura sugli eventi veri, con il **tasso di base** accanto (quante volte il
sistema avrebbe dato l'allarme comunque). Un sistema che dice «pericolo» ogni
giorno d'estate prende tutti gli incendi e non serve a niente. Il capitolo 5 è
dedicato a questo.

## A che punto siamo

Limen copre tutta Italia per tutti e tre i pericoli. Il pilota su cui è stato
validato per primo è Puglia e Basilicata. Ecco le misure principali, con la
loro fonte nel repository.

| Pericolo | Misura | Risultato | Contro |
|---|---|---|---|
| Incendio | Basilicata 2025, perimetri EFFIS | **79 %** degli incendi in classe alta | 43 % dei giorni in classe alta comunque |
| Incendio | Basilicata 2024 | **100 %** | 28 % |
| Alluvione | Emilia-Romagna, previsione come fu emessa, aree allagate Copernicus EMS | **77 %** delle celle allagate prese, con circa 50 ore di anticipo | 7,3 % di celle-giorno in allerta; il 79 % delle allerte non trova un allagamento osservato |
| Frana | Liguria, novembre 2019, 131 frane datate | **11 %** delle frane in classe alta | 0,17 % delle celle-ora in allerta |
| Frana | Marche, maggio 2014, 172 frane | **nessuna** in classe alta | |
| Frana, ML | sfidante, 37.000 esempi, validazione spaziale | AUC-PR **0,60** | 0,28 del motore deterministico |

Fonti: README del progetto, sezione *Does it work?*, e i commenti in testa a
[`flood.yaml`](https://github.com/agent-engineering-studio/limen/blob/main/src/limen/config/hazards/flood.yaml).

Come si leggono:

- **Incendio e alluvione funzionano.** Nella classe alta finiscono molti più
  eventi veri di quanti ne finirebbero a caso, con ore o giorni di anticipo.
- **Nell'alluvione i falsi allarmi sono ancora tanti.** Dentro l'area di
  un'alluvione piove su tutti allo stesso modo: decide l'incanalamento
  dell'acqua, non la pioggia locale, e oggi Limen non ha un buon segnale per
  quello.
- **La frana è il punto debole, e lo diciamo.** Il punteggio ordina bene le
  celle dentro una regione, ma la pioggia letta dalle rianalisi meteo non basta
  a far scattare la classe alta. È il prossimo lavoro grosso, tracciato in
  pubblico nella issue #122.
- **Il modello ML della frana batte il motore deterministico** sulla
  validazione spaziale. Resta comunque in ombra finché non lo batte anche sul
  backtest: due prove, non una.

!!! note "Per chi sviluppa"
    - I tre motori: `src/limen/core/scoring/` (`engine.py` per la frana,
      `flood/`, `wildfire/`), con la configurazione in
      `src/limen/config/hazards/{landslide,flood,wildfire}.yaml`.
    - Il flag «misurato» per pericolo: `measured()` sui breakdown in
      `src/limen/core/models/`.
    - I backtest: `limen backtest`, `limen backtest-flood`,
      `limen backtest-wildfire` (`src/limen/cli/`).
    - Le regole che il codice non può violare sono nella tabella *Locked
      invariants* di
      [`CLAUDE.md`](https://github.com/agent-engineering-studio/limen/blob/main/CLAUDE.md).

## Per approfondire

- *Limen in una pagina*, la scheda divulgativa da cui parte questo capitolo:
  [`docs/divulgazione/01-limen-in-una-pagina.md`](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/01-limen-in-una-pagina.md).
- ISPRA, *Dissesto idrogeologico in Italia: pericolosità e indicatori di
  rischio*, edizione 2021:
  <https://www.isprambiente.gov.it/it/pubblicazioni/rapporti/dissesto-idrogeologico-in-italia-pericolosita-e-indicatori-di-rischio-edizione-2021>.
- Piattaforma IdroGEO di ISPRA (IFFI e mosaici PAI): <https://idrogeo.isprambiente.it>.
- EFFIS, il sistema europeo d'informazione sugli incendi boschivi:
  <https://forest-fire.emergency.copernicus.eu>.
- Copernicus Emergency Management Service, Rapid Mapping:
  <https://mapping.emergency.copernicus.eu>.
- GloFAS, il sistema globale di allerta per le piene: <https://www.globalfloods.eu>.
- Radar meteo della Protezione civile: <https://radar.protezionecivile.it>.

[^iffi]: Catalogo dei dati di Limen,
    [`src/limen/config/dati.yaml`](https://github.com/agent-engineering-studio/limen/blob/main/src/limen/config/dati.yaml),
    voce `iffi`. Fonte: ISPRA IdroGEO, licenza CC BY-SA 4.0.
[^ispra]: Il numero è riportato nel README del progetto; la fonte è il rapporto
    ISPRA sul dissesto idrogeologico, edizione 2021 (link in *Per
    approfondire*).
[^effis]: Limen legge i perimetri EFFIS dal servizio pubblico, senza
    credenziali; li usa come verità per misurare il motore incendio.
[^faenza]: Docstring di
    [`src/limen/cli/backtest_flood.py`](https://github.com/agent-engineering-studio/limen/blob/main/src/limen/cli/backtest_flood.py).
[^melito]: Commento al blocco `pluvial.observed` di
    [`flood.yaml`](https://github.com/agent-engineering-studio/limen/blob/main/src/limen/config/hazards/flood.yaml)
    (issue #199).
[^sicilia]: Backtest ufficiale `backtest-wildfire` 2024-25, pubblicato nella
    issue #295 e adottato con `wildfire-v1.1.0` (PR #462).
[^cems]: Licenza CEMS-Floods; l'attribuzione è in
    `frontend/src/lib/attribuzioni.ts`.
[^openmeteo]: Issue #142 e la riga «Un'istanza Open-Meteo propria» di
    `CLAUDE.md`.
[^nonmisurato]: Issue #143 e la riga «"Non misurato" non è "nessun pericolo"»
    di `CLAUDE.md`.
