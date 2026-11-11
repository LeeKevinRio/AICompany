-- P-8b (RC-110 item 1): confirmed (rule_set_confirmed_at key or any parameter row) AND no
-- total_deploy key. Prints 0 or 1; never a symbol or an amount. SQL text per tech-architect.
SELECT CASE WHEN
  (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
   OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND NOT EXISTS (SELECT 1 FROM playbook_state WHERE key = 'total_deploy')
THEN 1 ELSE 0 END;
