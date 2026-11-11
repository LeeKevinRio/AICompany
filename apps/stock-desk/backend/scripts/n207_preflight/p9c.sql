-- P-9c: distinct TEXT symbols that are not K-suffixed and fail the shape rule
SELECT COUNT(*) FROM (
  SELECT symbol FROM playbook_batches
  UNION
  SELECT symbol FROM playbook_symbols
) AS u
WHERE typeof(u.symbol) = 'text'
  AND NOT (substr(u.symbol, -1) = 'K' COLLATE BINARY)
  AND NOT (
       u.symbol GLOB '[1-9][0-9][0-9][0-9]'
    OR u.symbol GLOB '[1-9][0-9][0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '00[0-9][0-9]'
    OR u.symbol GLOB '00[0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '00[0-9][0-9][0-9]'
    OR u.symbol GLOB '00[0-9][0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '00[0-9][0-9][0-9][0-9]'
    OR u.symbol GLOB '00[0-9][0-9][0-9][0-9][A-JL-Z]'
    OR u.symbol GLOB '91[0-9][0-9][0-9][0-9]'
  );
