# Sensori e MQTT

> ⚠️ **Lavori in corso — arriva nelle prossime release.** La rete dei
> sensori non accetta ancora misure: il broker esiste, ma protocollo,
> registrazione e kit sono in sviluppo e possono cambiare. Non costruire né
> installare un sensore pensando che Limen lo legga già.

**Limen usa MQTT in due direzioni opposte, con due broker separati.** Il
broker delle allerte fa uscire gli avvisi verso i sistemi di chi li riceve.
Il broker dei sensori fa entrare le misure dal territorio: pluviometri,
idrometri, sonde di umidità del suolo, costruiti anche da cittadini, scuole e
associazioni con un ESP32 o un Raspberry Pi. I due broker non sono mai lo
stesso processo, perché hanno esigenze di sicurezza opposte.

La rete dei sensori dei cittadini è **in costruzione** (epic
[#247](https://github.com/agent-engineering-studio/limen/issues/247)). Questa
pagina descrive cosa esiste già, cosa sta arrivando e, soprattutto, quali
regole valgono per chi installa un sensore.

## Due broker, due mestieri

| | Broker delle allerte | Broker dei sensori |
|---|---|---|
| Container | `limen-mosquitto` | `limen-mosquitto-sensori` |
| Direzione | Limen → fuori | fuori → Limen |
| Chi pubblica | solo Limen | ogni dispositivo, solo sul proprio topic |
| Autenticazione | nessuna: è raggiungibile solo dal server | certificato X.509 per dispositivo (mTLS) |
| Esposizione | mai, solo loopback | porta 8883, tramite nginx |
| Topic | `limen/alerts` | `limen/v2/<id>/obs`, `limen/v2/<id>/status` |

Tenerli separati non è una precauzione formale. Il broker delle allerte
accetta connessioni anonime perché nessuno, fuori dal server, può
raggiungerlo; quello dei sensori sta su Internet e non accetta nessuno senza
un certificato. Unirli significherebbe indebolire il primo o rompere il
secondo.

## Il broker delle allerte

**Quando un giro orario trova celle sopra soglia, Limen pubblica un avviso
sul topic `limen/alerts`.** È uno dei quattro canali push, insieme a
Telegram, email e webhook. Si accende elencando `mqtt` in
`NOTIFICATIONS__ENABLED_CHANNELS` e configurando le variabili
`NOTIFICATIONS__MQTT__*` (host, porta, topic, QoS, eventuali credenziali e
TLS).

Ogni avviso è un messaggio JSON, pubblicato con QoS 1 aprendo una
connessione, pubblicando e chiudendo: gli avvisi sono rari, e una sessione
sempre aperta non vale la sua complessità. Il contenuto:

| Campo | Cosa contiene |
|---|---|
| `aoi_id`, `hazard_type` | l'area e il pericolo (frana, alluvione, incendio) |
| `max_level`, `max_score` | la classe e il punteggio più alti fra le celle allertate |
| `cells` | le celle: identificativo, punteggio, classe, priorità, comune, link alla mappa |
| `aggregates` | il riepilogo per comune |
| `summary_it` | il testo italiano dell'avviso |
| `cascade` | le cascate fra pericoli attive, se ce ne sono |
| `map_url`, `pipeline_version`, `dispatched_at` | link, versione, ora d'invio |

Il testo `summary_it` è costruito in modo deterministico dai numeri del
motore: **nel percorso delle allerte non c'è nessun modello linguistico**,
quindi un avviso non può contenere una cifra inventata. Gli avvisi passano
dalla stessa deduplicazione e dagli stessi limiti degli altri canali: una
cella già avvisata nella finestra non viene ripetuta.

Il broker gira sul server di Limen e ascolta solo sul loopback. Per ricevere
gli avvisi in un altro sistema si usa un bridge MQTT dal proprio broker,
oppure il canale webhook, descritto in
[Integrazioni](#/integrazioni/notifiche-push).

## Il broker dei sensori

**Un Mosquitto dedicato, raggiungibile da Internet sulla porta 8883, che
accetta solo dispositivi con un certificato firmato dalla CA dei sensori di
Limen.** È ospitato sullo stesso server di Limen, non su un cloud: costa
quasi nulla e parla MQTT standard, quindi un dispositivo non deve cambiare
nulla se un giorno il broker si sposterà.

Come è difeso:

- **mutua autenticazione TLS**: il dispositivo verifica il server e il server
verifica il dispositivo. Un client senza certificato non completa nemmeno
la connessione;
- **l'identità è il certificato**: il nome del dispositivo viene dal campo
CN del suo certificato, mai da un campo del messaggio, quindi copiare l'id
di un altro non serve a niente;
- **ognuno scrive solo sul proprio topic**: un dispositivo pubblica su
`limen/v2/<il suo id>/…` e non può leggere niente, nemmeno i propri dati;
- **revoca immediata**: un dispositivo compromesso, rubato o guasto si revoca
da solo, senza toccare gli altri;
- **porta dietro nginx**: il container ascolta solo sul server; la porta
pubblica è di nginx, che inoltra il traffico cifrato senza decifrarlo e
limita il numero di connessioni per indirizzo.

Prima di ogni messa in servizio un controllo automatico verifica che il
broker rifiuti davvero quello che deve rifiutare:

| Prova | Esito atteso |
|---|---|
| client senza certificato | rifiutato |
| certificato firmato da un'altra CA | rifiutato |
| dispositivo valido sul proprio topic | consegnato a Limen |
| dispositivo valido sul topic di un altro | scartato |
| dispositivo revocato | rifiutato |
| lista di revoca vicina alla scadenza | segnalata |

## Il protocollo v2

**Pochi campi, unità fisse, l'identità nel certificato.** Limen legge già
messaggi in questo formato ([#252](https://github.com/agent-engineering-studio/limen/issues/252)),
ma solo da dispositivi registrati, e la registrazione non è ancora aperta.

Due topic per dispositivo:

```
limen/v2/<id>/obs       le misure
limen/v2/<id>/status    online alla connessione, offline come last will
```

Il dispositivo **non dichiara dove si trova**: la posizione, la regione e la
cella della griglia le registra Limen quando approva il dispositivo. Un dato
in meno da verificare, e un sensore spostato si nota.

Il messaggio segue SenML (RFC 8428), il formato standard per le misure dei
sensori, in JSON. Il CBOR, dove ogni byte conta, arriverà con LoRaWAN
([#266](https://github.com/agent-engineering-studio/limen/issues/266)).

```json
[
  {"bn": "pluvio-matera-01/", "bt": 1792065600, "n": "rainfall", "u": "mm", "v": 0.4},
  {"n": "seq", "v": 18342}
]
```

Le grandezze e le loro unità:

| Grandezza | Campo `u` | Per quale pericolo |
|---|---|---|
| `rainfall` | `mm` | frana, alluvione |
| `soil_moisture` | `m3/m3` | frana |
| `water_level` | `m` | alluvione (in arrivo) |
| `air_temperature`, `relative_humidity`, `wind_speed` | °C, %, km/h | incendio (in arrivo) |

L'unità si scrive esattamente così: Limen non converte, e un messaggio con
un'unità diversa si scarta. Una grandezza che Limen non conosce ancora si
ignora senza scartare le altre.

Tre regole valgono per ogni messaggio. Il tempo è sempre UTC, preso da NTP:
un messaggio dal futuro si scarta. Al massimo una dozzina di messaggi al
minuto: oltre si scartano, e un dispositivo che insiste va in quarantena
finché qualcuno non lo controlla. Il numero di sequenza cresce sempre, anche
dopo un riavvio, quindi va salvato nella memoria del dispositivo: un numero
già visto è un messaggio ripetuto e si scarta. Un dispositivo che resta senza rete
conserva le misure e le rimanda al ritorno, e Limen le accetta marcandole
**in ritardo**. Non entrano nella previsione dell'ora, ma restano
nell'archivio e nelle verifiche: sono spesso le ore del temporale, quelle
che contano di più.

## Come un dispositivo ottiene la sua identità

**La chiave privata nasce nel dispositivo e non ne esce mai.** Il dispositivo
genera la sua coppia di chiavi su curva P-256 e manda a Limen solo una
richiesta di firma (CSR) con il proprio id. Limen la firma con la CA dei
sensori e restituisce il certificato. Insieme al certificato, il
dispositivo riceve il certificato della CA, l'unico di cui si fiderà come
server.

Per questo serve hardware che sappia gestire TLS e chiavi a curve
ellittiche: un ESP32, un Raspberry Pi Pico W o un Raspberry Pi. Un Arduino
Uno non basta. Il modo più robusto di tenere la chiave è un secure element
come l'ATECC608, che costa circa un euro e non permette di estrarla; in
alternativa, secure boot e flash cifrata dell'ESP32.

## Come si registra un sensore

**Senza account: un modulo, una mail, una persona che approva.** Il modulo è
in fondo a questa pagina e si apre quando la rete accetta nuovi dispositivi
([#253](https://github.com/agent-engineering-studio/limen/issues/253)). Chiede
il tipo di sensore, la posizione, la CSR del dispositivo, una mail e tre
conferme: la licenza dei dati, le regole di sicurezza e l'informativa qui
sotto. La foto dell'installazione è facoltativa.

La CSR si genera sul dispositivo o, per una prova, su un computer:

```sh
openssl ecparam -name prime256v1 -genkey -noout -out dispositivo.key
openssl req -new -key dispositivo.key -subj "/CN=pluvio-matera-01" -out dispositivo.csr
```

Il CN è l'id del dispositivo: minuscole, cifre e trattini, da 3 a 63
caratteri. Nel modulo va il contenuto di `dispositivo.csr`. **Il file
`.key` non si manda mai**, nemmeno a Limen: se lo incolli, il modulo si
blocca.

La richiesta non crea niente da sola: arriva per mail a chi cura Limen, che la
legge e la approva o la respinge. Se la approva, ricevi per mail il
certificato del dispositivo e quello della CA, e il sensore entra nel
registro come osservatore. Ogni persona può registrare al massimo tre
dispositivi; un dispositivo revocato continua a contare.

## Dati personali

Limen conserva due dati personali di chi registra un sensore: **la mail e la
posizione esatta del sensore**. La mail serve a rispondere alla richiesta, a
contare quanti dispositivi ha registrato la stessa persona e a cancellare
tutto quando lo chiede. Non è mai pubblicata e nessuna interfaccia di Limen
la espone: non la mappa, non le API, non gli strumenti per agenti.

- **Posizione.** Quella esatta serve a legare il sensore a una cella della
griglia, e non è pubblicata. Quando le stazioni compariranno sulla mappa, la
posizione pubblica sarà arrotondata a 0,01° (circa un chilometro).
- **Foto e note.** Viaggiano solo nella mail a chi cura Limen e non sono
salvate nel database.
- **Misure.** Sono pubblicate con licenza CC BY 4.0 e non contengono dati
personali.
- **Cancellazione.** Basta rispondere alla mail di Limen. La mail viene
cancellata, i dispositivi sono revocati e la loro posizione torna al centro
della cella di un chilometro: le misure già raccolte restano, senza più
nulla che le colleghi a te.

## Cosa può fare un sensore, e cosa no

**Un sensore installato da un cittadino non fa scattare allerte e non
abbassa mai un punteggio.** Le misure entrano a livelli di fiducia, e si sale
di livello dimostrando di misurare bene, non dichiarandolo.

| Livello | Chi | Cosa può fare |
|---|---|---|
| 0 · osservatore | chiunque, dopo la registrazione | compare sulla mappa delle stazioni, serve alle verifiche e al confronto con il radar; non entra nella previsione |
| 1 · verificato | promosso in automatico dopo settimane d'accordo con il radar della Protezione civile | può solo alzare la stima della pioggia, insieme ad altri sensori di persone diverse, entro un tetto |
| 2 · istituzionale | enti, Protezione civile, università | è l'unico livello che può forzare un'allerta |

Il motivo è semplice: un pluviometro intasato che segna zero non deve poter
dire che un versante è tranquillo, e un sensore urtato non deve poter
mandare un'allerta a un comune. È la stessa regola che vale in tutto Limen:
**un dato che manca, o di cui non ci si fida, non è un dato che rassicura**.

## Sicurezza: dove non installare

**Nessuna misura vale un rischio per chi la installa.**

- Non installare su versanti in movimento, argini, alvei o sotto pareti
rocciose.
- Non installare su ponti, argini o opere pubbliche senza l'autorizzazione
dell'ente che le gestisce.
- Non andare a installare, controllare o riparare un sensore durante
un'allerta.
- Su un terreno privato serve il permesso del proprietario.
- Limen **non è un sistema di allerta personale**: per la sicurezza di
persone e beni valgono i bollettini e le allerte della Protezione civile.

La posizione pubblica di un sensore è arrotondata e la mail di chi lo
registra non è mai pubblicata.

## Stato dei lavori

| Passo | Stato |
|---|---|
| Broker dei sensori con mTLS, CA privata e verifica automatica ([#260](https://github.com/agent-engineering-studio/limen/issues/260)) | fatto |
| Livelli di fiducia nel motore ([#251](https://github.com/agent-engineering-studio/limen/issues/251)) | fatto |
| Protocollo v2 e ingresso delle misure via MQTT ([#252](https://github.com/agent-engineering-studio/limen/issues/252)) | fatto |
| Ingresso HTTP firmato ([#265](https://github.com/agent-engineering-studio/limen/issues/265)) e LoRaWAN da The Things Network ([#266](https://github.com/agent-engineering-studio/limen/issues/266)) | da fare |
| Registrazione senza account ([#253](https://github.com/agent-engineering-studio/limen/issues/253)) | fatto, il modulo apre con la rete |
| Progetti dei kit con firmware di esempio ([#256](https://github.com/agent-engineering-studio/limen/issues/256)) | da fare |
| Misura del valore dei pluviometri non ufficiali contro il radar ([#250](https://github.com/agent-engineering-studio/limen/issues/250)) | da fare |
