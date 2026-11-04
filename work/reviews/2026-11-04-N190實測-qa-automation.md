# N-190 實測：同請求兩次載入遮蔽 S/P 評估

- 審查者：qa-automation
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-190 推論成立，而且比原推論更廣。
- 情境 (a)：同一次 `/today` 的結算載入是 `fresh`，評估載入是 `cached_stale`，該檔 S/P 當次不評估。
- 情境 (c)：休市日造成的「永遠沒有那天 bar」，會讓這檔從休市日起每一天的 S/P 都不評估。實測 5 個連續交易日全部如此。
- 這個現象不限於休市日，只要標的有到期未結算列就會發生。
- 原推論有一個前提沒寫出來：結算載入必須真的打到 live。這要靠 `judge()` 判 REFETCH，也就是快取最後一根 bar 早於 expected session，且已過 1 小時冷卻。情境 (a) 就是這樣設定的。

## 各部門回報（qa-automation 實測事實）
**組態與方法**
- 真實程式：`PlaybookService`、`MarketDataService`（`cache_first=True`、`scope="equity"`，admission、wording、currency 與 `deps.py` 的 TW ladder 同形）、`PriceBarCache`（tmp sqlite）、`judge` 與 TW freshness policy、`PlaybookStore`。
- 假的部分：只有 live primary（`FakeLive`，`source_id="twse"`）、index（`FakePriceService`）和注入的時鐘。
- 沒有 backups。`deps.py` 的 TW ladder 有 TpexAdapter 和 FinMindAdapter，這次未接。
- 前置狀態：先在前一個交易日 17:00 做一次正常載入，讓快取有資料和 fetch log；再把時鐘撥到實測當日 16:00（過 15:00 publish cutoff）。
- 每個標的先建 open batch、成本 100，bar 收盤價 80，所以 S1 條件成立。標的 2330 有 batch 1 和 batch 2 兩個 open batch，且帶一列到期 S1 賣單；2454 只有 batch 1。

**(a) 到期未結算列，預定執行日 = 週三 8/12，時鐘週三 16:00**

| 項目 | 2330（到期列標的） |
|---|---|
| 結算載入 | `fresh`（twse），最後 bar 8/12 |
| 評估載入 | `cached_stale`（twse），最後 bar 8/12 |
| 結算結果 | 該列有結算，`unsettled` 為空，batch 1 變 `closed` |
| engine 結果 | 沒有產生指令；warning 為「【停損今日無法評估】2330 資料狀態為 cached_stale…」；`rules_fully_evaluated=False` |
| 持倉 | batch 2 仍是 open、100 股，S1 本該評估卻沒評估 |

- 快取行為：結算載入觸發 live 並寫入 fetch log（`last_fetched_at` 更新），評估載入就落在 layer 0（`HAS_LATEST_SESSION`），live 只被呼叫一次，與讀碼一致。
- 推論成立。

**(b) 對照組 2454（無到期列），同一次請求**

| 項目 | 2454 |
|---|---|
| 結算載入 | 無（不在 pending 內） |
| 評估載入 | `fresh`（twse） |
| engine 結果 | 有評估，產生 S2 指令，沒有 data-gap warning |

- 對照組成立：差別只在有沒有到期列。
- (b2) 補充：對照組 2454 在同一天再打一次 `/today`（reload），評估載入變 `cached_stale`，且出現 data-gap warning。現有同日機制會附加說明稍早已評估過（`SAME_DAY_EARLIER_*` 之類的說明）。

**(c) 休市日：預定執行日 = 週四 8/13，假的 live 永遠沒有 8/13 的 bar，每天 16:00 請求**

| 請求日 | 2330 結算載入 | 2330 評估載入 | 2330 是否評估 | 到期列狀態 |
|---|---|---|---|---|
| 8/13 週四 | `fresh` | `cached_stale` | 否 | unsettled |
| 8/14 週五 | `fresh` | `cached_stale` | 否 | unsettled |
| 8/17 週一 | `fresh` | `cached_stale` | 否 | unsettled |
| 8/18 週二 | `fresh` | `cached_stale` | 否 | unsettled |
| 8/19 週三 | `fresh` | `cached_stale` | 否 | unsettled |

- 該列永遠留在 pending，從休市日起每個請求日都重複同樣的失敗。
- 因為 2330 每天都被抓進結算載入，而評估載入永遠落在 layer 0，2330 的 S/P 在這 5 天都不評估。
- 推論成立。

**意外觀察（輪替現象）**
- 在情境 (c) 裡，2454 在 8/13 評估後產生 S2 指令，預定執行日是下一個交易日，也就是 8/14。
- 所以 8/14 2454 有了到期列，那天 2454 也變成 `cached_stale`，沒被評估。
- 8/17 到 8/18 同樣出現。每天都產出指令的標的，會出現「評估一天、跳過一天」的輪替。
- 上面 (c) 表格只列 2330，2454 的輪替見腳本輸出。

## 驗證
- 全部在 worktree 內跑，HEAD 是 bf03a9c。
- 結果是 3 passed、1 deselected（情境 c 的 holiday 測試之前已單獨跑過，也是通過）。
- 腳本內的斷言記錄的是「觀察到的行為」，用來偵測行為漂移，不是正式規格。
- 安全：DB 都在 pytest `tmp_path`（`--basetemp` 指到 scratchpad），沒讀 `.env` 和 `data/*.db`。
- 主 repo `git status --short` 無輸出，沒有改動，沒有 commit。
- `wt_n168` 沒碰。

可重跑指令（venv 用主 repo 的）：
```
cd /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190/apps/stock-desk/backend
PYTHONPATH=$PWD /home/user/AICompany/apps/stock-desk/backend/.venv/bin/python -m pytest \
  /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/test_n190.py \
  -s -p no:cacheprovider --rootdir=$PWD -c /dev/null \
  --basetemp=/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/tmp
```
- 腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/test_n190.py`
- worktree 保留：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190`

## 下一步
- 缺口：沒有測 US ladder（冷卻 24 小時、cutoff 不同）、沒有接 backups、沒有測 16:00 之前的請求。
- 建議（非必要）：若要納入正式測試套件，可以把「到期列 + 同請求兩次載入」和「休市日連續多日」這兩個情境，改寫成使用 `tests/market_service_helpers.py` 的 `equity_service` 與固定時鐘的測試。目前套件內的 playbook 測試多半用 `FakePriceService`，不會經過真實的 cache_first 層，所以測不到這個現象。
