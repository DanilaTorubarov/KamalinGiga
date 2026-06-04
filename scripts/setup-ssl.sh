#!/usr/bin/env bash
set -euo pipefail

DOMAIN="physgraph.tech"
EMAIL="admin@${DOMAIN}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "${DIR}/certbot/www" "${DIR}/certbot/conf"
CERT_DIR="${DIR}/certbot/conf/live/${DOMAIN}"
BOOT_CONF="${DIR}/nginx/prod-bootstrap.conf"
REAL_CONF="${DIR}/nginx/prod.conf"
ACTIVE_CONF="${DIR}/nginx/prod-active.conf"

# Если сертификат уже есть — запускаем сразу с HTTPS
if [ -f "${CERT_DIR}/fullchain.pem" ]; then
  echo "→ Сертификат уже есть, запускаем nginx с HTTPS…"
  cp "${REAL_CONF}" "${ACTIVE_CONF}"
  docker compose -f "${DIR}/docker-compose.prod.yml" up -d --build nginx
  echo "✓ Готово"
  exit 0
fi

# Шаг 1: bootstrap config (только HTTP + ACME)
echo "→ Запускаем nginx в bootstrap-режиме (HTTP, для Certbot)…"
cp "${BOOT_CONF}" "${ACTIVE_CONF}"
docker compose -f "${DIR}/docker-compose.prod.yml" up -d --build nginx

# Шаг 2: получаем сертификат
echo "→ Запрашиваем сертификат Let's Encrypt для ${DOMAIN}…"
docker run --rm \
  -v "${DIR}/certbot/www:/var/www/certbot:rw" \
  -v "${DIR}/certbot/conf:/etc/letsencrypt:rw" \
  certbot/certbot certonly --webroot \
    -w /var/www/certbot \
    -d "${DOMAIN}" \
    --non-interactive \
    --agree-tos \
    --email "${EMAIL}"

# Шаг 3: переключаем на HTTPS
echo "→ Переключаем nginx на HTTPS…"
cp "${REAL_CONF}" "${ACTIVE_CONF}"
docker compose -f "${DIR}/docker-compose.prod.yml" exec nginx nginx -s reload

echo "✓ HTTPS включён для ${DOMAIN}"

