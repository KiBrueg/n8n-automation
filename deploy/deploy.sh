#!/usr/bin/env bash
# ============================================================
# Деплой/обновление прод-стека на VPS.
# Запуск на сервере из корня проекта:  ./deploy/deploy.sh
#
# Шаги:
#   1. git pull (свежий код/конфиги)
#   2. docker compose pull (свежий образ gateway из GHCR + образы сервисов)
#   3. docker compose up -d (применить, пересоздать изменившееся)
#   4. prune старых образов (освободить диск)
#   5. показать статус
#
# Идемпотентно: можно гонять сколько угодно раз.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml"

if [[ ! -f .env ]]; then
	echo "ОШИБКА: нет .env. Сделай: cp .env.example .env и заполни." >&2
	exit 1
fi

echo "==> 1/5 git pull"
git pull --ff-only

echo "==> 2/5 docker compose pull"
$COMPOSE pull

echo "==> 3/5 docker compose up -d"
$COMPOSE up -d --remove-orphans

echo "==> 4/5 чистка неиспользуемых образов"
docker image prune -f

echo "==> 5/5 статус"
$COMPOSE ps
echo
echo "Готово. Логи: $COMPOSE logs -f --tail=50 <service>"
