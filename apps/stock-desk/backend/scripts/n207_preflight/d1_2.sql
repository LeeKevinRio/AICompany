-- 1d-2: unsettled buy/sell directives with NULL batch_no that are not S2
SELECT COUNT(*) FROM playbook_directives
WHERE settled = 0 AND batch_no IS NULL
  AND action IN ('buy', 'sell') AND rule_id <> 'S2';
