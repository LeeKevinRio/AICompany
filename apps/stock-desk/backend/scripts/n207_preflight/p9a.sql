-- P-9a: distinct symbols whose last character is ASCII uppercase 'K' (U+004B), case-sensitive
SELECT COUNT(*) FROM (
  SELECT symbol FROM playbook_batches
  UNION
  SELECT symbol FROM playbook_symbols
) AS u
WHERE typeof(u.symbol) = 'text'
  AND substr(u.symbol, -1) = 'K' COLLATE BINARY;
