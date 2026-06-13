# n8n Recovery — инструкция по восстановлению

> Используй этот файл когда workflow пропали, n8n не отвечает или обновление сломало установку.

---

## Быстрая диагностика (первые 2 минуты)

```bash
cd ~/n8n-automation

# Состояние контейнеров
docker compose -f docker-compose.prod.yml ps

# Логи n8n (последние 50 строк)
docker compose -f docker-compose.prod.yml logs --tail 50 n8n

# Health check
curl -s http://localhost:5678/healthz || echo "n8n не отвечает"
```

| Симптом | Причина | Раздел |
|---------|---------|--------|
| Workflow пропали из UI | Обновление сломало DB / не та база | → [Сценарий 1](#сценарий-1-workflow-пропали-после-обновления) |
| n8n не запускается | Ошибка миграции / bad image | → [Сценарий 2](#сценарий-2-n8n-не-запускается) |
| Контейнер падает в loop | Ошибка конфига / занят порт | → [Сценарий 3](#сценарий-3-контейнер-падает-crash-loop) |
| Credentials не работают | Сменился `N8N_ENCRYPTION_KEY` | → [Сценарий 4](#сценарий-4-credentials-перестали-работать) |

---

## Сценарий 1: Workflow пропали после обновления

Самый частый случай. n8n запущен, но список workflow пустой или недоступен.

### Шаг 1: Найти последний бэкап

```bash
ls -lt /home/kirill/backups/workflows-*.json | head -5
```

### Шаг 2: Восстановить workflow через n8n UI

Самый простой способ — импорт через интерфейс:

1. Открыть `https://YOUR_N8N_DOMAIN`
2. **Settings → Import Workflow**
3. Выбрать последний файл `/home/kirill/backups/workflows-YYYYMMDD-HHMM.json`
4. Подтвердить импорт

### Шаг 2 (альтернатива): Восстановить через API

```bash
BACKUP=$(ls -t /home/kirill/backups/workflows-*.json | head -1)
N8N_KEY=$(cat /home/kirill/.n8n-api-key)
N8N_URL="https://YOUR_N8N_DOMAIN"

echo "Восстанавливаем из: $BACKUP"

# Импортировать каждый workflow через API
python3 - << PYEOF
import json, urllib.request, sys

with open("$BACKUP") as f:
    data = json.load(f)

workflows = data.get("data", data) if isinstance(data, dict) else data

key = "$N8N_KEY"
url = "$N8N_URL"

ok, fail = 0, 0
for wf in workflows:
    payload = json.dumps({
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {})
    }).encode()
    req = urllib.request.Request(
        f"{url}/api/v1/workflows",
        data=payload,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
            print(f"[OK] {wf['name']} → id={result.get('id')}")
            ok += 1
    except Exception as e:
        print(f"[FAIL] {wf['name']}: {e}")
        fail += 1

print(f"\nИмпортировано: {ok}, ошибок: {fail}")
PYEOF
```

### Шаг 3: Переподключить credentials в UI

После импорта workflow — зайти в каждый флоу и переподключить credentials (Postgres, Gmail, Telegram и т.д.) вручную через n8n UI. Credentials не включаются в этот бэкап.

### Шаг 4: Активировать флоу

```bash
# Активировать все импортированные workflow через API
N8N_KEY=$(cat /home/kirill/.n8n-api-key)
curl -s -H "X-N8N-API-KEY: $N8N_KEY" \
  https://YOUR_N8N_DOMAIN/api/v1/workflows?limit=100 \
  | python3 -c "
import sys, json, urllib.request
data = json.load(sys.stdin)
key = open('/home/kirill/.n8n-api-key').read().strip()
for wf in data.get('data', []):
    if not wf.get('active'):
        req = urllib.request.Request(
            f'https://YOUR_N8N_DOMAIN/api/v1/workflows/{wf[\"id\"]}/activate',
            data=b'', headers={'X-N8N-API-KEY': key}, method='POST')
        try:
            urllib.request.urlopen(req)
            print(f'[activated] {wf[\"name\"]}')
        except Exception as e:
            print(f'[skip] {wf[\"name\"]}: {e}')
"
```

---

## Сценарий 2: n8n не запускается

```bash
# Посмотреть ошибку
docker compose -f docker-compose.prod.yml logs n8n | tail -30
```

### Если ошибка миграции (`migration failed` / `column does not exist`)

Откат к предыдущей версии + восстановление DB:

```bash
# 1. Остановить n8n
docker compose -f docker-compose.prod.yml stop n8n

# 2. Восстановить DB из последнего дампа
LATEST_DB=$(ls -t /home/kirill/backups/jobradar-*.sql.gz | head -1)
echo "Восстанавливаем DB из: $LATEST_DB"

docker exec -i n8n-automation-postgres-1 \
  psql -U hub -d hub -c "DROP DATABASE IF EXISTS jobradar; CREATE DATABASE jobradar;"
  
gunzip -c "$LATEST_DB" \
  | docker exec -i n8n-automation-postgres-1 psql -U hub jobradar

# 3. Откатить версию в docker-compose.prod.yml на рабочую
# Текущая стабильная: n8nio/n8n:2.23.4
sed -i "s|image: n8nio/n8n:.*|image: n8nio/n8n:2.23.4|" docker-compose.prod.yml

# 4. Запустить
docker compose -f docker-compose.prod.yml up -d n8n

# 5. Проверить
sleep 10 && curl -s http://localhost:5678/healthz
```

### Если ошибка `ENCRYPTION_KEY` или `cannot decrypt`

```bash
# Проверить что ключ тот же что был при создании credentials
grep N8N_ENCRYPTION_KEY ~/n8n-automation/.env
cat /home/kirill/backups/env-$(ls -t /home/kirill/backups/env-*.bak | head -1 | xargs basename).bak | grep ENCRYPTION
```

Если ключи разные — восстановить `.env` из бэкапа:

```bash
LATEST_ENV=$(ls -t /home/kirill/backups/env-*.bak | head -1)
cp ~/n8n-automation/.env ~/n8n-automation/.env.broken-$(date +%Y%m%d)
cp "$LATEST_ENV" ~/n8n-automation/.env
docker compose -f docker-compose.prod.yml up -d n8n
```

---

## Сценарий 3: Контейнер падает (crash loop)

```bash
# Посмотреть что происходит при старте
docker compose -f docker-compose.prod.yml up n8n  # без -d, чтобы видеть вывод
# Ctrl+C чтобы остановить после просмотра логов

# Или:
docker compose -f docker-compose.prod.yml logs --follow n8n
```

Частые причины:
- Занят порт 5678 → `lsof -i :5678`
- Нет места на диске → `df -h`
- Postgres не успел подняться → подождать 30 секунд, запустить снова

---

## Сценарий 4: Credentials перестали работать

Credentials в n8n зашифрованы ключом `N8N_ENCRYPTION_KEY`. Если ключ сменился — credentials нечитаемы.

```bash
# Проверить текущий ключ
grep N8N_ENCRYPTION_KEY ~/n8n-automation/.env

# Найти бэкап .env с оригинальным ключом
ls -lt /home/kirill/backups/env-*.bak | head -5
grep N8N_ENCRYPTION_KEY /home/kirill/backups/env-YYYYMMDD-HHMM.bak
```

Если нашли старый ключ — восстановить `.env` (см. Сценарий 2).
Если ключ потерян безвозвратно — credentials нужно создать заново в n8n UI.

---

## Ручной запуск бэкапа

```bash
# Запустить немедленно (не ждать расписания)
/home/kirill/n8n-backup.sh

# Посмотреть результат
ls -lh /home/kirill/backups/ | tail -10
```

Автоматически запускается в **04:00, 10:00, 20:00** по UTC (cron).

---

## Что есть в бэкапах

| Файл | Содержимое | Нужен для |
|------|-----------|-----------|
| `workflows-YYYYMMDD-HHMM.json` | Все workflow (структура, ноды, connections) | Восстановить флоу |
| `jobradar-YYYYMMDD-HHMM.sql.gz` | Postgres dump (jobs, companies, events) | Восстановить данные |
| `env-YYYYMMDD-HHMM.bak` | `.env` файл с `N8N_ENCRYPTION_KEY` | Восстановить credentials |

> **Credentials** (`postgres`, `gmail`, `telegram` и т.д.) НЕ входят в workflow JSON.
> После восстановления workflow их нужно переподключить вручную в n8n UI.
> Они хранятся в Postgres таблице `credentials_entity` — покрыты `jobradar-*.sql.gz`.

---

## Проверка после восстановления

```bash
# 1. n8n отвечает
curl -sf http://localhost:5678/healthz && echo "OK"

# 2. Количество workflow в API
N8N_KEY=$(cat /home/kirill/.n8n-api-key)
curl -sf -H "X-N8N-API-KEY: $N8N_KEY" \
  https://YOUR_N8N_DOMAIN/api/v1/workflows?limit=1 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Workflow в n8n: {len(d.get(\"data\",d))}')"

# 3. Запустить критичный флоу вручную в UI и убедиться что отработал
```

---

## Контакты / ссылки

- n8n UI: `https://YOUR_N8N_DOMAIN`
- Бэкапы: `/home/kirill/backups/`
- VPS shell: Hetzner Console (SSH заблокирован с Windows)
- Docker stack: `~/n8n-automation/docker-compose.prod.yml`
