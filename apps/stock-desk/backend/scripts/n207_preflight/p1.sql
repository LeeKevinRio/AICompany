-- P-1: number of symbols whose batch count differs from batches_per_target (bpt).
-- Read-only pre-deployment inventory item. Prints one count; never a symbol or an amount.
-- Current parameter row: WHERE / ORDER BY identical to PlaybookStore.active_params;
-- on_date is Taipei today (UTC+8, Taiwan has no DST). Defaults mirror RuleParams().
-- Pre-deployment every symbol is on round 1 (no batch_round column yet).
-- Drafted by data-engineer; semantics pending tech-architect review.
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
bpt AS (
  SELECT COALESCE((SELECT json_extract(payload, '$.batches_per_target') FROM cur), 3) AS v
)
-- The CASE guard forces bpt to be read (and a malformed payload to fail loudly) even when
-- the table is empty; a non-integer bpt yields NULL, which the runner reports as ERROR.
SELECT CASE WHEN typeof((SELECT v FROM bpt)) <> 'integer' THEN NULL ELSE (
  SELECT COUNT(*) FROM (
    SELECT symbol FROM playbook_batches
    GROUP BY symbol
    HAVING COUNT(*) <> (SELECT v FROM bpt)
  )
) END;
