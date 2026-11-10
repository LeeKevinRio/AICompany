-- P-4c: anomaly count; may be reported
SELECT COUNT(*) FROM playbook_symbols
WHERE typeof(high_volatility) <> 'integer' OR high_volatility NOT IN (0, 1);
