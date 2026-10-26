-- flight-deals: foreign_keys=off
-- 0002: allow notification.kind = 'daily_digest' (ADR-0002 FD-4 Decision 4, C-33).
-- SQLite cannot alter a CHECK constraint, so the table is rebuilt with the official
-- 12-step procedure. The runner applies this file with foreign keys OFF (marker above),
-- so dropping the old table does not cascade into notification_item, and runs
-- PRAGMA foreign_key_check before COMMIT.

CREATE TABLE notification_new (
  id INTEGER PRIMARY KEY,
  watch_id INTEGER REFERENCES watch(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('price_alert','ops_source_failure','test','daily_digest')),
  rule TEXT CHECK (rule IN ('below_budget','drop_pct','new_low')),
  price_kind TEXT,
  observation_id INTEGER REFERENCES price_observation(id) ON DELETE SET NULL,
  channel TEXT NOT NULL DEFAULT 'telegram',
  dedupe_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('pending','sent','failed','suppressed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  message_text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  last_error TEXT
);

INSERT INTO notification_new (id, watch_id, kind, rule, price_kind, observation_id, channel,
  dedupe_key, status, attempts, message_text, created_at, sent_at, last_error)
SELECT id, watch_id, kind, rule, price_kind, observation_id, channel,
  dedupe_key, status, attempts, message_text, created_at, sent_at, last_error
FROM notification;

DROP TABLE notification;

ALTER TABLE notification_new RENAME TO notification;

CREATE INDEX ix_notification_created ON notification(created_at);
