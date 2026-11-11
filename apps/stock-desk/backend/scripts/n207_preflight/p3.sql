-- SCOPE (TA A-1): this file equals the ADR-0043 D1 enabled-symbol count ONLY on the schema that
-- exists before N-207 is deployed. Before deployment playbook_batches has no entry_stopped
-- column, so every symbol in the list counts as enabled. After N-207 is deployed this file
-- must NOT be used again to decide R-14. Do not add an entry_stopped condition: before
-- deployment it would fail with a missing-column error.
-- P-3: two values, comma-joined by the runner: (1) distinct symbols in playbook_batches,
-- (2) n_targets in force. (1) > (2) means STOP-2. Definition per R-14.
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
nt AS (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM cur) THEN 5
    WHEN json_type((SELECT payload FROM cur)) <> 'object' THEN NULL
    WHEN json_type((SELECT payload FROM cur), '$.n_targets') IS NULL THEN 5
    WHEN json_type((SELECT payload FROM cur), '$.n_targets') = 'integer'
      THEN json_extract((SELECT payload FROM cur), '$.n_targets')
    ELSE NULL
  END AS v
)
SELECT COUNT(DISTINCT symbol),
       CASE WHEN (SELECT v FROM nt) IS NULL THEN NULL ELSE (SELECT v FROM nt) END
FROM playbook_batches;
