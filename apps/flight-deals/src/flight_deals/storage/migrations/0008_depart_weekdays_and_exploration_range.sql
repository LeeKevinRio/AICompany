-- flight-deals: foreign_keys=off
-- 0008: departure weekdays and exploration month ranges (ADR-0002 FD-10 Decision 1, C-71).
-- watch only gains a column (no rebuild: revision and sample_offset stay as they are;
-- every existing watch means "all weekdays").
-- exploration is rebuilt because SQLite cannot alter its condition_key CHECK. Same order
-- as 0003, and only this order: create exploration_new -> copy (explicit columns, ids
-- kept) -> drop exploration -> rename exploration_new to exploration -> recreate the
-- three indexes. The old table is never renamed first: a RENAME rewrites the parent name
-- inside the REFERENCES clause of the per-day cell table. With foreign keys OFF (marker
-- above) dropping the parent does no implicit DELETE, so the cell rows are kept; the
-- runner runs PRAGMA foreign_key_check before COMMIT. Every other CHECK is copied
-- verbatim from 0004.
-- The legacy ALTER TABLE compatibility pragma is never set here.

ALTER TABLE watch ADD COLUMN depart_weekdays INTEGER NOT NULL DEFAULT 127
  CHECK (typeof(depart_weekdays) = 'integer' AND depart_weekdays BETWEEN 1 AND 127);

CREATE TABLE exploration_new (
  id INTEGER PRIMARY KEY,
  -- v2|origin|destination|trip_type|month|month_end|weekday_mask|trip_days|max_stops|
  -- adults|children|cabin|airlines|dep_hour_from|dep_hour_to|currency (domain
  -- ExplorationSpec.condition_key); FD-6 rows keep their v1| key (table CHECK below).
  condition_key TEXT NOT NULL,
  origin TEXT NOT NULL CHECK (length(origin) = 3),
  destination TEXT NOT NULL CHECK (length(destination) = 3),
  trip_type TEXT NOT NULL CHECK (trip_type IN ('round_trip','one_way')),
  month TEXT NOT NULL CHECK (
    month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
    AND substr(month, 6, 2) BETWEEN '01' AND '12'
  ),
  -- End month of a range; NULL = single month (never equal to month).
  month_to TEXT CHECK (
    month_to IS NULL OR (
      month_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
      AND substr(month_to, 6, 2) BETWEEN '01' AND '12'
      AND month_to > month
    )
  ),
  -- Departure weekdays as a bitmask, bit d = date.weekday() d (0 = Monday); 127 = all.
  depart_weekdays INTEGER NOT NULL DEFAULT 127 CHECK (
    typeof(depart_weekdays) = 'integer' AND depart_weekdays BETWEEN 1 AND 127
  ),
  trip_days INTEGER,
  max_stops INTEGER CHECK (
    max_stops IS NULL OR (typeof(max_stops) = 'integer' AND max_stops BETWEEN 0 AND 2)
  ),
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
  -- Progress: no 'rejected' state, a refused exploration is never written (Decision 1).
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','running','done','failed')),
  total INTEGER NOT NULL CHECK (typeof(total) = 'integer' AND total BETWEEN 1 AND 31),
  done INTEGER NOT NULL DEFAULT 0 CHECK (typeof(done) = 'integer' AND done >= 0),
  queries_used INTEGER NOT NULL DEFAULT 0
    CHECK (typeof(queries_used) = 'integer' AND queries_used >= 0),
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error_summary TEXT,
  CHECK (done <= total),
  -- v1 rows are single-month, all-weekday explorations; only v2 keys carry a range.
  CHECK (
    (condition_key GLOB 'v1|*' AND month_to IS NULL AND depart_weekdays = 127)
    OR condition_key GLOB 'v2|*'
  ),
  CHECK (adults + children <= 9),
  CHECK (
    (dep_hour_from IS NULL AND dep_hour_to IS NULL)
    OR (dep_hour_from IS NOT NULL AND dep_hour_to IS NOT NULL
        AND typeof(dep_hour_from) = 'integer' AND typeof(dep_hour_to) = 'integer'
        AND dep_hour_from BETWEEN 0 AND 23 AND dep_hour_to BETWEEN 0 AND 23
        AND dep_hour_from < dep_hour_to)
  ),
  -- Round trips need a stay length of 1-30 days; one-way trips must not carry one.
  CHECK (
    (trip_type = 'one_way' AND trip_days IS NULL)
    OR (trip_type = 'round_trip' AND trip_days IS NOT NULL
        AND typeof(trip_days) = 'integer' AND trip_days BETWEEN 1 AND 30)
  )
);

INSERT INTO exploration_new (id, condition_key, origin, destination, trip_type, month,
  trip_days, max_stops, cabin, adults, children, airlines, dep_hour_from, dep_hour_to,
  currency, status, total, done, queries_used, created_at, started_at, finished_at,
  error_summary)
SELECT id, condition_key, origin, destination, trip_type, month,
  trip_days, max_stops, cabin, adults, children, airlines, dep_hour_from, dep_hour_to,
  currency, status, total, done, queries_used, created_at, started_at, finished_at,
  error_summary
FROM exploration;

DROP TABLE exploration;

ALTER TABLE exploration_new RENAME TO exploration;

CREATE INDEX idx_exploration_condition ON exploration (condition_key, created_at);
CREATE INDEX idx_exploration_created ON exploration (created_at);
CREATE INDEX idx_exploration_started ON exploration (started_at);
