-- 0007: multi-destination comparison (ADR-0002 FD-9 Decision 1, C-61).
-- Purely additive: two new tables and their indexes; no existing table is touched.
-- Stops, cabin and passenger CHECKs are copied verbatim from 0003 / 0004; the domain
-- always writes 1 adult and 0 children.

CREATE TABLE comparison (
  id INTEGER PRIMARY KEY,
  -- cmp1|origin|destinations(sorted)|trip_type|depart|return|max_stops|adults|children|
  -- cabin|currency (domain ComparisonSpec.condition_key).
  condition_key TEXT NOT NULL CHECK (condition_key GLOB 'cmp1|*'),
  origin TEXT NOT NULL CHECK (length(origin) = 3),
  -- Destination codes in input order, comma separated ("NRT,OSA,SEL").
  destinations TEXT NOT NULL CHECK (length(destinations) = total * 4 - 1),
  trip_type TEXT NOT NULL CHECK (trip_type IN ('round_trip','one_way')),
  depart_date TEXT NOT NULL
    CHECK (depart_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  return_date TEXT
    CHECK (return_date IS NULL OR return_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
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
  currency TEXT NOT NULL DEFAULT 'TWD',
  -- Progress: no 'rejected' state, a refused comparison is never written (Decision 1).
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','running','done','failed')),
  total INTEGER NOT NULL CHECK (typeof(total) = 'integer' AND total BETWEEN 2 AND 8),
  done INTEGER NOT NULL DEFAULT 0 CHECK (typeof(done) = 'integer' AND done >= 0),
  queries_used INTEGER NOT NULL DEFAULT 0
    CHECK (typeof(queries_used) = 'integer' AND queries_used >= 0),
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error_summary TEXT,
  CHECK (done <= total),
  CHECK (adults + children <= 9),
  -- One-way trips carry no return date; round trips need one, not before departure.
  CHECK (
    (trip_type = 'one_way' AND return_date IS NULL)
    OR (trip_type = 'round_trip' AND return_date IS NOT NULL AND return_date >= depart_date)
  )
);

CREATE INDEX idx_comparison_condition ON comparison (condition_key, created_at);
CREATE INDEX idx_comparison_created ON comparison (created_at);
CREATE INDEX idx_comparison_started ON comparison (started_at);

-- One row per destination, in input order (position); written (all 'pending') together
-- with the comparison row, then updated one by one by the background job.
CREATE TABLE comparison_cell (
  comparison_id INTEGER NOT NULL REFERENCES comparison(id) ON DELETE CASCADE,
  position INTEGER NOT NULL
    CHECK (typeof(position) = 'integer' AND position BETWEEN 0 AND 7),
  destination TEXT NOT NULL CHECK (length(destination) = 3),
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
  PRIMARY KEY (comparison_id, position),
  UNIQUE (comparison_id, destination),
  CHECK ((status = 'ok') = (amount_minor IS NOT NULL))
);
