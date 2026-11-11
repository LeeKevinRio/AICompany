-- P-9b: distinct symbols not stored as TEXT (the P-9a predicate cannot judge them)
SELECT COUNT(*) FROM (
  SELECT symbol FROM playbook_batches
  UNION
  SELECT symbol FROM playbook_symbols
) AS u
WHERE typeof(u.symbol) <> 'text';
