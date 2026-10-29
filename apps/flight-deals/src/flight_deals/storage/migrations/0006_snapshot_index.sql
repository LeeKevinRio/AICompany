CREATE INDEX ix_obs_snapshot ON price_observation(watch_id, watch_revision, price_kind, currency, depart_date, return_date, fetched_at DESC, id DESC, scan_run_id);
