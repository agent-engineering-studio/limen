// Sensore dei cittadini di Limen: firmware di esempio per ESP32 (#256).
//
// Misura a intervalli fissi allineati all'orologio, mette ogni misura in una
// coda e la pubblica sul broker dei sensori in SenML (RFC 8428), come la
// legge Limen (docs/guida/sensori.md, «Il protocollo v2»):
//
//   limen/v2/<id>/obs     [{"bn":"<id>/","bt":…,"n":"rainfall","u":"mm","v":0.2},
//                          …, {"n":"seq","v":18342}]
//   limen/v2/<id>/status  online alla connessione, offline come last will
//
// Senza rete la coda tiene un giorno di misure (in RAM: un calo di tensione
// la perde) e le rimanda al ritorno, a lotti e senza superare il limite di
// messaggi al minuto: Limen le accetta come «in ritardo». Un lotto rimandato
// tiene la sua sequenza, così se il primo invio era arrivato il secondo si
// scarta come replay invece di contare due volte la stessa pioggia.
//
// La conferma (QoS 1) è del broker, non di Limen: un messaggio che Limen
// scarta — troppi al minuto, unità sbagliata — è perso anche se confermato.
// Per questo il firmware sta largo sotto il limite: nel conto entrano anche
// `online`, il last will e ogni ritrasmissione.
//
// Si configura dalla seriale, a 115200: scrivi `aiuto`.

#include <Arduino.h>
#include <WiFi.h>
#include <mqtt_client.h>
#include <time.h>

#include "identita.h"
#include "sensore.h"

namespace {

// Prima di questo istante l'orologio non è ancora stato preso da NTP.
constexpr time_t OROLOGIO_VALIDO = 1767225600;  // 2026-01-01T00:00:00Z
constexpr size_t CODA = 288;                    // un giorno a cinque minuti
constexpr size_t PER_MESSAGGIO = 24;            // sotto i 2048 byte di Limen
// Limen scarta oltre dodici messaggi al minuto per dispositivo: sei lasciano
// posto a status, last will e ritrasmissioni.
constexpr uint32_t PAUSA_FRA_INVII_MS = 10000;
// esp-mqtt ritrasmette da sé un QoS 1 senza conferma; il valore predefinito
// (1 s) brucerebbe il limite al minuto su una rete lenta.
constexpr int RITRASMISSIONE_MS = 20000;
// Dopo una riconnessione l'outbox di esp-mqtt ha già buttato il messaggio
// (30 s): lo si rimanda noi, con gli stessi byte.
constexpr uint32_t ATTESA_CONFERMA_MS = 35000;
constexpr const char* BROKER = "mqtts://limen.agentengineering.it:8883";

struct Campione {
  time_t t;
  float v;
};

Campione coda[CODA];
size_t testa = 0;
size_t quanti = 0;

struct InVolo {
  String payload;
  size_t campioni = 0;
  int msg_id[2] = {0, 0};  // l'invio corrente e quello prima: una conferma tardiva vale
  uint32_t inviato_ms = 0;
  uint32_t connessione = 0;
  bool attivo = false;
};
InVolo in_volo;

esp_mqtt_client_handle_t client = nullptr;
volatile bool connesso = false;
volatile uint32_t connessioni = 0;

// Le conferme arrivano dal task di esp-mqtt, a raffica dopo una
// riconnessione (quella di `online` e quella del lotto): un anello, non una
// variabile sola. Gli id MQTT vanno da 1 a 65535, quindi 0 è «vuoto».
portMUX_TYPE mux_conferme = portMUX_INITIALIZER_UNLOCKED;
int conferme[8] = {};
size_t prossima_conferma = 0;

bool confermato(int msg_id) {
  if (msg_id <= 0) return false;
  bool trovato = false;
  portENTER_CRITICAL(&mux_conferme);
  for (int c : conferme) trovato |= c == msg_id;
  portEXIT_CRITICAL(&mux_conferme);
  return trovato;
}

String id, ca, cert, chiave, uri, topic_obs, topic_status;
uint32_t intervallo_s = 300;
time_t prossima_misura = 0;
uint32_t ultimo_invio_ms = 0;

void accoda(time_t t, float v) {
  if (quanti == CODA) {
    // Piena: si perde la più vecchia, che è anche la meno utile. Se era nel
    // lotto in volo, il lotto ne conta una in meno da togliere alla conferma.
    testa = (testa + 1) % CODA;
    --quanti;
    if (in_volo.attivo && in_volo.campioni > 0) --in_volo.campioni;
  }
  coda[(testa + quanti) % CODA] = {t, v};
  ++quanti;
}

String numero(double v) {
  char testo[24];
  snprintf(testo, sizeof(testo), "%.4f", v);
  return testo;
}

String componi(size_t n, uint64_t seq) {
  const Campione& primo = coda[testa];
  String s = "[{\"bn\":\"" + id + "/\",\"bt\":" + String(static_cast<uint32_t>(primo.t)) +
             ",\"n\":\"" + sensore::GRANDEZZA + "\",\"u\":\"" + sensore::UNITA +
             "\",\"v\":" + numero(primo.v) + "}";
  for (size_t i = 1; i < n; ++i) {
    const Campione& c = coda[(testa + i) % CODA];
    s += ",{\"n\":\"" + String(sensore::GRANDEZZA) + "\",\"u\":\"" + sensore::UNITA +
         "\",\"t\":" + String(static_cast<int32_t>(c.t - primo.t)) + ",\"v\":" + numero(c.v) +
         "}";
  }
  s += ",{\"n\":\"seq\",\"v\":" + String(static_cast<unsigned long long>(seq)) + "}]";
  return s;
}

void evento(void*, esp_event_base_t, int32_t tipo, void* dati) {
  auto* e = static_cast<esp_mqtt_event_handle_t>(dati);
  switch (tipo) {
    case MQTT_EVENT_CONNECTED:
      connesso = true;
      ++connessioni;
      esp_mqtt_client_publish(client, topic_status.c_str(), "online", 0, 1, 1);
      break;
    case MQTT_EVENT_DISCONNECTED:
      connesso = false;
      break;
    case MQTT_EVENT_PUBLISHED:
      portENTER_CRITICAL(&mux_conferme);
      conferme[prossima_conferma] = e->msg_id;
      prossima_conferma = (prossima_conferma + 1) % 8;
      portEXIT_CRITICAL(&mux_conferme);
      break;
    default:
      break;
  }
}

void avvia_mqtt() {
  id = identita::leggi("id");
  ca = identita::leggi("ca");
  cert = identita::leggi("cert");
  chiave = identita::leggi("chiave");
  uri = identita::leggi("broker", BROKER);
  topic_obs = "limen/v2/" + id + "/obs";
  topic_status = "limen/v2/" + id + "/status";

  // Le stringhe restano vive per tutta l'esecuzione: il client ne tiene i
  // puntatori. Il server si verifica solo contro la CA dei sensori.
  esp_mqtt_client_config_t cfg = {};
  cfg.uri = uri.c_str();
  cfg.client_id = id.c_str();
  cfg.cert_pem = ca.c_str();
  cfg.client_cert_pem = cert.c_str();
  cfg.client_key_pem = chiave.c_str();
  cfg.keepalive = 120;
  cfg.buffer_size = 2048;  // un lotto pieno supera i 1024 predefiniti
  cfg.message_retransmit_timeout = RITRASMISSIONE_MS;
  cfg.lwt_topic = topic_status.c_str();
  cfg.lwt_msg = "offline";
  cfg.lwt_qos = 1;
  cfg.lwt_retain = 1;
  client = esp_mqtt_client_init(&cfg);
  esp_mqtt_client_register_event(client, MQTT_EVENT_ANY, evento, nullptr);
  esp_mqtt_client_start(client);
}

void pubblica() {
  const int msg_id =
      esp_mqtt_client_publish(client, topic_obs.c_str(), in_volo.payload.c_str(), 0, 1, 0);
  in_volo.msg_id[1] = in_volo.msg_id[0];
  in_volo.msg_id[0] = msg_id;
  in_volo.connessione = connessioni;
  // Un invio fallito (-1) non aspetta la conferma: si ritenta al prossimo turno.
  in_volo.inviato_ms = msg_id > 0 ? millis() : millis() - ATTESA_CONFERMA_MS;
  ultimo_invio_ms = millis();
}

uint32_t connessione_vista = 0;

void invia() {
  if (connessioni != connessione_vista) {
    // Appena connessi è già partito `online`: si aspetta un turno.
    connessione_vista = connessioni;
    ultimo_invio_ms = millis();
  }
  if (!connesso || millis() - ultimo_invio_ms < PAUSA_FRA_INVII_MS) return;

  if (in_volo.attivo) {
    if (confermato(in_volo.msg_id[0]) || confermato(in_volo.msg_id[1])) {
      testa = (testa + in_volo.campioni) % CODA;
      quanti -= in_volo.campioni;
      in_volo.attivo = false;
    } else if (in_volo.connessione != connessioni &&
               millis() - in_volo.inviato_ms > ATTESA_CONFERMA_MS) {
      // Stessi byte, stessa sequenza: vedi in cima. Sulla stessa connessione
      // ritrasmette già esp-mqtt.
      pubblica();
      return;
    } else if (in_volo.msg_id[0] <= 0 && millis() - in_volo.inviato_ms >= ATTESA_CONFERMA_MS) {
      pubblica();
      return;
    } else {
      return;
    }
  }
  if (quanti == 0) return;
  in_volo.campioni = min(quanti, PER_MESSAGGIO);
  in_volo.payload = componi(in_volo.campioni, identita::prossima_sequenza());
  in_volo.msg_id[0] = in_volo.msg_id[1] = 0;
  in_volo.attivo = true;
  // Gli id sono casuali: una conferma vecchia non deve valere per il lotto nuovo.
  portENTER_CRITICAL(&mux_conferme);
  for (int& c : conferme) c = 0;
  portEXIT_CRITICAL(&mux_conferme);
  pubblica();
}

void misura_se_tocca() {
  const time_t ora = time(nullptr);
  if (ora < OROLOGIO_VALIDO) return;
  if (prossima_misura == 0) {
    identita::allinea_sequenza(ora);
    sensore::azzera();
    prossima_misura = (ora / intervallo_s + 1) * intervallo_s;
    return;
  }
  if (ora < prossima_misura) return;
  float v;
  // L'istante è la fine dell'intervallo: la pioggia di 10:00-10:05 sta alle 10:05.
  // Un NaN finirebbe nel JSON come `nan` e farebbe scartare tutto il lotto.
  if (sensore::misura(&v) && isfinite(v)) {
    accoda(prossima_misura, v);
  } else {
    Serial.println("misura non riuscita: niente dato per questo intervallo");
  }
  prossima_misura = (ora / intervallo_s + 1) * intervallo_s;
}

// --- console --------------------------------------------------------------

String riga;
String incolla;  // "cert" o "ca" mentre si incolla un PEM
String pem;

void aiuto() {
  Serial.println(
      "Comandi (uno per riga):\n"
      "  ssid=<rete>  password=<password>  id=<id-del-dispositivo>\n"
      "  csr          crea la chiave (la prima volta) e stampa la CSR da mandare a Limen\n"
      "  cert         poi incolla il certificato del dispositivo ricevuto per mail\n"
      "  ca           poi incolla il certificato della CA ricevuto per mail\n"
      "  intervallo=<secondi>  broker=<mqtts://host:porta>\n"
      "  grezza       la lettura grezza del sensore, per calibrarlo\n"
      "  stato        riavvia      (le impostazioni valgono dal riavvio)");
  sensore::descrivi_calibrazione();
}

void stato() {
  Serial.printf("sensore %s, id '%s', rete '%s'\n", sensore::TIPO, identita::leggi("id").c_str(),
                identita::leggi("ssid").c_str());
  Serial.printf("chiave %s, certificato %s, CA %s\n",
                identita::leggi("chiave").isEmpty() ? "no" : "sì",
                identita::leggi("cert").isEmpty() ? "no" : "sì",
                identita::leggi("ca").isEmpty() ? "no" : "sì");
  Serial.printf("Wi-Fi %s, broker %s, orologio %s, in coda %u\n",
                WiFi.isConnected() ? "connesso" : "no", connesso ? "connesso" : "no",
                time(nullptr) >= OROLOGIO_VALIDO ? "ok" : "non ancora", static_cast<unsigned>(quanti));
  sensore::descrivi_calibrazione();
}

void comando(const String& c) {
  const int uguale = c.indexOf('=');
  if (uguale > 0) {
    const String chiave = c.substring(0, uguale);
    const String valore = c.substring(uguale + 1);
    // Certificati e chiave passano solo da `cert`, `ca` e `csr`, che li
    // controllano: una riga `cert=…` li scavalcherebbe.
    static const char* const AMMESSE[] = {"ssid",      "password", "id",          "broker",
                                          "intervallo", "mm_scatto", "secco",      "bagnato",
                                          "saturazione", "quota"};
    bool ammessa = false;
    for (const char* a : AMMESSE) ammessa |= chiave == a;
    if (!ammessa) {
      Serial.println("impostazione sconosciuta: scrivi `aiuto`");
      return;
    }
    if (chiave == "intervallo" && (valore.toInt() < 60 || valore.toInt() > 3600)) {
      Serial.println("intervallo fra 60 e 3600 secondi");
      return;
    }
    if (chiave == "broker" && !valore.startsWith("mqtts://")) {
      Serial.println("il broker si raggiunge solo in TLS: mqtts://host:porta");
      return;
    }
    if (chiave == "id" && !identita::id_valido(valore)) {
      Serial.println("id non valido: minuscole, cifre e trattini, da 3 a 63 caratteri");
      return;
    }
    if (chiave == "id" && valore != identita::leggi("id") && !identita::leggi("cert").isEmpty()) {
      Serial.println("attenzione: il certificato salvato è per l'id precedente");
    }
    identita::scrivi(chiave.c_str(), valore);
    Serial.println("salvato; vale dal prossimo riavvio");
  } else if (c == "csr") {
    const String id_nuovo = identita::leggi("id");
    if (!identita::id_valido(id_nuovo)) {
      Serial.println("prima `id=<id-del-dispositivo>`");
      return;
    }
    Serial.println(identita::csr(id_nuovo));
  } else if (c == "cert" || c == "ca") {
    incolla = c;
    pem = "";
    Serial.println("incolla il PEM, da -----BEGIN CERTIFICATE----- a -----END CERTIFICATE-----");
    Serial.println("(`annulla` per uscire)");
  } else if (c == "grezza") {
    Serial.println(sensore::lettura_grezza());
  } else if (c == "stato") {
    stato();
  } else if (c == "riavvia") {
    ESP.restart();
  } else if (!c.isEmpty()) {
    aiuto();
  }
}

void console() {
  while (Serial.available()) {
    const char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') {
      if (riga.length() < 4096) riga += ch;
      continue;
    }
    String r = riga;
    riga = "";
    r.trim();
    if (!incolla.isEmpty()) {
      if (r == "annulla") {
        incolla = "";
        Serial.println("annullato");
        continue;
      }
      pem += r + "\n";
      if (r.startsWith("-----END ")) {
        const bool ok = incolla == "cert" ? identita::salva_certificato(pem) : identita::salva_ca(pem);
        Serial.println(ok ? "salvato; vale dal prossimo riavvio" : "non salvato");
        incolla = "";
      }
      continue;
    }
    comando(r);
  }
}

}  // namespace

void setup() {
  // Un PEM incollato arriva tutto insieme, e loop() può essere fermo qualche
  // secondo su una pubblicazione: il buffer predefinito (256 B) lo tronca.
  Serial.setRxBufferSize(4096);
  Serial.begin(115200);
  identita::inizia();
  sensore::inizia();
  intervallo_s =
      static_cast<uint32_t>(constrain(identita::leggi("intervallo", "300").toInt(), 60L, 3600L));

  // Il Wi-Fi si accende comunque: la radio serve anche al generatore casuale
  // con cui nasce la chiave.
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  const String ssid = identita::leggi("ssid");
  if (!ssid.isEmpty()) WiFi.begin(ssid.c_str(), identita::leggi("password").c_str());
  configTime(0, 0, "time.inrim.it", "pool.ntp.org");

  Serial.printf("\nLimen · sensore %s\n", sensore::TIPO);
  if (identita::pronta()) {
    avvia_mqtt();
  } else {
    Serial.println("Configurazione incompleta: scrivi `aiuto`.");
  }
}

void loop() {
  console();
  if (client != nullptr) {
    misura_se_tocca();
    invia();
  }
  delay(20);
}
