// L'identità del dispositivo: chiave, CSR, certificati e impostazioni.
//
// La chiave privata nasce qui, su P-256, e non esce mai: Limen riceve solo
// la CSR. Tutto sta nella NVS dell'ESP32. In chiaro, in questo esempio: per
// un dispositivo che resta all'aperto si accendono flash encryption e secure
// boot, o si tiene la chiave in un secure element come l'ATECC608.
#pragma once

#include <Arduino.h>

namespace identita {

void inizia();

String leggi(const char* chiave, const char* predefinito = "");
void scrivi(const char* chiave, const String& valore);

// Il CN del certificato e il segmento del topic: minuscole, cifre e
// trattini, da 3 a 63 caratteri. Lo stesso controllo di Limen.
bool id_valido(const String& id);

// Crea la chiave se manca e restituisce la CSR in PEM, con CN = id.
// Stringa vuota se qualcosa va storto (il motivo è sulla seriale).
String csr(const String& id);

// Salva il certificato del dispositivo solo se corrisponde alla sua chiave
// e se il suo CN è l'id del dispositivo.
bool salva_certificato(const String& pem);
bool salva_ca(const String& pem);

// Rete, id, chiave, CA, e un certificato il cui CN è l'id.
bool pronta();

// La sequenza cresce sempre, anche dopo un riavvio o una flash cancellata.
void allinea_sequenza(time_t adesso);
uint64_t prossima_sequenza();

}  // namespace identita
