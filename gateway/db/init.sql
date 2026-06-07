-- Таблица наблюдаемости ядра. Создаётся при первом старте postgres.
CREATE TABLE IF NOT EXISTS interactions (
    id            BIGSERIAL PRIMARY KEY,
    event_id      TEXT UNIQUE NOT NULL,
    channel       TEXT,
    mode          TEXT,
    provider      TEXT,
    escalate      BOOLEAN,
    latency_ms    INTEGER,
    actions_count INTEGER DEFAULT 0,
    intent        TEXT,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_interactions_created_at ON interactions (created_at);
CREATE INDEX IF NOT EXISTS idx_interactions_mode       ON interactions (mode);
CREATE INDEX IF NOT EXISTS idx_interactions_error      ON interactions (error) WHERE error IS NOT NULL;

-- Приёмники действий (action executor). Единая форма: idempotency_key + payload(jsonb).
-- idempotency_key уникален → повторный вебхук не создаёт дубликат.
CREATE TABLE IF NOT EXISTS tickets (
    id BIGSERIAL PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
    user_id TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS drafts (
    id BIGSERIAL PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
    user_id TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reminders (
    id BIGSERIAL PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
    user_id TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS records (
    id BIGSERIAL PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
    user_id TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS notes (
    id BIGSERIAL PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
    user_id TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
