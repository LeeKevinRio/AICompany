# N-190 scheduler／其他頁面預載情境實測

- 審查者：qa-automation
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

S1、S2、S3 三項推論在實測下都成立，但各有條件。實測沒有改動主 repo，也沒有 commit。

- **S1 成立**：標的在持倉簿內，且 TWSE 在 15:10 前已公布時，當天第一次 `/today` 的標的載入就是 `cached_stale`（ttl=True），S1 不評估，`directives=[]`。對照組同一條件下 `fresh`，S1 sell 正常產生。
- **S1′ 成立，而且比推論更糟**。TWSE 在 15:10 還沒公布時，到 16:00 `/today` 仍然看不到：
  - 15:10 的檢查把 cooldown（1 小時）鎖住，16:00 `/today` 回 `cached_stale`、ttl=False，最後一根 bar 是前一個交易日。
  - 16:30 排程重抓後，17:00 `/today` 變成 `cached_stale` ttl=True。
  - 兩種情況 S/P 都不評估。
- **S2 成立**：個股頁（`get_bars`）或訊號頁（`get_signals`）先載入同一檔，`/today` 標的就是 `cached_stale`，S1 不評估。
- **S3 成立**：訊號頁會順帶載入 `^TWII`，之後 `/today` 的指數是 `cached_stale`。實測看到三個後果：
  - M1 不評估。
  - 排程日 R 被順延，defer 計數 +1。
  - 防守模式沒進，S1 沒用 0.93 門檻。
- 條件限制：
  - 排程預載只在標的也在持倉簿時才會發生（負向對照 S1-neg 為 `fresh`）。
  - 排程器本身不載 `^TWII`；`refresh_market_data` 沒有載入指數的程式碼，指數預載只來自訊號頁等其他 consumer 與 sector board 的 TAIEX 參考。

## 各部門回報（qa-automation）

### 1. 讀碼確認

以 worktree bf03a9c 的 `apps/stock-desk/backend/app/` 為準：

- **同一個 cache、同一條 ladder**：
  - `deps.py:58` 的 `_default_cache()` 是 `lru_cache`，只有一個 `PriceBarCache`。
  - TW ladder、US ladder 與指數 service（`deps.py:149-190`）都吃這個 cache，都是 `cache_first=True`。
  - `scheduler.py` 的 `refresh_market_data` 用 `get_market_resolver()`，和 playbook（`deps.py:323`）是同一個 resolver 物件。
  - scheduler 與 playbook 都走 `load_bars`，所以是同一條 ladder。
- **範圍判定**：`data/service.py:766-768`（`_try_session_fresh_cache`）要求 `coverage.covered_start <= start`。scheduler 的 start 是 end 往前 540 天，playbook 是 180 天（`service.py:83`、`:941`），540 天涵蓋 180 天，所以 layer 0 命中。反過來，只抓短窗口的 consumer 不會預載。
- **指數 service**：`_default_index_resolver()` 把 `MarketDataService`（`scope="index"`、`cache_first=True`、共用 cache）包進 `IndexSeriesService`。`IndexSeriesService` 把 `fresh` 降為 `backup`，layer 0 命中則維持 `cached_stale`。
- **其他載入 `^TWII` 的路徑**：
  - 訊號頁 `api/signals.py:108`：窗口 540 天，且每次載入個股都會順帶載。
  - sector board 的 `taiex_reference_return`（`scheduler.py:445-460`）：窗口是 `(window[0], t)`，是短窗口。
- **ttl 欄位的語意**（`data/service.py:806-852`）：
  - `is_within_ttl` 在 `HAS_LATEST_SESSION` 時為 True。
  - `CHECKED_RECENTLY` 時為 False（此時 `cached_stale` 沒有最新一個交易日）。
  - `LoadedSeries` 沒保留這個欄位，engine 看不到。

### 2. 測試設計

- **真實程式**：
  - `PlaybookService`、`PlaybookStore`、`PriceBarCache`、equity 與 index 兩條 `MarketDataService` ladder（`cache_first`、admission、wording、currency 都是真的）。
  - `IndexSeriesService`、freshness policy、engine。
  - `app.scheduler.refresh_market_data(today=...)`，沒有模擬，直接呼叫。
  - `app.scheduler.taiex_reference_return`。
  - `app.api.bars.get_bars`、`app.api.signals.get_signals`，當成函式直接呼叫。
- **假的部分**：
  - 兩個 live provider（TWSE 替身、yfinance 指數替身），由 `available_through` 控制「交易所公布到哪一天」。
  - 排程器遍歷的 `get_position_store().list_all()`。
  - 兩個 route module 內的 `date.today()`，改成回傳測試時鐘。
  - 注入的時鐘。
  - 不連外，DB 都在 pytest `tmp_path`，路徑前綴已用 realpath 斷言。
- **前置步驟**：每個情境先用真的 scheduler 在週一 18:30 暖機一次，再用 playbook 載入暖指數。這代表系統已有前一天的資料，但沒有任何當天（週二）的預載。
- **衍生觀察，不是推論失敗**：指令的 `data_status` 在 `cached_stale` 情況下仍顯示 `fresh`，見下方「新現象」第 5 點。

### 3. 實測結果

載入欄位格式：`標的 status / ttl / 最後一根 bar 日期 / 該次 live 呼叫數`。`directives` 只列 playbook 帳本這次寫入的指令。除非另註，日期是 2026-08-11（週二，排程日）。

| 情境 | 標的載入 | 指數載入 | engine 結果 | 推論 |
|---|---|---|---|---|
| **對照組**：無預載，16:00 | 2330 `fresh` / None / 08-11 / 1 次 | `backup` / None / 08-11 / 1 次 | 有 `S1 sell` | 基準 |
| 對照組，5 分鐘後第二次 `/today` | `cached_stale` / True | `cached_stale` / True | 仍有 `S1 sell`（是前一次寫入的），但新增警示：「【停損今日無法評估】2330…cached_stale」 | 對應 b2 |
| **S1**：15:10 預載（已公布），16:00 `/today` | 2330 `cached_stale` / True / 08-11 / **0 次** | `backup` / 1 次 | `directives=[]`，S1 未評估 | **成立** |
| S1-neg：標的不在持倉簿 | `fresh` / 1 次 | `backup` | 有 `S1 sell` | 條件確認：需要在持倉簿內 |
| **S1′-a**：15:10 未公布，15:55 公布，16:00 `/today` | `cached_stale` / **False** / 最後 bar **08-10** / 0 次 | `backup` | `directives=[]`，S1 未評估 | **成立** |
| **S1′-b**：同上，16:30 排程補抓，17:00 `/today` | `cached_stale` / True / 08-11 / 0 次 | `backup` | `directives=[]`，S1 未評估 | **成立** |
| S1′-c：15:10 未公布，15:30 先打 `/today`，16:15 再打 | 15:30：`cached_stale` / False / 08-10。16:15：`fresh` / 1 次，S1 sell 產生 | 15:30：`backup`（最後 bar 08-10）。16:15：`cached_stale` / **False** / 最後 bar **08-10** / 0 次 | 15:30 時 `data_date=08-10`，非排程日。16:15 `mode=frozen`，M1 未評估 | 見新現象第 3 點 |
| **S2-bars**：個股頁先載（15:30），16:00 `/today` | `cached_stale` / True / 0 次 | `backup` | `directives=[]`，S1 未評估 | **成立** |
| **S2-signals**：訊號頁先載 2330，16:01 `/today` | `cached_stale` / True / 0 次 | `cached_stale` / True / 0 次 | `directives=[]`；同時 M1 未評估 | **成立**（同時觸發 S3） |
| **S3-R 對照**：排程日、2317 為 planned，無其他 consumer | 2317 `fresh` | `backup` / 1 次 | 無 R 指令（被現金 30% 下限擋下，見新現象第 4 點），defer 計數 **0** | 基準 |
| **S3-R**：訊號頁（看 2330，不在 playbook）先載 `^TWII`，16:01 `/today` | 2317 `fresh`（訊號頁沒載 2317） | `cached_stale` / True / 08-11 / **0 次** | `directives=[('2317',1,'M1','defer')]`，**defer 計數 0 → 1** | **成立：被順延並計次** |
| S3-R 第二次 `/today`（16:02） | 2317 也變 `cached_stale` | `cached_stale` | 仍是同一筆 M1 defer，計數維持 1，沒有每次請求累加 | 計數未隨請求增加 |
| **S3-def 對照**：2330 成本 100、收盤 92，指數連續 3 日以上低於月線 | `fresh` | `backup` | `mode=defense`、`defense_active=True`、`S1 sell`（0.93 門檻生效） | 基準 |
| **S3-def**：訊號頁（看 2454）先載 `^TWII` | 2330 `fresh` | `cached_stale` / True / 0 次 | `mode=normal`、`defense_active=False`、**沒有 S1**；改產生 `('2330',2,'M1','defer')`，defer 計數 +1 | **成立：翻轉** |
| S3-sector（有暖機的 `^TWII`）：`taiex_reference_return` 20 天窗口後 `/today` | — | `cached_stale` / True | 同 S3-R，M1 defer 計數 +1 | 成立，但前提是指數早已被暖過 |
| S3-sector 540 天窗口 | — | `cached_stale` / True | 同上 | 成立 |
| S3-sector-cold：`^TWII` 完全沒快取，只有 20 天窗口 | — | `backup` / **1 次**（coverage 起點 2026-07-22，不涵蓋 180 天，所以 playbook 重抓） | 無 M1 影響，defer 計數 0 | 窗口太短時**不成立**，推論要加條件 |

警示全文（逐字，`cached_stale` 情境下出現的）：

- 「加權指數資料狀態為 cached_stale（來源 yfinance），M1 今日未評估、沿用前一狀態；當日不新開倉。」
- 「加權指數資料狀態為 cached_stale，尚無前一次快市判定可沿用，本次以「非快市」處理；資料缺漏不會使系統首次進入快市。」
- 「今日為排程日，R 系列進場改為順延並計入順延次數（逐批列示）。」
- 「【停損今日無法評估】2330 資料狀態為 cached_stale（來源 twse），依鐵律⑤當日不產生指令；本檔目前持有部位，停損/停利（S/P 系列）今日無法依規則評估。」
- 「2330 本次資料狀態為 cached_stale，本次未重新評估這檔；指令帳冊中這檔的 1 筆買賣指令，是同一預定執行日稍早這檔資料可用時的評估已產生的指令，未因本次資料狀態而取消或修改，仍會照常以預定執行日開盤價在帳冊判定。」

完整逐字輸出：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/out_sched.txt`（收盤 88，純 S1）。

### 4. 驗證（可重跑指令）

```
cd /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190/apps/stock-desk/backend
PYTHONPATH=. /home/user/AICompany/apps/stock-desk/backend/.venv/bin/python -m pytest \
  /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/test_n190_sched.py \
  -s -q -p no:cacheprovider \
  --basetemp=/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/tmp2
```

- 結果：`15 passed`。
- 這些測試是觀察性質，沒有斷言實測結果，是用 `-s` 看輸出。
- 設環境變數 `N190_PX=80` 可改成收盤 80。此時 engine 在對照組會發 `S2` 並進入 `frozen`，不是 `S1`：收盤 80、成本 100 同時觸發 S2/S3，這是「S1 條件成立」的細節。收盤 80 的完整輸出存在 `scratchpad/n190/out_sched_px80.txt`。
- 前一輪的 `test_n190.py` 沒動，我重跑確認 4 個仍 pass。

## 下一步

沒有發現需要修的 bug，以下是新現象：

1. **S1′ 比 S1 更糟**。未公布的 15:10 檢查本身就會把 cooldown 鎖住。從 15:10 到 16:10 之間的 `/today`，標的與指數都可能回到 `cached_stale` / ttl=False 的前一日資料（S1′-a、S1′-c）。
2. **S3-def 與 S3-R 共用同一個源頭**：任何訊號頁瀏覽都會翻掉 M1。
3. **S1′-c 的指數問題**：15:30（TWSE 還沒公布）的 `/today` 會把指數的 cooldown 鎖住，導致 16:15 的指數仍是前一日 `cached_stale`，M1 當天不評估。
4. **現金下限擋 R**：S3-R 對照組沒有 R 買進，是被「鐵律①現金 30%」擋掉。所以 R 的「正常路徑」沒有被真正跑到，只能比 defer 計數 0 對 1。
5. **`Directive.data_status` 顯示 `fresh`** 即使當次載入是 `cached_stale`（例如 S3-R 的 M1 defer 指令），這是 interface 層的問題。
6. **前提限制**：我的暖機把週一資料與 `^TWII` 都先載好。若 `^TWII` 完全沒快取、其他 consumer 只載短窗口，S3 不會成立（S3-sector-cold）。

建議：架構評估的「第一包沿用結算序列」對 S1、S1′、S2、S3 完全無效，因為預載發生在 `/today` 之前。主路徑要靠第二包（engine 接受 `cached_stale` ∧ `is_within_ttl=True`）。但第二包解不了 S1′-a 與 S1′-c 的 ttl=False 情況：那時資料真的是前一日的，這屬於 cooldown 設計與公布時間的問題，需要另外處理。

產出檔案（皆在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/`）：
- `test_n190_sched.py`（新增的實測腳本）
- `out_sched.txt`（收盤 88 的完整輸出）
- `out_sched_px80.txt`（收盤 80 的完整輸出）
- `test_n190.py`（前一輪，未改）
