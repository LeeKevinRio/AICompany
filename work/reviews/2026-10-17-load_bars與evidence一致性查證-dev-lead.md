# load_bars 回傳列是否一定在 market_session_evidence 內（dev-lead 唯讀查證）

- 審查者：dev-lead（本次唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**不保證，答案是有條件的。** 在正式接線下，`load_bars` 回傳的每一列，在函式回傳的當下都已經在 `price_bars_cache` 裡（同市場、同日期），這點已查證。但「一定落在同一次 `market_session_evidence` 讀取結果內」目前不成立：這個讀取函式還沒實作，和 `load_bars` 也不共用 transaction，而且下面列了 6 條會出現差異的路徑。

不過結構性質其實不需要這麼強的前提，這是推論，理由見下一段第 C 點。只要把前提句改成以日期為單位、只限 R 內的日期，再加一條「evidence 讀取一律在 `load_bars` 之後」，就不需要多讀一次 evidence，也不會觸發 K-16。

## 依據

### A. 已查證：每條回傳路徑都先寫進快取或本來就從快取讀
- 正式接線中，四個端點都用 `get_market_resolver`，它只回傳 `MarketDataService`，而且所有 ladder（含 index）共用同一個 `PriceBarCache`。`get_price_bar_cache` 回傳的也是同一個物件。
  - 依據：`app/api/deps.py:51-59`、`:117-140`、`:172-183`、`:354-366`。
- 即時抓取成功（非增量）時，先執行 `self._cache.put(result.bars, ...)`，接著才 `bars = result.bars`，最後在 `:411-419` 回傳。
  - 回傳的是 provider 原始的 list，沒有用 `[start, end]` 過濾；但它和寫進快取的是同一批，所以超出範圍的列也都已經寫入。
  - 依據：`app/data/service.py:352-356`。
- 增量路徑先 put，再用 `self._cache.get(...)` 讀回來，回傳的是讀回的結果。依據：`service.py:362`、`:385`。
- layer 0、退回快取、只讀快取這三條路徑，回傳的都是 `cache.get` 讀出來的列。依據：`service.py:695`、`:455`、`_fall_back_to_cache` 從 `:931` 起。
- 快取寫入失敗時不會照樣回傳。
  - `put` 外面沒有 try，`put` 本身也沒有吞掉例外（`cache.py:212-231`）；只有 provider 呼叫被 try 包住（`service.py:912-920`）。
  - 所以寫入失敗時例外會一路往上拋，`load_bars` 不會回傳任何列（`app/services/market.py:171`）。
- 幣別閘門擋掉的列，既不會寫入也不會回傳。依據：`service.py:334-351`。

### B. 已查證：可能不在同一次 evidence 讀取內的路徑
1. **evidence 讀取還不存在。**
   - 在 `app/` 裡 grep `market_session_evidence`、`classify_session_evidence`、`row_date_anomaly`，結果都是 0 筆。
   - `PriceBarCache` 每個方法都自己開連線、自動 commit（`cache.py:153-166`、`:212`、`:485`），兩次呼叫之間沒有共用的 snapshot。
   - 因此「同一個 transaction」在現有架構下不可能成立，只能靠讀取順序來保證。
2. **讀取順序。** 如果 evidence 在 `load_bars` 之前讀，這次即時抓到並寫入的列就不會在 evidence 裡。
   - 現在四個端點都是第一步就呼叫 `load_bars`：`app/api/bars.py:89-96`、`signals.py:94-96`、`advice.py:156-165`（之後才在 `:166` 呼叫 `build_summary`）、`leverage.py:95-97`。
   - 但 ADR 沒有規定 evidence 讀取要放在 `load_bars` 之後。
3. **窗口不一致。**
   - evidence 的範圍是 `start = max(該市場各列 price_date 的最小值 − 7, D − 400)`，`end = D`（ADR-0028 `:259-261`）。
   - `load_bars` 的回看天數都超過 400 天：
     - signals、advice、bars 預設 540 天（`signals.py:45`、`app/signals/window.py:22`）；
     - `/api/bars` 最多可以開到 2000 天（`bars.py:87`）；
     - leverage 是 1200 天（`leverage.py:43`）。
   - 另外，端點的 `end` 用的是伺服器的 `date.today()`，不是 VS-1 時區下的市場日 D（`bars.py:89` 等處）。
4. **市場鍵由 bar 自己決定。**
   - `put` 寫入時用的是 `bar.market` 和 `bar.symbol`，不是請求帶的市場（`cache.py:196-197`）。
   - `_try_provider` 不會把 market 傳給 provider（`service.py:913`），而且整段 ladder 沒有任何地方檢查 `bar.market == market`。
   - 目前各 adapter 都把市場寫死（`twse.py:179`、`tpex.py:330`、`finmind.py:172`、`alpha_vantage.py:397`、yfinance 個股固定 `"US"` 在 `yfinance.py:172`），所以這條**目前到不了**，但也沒有任何機制擋住。
5. **並行刪除。**
   - `price_bars_cache` 唯一的刪除點是 `delete_by_source`（`cache.py:505-533`），由 demo seeder 的清除流程呼叫（`app/demo/seed.py:489`）。
   - 如果刪除發生在 `load_bars` 和 evidence 讀取之間，已回傳的示範列就不會在 evidence 裡。
   - API 和 scheduler 雙寫入只做 upsert（`cache.py:219`），不會讓某個日期消失。
6. **非快取的 `PriceService`。**
   - `load_bars` 收的是 `PriceService` protocol（`market.py:31`），不限定一定是 `MarketDataService`。
   - API 測試的 `FakePriceService`（`tests/api_helpers.py:80`、`:116`，在 `:200` 覆寫 `get_market_resolver`）完全不寫快取。CST-11 的 fixture 如果沿用它，列就一定不在 evidence 裡。

### C. 推論：哪些差異真的會破壞結構性質
這段根據 D-9 第 3～5 點推導（ADR-0028 `:244-257`）：
- 第 4 點說，只要那天有任何一列（包括示範資料），那天就至少是 unconfirmed，`is_session` 依週一至週五規則判斷。
- 第 5 點的表格裡，只有「∈ R，而且是 absent」這一格會讓平日的 `is_session` 變成 False。
- 第 4、5 點只看日期，所以結構性質需要的是「同市場、同 `trade_date` 至少有一列在 evidence 內」，不需要是同一列。

由此可知：
- R 是由窗口內 confirmed 的日期構成，所以 R 一定在 `[start, D]` 之內。B-3 那些超出窗口的列都在 R 外，會走週一至週五規則，**不會破壞**結構性質。
- 真正會破壞的只有 B-2、B-4、B-5、B-6，而且還要那天剛好在 R 內，並且同市場其他 symbol 那天都沒有列。
- 出錯時的方向是**多標** `unconfirmed_session`（多揭露），不會少標。

## 驗證
- 用 scratch 探針測試確認上面的路徑。檔案在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/probe/test_probe_load_bars_cache.py`，只用 `tmp_path`。
  - 指令：`PYTHONPATH=. uv run pytest -q -s -p no:cacheprovider --rootdir=. <該檔>`
  - 結果：**6 passed**。
  - (a) 即時抓取路徑：回傳的列，包括超出範圍的 2023-12-29，全都在快取的市場日期內。
  - (b) 退回快取路徑：回傳的列都來自快取。
  - (c) `put` 丟出 `OperationalError` 時，`load_bars` 跟著拋出，沒有回傳任何列。
  - (d) bar 的 `market` 標成 US 時，TW 請求仍然回傳這一列，但它寫在 US 底下，TW 的日期集合是空的。
  - (e) `FakePriceService` 回傳的列，快取裡是空的。
  - (f) 先 `load_bars` 再 `delete_by_source`，已回傳的那個日期就從快取消失了。
- 既有測試：`uv run pytest -q -p no:cacheprovider tests/test_services_market.py tests/test_service.py tests/test_f9b_load_bars_wd.py` 結果是 **68 passed, 1 warning**。這些測試都受 conftest 的 sentinel 隔離（`tests/conftest.py:245-262`）。
- 沒有碰 `data/*.db`，也沒有讀 `.env`，沒有改或 commit 任何檔案。`git status` 裡那筆 `work/research/2026-10-15-...事先宣告草案.md` 的修改在我查證之前就有了，不是我改的。
- 查證和推論的界線：B-1～B-6 和第 A 段都是讀碼加探針測試確認的。C 段，以及「目前到不了」「出錯方向是多揭露」這兩個判斷，是依 ADR 條文推導的。evidence 還沒實作，所以實際的讀取順序沒辦法驗證。

## 下一步（只是建議，沒有改檔）
1. **CST-10 結構性質的前提句**建議改成：
   > 「`basis_for(trade_date) ≠ official` 的平日列：若 `trade_date ∉ R`，`row_date_anomaly` 必為 None；若 `trade_date ∈ R`，前提是同一次 `market_session_evidence` 讀取結果內至少有一列同市場、同 `trade_date` 的列（不要求同一列），此時必為 None。」
   - 這樣就不必假設「`load_bars` 的列一定在 evidence 內」，原本〔未查證〕那句可以改成引用本次查證。
2. **新增實作約束**（供 CS-26 或 CST-11 使用）：
   - 每個端點的 evidence 讀取一定要在 `load_bars` 回傳之後，而且只讀一次。
   - 測試用呼叫順序 spy 斷言。
   - 這樣可以消掉 B-2，又不必多讀一次，**不會觸發 K-16**。
3. **CST-11 的 fixture**：要用 `MarketDataService`，並接上和 `get_price_bar_cache` 同一個 `tmp_path` 快取；如果用 `FakePriceService`，就要另外把同樣的列 seed 進快取。這是針對 B-6。
4. **B-4 防線**（選擇性）：在 ladder 加「`bar.market == market` 否則拒絕」的閘門，這屬於收緊，要另案排。或者先把它列在已知限制，記為「adapter 寫死市場、目前到不了」。
5. **B-5**：列為已知限制，可以接受。它只會在操作者手動清除示範資料、而且剛好和請求同時發生時出現，方向是多揭露。
6. **K-16 何時適用**：上面這些缺口本身不會觸發 K-16。但如果實作改成「`load_bars` 之後再讀一次 evidence」，或「把 `load_bars` 的列併進日曆輸入」，就會觸發：前者踩到 K-16 的「evidence 讀取超過一次」；後者等於另建日曆或增加 D-9 第 7 點以外的輸入（ADR-0028 `:328` 第 11 點）。這兩種情形都要回送風控，不得自行處理。
