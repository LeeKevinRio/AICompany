# ADR-0016：stock-desk 持倉漲跌欄的計算基準與 fail-closed

- 狀態：accepted
- 2026-10-04 accepted；此後變更以修訂註記或新 ADR 處理（依 ADR-0001，生效後不得原地改寫決策）。本檔上文「待核可」「核可前」字樣為核可前的歷史敘述，自 2026-10-04 起其所指內容一併生效。
- 日期：2026-10-03
- 決策者：tech-architect（草案）；CEO 核可 2026-10-04（CEO 原話：「ADR-0016、ADR-0017 可以開始執行」；來源：2026-10-04 任務單轉述）。各待決事項的裁定結果見「需要 CEO 決定」
- 適用範圍：僅 product/stock-desk 產品線
- 與既有 ADR 的關係（不取代任何一則 ADR 全文）：
  - 修訂 ADR-0014（`0014-stock-desk-盤中報價資料邊界顯示範圍與節流.md`）：D-1（`prev_close` 註解、說明、`interface.py` docstring 同 PR 補正）、D-4（「日線梯子」界定）、D-5、D-6、D-7 表、待實測參數段、「前置條件（明列）」段、I-18、I-28，新增 P-17 與 I-33～I-35。ADR-0014 目前為 `proposed`，依 ADR-0001 可原地加修訂註記；修訂註記已於 2026-10-03 落在 ADR-0014（來源：本 ADR 草案「二、ADR-0014 修訂條文」1～9，及 tech-architect 同日落檔覆核裁定）。本 ADR 獲 CEO 核可前，ADR-0014 的上述加註同屬待核可內容，不得據以放寬 I-18 的實作。ADR-0014 其餘決策內容未變。
  - 沿用 ADR-0014 D-1「`prev_close` check input only」的字面（草案以 β 方案維持此字面，見 Decision D-7）。
  - 引用 ADR-0009（`PRICE_LOOKBACK_DAYS` 的 coverage 與增量抓取，見 D-2）、ADR-0012（`TWT48U_ALL` 與 DE-5 查證狀態）、ADR-0010（SQLite 查詢量級估算）。
  - **〔2026-10-03 修訂〕不對 ADR-0012 C-7（accepted）開例外**：D-5 覆蓋判定與 F6 一律只讀主 DB，不讀市場 DB；持倉資料鏈（含 `GET /api/portfolio/summary` 的組裝點 `app/api/portfolio.py`）不得可達 `app.data.market_panel`。理由與資料流見 D-5 的 2026-10-03 修訂。本 ADR 不修訂 ADR-0012 任何條文。
- 編號說明：0013 已由員工線（`chore/agent-readonly-hook`）的唯讀 hook ADR 佔用（見 ADR-0014 編號說明）；0016 在草案作者撰寫時 grep 無結果，tech-writer 落檔時於 `docs/adr/` 目錄亦查無 0016。
- 來源與版本：本檔為 tech-architect 2026-10-03 草案（ADR-0016「stock-desk 持倉漲跌欄的計算基準與 fail-closed」）的落檔，僅做格式調整；另依 tech-architect 2026-10-03 落檔覆核裁定改動：「與既有 ADR 的關係」之 ADR-0014 項、行號抽驗說明、F7 門檻定義、K-8 的 D1 指涉、T-1 的 F7 邊界測項、「需要 CEO 決定」第 2 點；D-6 另有 2026-10-03 定稿 bullet（來源：風控核可）。除此之外技術內容未增補。
  - 落檔時的快照：分支 `product/stock-desk`，HEAD `1c8cdcd66b274f57084aa9e410fc7ee2bfb46659`（tech-writer 於落檔時讀取 `.git/refs/heads/product/stock-desk`）。此為落檔時快照；之後 HEAD 已前進，不代表檔內行號仍對應，也不表示內容已對新 HEAD 重新驗證。
  - 檔內 `檔案:行號` 為草案作者所引，行號以草案作者 2026-10-03 讀到的工作目錄為準，落檔時未重新對 code 驗證；行號會隨 commit 漂移，引用時以原文定位。
  - 檔內「風控 2b／2c(ii)／2d／(a)～(d)／第 4 項／待裁示點 (i)」等引用，指 `work/reviews/2026-10-03-首頁重排-第二階段字面-風控核可.md` 所列項目（草案相關檔案清單列有該檔；tech-writer 僅確認該檔存在，未逐項核對編號）。
  - 草案對 ADR-0014、ADR-0012 的行號引用，tech-writer 於 ADR-0014 加註前抽驗了 ADR-0014 的 L3（proposed）、L7、L123、L318、L430、L539 與 ADR-0012 L1116（DE-5），皆相符；其餘行號未驗證。ADR-0014 加註後行號已位移（L3、L7、L123 不變；以下括號前為加註前舊行號，括號內為 2026-10-03 加註後 qa-reviewer 查得之位置），請以原文定位：L318（今 L325）＝防線 2 的 ADR-0015 加註、L340（今 L347）＝合成 fixture 檔名明標 `synthetic`、L430（今 L437）＝I-4 的 ADR-0015 加註、L539（今 L550）＝附錄否決「用環境變數開關盤中功能」。檔內他處所引 ADR-0014 L340、L539 亦為舊行號。
  - 本 ADR 內的「附錄」為草案「評估摘要」，原樣轉錄。
  - 2026-10-03 實作註記：commit `0281f0c`、`52c6e8b`（`product/stock-desk`）落地後，依 qa-reviewer 審查指出與 tech-architect 同日裁定，於 D-3、D-4、D-5 加註標明「〔2026-10-03 實作註記〕」的條目，僅記錄實作上的保守行為、常數與指稱更正，不放寬任何決策；此等加註與本 ADR 同屬待 CEO 核可內容。
  - 2026-10-03 D-5 修訂：依 tech-architect 對 data-engineer 接線前三議題（ADR-0012 C-7 衝突、`MIN_ANNOUNCE_LEAD_DAYS` 未查證、F6 與覆蓋判定讀不同庫）之裁定，於 D-5 新增「〔2026-10-03 修訂〕」條目，新增 K-16～K-21、T-12～T-15 與「待查證參數」段（V-1），並於 Consequences、交接與升級、需要 CEO 決定、不該做的事加註；此等內容同屬待 CEO 核可內容。

---

## Context（背景）

- 首頁第二階段要加漲跌欄，字面風控已核可。現況是現價取自日線最新一根 bar（`valuation.py:314-338`），API 沒有任何漲跌欄位（`summary.py:47-92`）。
- 估值和風控上限一律用未調整收盤（`adjust.py:12-18`）。
- 除權息資料只涵蓋上市股，而且只有預告（`dividends/providers.py:92-106`）。

---

## Options（選項比較）

三個題目各一張表，**粗體**為採用方案。採用：A1、B-β、C1。

**A. 收盤版分母**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A1 未調整收盤對未調整收盤，同一份 ProviderResult（採用）** | `較 {MM/DD} 收盤` 是字面事實；分子就是畫面現價（風控 2c(ii)）；零額外 IO | 除權息日、分割日會出現假跌 | 用 F6 / F7 擋一部分，剩下的靠揭露 |
| A2 `back_adjust_bars` 還原價 | 沒有假跌 | 違反 `adjust.py:12-18` 的邊界；分母是合成價，標籤不實；上櫃股本來就沒有事件可還原 | 否決 |
| A3 分母用除權息參考價 | 等同交易所口徑 | 「收盤」字面不實，要重送風控；參考價只有上市股有，而且 DE-5 未查證（ADR-0012 L1116） | 否決 |
| A4 build_summary 另讀 `price_bars_cache` 取前一根 | 實作直覺 | 可能和顯示的現價來自不同序列（違反風控 2c(ii)）；多一次讀取 | 否決 |

**B. 盤中版分母**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| B-α 直接用 `y`（查證後才開） | 不必讀快取 | 正確性完全押在一次查證上；`y` 沒有日期，`basis_date` 只能空著或推算 | 除權息日語意如果判斷錯，「昨收」會整天標錯 |
| **B-β 快取前一根收盤當分母，`y` 只做等值比對（採用）** | 「昨收」由構造保證成立；`y` 的語意錯了也只會變成「—」；`basis_date` 一定有值 | 要修訂 I-18（允許一次 cache-only 讀取）；快取缺前一交易日時就是「—」 | 低 |

**C. 表頭開關**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **C1 `PortfolioSummary.change_mode`，由估值器建構參數決定（採用）** | 每次部署固定不變；W7 之前就能先上 | 多一個欄位 | 低 |
| C2 `price_basis` 盤中檔數 > 0 | 不用新增欄位 | 跟著資料跳動，違反風控 2b | 否決 |
| C3 `intraday.session_state` | — | 跟著時段跳動 | 否決 |
| C4 前端常數或環境變數（現在的 `TODAY_CHANGE_SLOT`，`positionsTableView.ts:65-71`） | 簡單 | 前後端分叉；用環境變數開關違反 ADR-0014 L539 | 否決 |
| C5 用 `intraday` 區塊是否為 null 判斷 | 語意相近 | W7 尚未落地；「存在與否」的語意不夠明確 | 備選 |

---

## Decision（決策）

**D-1 介面形狀**：新模組 `app/portfolio/price_change.py`。

```python
class PriceChange(BaseModel):          # frozen
    pct: Decimal                       # percent units: (price / basis_price - 1) * 100, quantize 0.0001
    basis_kind: Literal["close", "intraday"]
    basis_date: date                   # never None when PriceChange exists
    basis_price: Decimal               # raw (unadjusted) close on basis_date, > 0
```

- `SummaryPosition.change: PriceChange | None = None`，加在 `summary.py:47-78` 旁。
- `PortfolioSummary.change_mode: Literal["close_only", "may_include_intraday"] = "close_only"`。
- JSON 一律是十進位字串，例如 `{"pct":"1.2346","basis_kind":"close","basis_date":"2026-10-01","basis_price":"1072.00"}`。
- 對應關係固定：`basis_kind=="close"` ⇔ 該列 `valuation.price.price_kind=="daily_close"`；`"intraday"` ⇔ `"intraday_quote"`。
- **`Valuation` 與 `PriceInfo` 的 schema 不新增漲跌欄位**，保住 ADR-0014 I-16、I-17。

**D-2 基準來源**
- 估值器在 `_resolve_price` 內，從同一份 `result.bars` 取「最新一根」和「前一根」，結果放進內部 dataclass `PositionValuation`（`valuation.py:198-210`，不序列化），新增欄位 `change_basis`。
- 不得再呼叫任何價格服務。
- 不得為此擴大 `PRICE_LOOKBACK_DAYS`，那會動到 ADR-0009 的 coverage 與增量抓取。

**D-3 篩選只在 summary 端點做**
- 簽名改成 `build_summary(store, valuator, *, change_screen: ChangeScreen | None = None)`。
- 只有 `api/portfolio.py:99-100` 注入實際的 screen。其他四個呼叫端（`api/portfolio.py:125`、`alerts/snapshot.py:83`、`api/advice.py:165`、`api/settings.py:350`）不注入，`change` 恆為 null。
- `ChangeScreen` 依賴兩個 Protocol：
  - `ExDateLookup`：整本帳一次批次查詢，由 `DividendStore` 實作（`dividends/store.py:169`）。
    - **〔2026-10-03 實作註記〕** 實作類別為 `DividendEventStore`，批次方法為 `ex_dates_between`；上句 `DividendStore`（`dividends/store.py:169`）為草案撰寫時的指稱。該方法依儲存值精確比對代號，正規化（`strip().upper()`）由呼叫端 `price_change.py` 負責。
  - `TradingCalendarSource`：沿用 `services/market.py:42`，底層是 `cache.market_trading_days`（`cache.py:459`）。
- **〔2026-10-03 實作註記：dev-lead 於 `0281f0c` 追加、`52c6e8b` 擴大為整段保護，qa-reviewer 接受，tech-architect 確認不違反本 ADR〕** `ChangeScreen.screen` 整體 fail-closed：篩選過程任一處拋出例外，包括除權息查詢（`ExDateLookup`）、行事曆查詢（`TradingCalendarSource`）、D-5 覆蓋判定（`ExDateCoverageRule`），以及逐列計算遇極端值（例如 `change_pct` 量化時的 `InvalidOperation`），該本帳所有列的 `change` 一律為 null，並以 `logger.exception` 記錄，原因不得進入回應（K-6）。`GET /api/portfolio/summary` 照常回應估值與 totals，不因漲跌欄失敗而回 500：漲跌欄是輔助欄，估值不是。代價：程式錯誤也會被吞成整欄「—」，只留在 ERROR log。

**D-4 收盤版的 fail-closed 條件**：任一成立，該列 `change=null`。
- F1：現價不可得。
  - **〔2026-10-03 實作註記：dev-lead 於 `0281f0c` 自行追加之保守行為，qa-reviewer 接受，tech-architect 確認不違反本 ADR〕** F1 另涵蓋以下情形，皆判 null：(i) 現價 `PriceInfo.value ≤ 0`；(ii) `PriceInfo.value` 不等於 `change_basis.latest.close`，或 `PriceInfo.as_of` 不等於 `change_basis.latest.date` 的 ISO 字串，也就是畫面現價並非出自同一份基準 bar，不滿足 D-2 與風控 2c(ii) 的同源前提。
  - **〔2026-10-03 實作註記〕** F1 只判斷現價是否可得，不看 `valuation.status`。因匯率缺漏而為 `insufficient_data`、但現價與前一根收盤皆可得的列，照常計算：兩者同幣別相除，與匯率無關。
- F2：同一份 `ProviderResult` 在回看窗內不到 2 根 bar。
- F3：兩根 bar 的 `source` 不同，或任一根的 `source` 以 `+divadj` 結尾。
- F4：`basis_price ≤ 0`，或 `basis_date ≥ price_date`。
- F5：觀測到的市場行事曆在 `(basis_date, price_date)` 之間有交易日，也就是該檔缺了某個交易日。行事曆是空的時候不因此判 null，因為標籤上已經寫出日期。
- F6：已知有除權息事件，且 `basis_date < ex_date ≤ price_date`。
- F7：TW 標的（該部位 `market=="TW"`，含 ETF 與上櫃股）的 `|pct|` 嚴格大於 11（`pct` 為百分比單位，以 D-1 量化到 0.0001 後的值比較；恰為 `11.0000` 不判 null）。11 由本模組兩個常數相加而得：漲跌停 `Decimal("10")` 加容忍 `Decimal("1")`（百分比單位），比照 `sectors/definition.py:69-70` 的第 ③ 類公司行動保險（0.10＋0.01、嚴格大於），但要在本模組自己定義常數，不得 import `app.sectors`。槓桿或反向 ETF 的漲跌幅限制待 data-engineer 查證，查證前一律套這個門檻（方向是 fail-closed）。
- F8：沒有注入 `change_screen`。
- **〔2026-10-03 實作註記：dev-lead 於 `0281f0c` 自行追加之保守行為，qa-reviewer 接受，tech-architect 確認不違反本 ADR〕** 本版 D-7 盤中版未開，凡 `PriceInfo.price_kind != "daily_close"` 的列，`change` 一律為 null（通過 F1 同源檢查後，log 代碼為 `D7_not_enabled`），與 P-17 開關狀態無關。此條比 ADR-0014 I-34 更嚴，並確保收盤版篩選不會產生違反 D-1 對應關係（`basis_kind`／`price_kind`）或 D-8 不變式的結果。本條不編 F 號，不影響 T-1「F1～F8 每條至少一例」的計數，另由 `tests/test_price_change.py::test_intraday_priced_row_is_withheld_until_d7` 覆蓋。D-7 落地時以 G1～G5 取代本條，並同步修訂本條。

**D-5 除權息事件的覆蓋判定**
- 只有「最新 bar 的 `source=="twse"`」（比照 ADR-0014 D-8 ②）**而且**同步紀錄能證明窗內任何除權息日在某次同步時仍屬未來，才算覆蓋已知。具體規則由 data-engineer 寫成函式並附測試。
- 覆蓋未知時照常顯示，但這屬於剩餘風險，由 D-6 的揭露承擔。
- **〔2026-10-03 實作註記，來源：commit `0281f0c` 之 qa-reviewer 審查；tech-architect 裁定〕** 「覆蓋未知時照常顯示」由 `app/portfolio/price_change.py` 的模組級常數 `SHOW_WHEN_COVERAGE_UNKNOWN`（`Final`，預設 `True`）表達。它是程式碼常數，不是環境變數，也不得改由環境變數、設定檔或任何 runtime 輸入決定（比照 ADR-0014 附錄否決以環境變數開關功能）。data-engineer 交付 D-5 覆蓋判定函式前，覆蓋規則以 stub `CoverageNotYetJudged` 代替，對每列一律回答 `unknown`；此期間把常數改為 `False` 等於整欄全 null，屬 fail-closed 退路，不是調參旋鈕。改動此常數須 CEO 核可並以修訂本 ADR 留紀錄，不得以 hotfix 處理。`tests/test_price_change.py::test_unknown_coverage_still_shows_the_change` 釘住其值為 `True`，改值必然改動該測試，review 時據此追溯核可紀錄。覆蓋規則對某列未回答時，視同 `unknown`。
- **〔2026-10-03 修訂，來源：tech-architect 裁定 data-engineer 接線前三議題〕**
  - **D-5.1 首句的補正**：首句「同步紀錄能證明窗內任何除權息日在某次同步時仍屬未來」不足以證明覆蓋：某次同步時日期仍屬未來，不代表該事件那時已列出。覆蓋已知須同時滿足 D-5.3 的四個條件，其中條件 ③（列出前置天數 V-1）補足首句。
  - **D-5.2 資料來源（裁定：主 DB 同步紀錄；不開 ADR-0012 C-7 例外）**
    - 覆蓋判定只讀主 DB 的 `dividend_sync_runs` 與 `dividend_sync_unparsed`，由 `app/dividends/store.py` 提供讀取方法，經結構型 Protocol `AnnounceRunSource`（`app/dividends/coverage.py`）接入 `AnnounceRunCoverageRule`。
    - 市場 DB 的 `pit_snapshot_runs`／`pit_dividend_announce_rows` 不作為覆蓋判定或 F6 的執行期來源。`MarketPanelReader.dividend_announce_observations` 只供測試與 V-1 離線查證使用。
    - 寫入：唯一的同步函式（`app.dividends.sync.sync_dividends`，CLI 與排程共用）在**同一個 SQLite transaction** 內完成 `dividend_events` 的 upsert 與一列 `dividend_sync_runs` 的寫入。因此某次 ok 同步列出的事件必然已在 `dividend_events`，F6 看得到。
    - schema 草案（主 DB；兩表皆 append-only，比照 `app/data/market_panel.py` 以 `BEFORE UPDATE`／`BEFORE DELETE` trigger `RAISE(ABORT, 'append-only')`；表名不得以 `pit_` 開頭）：
      ```sql
      CREATE TABLE IF NOT EXISTS dividend_sync_runs (
          run_id INTEGER PRIMARY KEY AUTOINCREMENT,
          recorded_at TEXT NOT NULL,      -- store clock, tz-aware ISO 8601 (UTC)
          trigger TEXT NOT NULL CHECK (trigger IN ('scheduled', 'cli')),
          source TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
          event_count INTEGER NOT NULL,
          unparsed_count INTEGER NOT NULL,
          unattributed_count INTEGER NOT NULL,
          reason TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_dividend_sync_runs_status_recorded
          ON dividend_sync_runs (status, recorded_at);
      CREATE TABLE IF NOT EXISTS dividend_sync_unparsed (
          run_id INTEGER NOT NULL,
          symbol TEXT NOT NULL,           -- strip().upper() of a row whose date did not parse
          PRIMARY KEY (run_id, symbol)
      ) WITHOUT ROWID;
      ```
    - 欄位語意：
      - `recorded_at`：store 自身時鐘（可注入供測試），UTC、帶時區，固定為 ISO 8601 `YYYY-MM-DDTHH:MM:SS.ffffff+00:00` 以確保字串比較即時間比較；不得接受呼叫端傳入（比照 ADR-0012 C-10），現行 `upsert(..., synced_at=)` 參數不得用來填此欄。
      - `status='ok'` ⇔ adapter 回 ok、`event_count > 0`，且同一 transaction 的 upsert 成功；其餘一律 `failed`。`reason` 只進資料庫與 log，不進 API 回應（K-6）。
      - `unparsed_count`：有 `Code` 但日期無法解析的列數，代號逐一寫入 `dividend_sync_unparsed`。
        > 〔2026-10-04 實作註記，tech-architect 確認〕`unparsed_count` 與 `dividend_sync_unparsed` 的實際範圍為「有 `Code`、但未以事件寫入 `dividend_events` 的列」，不限於日期無法解析（例如 Exdividend 旗標不明、權／權息缺股票股利比）。理由：此類列 F6 看不到，必須擋覆蓋。方向比原文保守；`SHOW_WHEN_COVERAGE_UNKNOWN = True` 下不改變任何回應內容。schema 註解 `strip().upper() of a row whose date did not parse` 依此理解。
      - `unattributed_count`：沒有 `Code`、無法歸屬代號的列數。
    - 讀取：ok run（`recorded_at >= recorded_not_before`）左連查詢代號的 `dividend_sync_unparsed`，**整本帳一條 SQL**（K-7），回傳 `DividendAnnounceObservation` 形狀：
      - 與查詢代號無關的 run 回一筆 `symbol=None`；
      - `dividend_sync_unparsed` 命中者回 `symbol=該代號、ex_date=None`；
      - `unattributed_count > 0` 的 run，對**每個查詢代號**各回一筆 `ex_date=None`（該 run 可能藏有該代號的事件）。
      - 主 DB 的表不存在時視為「沒有 run」。
  - **D-5.3 `known` 的四條件**（全部成立才回 `known`，否則回 `unknown`）：
    - ① 該列 `market=="TW"`、最新 bar `source=="twse"`，且 `basis_date < price_date`。
    - ② 存在 ok run，其 `recorded_at` 換算 Asia/Taipei 的日期 ≤ `basis_date`；取日期最晚者為錨點。
    - ③ `price_date ≤ 錨點日期 + MIN_ANNOUNCE_LEAD_DAYS`（V-1）。
    - ④ 自錨點日期起（含當日）的每個 ok run，都沒有該代號 `ex_date` 為 null 的觀測，也沒有 `basis_date < ex_date ≤ price_date` 的觀測。
    - 補充規則：
      - 任一相關 run 的 `recorded_at` 沒有時區：該列回 `unknown`，不得略過該 run。
      - 讀取失敗（`sqlite3.Error`、`OSError`、`ValueError`）：整本帳回 `unknown`，記 WARNING，不拋出（不觸發 D-3 的整欄 null）。
      - 本資料流下，④ 的「窗內有日期」分支與 F6 重疊（同 transaction 保證），保留作為防線，不得因重疊而刪除。
        > 〔2026-10-04 實作註記，tech-architect 確認〕主 DB 資料流下，adapter 依 D-5.2 讀取規格不產出帶日期的觀測；④ 的「窗內有日期」分支實質由 F6（同讀 `dividend_events`）承擔。規則程式碼中該分支保留、不得刪除，供其他 `AnnounceRunSource` 實作使用。不要求主 DB adapter 另行 JOIN `dividend_events`：其與 F6 同源，不構成獨立防線。
  - **D-5.4 F6 與覆蓋判定同源**：F6 只讀主 DB `dividend_events`，不讀 `pit_dividend_announce_rows`。同源的前提是 TWT48U 同步排程化（見交接與升級，CEO 核可、devops-sre 執行）。排程落地前同步紀錄只來自手動 CLI，覆蓋判定多數回 `unknown`，行為等同 `CoverageNotYetJudged`，不構成退步。
  - **D-5.5 顯示效果的誠實說明**：`SHOW_WHEN_COVERAGE_UNKNOWN = True` 下，`known` 與 `unknown` 皆照常顯示，覆蓋判定不改變任何回應內容。它的作用是 (i) 經由排程同步讓 F6 擁有同源事件資料；(ii) 為日後是否檢討該常數提供可量測依據。
  - **D-5.6 參數與改動治理**
    - `MIN_ANNOUNCE_LEAD_DAYS`（`app/dividends/coverage.py`，`Final`，預設 `1`）為待查證參數 V-1（見「待查證參數」段）；不得由環境變數、設定檔或任何 runtime 輸入決定；建構子拒絕 `< 1`。
    - 調高 V-1 須具備 V-1 判準所列證據，以修訂本 ADR 的 V-1 列留紀錄，經 tech-architect 覆核；若當時 `SHOW_WHEN_COVERAGE_UNKNOWN` 為 `False`，另須 CEO 核可。不得以 hotfix 處理。`tests/test_dividends_coverage.py::test_monday_after_a_friday_anchor_is_unknown_under_the_default_lead` 釘住現值，改值必然改動該測試，review 時據此追溯紀錄。
    - `SHOW_WHEN_COVERAGE_UNKNOWN` 的治理不變（見上一則實作註記）。

**D-6 剩餘揭露**：上櫃股、美股、未同步期間的除權息，以及分割，會有假漲跌。這句要由 creative-lead 起草、風控逐字核可。**建議與收盤版同 PR 上線。**
- **〔2026-10-03 定稿，來源：risk-compliance-officer 2026-10-03 核可（非 tech-architect 草案）〕** 剩餘揭露句已由風控逐字核可：
  - 核可字面：「漲跌未計入除權息與分割，可能與實際報酬不同。」
  - 常數名：`CHANGE_COLUMN_RESIDUAL_NOTE`。
  - 觸發條件與漲跌欄渲染條件相同：不讀 `change` 是否為 null，也不讀 `change_mode`，兩種表頭下皆顯示。
  - 呈現：獨立 `<p>`，沿用口徑句樣式 `mb-2 text-xs text-neutral-400`，不得 truncate、line-clamp、更淡、斜體，不得只在某一種寬度出現，桌機與手機同位置；有外幣口徑句時緊接其下、不合併；不進 `<details>`、不進 `title`。
  - 測試：vitest 釘字面逐字相同、與漲跌欄同生滅（0 列持倉時不出現；全部列皆為「—」時仍出現）、不在 `title` 內、不在 `<details>` 內、全頁只出現一次、兩種表頭模式下皆顯示。
  - 常數與其他字面常數放同一處，讓既有禁用詞掃描涵蓋。
  - 範圍限制：這句只能跟著漲跌欄出現，不得出現在損益％、個股頁或其他沒有漲跌欄的畫面；日後他處新增漲跌數字須另送審。「實際報酬」不得作為任何其他欄位的標籤或說明。備案「與實際價格變動不同」已被風控否決（與事實不符）。
  - 風控 required (a)～(e) 與三點裁定之 required 全文以該核可紀錄為準，視同本 ADR 約束。
  - 風控立場：須與收盤版漲跌欄同 PR 上線；放寬須留 CEO 書面否決紀錄。
  - 紀錄：`work/reviews/2026-10-03-漲跌欄-剩餘揭露-風控核可.md`；起草：`work/stock-desk-漲跌欄-剩餘揭露-起草-2026-10-03.md`。

**D-7 盤中版（W15 之後）**
- 報價被接受時，透過 `get_cached_bars` 取 `date < quote.trade_date` 的最新一根 bar 當分母（`service.py:244-283` 是 cache-only，不寫任何表）。
- 以下任一成立就判 null：
  - G1：`change_mode != "may_include_intraday"`，或 P-17 關閉。
  - G2：`quote.prev_close is None`。
  - G3：沒有符合條件的快取 bar。
  - G4：`quote.prev_close != basis_price`（Decimal 相等比較）。
  - G5：F3～F7 的對應條件，日期改用 `quote.trade_date`。

**D-8 `change_mode` 的來源**
- 由估值器建構參數決定，例如新增 property `has_intraday`，比照 `price_mode` 在 `valuation.py:234-236` 的寫法。不由資料決定，也不讀環境變數。
- W15 前恆為 `close_only`。
- 後端不變式：`close_only` 時，回應裡不得有任何 `price_kind=="intraday_quote"` 或 `basis_kind=="intraday"`。

---

## Consequences（後果）

**好處：**
- 標籤由構造保證為真，分子和現價同源。
- 除權息日的 `y` 語意即使錯判，也只會變成「—」。
- 零額外網路 IO。SQLite 每本帳多兩次查詢（除權息一次、行事曆每個市場一次），在 ADR-0010 L119 估算的量級之內。
  - **〔2026-10-03 修訂〕** D-5 接線後每本帳再多一條主 DB 查詢（覆蓋判定），合計三次；請求路徑仍不讀市場 DB、仍零網路 IO。

**代價：**
- 長假之後、快取缺日、跨來源拼接、公司行動，都會出現「—」。
- 除權息只擋得住上市股，而且前提是有同步。剩餘部分要多一句揭露。
- portfolio 層新增對 `app.dividends.store` 的依賴，**只能是 store，不得是 adjust**。
- ADR-0014 需要修訂 I-18。
- **〔2026-10-03 修訂〕** 主 DB 新增 `dividend_sync_runs`、`dividend_sync_unparsed` 兩張 append-only 表。
- **〔2026-10-03 修訂〕** 排程化後，TWT48U 每個交易日由兩條鏈各抓一次（市場 DB 擷取、主 DB 同步），兩份紀錄在邊界時點可能不一致；各自內部一致即可，不做對帳。
- **〔2026-10-03 修訂〕** 排程化同步會讓回測、Kelly、事件研究讀到的 `dividend_events` 逐日增長，其「未還原」揭露的觸發情形隨之改變（各功能 owner 知悉，不在本 ADR 範圍）。
- **〔2026-10-03 修訂〕** 已實作的 `MarketPanelReader.dividend_announce_observations` 不進持倉資料鏈，只留給測試與 V-1 查證；覆蓋規則須另接主 DB adapter。

**已知限制：** 沒有假日表；`market_trading_days` 在示範加真實資料混合的資料庫裡會多算交易日（`cache.py:476-483`），F5 在那種情況會偏向判 null。

---

## 對實作的約束（逐條可檢查）

**後端（dev-lead；data-engineer 負責 D-5、F7、P-17 查證）**
- **K-1**：`Valuation`（`valuation.py:182-195`）與 `PriceInfo`（`:126-141`）不新增漲跌欄位。三個既有估值測試檔不改任何斷言即可通過（ADR-0014 I-17）。
- **K-2**：收盤版的基準只來自 `_resolve_price` 同一份 `result.bars`。有假服務測試確認每個部位的價格服務呼叫次數和改版前相同。
- **K-3**：`app/portfolio/price_change.py` 不 import `app.dividends.adjust`、`app.sectors`、`app.data.market_panel`（import graph 測試）。
- **K-4**：advice、alerts、kelly、playbook、signals、limits 不讀 `.change`（grep 測試）。非 summary 的四個呼叫端回傳的 `change` 恆為 null。
- **K-5**：`pct` 由後端算，前端不得自己用現價和 basis 重算（不要照 `pnlPercentTwd` 在 `positionsTableView.ts:78-86` 的前端算法）。
- **K-6**：`change` 為 null 時，不得回傳可供顯示的原因字串。目前沒有核可字面，原因只寫 log。
- **K-7**：除權息查詢和行事曆查詢每本帳各一次批次，不得每檔一次。
- **K-8**：收盤版漲跌欄的後端 PR（`work/stock-desk-首頁重排-視覺規範-2026-10-03.md` 第 9 節依賴項 D1；與 ADR-0014 Options D1 無關）要先加 `PriceInfo.price_kind`（預設 `"daily_close"`），前端就不必推斷 kind。
- **K-16**（2026-10-03 修訂）：`app.api.portfolio`、`app.portfolio.*`、`app.advice.*`、`app.dividends.coverage`、`app.dividends.store`、`app.dividends.sync` 皆不可達 `app.data.market_panel`；`app.portfolio.*` 不可達 `app.dividends.coverage`（依賴單向）。（import graph 測試）
- **K-17**（2026-10-03 修訂）：`AnnounceRunCoverageRule` 只在 `app/api/portfolio.py` 的 summary 端點注入 `ChangeScreen`（與 D-3 同一處）；其他 `build_summary` 呼叫端不注入。
- **K-18**（2026-10-03 修訂）：`dividend_events` upsert 與 `dividend_sync_runs` 寫入在同一 transaction；`recorded_at` 只來自 store 時鐘；CLI 與排程走同一個同步函式。
- **K-19**（2026-10-03 修訂）：`dividend_sync_runs`、`dividend_sync_unparsed` 具 append-only trigger；表名不以 `pit_` 開頭。
- **K-20**（2026-10-03 修訂）：覆蓋判定整本帳一條 SQL；讀取失敗、naive 時間戳一律回 `unknown`，不拋例外。
- **K-21**（2026-10-03 修訂）：`MIN_ANNOUNCE_LEAD_DAYS`、`SHOW_WHEN_COVERAGE_UNKNOWN` 為 `Final` 模組常數；`app/` 內無環境變數或設定讀取參與兩者（grep 測試）。

**前端（frontend-engineer）**
- **K-9**：只有一個衍生值：`allowIntraday = summary.change_mode === "may_include_intraday"`。以下全部只讀它：
  - 表頭（`收盤漲跌` 或 `漲跌`）。
  - 手機小標。
  - 排序選項第 8、9 項。`SORT_OPTIONS`（`positionsTableView.ts:176`）要改成依模式產生，而且欄名要引用同一個表頭常數（風控第 4 項）。
  - 是否允許渲染 `intraday_quote` 列。

  `TODAY_CHANGE_SLOT`（`positionsTableView.ts:65-71`）要刪除，不得成為第二個開關。
- **K-10**：`!allowIntraday` 時，如果出現 `intraday_quote` 列（契約違反），該列的價格格和漲跌格都顯示「—」，不顯示盤中標籤。
- **K-11**：格內 fail-closed：以下任一成立，整格只顯示「—」，不帶任何基準字樣：
  - `change` 為 null。
  - `pct` 無法解析。
  - `basis_date` 是 null 或空字串。
  - `basis_kind` 不在已知集合內。
  - `basis_kind` 和該列 `price_kind` 對不上。
- **K-12**：`{MM/DD}` 只做字串格式化，直接取 `basis_date`，不做任何日期運算（風控 2c(i)；ADR-0014 I-10）。
- **K-13**：數值一律用 `formatSignedPercent`（`positionsTableView.ts:89`），紅漲綠跌用 `pnlColorClass`（`format.ts:257`）。
- **K-14**：`盤中價較昨收` 在風控 2d 的 (a)～(d) 完成前不得出現在非測試檔。在那之前，`basis_kind=="intraday"` 的列一律顯示「—」。
- **K-15**：沒有 `NEXT_PUBLIC_*` 或任何時間常數參與開關（沿用 I-10 的 grep）。

---

## 測試要求

**後端（pytest）**
- **T-1**：`price_change` 表格驅動測試，F1～F8、G1～G5 每條至少一例。另外要有這些邊界：
  - `ex_date == basis_date`：不判 null。
  - `ex_date == price_date`：判 null。
  - 行事曆是空的：照常顯示。
  - 週一的基準日是週五：照常顯示，`basis_date` 是週五。
  - Decimal 量化與字串序列化。
  - F7 邊界（TW，`basis_price=100`）：現價 111 或 89（`pct`＝±11.0000）不判 null；現價 111.01 或 88.99（±11.0100）判 null；US 標的 ±20% 不因 F7 判 null。
- **T-2**：風控 2c(ii) 的不變式，針對 summary 每列：
  - `change` 非 null ⇒ `basis_kind` 對應 `price.price_kind`。
  - `basis_date < price.as_of`。
  - 用 `price.value` 和 `basis_price` 以同一個量化函式重算，結果與 `pct` 相等。
- **T-3**：I-33、I-34；非 summary 呼叫端的 `change` 恆為 null。
- **T-4**：計數測試：收盤版不增加價格服務呼叫。盤中版 `get_daily_bars` 0 次、`get_cached_bars` ≤1 次。
- **T-5**：用合成 fixture 測「`y` 不等於快取收盤」⇒ null；檔名要明標 `synthetic`（ADR-0014 L340）。
- **T-6**：import graph（K-3）與 `.change` 的 grep（K-4）。
- **T-12**（2026-10-03 修訂）：K-16 的 import graph；同時把既有 `tests/test_market_panel_boundary.py::test_c7_import_graph_cannot_reach_market_panel_from_the_positions_chain` 補齊 ADR-0012 T-3 所列 `app.portfolio.*`、`app.advice.*`。
- **T-13**（2026-10-03 修訂）：同步紀錄。成功同步 ⇒ 一列 ok run 且事件已寫入；注入寫入中途失敗 ⇒ 兩者皆不落地；adapter 失敗 ⇒ failed run、`dividend_events` 不變；對兩表 UPDATE／DELETE 皆 abort；呼叫端無法指定 `recorded_at`。
- **T-14**（2026-10-03 修訂）：以主 DB adapter 重跑 `tests/test_dividends_coverage.py` 全部情境，另加：unparsed 代號 ⇒ `unknown`；`unattributed_count > 0` 的 run ⇒ 每個查詢代號 `unknown`；naive ⇒ `unknown`；讀取錯誤 ⇒ `unknown`；整本帳一條 SQL。
- **T-15**（2026-10-03 修訂）：summary 端點整合。覆蓋判定拋錯或同步表不存在時回 200，漲跌欄依 `SHOW_WHEN_COVERAGE_UNKNOWN` 照常；`MIN_ANNOUNCE_LEAD_DAYS == 1` 與 `SHOW_WHEN_COVERAGE_UNKNOWN is True` 皆有測試釘住。

**前端（vitest）**
- **T-7**：兩個表頭字面逐字釘住；表頭、手機小標、排序第 8／9 項指向同一常數。
- **T-8**：任何 fixture 組合下，`收盤漲跌` 表頭都不會和 `intraday_quote` 列同時出現（風控 2b）。
- **T-9**：雙向釘住（風控待裁示點 (i)）：
  - 非 null 時一定有標籤，而且種類與 `price_kind` 一致。
  - null 或任一 K-11 條件成立時只顯示「—」，該格不得出現「較」「收盤」「昨收」。
- **T-10**：`較 — 收盤`、空的 `{MM/DD}`、沒帶 `%` 的數字都不得出現。
- **T-11**：排序時空值永遠排最後，混合基準照常可排。

---

## 待查證參數

〔2026-10-03 修訂新增〕本段參數皆為未查證的保守預設，不得當作已驗證事實引用。不併入 ADR-0014 P 表：P 表綁定 MIS 盤中實測（10/05、W13、`quote_params.py`、I-28），V 系列屬 `TWT48U_ALL` 與本 ADR。

| 編號 | 參數 | 預設 | 定義 | 狀態 |
| --- | --- | --- | --- | --- |
| V-1 | `MIN_ANNOUNCE_LEAD_DAYS`（`app/dividends/coverage.py`） | 1 | 最大整數 L，使任一上市除權息事件（除權息日 E）自 Asia/Taipei E−L 日 00:00 起至 E 前，每一次 ok 同步皆列於 `TWT48U_ALL`。這是資料集的列出時點，不是發行公司的公告義務 | 待查證 |

V-1 查證判準：
1. 主證據為實測：data-engineer 以唯讀離線腳本讀市場 DB 的 `pit_snapshot_runs`（`kind='dividend_announce'`、`status='ok'`）與 `pit_dividend_announce_rows`（離線查證不屬持倉資料鏈，不違反 ADR-0012 C-7），對每個事件 (symbol, E) 計算 ℓ = ⌊(E 當日 00:00 Asia/Taipei − 首次列出該事件之 run 的 `recorded_at`) ÷ 1 日⌋。
2. 持續性：同一事件自首次列出至 E 前的每個 ok run 都須列出；消失或日期變更者逐筆列出並說明，有未說明者不得調高。
3. 樣本：至少涵蓋一個完整的 6～9 月除權息旺季；回報事件數、run 數與缺 run 的日期。
4. 新值 ≤ min(ℓ) − 1。
5. 官方規章只作佐證：由有網路者取得，記錄名稱、條次、URL、取得日期與原文摘錄；規章約束的是發行公司，不證明 OpenAPI 的列出時點，不得單獨作為調高依據；規章下界小於第 4 點的值時，取較小者。
6. 證據放 `work/`，並修訂本表 V-1 列（新值、查證日期、證據路徑）；治理依 D-5.6。

---

## 不該做的事

- 不用還原價、不用參考價、不用 `y` 直接當分母，也不用 `y` 去補缺的基準。
- 不在 build_summary 另讀快取取基準，也不擴大 `PRICE_LOOKBACK_DAYS`。
- 前端不推算前一交易日、不自算 `pct`，也不用 `price_basis` 計數、`session_state` 或環境變數切換表頭。
- 不把 `change` 交給規則引擎、警示或風控上限使用。
- 不新增 `DataStatus` 值，也不把 MIS 價格寫進日線（ADR-0014 I-1、D-3）。
- 不在剩餘揭露核可前，就默認除權息假跌「已處理」。
- 〔2026-10-03 修訂〕不在持倉資料鏈（含 `app/api/portfolio.py`）讀市場 DB，也不讓 F6 讀 `pit_dividend_announce_rows`；要改須另立 ADR 取代 ADR-0012 C-7 的相關部分。
- 〔2026-10-03 修訂〕主 DB 同步不共用市場 DB 擷取的 HTTP 結果，兩條鏈不寫入對方的資料庫。

---

## 交接與升級

- **tech-writer**：把本 ADR 落檔（proposed）；在 ADR-0014 加修訂註記。（本次已完成；ADR-0014 修訂見其 L7 修訂行。）
- **dev-lead**：負責 K-1～K-8、T-1～T-6。
- **data-engineer**：
  - 寫 D-5 的覆蓋判定函式。
  - 查證 F7 中槓桿或反向 ETF 的漲跌幅限制。
  - 查證 P-17（`y` 在一般日和除權息日的語意）。
  - 建議把 TWT48U 同步排進排程。這件事要 CEO 核可、devops-sre 執行。
  - **〔2026-10-03 修訂〕** 依 D-5.2 實作主 DB 同步紀錄（兩表、同 transaction、store 讀取方法與 adapter；adapter 需能分辨 unparsed 代號與無代號列）；執行 V-1 實測查證；把 `MarketPanelReader.dividend_announce_observations` 與 `DividendAnnounceObservation` 的 docstring 改為「市場 DB 版本僅供測試與 V-1 查證，持倉資料鏈不得呼叫（ADR-0012 C-7）」。
- **devops-sre**（2026-10-03 修訂新增）：CEO 核可後，在 `app/scheduler.py` 新增 TWT48U 同步排程：平日、Asia/Taipei、排在 `pit_snapshot_capture` 之後；同一台北日期已有 ok run 即跳過；沿用既有 `_guarded`、`max_instances=1`、`coalesce=True`；呼叫與 CLI 相同的同步函式（`trigger='scheduled'`）；不新增任何會改變覆蓋判定語意的環境變數。
- **frontend-engineer**：負責 K-9～K-15、T-7～T-11。
- **creative-lead 到 risk-compliance-officer**：
  - D-6 的剩餘揭露句。
  - 確認 β 方案滿足 2d 的前置 (a)、(b)：β 方案下 `prev_close` 不當分母，「昨收」由快取收盤保證；`y` 語意錯判時結果是「—」。
- **CEO**：見下節「需要 CEO 決定」。
- **quant**：知悉 A1 加 F6 / F7 加剩餘揭露的處理方式。

---

## 需要 CEO 決定

> 裁定結果（2026-10-04，來源：CEO 2026-10-04 核可「ADR-0016、ADR-0017 可以開始執行」；各點逐項結果依任務單轉述）。以下各點正文為核可前原文，裁定以「**〔裁定 2026-10-04〕**」標註。

1. **核可 ADR-0016 與 ADR-0014 的修訂。** **〔裁定 2026-10-04：✔ 核可。〕** 範圍註記：ADR-0014 本身狀態維持 `proposed`（盤中功能待 10/05 實測），其依本 ADR 所加之註記隨本 ADR 核可生效（見 ADR-0014 修訂行 2026-10-04 補註）。
2. **裁定剩餘揭露（D-6）是否必須與收盤版同時上線。** tech-architect 建議同一批上線，並請風控或 CEO 決定是否放寬成不擋上線。風控立場：必須同 PR。 **〔裁定 2026-10-04：✔ 剩餘揭露與收盤版同批上線；已於 2026-10-03 同批落地（commit `ca46e6f`）。〕** 備註：tech-writer 僅確認 `ca46e6f` 在 `work/reviews/2026-10-03-漲跌欄-e2e驗收.md` 為漲跌欄 e2e 驗收的受測 commit，未逐一核對該 commit 內容。
3. **〔2026-10-03 修訂〕核可 D-5 的 2026-10-03 修訂**：不對 ADR-0012 C-7 開例外；覆蓋判定與 F6 只讀主 DB；主 DB 新增兩張同步紀錄表。 **〔裁定 2026-10-04：✔ 核可。〕**
4. **〔2026-10-03 修訂〕核可 TWT48U 同步排程化**（devops-sre 執行）。影響：D-5 開始可能回 `known`；`dividend_events` 逐日累積，回測、Kelly、事件研究的除權息還原範圍隨之改變。不核可時，覆蓋判定只在手動同步後短暫可能回 `known`，F6 維持手動資料，其餘維持現狀。 **〔裁定 2026-10-04：✔ 核可；隨本 ADR 核可一併執行，上述影響（副作用）已載明於本點與 Consequences。執行依「交接與升級」的 devops-sre 條目；落地狀態待查證，查法：`app/scheduler.py` 是否已有 TWT48U 同步排程，及主 DB `dividend_sync_runs` 是否出現 `trigger='scheduled'` 的列。〕**
5. **〔2026-10-03 修訂，知會〕** `SHOW_WHEN_COVERAGE_UNKNOWN` 本次不提改動；排程上線滿四週後，由 data-engineer 提交 `known` 比例統計，再請 CEO 決定是否檢討。 **〔2026-10-04：知會維持，不變。〕**

---

## 查證限制

（以下為草案作者 tech-architect 的聲明，原樣轉錄。）

- 我沒有 Bash，以上沒有跑測試。`get_daily_bars` 的 layer 0 和增量路徑會回傳完整的 `[start, end]` 區間，這是依 `service.py:158-237` 的閱讀推定。yfinance 的 chart close 是否已做分割調整，未查證。

---

## 相關檔案（絕對路徑，草案作者所列）

- /home/user/AICompany/docs/adr/0014-stock-desk-盤中報價資料邊界顯示範圍與節流.md
- /home/user/AICompany/docs/adr/0001-record-architecture-decisions.md
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/summary.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/interface.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/quote_params.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/quote_quality.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/cache.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/market.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/adjust.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/providers.py
- /home/user/AICompany/apps/stock-desk/backend/app/sectors/definition.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/portfolio.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/positionsTableView.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/types.ts
- /home/user/AICompany/work/reviews/2026-10-03-首頁重排-第二階段字面-風控核可.md
- /home/user/AICompany/work/stock-desk-首頁重排-視覺規範-2026-10-03.md
- /home/user/AICompany/work/stock-desk-首頁重排-第二階段字面-起草-2026-10-03.md

---

## 附錄：tech-architect 評估摘要（草案前言，原樣轉錄）

結論：

1. **採用未調整收盤對未調整收盤**。分子是該列畫面上顯示的現價，分母是同一次估值、同一份 `ProviderResult` 裡前一根 bar 的未調整收盤。基準要在 `_resolve_price` 內、用同一批 bars 取得（`valuation.py:322-338`，回看窗 `PRICE_LOOKBACK_DAYS=10`，`valuation.py:54`）。這樣不會多一次 IO，也不會出現第二份序列。
   - 否決還原價。`dividends/adjust.py:12-18` 明文規定估值路徑不得使用還原價，而且還原後的分母不是任何一天的真實收盤，`較 {MM/DD} 收盤` 這句就不是事實。
   - 否決用除權息參考價當分母，理由相同：寫「收盤」與事實不符。
2. **盤中版建議改走「β 方案」，不直接拿 `y` 當分母。**
   - 分母一律用日線快取裡 `trade_date` 之前最近一根 bar 的未調整收盤。MIS `y` 只拿來做等值比對：兩者 Decimal 相等才算數，不相等就整格 null。
   - 這樣 ADR-0014 D-1「`prev_close` check input only」（ADR L123；`interface.py:463-464,480-481`）字面上仍然成立。除權息日 `y` 如果其實是參考價，比對會失敗，結果是「—」而不是錯標「昨收」。風控 (b) 因此在 runtime 自動 fail-closed，不只靠一次查證。
   - 代價：I-18 要修訂，允許至多一次 cache-only 的 `get_cached_bars`。另外盤中漲跌加一個預設關閉的開關常數 P-17，查證完成後才開。
3. **表頭開關用後端在建構期決定的常數 `change_mode`。** 否決 `price_basis` 計數和 `session_state`，因為兩者都會隨資料或時段變動，違反風控 2b「不能隨每次載入的資料切換」。也否決前端常數或環境變數（ADR-0014 L539 已否決用環境變數開關盤中功能）。
4. **除權息假跌只能部分擋住，剩下的必須揭露。**
   - 擋得住的部分：`dividend_events` 能證明窗內有除權息日時回 null。但 `TWT48U_ALL` 只涵蓋上市股，而且只列未來的除權息日（`dividends/providers.py:92-97,101-106`；ADR-0012 L122），scheduler 也沒有排程同步（`scheduler.py` 查無 dividend 字樣）。
   - 擋不住的部分：上櫃股、美股、未同步期間的除權息，以及美股或 ETF 分割。這些需要一句揭露，由 creative-lead 起草、風控審。**我建議它和收盤版同一批上線**（請風控或 CEO 決定是否放寬成不擋上線）。
5. **事實更正**：風控紀錄 L61 寫「accepted ADR」，但 ADR-0014 目前是 `proposed`（ADR-0014 L3）。依 ADR-0001 L18，proposed 狀態可以原地加修訂註記，比照它在 L7 / L318 / L430 依 ADR-0015 加註的寫法。CLAUDE.md §2 的規則仍然照常適用，視同約束。

---

## 實作紀錄

- 2026-10-04：D-5.2 主 DB 同步紀錄與 adapter 已落地（commit `69c3c22`，未接線）；K-17 接線與 D-5.4 排程另案進行。
