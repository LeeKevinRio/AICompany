-- WARNING: LOCAL ONLY. This file lists symbols. run_preflight.py NEVER executes it.
-- Run it by hand, read-only, on the CEO's own machine, only when P-4a > 0, in the same
-- read-only session as P-4a. The output stays on the CEO's local screen: it must never
-- be pasted back into chat, work/, any record, or any agent.
-- 輸出只留在 CEO 本機畫面，不得貼回對話、work/、紀錄或任何 agent。
SELECT symbol FROM playbook_symbols WHERE high_volatility <> 0 ORDER BY symbol;
