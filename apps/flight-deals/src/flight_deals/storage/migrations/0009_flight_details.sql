-- 0009: flight details of the cheapest itinerary (ADR-0002 FD-12, C-95).
-- Only ADD COLUMN on the three price tables: no rebuild, no index, no foreign-key
-- change. Existing rows keep NULL (never backfilled). Per table, in order:
--   flight_numbers     "BR184" / "CZ3088,CZ3575" (code + number per segment)
--   arrive_time        local "HH:MM" at the final airport (CHECK copied from 0003)
--   arrive_day_offset  local arrival date - local departure date, -1..3; set together
--                      with arrive_time
--   route_airports     "TPE,NRT" / "TPE,SZX,SHA" (origin plus every segment's arrival)
-- Cell values are only written for ok cells (enforced in Python).

ALTER TABLE price_observation ADD COLUMN flight_numbers TEXT
  CHECK (flight_numbers IS NULL OR (length(flight_numbers) BETWEEN 3 AND 41
                                    AND flight_numbers NOT GLOB '*[^A-Z0-9,]*'
                                    AND flight_numbers NOT GLOB ',*'
                                    AND flight_numbers NOT GLOB '*,'
                                    AND flight_numbers NOT GLOB '*,,*'));
ALTER TABLE price_observation ADD COLUMN arrive_time TEXT
  CHECK (arrive_time IS NULL OR (arrive_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                 AND substr(arrive_time, 1, 2) <= '23'));
ALTER TABLE price_observation ADD COLUMN arrive_day_offset INTEGER
  CHECK ((arrive_day_offset IS NULL) = (arrive_time IS NULL)
         AND (arrive_day_offset IS NULL OR (typeof(arrive_day_offset) = 'integer'
                                            AND arrive_day_offset BETWEEN -1 AND 3)));
ALTER TABLE price_observation ADD COLUMN route_airports TEXT
  CHECK (route_airports IS NULL OR (length(route_airports) BETWEEN 7 AND 27
                                    AND length(route_airports) % 4 = 3
                                    AND route_airports NOT GLOB '*[^A-Z,]*'
                                    AND substr(route_airports, 4, 1) = ','));

ALTER TABLE exploration_cell ADD COLUMN flight_numbers TEXT
  CHECK (flight_numbers IS NULL OR (length(flight_numbers) BETWEEN 3 AND 41
                                    AND flight_numbers NOT GLOB '*[^A-Z0-9,]*'
                                    AND flight_numbers NOT GLOB ',*'
                                    AND flight_numbers NOT GLOB '*,'
                                    AND flight_numbers NOT GLOB '*,,*'));
ALTER TABLE exploration_cell ADD COLUMN arrive_time TEXT
  CHECK (arrive_time IS NULL OR (arrive_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                 AND substr(arrive_time, 1, 2) <= '23'));
ALTER TABLE exploration_cell ADD COLUMN arrive_day_offset INTEGER
  CHECK ((arrive_day_offset IS NULL) = (arrive_time IS NULL)
         AND (arrive_day_offset IS NULL OR (typeof(arrive_day_offset) = 'integer'
                                            AND arrive_day_offset BETWEEN -1 AND 3)));
ALTER TABLE exploration_cell ADD COLUMN route_airports TEXT
  CHECK (route_airports IS NULL OR (length(route_airports) BETWEEN 7 AND 27
                                    AND length(route_airports) % 4 = 3
                                    AND route_airports NOT GLOB '*[^A-Z,]*'
                                    AND substr(route_airports, 4, 1) = ','));

ALTER TABLE comparison_cell ADD COLUMN flight_numbers TEXT
  CHECK (flight_numbers IS NULL OR (length(flight_numbers) BETWEEN 3 AND 41
                                    AND flight_numbers NOT GLOB '*[^A-Z0-9,]*'
                                    AND flight_numbers NOT GLOB ',*'
                                    AND flight_numbers NOT GLOB '*,'
                                    AND flight_numbers NOT GLOB '*,,*'));
ALTER TABLE comparison_cell ADD COLUMN arrive_time TEXT
  CHECK (arrive_time IS NULL OR (arrive_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                 AND substr(arrive_time, 1, 2) <= '23'));
ALTER TABLE comparison_cell ADD COLUMN arrive_day_offset INTEGER
  CHECK ((arrive_day_offset IS NULL) = (arrive_time IS NULL)
         AND (arrive_day_offset IS NULL OR (typeof(arrive_day_offset) = 'integer'
                                            AND arrive_day_offset BETWEEN -1 AND 3)));
ALTER TABLE comparison_cell ADD COLUMN route_airports TEXT
  CHECK (route_airports IS NULL OR (length(route_airports) BETWEEN 7 AND 27
                                    AND length(route_airports) % 4 = 3
                                    AND route_airports NOT GLOB '*[^A-Z,]*'
                                    AND substr(route_airports, 4, 1) = ','));
