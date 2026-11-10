-- P-5: status outside the closed set, or NULL (BINARY comparison; non-TEXT values count as exceptions)
-- Drafted by data-engineer; semantics pending tech-architect review.
SELECT COUNT(*) FROM playbook_batches
WHERE status IS NULL OR status NOT IN ('planned', 'open', 'closed', 'skipped');
