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

## Perché un sensore in più

**Il 10 ottobre 2026, nel Reggino, il modello meteo vedeva un terzo della
pioggia che stava cadendo.** A Melito, San Lorenzo e Bagaladi le previsioni
davano circa 50 mm nel giorno; il radar della Protezione civile, corretto con
i pluviometri, ne misurava fra 110 e 176. Sulle celle delle frane la
componente meteo di Limen non ha mai superato 0,29, quando per arrivare ad
«Alto» serviva 0,65. Il terreno era quello giusto: mancava la pioggia vera.

Un temporale autunnale sul Sud Italia scarica in pochi chilometri quadrati,
e fra un pluviometro ufficiale e l'altro ci sono spesso dieci o quindici
chilometri. Un pluviometro in più non decide da solo, ma dice al radar dove
sbaglia, e messo insieme ad altri di persone diverse alza la stima della
pioggia proprio dove le reti ufficiali non arrivano.

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
minuto, contando anche `status`, il last will e le ritrasmissioni: oltre si
scartano, e un dispositivo che insiste va in quarantena
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

## Tre sensori da costruire

**Un ESP32, il sensore, una scatola stagna e un'alimentazione: fra 35 e 60
euro.** I prezzi sono indicativi, per pezzi singoli comprati in Italia. Gli
inclinometri restano fuori: misurano un versante che si muove, e un dato del
genere vale solo da un ente (livello 2).

### Pluviometro a bascula

Una bascula si riempie con una quantità fissa di pioggia, si svuota
ribaltandosi e chiude per un attimo un interruttore reed: l'ESP32 conta gli
scatti e ogni cinque minuti manda i millimetri caduti.

| Componente | Costo |
|---|---|
| ESP32 DevKit (ESP32-WROOM-32) | 8 € |
| Pluviometro a bascula da ricambio per stazioni meteo, uscita reed | 20 € |
| Alimentatore USB 5 V, oppure pannello da 6 W con batteria 18650 e caricatore | 8-20 € |
| Scatola IP65 con pressacavi | 6 € |
| Palo o staffa, cavo, morsetti | 8 € |
| **Totale** | **circa 50-60 €** |

| Pluviometro | ESP32 |
|---|---|
| filo del reed | GPIO 27 |
| altro filo del reed | GND |

Non serve una resistenza: il firmware accende quella interna e ignora i
rimbalzi del contatto. Ogni bascula ha il suo volume: si misura versando
lentamente una quantità d'acqua nota e contando gli scatti, poi si scrive
`mm_scatto=` sulla seriale. Il valore di partenza, 0,2794 mm, è quello dei
modelli più diffusi.

**Dove metterlo**, secondo le regole dell'Organizzazione meteorologica
mondiale: bocca orizzontale a 1-1,5 m da terra; lontano da ogni ostacolo
(muri, alberi, recinzioni) almeno il doppio della sua altezza sopra la bocca,
meglio quattro volte; non su un tetto o vicino a un edificio, dove il vento
gira e porta via la pioggia. Una volta al mese si pulisce il filtro: foglie e
insetti lo intasano, e un pluviometro intasato segna zero.

### Umidità del suolo

Una sonda capacitiva misura quanto il terreno trattiene l'acqua, che per una
frana conta quanto la pioggia: lo stesso temporale fa scivolare un versante
già saturo e non quello asciutto.

| Componente | Costo |
|---|---|
| ESP32 DevKit | 8 € |
| Sonda capacitiva v2.0 con TLC555 (non quelle con NE555, che a 3,3 V non funzionano) | 3 € |
| Cavo schermato a tre poli, 3 m | 3 € |
| Alimentazione e scatola IP65, come sopra | 15-25 € |
| **Totale** | **circa 35-40 €** |

| Sonda | ESP32 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| AOUT | GPIO 34 |

La sonda va infilata in verticale fino alla linea, a 5-10 cm di profondità,
lontano da radici e sassi, con l'elettronica sopra il terreno sigillata con
resina o guaina termorestringente. Si calibra prima di interrarla: `grezza`
in aria dà `secco=`, `grezza` con la sonda in un bicchiere d'acqua fino alla
linea dà `bagnato=`. Una sonda da tre euro sbaglia di qualche punto
percentuale anche ben calibrata, ed è uno dei motivi per cui parte come
osservatore.

### Idrometro

Un sensore a ultrasuoni impermeabile, montato sopra un corso d'acqua, misura
la distanza dalla superficie: il livello è la sua quota meno quella
distanza. **Solo con l'autorizzazione dell'ente che gestisce il corso
d'acqua o il ponte**, e Limen non legge ancora il livello dell'acqua: il
modulo di registrazione lo offrirà quando il motore dell'alluvione saprà
usarlo.

| Componente | Costo |
|---|---|
| ESP32 DevKit | 8 € |
| JSN-SR04T impermeabile (da 25 cm a 4,5 m) | 10 € |
| Due resistenze, 1 kΩ e 2 kΩ | 0,5 € |
| Staffa, alimentazione e scatola IP65 | 25-35 € |
| **Totale** | **circa 45-55 €** |

| JSN-SR04T | ESP32 |
|---|---|
| 5V | VIN (5 V) |
| GND | GND |
| TRIG | GPIO 26 |
| ECHO | GPIO 25, attraverso il partitore: 1 kΩ verso ECHO, 2 kΩ verso GND |

Il partitore serve perché l'ECHO esce a 5 V e l'ESP32 ne regge 3,3. La quota
del trasduttore sopra lo zero idrometrico, in metri, si scrive come
`quota=`. Un radar a onde millimetriche (40-70 €) misura meglio con la
pioggia e la schiuma, ma il firmware di esempio non lo gestisce.

## Il firmware di esempio

**Un solo programma per i tre sensori, nel repository di Limen in
[`firmware/limen-sensore`](https://github.com/agent-engineering-studio/limen/tree/main/firmware/limen-sensore),
compilato a ogni modifica.** Si carica con
[PlatformIO](https://platformio.org):

```sh
cd firmware/limen-sensore
pio run -e pluviometro -t upload     # oppure umidita_suolo, idrometro
pio device monitor                   # la seriale, a 115200
```

Nel programma non c'è nessun segreto: rete, id e certificati si danno dalla
seriale e restano nella memoria del dispositivo.

```
ssid=LaMiaRete
password=…
id=pluvio-matera-01
riavvia
csr
```

`csr` crea la chiave del dispositivo la prima volta e stampa la richiesta da
incollare nel modulo di registrazione. Quando arriva la mail con i due
certificati si scrive `cert` e si incolla quello del dispositivo, poi `ca` e
si incolla quello della CA, poi `riavvia`. Il firmware rifiuta un
certificato che non corrisponde alla sua chiave o che è per un altro id.
Ogni impostazione, calibrazioni comprese, vale dal riavvio successivo.
`stato` dice cosa manca.

Cosa fa da solo:

- prende l'ora UTC da NTP e non misura finché non ce l'ha;
- misura ogni cinque minuti, allineato all'orologio (`intervallo=` per
cambiarlo);
- pubblica in SenML con conferma (QoS 1), e annuncia `online`/`offline`;
- senza rete tiene un giorno di misure e le rimanda al ritorno a gruppi, senza
superare il limite di messaggi al minuto. La coda sta in memoria volatile:
un calo di tensione la perde;
- tiene il numero di sequenza fra un riavvio e l'altro, e un gruppo rimandato
conserva il suo: se il primo invio era arrivato, Limen scarta il secondo
invece di contare due volte la stessa pioggia. La conferma viene dal broker,
non da Limen: un messaggio che Limen scarta è perso, per questo il firmware
ne manda al massimo sei al minuto.

**La chiave nella memoria è in chiaro.** Per un dispositivo che resta
all'aperto, dove chiunque può staccarlo, si accendono la flash encryption e
il secure boot dell'ESP32, o si tiene la chiave in un ATECC608.

## Come collegarlo

| Collegamento | Quando | Stato |
|---|---|---|
| Wi-Fi con un ESP32 | c'è una rete a portata, a casa, a scuola | il firmware di esempio |
| Raspberry Pi Pico W | come l'ESP32; TLS con mbedTLS o MicroPython | nessun esempio |
| Raspberry Pi | ha già Linux: bastano `mosquitto_pub` o Paho | vedi sotto |
| LoRaWAN con The Things Network | in campagna, senza Wi-Fi, chilometri di portata | in arrivo ([#266](https://github.com/agent-engineering-studio/limen/issues/266)) |
| Arduino Uno | — | **no**: non fa TLS |

Da un Raspberry Pi, o da un computer per una prova, un messaggio si manda
così (la sequenza deve crescere a ogni invio):

```sh
mosquitto_pub -h limen.agentengineering.it -p 8883 -q 1 \
  --cafile ca.crt --cert dispositivo.crt --key dispositivo.key \
  -t limen/v2/pluvio-matera-01/obs \
  -m "[{\"bn\":\"pluvio-matera-01/\",\"bt\":$(date +%s),\"n\":\"rainfall\",\"u\":\"mm\",\"v\":0.0},{\"n\":\"seq\",\"v\":1}]"
```

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
caratteri. **L'id è pubblico**, perché compare sulla mappa delle stazioni:
non metterci il tuo nome né il tuo indirizzo. Nel modulo va il contenuto di `dispositivo.csr`. **Il file
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
griglia, e non è pubblicata. Sulla mappa, nel livello «Stazioni dei
cittadini», la posizione è arrotondata a 0,01° (circa un chilometro).
- **Foto e note.** Viaggiano solo nella mail a chi cura Limen e non sono
salvate nel database.
- **Misure.** Sono pubblicate con licenza CC BY 4.0 e non contengono dati
personali.
- **Cancellazione.** Basta rispondere alla mail di Limen. La mail viene
cancellata, i dispositivi sono revocati e la loro posizione torna al centro
della cella di un chilometro: le misure già raccolte restano, senza più
nulla che le colleghi a te.

## Licenza dei dati

**Le misure di un sensore registrato sono pubblicate con licenza
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.it).**
Chiunque può riusarle, anche per scopi commerciali, citando Limen e la
stazione. Il modulo di registrazione lo chiede esplicitamente: è ciò che
permette a un comune, a un'università o a un'altra rete di usarle. Le misure
non contengono dati personali; la posizione pubblica della stazione è
arrotondata (vedi sopra).

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
| Le stazioni sulla mappa, con livello, ultimo dato e controllo di qualità ([#255](https://github.com/agent-engineering-studio/limen/issues/255)) | fatto |
| Ingresso HTTP firmato ([#265](https://github.com/agent-engineering-studio/limen/issues/265)) e LoRaWAN da The Things Network ([#266](https://github.com/agent-engineering-studio/limen/issues/266)) | da fare |
| Registrazione senza account ([#253](https://github.com/agent-engineering-studio/limen/issues/253)) | fatto, il modulo apre con la rete |
| Progetti dei kit con firmware di esempio ([#256](https://github.com/agent-engineering-studio/limen/issues/256)) | fatto |
| Misura del valore dei pluviometri non ufficiali contro il radar ([#250](https://github.com/agent-engineering-studio/limen/issues/250)) | da fare |
