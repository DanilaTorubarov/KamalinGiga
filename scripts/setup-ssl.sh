#!/usr/bin/env bash
set -euo pipefail

DOMAIN="physgraph.tech"
EMAIL="admin@${DOMAIN}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "${DIR}/certbot/www" "${DIR}/certbot/conf"
CERT_DIR="${DIR}/certbot/conf/live/${DOMAIN}"

# Если сертификат уже есть — просто перезапускаем
if [ -f "${CERT_DIR}/fullchain.pem" ]; then
  echo "→ Сертификат уже есть, перезапускаем nginx…"
  docker compose -f "${DIR}/docker-compose.prod.yml" up -d nginx
  echo "✓ Готово"
  exit 0
fi

# Создаём временный самоподписанный сертификат, чтобы nginx запустился
echo "→ Создаём временный сертификат для первого запуска nginx…"
mkdir -p "${CERT_DIR}"
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "${CERT_DIR}/privkey.pem" \
  -out "${CERT_DIR}/fullchain.pem" \
  -days 1 \
  -subj "/CN=${DOMAIN}" 2>/dev/null

echo "→ Запускаем nginx…"
docker compose -f "${DIR}/docker-compose.prod.yml" up -d nginx

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

echo "→ Перезапускаем nginx с настоящим сертификатом…"
docker compose -f "${DIR}/docker-compose.prod.yml" exec nginx nginx -s reload

echo "✓ HTTPS включён для ${DOMAIN}"

