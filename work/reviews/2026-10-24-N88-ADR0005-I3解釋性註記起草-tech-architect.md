# N-88 ADR-0005 I-3 解釋性註記起草（附 N-93 ADR-0024 重審草稿）

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

1. **方案 A 只需要對 I-3 加一則解釋性註記，不必修訂 I-3。CEO 知悉即可。** 字面衝突只有兩處：I-3 末句「呼叫端必須經由 `IndexSeriesService` 取得結果，不得直接持有底層 service」，以及決策三第 5 點「指數序列走獨立的 `IndexSeriesService`」（L185，這處之前沒有人點出，這次一併涵蓋）。
   - 末句自己寫了理由：`MarketDataService` 會把主來源成功一律標成 `FRESH`，所以要經 `IndexSeriesService` 降回 `BACKUP`。
   - 重放取數函式不經 `MarketDataService`，在 `app/services/index.py` 內直接標 `BACKUP`。這和 `BACKUP` 的定義「即時取自備援來源」完全吻合。
   - I-3 的三項決定一字不動，而且全部適用於這個函式：不以 `FRESH` 呈現、降級只往悲觀方向、`BACKUP` 專指即時取自備援來源。
   - 註記另外寫明了一條界線：一旦要讀快取、要標 `FRESH`、輸出要進 views 或 API，或開放給第二個呼叫端或第二個代號，就屬於修訂 I-3，須經 CEO 裁決。
2. **新發現的衝突，先前的方案比較（包括我上一份）漏掉了：方案 A 也碰到 ADR-0024（accepted）。**
   - 該 ADR「被此決策約束的事」寫：「日後新增 `load_bars` 以外直接取日線的程式路徑，須經 `MarketDataService`（D-1），不得自行繞過。」失效條件 7 寫：「新增任何不經 `MarketDataService` 取得日線價格的 production 路徑 → 重審 D-1」。
   - 重放取數函式正好是這樣一條路徑。
   - 我判斷實質保護沒有損失：yfinance 指數路徑的幣別寫死在 `INDEX_SYMBOL_METADATA`，不讀上游（ADR-0024 D-6 把 role 2 排除），正式設定下經服務層也不會觸發幣別閘門（D-4）；快照也不帶幣別、不用於估值。
   - 但字面上要依失效條件 7 做重審並留紀錄。我在第二節 D 附了草稿，建議登記為新追蹤項 **N-93**，和 N-88 一樣要在實作取數函式之前落檔，因此也擋閘門 (b)。CEO 層級我判斷為知悉；風控若認定這是放寬，就改為明確同意。
3. ADR-0027 要改一句交叉引用（L247，屬收緊）；事先宣告不必改。
4. 這個 I-3 註記不是面向使用者的建議類文案。依風控 (i) 送風控，是因為 I-3 管的是狀態標示是否誠實。

## 二、各部門回報（tech-architect）

### A. ADR-0005 註記正文（N-88）

檔案：`/home/user/AICompany/docs/adr/0005-stock-desk-指數來源與美股額度管理.md`

- **定位串（old）**：位於 L253，也就是 I-3 該行的行末。Grep 計數為 1。
```
因此呼叫端必須經由 `IndexSeriesService` 取得結果，不得直接持有底層 service。
```
- **new**：old 原樣保留，換行後接下列整塊，子項縮排 2 格，掛在 I-3 底下。
```
  - **I-3 解釋性註記：重放快照取數函式**（tech-architect 2026-10-24；後續追蹤清單 N-88、N-82；依風控 2026-10-23 v0.26 逐字確認 (i)；CEO 知悉，不修訂）。本註記只說明 I-3 末句「呼叫端必須經由 `IndexSeriesService` 取得結果，不得直接持有底層 service」與決策三第 5 點「指數序列走獨立的 `IndexSeriesService`」的適用範圍。I-3 的決定（指數序列不以 `FRESH` 呈現、降級只往悲觀方向、`BACKUP` 專指即時取自備援來源）一字不改，全部適用於下述函式。
    - **為什麼是解釋、不是修訂**：末句的理由寫在句中：`MarketDataService` 會把主來源成功一律標為 `FRESH`，所以凡經它取得的指數結果，都要經 `IndexSeriesService` 降回 `BACKUP`。末句的「底層 service」指包住 `IndexProviderBridge` 的 `MarketDataService`。下述函式不經也不持有 `MarketDataService`，沒有會把結果標成 `FRESH` 的中間層，而是在 `app/services/index.py` 內直接標 `BACKUP`，I-3 要防的結果不會出現。決策三第 5 點的要旨是指數路徑與個股路徑分離、代號不經 `canonical_us_symbol`；下述函式同樣在 `app/services/index.py`，代號同樣不經它，所以同樣適用。
    - **適用範圍（只限一處）**：`app/services/index.py` 裡唯一的重放快照取數函式（名稱暫定 `fetch_replay_index_snapshot`；ADR-0027 D-3 `forecast_replay_index_check` snapshot 的 v0.26 一句）。它只取 `MARKET_BENCHMARK["TW"]` 的 `^TWII`，唯一的呼叫端是 `app/forecast/replay_checks.py`（ADR-0027 D-1）。其他函式、其他呼叫端、其他代號都不適用本註記，照 I-3 末句的字面經 `IndexSeriesService` 取得。
    - **狀態**：成功為 `DataStatus.BACKUP`（即時取自非官方來源，合於 `BACKUP` 的定義），失敗為 `DataStatus.UNAVAILABLE`。不得出現 `FRESH`；不讀快取，所以也不會出現 `CACHED_STALE`。
    - **快取：不讀也不寫。** 不讀寫 `price_bars_cache` 及其取數與嘗試紀錄（`record_fetch`、`record_attempt`），不經 layer 0，不呼叫 `get_cached_bars`。所以它不改變使用者面 `^TWII` 的新鮮度判定與冷卻（決策四、ADR-0009），也碰不到 I-7 的 symbol key。重放快照本來就不在 ADR-0027 D-4 第 8 點 `CACHE_BAR_CONSUMERS` 內。
    - **輸出去向：只進重放快照。** 回傳值只交給 `replay_checks.py`，在同一個呼叫內寫入 `forecast_input_series`（`series_kind = replay_index_bars`；ADR-0027 D-3）。回傳值不得交給 `app.forecast.views`、`app/api/**` 或任何使用者可見面，也不得交給前瞻路徑、估值、訊號或槓桿專章。回傳型別不得是 `ProviderResult`、`LoadedIndexBars` 或 `LoadedBenchmark`，不設 `meta()`，也不設 `notes` 欄位。快照存入之後誰可以讀、由快照算出的重放結果怎麼揭露，依 ADR-0027 與事先宣告 §4.7，本註記不改。I-3 要求的來源揭露（「本序列取自非官方來源」）落在使用者看得到指數的地方；本函式沒有這種地方，改由揭露重放結果之處承擔：凡寫到指數來源，都要寫明來源名稱與 `backup`，不得寫 `fresh`。
    - **與美股額度管理的交互：沒有。** Alpha Vantage 不在這條路徑上（決策一第 1 點）；不讀也不寫 `QuotaLedger` 與 `provider_quota_usage`，不消耗美股額度，`GET /api/settings` 的額度數字不受影響。yfinance 在本系統沒有額度帳，沿用 adapter 既有的 `RateLimitedClient` 節流，不另設、不繞過。
    - **失敗時 fail-closed**：連線錯誤、非預期的 HTTP 狀態、回應無法解析、`chart.error`、沒有結果區塊、區間內沒有 bar，或多份回應中任一份失敗，都是整次失敗：不回傳任何 bar，也不回傳部分回應，並附中文原因。不退回快取，不改經 `IndexSeriesService`，不換來源或代號。`RateLimitedClient` 內建的傳輸層重試屬於同一次請求，不算退回。之後由 `replay_checks.py` 依 ADR-0027 寫 `fetch_failed` 列，可以再取。
    - **adapter 一側**：yfinance adapter 新增的原始回應方法，帶出每份回應的 `meta.exchangeTimezoneName`、`meta.gmtoffset` 原值，以及每根 bar 的原始 timestamp、推導日期與 OHLCV。它和 `get_index_daily_bars` 一樣不加進 `MarketDataProvider` ABC，也不經 `IndexProviderBridge` 包進 `MarketDataService`；代號只收 `INDEX_SYMBOL_METADATA` 內的值；檔頭的未查證聲明要涵蓋這個方法（本 ADR 約束 D-3）。`app/services/index.py` 照舊不 import 任何具體 adapter，以 Protocol 接受注入。`PriceBar`、`ProviderResult` 與快取 schema 都不動。
    - **與 ADR-0024 的關係**：本函式不經 `MarketDataService`，所以也不經 ADR-0024 D-1 的幣別閘門，觸及 ADR-0024 失效條件 7。這一點由 ADR-0024 自己的重審處理（後續追蹤清單 N-93），本註記不代為解釋 ADR-0024。
    - **超出本註記的情形**：重放取數若要讀快取、要標 `FRESH`、輸出要進 views 或 API，或要開放給第二個呼叫端或第二個代號，就不是解釋，而是修訂 I-3，要另立修訂、送風控，並經 CEO 裁決。
    - **驗收**（qa-reviewer 逐條可查）：
      - (a) 呼叫點封閉（AST，掃 `app/**`）：重放取數函式的名稱只出現在 `app/services/index.py`（定義）與 `app/forecast/replay_checks.py`；adapter 原始回應方法的名稱只出現在 `app/data/providers/yfinance.py`（定義）與 `app/services/index.py`；回傳型別的名稱只出現在前兩個檔。
      - (b) 不碰快取、服務層與額度（AST）：函式本體不引用 `MarketDataService`、`IndexSeriesService`、`IndexProviderBridge`、`PriceService`、`PriceBarCache`、`get_cached_bars`、`get_daily_bars`、`record_fetch`、`record_attempt`、`QuotaLedger`、`canonical_us_symbol`；`app/services/index.py` 不 import `app.data.cache`、`app.data.quota` 與 `app.data.providers` 底下任何模組。
      - (c) 狀態（AST 與執行期）：函式中出現的 `DataStatus` 成員只有 `BACKUP` 與 `UNAVAILABLE`；以假 adapter 回成功時為 `BACKUP`。
      - (d) 快取與額度 spy（執行期）：暫存 DB 預先放入 `^TWII` 的快取列與嘗試紀錄；成功與失敗各跑一次，`PriceBarCache` 與 `QuotaLedger` 每個公開方法的呼叫次數都是 0，快取列、嘗試紀錄與 `provider_quota_usage` 的列數不變。
      - (e) fail-closed（執行期）：上列每一種失敗各一格，都回 `UNAVAILABLE`、零 bar、零回應、原因非空；快取有 `^TWII` 列時同樣零 bar；兩份回應中第二份失敗時零 bar；除了注入的 adapter，沒有其他來源被呼叫。
      - (f) 代號（執行期）：`^GSPC`、`^NDX`、`^SOX` 回 `UNAVAILABLE`，transport spy 0 次。
      - (g) 既有路徑不變：`IndexSeriesService`、`IndexProviderBridge`、`load_index_series`、`load_market_benchmark` 與 `deps` 組裝的既有測試不改而通過；`PriceBar`、`ProviderResult` 的欄位集合與 `MarketDataProvider` 的抽象方法集合不變（以集合相等斷言）。
```

### B. ADR-0005 檔頭指標（同一個檔，同批）

- **old**：位於 L14 行末，Grep 計數為 1。
```
本次僅修訂措辭，決策實質與實作均未改變。
```
- **new**：old 原樣保留，換行後接下列一行（行首 2 格，與 L14 同層）。
```
  2026-10-24 解釋性註記（後續追蹤清單 N-88）：I-3 末句「呼叫端必須經由 `IndexSeriesService` 取得結果」對重放快照取數函式的適用範圍，記在 I-3 之下；不修訂 I-3 與決策三第 5 點，CEO 知悉。
```
- **套用順序**：先套 A（檔尾方向），再套 B。新字句都不含兩個定位串（A 引用末句時沒有「因此」，也沒有句號），所以套用後兩個定位串仍各只有 1 處。L3 狀態行不改。

### C. 交叉引用

- **ADR-0027：要改一句。** 檔案：`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`，位置在 L247，D-1 表 `replay_checks.py` 列。
  - old（Grep 計數為 1）：`` 只經 `app.services.index` 讀取 `^TWII`；每次取數嘗試都留紀錄 ``
  - new：`` 只經 `app.services.index` 讀取 `^TWII`（N-82 方案 A，tech-architect 2026-10-24：只經其中唯一的重放快照取數函式，不經 `IndexSeriesService` 或任何會讀快取的路徑；ADR-0005 I-3 解釋性註記）；每次取數嘗試都留紀錄 ``
  - 理由：ADR-0005 的註記把 `replay_checks.py` 定為唯一呼叫端，ADR-0027 這邊也要寫明它只經這一個函式取數，兩端才算封閉。否則照 L247 現行字面，`replay_checks.py` 經 `IndexSeriesService` 取到 `CACHED_STALE` 也算合規，只剩 S-5b-1 一句在擋。qa 的檢查和 A (a) 是同一個 AST 測試。
  - 方向：補定義（收緊：明寫唯一入口）。CEO：否。被取代原文：無（句中插入）。ADR-0027 是 proposed，這一句要和 N-88 一起送風控。
  - S-5b-1（L649）「取數路徑另案定案（後續追蹤清單 N-82）；定案並實作之前，不得進行執行閘門 (b)」照舊成立：路徑已定案、還沒實作，所以不改。L5217 骨架是 v0.26 的歷史紀錄，也不改。
- **事先宣告：不需要改。** 事先宣告沒有引用 I-3 或 `IndexSeriesService`。§4.7「單一快照」v0.26 註與 Q26-4 只要求取數路徑「在同一個呼叫內帶出原始欄位、不取自快取」，方案 A 加上本註記滿足這個要求。

### D. 附帶草稿：ADR-0024 依失效條件 7 重審 D-1（建議 N-93，是否同批由 coordinator 定）

檔案：`/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`，位置在 L329。

- old（Grep 計數為 1）：
```
- 日後新增 `load_bars` 以外直接取日線的程式路徑，須經 `MarketDataService`（D-1），不得自行繞過。
```
- new：old 原樣保留，在句末接上下列文字。
```
〔tech-architect 2026-10-24 依失效條件 7 重審 D-1（後續追蹤清單 N-93）：D-1 不變；唯一的例外是 ADR-0005 I-3 解釋性註記所述的重放快照取數函式（`app/services/index.py`，只取 `^TWII`，唯一呼叫端 `app/forecast/replay_checks.py`），它不經 `MarketDataService`，所以不經幣別閘門。理由：它的輸出只進重放快照，不用於估值，也不進任何使用者可見面；yfinance 指數路徑的幣別本來就取自 `INDEX_SYMBOL_METADATA`，不讀上游宣告（D-6 role 2 排除），正式設定下經服務層也不會觸發閘門（D-4）。role 2 改讀上游 `meta.currency`（D-6、F-9c）時，本例外一併重審。CEO 知悉。〕
```
- 這是在 accepted ADR 上記一筆範圍例外。先例是 ADR-0024 自己的「範圍外同類路徑」（L318，`pit_snapshot` 直打 FinMind、全市場面板）。層級由風控裁定：我建議知悉，若認定為放寬就改為明確同意。
- 另有一個可選的加強做法，我不建議當作條件：重放函式比對 `INDEX_SYMBOL_METADATA["^TWII"]` 的幣別與 `MARKET_CURRENCY["TW"]`，不一致就回 `UNAVAILABLE`。正式設定下這個檢查恆成立，效益很低。

### E. 給風控的替代句（只在風控不接受 A 第 6 子項的「不設 `notes`」時用）

- **我建議的讀法（甲，已寫進 A）**：I-3 的 `notes` 義務針對的是呈現面，這個函式沒有呈現面，所以義務落在揭露重放結果之處。另一個附帶好處：不會新增 `.notes` 屬性存取，不碰 ADR-0023 KD-2a 那份封閉 allowlist（目前 9 項，要求完全相等）。
- **乙（照字面）**：
  - 把「不設 `meta()`，也不設 `notes` 欄位。」改為「不設 `meta()`；成功與每一條失敗路徑都在 `notes` 欄位掛 `UNOFFICIAL_SOURCE_NOTE`。」並刪掉「I-3 要求的來源揭露…不得寫 `fresh`。」一句。
  - 代價：若 `replay_checks.py` 讀 `.notes`，KD-2a 的 allowlist 要依 KD-2b 流程加 1 項。
  - 預期值也會跟著變：`UNOFFICIAL_SOURCE_NOTE` 0→1。

### F. 給 dev-lead／qa 的實作提醒（不屬本註記約束）

- 單一解析路徑屬 N-82，依我上一份追加第二節 B 的風險欄：原始回應方法與 `_parse_row` 共用同一套逐列解析，日期推導只有一處。測試建議用 AST 斷言 `yfinance.py` 中 `fromtimestamp` 只出現一次。
- null 欄位的列是否保留，會改變快照的列集合，照 N-82 另案處理，本註記不動。

## 三、驗證

**讀過的檔案**
- ADR-0005 全文。
- 風控 v0.26 逐字確認全文。
- TA 追加 5a～5f 全文。
- data-engineer N-81 全文。
- 追蹤清單 N-80～N-92。
- `app/services/index.py` 全文、`yfinance.py` 全文。
- `deps.py` L120～208。
- ADR-0027 L236～255、L284～297、L640～659、L826～858。
- ADR-0024 L1～20、L142～173、L318～367。
- ADR-0023 L240～261。
- 事先宣告：Grep 重點行。

**查到的事實**
- 現行程式：
  - `index.py` 的 import 只有 `app.data.interface`、`app.leverage.index_mapping`、`app.portfolio.valuation`、`app.services.market`，沒有 cache、quota 或具體 adapter，所以驗收 (b) 的 import 部分現在就成立。
  - `quota.py` 的設定只有 `ALPHA_VANTAGE_*`；`yfinance.py` 除了檔頭 docstring 以外沒有任何 quota 字樣。據此我寫「yfinance 在本系統沒有額度帳」。
  - `RateLimitedClient` 對 5xx 與傳輸錯誤有內建重試（`http.py` L154、L228～250）。
- ADR 交叉核對：
  - ADR-0025 L196 與 ADR-0027 D-4.5 都要求指數恆標 `backup`，與本註記一致。
  - ADR-0028 L384 要求 `MARKET_BENCHMARK` 的代號屬於 `INDEX_SERIES_SYMBOLS`；本註記只取 `MARKET_BENCHMARK["TW"]`，不衝突。

**定位串計數（Grep）**：A、B、C、D 四個 old 在各自檔中都恰好 1 處。

**ADR-0005 落檔後預期值**
- 算法是「現行＋B＋A」，純插入、沒有移除。下列是人工點數，請照風控前例用工具算一次，以工具值為準。
- 現行值用 Grep `-o` 取得。

| 字串 | 現行 | 落檔後 |
|---|---|---|
| `I-3` | 2 | 12（B 3＋A 7） |
| `IndexSeriesService` | 2 | 10（B 1＋A 7） |
| `` `FRESH` ``（含反引號） | 4 | 9（A 5） |
| `QuotaLedger` | 2 | 5（A 3） |
| `解釋性註記` | 0 | 2 |
| `N-88` | 0 | 2 |
| `N-82` | 0 | 1 |
| `N-93` | 0 | 1 |
| `fetch_replay_index_snapshot` | 0 | 1 |
| `replay_checks.py` | 0 | 4 |
| `ADR-0027` | 0 | 6 |
| `ADR-0024` | 0 | 5 |
| `CACHE_BAR_CONSUMERS` | 0 | 1 |
| `UNOFFICIAL_SOURCE_NOTE` | 0 | 0（採乙則為 1） |
| A、B 兩個定位串 | 各 1 | 各 1 |

**其他檔的預期值**
- ADR-0027（套用 C 之後）：`ADR-0005 I-3` 1→2、`解釋性註記` 5→6、`IndexSeriesService` 0→1、`N-82` 4→5、`方案 A` 7→8。
- ADR-0024（套用 D 之後）：`ADR-0005 I-3` 1→2、`解釋性註記` 0→1、`N-93` 0→1、`replay_checks` 0→1、`重放` 0→2。
- git：只套 N-88 時，只動 ADR-0005 與 ADR-0027 兩個檔；D 同批時再加 ADR-0024。

**限制**
- 註記中的函式名稱與 adapter 方法名稱都是暫定，實作時以實際名稱為準，驗收 (a) 照實際名稱跑。
- `N-93` 是我建議的編號，coordinator 若另行編號，A 第 10 子項、D 與上表要同步改。
- 我沒有改任何檔案，沒有跑 git、程式或測試，沒有讀 `.env`，沒有碰 `*.db`。有一次 Glob 逾時，沒有影響結論。
- 本意見不是法律意見。

## 四、下一步

1. **coordinator**
   - 把 A、B、C 送風控逐字確認。
   - 決定 D（ADR-0024，N-93）要併入同批，還是另批送風控。兩者都必須在實作重放取數函式之前落檔，所以都擋閘門 (b)。
   - 在追蹤清單登記 N-93，負責人 tech-architect → 風控（CEO 知悉），擋點「方案 A 取數函式實作前」。
2. **risk-compliance-officer**
   - 逐字確認 A、B、C（以及 D，若同批）。
   - 裁定 E 的甲或乙。
   - 裁定 D 的 CEO 層級是知悉還是明確同意。
3. **dev-lead／data-engineer（N-82）**：等風控確認並落檔之後才動工。照 A 的「驗收」(a)～(g) 與 F 補測試，送 qa-reviewer（含 Codex）。
4. **CEO（知悉）**，建議的白話句：
   > 歷史重放需要一次下載加權指數的原始資料（含原始時間戳記），現有的指數取數關口帶不出這些欄位，所以要在同一個指數模組裡開一個只給重放用的取數函式。它照樣標「備援」、不標「即時」，不讀也不寫本機快取；下載失敗就整次作廢，不改用快取。下載的資料只存進重放快照，不會出現在任何畫面或 API，也不動用美股的 Alpha Vantage 額度。這是說明既有規則（ADR-0005）的適用範圍，不改規則，請您知悉。另外，這個函式也不經過幣別檢查關口（ADR-0024）。指數的幣別本來就是固定設定，實際上不會漏掉任何檢查，但我們會補一則重審紀錄，同樣送風控、請您知悉。

**相關檔案**
- `/home/user/AICompany/docs/adr/0005-stock-desk-指數來源與美股額度管理.md`
- `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`
- `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`
- `/home/user/AICompany/docs/adr/0023-stock-desk-風險上限分子不完整時的非對稱判定通則.md`
- `/home/user/AICompany/work/reviews/2026-10-23-v0.26重放執行閘門批逐字確認-風控.md`
- `/home/user/AICompany/work/reviews/2026-10-23-v0.26之ADR同步追加5a至5f-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-10-23-N81-yfinance日期慣例查證-data-engineer.md`
- `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/index.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/api/deps.py`
