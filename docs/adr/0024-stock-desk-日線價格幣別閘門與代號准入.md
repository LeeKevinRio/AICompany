# ADR-0024：stock-desk 日線價格幣別閘門與代號准入

- 狀態：**proposed**
  - **尚未經 CEO 核可，不得視為 accepted。** 本檔為 tech-architect 評估的落檔（2026-10-12 修訂版），不是核可紀錄。
  - **accepted 前提**〔TA2 R-1；F9W 第 6 題〕：T-5～T-9 的裁示結果須已納入本 ADR（本修訂納入 F9W-4、F9W-9、F9W-11、F9W-12、F9W-13、F9W-14）；T-1～T-4 的逐字字面（W-a～W-d 等）是 F-9b／F-9c 的**合併前提**，不是本 ADR 的核可前提。〔TA1 M-1 已被 TA2 R-1 取代〕
  - 本修訂版已納入上列裁示；**仍待 CEO 核可**（T-10）。核可時須一併知悉：本 ADR 對 ADR-0009 為「部分修訂」，**須 CEO 核可**〔TA2 下一步 4〕；X3-F7 前提在殘留 R-a～R-c 下不保證成立，CEO 須知悉〔TA2 R-6、F9W-13〕。
  - 與字面相關的待決事項、各字面核可狀態見文末「待決事項」。
- 日期：2026-10-12（tech-architect 評估日；落檔與本修訂版同日）
- 決策者：tech-architect（評估）；CEO（核可，**尚未核可**）。
- 適用範圍：僅 product/stock-desk 產品線。
- 標註約定：每處修訂內容以〔來源 編號〕標註。〔TA1 M-x〕＝tech-architect 第一次核對（落檔核對 M-1～M-15）；〔TA2 R-x〕＝tech-architect 第二次評估（風控裁定之工程影響，R-1～R-37）；〔TA3 R-x〕＝tech-architect 對 creative-lead 第二批四題的回覆（R-38～R-46）；〔TA4 R-x〕＝tech-architect 對本檔的抽驗與待確認項裁決（R-47～R-56；TA4 在下述衝突優先序中的位置，來源未載，與其他來源衝突時回報 tech-architect／coordinator，不自行裁決；TA4 送審項已由風控 F9W-30～F9W-34 裁示，風控裁定優先）；〔F9W-x〕＝風控裁定（F9W-1～F9W-16 為第一批、F9W-17～F9W-29 為第二批、F9W-30～F9W-34 為對 TA4 送審項的裁示）。**衝突時優先序：風控裁定 > TA3 R-38～R-46 > TA2 R-1～R-37 > TA1 M-1～M-15**；R-45 已修正 M-8，M-1 已被 R-1 取代；M 清單中 R 清單未涵蓋者照原文併入。
- 來源與版本（B 類轉錄）：
  - 原始技術來源（初稿）：`work/dispatch/2026-10-08-任務單-F-9-日線上游幣別未核對.md` 末段「tech-architect 架構評估（2026-10-12，唯讀讀碼；coordinator 轉錄）」，含其「結論」「現況盤點要點」「設計建議」「ADR-0024 草案要點（proposed）」「實作約束（F-9b 為主）」「拆 PR」「風險與相依」「coordinator 定案（CEO 可推翻）」各小節；以及該任務單開頭的起因、現況、影響、範圍與兩則補充（風控 F7-R8、F7-R14，2026-10-08）。
  - 本修訂版來源（2026-10-12，皆經 coordinator 轉錄）〔TA2 R-2〕：
    - 第一次核對：`work/reviews/2026-10-12-tech-architect-ADR-0024落檔核對M-1至M-15.md`（M-1～M-15 與失效條件意見）。
    - 第二次評估：`work/reviews/2026-10-12-tech-architect-F-9-風控裁定工程評估與ADR-0024修改清單R-1至R-37.md`（含 R-1～R-37、C-11～C-29、方向子句「四」、PR 拆分「五」）。
    - 第三次回覆：`work/reviews/2026-10-12-tech-architect-F-9-第二批字面四題回覆R-38至R-46.md`。
    - 第四次回覆（TA4）：`work/reviews/2026-10-12-tech-architect-ADR-0024抽驗與待確認項裁決R-47至R-56.md`（R-47～R-56；其讀碼基準為 product/stock-desk 工作樹現況、F-9a 已合併，唯讀、未執行測試）。
    - 風控對 TA4 送審項的裁示：`work/reviews/2026-10-12-F-9-R47至R49送審裁示-F9W-30至F9W-34-風控.md`（F9W-30～F9W-34；整體 APPROVE WITH CONDITIONS，無否決；coordinator 轉存，本檔據 coordinator 2026-10-12 補充指示納入）。
    - 風控裁定：`work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md`、`work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md`（第二批「下一步 2」要求將 F9W-18、F9W-23、F9W-24、F9W-25 寫入 ADR，並納入 F9W-17、F9W-21、F9W-27）。
  - 風控原始出處（任務單所述，tech-writer 未讀）：`work/reviews/2026-10-08-F-7-幣別標示字面逐字審-F7-R1～R8-風控.md`（F7-R6、F7-R8）；`work/reviews/2026-10-08-F-7-技術分析閘門偏離裁定-F7-R11至R14.md`（F7-R14、F7-R12 (ii)）。
  - **本檔所有技術敘述皆為轉錄（B 類），tech-writer 未讀後端 code 驗證。** 來源內所有 `檔案:行號`、函式名、常數名、測試名皆為 tech-architect 或風控所述，**保留原樣**；行號會隨 commit 漂移（F-9a 已合併後行號可能已變動），引用時以原文定位。草案若與 code 不符，應回報 tech-architect 確認，tech-writer 不自行裁決。
  - tech-writer 實際讀過的只有 ADR 之間的交叉引用（不是後端 code）：ADR-0003「對實作的約束」第 8 點（`docs/adr/0003-stock-desk-daily-data-source.md` L58）、ADR-0005「決策三：額度計數器與美股 ticker 正規化」（`docs/adr/0005-stock-desk-指數來源與美股額度管理.md` L133）、ADR-0009 R-5 列（`docs/adr/0009-stock-desk-日線快取以交易日判定新鮮度.md` L154，內容為 `delete_by_source` 連帶清 log）、ADR-0017 X3-F3（`docs/adr/0017-stock-desk-持倉部分更新與寫入路徑的市場幣別一致性.md` L185）。ADR-0010、ADR-0019、ADR-0022、ADR-0023 僅確認檔案存在，條文引用皆為 TA2 所述。
  - 快照：分支 `product/stock-desk`，HEAD `260ef0419b02df769aed6f331281e5d71259d65e`（本次修訂時 tech-writer 讀取 `.git/refs/heads/product/stock-desk`；初稿落檔時為 `d583ebdef1fc8bebef7a8d471f546f7d6677e3fb`，其間已合併 F-9a）。tech-architect 評估時所用 HEAD 來源未載，可能不同，此為快照。
  - 編號說明：落檔時 `docs/adr/` 最後一份為 ADR-0023，任務單暫編 ADR-0024，故使用 0024。

---

## 關聯

- 任務單：`work/dispatch/2026-10-08-任務單-F-9-日線上游幣別未核對.md`（狀態：spec；起因為風控 F7-R6）。
- **ADR-0003**（日線資料源）：本 ADR **具體化**其「對實作的約束」第 8 點（跨來源不得靜默拼接；品質檢查任一觸發須浮上 log/UI）。
- **ADR-0005**（指數來源與美股額度管理）：本 ADR **擴充**其決策三（額度計數器與美股 ticker 正規化），**不修訂**其文字；`canonical_us_symbol` 語意不變（任務單所述）。相容其 I-3。
- **ADR-0009**（accepted）：**部分修訂**其 D-3 的 `price_bars_attempt_log` 語意（另記該次提問的拒收類別與其時間，見本 ADR D-9），以及 R-8／D-8 對「最近一次提問帶 W-c 標記」序列的行為（不以快取回覆、冷卻期內回 C 版）；其餘不變。比照 ADR-0019 先例，ADR-0009 只在檔頭「修訂」清單加一行指標。本 ADR D-8（清理指令）依其 R-5 連帶刪 log。**此部分修訂須 CEO 核可。**〔TA2 R-3；F9W-4、F9W-12〕
- **ADR-0010**（proposed）：相容。cache-only 讀取同樣先過准入與幣別閘門，並**讀取**（不寫）W-c 標記；R-1／R-2 不變；新 `Valuation.missing` token（D-7）與 R-5 的 `price`／`price_not_queried` 並列、不改其語意；揭露點 5 對非 W-c／W-c′ 序列不變。〔TA2 R-4〕
- **ADR-0017**（持倉部分更新與寫入路徑的市場幣別一致性）：
  - X3-F3 觸發時須連帶重審本 ADR（見失效條件 4）。
  - **X3-F7**：方向子句前提補「已估值列的日線價格單位與市場一致」（不用「價格幣別」，F7-R5）；此前提在 Consequences 殘留 R-a～R-c 情形下不保證成立，CEO 須知悉。〔TA2 R-6；F9W-13〕
- **ADR-0019**（proposed）：相容。兩案改不同的表、各自遷移，採同一種 `PRAGMA table_info`＋`BEGIN IMMEDIATE` 重新檢查的模式（ADR-0019 K-7）；W-c 標記只用 `attempted > last_fetched_at` 比對（ADR-0019 K-3 允許的 R-8／D-8 用途），且守門置於 `_try_session_fresh_cache` 所有分支之前；實作先後皆可，後合者負責 rebase。〔TA2 R-5〕
- **ADR-0022／ADR-0023**：方向子句規則不變；被撤下的列以 `insufficient_data` 進入同一未估值集合，由 ADR-0022 Decision 5 規則選句。〔TA2 R-7；F9W-13〕
- **不取代任何既有 ADR。**
- 相關但不重用字面：X-3c（持倉幣別與市場不符的 legacy 列）為不同軸（任務單所述），本 ADR 不重用其字面；整書成因另立一組（D-7），計數優先序 X-3c 先於本組。〔TA2 R-8；F9W-11〕
- 相關正交工作：F-1／F-1b（`usable_price`／`usable_rate`），先幣別閘門、再 F-1／F-1b（任務單所述）。

---

## Context（背景）

以下皆為任務單「現況」「影響」「範圍」與 tech-architect「現況盤點要點」所述（B 類轉錄，tech-writer 未驗證 code）：

1. **起因**：風控 F7-R6。F-7 價格單位標籤雖以 F7-R1 失效關閉防護（bars 幣別與市場不符即不印），但資料層的錯誤本身未修。
2. **現況（任務單標示為「讀碼推論，未上網實證」）**：
   - 各 adapter 依市場寫死 `currency`：TWSE／TPEx／FinMind 為 `"TWD"`；Alpha Vantage 為 `"USD"`；yfinance 個股（role 1）為 `"USD"`（`apps/stock-desk/backend/app/data/providers/yfinance.py` L172），指數（role 2）取自 `INDEX_SYMBOL_METADATA`（L122-126），FX 路徑 `fetch_chart_closes` 為 placeholder（L242-265）；三者都不讀上游。〔TA1 M-2〕逐檔行號見下「現況盤點」。
   - yfinance 不讀上游回應的 `meta.currency`。
   - `app/data/quality.py::_check_currency` 在 app 內無呼叫點。
   - `us_symbols.py::canonical_us_symbol` 允許帶點代號且 Alpha Vantage 原樣轉送；帶交易所後綴的外國代號可能拿回非美元價格卻被標 USD。
   - 台股端未排除外幣計價交易單位。
3. **影響**：該類代號的價格數字本身即非市場幣別；風險上限的匯率換算（第 4 條、建議股數區間）與 `FX_APPLIED_NOTE`「價格與 ATR 以…換算」同受影響。
4. **最大傷害**：估值器 `PositionValuator._resolve_price` 直接呼叫 `service.get_daily_bars`／`get_cached_bars`（`valuation.py` L451-454），不經 `load_bars`；外幣價格會被當成 USD／TWD 灌進總資產；常見的外國掛牌（例：以便士、日圓報價）數值遠大於等值美元，使總資產虛增、全書比率偏低（**不保守**）；方向取決於該報價數值與市場幣別的比例，並非必然偏低。〔TA2 R-9；其「多半偏低」屬依常見報價單位的推論，TA2 自述未實測〕
5. **範圍補充（風控，2026-10-08）**：
   - F7-R8 (ii)：Alpha Vantage 拒絕或另查帶外國交易所字尾代號時，不得誤傷 `BRK.B`。
   - F7-R8 (iii)：例如 K 字尾雙幣 ETF（任務單註明「現況是否仍掛牌未查證」）。嚴重度高於 F-7。
   - F7-R14：`load_bars` 取得的 bar 若 currency 不等於該 market 的幣別，後端回 unavailable／insufficient，讓價格與 F-7 價格單位標籤一起不印，從根本消除「有價格、沒單位」的狀態。F-9 落地前，該狀態屬 F7-R12 (ii) 已接受殘留。

### 現況盤點（tech-architect 所述，保留原行號；行號會漂移）

- 5 個 adapter 都寫死市場幣別：TWSE `twse.py` L71/L186、TPEx `tpex.py` L92/L337、FinMind `finmind.py` L70/L179、AV `alpha_vantage.py` L145/L394、yfinance `yfinance.py` L172。因此「宣告幣別 ≠ 市場幣別」在現況**不會發生**；F7-R14 式的幣別閘門須搭配 (ii)(iii) 代號准入規則與 (i) adapter 誠實回報上游幣別才有效。
- yfinance 讀得到但未讀 `meta.currency`（`_parse_result` L335-347 只讀 timestamp／indicators）；fixture 皆合成，實際回傳待連網實證。
- `quality.check_price_bars`（含 `_check_currency`）在 app 內零呼叫者，只有 `tests/test_quality.py`。
- 快取忠實保存 currency（`cache.py` L48、L205/L225、L580/L595），但上游寫死使既有壞資料看不出異常；`market_trading_days`／`market_has_session` 不看幣別，外國代號列會汙染美股交易日行事曆。
- `MarketDataService.get_daily_bars`（`service.py` L182）、`get_cached_bars`（L244-283）、`load_bars`（`services/market.py` L147-194）皆不檢查。
- `load_bars` 消費者：`/api/bars`、`/api/signals`、`/api/advice`、alerts snapshot、portfolio limits、backtest、event study、leverage、playbook、scheduler、diagnose。
- 繞過 `load_bars` 者：即時與 cache_only 估值器（`deps.py` L163-185，進入 `valuation.py` L451-454）；指數路徑（`IndexProviderBridge` 包在 `MarketDataService` 內，`deps.py` L131-137，**仍經服務層**，因此仍受 D-1 閘門涵蓋）。〔TA1 M-3〕
- 代號：`canonical_us_symbol` 只剝 `.US`、允許 `[A-Z0-9.-]`，AV 轉換為 identity，`TSCO.LON` 原樣送出；台股無代號形狀檢查，且有合法字尾字母（`00679B`、`00631L`、`00632R`）。

---

## Options（選項比較）

任務單僅載明部分取捨；以下依 TA1 M-4 補回 tech-architect 2026-10-12 原評估的比較表（任務單轉錄時未收，核對時補交），並依 TA2 R-10 擴為「方案／優點／缺點／風險」四欄（另列結論）。來源未載的欄位寫「來源未載」，不補。

### 表 1：幣別閘門放哪一層

任務單原編號 A／B／C／D 沿用；M-4 原表另有「adapter 自行擋」「API 各端點」兩案，列為 M-4 編號。〔TA1 M-4；TA2 R-10〕

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| adapter 自行擋（M-4 A） | 最貼近來源 | 只能回報事實、快取列擋不到 | 來源未載 | **不採作為閘門**；adapter 負責誠實回報（D-6） |
| A：只放 `load_bars`（對應風控 F7-R14 字面；M-4 B） | 改動小 | 估值器不經 `load_bars`（`valuation.py` L451-454），只擋 `load_bars` 會留下最大傷害 | 外幣價格被當成 USD／TWD 灌進總資產，全書比率偏低（不保守） | **不採** |
| C：不符時濾掉不符列、回傳其餘（M-4 C「讀快取時過濾不符列」） | 不必動服務流程 | 靜默截斷序列、擋不到即時路徑 | 濾掉部分列會在序列內部造成缺口，並被當成完整序列使用；同批混入不同單位，本身就表示該批不可信 | **不採**（實作約束 C-2） |
| API 各端點（M-4 D） | 可就地顯示原因 | 分散、漏掉 scheduler、alerts | 來源未載 | **不採** |
| **B：`MarketDataService`（M-4 E）** | 唯一入口，涵蓋所有消費者含估值器、指數 | 建構參數改必填，牽動測試 | 來源未載 | **採用** |
| D：移除 `_check_currency` | 來源未載 | 來源未載 | 來源未載 | **不採**；任務單範圍原列「接上或移除」，tech-architect 建議「接上不移除」，改公開 `check_currency`，`check_price_bars` 委派 |

`_check_currency` 處置理由：`check_price_bars` 整個在 app 內零呼叫；只接幣別這一項，其餘檢查（重複列、未來日期、OHLC）的處置政策屬 F-2 範圍，不在本 ADR 內接上。〔TA1 M-4〕

### 表 2：美股代號准入規則

〔TA1 M-4 表 2；欄位依其「優點／缺點／風險」斜線分段轉錄〕

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| **A：形狀白名單** | 零成本、離線可做、保住 `BRK.B`／`BF.B`／`BRK-B`，AV 格式 2 字母以上字尾全擋 | 誤擋特別股、權證、單位；單一字母 `.L`／`.T` 擋不到 | 誤擋只損可用性；依 `yfinance.py` 檔頭 2026-08-16 記錄目前無美股持倉，F-9a 核實（盤點結果待 CEO 本機執行，見「實作進度補記」） | **採用** |
| B：已知交易所字尾黑名單 | 誤擋少 | 漏清單外字尾、需維護 | 漏網即錯價 | 不採（M-4 表未載明文理由，結論欄為 tech-writer 依 A 採用而列） |
| C：AV `SYMBOL_SEARCH` 查幣別 | 依據接近權威 | 吃 25 req/day、欄位待實證 | 離線做不了 | 不採（同上）；後續擴充，見「尚缺的事實」 |
| D：美股官方掛牌清單 | 最權威 | 新資料源需另立 ADR | 範圍大 | 不採（同上） |

### 表 3：F9W-4／F9W-12 標記怎麼存

〔TA2 方案比較；TA2 R-10〕

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **E：attempt log 加 `rejection`＋`rejection_at`（採用）** | 和冷卻判斷讀同一列；`delete_by_source`（ADR-0009 R-5）、`clear_attempt` 刪整列時標記自動一起清掉；加欄遷移有先例（`directory/store.py`、`kelly/store.py`、ADR-0019 D-3） | ADR-0009 D-3 的語意要擴充，需要在 ADR-0009 加修訂指標 | 舊版程式（或部署過程中 scheduler／API 兩個寫入程序版本不一致，ADR-0005 P-1）只更新 `last_attempt_at`，會留下屬於舊提問的標記。用 `rejection_at == last_attempt_at` 才算有效來防 |
| H：只加一欄 `last_rejection` | 少一欄 | 過期標記會讓 C 版「最近一次」這句話不屬實 | 否決 |
| F：新開 `price_bars_rejection_log` 表 | 不動既有表 | 兩張表要保持同步；`delete_by_source`、`clear_attempt`、diagnose 都要跟著改 | 兩表分歧後留下過期標記；否決 |
| G：程序內記憶 | 不用改 schema | API 與 scheduler 是兩個程序，重啟就消失；scheduler 觸發的 W-c，API 看不到 | 冷卻期內會回快取，直接違反 F9W-4；否決 |

### 表 4：整書 token

〔TA2 方案比較；TA2 R-10〕

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **I：新 token（採用）** | 語意正確；成本低 | 多一組成因句和一個標籤要送審 | 送審排程 |
| J：沿用 `price`／`price_not_queried` | 不用改 | 風控 F9W-11 不接受：沒問過來源卻顯示「查無」，語意相反 | 否決 |
| K：併入 `currency_market_mismatch` | 來源未載 | X-3c 是指持倉紀錄不一致、使用者可以更正，語意不同 | 否決 |

---

## Decision（決策）

選方案 B（`MarketDataService` 單一閘門）。以下 D-1～D-9 為 tech-architect「ADR-0024 草案要點」，設計細節取自其「設計建議」(i)～(v) 與「結論」；D-9 為 2026-10-12 依風控裁定新增。〔TA2 R-11〕

### D-1 唯一閘門在 `MarketDataService`

`get_daily_bars` 與 `get_cached_bars` 所有出口皆過。**不放 `load_bars`**（理由見 Options 表 1 與 Context 第 4 點）。閘門（預期幣別、准入函式、該市場字面）為 `MarketDataService` 的 keyword-only 必填建構參數，由組裝層注入。〔TA2 R-12〕

### D-2 整條序列 fail-closed

1. **分類與拒答**：`_try_provider` 的結果逐根以 D-5 `classify_currency` 分類：任一根宣告值非空且不等於預期幣別 → 該層為 **W-c**；否則任一根為空字串或只有空白 → 該層為 **W-c′**。兩者都把整條序列視為該層拒答：不寫快取、不 `record_fetch`、照記 `record_attempt`。以原值比對，不轉大寫（`usd` 屬 W-c，見失效條件 11）。〔TA2 R-13；F9W-3〕
   - 「照記 `record_attempt`」指沿用既有時點（`service.py` L184 成功、L241 全層拒答），不新增記錄點。幣別檢查必須放在 `_try_provider` 內、早於 L182 的 `cache.put`。〔TA1 M-7〕與 D-9 並存：記錄點不新增，L241 帶入標記參數。〔TA1 M-7 註記〕
2. **W-c 不得與價格並存**：同一次梯子任一 live 層為 W-c，該次回覆不以快取回價格——降級時不讀快取，直接回 `UNAVAILABLE`、`bars=[]`，reason 依 `_combine_reasons` 合併；W-c 層之後若有層成功且原本要做增量合併，改向該層要整段、不讀回快取頭段。經 `MarketDataService` 涵蓋 `load_bars` 全部消費者與 live 估值器。〔TA2 R-13；F9W-4〕
3. **標記延續**：有效 W-c 標記（D-9）存在時，任何讀取路徑都不以快取回該序列價格——冷卻期內回 C 版（若採用 T-14 則回分市場版，見 D-9）；冷卻期外 layer 0 不服務快取、改走梯子；cache-only 回 `UNAVAILABLE`。〔TA2 R-13；F9W-4、F9W-12、F9W-21〕
4. **W-c′ 不套用 (2)(3)**。〔TA2 R-13〕
5. **快取閘門**：讀出的列任一根宣告值不符或空白，整條序列 fail-closed、不刪資料、`rejection=cache_unit_rejected`。〔TA3 R-39〕
   - (a) **layer 0**：在讀出整段快取後、所有分支之前檢查一次（不放在 `_cached_result` 裡；此修正 TA1 M-8 的建議），得出「可採用的快取」（快取存在且通過快取閘門）。〔TA3 R-39、R-45〕再依下列順序判定，先命中者為準〔F9W-23、F9W-24；TA4 R-47、R-53〕：
     1. 有效 W-c 標記、冷卻期內：不論快取有無、是否被擋，回 C 版（採用 T-14 時回該市場句，見 D-9），`bars=[]`、`rejection=unit_mismatch`，reason 不含 T-15。
     2. 有效 W-c 標記、冷卻期外：回 None 走梯子、不服務快取；快取被擋時，本次停用增量。
     3. 有效 W-c′ 標記、冷卻期內、本機無可採用的快取（無快取，或快取被快取閘門擋下）：回 C′（T-13），`bars=[]`、`rejection=unit_missing`；reason 完全等於 C′，不含 T-15，不打來源。冷卻期內「C′。 T-15。」等任何其他未經審查的合併組合不得出現。〔F9W-23、F9W-30；TA4 R-47 擇定 C′〕
     4. 快取被擋，且不屬於 1～3：若符合 ADR-0009 R-8 冷卻條件（最後一次提問晚於最後一次完整成功、且在冷卻期內），回 `UNAVAILABLE`，reason 完全等於 T-15，`rejection=cache_unit_rejected`，不打來源（冷卻資訊不寫進 reason）；否則回 None 走梯子，本次停用增量（`fetch_start = start`；`_incremental_start` 本身不改，ADR-0019 K-10 相容）。〔TA3 R-39、題 2；TA4 R-47〕
     5. 其餘（快取通過閘門，或無快取且不屬於 3）：照現行 layer 0 分支行為（ADR-0009 R-8／D-8）。**快取閘門檢查必須在 R-8 分支之前**，以測試釘住。有效 W-c′ 標記不改變任何分支；落在以 `RECENT_ATTEMPT_FAILED_REASON` 回快取的分支時即 T-17（風控核可，F9W-24）。回覆 `rejection=None`，該列照 D-7 的 F9W-18 條件正常估值。〔TA4 R-47〕
   - (b) `_fall_back_to_cache`：回 `UNAVAILABLE`，reason 依 `_combine_reasons` 合併各層原因並加上 T-15。〔TA3 R-39〕
   - (c) `get_cached_bars` 依序：准入 → 有效 W-c 標記（不論冷卻）回 `UNAVAILABLE`、reason 為 None、`rejection=unit_mismatch`〔TA2「一」〕→ 快取閘門被擋回 `UNAVAILABLE`、reason 為 T-15、`rejection=cache_unit_rejected`。W-c′ 標記不適用。〔TA3 R-39；TA4 R-54〕
   - (d) 增量合併讀回被擋：reason 加 T-15，不用 `MERGE_READBACK_FAILED_REASON`；之後各層整段請求；`_fall_back_to_cache` 不再讀快取；T-15 至多出現一次。照 (a) 的設計，此路徑只剩另一個程序在兩次讀取之間寫入壞列的競態時才會觸發。〔TA3 R-39、題 3〕
   - `cache_unit_rejected` 由快取閘門設定，**永不寫入 attempt log**；D-9 標記只由 live 層寫入。〔TA3 R-38〕
6. 放寬 (2)(3) 須 CEO 明確同意並附 tech-architect 實證。〔TA2 R-13；F9W-4〕

### D-3 不符 bars 不寫快取

（細節同 D-2 與實作約束 C-3：不符時 `cache.get` 仍為 None、不 `record_fetch`、照記 `record_attempt`。）

### D-4 admission 在 layer 0 前、按市場注入

admission 由服務層注入、在 layer 0 之前執行。被拒代號：不讀快取、不呼叫來源、不扣額度、不寫 attempt log。AV adapter 在扣額度前再呼叫一次 admission（縱深）。

- 准入在 `get_daily_bars` 與 `get_cached_bars` 兩個入口、任何快取讀取之前執行；被拒時回 `UNAVAILABLE`、`bars=[]`，reason 為 W-a 或 W-b 全文，`rejection=symbol_not_admitted`。W-a／W-b 只能由服務層准入發出；AV adapter 扣額度前的縱深檢查被拒時，**不得**產出 W-a／W-b（正常路徑不可達，若需使用者面字面須用既有核可句或另送審）。〔TA2 R-14；F9W-7〕
- **指數服務**顯式「不檢查形狀、只檢查幣別」，但 **W-a、W-b、W-c、W-c′、C、C′ 皆不適用指數路徑**（`services/index.py` 兩處會接指數版 `NO_BARS_REASON` 並加前綴）：指數閘門不帶任何使用者面字面、不寫 W-c 標記；yfinance role 2 誠實回報前，指數幣別檢查不可觸發，以測試釘住；role 2 合併的前提是指數用字面（T-16）另經 creative-lead 起草、風控逐字審。〔TA2 R-15；F9W-9〕
  - **指數路徑**〔TA4 R-49〕：指數服務的閘門設定為「只檢查幣別、不檢查形狀、不帶任何使用者面字面、不讀也不寫 D-9 標記」，因此 W-a、W-b、W-c、W-c′、C、C′、T-14、T-15 皆不適用指數路徑。
  - 指數服務的快取閘門照常 fail-closed（D-1 所有出口皆過）。被擋時回 `UNAVAILABLE`、`bars=[]`、`rejection=cache_unit_rejected`，reason 只含各 live 層的既有原因（可為 None），不加任何字面；layer 0 冷卻期內被擋時 reason 為 None。〔TA4 R-49〕
  - 以測試釘住 `INDEX_SYMBOL_METADATA` 每一列的幣別都等於 `MARKET_CURRENCY[market]`，故正式設定下指數快取閘門不可觸發；只有手動改庫或 `MARKET_CURRENCY` 變動（失效條件 4）會觸發，一觸發即適用失效條件 13（T-16 須先核可）。〔TA4 R-49；「正式設定下不可達」為 TA4 依 `INDEX_SYMBOL_METADATA` 與 `MARKET_CURRENCY` 一致所推得，屬推論、尚未實證，須以上述測試釘住〕
  - **已裁示：附條件接受列為殘留（風控 F9W-31、F9W-32）**：上述非正式設定的觸發情境下，TA4 所述 `index.py` L265／L385 會接既有的指數版 `NO_BARS_REASON`「（來源與快取皆無）」；快取其實有列、只是被拒，「快取皆無」並不精確。風控判斷不精確的在原因、不在結論（「沒有可用的日線資料」屬實），被擋的快取列不上畫面；正式設定下不可達，接受列為殘留。〔TA4 R-49；F9W-31、F9W-32〕條件如下：
    - (a) 「`INDEX_SYMBOL_METADATA` 每一列的幣別等於 `MARKET_CURRENCY[market]`」測試是本殘留成立的前提，同時作為失效條件 4 的絆線：日後改 `MARKET_CURRENCY` 使測試轉紅，必須連同本殘留回風控，不得只改測試期望值。〔F9W-31 (a)，F-9b 合併前〕
    - (b) 指數快取閘門被擋時，必須留下操作端看得到的記錄（可沿用 F-9a 的 `CURRENCY_DIFFERS_LOG_PREFIX` WARNING，或由 tech-architect 指定同等方式；採哪一種**待 tech-architect 指定**），以測試釘住。〔F9W-31 (b)，F-9b 合併前〕
    - (c) 觸發情境下，指數回覆一律 `bars=[]`，不改用代理 ETF 或其他指數，不顯示任何價格或 beta；reason 不含 T-15，也不含任何股票路徑字面。〔F9W-31 (c)〕
    - (d) T-16 起草範圍須明列「指數快取被閘門拒收」情境；T-16 核可後，此情境不得再接「（來源與快取皆無）」。〔F9W-32 (b)〕
    - (e) 本殘留只適用指數路徑，**不得作為股票路徑的先例**；股票路徑快取被擋一律用 T-15，並依 W-d 不接 `NO_BARS_REASON`（F9W-22）。〔F9W-32 (c)〕
    - (f) CEO 在 T-10 核可時一併知悉本殘留。〔F9W-32 (d)〕
- 〔核對補充，非任務單原文〕admission 以 `canonical_us_symbol` 正規化後的形式判斷，但不改寫傳給下游的 symbol。admission 與幣別規則都是必填建構參數；指數服務顯式傳入「只檢查幣別、不檢查形狀」，不得以預設值省略。market 查不到預期幣別時 fail-closed（回 `UNAVAILABLE`）。〔TA1 M-5〕

代號准入規則：

- **美股（設計建議 ii）**：採**形狀白名單**——root 1–5 字母，可選單一字母類別（`.X`／`-X`）。保住 `BRK.B`／`BF.B`／`BRK-B`；擋 2 字母以上字尾。
- **台股（設計建議 iii）**：以精確樣式擋「數字＋K」；**不得**擋 `B`／`L`／`R`／`U` 字尾。測試 `00679B`、`00631L`、`00632R`、`00635U`、`0050`、`2330` 須通過。`verified=False`，待連網實證。樣式須與 W-b「數字後接英文字母 K」逐字對應並以測試釘住；F-9d 實證若不符，規則與 W-b 回風控重審。〔TA2 R-16；F9W-8〕

### D-5 判準單一來源 `MARKET_CURRENCY`，由組裝層注入且為必填建構參數

預期幣別由組裝層（`deps.py`）從 `app.positions.models.MARKET_CURRENCY` 注入；`app/data` 不 import `app/positions`、不新增字典常值，KX-A1 續綠。`_check_currency` 接上不移除：改公開 `check_currency`，`check_price_bars` 委派；加與 `currency_matches_market` 的等價測試。

- W-c／W-c′ 分流的唯一來源為 `classify_currency(bars, expected) -> ok｜mismatch｜missing`；`check_currency` 的「不符」等於 mismatch ∪ missing，以等價測試釘住。〔TA2 R-17；F9W-3〕
- 〔核對補充〕注入的是 market → 預期幣別的查表函式（由 `MARKET_CURRENCY` 提供），每次呼叫依該次的 `market` 參數查，不得在建構時固定成單一幣別。理由：指數服務是 TW、US 共用的同一個實例（`deps.py` L131-137，market 只是快取鍵的一個維度）。〔TA1 M-6〕

### D-6 adapter 回報上游宣告的幣別；尚未讀取上游宣告的 adapter 以市場幣別為假設值；缺值不補

（標題原為「只回報上游宣告幣別或經 admission 保證之值，缺值不補」，風控認定「經 admission 保證之值」說過頭而更正。）〔TA2 R-18；F9W-14〕

- **yfinance role 1**（F-9c）：改用 `meta.currency` 原值照存（不轉大寫）；缺值時以空字串原樣放入 `PriceBar.currency`、不補市場預設，由服務層閘門判定 W-c′；adapter **不**自行回 `UNAVAILABLE`、不產出使用者面原因句（單一閘門，D-1）。〔TA2 R-19；修訂初稿 D-6 原寫的「缺值時 role 1 回 UNAVAILABLE」〕
- **yfinance role 2（指數）**：本階段排除，不讀 `meta.currency`；等連網實證且指數用字面（T-16）核可才合併。〔TA2「五」F-9c 列、硬性前提 5；初稿 D-6 原寫「role 1／2 改用」，以 TA2「五」為準〕TA4 同意以 TA2「五」的 role 2 排除為準：R-20 把 role 2 列為寫死的假設值，R-15 要求 role 2 誠實回報前指數幣別檢查不可觸發，「五」的硬性前提 5 亦同。〔TA4 R-52〕
- `fetch_chart_closes`（FX 路徑）排除，並以測試釘住（屬 F-9c）。
- TWSE／TPEx／FinMind／Alpha Vantage 與 yfinance role 2 寫入的 `currency` 是依市場寫死的**假設值**，**不是**上游宣告，也**不受**准入保證：准入只排除特定代號形狀、降低外國掛牌混入的機會，無法確認任一回傳的價格單位（單一字母外國字尾仍可通過）。role 1 改讀 `meta.currency` 屬 F-9c，**須在 F-9b 與 F-9b2 皆合併之後**；F-9c 重錄真實 fixture 須確認 USD／TWD 實際寫法，發現變體回風控。〔TA2 R-20；F9W-3、F9W-14〕

### D-7 不新增 DataStatus 與 API 狀態值；新增一個估值缺漏 token 與整書成因組

〔標題：TA2 R-21；F9W-11〕

1. 資料層回 `UNAVAILABLE`、bars 清空，API 外層照既有路徑回 `insufficient_data`。
2. `ProviderResult` 新增**內部**欄位 `rejection`（`symbol_not_admitted`｜`unit_mismatch`｜`unit_missing`｜`cache_unit_rejected`｜None）。同一次回覆有多種時取 `unit_mismatch` ＞ `unit_missing` ＞ `cache_unit_rejected`；`symbol_not_admitted` 與其他值不會同時出現；`cache_unit_rejected` 由快取閘門設定，永不寫入 attempt log。它只供 `load_bars` 的 W-d 分流與估值器使用，**不得**序列化進 `LoadedBars.meta()` 或任何 API 回應。**不變式**：`rejection` 不為 None ⇔ 該回覆為 `UNAVAILABLE` 且 `bars=[]`，以 `ProviderResult` 的 model validator 強制，違反即 raise。任何帶 bars 的回覆一律 `rejection=None`，包括：W-c′ 加上通過閘門的快取而回快取、T-17、合併讀回被擋後由其他層整段成功、W-c 層之後有層整段成功。各層的拒收類別只用於 D-9 標記的寫入判斷，不帶到帶 bars 的回覆上。〔TA2 R-22；TA3 R-38、題 1；TA4 R-48〕
   - 為何新增 `cache_unit_rejected` 而非沿用 `unit_mismatch`／`unit_missing`：後兩者會觸發「本次不讀快取」與 D-9 標記，這兩件事都不該由快取拒收觸發。〔TA3 題 1 方案比較〕
3. `Valuation.missing` 新增一個 token（名稱由實作定，不面向使用者），涵蓋准入拒絕、W-c、W-c′（含 C／C′ 冷卻回覆）、快取舊列幣別不符或空白（T-15），live 與 cache_only 相同，取代 `price`／`price_not_queried`、不並存。〔TA2 R-22；TA3 R-38〕
   - **新 token 只給「該次回覆為 `UNAVAILABLE`、`bars=[]`」的列**〔F9W-18，F-9b 合併前〕。有 bars 的回覆，`rejection` 不得讓估值器產生新 token；這包括兩種情形：W-c′ 加上通過閘門的快取而回快取；合併讀回被擋之後由其他層整段成功。這兩種情境測試須釘住：該列正常估值，不進 T-11 組，也不顯示 T-12。
   - 新 token 與 `price`、`price_not_queried` **互斥**；`missing` 只有這一個 token，因此庫存頁不會串接「、查無匯率」這類未審過的組合；若要改成可並存，回風控。〔F9W-18〕因此 TA2 原「建議該列不查匯率」在風控裁定下升為條件：拿到新 token 後不再查匯率，`fx`／`fx_open` 為 None，並同步更新 `Valuation.fx_open` docstring 列出的「None only where nothing was asked」清單。〔TA2 R-22 與 TA2 影響面表；F9W-18〕TA4 同意此升級：F9W-18 要求 `missing` 只有一個 token，若查了匯率又不記 fx token 則結果毫無用處，還會多打 FX 來源；不查是唯一乾淨的做法，也和 X-3c 先例一致。〔TA4 R-52〕
4. **整書成因另立一組**，不計入 `asked`；計數優先序 X-3c ＞ 本組 ＞ `price_not_queried` ＞ `asked`，各組互斥；陳述順序 **W4 → W5 → (b) → 本組**，固定並以測試釘住（T-18，風控已核可；X-3c 第二段裁定只要求「順序固定並有測試」，本組排在 (b) 之後不違反既有核可）。〔TA2 R-22；F9W-25〕此處 W4、W5、(b) 沿用來源代號，tech-writer 未讀 `book.py` 對照其具體所指。
5. 方向子句、`UnvaluedComposition`、`SYMBOL_UNVALUED_NOTE` 不改：它們只看 `status != "ok"`；`SYMBOL_UNVALUED_NOTE` 不講成因，對被拒列也屬實。〔TA2 影響面表〕
6. **字面狀態**：整書成因句（T-11）、庫存頁標籤（T-12）、T-15 已由風控第二批核可主案（本檔不收錄字面，核可全文見 F9W-17～F9W-29 裁定檔）。T-11 採主案、**撤回 F9W-11 (e)**；live 與 cache_only 用同一句；句內不得加入任何「非…中斷」「並非只是…」類否定句；成因常數不得重用 `CURRENCY_MARKET_MISMATCH_CAUSE`；`UNVALUED_NOTE_TEMPLATE` 不改。〔F9W-17〕理由：一組成因句必須對組內每一列都成立，組內含混合情境（例：AV 額度用完加上 yfinance 單位被拒）時 (e) 對該列不成立。〔第二批結論；TA3〕風控「暫時沿用」例外：tech-architect 評估新 token 可隨 F-9b 落地，例外條件一不成立。〔TA2 R-22〕
7. **W-d**：W-a、W-b、W-c、W-c′、C、C′、T-15 即完整 reason；`rejection` 不為 None 時，`load_bars` 不接 `NO_BARS_REASON`、不走 `with_provider_reason`、不加 `PROVIDER_REASON_PREFIX`；W-c 與其他層原因並列時走 `_combine_reasons`（合併分隔依 `_REASON_SEPARATOR`）。T-15 併入此整組，並同樣不用 `MERGE_READBACK_FAILED_REASON`，同一 reason 內至多出現一次（C-30）。〔TA2 R-22；TA3 R-41、題 4；F9W-6、F9W-22〕
   - `load_bars` 三分流：(i) 有 bars → 走既有成功路徑，`reason` 原樣傳出，不接 `NO_BARS_REASON`、不加前綴；(ii) 無 bars 且 `rejection` 不為 None → W-d，reason 原樣傳出；(iii) 無 bars 且 `rejection` 為 None → 既有 `NO_BARS_REASON`＋`with_provider_reason`。〔TA4 R-48〕
   - 估值器：`rejection` 不為 None → 新 token（不變式保證 `bars=[]`），不查匯率；否則照既有規則。估值器不得自行用「bars 是否為空」另做第二套判斷。〔TA4 R-48〕
   - 合併讀回被擋後由其他層整段成功時，回傳的 bars 全是該層新抓的列（整段請求，不讀回快取），reason 照既有成功路徑只帶 `mixed_sources_reason`，不含 T-15。〔TA4 R-48〕
   - **已裁示：可接受（風控 F9W-33、F9W-34）**：W-c′ 層加上通過閘門的快取，經 `_fall_back_to_cache` 回快取時（情境 (c)，見 C-34 (b)），K 線區的 reason 是「AV 原因句。 W-c′。」這類合併句，配上快取價格與 F-7 單位標籤。TA4 稱此為既有合併機制、不是新字面；風控先前只審了估值面（F9W-18），本次確認 W-c′ 句可與快取價格、F-7「價格單位：美元」並存（風控判斷：W-c′ 句講的是該來源這次回傳的日線，單位標籤講的是畫面上的快取列，兩者描述不同資料；快取狀態標示使讀者可讀出「來源回應不採用、故顯示快取」）。條件見 C-34 (b)～(e)、F-9b 驗收欄（F9W-34）。依 F9W-10，各消費端若把 `loaded.reason` 包進框架句，特別是會讓人以為畫面價格就是「這次回傳」的句型，都要回風控；**不得自行在 W-c′ 句旁補「已改以快取」「單位為美元」這類橋接句**，要加須另送審。〔TA4 R-48 情境 (c)；F9W-33 (d)〕
8. 既有 token 不變。`load_bars` 此情境**不得**接 `NO_BARS_REASON`（不實）。**不得**重用 `CURRENCY_MARKET_MISMATCH_NOTE`／`_CAUSE`（指持倉紀錄，不實）。
9. 字面代號：W-a（美股外國字尾被拒）、W-b（台股外幣交易單位被拒）、W-c（來源宣告幣別與市場不符）、W-c′（來源未標示幣別）、W-d（`load_bars` 基底句，或只帶 provider reason；已核可「不另立基底句、不加前綴」）、C／C′（冷卻期版）、T-11～T-15。本檔**不收錄**字面。
10. 本檔及日後字面、PR 說明不採兩種過滿說法：「不是暫時抓不到」（對混合情境不成立）、「AV 恢復就能估值」（恢復後用的是 AV 寫死 USD 的價格，屬殘留 R-a，不代表估值正確）。〔F9W-28，紀錄更正〕

### D-8 既有壞列不自動遷移

由運維指令清理：預設 dry-run，`--apply` 才刪；依 ADR-0009 R-5 連帶刪 fetch_log／attempt_log（F-9e）。（suggested）清理指令可另列帶有效 W-c 標記的序列，只列不刪，供 CEO 判斷。〔TA2 R-23〕行事曆汙染一併由 F-9e 處置，dry-run 輸出須包含「清除後各市場減少的行事曆日數」，見 Consequences 壞處 6。〔TA1 M-13〕

### D-9 attempt log 記錄拒收類別（2026-10-12 新增）

〔TA2 R-24；F9W-4、F9W-12〕

- **欄位**：`price_bars_attempt_log` 新增 `rejection TEXT`（`unit_mismatch`／`unit_missing`／NULL）與 `rejection_at TEXT`。
- **有效條件**：`rejection_at == last_attempt_at`，且 `last_attempt_at` 晚於 fetch log 的 `last_fetched_at`（或沒有 fetch log）。
- **設定**：該次梯子至少一層 W-c 或 W-c′、且沒有任何一層取得可用資料時寫入，有 W-c 就記 `unit_mismatch`；其他提問一律寫 NULL（成功路徑與一般失敗路徑都清成 NULL）。`cache_unit_rejected` 永不寫入（D-2 (5)）。
- **遷移**：缺欄時在 `BEGIN IMMEDIATE` 內重新檢查後 `ADD COLUMN`，不回填；重複初始化與同檔雙實例不得報錯。
- **讀寫分工**：只有 `get_daily_bars` 寫入；layer 0 與 `get_cached_bars` 只讀（ADR-0010 R-2）。cache-only 路徑套用 W-c 標記比風控裁定字面更嚴、方向保守，風控已知悉並同意；放寬須 CEO 同意。〔TA2「一」；F9W-26〕
- `delete_by_source`、`clear_attempt` 刪整列，不另處理。讀到未知值：記 ERROR、視同無標記。
- **冷卻字面**：
  - 有效 W-c 標記 → C 版（風控核可）；`{minutes}` 取 `rejection_at`。T-14（C 版分市場兩句）為選用：**採用即兩市場全面使用，不得與 C 版混用**，以完全相等測試釘住；`market` 必須與該標記所屬序列的 `(symbol, market)` 相同；C′ 不隨 T-14 分市場。〔F9W-21〕
  - 有效 W-c′ 標記、冷卻期內、本機無可採用的快取（無快取或快取被擋）→ C′ 版（風控核可，F-9b2 合併前提；F9W-20；適用範圍原為「本機無快取」，依 F9W-23 與 TA4 R-47 正式擴為「本機無可採用的快取（無快取，或快取被快取閘門擋下）」；只用於 W-c′ 標記有效、在冷卻期內、沒有 W-c、沒有任何一層取得可用資料、本機無可採用的快取）。C′ 常數的出處註記須同時引用 F9W-20、F9W-23、F9W-30。〔F9W-20、F9W-23、F9W-30；TA4 R-47〕
  - 有效 W-c′ 標記、冷卻期內、快取存在且通過快取閘門 → 照 ADR-0009 R-8 回快取，沿用 `RECENT_ATTEMPT_FAILED_REASON`（T-17，風控核可；閘門檢查在 R-8 分支之前，該列照 F9W-18 正常估值）。這句屬實：該次梯子沒有任何一層取得可用資料；W-c′ 只是「無法確認」，不是單位不符的證據。此時快取列的單位標示可能只是寫死的假設值，屬殘留 R-b，已交 CEO 知悉。〔F9W-24〕
  - 有效 W-c′ 標記、冷卻期內、快取被擋 → 見 D-2 (5)(a) 第 3 項：已擇定回 C′（不回 T-15），以完全相等測試釘住；擇定屬 F9W-23 授權範圍，風控已知悉、無異議。〔F9W-23、F9W-30；TA4 R-47〕
  - 有效 W-c 標記 → 不論有沒有快取、快取是否被擋，一律回 C 版或 T-14。〔F9W-23〕

### 實作約束（F-9b 為主；tech-architect C-1～C-10 原文轉錄，C-11～C-33 為 2026-10-12 增列；C-34 為 TA4 R-48 增列）

| 編號 | 約束 |
|---|---|
| C-1 | 即時層（`_try_provider` 結果）＋**四條快取讀出路徑、六個出口**（layer 0 三個出口〔`_try_session_fresh_cache`，含 R-8 冷卻期回快取〕、`_fall_back_to_cache`、`get_cached_bars`、增量抓取的合併讀回〔`service.py` L191 的 `merged.bars`〕）非空結果逐根等於預期幣別，否則 `UNAVAILABLE`、`bars=[]`；各至少一個測試。實作：layer 0 在讀出整段快取後檢查一次（D-2 (5)(a)），`_fall_back_to_cache`、`get_cached_bars`、合併讀回各檢查一次。〔原文「五條讀取路徑＋即時路徑…（各一測試）」；TA1 M-8；TA3 R-45 修正 M-8〕 |
| C-2 | 不得濾掉不符列回傳其餘 |
| C-3 | 不符時 `cache.get` 仍 None、不 `record_fetch`、照記 `record_attempt` |
| C-4 | 被拒代號 transport 零呼叫、額度 `used` 不變、不寫 attempt log、不讀快取 |
| C-5 | `app/data` 不 import `app/positions`，KX-A1 續綠，與 `currency_matches_market` 等價測試 |
| C-6 | `deps.py` 三個建構點（TW、US、index）規則由測試釘住。釘住測試建議放在 `tests/test_api_deps.py`（已引用 `deps._default_resolver`／`_default_index_resolver`）。〔TA1 M-9〕 F-9a 的 `expected_currency: str \| None`（指數傳 None；TA4 所述見 `deps.py` L144-149）在 F-9b 改為 keyword-only 必填的 market→幣別查表函式（D-5、M-6）。三個建構點各自顯式傳入准入規則（指數：只檢查幣別、不檢查形狀）和字面組（指數：無）。不得保留 None 預設值。〔TA4 R-56，給 F-9b 實作〕 |
| C-7 | `BRK.B`、`BF.B`、`BRK-B`、`AAPL`、`00679B`、`00631L`、`00632R`、`00635U` 通過 admission |
| C-8 | `price_guard.py` 零 diff；F-7 前端閘門與測試不改且常綠 |
| C-9 | 新字面逐字常數並標風控核可出處 |
| C-10 | `fetch_chart_closes` 行為不變 |
| C-11 | fake primary 回 W-c、快取裡有幣別正確的舊列時 → 回 `UNAVAILABLE`、`bars=[]`，不回傳任何快取列；live 估值器在同一情境得到新 token。 |
| C-12 | F-9b 合併時 W-c 不可觸發。deps 建構的每個正式 adapter 用既有 fixture 斷言 `currency == MARKET_CURRENCY[market]`；F-9c 前，yfinance `_parse_result` 不讀 `meta.currency`。 |
| C-13 | `LoadedBars.reason` 以完全相等釘住**十種**情境：(1) W-a 單獨、(2) W-b 單獨、(3) W-c 單獨、(4) W-c＋AV 原因句、(5) W-c′、(6) C 版（採用 T-14 時為美／台兩句，各一測）；(7) 冷卻期內 layer 0 被擋：reason 等於 T-15，provider 呼叫次數為 0；(8) 不在冷卻期、梯子全部失敗、快取被擋：reason 等於「AV 原因句。 yfinance 原因句。 T-15。」，第一個 rung 收到的請求起點等於 `start`；(9) live 層 W-c′ 加上快取被擋：reason 等於「W-c′。 T-15。」；(10) W-c 加上壞快取：reason 不含 T-15，快取沒有被讀取。〔原文六種；TA3 R-42、題 4；TA4 R-50〕 (9) 是 live 梯子路徑：某 live 層為 W-c′、其餘層都拒答、`_fall_back_to_cache` 快取被擋（D-2 (5)(b)），reason 依 `_combine_reasons` 為各層原因＋T-15，`rejection=unit_missing`，D-9 寫入 `unit_missing`。測試用單一 rung 梯子，使字串恰為「W-c′。 T-15。」。這和 F9W-23 禁止的冷卻期「C′。 T-15。」不同：C′ 是冷卻期內的整句回覆（D-2 (5)(a) 第 3 項），不與任何句合併。(9) 在 TA3 題 4 已列出，風控 F9W-22 要求 (7)～(10) 用完全相等斷言，屬已審範圍。〔TA4 R-50〕 |
| C-14 | `{provider}` 只取 `source_id`；provider 沒有 `source_id` 時，不得產生 W-c／W-c′（測試）。 |
| C-15 | AV 縱深檢查的程式路徑不出現 W-a／W-b 常數（grep 加測試）。 |
| C-16 | 台股准入 regex 與「數字後接英文字母 K」逐字對應；正、反例各至少 4 個，C-7 清單照舊。 |
| C-17 | 指數服務不寫標記、不帶 W-c 字面；`services/index.py` 與指數服務的建構點不引用 W-a、W-b、W-c、W-c′、C、C′、T-14、T-15 常數（grep）。預置任何 D-9 標記不改變指數回覆（測試）。以假快取壞列觸發指數快取閘門 → `bars=[]`、reason 不含 T-15（測試）。`INDEX_SYMBOL_METADATA` 幣別一致（測試）；此測試是指數殘留成立的前提，同時作為失效條件 4 的絆線：日後改 `MARKET_CURRENCY` 使其轉紅，必須連同本殘留回風控，不得只改測試期望值（F9W-31 (a)）。指數快取閘門被擋須留下操作端看得到的記錄並以測試釘住（F9W-31 (b)）；觸發時指數回覆一律 `bars=[]`，不改用代理 ETF 或其他指數，不顯示價格或 beta（F9W-31 (c)）。role 2 的 live 幣別檢查不可觸發（測試）。〔TA4 R-49；F9W-31〕指數路徑非正式設定觸發時沿用既有指數版 `NO_BARS_REASON` 一事，風控已附條件接受列為殘留，見 D-4（F9W-31、F9W-32）。 |
| C-18 | `LoadedBars.meta()` 鍵集合不變；任何 API schema 都不出現 `rejection`。 |
| C-19 | 新 token：live 下准入、W-c、W-c′、快取被擋（T-15）各一測；cache_only 下准入、快取被擋各一測（W-c 標記屬 F-9b2，見 C-25）。cache_only 不打來源、W-c′ 標記也不適用 cache-only，不會產生 W-c′，不設此測試。每測斷言 `missing == [新 token]`，不含 `price`、`price_not_queried`、`fx_now`、`fx_open`；`fx`／`fx_open` 為 None；匯率 provider 零呼叫（F9W-18 條件，不是建議）。帶 bars 的情境見 C-34。〔F9W-18；TA4 R-52，含 TA4 對 TA2 原組合數的自我更正〕 |
| C-20 | 計數優先序與互斥（方向子句測試 6）；新組不計入 `asked`；陳述順序（W4 → W5 → (b) → 本組）釘住。〔F9W-25〕 |
| C-21 | 方向子句測試 1～5（見「風險與相依」）。 |
| C-22 | `MISSING_LABELS` 的鍵集合測試更新；新標籤不以「查無」或「本次未查」開頭；禁詞掃描通過。 |
| C-23（F-9b2） | 遷移測試：舊 schema 加欄後兩欄為 NULL；第二次初始化不改變任何值；同檔兩個實例不報 duplicate column。 |
| C-24（F-9b2） | `rejection_at != last_attempt_at` 時視同無標記；只更新 `last_attempt_at` 的舊式寫入不會留下有效標記。 |
| C-25（F-9b2） | 冷卻期內的有效 W-c 標記：無快取，以及有快取的三種分支（無 coverage、REFETCH、一般服務）→ 皆回 C 版、`bars=[]`，不出現 `RECENT_ATTEMPT_FAILED_REASON`；冷卻期外 → provider 被呼叫；cache-only → `UNAVAILABLE`，並帶新 token。〔F9W-23 追加：有效 W-c 標記加上快取被擋時，同樣回 C 版（或採用 T-14 時的分市場句），reason 不含 T-15；T-14 若採用，以完全相等測試釘住且兩市場全面使用，不與 C 版混用（F9W-21）〕 |
| C-26（F-9b2） | W-c′ 標記：無快取或快取被擋 → reason 完全等於 C′、`bars=[]`、provider 呼叫 0 次、`rejection=unit_missing`，不含 T-15；快取通過閘門 → 照現行 R-8 行為（閘門檢查在 R-8 分支之前，測試釘住），該列正常估值。兩個子情境（無快取、快取被擋）各一測，都用完全相等斷言：reason 等於 C′，不含 T-15，不含 `RECENT_ATTEMPT_FAILED_REASON`，provider 呼叫 0 次，`bars=[]`，`rejection=unit_missing`（F9W-30 (b)(e)）。該列依 F9W-18 進 T-11 組並顯示 T-12（F9W-30 (c)）。五步先後（D-2 (5)(a)）以測試釘住，至少包括：第 1 步（W-c）先於第 3 步（W-c′）；快取通過閘門時落在第 5 步、不回 C′（F9W-30 (d)）。「C′。 T-15。」禁止組合照舊有效（F9W-23）。〔F9W-23、F9W-24、F9W-30；TA4 R-47〕 |
| C-27（F-9b2） | 成功提問與一般失敗提問都把標記寫成 NULL；W-c 與 W-c′ 同時出現時記 `unit_mismatch`。 |
| C-28 | PR 說明附上 W-a 在每個消費端最終顯示的字串表（F9W-10）。 |
| C-29 | 每個常數依 C-9 註明風控核可出處並引用本次裁定；PR 說明引用本裁定與 F7-R10（F9W-16）。〔F9W-29 追加：第二批常數引用 F9W-17～F9W-29；改任何字、改分流或先後順序，都回風控重審；C、C′、T-14 沿用 `{minutes}`，「約 0 分鐘前」與四位數分鐘的讀感問題仍在列管〕 |
| C-30 | 合併讀回被擋時 T-15 只出現一次，且不出現 `MERGE_READBACK_FAILED_REASON`。〔TA3 R-43〕 |
| C-31 | `cache_unit_rejected` 永不寫入 attempt log（測試快取被擋後 `rejection` 欄為 NULL）。〔TA3 R-43〕 |
| C-32 | layer 0 被擋：冷卻期內 provider 呼叫 0 次；冷卻期外 provider 被呼叫，請求起點等於 `start`；來源成功後，同一請求下一次由 layer 0 服務。〔TA3 R-43〕 |
| C-33 | W-c 加上壞快取時，reason 不含 T-15，且快取沒有被讀取。〔TA3 R-43〕 |
| C-34 | (a) 違反 D-7 (2) 不變式時 `ProviderResult` 建構即 raise；(b) W-c′＋通過閘門的快取（`_fall_back_to_cache`）：`rejection` 為 None、`LoadedBars.reason` 等於服務層 reason（完全相等）、估值正常。風控已裁示可接受（K 線區的合併 reason 配快取價格與 F-7 單位標籤，見 D-7 (7)；F9W-33），並加條件：完全相等要釘到字串層級，`LoadedBars.reason == _combine_reasons([各層原因..., W-c′ 句])`，單層與兩層梯子各一測，W-c′ 句不得被截斷、改寫或改變順序，不接 `NO_BARS_REASON`、不加「來源回報：」前綴（F9W-33 (a)）；此路徑的 status 必須是 `cached_stale`（使「快取資料」標示與 reason 同時出現），以測試斷言（F9W-33 (b)）；不得自補「已改以快取」「單位為美元」這類橋接句（F9W-33 (d)）；(c) 合併讀回被擋後他層整段成功：`rejection` 為 None、reason 不含 T-15、估值正常；(d) T-17 回快取：`rejection` 為 None、估值正常。(b)～(d) 都斷言該列不進 T-11 組、不顯示 T-12。(e) 負面測試（重申 F9W-4）：任一 live 層是 W-c、且快取通過閘門時，**不得**回快取，使 W-c′ 的放行不會連帶放出 W-c（F9W-33 (c)；以 C-34 增列或沿用既有測試釘住）。〔TA4 R-48；F9W-33，F-9b 合併前〕 |

C-11～C-29 出處：TA2 R-25（原文照 TA2「對實作的約束」），各條來源為對應 F9W 裁定與 TA2。C-6、C-13、C-17、C-19、C-26 的 TA4 修訂與 C-34 見各列標註；其中 C-17、C-26、C-34 另納入風控 F9W-30～F9W-33 的條件。

---

## Consequences（後果）

### 好處（任務單所述）

- 估值器、`load_bars` 全部消費者與快取讀取路徑共用同一道幣別檢查，消除「有價格、沒單位」的資料層成因（F7-R14 意圖）。
- F7-R12 (ii) 殘留**只部分關閉**：F-9b 後關閉 2 字母以上字尾的美股代號、台股「數字＋K」（未實證）；F-9c 後（且 F9W-4 已落地）關閉 yfinance 新抓、宣告與市場不符的資料。其餘見壞處 R-a～R-c。〔TA2 R-26；F9W-14。取代初稿「對可偵測情形關閉」的寫法〕
- `_check_currency` 由死碼變成有呼叫者，且判準與 `currency_matches_market` 以等價測試釘住，不新增第二份幣別字典。
- 不新增 DataStatus 與 API 狀態值（D-7）；新增的 `ProviderResult.rejection` 為內部欄位、不進 API。〔TA2 R-27〕
- 不自動遷移，既有資料不被刪除；清理由 CEO 本機明示執行。
- 被准入規則拒絕的代號不呼叫任何來源、不扣 AV 額度。現況下這類持倉每天的 scheduler 刷新（`scheduler.py` L295）都會白白耗掉一次 AV 額度。〔TA1 M-10〕

### 壞處與殘留

1. **誤擋特別股、權證、單位**：美股形狀白名單擋 2 字母以上字尾，合法的此類代號會被拒（任務單設計建議 ii 明列）。
2. **單一字母外國字尾擋不到（殘留）**：單一字母的 Yahoo 式字尾（如 `.L`、`.T`）形狀上與類別股（`.B`）相同，白名單無法區分。緩解：yfinance 會把 `.` 轉成 `-`（`us_symbols.py` L132-139），這類代號大概率查無資料；AV 的外國字尾慣例為 3 字母。兩者都待 F-9d 連網實證；殘留的部分由 F-9c 的 `meta.currency` 檢查補防（僅 yfinance 路徑）。〔TA1 M-11〕此殘留的後續見 R-a。
3. **冷卻期原因句**：W-c 標記序列回 C 版、W-c′ 回 C′ 版（F-9b2）。F-9c 合併前，W-c 不可觸發，暫時沿用 `COOLDOWN_NO_CACHE_REASON`／`RECENT_ATTEMPT_FAILED_REASON`（A 版）可以接受；B 版不採。〔TA2 R-28；F9W-12。T-6 已裁示〕
4. **建構參數改為必填牽動測試**：D-5 將預期幣別注入改為必填建構參數。現況 `MarketDataService(` 建構點 48 處、分布 9 檔（`deps.py` 3 處，其餘為測試，其中 `test_service.py` 32 處）；建議閘門參數為 keyword-only 必填，測試以單一 helper 建構，避免無關 diff。〔TA2 R-29，grep 所得〕明細：production 3 處（`deps.py` L96 TW、L102 US、L131 指數）；測試 45 處 8 檔：`test_service.py` 32（helper `_service` L97-106；`_us_bar` L48-62 為 `symbol="2330"`、`market="US"`，美股准入會擋，須顯式寬鬆 admission 或改字母代號）、`test_us_market_chain.py` 3、`test_fast_fail.py` 3、`test_demo_seed.py` 2、`test_adr0019_pending.py` 2、`test_api_advice.py` 1、`test_services_index_bridge.py` 1（須傳指數用「只檢查幣別」）、`test_scheduler_data_refresh.py` 1。建議 `tests/` 共用 helper 提供「`MARKET_CURRENCY` 查表」與「全部放行 admission」兩個顯式值；production 不給預設值；不得為少改測試而設成可選。〔TA1 M-12；R-29 為其摘要版〕
5. **既有壞列不自動遷移**：layer 0 讀到不符或空白的舊列時，冷卻期外改走梯子並整段重抓：來源能回答時，以通過閘門的新列覆寫請求區間內的舊列（自行修復）；來源失敗時回 `UNAVAILABLE` 並附 T-15，每個冷卻窗至多重跑一輪梯子（美股每窗至多一次 AV 額度）。請求區間外的舊列仍留存，直到 F-9e。未被准入規則涵蓋的舊列仍殘留，F-7 的殘留不會因此完全關閉。〔TA3 R-40；原文後句保留〕
6. **美股交易日行事曆汙染**：外國代號列會汙染美股交易日行事曆（`market_trading_days`／`market_has_session` 不看幣別，任務單所述）。不另案處理行事曆本身：F-9b 後被閘門擋下的列不再寫入（D-3），既有汙染由 F-9e 清理；殘留 R-a、R-b 仍會汙染，數量由 F-9a 盤點交 CEO 知悉。〔TA2 R-30〕併入 F-9e 處置：清除 admission 不通過序列的列，行事曆隨之修正；不在 `market_trading_days`／`market_has_session` 加幣別過濾（舊列幣別欄位寫死，無效）。F-9b 合併後應儘速執行 F-9e；執行前，「資料過舊」提示可能因外國交易日而誤報（F-9a 盤點會輸出受影響的日數）。F-9e 的 dry-run 輸出須包含「清除後各市場減少的行事曆日數」，供 CEO 判斷。〔TA1 M-13，與 R-30 合併〕
7. **範圍外同類路徑（另案，本 ADR 不處理）**：盤中報價寫死 TWD（`quote_quality.py` L359，ADR-0014）、`services/pit_snapshot.py` 直打 FinMind、全市場面板（ADR-0012）、持倉寫入入口代號形狀檢查（新字面、ADR-0017 X3-F2）。
8. **殘留 R-a～R-c**（F7-R12 (ii) 未關閉的部分）〔TA2 R-31；F9W-14〕：
   - **R-a**：Alpha Vantage 供應的單一字母外國字尾代號（AV 寫死 USD，閘門看不出）。
   - **R-b**：寫死幣別的 adapter 寫入的舊快取列（快取閘門只比對宣告值，看不出；F-9e 清不到未被准入涵蓋者）。
   - **R-c**：准入未涵蓋的其他樣式。
   - F-9a 盤點單一字母字尾清單，交 CEO 逐一人工確認。〔F9W-15 suggested，已採納〕
9. **W-c 標記不黏著**：下一次一般失敗會覆寫標記，之後的降級路徑可能再以快取回覆該序列（附既有原因句）；若盤點顯示此類序列存在，再評估「隔離」（只由成功提問或清理指令解除，需新字面）。〔TA2 R-31〕
10. **四組計數**：被拒列不再計入「缺價格或匯率」，X-3c 既有三組計數測試改為四組（只能延伸，不能放寬）。〔TA2 R-31；TA2 影響面風險〕

### 被此決策約束的事

- 日後新增 `load_bars` 以外直接取日線的程式路徑，須經 `MarketDataService`（D-1），不得自行繞過。
- 新增 adapter 不得寫死幣別後直接宣稱為上游宣告值；缺值不補（D-6）。
- 新使用者面字面須經 creative-lead 起草、風控逐字審後才可上線（CLAUDE.md 風險閘門）。
- 新增任何可能以快取回價格的讀取路徑，須先檢查 D-9 標記；新增的 adapter 須有 `source_id`（W-c／W-c′ 的 `{provider}` 只取它）。〔TA2 R-32；F9W-3、F9W-4〕

---

## 與既有 ADR 的關係

| ADR | 關係 | 說明 |
|---|---|---|
| ADR-0003 約束 8 | 具體化 | 跨來源不得靜默拼接、品質檢查觸發須浮上；本 ADR 把幣別納入品質檢查並接上服務層。（任務單所述） |
| ADR-0005 決策三 | 擴充，**不修訂** | 額度計數器與美股 ticker 正規化；`canonical_us_symbol` 語意不變，admission 為其上的獨立檢查；AV adapter 扣額度前多呼叫一次 admission。（任務單所述） |
| ADR-0005 I-3 | 相容 | 任務單所述；內容細節 tech-writer 未對照逐條驗證。 |
| ADR-0009 | **部分修訂**（D-9、D-2 (2)(3)） | D-3 的 attempt log 語意擴充；R-8／D-8 在帶 W-c 標記序列上的行為改變；ADR-0009 只在檔頭加一行指標；D-8 清理依其 R-5 連帶刪 log。須 CEO 核可。〔TA2 R-3、R-33〕 |
| ADR-0010 | 相容 | 見「關聯」。〔TA2 R-4、R-33〕 |
| ADR-0019 | 相容（先後皆可） | 見「關聯」。〔TA2 R-5、R-33〕 |
| ADR-0017 X3-F3 | 觸發時連帶重審 | `MARKET_CURRENCY` 變動（新增市場或幣別，或允許美股以台幣交割記帳）時，本 ADR 須與 X-3 規則一併重審。（任務單所述） |
| ADR-0017 X3-F7 | 補前提 | 「已估值列的日線價格單位與市場一致」；殘留下不保證成立，CEO 須知悉。〔TA2 R-6、R-33〕 |
| ADR-0022／ADR-0023 | 規則不變 | 被撤下的列進入同一未估值集合。〔TA2 R-7、R-33〕 |

---

## 失效條件

出處說明〔TA2 R-34；TA1 失效條件意見〕：原 1～6（舊編號）為 tech-writer 依草案各項決策與明示前提自擬，經 tech-architect 2026-10-12 確認（第一次核對保留 1、4、5、6 並改寫 2、3；第二次評估確認 1～6）；其餘為 tech-architect 於第一次核對或第二次評估增列。以下已合併兩次意見、去重並重新編號，每條註明出處。

| # | 條件 → 動作 | 出處 |
|---|---|---|
| 1 | 連網實證顯示 yfinance 的 `meta.currency` 實際上不可得、型別與預期不同、或缺值比例使 role 1 大量被服務層判為 W-c′（`UNAVAILABLE`）→ 重審 D-6。 | tech-writer 自擬並經 tech-architect 確認（第二次評估 R-34）；用語同步 R-19 |
| 2 | 連網實證顯示 AV 或 yfinance 會接受單一字母外國字尾並回傳非美元價格，或 `BRK.B` 類代號在任一來源的實際格式與假設不同 → 重審 D-4 美股白名單。 | tech-writer 原擬，tech-architect 第一次核對改寫（M 失效條件第 2 條） |
| 3 | 連網實證顯示存在 K 以外的台股外幣計價樣式，或「數字＋K」其實非外幣計價、或有 K 字尾但以 TWD 計價的合法商品（會被誤擋）→ 重審 D-4 台股樣式（目前 `verified=False`），准入規則與 W-b 回風控。 | tech-writer 原擬，第一次核對改寫（M 第 3 條）；與第二次評估增列的「F-9d 實證『數字＋K』…」（R-35 第 8 條）合併去重 |
| 4 | `MARKET_CURRENCY` 變動（ADR-0017 X3-F3）→ 重審 D-5 與本 ADR 整體（變動後所有既有快取列都會被快取閘門拒收，每條序列每個冷卻窗各重抓一次；須連同重抓成本一併重審）。 | tech-writer 自擬並經確認；句尾括號為第二次評估 / TA3 R-44 增列 |
| 5 | 風控否決或撤回任一新字面或字面用法（W-a、W-b、W-c、W-c′、C、C′（T-13）、T-11、T-12、T-14、T-15，以及 T-17「W-c′ 有快取時沿用 `RECENT_ATTEMPT_FAILED_REASON`」）→ 重審 D-7／D-9 與對應 PR 範圍。T-14 若被否決，只退回 C 版，不影響其餘。 | tech-writer 自擬，第二次評估 R-34 改寫；T-14、T-15、T-17 為 TA4 R-51 補列 |
| 6 | 範圍外同類路徑（盤中報價、`pit_snapshot`、全市場面板、持倉寫入入口）改為納入同一閘門 → 重審 D-1 的「唯一閘門」範圍。 | tech-writer 自擬並經確認 |
| 7 | 新增任何不經 `MarketDataService` 取得日線價格的 production 路徑 → 重審 D-1。 | tech-architect 第一次核對增列 |
| 8 | `MarketDataService` 新增快取讀出口 → C-1 必須同步補測試，否則視為閘門有缺口。 | tech-architect 第一次核對增列 |
| 9 | F-9a 盤點或日後回報顯示有合法美股商品被白名單誤擋 → 重審白名單；任何代號列入例外須經 tech-architect 與風控。 | tech-architect 第一次核對增列 |
| 10 | F-9c 在 F-9b 之前合併 → 視同 F7-R12 (ii) 殘留擴大，回報風控。（F-9c 亦須在 F-9b2 之後合併，見 D-6、PR 硬性前提；第一次核對原文只寫 F-9b，F-9b2 部分依第二次評估 R-20 與「五」補列。） | tech-architect 第一次核對增列；第二次評估延伸 |
| 11 | F-9c 實證 `meta.currency` 出現大小寫或其他變體（例：`usd`）→ 重審 D-2 分類規則與 W-c 字面（回風控）；**延伸**：T-11 第二個子原因、T-14 的「不是美元／不是新台幣」、T-15 的「與市場所用的單位不同」同屬此條，連同 W-c 一併回風控重審。 | 第二次評估增列（R-35 第 7 條，F9W-3）；延伸為風控 F9W-27 |
| 12 | 單一字母字尾盤點出外國掛牌持倉 → 重審 D-4 美股白名單（考慮已知外國交易所字母清單）與 D-9 是否改為黏著。 | 第二次評估增列（R-35 第 9 條，F9W-15） |
| 13 | 指數幣別檢查要觸發，**或指數快取閘門在實際環境被觸發（F9W-31 (b) 的記錄出現、或手動改庫）** → 回風控；指數字面送審（T-16）；重審 D-4 指數段。 | 第二次評估增列（R-35 第 10 條，F9W-9）；擴寫依 F9W-32 (a) |
| 14 | CEO 放寬 F9W-4 → 重審 D-2 (2)(3)。 | 第二次評估增列（R-35 第 11 條，F9W-4） |

---

## 尚缺的事實（待可連網環境實證）

以下各項任務單明示未上網實證；實證須由 CEO 本機或 devops-sre 可連網環境執行（任務單流程欄）。編號 8 以後為修訂新增（先 TA2 R-36，再 TA1 M-14，M-14 編號依其註記順延）。

| # | 待實證事項 | 影響 | 對應 PR |
|---|---|---|---|
| 1 | yfinance 實際回傳的 `meta.currency`（現有 fixture 皆合成），**含 USD／TWD 實際寫法**〔TA2 R-36；F9W-3〕 | D-6；需重錄真實 fixture | F-9c |
| 2 | yfinance `meta.currency` 缺值時的實際情形 | D-6 缺值測試 | F-9c |
| 3 | yfinance role 2（指數）是否可採同一規則 | D-6 role 2 | F-9c（合併須等實證與 T-16） |
| 4 | Alpha Vantage 對帶外國交易所字尾代號（如 `TSCO.LON`）的實際行為；`BRK.B` 是否被接受 | D-4 美股白名單 | F-9d |
| 5 | 台股 K 字尾雙幣 ETF 現況是否仍掛牌（F7-R8 (iii)，任務單：未查證） | D-4 台股樣式、`verified` 欄 | F-9d |
| 6 | 台股外幣計價交易單位的上游實際回傳 | D-4 台股樣式 | F-9d |
| 7 | 既有快取中不符列、admission 不通過的序列與持倉、汙染行事曆日數的實際數量 | D-8 清理規模 | F-9a 已合併，**盤點結果待 CEO 本機執行** |
| 8 | AV 對 `.L` 等單一字母外國字尾的實際反應〔TA2 R-36；F9W-14〕（M-11：yfinance 對此類代號的反應——`.` 轉 `-` 後是否查無資料——亦待實證） | D-4 美股白名單、殘留 R-a | F-9d |
| 9 | 單一字母字尾序列與持倉清單〔TA2 R-36；F9W-15〕 | 殘留 R-a、失效條件 12 | F-9a 已合併，由 CEO 本機盤點 |
| 10 | 美股 root 長度（1–5 個字母）的官方規格〔TA1 M-14〕 | D-4 美股白名單 | F-9d |
| 11 | AV `SYMBOL_SEARCH` 是否回傳幣別欄位（後續方案 C 的前提）〔TA1 M-14〕 | 後續擴充，本 ADR 不依賴 | F-9d（可選） |

另：任務單「現況」整段標為「讀碼推論，未上網實證」；tech-architect 評估為唯讀讀碼（TA2、TA3 亦未執行測試、未連網）。tech-writer 未讀後端 code，**待查證**：F-9a 實作者或 qa-reviewer 於實作前以原文定位核對本檔所引行號（F-9a 合併後行號可能已漂移；保留此項是因為 tech-writer 本次仍未讀 code）。

---

## PR 拆分與順序

（任務單「拆 PR」表與「coordinator 定案（CEO 可推翻）」為初稿來源；本節 PR 表依 TA2「五」更新，B 類轉錄。）〔TA2 R-37〕

| PR | 內容 | 前提／審查 |
|---|---|---|
| **F-9a**（已合併，見下「實作進度補記」） | `diagnose` 唯讀幣別盤點（SQLite `mode=ro`；列不符列、admission 不通過的快取序列與持倉、汙染行事曆日數；只輸出計數與代號，無數量與成本）；US／TW admission 純函式；`check_currency` 公開＋等價測試；服務層對宣告不符記 WARNING（行為不變）；加上 F9W-15（suggested，採納）：列出所有通過准入、帶單一字母字尾的快取序列與持倉（只列代號與計數，A／B／C 等常見類別字母只標註、不判斷），交 CEO 人工確認 | qa-reviewer＋Codex；不需 qa-e2e、不需風控 |
| **F-9b**（範圍擴大） | 服務層閘門與 `classify_currency`；兩個入口的准入；`ProviderResult.rejection`；`load_bars` W-d；F9W-4 (a) 同次回覆不讀快取；W-a、W-b、W-c、W-c′ 常數；快取閘門（含 T-15 四條路徑）；新 token、整書成因組、前端標籤（F9W-11）；方向子句測試（F9W-13）；deps 接線（含指數閘門無字面，F9W-9）；AV 縱深檢查（F9W-7）；消費端字串表（F9W-10）。建議分 commit：介面 → 閘門 → 准入 → W-d → 估值器 → 成因組 → 前端 → deps | 字面 T-11、T-12、T-15（風控第二批已核可主案）；F9W-18 工程條件（D-7 (2)(3) 不變式與互斥、C-19、C-34）〔TA4 R-55〕；建議 ADR-0024 修訂版經 CEO 核可；qa-reviewer＋Codex＋風控＋qa-e2e（K 線區、操作摘要、首頁風險上限「詳細」、庫存頁，375／1280；庫存頁驗 T-12 與整書四組並列折行，三處驗 T-15 與合併 reason）。qa-e2e 依 `e2e-fallback` skill 以 fixture 造出受閘門擋下的狀態（執行與判斷分離）；確認原因句可見、無價格數字、無價格單位標籤。〔TA1 M-15；F9W 第二批下一步 4〕 另依 F9W-34，qa-e2e 在 375／1280 驗 K 線區的 W-c′＋通過閘門的快取情境（C-34 (b)）：主畫面 compact「快取資料」標示、價格、「價格單位：美元」三者並存、不溢位；`<details>` 內「快取資料…」後接完整合併 reason、不截斷；操作摘要、首頁風險上限「詳細」兩處同一 reason 完整呈現。 |
| **F-9b2**（新增） | D-9 標記欄位與遷移；layer 0 前置守門（C／C′、冷卻期外強制走梯子）；`get_cached_bars` 讀標記；F9W-12 測試 | 在 F-9b 之後；C′（T-13）已核可；T-14 已核可兩句，採用與否由實作端選（採用須全面，F9W-21）；W-c′ 加快取被擋的二擇一（D-2 (5)(a)）已擇定 C′〔TA4 R-47〕，依 D-2 (5)(a) 五步先後實作並以完全相等測試釘住；qa-reviewer＋Codex＋風控（字面） |
| **F-9c** | yfinance role 1 讀 `meta.currency`，缺值傳空字串；role 2 排除 | 見下方硬性前提 |
| **F-9d** | 原範圍，加 AV 對 `.L` 的反應（F9W-14）；「數字＋K」實證結果回風控（F9W-8）；美股 root 長度規格（M-14） | 需連網 |
| **F-9e** | 原範圍，（suggested）可列出帶 W-c 標記的序列；dry-run 輸出含清除後各市場減少的行事曆日數 | CEO 本機執行 |

- **硬性順序：F-9b 與 F-9b2 必須早於 F-9c 合併。** 原因（任務單所述）：否則「有價格、沒單位」狀態會變多。
- **F-9c 合併前的硬性前提**〔TA2「五」〕：
  1. F-9b 已合併，含 F9W-4 (a) 與 F9W-11。
  2. F-9b2 已合併，含 F9W-4 (b) 與 F9W-12。
  3. C′ 字面已核可（現況：F9W-20 已核可）。
  4. 真實 fixture 已確認 USD／TWD 寫法（F9W-3）。
  5. role 2 已排除；若要納入，指數字面 T-16 須先核可。
  6. ADR-0024 已 accepted。
- ADR-0019 的實作與 F-9b2 先後都可以，後合者負責 rebase，並重跑 ADR-0019 T-5（REFETCH 不得帶 `RECENT_ATTEMPT_FAILED_REASON`）。〔TA2「一」〕
- coordinator 定案（CEO 可推翻；任務單所述）：F-9 依預排接在 F-1b 之後開工；F-9a 先行；並行由 creative-lead 起草字面、風控逐字審並裁示兩題，使 F-9b 不卡字面；F-9c／F-9d 連網實證交 CEO 本機或 devops-sre 可連網環境。

### 實作進度補記（F-9a）

- F-9a 已合併（commits `d6b2f58`、`ecf70b9`，2026-10-12）。
- 服務層對宣告不符記 WARNING，開頭字串為 `price bars currency differs from market:`。
- 盤點指令：`python -m app.data.diagnose currency-inventory`（SQLite `mode=ro`；可能遺留 0 byte 的 `-wal`／`-shm` 檔）。
- 盤點結果**待 CEO 本機執行**後回報；在此之前，F-9a 核實「目前無美股持倉」（Options 表 2）、尚缺的事實 7、9 皆未完成。
- 來源：coordinator 本次任務指示（2026-10-12）。tech-writer 未讀這些 commit 的內容，上述字串與指令為轉錄，未經 code 驗證。

### 風險與相依

- F-1／F-1b 正交（先幣別閘門、再 `usable_price`／`usable_rate`）。
- **X-3c 與方向子句**〔TA2「四」更正句，取代任務單 L54 整句；F9W-13〕：X-3c 為不同軸，F-9 不重用其字面。被 F-9 撤下的列（准入拒絕、W-c、W-c′）以 `status=insufficient_data` 進入與其他未估值列相同的未估值集合（`UnvaluedComposition`）；方向子句由既有規則（`book.py::_symbol_direction`／`_book_direction`，只看估值狀態、產業歸屬與是否本標的，不看成因）選出 D-a／D-P／D-d1／D-d2，「偏高」只在選中 D-a 時成立，並非一律成立。（初稿「被撤下列使總資產變小，方向子句『偏高』仍成立」不採。）
- **X3-F7 前提**補「已估值列的日線價格單位與市場一致」（不用「價格幣別」）；此前提在殘留 R-a～R-c 下不保證成立，CEO 須知悉。〔TA2 R-37；F9W-13、F9W-14〕
- **F-7**：F7-R12 (ii) 殘留只部分關閉（內容見 Consequences 好處第 2 點）；未被准入規則涵蓋的舊列仍殘留。〔TA2 R-37、R-26〕
- **方向子句測試**（後端，F-9b；TA2「四」）：
  1. 被撤下列（帶新 token）出現在 `UnvaluedComposition`，且 `composition.total()` 等於整書未估值數。
  2. 被撤下列是本標的自己的列、而且是唯一的未估值列 → D-d1；同時還有其他標的未估值 → D-d2。
  3. 被撤下列屬於別的標的、和卡片同產業 → D-P；產業未知 → D-P。
  4. 被撤下列屬於別的標的、在其他產業，卡片有產業 → D-a。
  5. 整書範圍：回報產業 Y 為 None → D-a；被撤下列在 Y 內 → D-P。
  6. 同一本帳同時有 X-3c、新組、not_queried、asked 各一列：四句成因各自的 count 正確、互斥，方向子句只選一次、四句共用。

---

## 待決事項

字面狀態依 TA2 R-37、TA3 R-46 更新，再依風控第二批（F9W-17～F9W-29）改標；**已核可的字面本檔仍不收錄全文，只列代號與出處**（核可全文見風控裁定檔）。

| # | 事項 | 負責 | 狀態 |
|---|---|---|---|
| T-1 | W-a（美股外國字尾被拒）字面 | creative-lead → 風控 | 已核可（alt-1；F9W 第一批，條件 F9W-1） |
| T-2 | W-b（台股外幣交易單位被拒）字面 | 同上 | 已核可（第二句 alt-2；條件 F9W-2） |
| T-3 | W-c（來源宣告幣別與市場不符）字面 | 同上 | 已核可（美／台各一句；F9W 第一批、條件 F9W-3） |
| T-4 | W-d（`load_bars`）字面 | 同上 | 已核可（不另立基底句、不加前綴；保守退路未核可；F9W-6） |
| T-5 | 風控裁示 1：整書成因 | 風控 | 已裁示：另立成因組（F9W-11） |
| T-6 | 風控裁示 2：冷卻期原因句 | 風控 | 已裁示：採 C 版（F9W-12） |
| T-7 | 風控確認：X-3c 方向子句 | 風控 | 已更正（F9W-13；見「風險與相依」） |
| T-8 | 風控確認：X3-F7 前提 | 風控 | 已同意，用詞「日線價格單位」（F9W-13） |
| T-9 | 風控確認：F7-R12 (ii) 殘留 | 風控 | 部分關閉（F9W-14） |
| T-10 | 本 ADR 核可（proposed → accepted），含 ADR-0009 部分修訂 | CEO | 待核可 |
| T-11 | 整書成因句 | creative-lead → 風控 | 已核可（主案；F9W-17）；F9W-18 工程條件須於 F-9b 合併前落實 |
| T-12 | 庫存頁新標籤 | 同上 | 已核可（主案；F9W-19） |
| T-13 | C′ 版（W-c′ 冷卻） | 同上 | 已核可（主案；F9W-20；F-9b2 合併前提）；適用範圍依 F9W-23、F9W-30 擴及快取被擋 |
| T-14 | C 版是否分市場兩句（suggested） | 實作端選用 | 已核可美／台兩句（F9W-21）；採用即全面使用、不得與 C 版混用；是否採用待實作端決定 |
| T-15 | 快取舊列幣別不符 fail-closed 的原因句 | creative-lead → 風控 | 已核可（主案；F9W-22）；涵蓋四條路徑；F-9b 合併前提；併入 W-d。〔TA3 R-46 原狀態為「已起草，待風控」，風控已核可後更新〕 |
| T-16 | 指數用字面 | creative-lead → 風控 | 待起草（role 2 合併前；不急）；起草範圍須明列「指數快取被閘門拒收」情境，T-16 核可後此情境不得再接「（來源與快取皆無）」（F9W-32 (b)） |
| T-17 | W-c′ 有快取時沿用 `RECENT_ATTEMPT_FAILED_REASON` | 風控 | 已核可（F9W-24，條件：閘門檢查在 R-8 分支之前、該列照 F9W-18 正常估值） |
| T-18 | 新組陳述順序 | 風控 | 已核可（W4 → W5 → (b) → 本組；F9W-25） |
| —（F9W-23 衍生，來源未編號） | 有效 W-c′ 標記、冷卻期內、快取被擋：回 C′ 或只回 T-15 | tech-architect | 已擇定：C′（TA4 R-47）；以完全相等測試釘住（F9W-23；其他合併組合不得出現）。屬 F9W-23 授權範圍，擇定結果須轉知風控（只需知悉） |

已核可字面總覽〔TA2 R-37；F9W 第二批〕：第一批已核可 W-a、W-b、W-c（美／台）、W-c′（美／台）、C，共 7 句；第二批另核可 T-11 主案、T-12 主案、T-13 主案、T-14 美／台兩句（選用）、T-15 主案。不採的版本（含 T-11 alt-A～D、T-12 alt-1～3、T-13 alt-1～3、T-15 alt-1～4、冷卻期 B 版、W-d 保守退路）若要啟用須另送審。〔F9W 第二批「不採用的版本」；F9W-12〕

字面核可後如需收錄於本 ADR，比照 ADR-0022／0023 先例由 coordinator 指示（本檔現不收錄任何字面）。

**給 CEO 的知悉事項**〔TA2「給其他部門」〕：本修訂把 ADR-0009 列為「部分修訂」，需要核可；X3-F7 前提在殘留 R-a～R-c 下不保證成立；W-c 標記不黏著；F-9c 有 6 項硬性前提；F-9a 盤點結果待本機執行後依單一字母字尾清單逐一確認。另，指數路徑殘留（非正式設定下指數快取閘門被觸發時，reason 沿用既有指數版 `NO_BARS_REASON`「（來源與快取皆無）」；風控附條件接受，見 D-4、失效條件 13）須於 T-10 核可時一併知悉。〔F9W-32 (d)；TA4 R-49〕

---

## 佐證清單（tech-writer 交件）

**快照**：分支 `product/stock-desk`，HEAD `260ef0419b02df769aed6f331281e5d71259d65e`（本次修訂時讀取 `.git/refs/heads/product/stock-desk`；初稿快照為 `d583ebdef1fc8bebef7a8d471f546f7d6677e3fb`）。行號（含下列來源檔的 L 行號與本檔所引後端 `檔案:行號`）會隨時間漂移，抽驗請以原文定位。

**A 類**：本檔**無** A 類宣稱（未讀後端 code，未描述未經來源的系統當前行為）。凡看似 A 類的敘述（欄位、函式、行號、預設值），皆屬 B 類轉錄。

**B 類**：來源檔簡稱——TASK＝`work/dispatch/2026-10-08-任務單-F-9-日線上游幣別未核對.md`（2026-10-12 版本）；TA1＝`work/reviews/2026-10-12-tech-architect-ADR-0024落檔核對M-1至M-15.md`；TA2＝`work/reviews/2026-10-12-tech-architect-F-9-風控裁定工程評估與ADR-0024修改清單R-1至R-37.md`；TA3＝`work/reviews/2026-10-12-tech-architect-F-9-第二批字面四題回覆R-38至R-46.md`；TA4＝`work/reviews/2026-10-12-tech-architect-ADR-0024抽驗與待確認項裁決R-47至R-56.md`；F9W-A＝`work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md`；F9W-B＝`work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md`；F9W-C＝`work/reviews/2026-10-12-F-9-R47至R49送審裁示-F9W-30至F9W-34-風控.md`。

| 本檔章節 | 來源（版本皆為 2026-10-12） |
|---|---|
| 檔頭 狀態／accepted 前提 | TA2 R-1（L124）；F9W-A 第 6 題（L73-75）；TA1 M-1（L5，已被取代）；TA2「給其他部門」CEO 項（L246-249） |
| 檔頭 優先序、來源與版本 | 使用者（coordinator）任務指示；TA2 R-2（L125） |
| 關聯 ADR-0009／0010／0019／0017 X3-F7／0022-0023／X-3c | TA2 R-3～R-8（L126-131） |
| Context 1～5、現況盤點（原有部分） | TASK L3-L10、L21-L28 |
| Context 2 第一點（role 1／2、FX 路徑） | TA1 M-2（L6） |
| Context 4（方向不必然偏低） | TA2 R-9（L132）；推論未實證註記見 TA2 驗證（L272） |
| 現況盤點 繞過者 | TA1 M-3（L7） |
| Options 表 1、表 2、`_check_currency` 處置 | TASK L15、L33；TA1 M-4（L8-11）；TA2 R-10（L133） |
| Options 表 3、表 4 | TA2 方案比較（L29-44）；R-10 |
| D-1 | TASK L38；TA2 R-12（L135） |
| D-2 (1)～(4)、(6) | TA2 R-13（L136）；TA1 M-7（L14）；F9W-A F9W-3、F9W-4（L46-49） |
| D-2 (5) | TA3 R-39（L99）、R-45（L105）、題 2、3（TA3 L41-69）；F9W-B F9W-23（L81-84）、F9W-24（L85-90） |
| D-3 | TASK L34、L42（C-3） |
| D-4 | TASK L31-L32、L38；TA2 R-14～R-16（L137-139）；TA1 M-5（L12）；F9W-A F9W-7、8、9（L52-54） |
| D-5 | TASK L33、L7；TA2 R-17（L140）；TA1 M-6（L13） |
| D-6 | TASK L30、L38；TA2 R-18～R-20（L141-143）；TA2 結論 採用方案（L24）；F9W-A F9W-14（L65-69） |
| D-7 | TASK L17、L35、L38；TA2 R-21、R-22（L144-145）；TA3 R-38、R-41（L98、L101）；F9W-A F9W-6、F9W-11、F9W-12（L51、L56-61）；F9W-B F9W-17、F9W-18、F9W-22、F9W-25、F9W-28（L51-59、L74-80、L91-93、L101-103） |
| D-8 | TASK L38、L51；TA2 R-23（L146）；TA1 M-13（L20） |
| D-9 | TA2 R-24（L147）；F9W-A F9W-4、F9W-12（L47-49、L61）；F9W-B F9W-20、F9W-21、F9W-23、F9W-24、F9W-26（L65-73、L81-90、L94）；TA3 R-38 |
| 實作約束 C-1～C-10 | TASK L42；TA1 M-8、M-9（L15-16）；TA3 R-45（L105） |
| 實作約束 C-11～C-29 | TA2 R-25（L148）與 TA2「對實作的約束」（L217-240）；F9W-B 追加註記（F9W-18、21、23、24、25、29） |
| 實作約束 C-13、C-30～C-33 | TA3 R-42、R-43（L102-103）、題 4（L70-77） |
| Consequences 好處 | TASK L55-L56（原有）；TA2 R-26、R-27（L149-150）；TA1 M-10（L17） |
| Consequences 壞處 1、2、3 | TASK L31、L35；TA1 M-11（L18）；TA2 R-28（L151） |
| Consequences 壞處 4 | TASK L38、L42；TA2 R-29（L152）；TA1 M-12（L19） |
| Consequences 壞處 5 | TASK L38、L55；TA3 R-40（L100） |
| Consequences 壞處 6 | TASK L24、L47；TA2 R-30（L153）；TA1 M-13（L20） |
| Consequences 壞處 7 | TASK L56 |
| Consequences 壞處 8～10、被約束的事 | TA2 R-31、R-32（L154-155）；F9W-A F9W-14、F9W-15（L65-70） |
| 與既有 ADR 的關係 | TASK L18、L39；TA2 R-33（L156）；ADR 條文由 tech-writer 讀取確認存在（ADR-0003 L58、ADR-0005 L133、ADR-0009 L154、ADR-0017 L185） |
| 失效條件 | TA1 失效條件（L24-29）；TA2 R-34、R-35（L157-158）；TA3 R-44（L104）；F9W-B F9W-27（L95-100）；去重與編號為 tech-writer 整理 |
| 尚缺的事實 | TASK L5、L9、L30、L32、L49-L50、L62；TA2 R-36（L159）；TA1 M-14（L21） |
| PR 拆分與順序 | TASK L44-L56、L58-L61；TA2 R-37（L160）與「五」（L196-215）；TA1 M-15（L22）；F9W-A F9W-15；F9W-B 下一步（L123-138） |
| 實作進度補記（F-9a） | coordinator 本次任務指示（commit 代號、WARNING 開頭字串、盤點指令、`mode=ro` 與 `-wal`／`-shm` 說明、結果待 CEO 本機執行）；tech-writer 未讀 commit 內容 |
| 風險與相依、方向子句測試 | TA2「四」（L164-194）；TA2 R-37；F9W-A F9W-13（L62-64） |
| 待決事項 | TA2 R-37（L160）；TA3 R-46（L106）；F9W-B 結論與條件（L6-L109）；F9W-A 判定（L7-L15） |
| TA4 套用（2026-10-12；L 行號為 TA4 檔內行號，以原文定位） | D-2 (5)(a) 五步、D-9 冷卻字面第 2／4 子項、C-26、待決事項末列、PR 表 F-9b2 列：TA4 R-47、R-53（L43-66）。D-2 (5)(c)：R-54（L132-134）。D-4 指數路徑、C-17：R-49（L88-102）。D-7 (2) 不變式、D-7 (7) 三分流、C-34：R-48（L68-86）。C-13 (6) 與註：R-50（L104-112）。失效條件 5：R-51（L114-120）。C-19、D-6、D-7 (3) 不查匯率：R-52（L122-128）。PR 表 F-9b 前提：R-55（L135-136）。C-6：R-56（L138-140）。TA4 送審兩項的原始敘述：TA4 本文「本次結論」第 3 點與「需送風控知悉」（L19、L102、L147-148） |
| 風控對 TA4 送審項的裁示（2026-10-12；L 行號為 F9W-C 檔內行號，以原文定位） | D-9 與 C′ 出處、C-26 兩子情境與五步測試：F9W-30 (a)～(e)（F9W-C L26-31）。D-4 指數殘留條件、C-17 絆線與記錄：F9W-31 (a)～(c)（L45-49）。失效條件 13 擴寫、T-16 範圍、不作股票先例、CEO 知悉：F9W-32 (a)～(d)（L50-54）。C-34 (b)(e)、橋接句限制、D-7 (7) 已裁示：F9W-33 (a)～(d)（L71-75）。F-9b 驗收欄 qa-e2e 項：F9W-34（L76-79）。無新字面（F9W-C L111） |

**tech-writer 未驗證**：所有後端 `檔案:行號`、函式名、常數名、測試名（皆保留 tech-architect 原樣）、F-9a 的 commit 內容與 WARNING／指令字串。草案若與 code 不符，請 tech-architect 確認。

**本次修訂的待確認項（tech-writer 提出）已由 tech-architect 於 TA4 裁決**：(1) D-2 (5)(a)：W-c′ 標記＋快取被擋的 C′ 或 T-15 二擇一 → 擇定 C′（TA4 R-47）；(2) D-7 (7)：有 bars 且 `rejection` 不為 None 的回覆在 `load_bars` 的處置 → 以不變式排除並定三分流（TA4 R-48）；(3) D-4：T-14、T-15 與指數路徑的關係 → 皆不適用，非正式設定觸發的殘留見下（TA4 R-49）；(4) C-13 (9) 與 F9W-23 禁止組合的判讀 → 兩者不同（TA4 R-50）；(5) 失效條件 5 是否補列 T-14、T-15 → 補列，另加 T-17（TA4 R-51）。

**TA4 送審項已由風控裁示（F9W-30～F9W-34；整體 APPROVE WITH CONDITIONS，無否決）**：(a) 指數路徑非正式設定觸發時沿用既有指數版 `NO_BARS_REASON`（「快取皆無」不精確）→ 附條件接受列為殘留（F9W-31、F9W-32；D-4、C-17、失效條件 13、T-16）；(b) W-c′ 層加上通過閘門的快取、經 `_fall_back_to_cache` 回快取時，K 線區合併 reason 配快取價格與 F-7 單位標籤 → 可接受，附條件（F9W-33、F9W-34；D-7 (7)、C-34、F-9b 驗收欄）；(c) R-47 擇定 C′ 屬 F9W-23 授權範圍 → 風控知悉、無異議，附 F9W-30 條件（D-2 (5)(a)、D-9、C-26）。仍待指定：指數快取閘門被擋時的操作端記錄方式（沿用 `CURRENCY_DIFFERS_LOG_PREFIX` WARNING 或同等方式，F9W-31 (b)，待 tech-architect 指定）。

**tech-writer 套用 TA4 時的對照限制**：TA4 的讀碼結論（含 `deps.py` L144-149、`index.py` L265／L385、`INDEX_SYMBOL_METADATA` 與 `MARKET_CURRENCY` 一致）皆為轉錄，tech-writer 未讀後端 code；TA4 自述「指數快取閘門正式設定下不可達」與「R-48 各情境的 reason 字串」屬推論、尚未實證。
