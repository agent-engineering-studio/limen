// La misura: una per ambiente di compilazione (platformio.ini).
//
//   pluviometro    bascula con interruttore reed sul GPIO 27 verso GND;
//                  pubblica i mm caduti nell'intervallo (`rainfall`, mm)
//   umidita_suolo  sonda capacitiva sul GPIO 34 (ADC1); pubblica il
//                  contenuto d'acqua volumetrico (`soil_moisture`, m3/m3)
//   idrometro      ultrasuoni impermeabile JSN-SR04T, TRIG 26 ed ECHO 25
//                  (con partitore: l'ECHO è a 5 V); pubblica il livello
//                  dell'acqua (`water_level`, m), che Limen ancora non legge
#pragma once

#include <Arduino.h>

namespace sensore {

extern const char* const GRANDEZZA;  // il nome SenML
extern const char* const UNITA;      // l'unità esatta che Limen si aspetta
extern const char* const TIPO;       // come nel modulo di registrazione

void inizia();

// Dimentica quanto accumulato finora: la pioggia caduta prima che
// l'orologio fosse giusto non ha un intervallo a cui appartenere.
void azzera();

// Una misura per l'intervallo appena chiuso. False se il sensore non
// risponde: meglio nessun dato che un numero inventato.
bool misura(float* valore);

// La calibrazione, dalla seriale: `mm_scatto`, `secco`, `bagnato`,
// `saturazione`, `quota`. La lettura grezza aiuta a trovarla.
void descrivi_calibrazione();
float lettura_grezza();

}  // namespace sensore
