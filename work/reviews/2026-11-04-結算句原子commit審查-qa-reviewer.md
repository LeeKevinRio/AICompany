# 結算句原子 commit 審查（73f369e，PASS）

- 審查者：qa-reviewer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
審查 `git diff 346d5cb 73f369e`（1 個 commit，3 個檔案）。QB-15 的 7 條都已對照 diff 本身逐條檢查，無 critical 或 high 問題，結論 PASS。有兩項只能做到部分確認，列在下方限制，不影響 Verdict。

## 各部門回報
### Summary
這個 commit 只動 `wording.py` 的常數與註解、`n171a.json` 登記三筆差異、`test_playbook_wording.py` 新增一個逐字守門測試。內容與風控定稿、TA 釐清五一致。

### QB-15 逐條
1. 通過。`n171a.json` 的 `deltas` 恰好是 N171A-D1、D2、D3。
   - `scenario`/`body` 依序是 after_exit/today、authored/today、authored/today_again。
   - `path` 都是 `["settlement","warnings",0]`，`op` 都是 replace。
   - `before` 是舊句，`after` 是「判定」版。
   - `approval` 指向核准檔，`source` 指向風控終核和逐字核可檔。
   - 欄位與 E-19 第 1 點一致。diff 新增行中沒有 `<<`。
   - 工作樹裡沒有 `approved/` 目錄，所以無法直接 grep 全目錄，這項只憑 diff 判斷。
2. 通過。常數與註解、登記檔、逐字守門測試三件都在同一個 commit，且是該 commit 唯一的 3 個檔案。
3. 通過。`service.py`、golden、`GOLDEN_SHA256`、`test_api_playbook.py` 都不在 `--name-only` 清單內。頂層 `warnings` 沒有變動。
4. 通過。`wording.py` 的 diff 只有這個常數與它前面的 `#:` 註解，常數名不變。
5. 通過。測試 diff 只有新增，沒有刪除或修改任何既有行。新增的 `test_settlement_nothing_pending_is_the_signed_off_text_verbatim` 屬 E-20 第 2 點。
6. 守門測試沒有寫死舊字串，新測試斷言的是新值。
   - 可出貨原始碼中的舊字串：我在工作樹 grep，只剩 `pre_seam_responses.json` 的 3 處（:192、:488、:607），那是 golden，依 TA 裁定除外。
   - 工作樹的 `wording.py:621` 仍是舊值，因為工作樹不是這個分支的 tip。分支上該常數已由本 diff 替換。
   - 因為無法 checkout 分支，我沒有 grep 到分支 tip 上的所有測試。以子字串或否定式斷言舊句內容的測試，目前沒有看到。
   - 這些測試依 TA 在 E-21 的讀碼都不寫死本句：`test_api_playbook.py`（settle 三條與 `/today` 結算那一條）、`test_playbook_settle_on_request.py:111`、`:214`、`:376-381`。
   - 若分支上另有未揭露的此類測試，依 E-20 第 4 點會需要送核。
7. 唯讀權限判準常數：兩道檢查都沒有命中，見下節。

### 各檔問題
- `wording.py`：新值與風控定稿逐字相同，含「判定」、不含「處理」。無問題。
- `n171a.json`：無問題。
- `test_playbook_wording.py`：無問題。
  - [可維護性][low] 禁用詞清單裡的「已」「應」「需」是單字元比對，對這句靜態字串有效，目前不用改。

## 第二意見（Codex）
單家審查，Codex 待環境可用時補跑。`codex --version` 回傳 exit 127，環境裡沒有安裝。

## 唯讀權限判準常數
未觸及。
- 檔名檢查：`--name-only` 的 3 個檔案裡沒有 `scripts/validate_agents.py`。
- 內容檢查：diff 中沒有任何 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的新增或刪除行，也沒有 shadow 定義。
- 我是用完整 diff 輸出人工比對，沒有接 grep pipe，因為 Bash 被限制不能用 pipe。

## 驗證
- 實際執行的 Bash：`git diff 346d5cb 73f369e`、`git diff 346d5cb 73f369e --stat`、`git diff 346d5cb 73f369e --name-only`、`codex --version`。
- 其他讀取用 Read 與 Grep，沒有越界，沒有讀 `.env`，沒有碰 `data/*.db`。
- 沒有執行測試。
- 限制：
  - 工作樹不在該分支上，所以第 1、6 條的全目錄與全測試 grep 無法在分支 tip 上完成，只能靠 diff 與工作樹間接確認。
  - 交件說明檔 `work/reviews/2026-11-04-結算句原子commit交件-dev-lead.md` 沒有讀。

## 下一步
1. 回報 CEO。
2. 後續依 TA 的順序：
   - qa-automation 代跑完整測試，確認 `test_c6_*`、`test_i_*` 全綠。
   - qa-e2e 重新擷取 S-A（375、1280）與 S-D 的結算區 DOM 文字。
   - 風控書面複核。
3. 環境有 Codex 時補跑 `/review`，並在可 checkout 分支的環境對分支 tip 補做全樹 grep 舊字串與 `<<`。

## Verdict
PASS
BLOCKING_ISSUES=false
