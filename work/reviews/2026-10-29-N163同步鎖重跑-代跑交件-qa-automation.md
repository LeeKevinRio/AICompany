# N-163 同步鎖 74979dd 重跑代跑交件

- 審查者：qa-automation
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# 74979dd 重跑交件（qa-automation，只交事實，不下 Verdict）

## 輸出位置
- 輸出目錄：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n163_out/lock_rerun/`
- 事實檔：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n163_out/facts.md`，已加「74979dd 重跑」一節。
- 原始資料：`lock_rerun/facts-L.json`。
- runner 原文與執行腳本：`lock_rerun/e2e_n163_lock_runner.js`、`lock_rerun/e2e_n163_run_L.sh`。
- stdout：`lock_rerun/runner_stdout_L.txt`。
- 截圖：`lock_rerun/*-L3-pending-after-tabs.png`（兩種尺寸各一張）。

## 環境與紅線
- 受測樹 detached HEAD 是 `74979dd`。重新做了 production build（exit 0）。
- 全程與結束時 `git status --short` 都是空的，沒有 commit。
- 後端使用 scratchpad 內的拋棄式 DB：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n163_db_ab/stock.db`。`backend_lock_env_proof.txt` 記錄了行程實際的三個 DB 路徑，都在 scratchpad 下。
- 沒有讀 `.env`，沒有碰 `backend/data/*.db`，沒有安裝任何東西。
- 儀器 provenance 與上一輪相同：playwright 1.63.0（`/opt/node-tools/...`）、chromium 153.0.8010.12（`/opt/pw-browsers/...`），stdout 無 `ABORT`。

## safetyChecks 結果
- `safetyChecks` 共 54 筆，全部一致。
- `finalSafety`：postEvents 60、postHits 60、backendLogExitLines 0（baseline 0）。
- `backend_lock.log` 裡沒有任何 `emergency-exit` 行，只有 109 次 `GET /today`。
- 瀏覽器端 emergency-exit 回應共 60 筆（200×54、500×6），全是 mock。
- console 有 6 筆，都是 L2a 的 mock 500，內容為 `Failed to load resource: the server responded with a status of 500 (Internal Server Error)`。requestfailed 為 0。

## 1. A2 快速重複觸發：修鎖前後對照
每種方式每個尺寸各 4 次，mock 200 延遲 3000ms。數字是最終 emergency-exit POST 累計。修鎖前是 3ceef60 的上一輪資料，修鎖後是 74979dd。

| 觸發方式 | 尺寸 | 修鎖前 | 修鎖後 |
|---|---|---|---|
| `locator.dblclick()` | 1280×900 | 2,2,2,2 | 1,1,1,1 |
| | 375×812 | 2,2,2,2 | 1,1,1,1 |
| `page.mouse.click` ×2，不等待 | 1280×900 | 2,1,1,1 | 1,1,1,1 |
| | 375×812 | 1,1,1,1 | 1,1,1,1 |
| 頁內同 task 內 `el.click(); el.click()` | 1280×900 | 2,2,2,2 | 1,1,1,1 |
| | 375×812 | 2,2,2,2 | 1,1,1,1 |
| 頁內 click → `setTimeout(0)` → click | 1280×900 | 1,1,1,1 | 1,1,1,1 |
| | 375×812 | 1,1,1,1 | 1,1,1,1 |
| Enter 連按兩次，不等待 | 1280×900 | 2,2,2,2 | 1,1,1,1 |
| | 375×812 | 2,2,1,1 | 1,1,1,1 |
| `dblclick()` 後立刻 `mouse.click`（本輪新增） | 1280×900 | 無資料 | 1,1,1,1 |
| | 375×812 | 無資料 | 1,1,1,1 |

- 修鎖後 6 種方式 × 4 次 × 2 尺寸共 48 次，最終 POST 全部是 1。
- 瀏覽器的 POST request 事件數與 route handler 命中數一致，每次 mock 回應後對話框都關閉。
- 同 task 兩次 click 時，按鈕在兩次 click 後仍沒有 aria-disabled 屬性（`ariaDisabledAfter: null`），但 POST 只有 1。

## 2. 鎖不卡死（兩種尺寸結果相同）
- **mock 500 後重試**：連續點 3 次「確認送出全部出清」，POST 依序從 0 到 1、2、3，每次都剛好 +1。
  - 每次點擊後 300ms，兩顆按鈕 `aria-disabled="true"`，按鈕文字是「取消」「送出中…」，焦點在「送出中…」。
  - 每次錯誤回來後，錯誤文字是「全部出清送出失敗：Internal Server Error」，焦點在「確認送出全部出清」，兩顆按鈕沒有 `aria-disabled` 屬性。
- **mock 200 後再送一次**：重新開啟流程、勾完 4 個核取框再送，POST 從 1 變 2（+1），也進入送出中，完成後焦點回「全部出清」。

## 3. A1 回歸（兩種尺寸結果相同）
- 送出前兩顆按鈕的 `aria-disabled` 屬性不存在（`getAttribute` 回 `null`），也沒有 `disabled` 屬性。
- 送出中兩顆按鈕 `aria-disabled="true"`，沒有 `disabled` 屬性，`disabled` property 為 false。
- Tab 與 Shift+Tab 各 6 次，activeElement 在「取消」與「送出中…」之間交替，12/12 都 `inDialog=true`，`aria-disabled` 皆為 `"true"`。每步對話框都在，POST 累計都是 1。
- 完成後焦點在「全部出清」。失敗後兩顆按鈕的 `aria-disabled` 屬性回到不存在。

## 無法完成與收尾
- 無法完成的項目：無。
- 我只用 `kill -TERM -- -<pgid>` 關掉本輪自己的後端（15809）與前端（15810），事後 `ps` 查無 uvicorn 與 next-server。
- 另提醒：舊的 `facts.md` 與前一輪交件仍描述 3ceef60 的行為，修鎖後的對照請以本節為準。
