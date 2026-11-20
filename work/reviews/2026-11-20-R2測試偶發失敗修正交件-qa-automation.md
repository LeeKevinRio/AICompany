# R2 一鍵檔測試偶發失敗修正交件

- 審查者：qa-automation
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
已修正並推送。分支 `fix/r2-first-run-symbol-substring`，head `f20743d810f60b17b4018462701c0c09ef4454a3`，只改了 `apps/stock-desk/backend/tests/test_r2_first_run.py`。全檔連跑 30 次全綠，ruff 和 mypy 也通過。

`git diff --stat origin/product/stock-desk HEAD`：
```
 apps/stock-desk/backend/tests/test_r2_first_run.py | 94 ++++++++++++++++++++--
 1 file changed, 89 insertions(+), 5 deletions(-)
```

## 做了什麼
**成因確認**
- paste-back 與主控台輸出含 `script_sha256_lf=`、`db_sha256_before=`、`db_sha256_after=`，值是 64 位十六進位雜湊。
- 這些行由 `scripts/n177_n190_backtrack_probe.py` 印出，r2 腳本只做白名單轉述。雜湊來自 hashlib 摘要，腳本不可能把代號放進這些欄位。
- 舊的 `symbol not in text` 是裸子字串比對，雜湊碰巧含 2330、2317、9958 時就會誤判。與產品行為無關。
- 檔內共 3 處同樣的子字串比對會碰到含雜湊的輸出，都已改掉：
  - 原第 194 行，paste-back 文字。
  - 原第 209 行，主控台輸出。
  - `test_probe_lines_are_matched_whole_and_bad_ones_dropped_and_counted` 內的 `("2330", "2317", ...)` 迴圈，它掃的是含真實雜湊的 paste-back 與主控台。其餘 `leak` 項目（ABC、secret、AAAA 等）維持原樣。
- 第 568 行附近的參數化測試掃的是 `n208_count` 的輸出，沒有雜湊，不需改。

**採用的修法：先遮雜湊值再做子字串比對**
- 新增 `_HASH_FIELD_RE = (?P<key>sha256\w*=)[0-9a-f]{64}(?![0-9A-Za-z])`、`_mask_hash_values` 與 `_leaked_symbols(text)`。
- 只遮「鍵含 sha256」且「值恰為 64 位小寫十六進位」的欄位。
- 不選邊界比對的理由：邊界比對會漏掉代號黏在英數字之間的洩漏，例如 `x2330y`。先遮再比對保留子字串的嚴格度，代號出現在 `=` 後、空白或逗號後、行尾、黏在文字中，都照舊抓得到。
- 「代號被印在 sha256 鍵的值裡」會不會漏：
  - 值不是恰好 64 位小寫十六進位，例如 `db_sha256_before=2330`、63 位、大寫、後面黏字元，就不會被遮，仍會被抓到。
  - 恰好 64 位十六進位且內含代號數字的值，無法與巧合區分，會被放過。這是此修法固有的殘餘。
  - 這種值由 hashlib 產生，腳本無法放入代號，且白名單測試已鎖死格式。

**新增的測試**
- `test_symbol_digits_inside_a_genuine_digest_are_not_a_leak`：確定性重現。手造含 2330、2317、9958 的三個雜湊行，斷言舊的子字串比對會命中，新檢查不會。
- `test_symbol_digits_in_a_real_digest_do_not_fail_the_console_check`：用 monkeypatch 讓 probe 的 stdout 帶含 2330 的雜湊，跑完整流程。斷言 paste-back 確實含 2330，但 paste-back 與主控台的新檢查都不報洩漏。
- `test_real_symbol_leaks_are_still_caught`（參數化 12 種）：
  - 獨立 token，如 `9958`。
  - `=` 後，如 `gate_affected_symbols=2330`。
  - 空白後、逗號串列。
  - 行尾，如 `line end 9958\nnext`。
  - 中括號內、黏在文字中（`x2330y`）。
  - sha256 鍵的值是裸代號（`db_sha256_before=2330`）。
  - 大寫 `A` 填充加代號的假雜湊。
  - 雜湊後黏 `e` 加代號。
  - 合法雜湊後接代號。
  - 合法雜湊換行後接代號。
- 我不小心加過 `sha256=` 加 60 個 a 再加 2330 這個案例，它本身是合法 64 位十六進位，屬上述殘餘，不該放進 teeth，已移除。

## 驗證
- 環境：Python 3.12 獨立 venv，`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/venv312-r2fix`，`uv sync --frozen --python /usr/bin/python3.12`。
- `tests/test_r2_first_run.py` 全檔重複 30 次，失敗 0 次，每次 58 passed。
- `ruff check` 通過。
- `ruff format --check` 為 546 files already formatted。
- `mypy app tests` 為 no issues found in 534 source files。
- 已推送到 origin，未 force push，未 rebase，未 amend。

## 沒有驗到的部分
- 沒有跑全套測試，依指示留待合併結果上跑。
- 沒有以 `-p random` 或大量重複去驗證「真實雜湊碰巧含代號」的機率情境，只以確定性 monkeypatch 重現。
- 沒有在 Windows 或實際 `.bat` 流程驗證。

## 下一步
交 qa-reviewer 審查（含 Codex 第二意見）。合併時請在合併結果上跑全套測試。
