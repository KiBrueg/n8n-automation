#!/usr/bin/env bash
# Demo флагманского режима support_triage без внешних ключей (LLM_PROVIDER=stub).
# Использование:
#   GATEWAY=http://localhost:8000 API_KEY=change_me_shared_secret ./scripts/demo.sh
set -euo pipefail

GATEWAY="${GATEWAY:-http://localhost:8000}"
API_KEY="${API_KEY:-change_me_shared_secret}"

send () {
  local title="$1" text="$2"
  echo ""
  echo "=== $title ==="
  curl -s -X POST "$GATEWAY/v1/process" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d "{\"channel\":\"webform\",\"mode_hint\":\"support_triage\",
         \"user\":{\"user_id\":\"demo-user\"},
         \"message\":{\"type\":\"text\",\"text\":\"$text\"}}" | python3 -m json.tool
}

echo "Gateway: $GATEWAY"
curl -s "$GATEWAY/health" | python3 -m json.tool

send "Обычный support"  "Здравствуйте, не приходит письмо для подтверждения регистрации"
send "Sales-лид"        "Сколько стоит тариф Pro и есть ли trial?"
send "Жалоба (эскалация)" "Это ужас, ничего не работает, верните деньги и дайте оператора"
send "Billing"          "Не прошёл платёж по счёту за апрель"

echo ""
echo "Готово. Эскалация и фильтр действий по trust_level видны в полях decision.escalate / decision.actions."
