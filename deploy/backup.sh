#!/usr/bin/env bash
# ============================================================
# Бэкап Postgres из контейнера + ротация.
# Запуск вручную:   ./deploy/backup.sh
# Через cron (ежедневно в 03:30) — см. строку ниже:
#   30 3 * * * cd /home/<user>/n8n-automation && ./deploy/backup.sh >> /var/log/hub-backup.log 2>&1
#
# Дамп: backups/postgres/hub-YYYYmmdd-HHMMSS.sql.gz
# Хранится RETENTION_DAYS дней, старше — удаляется.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."   # корень проекта

COMPOSE="docker compose -f docker-compose.prod.yml"
BACKUP_DIR="backups/postgres"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TS="$(date +%Y%m%d-%H%M%S)"

# подхватываем POSTGRES_* из .env
set -a; [[ -f .env ]] && . ./.env; set +a
: "${POSTGRES_USER:?POSTGRES_USER не задан в .env}"
: "${POSTGRES_DB:?POSTGRES_DB не задан в .env}"

mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/hub-$TS.sql.gz"

echo "==> Бэкап БД $POSTGRES_DB → $OUT"
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip -9 > "$OUT"

# проверка, что дамп не пустой
if [[ ! -s "$OUT" ]]; then
	echo "ОШИБКА: дамп пустой, удаляю $OUT" >&2
	rm -f "$OUT"
	exit 1
fi

echo "==> Ротация: удаляю дампы старше ${RETENTION_DAYS} дней"
find "$BACKUP_DIR" -name 'hub-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "==> Готово. Текущие бэкапы:"
ls -lh "$BACKUP_DIR" | tail -n 5

# Восстановление (вручную):
#   gunzip -c backups/postgres/hub-XXXX.sql.gz | \
#     docker compose -f docker-compose.prod.yml exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
