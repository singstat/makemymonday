CREATE TABLE IF NOT EXISTS facts (
  fact_key   TEXT PRIMARY KEY,
  fact_value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
  id         BIGSERIAL PRIMARY KEY,
  role       TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
  content    TEXT NOT NULL,
  day        DATE NOT NULL DEFAULT (CURRENT_DATE),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_day ON messages(day);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

CREATE TABLE IF NOT EXISTS summaries (
  day        DATE PRIMARY KEY,
  summary    TEXT NOT NULL,
  tokens     INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
