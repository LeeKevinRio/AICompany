-- 0001: initial schema (ADR-0002 draft, plus columns the MVP needs).
-- Timestamps (*_at, as_of) are UTC ISO 8601 text. Travel dates are local YYYY-MM-DD.
-- Money is integer minor units plus ISO 4217 currency code.

CREATE TABLE watch (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'TPE' CHECK (length(origin) = 3),
  destination TEXT NOT NULL CHECK (length(destination) = 3),
  trip_type TEXT NOT NULL CHECK (trip_type IN ('round_trip','one_way')),
  date_mode TEXT NOT NULL CHECK (date_mode IN ('fixed','flexible')),
  depart_date TEXT, return_date TEXT,
  window_start TEXT, window_end TEXT,
  min_trip_days INTEGER, max_trip_days INTEGER,
  max_stops INTEGER,
  cabin TEXT NOT NULL DEFAULT 'economy' CHECK (cabin = 'economy'),
  adults INTEGER NOT NULL DEFAULT 1 CHECK (adults = 1),
  currency TEXT NOT NULL DEFAULT 'TWD',
  budget_amount_minor INTEGER CHECK (budget_amount_minor IS NULL OR budget_amount_minor > 0),
  notify_on_new_low INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','stale','expired')),
  revision INTEGER NOT NULL DEFAULT 1,
  sample_offset INTEGER NOT NULL DEFAULT 0,
  consecutive_failed_scans INTEGER NOT NULL DEFAULT 0,
  last_scanned_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE scan_run (
  id INTEGER PRIMARY KEY,
  watch_id INTEGER NOT NULL REFERENCES watch(id) ON DELETE CASCADE,
  watch_revision INTEGER NOT NULL,
  trigger TEXT NOT NULL DEFAULT 'scheduled' CHECK (trigger IN ('scheduled','manual','startup')),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('running','ok','partial','failed')),
  sampled_pairs TEXT NOT NULL,
  total_pairs INTEGER NOT NULL DEFAULT 0,
  limit_reached INTEGER NOT NULL DEFAULT 0,
  global_limit_reached INTEGER NOT NULL DEFAULT 0,
  query_results TEXT NOT NULL DEFAULT '[]',
  queries_used INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT
);
CREATE INDEX ix_scan_run_watch ON scan_run(watch_id, started_at);
CREATE INDEX ix_scan_run_started ON scan_run(started_at);

CREATE TABLE price_observation (
  id INTEGER PRIMARY KEY,
  scan_run_id INTEGER NOT NULL REFERENCES scan_run(id) ON DELETE CASCADE,
  watch_id INTEGER NOT NULL REFERENCES watch(id) ON DELETE CASCADE,
  watch_revision INTEGER NOT NULL,
  source TEXT NOT NULL,
  price_kind TEXT NOT NULL CHECK (price_kind IN ('live','cached')),
  depart_date TEXT NOT NULL,
  return_date TEXT,
  amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
  currency TEXT NOT NULL,
  as_of TEXT NOT NULL,
  as_of_basis TEXT NOT NULL CHECK (as_of_basis IN ('source_reported','fetch_time')),
  fetched_at TEXT NOT NULL,
  carrier TEXT,
  stops INTEGER,
  duration_minutes INTEGER
);
CREATE INDEX ix_obs_watch_pair
  ON price_observation(watch_id, price_kind, depart_date, return_date, fetched_at);
CREATE INDEX ix_obs_watch_price ON price_observation(watch_id, price_kind, amount_minor);

CREATE TABLE alert_state (
  watch_id INTEGER NOT NULL REFERENCES watch(id) ON DELETE CASCADE,
  price_kind TEXT NOT NULL,
  last_notified_amount_minor INTEGER,
  last_notified_at TEXT,
  armed INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (watch_id, price_kind)
);

CREATE TABLE notification (
  id INTEGER PRIMARY KEY,
  watch_id INTEGER REFERENCES watch(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('price_alert','ops_source_failure','test')),
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
CREATE INDEX ix_notification_created ON notification(created_at);

-- One row per date-pair/price listed in a merged price alert (FR-C3 / FR-C9).
CREATE TABLE notification_item (
  id INTEGER PRIMARY KEY,
  notification_id INTEGER NOT NULL REFERENCES notification(id) ON DELETE CASCADE,
  item_key TEXT NOT NULL,
  depart_date TEXT NOT NULL,
  return_date TEXT,
  amount_minor INTEGER NOT NULL,
  currency TEXT NOT NULL,
  reasons TEXT NOT NULL,
  carrier TEXT,
  fetched_at TEXT NOT NULL
);
CREATE INDEX ix_notification_item_key ON notification_item(item_key);

CREATE TABLE source_health (
  source TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL,
  breaker_state TEXT NOT NULL CHECK (breaker_state IN ('closed','open','half_open')),
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  open_until TEXT,
  last_success_at TEXT,
  last_failure_at TEXT,
  last_error TEXT
);

CREATE TABLE app_setting (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Scheduler-level events such as skipped overlapping scans (FR-B7).
CREATE TABLE scheduler_event (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT
);
