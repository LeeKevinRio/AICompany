-- P-8: authorship confirmed AND the cash key is missing (0 or 1)
SELECT CASE WHEN
  (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
   OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND NOT EXISTS (SELECT 1 FROM playbook_state WHERE key = 'cash')
THEN 1 ELSE 0 END;
