-- P-7: authorship NOT confirmed AND the total_deploy key exists (0 or 1)
SELECT CASE WHEN
  NOT (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
       OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND EXISTS (SELECT 1 FROM playbook_state WHERE key = 'total_deploy')
THEN 1 ELSE 0 END;
