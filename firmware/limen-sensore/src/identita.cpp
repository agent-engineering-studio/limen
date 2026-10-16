#include "identita.h"

#include <Preferences.h>
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/entropy.h>
#include <mbedtls/oid.h>
#include <mbedtls/pk.h>
#include <mbedtls/version.h>
#include <mbedtls/x509_crt.h>
#include <mbedtls/x509_csr.h>

namespace identita {

namespace {

Preferences nvs;

// La sequenza deve crescere anche dopo un riavvio, ma scriverla in flash a
// ogni messaggio la consumerebbe. Si prenota un blocco: al riavvio si riparte
// dalla fine dell'ultimo blocco prenotato, saltando al più BLOCCO numeri.
constexpr uint64_t BLOCCO = 100;
uint64_t sequenza = 0;
uint64_t prenotata = 0;

struct Caso {
  mbedtls_entropy_context entropia;
  mbedtls_ctr_drbg_context drbg;
  bool pronto = false;

  Caso() {
    mbedtls_entropy_init(&entropia);
    mbedtls_ctr_drbg_init(&drbg);
    static const char personalizza[] = "limen-sensore";
    pronto = mbedtls_ctr_drbg_seed(&drbg, mbedtls_entropy_func, &entropia,
                                   reinterpret_cast<const unsigned char*>(personalizza),
                                   sizeof(personalizza)) == 0;
  }
  ~Caso() {
    mbedtls_ctr_drbg_free(&drbg);
    mbedtls_entropy_free(&entropia);
  }
};

String cn(const mbedtls_x509_crt& crt) {
  for (const mbedtls_x509_name* n = &crt.subject; n != nullptr; n = n->next) {
    if (MBEDTLS_OID_CMP(MBEDTLS_OID_AT_CN, &n->oid) == 0) {
      // Il valore non finisce con uno zero: si copia per lunghezza.
      String valore;
      valore.reserve(n->val.len);
      for (size_t i = 0; i < n->val.len; ++i) valore += static_cast<char>(n->val.p[i]);
      return valore;
    }
  }
  return "";
}

bool carica_chiave(mbedtls_pk_context* pk, Caso& caso) {
  String pem = leggi("chiave");
  if (pem.isEmpty()) return false;
  const auto* testo = reinterpret_cast<const unsigned char*>(pem.c_str());
#if MBEDTLS_VERSION_MAJOR >= 3
  return mbedtls_pk_parse_key(pk, testo, pem.length() + 1, nullptr, 0, mbedtls_ctr_drbg_random,
                              &caso.drbg) == 0;
#else
  (void)caso;
  return mbedtls_pk_parse_key(pk, testo, pem.length() + 1, nullptr, 0) == 0;
#endif
}

bool crea_chiave(mbedtls_pk_context* pk, Caso& caso) {
  if (mbedtls_pk_setup(pk, mbedtls_pk_info_from_type(MBEDTLS_PK_ECKEY)) != 0) return false;
  if (mbedtls_ecp_gen_key(MBEDTLS_ECP_DP_SECP256R1, mbedtls_pk_ec(*pk), mbedtls_ctr_drbg_random,
                          &caso.drbg) != 0) {
    return false;
  }
  static unsigned char pem[512];
  if (mbedtls_pk_write_key_pem(pk, pem, sizeof(pem)) != 0) return false;
  scrivi("chiave", String(reinterpret_cast<char*>(pem)));
  return true;
}

bool prenota(uint64_t fino_a) {
  if (nvs.putULong64("seq", fino_a) == 0) {
    Serial.println("errore: memoria piena, sequenza non salvata");
    return false;
  }
  prenotata = fino_a;
  return true;
}

}  // namespace

void inizia() {
  nvs.begin("limen", false);
  sequenza = nvs.getULong64("seq", 0);
  prenota(sequenza + BLOCCO);
}

String leggi(const char* chiave, const char* predefinito) {
  return nvs.getString(chiave, predefinito);
}

void scrivi(const char* chiave, const String& valore) { nvs.putString(chiave, valore); }

bool id_valido(const String& id) {
  if (id.length() < 3 || id.length() > 63) return false;
  for (size_t i = 0; i < id.length(); ++i) {
    const char c = id[i];
    const bool ammesso = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || (c == '-' && i > 0);
    if (!ammesso) return false;
  }
  return id != "limen-ingestore" && id != "limen-salute";
}

String csr(const String& id) {
  static Caso caso;  // grande per lo stack di loop(), e basta seminarlo una volta
  if (!caso.pronto) {
    Serial.println("errore: generatore casuale non inizializzato");
    return "";
  }
  mbedtls_pk_context pk;
  mbedtls_pk_init(&pk);
  // L'ESP32 dà numeri davvero casuali solo con la radio accesa: la chiave si
  // crea dopo aver acceso il Wi-Fi (vedi main.cpp).
  if (!carica_chiave(&pk, caso)) {
    if (!leggi("chiave").isEmpty()) {
      // Rigenerarla invaliderebbe il certificato già firmato.
      Serial.println("errore: la chiave salvata non si legge; non ne creo un'altra");
      mbedtls_pk_free(&pk);
      return "";
    }
    mbedtls_pk_free(&pk);
    mbedtls_pk_init(&pk);
    Serial.println("creo la chiave P-256 del dispositivo…");
    if (!crea_chiave(&pk, caso)) {
      Serial.println("errore: chiave non creata");
      mbedtls_pk_free(&pk);
      return "";
    }
  }

  mbedtls_x509write_csr richiesta;
  mbedtls_x509write_csr_init(&richiesta);
  mbedtls_x509write_csr_set_md_alg(&richiesta, MBEDTLS_MD_SHA256);
  mbedtls_x509write_csr_set_key(&richiesta, &pk);
  String soggetto = "CN=" + id;
  String uscita;
  static unsigned char pem[1024];
  if (mbedtls_x509write_csr_set_subject_name(&richiesta, soggetto.c_str()) == 0 &&
      mbedtls_x509write_csr_pem(&richiesta, pem, sizeof(pem), mbedtls_ctr_drbg_random,
                                &caso.drbg) == 0) {
    uscita = reinterpret_cast<char*>(pem);
  } else {
    Serial.println("errore: CSR non scritta");
  }
  mbedtls_x509write_csr_free(&richiesta);
  mbedtls_pk_free(&pk);
  return uscita;
}

bool salva_certificato(const String& pem) {
  static Caso caso;
  mbedtls_x509_crt crt;
  mbedtls_x509_crt_init(&crt);
  mbedtls_pk_context pk;
  mbedtls_pk_init(&pk);
  bool ok = mbedtls_x509_crt_parse(&crt, reinterpret_cast<const unsigned char*>(pem.c_str()),
                                   pem.length() + 1) == 0;
  if (!ok) {
    Serial.println("errore: non è un certificato PEM");
  } else if (!caso.pronto || !carica_chiave(&pk, caso)) {
    Serial.println("errore: manca la chiave, genera prima la CSR con `csr`");
    ok = false;
  } else if (cn(crt) != leggi("id")) {
    Serial.printf("errore: il certificato è per '%s', il dispositivo è '%s'\n", cn(crt).c_str(),
                  leggi("id").c_str());
    ok = false;
  } else if (
#if MBEDTLS_VERSION_MAJOR >= 3
      mbedtls_pk_check_pair(&crt.pk, &pk, mbedtls_ctr_drbg_random, &caso.drbg) != 0
#else
      mbedtls_pk_check_pair(&crt.pk, &pk) != 0
#endif
  ) {
    Serial.println("errore: il certificato non è di questa chiave");
    ok = false;
  }
  if (ok) scrivi("cert", pem);
  mbedtls_pk_free(&pk);
  mbedtls_x509_crt_free(&crt);
  return ok;
}

bool salva_ca(const String& pem) {
  mbedtls_x509_crt crt;
  mbedtls_x509_crt_init(&crt);
  const bool ok = mbedtls_x509_crt_parse(&crt, reinterpret_cast<const unsigned char*>(pem.c_str()),
                                         pem.length() + 1) == 0;
  mbedtls_x509_crt_free(&crt);
  if (ok) {
    scrivi("ca", pem);
  } else {
    Serial.println("errore: non è un certificato PEM");
  }
  return ok;
}

bool pronta() {
  const String id = leggi("id");
  if (leggi("ssid").isEmpty() || !id_valido(id) || leggi("chiave").isEmpty() ||
      leggi("ca").isEmpty()) {
    return false;
  }
  // Con un certificato per un altro id il broker scarterebbe ogni messaggio,
  // confermandolo comunque: la coda si svuoterebbe nel vuoto.
  const String pem = leggi("cert");
  mbedtls_x509_crt crt;
  mbedtls_x509_crt_init(&crt);
  const bool ok = !pem.isEmpty() &&
                  mbedtls_x509_crt_parse(&crt, reinterpret_cast<const unsigned char*>(pem.c_str()),
                                         pem.length() + 1) == 0 &&
                  cn(crt) == id;
  mbedtls_x509_crt_free(&crt);
  return ok;
}

void allinea_sequenza(time_t adesso) {
  // Una flash cancellata o una NVS rovinata riporterebbe la sequenza a zero,
  // e Limen scarterebbe ogni messaggio come replay per settimane. L'orologio
  // le dà un pavimento che cresce di 256 al secondo: più di quanto il
  // dispositivo possa mai consumare, quindi resta monotona fra i riavvii.
  const uint64_t pavimento = static_cast<uint64_t>(adesso) << 8;
  if (sequenza < pavimento) {
    sequenza = pavimento;
    prenota(sequenza + BLOCCO);
  }
}

uint64_t prossima_sequenza() {
  if (sequenza + 1 >= prenotata) prenota(prenotata + BLOCCO);
  return ++sequenza;
}

}  // namespace identita
