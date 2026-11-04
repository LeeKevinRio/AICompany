-- 0010: Google marks the fare as excluding the overhead bin (ADR-0002 FD-15).
-- Only ADD COLUMN on the three price tables: no rebuild, no index, no foreign-key
-- change. 1 = marked; NULL = not marked or written before this migration, and both must
-- stay silent: NULL never means the fare includes it. Existing rows are not backfilled.

ALTER TABLE price_observation ADD COLUMN overhead_bin_excluded INTEGER
  CHECK (overhead_bin_excluded IS NULL OR overhead_bin_excluded = 1);
ALTER TABLE exploration_cell ADD COLUMN overhead_bin_excluded INTEGER
  CHECK (overhead_bin_excluded IS NULL OR overhead_bin_excluded = 1);
ALTER TABLE comparison_cell ADD COLUMN overhead_bin_excluded INTEGER
  CHECK (overhead_bin_excluded IS NULL OR overhead_bin_excluded = 1);
