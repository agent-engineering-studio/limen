# Dati personali

**Limen non ha account, non usa cookie e non traccia chi guarda la mappa.**
Per leggere la mappa, le regioni, i comuni, le verifiche e le guide non serve
dare niente. Dati personali entrano solo in tre casi, tutti per scelta di chi
scrive: un contributo da esperto, la registrazione di un sensore, la
ricezione degli avvisi. Questa pagina dice quali dati, perché, per quanto
tempo e come cancellarli.

> **Chi installa Limen** diventa titolare dei dati della propria
> installazione, in particolare dei destinatari degli avvisi che configura.
> Questa pagina descrive l'installazione pubblica del progetto: chi ne
> gestisce un'altra deve adattare titolare, contatto e tempi di
> conservazione, e pubblicare la propria versione.

## Chi è il titolare

Per l'installazione pubblica di Limen il titolare del trattamento è il
curatore del progetto Limen. Per ogni richiesta sui dati personali:
**gzileni@agentengineering.it**.

## Che cosa entra, perché, per quanto

| Quando | Quali dati | Perché | Base giuridica | Per quanto |
|---|---|---|---|---|
| Visiti il sito | l'indirizzo IP, nel registro del server web | sicurezza e diagnosi dei guasti | legittimo interesse (art. 6.1.f GDPR) | 14 giorni, poi il registro è cancellato |
| Mandi un contributo da esperto | nome o profilo, email, ente (facoltativo), testo | ricontattarti su quel contributo | consenso, dato con la casella del modulo (art. 6.1.a) | non è salvato da Limen: resta solo nella mail ricevuta dal curatore, cancellata dopo 12 mesi |
| Mandi un contributo da esperto | l'indirizzo IP | limitare gli invii, contro lo spam | legittimo interesse (art. 6.1.f) | solo in memoria, un'ora; mai scritto su disco |
| Registri un sensore | email, posizione esatta del sensore, foto e note | rispondere alla richiesta, legare il sensore a una cella, cancellare tutto quando lo chiedi | esecuzione della tua richiesta (art. 6.1.b) | email e posizione finché il sensore è registrato; foto e note solo nella mail al curatore, cancellata dopo 12 mesi |
| Ricevi gli avvisi | indirizzo email o chat Telegram | mandarti gli avvisi | li decide l'ente che gestisce l'installazione | finché l'ente non ti toglie dall'elenco |

**Che cosa non entra mai.** Nessun dato personale va ai modelli di
intelligenza artificiale: i testi spiegati delle regioni sono scritti a partire
da numeri e nomi di luoghi. Nessun dato personale è pubblicato sulla mappa,
nelle API o negli strumenti per agenti. Le misure dei sensori sono pubblicate
con licenza CC BY 4.0 e non contengono dati personali: sulla mappa la
posizione di un sensore è arrotondata a circa un chilometro.

## Chi altro vede i dati

- **Il fornitore della posta** dell'installazione, che consegna le mail dei
  contributi, delle registrazioni e degli avvisi.
- **Telegram**, per chi riceve gli avvisi in una chat.
- **Mentre guardi la mappa**, il tuo browser scarica direttamente da altri
  server lo sfondo cartografico (OpenStreetMap,
  [informativa](https://osmfoundation.org/wiki/Privacy_Policy)) e i caratteri
  del testo (Google Fonts,
  [informativa](https://policies.google.com/privacy)). Quei server vedono il
  tuo indirizzo IP come per qualunque sito che li usa; Limen non riceve
  niente da loro.

Nessun dato è venduto o ceduto ad altri, né trasferito fuori dall'Unione
europea da Limen.

## I tuoi diritti

Puoi chiedere in qualsiasi momento di vedere, correggere o cancellare i tuoi
dati, di limitarne l'uso o di opporti, e puoi ritirare il consenso dato per un
contributo. Scrivi a **gzileni@agentengineering.it**: rispondiamo entro un
mese. Per un sensore basta rispondere alla mail di Limen: la mail viene
cancellata, i dispositivi sono revocati e la posizione torna al centro della
cella di un chilometro; le misure già raccolte restano, senza più nulla che le
colleghi a te.

Se ritieni che i tuoi dati siano trattati in modo non corretto, puoi
rivolgerti al [Garante per la protezione dei dati
personali](https://www.garanteprivacy.it).

## Per chi sviluppa o installa

- **Contributi**: `src/limen/core/contributi.py`. Il limite per IP sta in un
  dizionario in memoria con una finestra di 3600 s (`Limitatore`); i log
  `contributi.*` non contengono né email né IP.
- **Sensori**: tabelle `sensori_registranti` (email) e `sensori_richieste`
  (posizione, migrazione 077); i log `sensori.registrazione.*` portano solo
  identificativi. Cancellazione: `limen sensore cancella-registrante <email>`.
- **Registri**: con il proxy Caddy del compose non c'è un registro degli
  accessi; con nginx sull'host (`infra/nginx/limen.conf.template`) il registro
  `limen.access.log` ruota con il logrotate del pacchetto (14 giorni su
  Debian e Ubuntu). I log dei container sono limitati a 3 file da 10 MB per
  servizio.
- **Destinatari degli avvisi**: `NOTIFICATIONS__EMAIL__RECIPIENTS` e
  `NOTIFICATIONS__TELEGRAM__CHAT_ID` nel `.env` di chi installa; non escono
  dal server.
