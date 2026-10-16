#include "sensore.h"

#include <algorithm>

#include "identita.h"

namespace sensore {

namespace {

float numero(const char* chiave, float predefinito) {
  const String testo = identita::leggi(chiave);
  return testo.isEmpty() ? predefinito : testo.toFloat();
}

}  // namespace

#if defined(LIMEN_PLUVIOMETRO)

const char* const GRANDEZZA = "rainfall";
const char* const UNITA = "mm";
const char* const TIPO = "pluviometro";

namespace {

constexpr int PIN_BASCULA = 27;
// Il reed resta chiuso 50-150 ms e rimbalza anche quando si riapre; una
// bascula da 0,28 mm non scatta più di una volta al secondo nemmeno a
// 300 mm/h. Tutto ciò che arriva entro 200 ms dall'ultimo scatto è rimbalzo.
constexpr uint32_t ANTIRIMBALZO_US = 200000;

portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t scatti = 0;
volatile uint32_t ultimo_us = 0;
float mm_scatto = 0.2794f;

void IRAM_ATTR scatto() {
  const uint32_t ora = micros();
  portENTER_CRITICAL_ISR(&mux);
  if (ora - ultimo_us > ANTIRIMBALZO_US) {
    ++scatti;
    ultimo_us = ora;
  }
  portEXIT_CRITICAL_ISR(&mux);
}

uint32_t prendi_scatti() {
  portENTER_CRITICAL(&mux);
  const uint32_t n = scatti;
  scatti = 0;
  portEXIT_CRITICAL(&mux);
  return n;
}

}  // namespace

void inizia() {
  // 0,2794 mm è la bascula da 0,011 pollici dei kit più diffusi: va misurata
  // sulla propria versando una quantità d'acqua nota.
  mm_scatto = numero("mm_scatto", 0.2794f);
  pinMode(PIN_BASCULA, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BASCULA), scatto, FALLING);
}

void azzera() { prendi_scatti(); }

bool misura(float* valore) {
  const uint32_t n = prendi_scatti();
  // Zero è una misura: un intervallo senza scatti dice che non è piovuto.
  *valore = n * mm_scatto;
  return true;
}

void descrivi_calibrazione() {
  Serial.printf("mm_scatto=%.4f (mm per ogni svuotamento della bascula)\n", mm_scatto);
}

float lettura_grezza() { return scatti; }

#elif defined(LIMEN_UMIDITA_SUOLO)

const char* const GRANDEZZA = "soil_moisture";
const char* const UNITA = "m3/m3";
const char* const TIPO = "umidita_suolo";

namespace {

constexpr int PIN_SONDA = 34;
float secco = 0;
float bagnato = 0;
float saturazione = 0.45f;

}  // namespace

float lettura_grezza() {
  uint32_t somma = 0;
  for (int i = 0; i < 32; ++i) {
    somma += analogRead(PIN_SONDA);
    delay(5);
  }
  return somma / 32.0f;
}

void azzera() {}

void inizia() {
  analogSetPinAttenuation(PIN_SONDA, ADC_11db);
  secco = numero("secco", 0);
  bagnato = numero("bagnato", 0);
  saturazione = numero("saturazione", 0.45f);
}

bool misura(float* valore) {
  // Senza calibrazione la sonda dà un numero che non è un contenuto d'acqua.
  if (secco <= 0 || bagnato <= 0 || secco == bagnato) return false;
  const float grezza = lettura_grezza();
  // Una sonda staccata o in corto legge agli estremi dell'ADC.
  if (grezza < 50 || grezza > 4045) return false;
  // Le capacitive leggono meno quando il suolo è più bagnato.
  float frazione = (secco - grezza) / (secco - bagnato);
  frazione = constrain(frazione, 0.0f, 1.0f);
  *valore = frazione * saturazione;
  return true;
}

void descrivi_calibrazione() {
  Serial.printf("secco=%.0f bagnato=%.0f saturazione=%.2f\n", secco, bagnato, saturazione);
  Serial.println("secco: lettura grezza con la sonda in aria; bagnato: immersa in acqua fino");
  Serial.println("alla linea; saturazione: il contenuto d'acqua del tuo suolo saturo (0,35-0,50)");
}

#elif defined(LIMEN_IDROMETRO)

const char* const GRANDEZZA = "water_level";
const char* const UNITA = "m";
const char* const TIPO = "idrometro";

namespace {

constexpr int PIN_TRIG = 26;
constexpr int PIN_ECHO = 25;
constexpr float VELOCITA_SUONO_M_US = 0.000343f;
float quota = 0;

float distanza_m() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(5);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(20);
  digitalWrite(PIN_TRIG, LOW);
  const unsigned long eco = pulseIn(PIN_ECHO, HIGH, 40000);
  if (eco == 0) return NAN;
  return eco * VELOCITA_SUONO_M_US / 2.0f;
}

}  // namespace

float lettura_grezza() { return distanza_m(); }

void azzera() {}

void inizia() {
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  quota = numero("quota", 0);
}

bool misura(float* valore) {
  if (quota <= 0) return false;
  // La mediana di cinque: un'eco sul bordo del pozzetto o una goccia sul
  // trasduttore non deve diventare un'onda di piena.
  float letture[5];
  int n = 0;
  for (int i = 0; i < 5; ++i) {
    const float d = distanza_m();
    if (!isnan(d) && d > 0.20f) letture[n++] = d;
    delay(60);
  }
  if (n < 3) return false;
  std::sort(letture, letture + n);
  *valore = quota - letture[n / 2];
  return true;
}

void descrivi_calibrazione() {
  Serial.printf("quota=%.3f (m fra il trasduttore e lo zero idrometrico)\n", quota);
}

#else
#error "Scegli un sensore: -DLIMEN_PLUVIOMETRO, -DLIMEN_UMIDITA_SUOLO o -DLIMEN_IDROMETRO"
#endif

}  // namespace sensore
