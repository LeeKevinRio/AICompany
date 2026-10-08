# tech-architect 評估（2026-10-08，唯讀；coordinator 轉錄）：第 4 條 W-a2 在 PR-0 後的可達性、F-6 修法方向

- 來源：第二十六輪 qa-e2e 另案（第 4 條 W-a2 無法驗收）、風控小項裁定第 4 項（`opened_at` 留空推定）、F-6 任務單 draft。
- **結論 1：第 4 條 W-a2 可達，且只用正式 API 即可建出**——同一檔美股（US／USD）兩批，一批有建倉日期、一批 `opened_at` 留空 → 後者 `fx_open` 缺、記 insufficient_data；book 層幣別單一、匯率可解、close 與 ATR 保留、own=1。同路徑也到第 1、5 條 W-a2 與 D-5 own>0。第二十六輪結論 2 與 `test_adr0023_own_unvalued.py:814-815` 註解「正式 API 建不出」不精確。ADR-0023 應加註可達路徑與驗收前提，**不得寫成不可達**。
- **結論 2：F-6 採 (a)**（只改 `app/data/service.py` `_fall_back_to_cache` 有快取分支、`combined is None` 時補句），否決 (b) 作為修法；美股無此問題；不需新 ADR，在 **ADR-0009 D-3** 加註；約束 F6-C1～C8。字面是否可沿用 `RECENT_ATTEMPT_FAILED_REASON` 由風控裁定。
- coordinator 定案（CEO 可推翻）：第 4 條 W-a2 先以 API 層正式路徑測試結案（qa-automation，待 X3b 兩個 commit 完成後派工以免混入 staged diff）；e2e 實機補驗列為待辦，前提是 devops-sre 提供核可的 FX stub（不得以放寬唯讀邊界處理）。

全文如下（標題層級各降一級）。

### 本次結論

**問題 1：第 4 條 W-a2 在 PR-0 之後仍然可達，而且可以只用正式 API 建出來。風控提出的推定成立。**
- 成立條件：同一檔美股（US／USD）建兩批，一批填建倉日期、另一批 `opened_at` 留空。留空那批的 `fx_open` 會是 None，估值記為 `insufficient_data`，`missing` 為 `["fx_open"]`。
- 這時 book 層只有一種幣別、匯率解得出來，close 和 ATR 都保留，own=1，第 4 條比率算得出來；比率超過上限就是 violated 加 W-a2。
- 同一條路徑也能讓第 1、5 條出現 W-a2，以及 D-5 的 own>0 分支。所以第二十六輪結論 2「W-a2、D-5 加 own>0 在正式 API 路徑不可達」不精確，`tests/test_adr0023_own_unvalued.py:814-815` 的註解（「test client 建不出同標的一批已估值、一批未估值」）也不精確。
- **ADR-0023 不應加註「不可達、保留為防禦」**，要改加註可達路徑與驗收前提（見下一步）。

**問題 2：F-6 建議採 (a)，否決以 (b) 當修法，不需要新 ADR，在 ADR-0009 D-3 加註即可，不是 ADR-0005。**
- (a) 只改 `service.py` 的 `_fall_back_to_cache`，而且只改「有快取」那個分支，條件是 `combined is None`。
- 句子建議用 `service.py` 裡的單一常數。架構上我建議直接沿用 `RECENT_ATTEMPT_FAILED_REASON`：首次失敗時，「最近一次」就是這一次，句意成立，而且第一次和第二次回覆會逐位元組相同。但這句能不能用在新情境，由風控裁定；風控要另擬時由 creative-lead 起草。我不定字面。
- 美股沒有 F-6 的問題。

### 各部門回報

#### tech-architect：問題 1，「本標的有批次未估值」的成因逐一判定

前提有兩個：
- own 的計數是 `_unvalued_composition` 數 matched 裡 `valuation.status != "ok"` 的批次，`symbol_has_unvalued_lots` 讀的就是這個計數，所以 `fx_open` 缺的批次會算成 own。
- 第 4 條用 `held_shares()`，也就是 `quantity`，只加總已估值的批次。

所以要到 W-a2，必須「同標的有已估值批次，也有未估值批次」，而且 close 和 ATR 不能被撤下。

| 成因 | atr 是否非 None 且 own>0 | 能否到 W-a2 |
| --- | --- | --- |
| 價格缺（沒有 adapter、UNAVAILABLE、沒有 bars；live 或 cache_only） | 同一個 (symbol, market) 的所有批次共用同一次取價，會一起失敗，已估值股數為 0。advice 的 close 走另一條 live 的 `load_bars`，所以 atr 可能在（cache_only 漏抓，正好就是測試 :894 的情境），但比率是 0 | 不可達，只會到 W-a1 |
| close 非正值（F-1） | 估值時整檔一起丟；卡片 `advice.py:179` 的 latest 為 None，回 insufficient_data；book 層 `priced=False`，close 和 atr 一起撤下 | 不可達 |
| `fx_now` 缺（今日匯率） | 同幣別所有批次一起失敗，已估值股數為 0；卡片的 fx 通常也失敗，會撤下 | 不可達 |
| **`fx_open` 缺（`opened_at` 為 None，或建倉日前 7 天內查不到匯率）** | **逐批判定**，其他批次可以 ok；卡片幣別單一、匯率可解，close 和 atr 都保留 | **可達** |
| 幣別混雜 | `book.py:1114-1124` 把 rate 設成 None，close 和 atr 一起撤下 | 不可達 |
| legacy A 型（US 市場、TWD 幣別） | fx 恆為 1，估值是 ok，不會讓 own>0；和一致的批次並存時變成混雜，會撤下 | 不可達 |
| legacy B 型（TW 市場、USD 幣別） | 卡片 fx 依 bar 的幣別（TWD）解析，得到 None；`_resolve_fx("USD", None)` 回 `NO_FX_QUOTE`，撤下 | 不可達 |
| X-3c 之後的不符列 | KX-A4 規定 rate、close、atr 全部為 None | 不可達 |
| 退化情形（low，非本案） | `max_loss_per_trade` 只有 `gt=0` 的限制，門檻 ≤ 1e-9 時比率 0 也會判成 `_breaches`，全部未估值的批次也會走到 W-a2 | 理論可達，屬既有的邊界問題 |

**現有測試怎麼構造第 4 條 W-a2：**
- 單元測試 `test_own_unvalued_lots_keep_a_breach_with_w_a2`（:358-374）用手組的 `_ctx(own_lots=1, close=100, atr=2, **_BREACH)`，不經過 `build_book_context`。
- API 測試 :873-891 用 monkeypatch 換掉 `build_summary`，而且在那個帳本裡第 4 條斷言是 **W-a1，不是 W-a2**（:888）。
- 結論：目前沒有任何經正式路徑的第 4 條 W-a2 測試。

**交給 qa-automation 的最小 fixture（API 層 pytest）：**
1. 環境沿用 `test_pr0_cap4_atr_backfill.py` 的做法：
   - `us_market`（:120-127）seed `recent_bars(trending_closes(200), symbol="AAPL", market="US")`，resolver 設成 `{"TW","US"}`。
   - live 和 cache_only 兩個 valuator 都接 `_FlatFx()`（:70-84 和 :130-138）。
   - `get_fx_provider` 也覆寫成 `_FlatFx()`（:281）。
2. `POST /api/positions` 送 `position_payload(symbol="AAPL", market="US", currency="USD", quantity="100", opened_at="2024-01-02")`，這批會是 ok。
3. `POST /api/positions` 送 `position_payload(symbol="AAPL", market="US", currency="USD", quantity="10", opened_at=None)`，這批應為 insufficient_data，`missing == ["fx_open"]`。
4. 選做：`PUT /api/kelly-inputs/AAPL?market=US` 送 `{win_rate:0.6, payoff_ratio:2.0}` 驗第 5 條 W-a2；改成 f*≤0 的組合可驗 D-5 own>0。
5. 呼叫 `GET /api/advice/AAPL?market=US`，斷言：
   - `unvalued.own_lots == 1`，close 和 atr 非 null，`fx_to_twd == 31.5`，沒有混雜或匯率失敗的 note。
   - 第 4 條 detail 等於「同帳本去掉第 2 批」的參考 detail 加 W-a2，observed 等於參考值，`format_percent(observed)` 出現在 detail 裡。第 1 條（佔比 100%）同理。
6. 前提要先斷言：參考帳本的第 4 條必須是 violated。AAPL 是唯一已估值部位時，比率約等於 2×ATR/close，需要 ≥ 1%。如果 fixture 的 bars 波動太小，可以經設定 API 調低 `max_loss_per_trade`，或換波動較大的 bars。
7. 警示快照（`build_snapshot("AAPL","US", …)`）可以用同一套構造再驗一次。

**qa-e2e 實機驗收的前提：**
- USDTWD 要解得出來。FX 目前沒有快取層（`fx.py:313,325`），直寫 DB 補不了匯率，所以要嘛有對外網路，要嘛由 devops-sre 建一個經核可的 FX stub。
- advice 用 cache_only 估值（`deps.py:171-185`），AAPL 的日線要先在 bar cache 裡。
- 兩批持倉都經正式的 POST 或 UI 建立。

**與 dev-lead 進行中工作的關係：**
- X-3b 規定估值輸出逐位元組不變；KX-10 只改 A 型的 book 層和 snapshot。兩者都不動 `fx_open` 的語意（`valuation.py:438-446`）。
- 以後如果有人改成「沒有建倉日就拿 fx_now 代替」，這條路徑就會消失，到時要重新評估。

#### tech-architect：問題 2，F-6 評估

**比較 (a) 和 (b)：**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **(a) 由 service 在 `_fall_back_to_cache` 的有快取分支，`combined is None` 時補句（採用）** | 「所有 live rung 都失敗、改回快取」這件事只有編排層知道，這句也屬於編排層；和冷卻期路徑（:384、:425）對稱；之後新增的 adapter 不會再退化成 null；有先例（ADR-0015 C-8：FX 梯子失敗且有快取列時 reason 必須非空，由快取層保證，不靠 adapter） | `_try_provider` docstring（:481-485）「不替 provider 補猜」要改寫，說清楚這句陳述的是 service 自己知道的事實，不是猜原因 | 低 |
| (b) TWSE、TPEx、FinMind 失敗時帶 reason | 原因較具體（美股 adapter 已經這樣做） | 不保證非 null：還有 TWSE `not bars`（:133-140）、TPEx（:268-275）、FinMind 缺 token（:102-106）等路徑；上櫃股在 TWSE 本來就查不到，那是正常結果，補句會變成歸因錯誤；每個來源要一句新文案，都要送風控；冷卻期路徑仍會改成另一句，第一次和第二次的字面還是不同 | 中 |
| 其他：在 attempt log 存最後一次失敗原因，讓前後回覆完全一致 | 字面和請求順序無關 | 要改 ADR-0009 的 schema 和 D-3，超出 F-6 範圍 | 不採，列管 |

(b) 可以留作日後提升原因具體度的選項，但不能當成修掉 null 的方法。

**美股：** 沒有這個問題。Alpha Vantage 每條失敗路徑都帶 reason（`alpha_vantage.py:234-303`）；yfinance 的 `_unavailable` 規定 reason 必填（`yfinance.py:129-137, 165-182`）。

**沒有快取的分支（:563-571）：** 不在 F-6 範圍內。API 層由 `NO_BARS_REASON` 加 provider reason 組句（`services/market.py:170-175`），不是 null。這裡也絕不能補「暫以本機快取回覆」，因為不是事實。

**對既有測試的影響：**
- `test_service.py:766` 的 `degraded.reason == spliced` 必須改。這行目前固定的就是 F-6 的缺口，而它自己 :762 的註解寫著「the failure reason and the splice both stand」，改完反而和註解一致。PR 裡要明列這一處。
- `test_service.py:303-329` 補上對 `first.reason` 的斷言。
- `test_price_info_freshness.py` 用 stub service，不受影響；`get_cached_bars` 零改動。

**前端：**
- `DataStatusBadge.tsx:58-65`：is_within_ttl 不為 true 時，reason 顯示在「資料較舊」的 title；原本的後備字「可能未含最近交易日」（:9）在首次載入時會被新句取代。
- is_within_ttl 為 true 時這個徽章不顯示，reason 不會出現在持倉表上。
- 卡片頁的 DataMetaStatusBadge 會常駐顯示 reason（ADR-0009 D-5）。第二次載入原本就走這個版面，不是新版面。

**e2e：**
- 第二十六輪 A 情境 `price.reason=null` 的基準要重錄，verify.py 對 TW 降級回快取的期望值要改成常數。
- 驗收條件第 3 條要收窄成「不再出現 null 與非 null 之間的差異」。原因是 combined 非 null 時（美股，或 TW 的 `UNEXPECTED_ERROR_REASON`、`MERGE_READBACK_FAILED_REASON`），第一次和第二次仍然是兩種非 null 字面，這是刻意不擴張範圍。

**ADR：** 這句原本歸 ADR-0009 D-3，D-5 已規定降級路徑和第 0 層共用同一套規則；ADR-0005 決策四第 1～4 點已被 ADR-0009 取代（ADR-0009 L12）。所以由 tech-writer 在 **ADR-0009 D-3 加註**，依據是 ADR-0003 約束 7。不需要新 ADR。

**對實作的約束（qa-reviewer 可以逐條核對）：**
- F6-C1：只改 `service.py`；`twse.py`、`tpex.py`、`finmind.py` 零 diff。
- F6-C2：只在有快取的分支、`combined is None` 時補句；沒有快取的分支的 reason 不變。「確實嘗試過」要明示：目前唯一呼叫點是 :242，請用參數或註解固定下來，避免以後沒跑梯子的呼叫端繼承這句。
- F6-C3：combined 非 None 時，輸出逐位元組不變；要加美股型（provider 有帶 reason）的回歸測試。
- F6-C4：句子是 `service.py` 的模組常數。如果沿用 `RECENT_ATTEMPT_FAILED_REASON`，不新增任何繁中字串；如果另擬，常數旁要附風控核可註記。
- F6-C5：順序是失敗句在前、拼接句在後（沿用 `_cached_result` 的組法）。
- F6-C6：`get_cached_bars`（cache-only）零改動（ADR-0010 R-5：這條路徑沒有向來源詢問）。
- F6-C7：`as_of`、`staleness_minutes` 不變（風控 R-10）。
- F6-C8：要有單元測試：首次失敗即帶 reason，第一次和第二次的字面相同（或差異經風控核可）。

### 驗證

只讀，沒有跑測試、沒有跑 git。dev-lead 正在改工作樹，下列行號可能漂移。

**問題 1 的程式：**
- `app/advice/limits.py`：362-395（W-a1／W-a2 常數）、852-859（`held_shares`）、989-1011、1093-1111（`symbol_has_unvalued_lots`）、1270-1303（第 4 條）、557-559（budget 欄位）
- `app/advice/book.py`：427-457、481-520、606-714（`_unvalued_composition`）、1040-1205（`build_book_context`／`_resolve_fx`）
- `app/portfolio/valuation.py`：20-47、262-489（特別是 317-350、388-410、430-447）
- `app/positions/models.py`：60-259（`opened_at` 可為 None 在 :141；`PositionWriteInput` 在 :208-226）
- `app/api/advice.py`：143-229；`app/api/deps.py`：75-185；`app/alerts/snapshot.py`：100-132；`app/services/fx.py`：57-97；`app/data/price_guard.py`：24-36

**問題 1 的測試：**
- `tests/test_adr0023_own_unvalued.py`：110-433、660-1059
- `tests/test_pr0_cap4_atr_backfill.py`：60-149
- `tests/conftest.py`：100-169；`tests/api_helpers.py`：161-185

**問題 1 的工作文件：**
- `work/reviews/2026-10-08-第二十六輪-PR-0第4條ATR與6-a非對稱判定-e2e驗收.md`（grep W-a2 段落）
- `work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md`（grep KX-10／KX-A4）

**問題 2 的程式：**
- `app/data/service.py`：1-572
- `app/data/providers/twse.py`：90-149；`tpex.py`：225-284；`finmind.py`：40-119；`yfinance.py`：126-255；`alpha_vantage.py`（grep reason，:234-344）
- `app/data/interface.py`：100-115、160-168；`app/services/market.py`（grep reason）
- `frontend/app/components/DataStatusBadge.tsx`：全檔

**問題 2 的測試與文件：**
- `tests/test_service.py`：135-330、735-769、810-834；`tests/test_price_info_freshness.py`：100-239
- `docs/adr/0009-…`：1-110；`docs/adr/0015-…`、`docs/adr/0023-…`（grep）
- `work/dispatch/2026-10-08-任務單-F-6-首次取價失敗時快取回覆缺少reason說明.md`：全檔

**沒查證的部分：** 沒有實際跑 fixture，`trending_closes(200)` 算出的 ATR/close 是否 ≥ 0.5% 未驗證，所以 fixture 要求先斷言前提。

### 下一步

1. **qa-automation**：依上面的 fixture 補第 1、4、5 條 W-a2 和 D-5 own>0 的正式路徑測試，snapshot 一併驗；同時把 `test_adr0023_own_unvalued.py:814-815` 的註解改成「TW 建不出；US 的 opened_at 留空可以建出」。
2. **tech-writer**：
   - ADR-0023 Decision 4 加註：W-a2 在正式路徑可達，成因是同標的有一批 US 持倉建倉日期空白、`fx_open` 缺；e2e 前提是 USDTWD 解得出來。**不要寫成不可達。**
   - ADR-0009 D-3 加註 F-6 的處置。
3. **coordinator**：更正第二十六輪結論 2；決定第 4 條 W-a2 的 e2e 補驗要等網路或 FX stub，還是先以 API 測試結案。
4. **devops-sre**：如果要做 e2e 補驗，提供一個經核可、能解出 USDTWD 的 FX stub；它是執行介面，不能用放寬唯讀邊界的方式處理。
5. **CEO**：F-6 立案。決定後由風控裁定能否沿用 `RECENT_ATTEMPT_FAILED_REASON`；不能沿用時，由 creative-lead 起草新句、風控逐字審。之後 dev-lead 依 F6-C1～C8 實作，qa-reviewer 加 Codex 審查，qa-e2e 重錄 price.reason 的基準。
6. **列管（low，本案不處理）**：`max_loss_per_trade` 門檻 ≤ 1e-9 的退化邊界；「F-6 前後回覆字面完全一致」的需求（要改 attempt log，屬 ADR-0009 修訂）。

**相關檔案：**
- /home/user/AICompany/apps/stock-desk/backend/app/advice/limits.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/positions/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_adr0023_own_unvalued.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_pr0_cap4_atr_backfill.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_service.py
- /home/user/AICompany/docs/adr/0009-stock-desk-日線快取以交易日判定新鮮度.md
- /home/user/AICompany/docs/adr/0023-stock-desk-風險上限分子不完整時的非對稱判定通則.md
- /home/user/AICompany/work/dispatch/2026-10-08-任務單-F-6-首次取價失敗時快取回覆缺少reason說明.md