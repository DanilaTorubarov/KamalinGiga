#!/usr/bin/env bash
set -euo pipefail

DOMAIN="physgraph.tech"
DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "→ Обновляем сертификат Let's Encrypt для ${DOMAIN}…"

docker run --rm \
  -v "${DIR}/certbot/www:/var/www/certbot:rw" \
  -v "${DIR}/certbot/conf:/etc/letsencrypt:rw" \
  certbot/certbot renew --webroot -w /var/www/certbot --non-interactive

echo "→ Перезагружаем nginx…"
docker compose -f "${DIR}/docker-compose.prod.yml" exec nginx nginx -s reload

echo "✓ Обновление завершено"
