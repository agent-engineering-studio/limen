#!/usr/bin/env bash
# Attiva limen.agentengineering.it su questo server: certificato Let's Encrypt
# e vhost nginx. Da lanciare con sudo, DOPO che il record DNS
#   limen.agentengineering.it  CNAME  office-gdc.w3pro.it.
# risolve. CNAME e non A: l'IP della fibra e' dinamico, e office-gdc.w3pro.it
# lo segue gia' con il DNS dinamico. Rilanciabile: se il certificato c'e'
# gia' non lo richiede.
set -euo pipefail

DOMINIO=limen.agentengineering.it
QUI="$(cd "$(dirname "$0")" && pwd)"
VHOST=/etc/nginx/sites-available/$DOMINIO

ip_dns=$(getent hosts "$DOMINIO" | awk '{print $1}' | head -1 || true)
if [ -z "$ip_dns" ]; then
  echo "Il DNS di $DOMINIO non risolve ancora: crea il CNAME verso office-gdc.w3pro.it e riprova." >&2
  exit 1
fi
echo "DNS: $DOMINIO -> $ip_dns"

if [ ! -f "/etc/letsencrypt/live/$DOMINIO/fullchain.pem" ]; then
  # Prima solo il blocco :80, che serve la sfida ACME da /var/www/html: il
  # blocco :443 punta a un certificato che ancora non esiste, e nginx
  # rifiuterebbe l'intera configurazione.
  sed '/^server {$/,$!d' "$QUI/$DOMINIO" | awk 'BEGIN{n=0} /^server \{$/{n++} n==1' > "$VHOST"
  ln -sfn "$VHOST" "/etc/nginx/sites-enabled/$DOMINIO"
  nginx -t && systemctl reload nginx
  certbot certonly --webroot -w /var/www/html -d "$DOMINIO" --non-interactive --agree-tos \
    --register-unsafely-without-email
fi

cp "$QUI/$DOMINIO" "$VHOST"
ln -sfn "$VHOST" "/etc/nginx/sites-enabled/$DOMINIO"
nginx -t && systemctl reload nginx
curl -s -o /dev/null -w "https://$DOMINIO/ -> %{http_code}\n" "https://$DOMINIO/"
