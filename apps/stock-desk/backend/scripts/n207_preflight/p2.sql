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
-- Parameter guard (TA A-7): key absent -> RuleParams default; payload not a JSON object, or key
-- present but not a JSON integer (null / true / real / text / ...) -> NULL -> the runner prints
-- ERROR; a payload that is not valid JSON makes json_type fail -> ERROR. The app would reject
-- the same rows, so an inventory that silently applied the default would point the wrong way.
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
bpt AS (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM cur) THEN 3
    WHEN json_type((SELECT payload FROM cur)) <> 'object' THEN NULL
    WHEN json_type((SELECT payload FROM cur), '$.batches_per_target') IS NULL THEN 3
    WHEN json_type((SELECT payload FROM cur), '$.batches_per_target') = 'integer'
      THEN json_extract((SELECT payload FROM cur), '$.batches_per_target')
    ELSE NULL
  END AS v
),
per_symbol AS (
  SELECT MIN(batch_no) AS mn, MAX(batch_no) AS mx, COUNT(*) AS cnt
  FROM playbook_batches
  GROUP BY symbol
)
SELECT
  -- The CASE forces bpt to be evaluated even when the table is empty.
  CASE WHEN (SELECT v FROM bpt) IS NULL THEN NULL
       ELSE COALESCE(SUM(mx > (SELECT v FROM bpt)), 0) END,
  COALESCE(SUM(mn <> 1), 0),
  COALESCE(SUM(mn < 1), 0),
  COALESCE(SUM(cnt <> mx - mn + 1), 0),
  (SELECT COUNT(*) FROM playbook_batches WHERE typeof(batch_no) <> 'integer')
FROM per_symbol;
