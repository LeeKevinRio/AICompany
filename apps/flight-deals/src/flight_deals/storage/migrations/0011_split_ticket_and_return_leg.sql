-- 0011: Google's separate-tickets mark and the return leg of the cheapest pair (FD-16).
-- Only ADD COLUMN: no rebuild, no index, no foreign-key change. Existing rows stay NULL.
-- split_ticket: 1 = Google marks this price as separate tickets; NULL = not marked or
-- unknown, and NULL never means one ticket. The return columns belong to one observation:
-- the return flight whose total equals that observation's price when it was looked up.

ALTER TABLE price_observation ADD COLUMN split_ticket INTEGER
  CHECK (split_ticket IS NULL OR split_ticket = 1);
ALTER TABLE exploration_cell ADD COLUMN split_ticket INTEGER
  CHECK (split_ticket IS NULL OR split_ticket = 1);
ALTER TABLE comparison_cell ADD COLUMN split_ticket INTEGER
  CHECK (split_ticket IS NULL OR split_ticket = 1);

ALTER TABLE price_observation ADD COLUMN return_carrier TEXT;
ALTER TABLE price_observation ADD COLUMN return_stops INTEGER
  CHECK (return_stops IS NULL OR (typeof(return_stops) = 'integer' AND return_stops >= 0));
ALTER TABLE price_observation ADD COLUMN return_depart_time TEXT
  CHECK (return_depart_time IS NULL OR (return_depart_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                        AND substr(return_depart_time, 1, 2) <= '23'));
ALTER TABLE price_observation ADD COLUMN return_duration_minutes INTEGER
  CHECK (return_duration_minutes IS NULL OR (typeof(return_duration_minutes) = 'integer'
                                             AND return_duration_minutes > 0));
ALTER TABLE price_observation ADD COLUMN return_flight_numbers TEXT
  CHECK (return_flight_numbers IS NULL OR (length(return_flight_numbers) BETWEEN 3 AND 41
                                           AND return_flight_numbers NOT GLOB '*[^A-Z0-9,]*'
                                           AND return_flight_numbers NOT GLOB ',*'
                                           AND return_flight_numbers NOT GLOB '*,'
                                           AND return_flight_numbers NOT GLOB '*,,*'));
ALTER TABLE price_observation ADD COLUMN return_arrive_time TEXT
  CHECK (return_arrive_time IS NULL OR (return_arrive_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                        AND substr(return_arrive_time, 1, 2) <= '23'));
ALTER TABLE price_observation ADD COLUMN return_arrive_day_offset INTEGER
  CHECK ((return_arrive_day_offset IS NULL) = (return_arrive_time IS NULL)
         AND (return_arrive_day_offset IS NULL
              OR (typeof(return_arrive_day_offset) = 'integer'
                  AND return_arrive_day_offset BETWEEN -1 AND 3)));
ALTER TABLE price_observation ADD COLUMN return_route_airports TEXT
  CHECK (return_route_airports IS NULL OR (length(return_route_airports) BETWEEN 7 AND 27
                                           AND length(return_route_airports) % 4 = 3
                                           AND return_route_airports NOT GLOB '*[^A-Z,]*'
                                           AND substr(return_route_airports, 4, 1) = ','));
