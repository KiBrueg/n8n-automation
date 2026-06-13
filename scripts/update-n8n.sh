#!/bin/bash
# =============================================================
# update-n8n.sh — безопасное обновление n8n на VPS
# Запуск: cd ~/n8n-automation && bash scripts/update-n8n.sh 2.24.0
# =============================================================
set -e

TARGET_VERSION="${1:-}"
COMPOSE_FILE="docker-compose.prod.yml"
BACKUP_DIR=~/backups/pre-update-$(date +%Y-%m-%d_%H-%M)

if [ -z "$TARGET_VERSION" ]; then
  echo "Использование: $0 <новая_версия>"
  echo "Пример: $0 2.24.0"
  echo ""
  echo "Текущая версия:"
  docker compose -f "$COMPOSE_FILE" exec n8n n8n --version 2>/dev/null || echo "(n8n не запущен)"
  exit 1
fi

echo "========================================"
echo " Обновление n8n → $TARGET_VERSION"
echo "========================================"

# --- Шаг 1: Бэкап ---
echo "[1/6] Создаём бэкап в $BACKUP_DIR ..."
mkdir -p "$BACKUP_DIR"
cp .env "$BACKUP_DIR/.env.bak"
cp "$COMPOSE_FILE" "$BACKUP_DIR/docker-compose.prod.yml.bak"
docker exec n8n-automation-postgres-1 pg_dump -U hub jobradar \
  | gzip > "$BACKUP_DIR/jobradar_db.sql.gz"
echo "    Бэкап: OK ($(du -sh "$BACKUP_DIR" | cut -f1))"

# --- Шаг 2: Текущая версия ---
echo "[2/6] Текущая версия n8n:"
docker compose -f "$COMPOSE_FILE" exec n8n n8n --version 2>/dev/null || echo "    (не удалось получить)"

# --- Шаг 3: Обновляем тег в docker-compose.prod.yml ---
echo "[3/6] Обновляем тег n8n → $TARGET_VERSION ..."
sed -i "s|image: n8nio/n8n:.*|image: n8nio/n8n:$TARGET_VERSION|" "$COMPOSE_FILE"
grep "image: n8nio/n8n" "$COMPOSE_FILE"

# --- Шаг 4: Pull новой версии ---
echo "[4/6] docker compose pull n8n ..."
docker compose -f "$COMPOSE_FILE" pull n8n

# --- Шаг 5: Перезапуск (stop, НЕ down — volumes сохраняются) ---
echo "[5/6] Перезапуск (stop → up) ..."
docker compose -f "$COMPOSE_FILE" stop n8n
docker compose -f "$COMPOSE_FILE" up -d n8n

# --- Шаг 6: Верификация ---
echo "[6/6] Верификация ..."
sleep 10
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5678/healthz 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ]; then
  echo "    Health check: OK (200)"
else
  echo "    ВНИМАНИЕ: health check вернул $HTTP — проверь логи:"
  echo "    docker compose -f $COMPOSE_FILE logs --tail 30 n8n"
  exit 1
fi

ACTUAL=$(docker compose -f "$COMPOSE_FILE" exec n8n n8n --version 2>/dev/null | tr -d '\r\n')
echo "    Версия после обновления: $ACTUAL"
echo ""
echo "========================================"
echo " Обновление завершено успешно."
echo " Бэкап сохранён в: $BACKUP_DIR"
echo ""
echo " Следующий шаг: вручную проверить 3-5 критических флоу в n8n UI"
echo "========================================"
