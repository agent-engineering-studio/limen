#!/usr/bin/env bash
# Verifica il broker dei sensori (#260) dal lato di chi lo attacca: non basta
# che il dispositivo buono entri, deve restare fuori tutto il resto.
#
#   1. anonimo, senza certificato             → rifiutato
#   2. certificato di una CA estranea         → rifiutato
#   3. dispositivo valido sul proprio topic   → consegnato all'ingestore
#   4. dispositivo valido sul topic di un altro → non consegnato (ACL)
#   5. dispositivo revocato                   → rifiutato
#   6. la CRL non scade entro 30 giorni
#
# I dispositivi di prova valgono un giorno e quello revocato resta revocato:
# rilanciare il check non lascia identita' valide in giro.
set -euo pipefail

# `make` non esporta il .env: se le variabili non sono nell'ambiente, le si
# legge da li' (solo le LIMEN_SENSORI_* e LIMEN_MQTT_SENSORI_*).
RADICE="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$RADICE/.env" ]; then
  while IFS='=' read -r k v; do
    [ -z "${!k:-}" ] && export "$k=$v"
  done < <(grep -E '^(LIMEN_SENSORI_|LIMEN_MQTT_SENSORI_)[A-Z_]+=' "$RADICE/.env")
fi

DIR="${LIMEN_SENSORI_DIR:?imposta LIMEN_SENSORI_DIR (vedi .env.example)}"
PORTA="${LIMEN_MQTT_SENSORI_PORT:-18883}"
QUI="$(cd "$(dirname "$0")" && pwd)"
CA_SH="$QUI/sensori_ca.sh"
IMG=eclipse-mosquitto:2.0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fallimenti=0

ok() { echo "  ok   $*"; }
ko() { echo "  KO   $*"; fallimenti=$((fallimenti + 1)); }

# I client girano nell'immagine del broker, in rete host: stessa versione
# di Mosquitto, nessun pacchetto da installare sull'host.
mq() {
  docker run --rm --network host --user "$(id -u):$(id -g)" \
    -v "$DIR/broker/ca.crt:/ca.crt:ro" -v "$DIR/client:/client:ro" -v "$TMP:/t:ro" \
    "$IMG" "$@"
}
tls() { echo -h localhost -p "$PORTA" --cafile /ca.crt; }

dispositivo() {
  # Simula un dispositivo: chiave generata "a bordo", alla CA arriva solo la CSR.
  local id=$1
  openssl ecparam -name prime256v1 -genkey -noout -out "$TMP/$id.key"
  openssl req -new -key "$TMP/$id.key" -subj "/CN=$id" -out "$TMP/$id.csr"
  # Gli id di prova si rifirmano a ogni giro: il certificato di ieri vale
  # ancora qualche ora, e senza il rinnovo due verifiche nello stesso giorno
  # si fermavano qui.
  SENSORI_RINNOVO=1 "$CA_SH" firma "$TMP/$id.csr" 1 >"$TMP/$id.crt" 2>/dev/null
  chmod 644 "$TMP/$id.key"
}

pubblica() {
  local id=$1 topic=$2
  # shellcheck disable=SC2046
  mq mosquitto_pub $(tls) --cert "/t/$id.crt" --key "/t/$id.key" \
    -t "$topic" -m '[{"n":"rainfall","u":"mm","v":0.2}]' -q 1 >/dev/null 2>&1
}

consegnato() {
  # Una sessione persistente QoS 1 dell'ingestore: ci si iscrive (-E esce al
  # SUBACK), il dispositivo pubblica, ci si riconnette a ritirare la coda. Con
  # un sottoscrittore in ascolto e un'attesa fissa, un `docker run` lento
  # faceva pubblicare prima dell'iscrizione.
  local id=$1 topic=$2 ricevuto
  # shellcheck disable=SC2207 # tls stampa opzioni da dividere
  local ingestore=($(tls) --cert /client/ingestore.crt --key /client/ingestore.key
    -i limen-verifica-ingestore -t 'limen/v2/#' -q 1)
  mq mosquitto_sub "${ingestore[@]}" -c -E >/dev/null 2>&1 || return 1
  pubblica "$id" "$topic" || true
  ricevuto=$(mq mosquitto_sub "${ingestore[@]}" -c -C 1 -W 5 2>/dev/null || true)
  # Senza -c la sessione si chiude con la connessione: niente coda lasciata.
  mq mosquitto_sub "${ingestore[@]}" -E >/dev/null 2>&1 || true
  [ -n "$ricevuto" ]
}

echo "broker dei sensori su localhost:$PORTA"

# shellcheck disable=SC2046
if mq mosquitto_pub $(tls) -t limen/v2/anonimo/obs -m x >/dev/null 2>&1; then
  ko "1. un client senza certificato e' entrato"
else
  ok "1. senza certificato: rifiutato"
fi

openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 1 \
  -subj "/CN=Altra CA" -keyout "$TMP/altra.key" -out "$TMP/altra-ca.crt" 2>/dev/null
openssl ecparam -name prime256v1 -genkey -noout -out "$TMP/estraneo.key"
openssl req -new -key "$TMP/estraneo.key" -subj "/CN=verifica-estraneo" -out "$TMP/estraneo.csr"
openssl x509 -req -in "$TMP/estraneo.csr" -CA "$TMP/altra-ca.crt" -CAkey "$TMP/altra.key" \
  -CAcreateserial -days 1 -out "$TMP/estraneo.crt" 2>/dev/null
chmod 644 "$TMP/estraneo.key"
if pubblica estraneo limen/v2/verifica-estraneo/obs; then
  ko "2. un certificato di un'altra CA e' entrato"
else
  ok "2. CA estranea: rifiutato"
fi

dispositivo verifica-a
if consegnato verifica-a limen/v2/verifica-a/obs; then
  ok "3. dispositivo valido: l'ingestore riceve dal suo topic"
else
  ko "3. il dispositivo valido non arriva all'ingestore"
fi

if consegnato verifica-a limen/v2/verifica-b/obs; then
  ko "4. un dispositivo ha scritto sul topic di un altro"
else
  ok "4. topic di un altro: negato dall'ACL"
fi

dispositivo verifica-revocato
"$CA_SH" revoca verifica-revocato 2>/dev/null
sleep 1
if pubblica verifica-revocato limen/v2/verifica-revocato/obs; then
  ko "5. un dispositivo revocato e' entrato"
else
  ok "5. revocato: rifiutato"
fi

if "$CA_SH" stato >/dev/null 2>&1; then
  ok "6. la CRL non scade entro 30 giorni"
else
  ko "6. la CRL scade entro 30 giorni: make sensori-crl"
fi

if [ "$fallimenti" -gt 0 ]; then
  echo "$fallimenti controlli falliti" >&2
  exit 1
fi
echo "tutti i controlli passati"
