-- P-1: number of symbols whose batch count differs from batches_per_target (bpt).
-- Read-only pre-deployment inventory item. Prints one count; never a symbol or an amount.
-- Current parameter row: WHERE / ORDER BY identical to PlaybookStore.active_params;
-- on_date is Taipei today (UTC+8, Taiwan has no DST). Defaults mirror RuleParams().
-- Pre-deployment every symbol is on round 1 (no batch_round column yet).
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
)
-- The outer CASE forces bpt to be evaluated even when the table is empty.
SELECT CASE WHEN (SELECT v FROM bpt) IS NULL THEN NULL ELSE (
  SELECT COUNT(*) FROM (
    SELECT symbol FROM playbook_batches
    GROUP BY symbol
    HAVING COUNT(*) <> (SELECT v FROM bpt)
  )
) END;
