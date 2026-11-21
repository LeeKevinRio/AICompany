# gap_check 註解與 regex 修正複審（單家審查）

- 審查者：qa-reviewer
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**PASS**（單家審查；Codex 不可用，依 CEO 決策 #58）。無 critical/high，無 BLOCKING_ISSUES。

## 各部門回報
**A. commit 1（註解）**：`1faae4a` 對 `f6aff2c` 的 `-U0` diff 只有 `gap_check.py` 第 180 行一行。新行等於舊行刪去 `; replaces the cg2_register.py line`。tests 零差異。ruff／mypy 結果讀 devops 交件（全綠）。

**B. commit 2（regex）**
- `--name-status` 全範圍只有兩個檔：`gap_check.py`、`test_gap_check_logic.py`，皆為 M。
- `gap_check.py` 只動第 90 行。STOP 字面與 `env_file_sets_db_path` 本體不在 diff 內，故零差異。
  - 函式仍是 `open(..., encoding="utf-8-sig")` 加 `ENV_KEY_PATTERN.match(line)`，只比對鍵、不讀值。
  - `test_ast_the_env_file_is_only_searched_for_the_key_never_read_for_values` 不在 diff 內，零差異。
- `tests/fixtures/` 零差異（`--stat` 無輸出）。
- 新增測試含 3 個補例：`export\tSTOCK_DESK_DB_PATH=/x`、`EXPORT STOCK_DESK_DB_PATH=`、`  # export STOCK_DESK_DB_PATH=/x`（反例）。
- BOM 正例用 `"﻿..."` 跳脫寫法。新增行（699 行之後）無非 ASCII 字元，檔內 8 處非 ASCII 都是舊有的中文與 `é`。
- **一次性人工核對**：
  - gap_check 第 90 行：`re.compile(r"^\s*(?:export\s+)?STOCK_DESK_DB_PATH\s*=", re.IGNORECASE)`。
  - `claims.py:294`：`re.compile(rf"^\s*(?:export\s+)?{DB_PATH_ENV_VAR}\s*=", re.IGNORECASE)`，`claims.py:147` 的 `DB_PATH_ENV_VAR = "STOCK_DESK_DB_PATH"`。
  - 展開後 pattern 字面與 flags 完全相同。

**C. 測試品質**
- 正例 9 個：基本、空白、`export`、多空白、小寫、混合大小寫、tab、空值、BOM。
- 反例 8 個：註解、`# export`、後綴、前綴、`exportSTOCK`（無空白）、無 `=`、鍵在值內、無關祕密行。涵蓋合理。
- 全部只寫 `tmp_path`，不碰真實 `.env`。
- `test_the_env_file_key_pattern_flags_and_source` 釘死 pattern 字面，是刻意的對齊釘子，不算 tautology。
  - [可維護性][low] 它會讓日後任何合理調整 regex 都要同步改測試。這是與 claims 對齊的有意設計，可接受。

**D. 凍結基準**：`pipeline_acceptance_bat_frozen.txt` 與 `.gitattributes` 在三個 commit 之間零差異（fixtures 目錄零差異，且全範圍只有兩個檔被改）。

**E.** diff 中無 model ID 與祕密（反例的 `TOPSECRETVALUE` 是假值）。兩個 commit 訊息合乎 Conventional Commits、繁中。

## 驗證
實際執行的指令（皆在 `/home/user/AICompany`，皆為單一 `git diff`）：
- `git diff f6aff2c 243596c --name-status`
- `git diff f6aff2c 1faae4a -U0`
- `git diff 1faae4a 243596c`
- `git diff f6aff2c 243596c --stat -- apps/stock-desk/backend/tests/fixtures`

其餘用 Grep／Read 讀兩邊工作樹原始碼與 devops 交件。

devops 交件宣稱：新增 18 個測試（9 正例＋8 反例＋1 釘 pattern，與我數的相符），gap_check 兩個測試檔 221 passed，ruff、format、mypy 全綠。

沒有查證的事：
- 沒有自行跑 pytest、ruff、mypy，這些結果採信交件。
- 沒有逐字節比對 `gap_check.py` 的 LF 雜湊，也沒有驗證 `script_sha256_lf` 的新值。
- 沒有核對兩份 tech-architect 裁示全文逐條，只依任務敘述的 1～7 條重點核對。
- 沒有跑 `scripts/validate_agents.py`；本次沒有觸及 `.claude/` 或唯讀判準常數。

## 下一步
可進 risk-gate／合併流程。合併後 `script_sha256_lf` 以新 head 為準，需確認其引用處與新 head 一致（devops 交件已提過這點）。

## 唯讀權限判準常數
未觸及。本次 diff 只動 `apps/stock-desk/backend/` 下兩個檔案，不含 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的任何異動。

## Verdict
PASS
BLOCKING_ISSUES=false
