-- flight-deals: foreign_keys=off
-- 0003: trip options on watch (ADR-0002 FD-5 Decision 1, C-37).
-- SQLite cannot alter a CHECK constraint, so watch is rebuilt with the official 12-step
-- procedure, in this order only: create watch_new -> copy -> drop watch -> rename
-- watch_new to watch. The old table is never renamed first: since SQLite 3.26 a RENAME
-- rewrites the parent name inside every child table's REFERENCES clause (whatever the
-- foreign_keys setting), which would leave the children pointing at the old table.
-- With foreign keys OFF (marker above) the DROP does no implicit DELETE, so the five
-- child tables keep their rows; the runner runs PRAGMA foreign_key_check before COMMIT.
-- The legacy ALTER TABLE compatibility pragma is never set here.

CREATE TABLE watch_new (
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
  cabin TEXT NOT NULL DEFAULT 'economy'
    CHECK (cabin IN ('economy','premium_economy','business','first')),
  -- typeof() checks: INTEGER affinity alone would store 1.5 as a real.
  adults INTEGER NOT NULL DEFAULT 1
    CHECK (typeof(adults) = 'integer' AND adults BETWEEN 1 AND 9),
  children INTEGER NOT NULL DEFAULT 0
    CHECK (typeof(children) = 'integer' AND children BETWEEN 0 AND 8),
  -- Upper-case IATA codes, comma separated, at most 5; NULL = any airline.
  airlines TEXT CHECK (
    airlines IS NULL OR (
      (airlines GLOB '[A-Z0-9][A-Z0-9]'
        OR airlines GLOB '[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9]'
        OR airlines GLOB '[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9]'
        OR airlines GLOB '[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9]'
        OR airlines GLOB
          '[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9],[A-Z0-9][A-Z0-9]')
      AND airlines NOT GLOB '*[0-9][0-9]*'
    )
  ),
  -- Outbound departure window in whole local hours: both NULL, or 0-23 with from < to
  -- (the IS NOT NULL terms matter: a NULL inside BETWEEN would make the CHECK pass).
  dep_hour_from INTEGER,
  dep_hour_to INTEGER,
  currency TEXT NOT NULL DEFAULT 'TWD',
  budget_amount_minor INTEGER CHECK (budget_amount_minor IS NULL OR budget_amount_minor > 0),
  notify_on_new_low INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','stale','expired')),
  revision INTEGER NOT NULL DEFAULT 1,
  sample_offset INTEGER NOT NULL DEFAULT 0,
  consecutive_failed_scans INTEGER NOT NULL DEFAULT 0,
  last_scanned_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (adults + children <= 9),
  CHECK (
    (dep_hour_from IS NULL AND dep_hour_to IS NULL)
    OR (dep_hour_from IS NOT NULL AND dep_hour_to IS NOT NULL
        AND typeof(dep_hour_from) = 'integer' AND typeof(dep_hour_to) = 'integer'
        AND dep_hour_from BETWEEN 0 AND 23 AND dep_hour_to BETWEEN 0 AND 23
        AND dep_hour_from < dep_hour_to)
  )
);

INSERT INTO watch_new (id, name, origin, destination, trip_type, date_mode, depart_date,
  return_date, window_start, window_end, min_trip_days, max_trip_days, max_stops, cabin,
  adults, currency, budget_amount_minor, notify_on_new_low, status, revision,
  sample_offset, consecutive_failed_scans, last_scanned_at, created_at, updated_at)
SELECT id, name, origin, destination, trip_type, date_mode, depart_date,
  return_date, window_start, window_end, min_trip_days, max_trip_days, max_stops, cabin,
  adults, currency, budget_amount_minor, notify_on_new_low, status, revision,
  sample_offset, consecutive_failed_scans, last_scanned_at, created_at, updated_at
FROM watch;

DROP TABLE watch;

ALTER TABLE watch_new RENAME TO watch;

-- Local departure time "HH:MM" of the first segment (optional; FD-5 Decision 4).
ALTER TABLE price_observation ADD COLUMN depart_time TEXT
  CHECK (depart_time IS NULL OR (depart_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                 AND substr(depart_time, 1, 2) <= '23'));

-- Dedupe item keys gain the revision (Decision 8):
--   price:<watch>:<kind>:...  ->  price:<watch>:r<revision>:<kind>:...
-- The revision comes from the alert's observation; rows whose notification has no
-- observation (observation_id NULL) cannot be resolved and stay unchanged.
UPDATE notification_item
SET item_key = (
  SELECT 'price:' || po.watch_id || ':r' || po.watch_revision
         || substr(notification_item.item_key, length('price:' || po.watch_id) + 1)
  FROM notification n
  JOIN price_observation po ON po.id = n.observation_id
  WHERE n.id = notification_item.notification_id
)
WHERE EXISTS (
  SELECT 1
  FROM notification n
  JOIN price_observation po ON po.id = n.observation_id
  WHERE n.id = notification_item.notification_id
    AND substr(notification_item.item_key, 1, length('price:' || po.watch_id || ':'))
        = 'price:' || po.watch_id || ':'
    AND substr(notification_item.item_key, length('price:' || po.watch_id || ':') + 1, 1)
        != 'r'
);
