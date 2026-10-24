#!/usr/bin/env bash
# CA privata dei sensori (#260, epic #247).
#
#   sensori_ca.sh init                      CA, server, ingestore, healthcheck, ACL (idempotente)
#   sensori_ca.sh firma <csr> [giorni]      firma la CSR di un dispositivo; il CN e' il suo id
#                                           (rifiuta un id con un certificato valido)
#   sensori_ca.sh revoca <id>               revoca i certificati validi di quell'id e rigenera la CRL
#   sensori_ca.sh crl                       rigenera la CRL (prima che scada: vedi sotto)
#   sensori_ca.sh stato                     scadenza di CA, server e CRL
#   sensori_ca.sh ca                        il certificato della CA (pubblico)
#
# Tutto vive in $LIMEN_SENSORI_DIR, fuori dal repo:
#   ca/       chiave della CA e database di openssl  — non esce mai da qui
#   broker/   cio' che il broker monta in sola lettura (ca.crt, server.*, crl.pem, salute.*, acl)
#   client/   il certificato dell'ingestore
#   data/     la persistenza di Mosquitto
#
# Chiavi EC P-256: e' l'unica curva del secure element ATECC608, e un ESP32
# la gestisce in hardware. Il dispositivo genera la sua chiave e manda solo la
# CSR: la chiave privata non lascia mai il dispositivo.
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
HOST="${LIMEN_SENSORI_HOST:-limen.agentengineering.it}"
CA="$DIR/ca"
BROKER="$DIR/broker"
CLIENT="$DIR/client"
# Una CRL scaduta fa rifiutare a Mosquitto TUTTI i client. Si firma per dieci
# anni e si rigenera a ogni revoca (`revoca` chiama `crl`): così non scade da
# sola e non serve un cron mensile sull'host (#306). La scadenza breve serve
# a chi riceve la CRL da terzi; qui l'unico che la legge è il nostro broker, e
# rinnovarla da un container vorrebbe dire metterci la chiave della CA.
# `stato` avvisa ancora sotto i 30 giorni (una CRL firmata prima della #306).
CRL_GIORNI=3650
RISERVATI="limen-ingestore limen-salute"

log() { echo "sensori-ca: $*" >&2; }

conf() {
  cat <<EOF
[ ca ]
default_ca = sensori

[ sensori ]
dir              = $CA
database         = $CA/index.txt
new_certs_dir    = $CA/emessi
certificate      = $CA/ca.crt
private_key      = $CA/ca.key
serial           = $CA/serial
crlnumber        = $CA/crlnumber
default_md       = sha256
default_crl_days = $CRL_GIORNI
policy           = solo_cn
# Un id revocato si puo' riemettere (dispositivo sostituito).
unique_subject   = no
copy_extensions  = none

[ solo_cn ]
commonName = supplied

[ dispositivo ]
basicConstraints       = critical, CA:FALSE
keyUsage               = critical, digitalSignature
extendedKeyUsage       = clientAuth
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid

[ server ]
basicConstraints       = critical, CA:FALSE
keyUsage               = critical, digitalSignature
extendedKeyUsage       = serverAuth
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid
subjectAltName         = DNS:$HOST, DNS:mosquitto-sensori, DNS:limen-mosquitto-sensori, DNS:localhost, IP:127.0.0.1

[ radice ]
basicConstraints       = critical, CA:TRUE, pathlen:0
keyUsage               = critical, keyCertSign, cRLSign
subjectKeyIdentifier   = hash
EOF
}

openssl_ca() { openssl ca -batch -config <(conf) "$@"; }

valida_id() {
  # Minuscole, cifre e trattini: niente + # / che spezzerebbero l'ACL a
  # pattern, niente maiuscole che renderebbero ambigui due id.
  [[ "$1" =~ ^[a-z0-9][a-z0-9-]{2,62}$ ]] || {
    log "id non valido: '$1' (minuscole, cifre, trattini; 3-63 caratteri)"
    exit 2
  }
}

emetti_locale() {
  # Chiave e certificato generati qui: solo per le identita' di Limen
  # (server, ingestore, healthcheck), mai per un dispositivo.
  local cn=$1 estensione=$2 chiave=$3 cert=$4 giorni=$5
  if [ -s "$cert" ] && openssl x509 -in "$cert" -noout -checkend $((30 * 86400)) >/dev/null; then
    return
  fi
  openssl ecparam -name prime256v1 -genkey -noout -out "$chiave"
  chmod 600 "$chiave"
  openssl_ca -in <(openssl req -new -key "$chiave" -subj "/CN=$cn") \
    -extensions "$estensione" -days "$giorni" -notext -out "$cert" 2>/dev/null
  log "emesso $cn"
}

cmd_init() {
  mkdir -p "$CA/emessi" "$BROKER" "$CLIENT" "$DIR/data"
  chmod 700 "$DIR" "$CA"
  [ -f "$CA/index.txt" ] || : >"$CA/index.txt"
  [ -f "$CA/serial" ] || openssl rand -hex 16 >"$CA/serial"
  [ -f "$CA/crlnumber" ] || echo 1000 >"$CA/crlnumber"

  if [ ! -s "$CA/ca.key" ]; then
    openssl ecparam -name prime256v1 -genkey -noout -out "$CA/ca.key"
    chmod 600 "$CA/ca.key"
    openssl req -new -x509 -key "$CA/ca.key" -days 3650 -subj "/CN=Limen CA sensori" \
      -config <(conf) -extensions radice -out "$CA/ca.crt"
    log "creata la CA"
  fi
  cp "$CA/ca.crt" "$BROKER/ca.crt"
  install -m 600 "$RADICE/infra/mosquitto-sensori/acl" "$BROKER/acl"

  emetti_locale "$HOST" server "$BROKER/server.key" "$BROKER/server.crt" 825
  emetti_locale limen-salute dispositivo "$BROKER/salute.key" "$BROKER/salute.crt" 825
  emetti_locale limen-ingestore dispositivo "$CLIENT/ingestore.key" "$CLIENT/ingestore.crt" 825
  # Il worker la legge con l'uid suo e il gruppo di questa directory
  # (docker-compose.sensori-worker.yml, `group_add`).
  chmod 640 "$CLIENT/ingestore.key"
  cp "$CA/ca.crt" "$CLIENT/ca.crt"
  [ -s "$BROKER/crl.pem" ] || cmd_crl
}

cmd_firma() {
  local csr=${1:?serve il percorso della CSR} giorni=${2:-730} cn
  cn=$(openssl req -in "$csr" -noout -subject -nameopt multiline | awk -F' = ' '/commonName/{print $2}')
  valida_id "$cn"
  for r in $RISERVATI; do
    [ "$cn" != "$r" ] || { log "'$cn' e' un id riservato a Limen"; exit 2; }
  done
  openssl req -in "$csr" -noout -verify 2>/dev/null || { log "firma della CSR non valida"; exit 2; }
  # Due certificati validi per lo stesso id sono due dispositivi che parlano
  # come uno: quello di un cittadino potrebbe ereditare il livello di uno
  # istituzionale. Per un rinnovo voluto: SENSORI_RINNOVO=1.
  if [ "${SENSORI_RINNOVO:-0}" != 1 ] &&
    awk -F'\t' -v s="/CN=$cn" '$1 == "V" && $6 == s {f=1} END {exit !f}' "$CA/index.txt"; then
    log "'$cn' ha gia' un certificato valido (rinnovo: SENSORI_RINNOVO=1)"
    exit 2
  fi
  openssl_ca -in "$csr" -extensions dispositivo -days "$giorni" -notext 2>/dev/null
}

cmd_revoca() {
  local id=${1:?serve l id del dispositivo} n=0 serial
  valida_id "$id"
  # index.txt: stato, scadenza, revoca, seriale, file, soggetto. Con awk e non
  # con `read`: la colonna della revoca e' vuota, e un IFS di tabulazioni
  # fonde i campi vuoti — il seriale finirebbe nella colonna sbagliata.
  for serial in $(awk -F'\t' -v s="/CN=$id" '$1 == "V" && $6 == s {print $4}' "$CA/index.txt"); do
    openssl_ca -revoke "$CA/emessi/$serial.pem" 2>/dev/null
    n=$((n + 1))
  done
  log "revocati $n certificati di $id"
  cmd_crl
}

cmd_crl() {
  openssl_ca -gencrl -out "$BROKER/crl.pem" 2>/dev/null
  # Mosquitto rilegge certificati e CRL al SIGHUP, senza chiudere le
  # connessioni degli altri dispositivi.
  if docker inspect limen-mosquitto-sensori >/dev/null 2>&1; then
    docker kill -s HUP limen-mosquitto-sensori >/dev/null
    log "CRL rigenerata, broker ricaricato"
  else
    log "CRL rigenerata"
  fi
}

cmd_stato() {
  local fine rc=0
  for f in "$CA/ca.crt" "$BROKER/server.crt" "$CLIENT/ingestore.crt"; do
    echo "$(basename "$f"): scade $(openssl x509 -in "$f" -noout -enddate | cut -d= -f2)"
  done
  fine=$(openssl crl -in "$BROKER/crl.pem" -noout -nextupdate | cut -d= -f2)
  echo "crl.pem: prossimo aggiornamento $fine"
  if (($(date -d "$fine" +%s) - $(date +%s) < 30 * 86400)); then
    echo "ATTENZIONE: la CRL scade fra meno di 30 giorni — make sensori-crl" >&2
    rc=1
  fi
  return $rc
}

case "${1:-}" in
  init) cmd_init ;;
  firma) shift; cmd_firma "$@" ;;
  revoca) shift; cmd_revoca "$@" ;;
  crl) cmd_crl ;;
  stato) cmd_stato ;;
  ca) cat "$CA/ca.crt" ;;
  *) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
esac
