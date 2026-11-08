# f589be8 CI 落差結案紀錄（風控 R21）

- 記錄者：coordinator（非唯讀執行者）
- 日期：2026-11-08（Asia/Taipei）
- 依據：`work/reviews/2026-11-07-R14至R16改寫回審-風控.md` R21

## 1. 補跑對象
- `<tip>` = 2bc560f6dc4515d6c381aec1a83299e4145b7096
- `$ git merge-base --is-ancestor f589be8 2bc560f6dc4515d6c381aec1a83299e4145b7096` → exit=0

## 2. CI 步驟（worktree `scratchpad/wt_n190fix`，detached 在 <tip>）
- backend：
  - `ruff check .` → All checks passed!（exit=0）
  - `ruff format --check .` → 494 files already formatted（exit=0）
  - `mypy app tests` → Success: no issues found in 485 source files（exit=0）
  - `pytest -q -p no:cacheprovider --cov=app --cov-fail-under=90` → 9895 passed, 1 skipped, 2 xfailed；Total coverage 97.62%（PYTEST=0）。skip 的是偵測工具 S11 的 N-177a 對齊測試，N-177a 合入後會自動啟用。
- compose-validate：
  - `docker compose config > /dev/null` → exit=0
  - `docker compose config --format json | python3 .github/workflows/scripts/verify_stock_desk_compose.py` → exit=0,0（compose-guard 通過）
- frontend：
  - `npx tsc --noEmit` → TSC=0
  - `npx vitest run` → 116 files / 3086 tests passed（VITEST=0）
  - `npx next build` → BUILD=0
- `python3 scripts/validate_agents.py` → validate_agents: OK（15 個 agents 全數通過），exit=0

## 3. 落差的事實紀錄
- 119988f0204f8d2dd5fb05e82bd7a3ded6e06c15，tree f93eee6f3d349cc86cf4e9c50178f47061aa2175
- f589be8a19529e873ac6f57e40afe95ac7d55933，tree df857e404866e288d199395aaf2400ee07c50141
- `$ git diff --name-only 119988f f589be8`（不加路徑過濾，exit=0）：
  - docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md
  - work/dispatch/2026-10-17-後續追蹤清單.md
  - work/reviews/2026-11-07-N177a交件-dev-lead.md
  - work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md
  - work/reviews/2026-11-07-REBALANCE_SUPERSEDED候選-creative-lead.md

## 4. 結論
完整 CI 全綠，依 R21 結案。往後依修訂八：merge 時以 40 碼指定合入對象；只有整棵 tree 雜湊相同，才能沿用前一次的 CI 結果。
