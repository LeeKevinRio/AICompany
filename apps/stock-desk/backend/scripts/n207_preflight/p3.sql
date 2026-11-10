-- P-3: two values, comma-joined by the runner: (1) distinct symbols in playbook_batches,
-- (2) n_targets in force. (1) > (2) means STOP-2. Definition per R-14.
-- Read-only pre-deployment inventory item. Prints one count; never a symbol or an amount.
-- Current parameter row: WHERE / ORDER BY identical to PlaybookStore.active_params;
-- on_date is Taipei today (UTC+8, Taiwan has no DST). Defaults mirror RuleParams().
-- Drafted by data-engineer; semantics pending tech-architect review.
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
nt AS (
  SELECT COALESCE((SELECT json_extract(payload, '$.n_targets') FROM cur), 5) AS v
)
SELECT COUNT(DISTINCT symbol),
       CASE WHEN typeof((SELECT v FROM nt)) <> 'integer' THEN NULL ELSE (SELECT v FROM nt) END
FROM playbook_batches;
