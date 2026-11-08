#!/usr/bin/env bash
# Attiva Limen sull'nginx di questo server (#517): vhost dal modello
# infra/nginx/limen.conf.template, riempito dal .env, e certificato Let's
# Encrypt. Da lanciare con sudo dalla radice del repo, DOPO che il DNS
# dell'host di PUBBLICO__URL punta a questo server. Rilanciabile: se il
# certificato c'e' gia' non lo richiede.
#
#   sudo infra/nginx/attiva-limen.sh
#
# Senza PUBBLICO__URL si ferma: il vhost non avrebbe un nome.
set -euo pipefail

QUI="$(cd "$(dirname "$0")" && pwd)"
RADICE="$(cd "$QUI/../.." && pwd)"
valore() {  # valore NOME: dall'ambiente, altrimenti dal .env
  if [ -n "${!1:-}" ]; then
    printf '%s' "${!1}"
  else
    { grep -s "^$1=" "$RADICE/.env" || true; } | tail -n 1 | cut -d= -f2- | tr -d "\"'"
  fi
}

url="$(valore PUBBLICO__URL)"
if [ -z "$url" ]; then
  echo "Manca PUBBLICO__URL nel .env (es. https://limen.example.org): e' il nome del vhost." >&2
  exit 2
fi
DOMINIO="${url#*://}"
DOMINIO="${DOMINIO%%/*}"
DOMINIO="$(printf '%s' "${DOMINIO%%:*}" | tr '[:upper:]' '[:lower:]')"
TILES_DIR="$(valore LIMEN_DEM_TILES_DIR)"
TILES_DIR="${TILES_DIR:-/srv/data/limen-tiles}"
case "$TILES_DIR" in
  /*) ;;
  *) echo "LIMEN_DEM_TILES_DIR deve essere assoluta per nginx: $TILES_DIR" >&2; exit 2 ;;
esac
VHOST=/etc/nginx/sites-available/$DOMINIO

ip_dns=$(getent hosts "$DOMINIO" | awk '{print $1}' | head -1 || true)
if [ -z "$ip_dns" ]; then
  echo "Il DNS di $DOMINIO non risolve ancora: crea il record verso questo server e riprova." >&2
  exit 1
fi
echo "DNS: $DOMINIO -> $ip_dns"

# Le intestazioni verso i container. X-Real-IP lo scrive nginx: contributi e
# registrazione dei sensori fanno il limite per IP su quello.
if [ ! -f /etc/nginx/snippets/limen-proxy.conf ]; then
  install -d /etc/nginx/snippets
  cat >/etc/nginx/snippets/limen-proxy.conf <<'FINE'
proxy_http_version 1.1;
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Upgrade           $http_upgrade;
proxy_set_header Connection        $connection_upgrade;
FINE
fi
# La map si definisce una volta sola in tutto nginx: una seconda copia
# farebbe fallire `nginx -t`.
if ! grep -rqs 'map[[:space:]]\+\$http_upgrade[[:space:]]\+\$connection_upgrade' /etc/nginx; then
  cat >/etc/nginx/conf.d/limen-upgrade.conf <<'FINE'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
FINE
fi

riempi() {
  sed -e "s|@DOMINIO@|$DOMINIO|g" -e "s|@TILES_DIR@|${TILES_DIR%/}|g" "$QUI/limen.conf.template"
}

if [ ! -f "/etc/letsencrypt/live/$DOMINIO/fullchain.pem" ]; then
  # Prima solo il blocco :80, che serve la sfida ACME da /var/www/html: il
  # blocco :443 punta a un certificato che ancora non esiste, e nginx
  # rifiuterebbe l'intera configurazione.
  riempi | sed '/^server {$/,$!d' | awk 'BEGIN{n=0} /^server \{$/{n++} n==1' >"$VHOST"
  ln -sfn "$VHOST" "/etc/nginx/sites-enabled/$DOMINIO"
  nginx -t && systemctl reload nginx
  certbot certonly --webroot -w /var/www/html -d "$DOMINIO" --non-interactive --agree-tos \
    --register-unsafely-without-email
fi

# La cartella delle tile del rilievo, scritta da `limen dem-tiles` come
# utente normale (LIMEN_DEM_TILES_DIR) e letta da nginx.
install -d -m 755 -o "${SUDO_USER:-root}" "$TILES_DIR"
riempi >"$VHOST"
ln -sfn "$VHOST" "/etc/nginx/sites-enabled/$DOMINIO"
nginx -t && systemctl reload nginx
curl -s -o /dev/null -w "https://$DOMINIO/ -> %{http_code}\n" "https://$DOMINIO/"
