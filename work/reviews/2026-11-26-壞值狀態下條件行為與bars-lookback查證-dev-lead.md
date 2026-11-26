# 壞值狀態下的條件行為與 `/api/bars` lookback 查證（dev-lead）

> 依據：`work/reviews/2026-11-26-RC772補起草逐字審RC800至RC809-風控.md` 的 RC-802、RC-806、RC-809。
> 分支：`product/stock-desk`（HEAD `284d1b0e`）。共用壞值判斷 `evaluateDailyBarsUsability` 只在 `fix/technical-section-unusable-bars`（RC-695，未合併），用 `git show` 唯讀查看。
> 本次只讀：沒有改任何程式檔，沒有 commit，沒有連網，沒有讀 DB 或 `.env*`。

---

## 本次結論

1. **lookback 一致（RC-809 前提成立）。** 個股頁的 `/api/bars`、`/api/signals`、`/api/advice` 三支都沒有帶 `lookback_days`，視窗都是後端的 540 天。
2. **成交量條件（RC-802）：照樣判定。** 只要有 20 根以上 bar，而且量的標準差不是 0，壞值狀態下仍然會判成「成立」或「不成立」，不會是「無法判定」。依 RC-802，volume 要和 momentum 一起改，放進 PR-β。
3. **規則條件（RC-806 第 1 點）：要看壞值落在哪一根。**
   - **最新一根的 close 壞掉：** 後端建議卡回 `insufficient_data`，前端這條是「無法判定」，沒有問題。
   - **其他壞值情形：** 包括較早的 bar 有 close、high、low 壞值，或最新一根只有 high、low 壞值。這時後端照樣用含壞值的 signals 算規則。持有中、又沒有命中防禦型規則時，前端會判為 **「成立」**。風控擔心的放心型輸出確實存在。

## 各部門回報

### dev-lead

**一、前端 `/api/bars` 的 lookback（RC-809、PR-α 前置）**

- 個股頁只在一個地方發出 `/api/bars`：
  - `frontend/app/position/[symbol]/page.tsx:95` 呼叫 `useBars(symbol, market, true)`；
  - `frontend/app/lib/queries.ts:216-223` 的 `queryFn` 是 `getBars(symbol, market)`，**沒有傳第三個參數**；
  - `frontend/app/lib/api.ts:294-297` 只在 `lookbackDays !== undefined` 時才加 `lookback_days`，所以實際送出的請求只有 `?market=`。
  - 在 `frontend/app` 底下 Grep `getBars(`，除了測試以外只有 `queries.ts:219` 這一處。也沒有其他地方直接用 `fetch` 打 `/api/bars`。
- 後端的預設值：
  - `backend/app/api/bars.py:87` 是 `lookback_days = DEFAULT_LOOKBACK_DAYS`，`:89-95` 算出 `[today − lookback_days, today]`；
  - `backend/app/api/signals.py:45` 是 `DEFAULT_LOOKBACK_DAYS = OBSERVATION_LOOKBACK_DAYS`；
  - `backend/app/signals/window.py:22` 是 `OBSERVATION_LOOKBACK_DAYS = 540`。
- 另外兩支：
  - `/api/signals`：`queries.ts:210` 呼叫 `getSignals(symbol, market)`，也沒有帶 lookback。後端 `signals.py:92` 預設 540。
  - `/api/advice`：`api.ts:300-303` 本身就不收 lookback 參數。後端 `advice.py:187` 固定用 `DEFAULT_LOOKBACK_DAYS`，也是 540。
- 結論：三支端點的視窗都是 540 天，取數都走 `load_bars`。PR-α 的前置條件「實際視窗等於 `DEFAULT_LOOKBACK_DAYS`」成立。
  - 唯一的差異是每支請求各自取一次 `date.today()`。三支請求如果剛好跨過午夜，視窗會差一天。依 RC-809，這種差異已經由「可能」涵蓋。

**二、成交量條件（`entryObservation.ts:97-103`，RC-802）**

- 讀的欄位：`signals.technical.volume_zscore`，只在 `status === "ok"` 時取 `last.zscore`（`:98-99`）。`volumeZBand` 在 `indicatorBands.ts:50-55` 只排除 `null` 和非有限值。
- signals 怎麼傳進來：`page.tsx:143` 只看 `signals.data?.status === "ok"`。在 RC-695 分支上，`page.tsx:153-158` 也一樣，不受 `technicalCollapsed` 影響。
- 後端 `/api/signals` 不做壞值把關：
  - `signals.py:96-127` 只在完全沒有 bar 時回 `insufficient_data`，其他情形一律 `status="ok"`，把整批 bar 交給 `compute_signals`。
  - 它和 advice 不同，**沒有** `usable_price` 檢查。
- `volume_zscore` 只用成交量：
  - `technical.py:410-411` 的 `columns=[VOLUME]`，`:425-429` 只對 `frame[VOLUME]` 算 rolling mean 和 std；
  - `frame.py:55` 的 volume 直接取 `bar.volume`；
  - 條件不足時才回 `_insufficient`，也就是不滿 20 根（`:421-422`）。std 為 0 時 z 是 null。其他情形都是 `status="ok"` 加上數值 `last.zscore`（`:435-447`）。
- 資料層也不過濾壞值：
  - `PriceBar` 只檢查 `volume ≥ 0`（`data/interface.py:77-82`），close、high、low 沒有正值檢查；
  - `data/quality.py` 開頭說明「only detects and reports」，`load_bars` 也沒有過濾（`services/market.py:199-207`）；
  - 既有測試 `tests/test_unusable_close_f1.py:530-543` 斷言 `/api/bars` 會原樣回傳 close 為 0 或 −1 的 bar。
- **結果：** 前端判定壞值（任一根 close、high、low ≤ 0 或非有限）、volume 正常、根數 ≥ 20 時，這條**照樣判成「成立」或「不成立」**，並印出 z 值。這和 RC-766 第 4 項是同一類矛盾。依 RC-802，要和 momentum 一起在 PR-β 改成「無法判定」。
- 順帶一提（不在本次查證範圍）：`/api/signals` 沒有把關，最新一根 close 壞掉時，RSI 一樣是 `status="ok"`，而且是用壞值算出的數值。這和 PR-β 對 momentum 的前提一致。

**三、規則條件（`entryObservation.ts:111-124`，RC-806 第 1 點）**

- 前端邏輯：
  - `advice` 為空，或 `held !== true` 時，判為「無法判定」（`:116`）；
  - 否則逐筆檢查 `advice.matched_rules`，防禦型筆數為 0 就是 `met`（`:117-123`）；
  - `matched_rules` 是空陣列時，迴圈不會執行，結果也是 `met`。
  - `page.tsx:144-145` 只在 `advice.data?.status === "ok"` 時才傳入 card 和 held。
- 後端的把關**只看最新一根的 close**：
  - `advice.py:207` 是 `latest = newest if newest is not None and usable_price(newest.close) else None`；
  - `:208` 只有 `latest` 存在時才 `compute_signals(symbol, loaded.bars)`，算的是**整批 bar，含壞值**；
  - `:234-256` 在 `latest is None` 時回 `status="insufficient_data"`、`advice=None`；
  - 其他情形走 `:260` 的 `build_advice`，`:278-284` 回 `status="ok"`、`advice=card`。
- 規則怎麼算：
  - `engine.py:356` 呼叫 `build_context(signals, portfolio)`；
  - `context.py:141-166` 把 MA、RSI、KD、布林、volume z、drawdown 從 signals 攤平，`close` 取 `portfolio.close`，也就是那根可用的最新 close；
  - `engine.py:360-362` 逐條評估。`:188-190` 只有欄位是 `None` 才算 skipped，數值一律照比。
  - 引擎沒有任何「這批 bar 有壞值」的判斷。
- 分情形：

| 前端判為不可用的原因 | 後端 advice | 前端規則條件（持有、無防禦型命中） |
|---|---|---|
| 最新一根 close ≤ 0（或非有限） | `insufficient_data`、`advice=None`（`advice.py:234-245`） | **無法判定**（`entryObservation.ts:116`） |
| 最新一根 high 或 low ≤ 0，close 正常 | `ok`，用整批 bar 算 | **成立** |
| 較早某一根的 close、high 或 low ≤ 0 | `ok`，用整批 bar 算 | **成立** |

- 偏向哪一邊（讀碼推論，未實測）：
  - 視窗內有一根 close 是 0 或負值時，MA20、MA60 會被拉低。
  - 這會讓 `price_below_ma60`（reduce）和 `downtrend_ma_stack` 的比較結果改變（`rules/default.yaml:88-111`）。以 `price_below_ma60` 來說，均線被拉低，就更不容易命中。
  - 所以這個情形不只是「照算」，還可能把防禦型規則壓成沒命中，讓「成立」更容易出現，方向偏放心。
- **結論：** RC-806 第 1 點的疑慮在後兩列成立。要讓壞值狀態下的規則條件一律「無法判定」，前端得改讀共用的 `evaluateDailyBarsUsability` 結果，不能依賴後端。後端的把關範圍只有最新 close，比前端窄。
  - 依 RC-806，`ENTRY_BASIS_RULES.qualifier`（`entryObservationWording.ts:136`）要同步補字，由 creative 起草送風控。

## 驗證

- **實際跑過的：** 沒有跑任何測試。
  - backend 沒有 `.venv`，系統 python 也沒有 pandas。要跑就得 `uv sync`，這會連網並寫入 repo，本次不准。
  - frontend 沒有 `node_modules`，vitest 和 tsx 都不在。
- **已有的測試佐證（讀過程式碼，本次沒有執行）：**
  - `backend/tests/test_unusable_close_f1.py:348-382`：最新一根 close 是 "0" 或 "-1"、持有或未持有時，`/api/advice` 回 `insufficient_data`、`advice is None`，`compute_signals` 沒有被呼叫。這支撐上表第 1 列。
  - `backend/tests/test_unusable_close_f1.py:530-543`：`/api/bars` 原樣回傳壞的最新 close。這支撐「資料層不過濾」。
- **讀碼推論，未實測：**
  - `/api/signals` 在壞值下，`volume_zscore` 仍是 `status="ok"` 並帶數值；
  - 上表第 2、3 列 advice 回 `ok` 並照算規則；
  - MA 被拉低之後對防禦型規則的影響方向；
  - 非有限值（NaN、Inf 的 Decimal）能不能通過 `PriceBar` 和 JSON 序列化，我沒有查證，所以上表以 ≤ 0 為準。
- **讀過的檔案（`apps/stock-desk/` 底下）：**
  - frontend：`app/lib/api.ts:275-305`、`app/lib/queries.ts:200-235`、`app/lib/entryObservation.ts:1-186`、`app/lib/ruleDirection.ts:1-56`、`app/lib/indicatorBands.ts:50-55`、`app/lib/entryObservationWording.ts:129-137`、`app/lib/keyLevels.ts:85-125`、`app/position/[symbol]/page.tsx:94-96、136-150`；
  - RC-695 分支（`git show`）：`app/lib/dailyBarsUsability.ts`（全文）、`page.tsx:140-165、520-545`；
  - backend：`app/api/bars.py:1-100`、`app/api/signals.py:80-127`、`app/api/advice.py:150-300`、`app/signals/window.py`、`app/signals/frame.py:25-110`、`app/signals/service.py:50-112`、`app/signals/technical.py:136-160、380-451`、`app/advice/engine.py:90-100、160-260、325-450`、`app/advice/context.py:80-166`、`app/advice/rules/default.yaml`（Grep）、`app/data/interface.py:46-90`、`app/data/quality.py`（開頭和 Grep）、`app/services/market.py:147-207`、`tests/test_unusable_close_f1.py:55-102、320-385、495-545`。

## 下一步

1. **frontend-engineer（PR-β）：** volume 照 RC-802 和 momentum 一起改，壞值狀態下改成「無法判定」。判斷依據讀共用的 `evaluateDailyBarsUsability`，不能依賴 signals 的 `status`。
2. **product-manager：** 把 RC-806 第 1 點登記為另案。修法方向是讓前端的規則條件在壞值狀態下改讀共用函式，一律「無法判定」，不必等後端。
3. **creative-lead：** 起草 `ENTRY_BASIS_RULES` 頁尾的補字，送 risk-compliance-officer。
4. **tech-architect（給 ADR-δ 參考）：** 後端 `/api/signals` 和 `/api/advice` 對壞值的把關範圍不一致。signals 沒有把關，advice 只看最新 close，兩者都比前端共用函式窄。要不要在後端補一致的整批拒算，由 ADR 決定。本件不改。
5. **qa-reviewer / qa-automation：** 上面「讀碼推論，未實測」的各項，等有可以離線跑的環境之後，用 fixture 補測：較早一根 close 為 0、最新一根 low 為 0 這兩種情形下，`/api/signals` 的 `volume_zscore.status`，以及 `/api/advice` 的 `status` 和 `matched_rules`。
