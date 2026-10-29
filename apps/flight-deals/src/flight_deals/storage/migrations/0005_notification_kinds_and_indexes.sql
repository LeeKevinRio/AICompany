-- flight-deals: foreign_keys=off
-- 0005: notification.kind gains 'command' and 'manual_digest', plus the indexes the
-- list query and the retention purge need (ADR-0002 FD-7 Decisions 6 and 9, C-52).
-- SQLite cannot alter a CHECK constraint, so notification is rebuilt exactly like 0002:
-- create notification_new -> copy -> drop notification -> rename notification_new.
-- The runner applies this file with foreign keys OFF (marker above), so dropping the
-- old table does not cascade into notification_item, and runs PRAGMA foreign_key_check
-- before COMMIT. The scan and observation tables are only indexed, never rebuilt.

CREATE TABLE notification_new (
  id INTEGER PRIMARY KEY,
  watch_id INTEGER REFERENCES watch(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN (
    'price_alert','ops_source_failure','test','daily_digest','command','manual_digest'
  )),
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

-- Foreign-key child columns: the purge deletes parents in batches (Decision 7).
CREATE INDEX ix_notification_observation ON notification(observation_id);
CREATE INDEX ix_notification_item_notification ON notification_item(notification_id);
CREATE INDEX ix_price_observation_scan_run ON price_observation(scan_run_id);

-- Per-watch "latest finished run" lookups of the list query (Decision 9).
CREATE INDEX ix_scan_run_watch_id ON scan_run(watch_id, id);
CREATE INDEX ix_scan_run_watch_rev ON scan_run(watch_id, watch_revision, id);
