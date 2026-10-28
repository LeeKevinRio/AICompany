-- 0004: exploration mode (ADR-0002 FD-6 Decision 1, C-43).
-- Purely additive: two new tables and their indexes; no existing table is touched.
-- Passenger, cabin, airline and departure-hour CHECKs are copied verbatim from 0003.

CREATE TABLE exploration (
  id INTEGER PRIMARY KEY,
  -- v1|origin|destination|trip_type|month|trip_days|max_stops|adults|children|cabin|
  -- airlines|dep_hour_from|dep_hour_to|currency (domain ExplorationSpec.condition_key).
  condition_key TEXT NOT NULL CHECK (condition_key GLOB 'v1|*'),
  origin TEXT NOT NULL CHECK (length(origin) = 3),
  destination TEXT NOT NULL CHECK (length(destination) = 3),
  trip_type TEXT NOT NULL CHECK (trip_type IN ('round_trip','one_way')),
  month TEXT NOT NULL CHECK (
    month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
    AND substr(month, 6, 2) BETWEEN '01' AND '12'
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

CREATE INDEX idx_exploration_condition ON exploration (condition_key, created_at);
CREATE INDEX idx_exploration_created ON exploration (created_at);
CREATE INDEX idx_exploration_started ON exploration (started_at);

-- One row per departure day to query; written (all 'pending') together with the
-- exploration row, then updated one by one by the background job.
CREATE TABLE exploration_cell (
  exploration_id INTEGER NOT NULL REFERENCES exploration(id) ON DELETE CASCADE,
  depart_date TEXT NOT NULL
    CHECK (depart_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  return_date TEXT
    CHECK (return_date IS NULL OR return_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','ok','no_data','blocked','error','skipped')),
  reason TEXT,
  source TEXT,
  price_kind TEXT CHECK (price_kind IS NULL OR price_kind IN ('live','cached')),
  from_cache INTEGER NOT NULL DEFAULT 0 CHECK (from_cache IN (0, 1)),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (typeof(attempts) = 'integer' AND attempts >= 0),
  amount_minor INTEGER CHECK (
    amount_minor IS NULL OR (typeof(amount_minor) = 'integer' AND amount_minor > 0)
  ),
  currency TEXT,
  carrier TEXT,
  stops INTEGER,
  duration_minutes INTEGER,
  depart_time TEXT
    CHECK (depart_time IS NULL OR (depart_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                   AND substr(depart_time, 1, 2) <= '23')),
  as_of TEXT,
  fetched_at TEXT,
  error TEXT,
  PRIMARY KEY (exploration_id, depart_date),
  CHECK ((status = 'ok') = (amount_minor IS NOT NULL))
);
