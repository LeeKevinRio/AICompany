-- 1d: unsettled directives whose batch_no is < 1 or has no matching playbook_batches row
SELECT COUNT(*) FROM playbook_directives AS d
WHERE d.settled = 0
  AND d.batch_no IS NOT NULL
  AND (d.batch_no < 1
       OR NOT EXISTS (SELECT 1 FROM playbook_batches AS b
                      WHERE b.symbol = d.symbol AND b.batch_no = d.batch_no));
