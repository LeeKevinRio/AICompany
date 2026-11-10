-- P-2: five counts, comma-joined by the runner, in this order:
--   (1) symbols whose MAX(batch_no) > bpt
--   (2) symbols whose MIN(batch_no) <> 1
--   (3) symbols whose MIN(batch_no) < 1
--   (4) symbols with a gap: COUNT(*) <> MAX - MIN + 1
--   (5) rows whose batch_no is not stored as INTEGER (typeof(batch_no) <> 'integer')
-- Read-only pre-deployment inventory item. Prints one count; never a symbol or an amount.
-- Current parameter row: WHERE / ORDER BY identical to PlaybookStore.active_params;
-- on_date is Taipei today (UTC+8, Taiwan has no DST). Defaults mirror RuleParams().
-- Drafted by data-engineer; semantics pending tech-architect review.
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
bpt AS (
  SELECT COALESCE((SELECT json_extract(payload, '$.batches_per_target') FROM cur), 3) AS v
),
per_symbol AS (
  SELECT MIN(batch_no) AS mn, MAX(batch_no) AS mx, COUNT(*) AS cnt
  FROM playbook_batches
  GROUP BY symbol
)
SELECT
  -- The CASE guard forces bpt to be read even when the table is empty; a malformed payload
  -- fails loudly and a non-integer bpt yields NULL (the runner reports ERROR).
  CASE WHEN typeof((SELECT v FROM bpt)) <> 'integer' THEN NULL
       ELSE COALESCE(SUM(mx > (SELECT v FROM bpt)), 0) END,
  COALESCE(SUM(mn <> 1), 0),
  COALESCE(SUM(mn < 1), 0),
  COALESCE(SUM(cnt <> mx - mn + 1), 0),
  (SELECT COUNT(*) FROM playbook_batches WHERE typeof(batch_no) <> 'integer')
FROM per_symbol;
