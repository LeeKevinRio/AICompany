# 任務單：FD-5 行程條件擴充（人數、艙等、航空、出發時段）

- 狀態：done（待 CEO 驗收）
- 發起人：總經理（CEO 定調）
- 目前負責：CEO
- 相關文件：`work/flight-deals-FD-5-PRD.md`、`work/flight-deals-PRD.md`（FD-1，FR-A、FR-C）、`work/flight-deals-FD-2-PRD.md`（revision、下拉）、`work/flight-deals-FD-4-PRD.md`（摘要、列表趨勢）、`work/tasks/FD-4.md`、`docs/adr/0002-flight-deals-技術棧與資料源.md`（accepted；D-1、C-14、C-17 為約束；`watch.cabin` 與 `watch.adults` 的 CHECK 需處理；D-6 金額）

## 目標

讓每個監看可設定：

1. 人數：成人 1 至 9、兒童 0 至 9（嬰兒不做）。
2. 艙等：經濟／豪華經濟／商務／頭等，預設經濟。
3. 航空公司偏好（可選）：1 至 5 家，IATA 二碼儲存，中文名稱選取，內建至少 30 家對照表。
4. 出發時段偏好（可選）：最早與最晚出發整點 0 至 23，當地時間，套用去程與回程各段。
5. 價格口徑：Google Flights 回傳整組乘客總價，預算、紀錄、通知、列表、詳情、摘要全部以總價計，所有價格處標明人數與艙等（例「TWD 18,509（2 大 1 小總價）」，單人標「1 人」），不做每人價換算。
6. 修改人數、艙等、航空、時段任一項，視為影響價格的設定變更，沿用 FD-2 revision（舊歷史標「舊設定」，通知基準重算）。
7. 既有監看不變（經濟艙 1 人）。
8. 查票連結：能帶入人數與艙等就帶，否則連結旁註明「請自行調整人數與艙等」，由實作者實測決定。

範圍外：嬰兒、多艙等混合、抵達時段、飛行時間上限、里程／點數票、每人價換算。

## 驗收條件

完整 Given/When/Then 見 PRD「驗收條件」章節（AC-P1 至 AC-P8、AC-A1 至 AC-A14、AC-V1 至 AC-V11、AC-C1 至 AC-C10）。摘要：

- 乘客與艙等：2 大 1 小建立後價格帶「2 大 1 小總價」；商務艙查到的價與經濟艙不同；人數上限與非法值（0、10、負數、非數字、合計超過 9、非法艙等）被拒絕。
- 航空與時段：指定航空後結果只含該航空；時段設定後結果出發時刻落在區間內（以實際查價結果驗）；航空代碼白名單與 5 家上限；篩選後無結果與資料源失敗區分。
- 價格口徑：預算以總價比較；推播與每日摘要含人數與艙等；列表、詳情、通知紀錄皆標示；禁用字檢查。
- 驗證與相容：修改人數／艙等／航空／時段後舊歷史標舊設定；只改預算或值未變不升版；既有監看與通知紀錄不受影響；遷移有備份可回復。

## tech-architect 評估關卡需回覆

1. 資料模型與遷移：放寬 `cabin`、`adults` CHECK，新增兒童、航空清單、時段欄位；重建表的 FK 與備份處理；既有監看預設值；`revision` 判定欄位；`item_key`／`dedupe_key` 是否須含新條件（PRD 開放問題 6）。
2. 資料源能力（可請實作者先做實測）：指定航空與出發時段是原生還是取回後篩選；人數、兒童、艙等如何帶入；對用量與 FR-B3 上限的影響；聯營與轉機航空認定（開放問題 2、7）。
3. 價格口徑：確認所有顯示處與比較邏輯（預算、下跌比例、歷史新低、列表趨勢、摘要）皆以總價，並列出需改動的模板與推播文案位置。
4. 航空對照表的存放形式、出處與查證方式（開放問題 8）；多選下拉在 D-1、C-14 約束下的做法。
5. 是否需增補 ADR-0002 或另開 ADR。
6. 評估通過才可推進至 `build`；若認為某需求不可行，須退回 product-manager 並附理由。

## 待回覆的預設值

PRD 開放問題 1（合計上限 9 人，待 CEO 確認）、2（所有航段實際承運航空皆須在所選範圍）、3（時段含頭含尾，最晚 12 即至 12:59）、4（不另加確認步驟）、5（不做分組篩選）、9（revision 變動後不跨版本比較）。未覆議則照預設。

## 後續關卡（預期）

- spec → build：tech-architect 評估通過；dev-lead、frontend-engineer 分工。
- review：qa-reviewer（含 Codex）；遷移備份與回復、禁用字、總價口徑測試必過。
- risk-gate：新增文案屬事實陳述，原則上不適用；若加入建議性文案須重送 risk-compliance-officer。
- UI 實機：qa-e2e（或總經理代跑），含 375px 與鍵盤；依賴真實查價的驗收項（AC-P7、AC-P8、AC-A7、AC-A8、AC-A10）須附實跑結果；真實 Telegram 推播送達由 CEO 或總經理手動驗收。

## 交接紀錄

- 2026-10-28 product-manager → tech-architect：FD-5 PRD v0.1 與驗收條件已定（依總經理定調），請依上列評估關卡回覆；開放問題 1、3、4、5、9 待 CEO（有預設），2、6、7 待 tech-architect，8 待實作者，10 待 qa-e2e。PRD 相對定調新增三點：成人兒童合計上限 9、無符合結果與資料源失敗分開計、值未變不升 revision。
- 2026-10-28 tech-architect → 總經理：評估通過，不另開 ADR；增補小節與 C-37～C-42 落進 ADR-0002。要點：migration 0003 重建 watch 父表（禁止先改名舊表）、總價口徑、硬篩選 ≤5 家、時段只套去程、tfs 查票連結（`ports.BookingLinkBuilder`）、去重 key 納入 revision。
- 2026-10-28 總經理：實測 Google Flights 總價語意與篩選生效（TPE→NRT：1 成人 6,202／2 成人 9,736／2 大 1 小 18,509／商務 20,904／BR 06–12 時 2 筆）；查票連結文字查詢不支援人數艙等且單程被當來回，tfs 網址可精確重現。PRD 開放問題 1、3、4、5、9 照預設（合計 ≤9、含頭含尾以小時計、不另加確認、不做分組、趨勢不跨版本）；開放問題 2 依架構（不做後過濾）。PRD 與裁決衝突處依 ADR 增補 Decision 9。狀態 spec → build。

## dev-lead 實作查證紀錄（2026-10-28）

環境：Windows 11、Python 3.11（uv venv）、fast-flights 3.1.0、`sqlite3.sqlite_version` = **3.45.1**（≥ 3.26，RENAME 會改寫子表 FK 的語意成立，migration 0003 依「建 watch_new → 複製 → DROP watch → RENAME」順序）。

1. **tfs 屬性名與 base path**：fast-flights 3.1.0 `create_query(...)` 回傳 `Query`；`Query.params()` 回 `{"tfs", "hl", "curr"}`，`Query.to_str()` 為標準 base64（含 `+`、`/`、`=`，未 URL 編碼）。`Query.url()` 的 base 為 `https://www.google.com/travel/flights/search?tfs=`（未編碼）；抓取端 `fetch_flights_html` 用的是 `https://www.google.com/travel/flights` + params。查票連結採 `/travel/flights/search`，以 `urlencode` 編碼 `tfs`／`hl`／`curr`（`GoogleFlightsLinkBuilder`，只用既有的 `build_query`，**未新增 fast_flights import 名稱**，C-26 的 import 名單測試不需改）。golden（單程 TPE→NRT 2026-12-10、2 大 1 小、商務艙、BR、06–12）：`https://www.google.com/travel/flights/search?tfs=GiISCjIwMjYtMTItMTAyAkJSQAZIDGoFEgNUUEVyBRIDTlJUQgMBAQJIA5gBAg%3D%3D&hl=zh-TW&curr=TWD`。瀏覽器手動開 3 條連結（單程、多人、商務艙）驗收仍待總經理（C-42）。
2. **`airlines=None` 與 `[]`**：protobuf repeated 欄位，`FlightQuery(airlines=None)` 與 `airlines=[]` 序列化位元組完全相同（實測 `to_str()` 相等）；adapter 仍在空清單時傳 `None`（C-39 測試鎖定）。
3. **時段上界是否含該小時**：**本次 fixture 無法判定**。錄製條件 BR、06–12 時只回 2 筆（07:55、08:50）；BR 當日 TPE→NRT 另有 15:20 班次（2026-10-25 fixture），但沒有 12:00–12:59 的 BR 班次可觀察。文案因此只寫「去程 06–12 時」（整點、以 Google Flights 時段篩選為準），不宣稱到 12:59，也不寫「X 點前」。如要確認，需另一次不帶航空、06–12 的實查，看 12:35（CI）／12:50（GK、CX）是否出現。
4. **來回 payload 只含去程**：`tests/fixtures/fixture_roundtrip_TPE_NRT.json`（來回 12/10–12/15）18 筆行程，每筆第一段 `from_airport=TPE`、最後一段 `to_airport=NRT`，沒有回程航段；因此 `depart_time` 只代表去程第一段，與「時段只套去程」一致（測試 `test_round_trip_payload_lists_outbound_flights_only`）。
5. **`segment[8]` 午夜班次形狀**：錄到的樣本只有 `[h, m]`（例 `[7, 55]`）與 `[h]`（例到達 `[12]`、`[13]`、出發 `[15]`）。依上游 `fast_flights.parser._parse_time` 註解，Google 會省略為 0 的分量並以 `None` 代表前導 0，即 00:31 為 `[None, 31]`、00:00 可能為 `[]` 或 None。依 ADR Decision 4 這些形狀一律記 None（不計 malformed、不影響狀態），代價是午夜 00:xx 出發的班次不顯示出發時刻。測試涵蓋 `[7,55]`、`[7]`、`[]`、None、`[24,0]`、`["7",55]`、`[None,31]`。
6. **新錄 fixture**：`tests/fixtures/payload_TPE_NRT_BR_06_12.json`（2026-10-28 一次真實連線，TPE→NRT 2026-12-10 單程、BR、去程 06–12、1 成人、經濟艙、max_stops 不限）：itineraries=2、priced=2、皆為 BR 長榮航空，TWD 15,911（07:55）、17,172（08:50）。斷言 `depart_time` 落在 06:00–12:59。payload 內嵌的航空公司代碼表（`payload[7][1][1]`）共 50 家，作為對照表查證來源。
7. **資料源能力（FR-C7）**：人數、兒童、艙等、航空、去程時段皆以 Google Flights 查詢參數原生帶入（總經理 2026-10-28 實測價格差異：1 成人 6,202／2 成人 9,736／2 大 1 小 18,509／商務 20,904）；不做取回後過濾（Decision 6、9）；每個日期對仍是一次查詢，FR-B3 用量不變。

### 航空公司對照表（`domain/airlines.py`，41 家）

- 出處：Google Flights 結果頁內嵌的航空公司代碼與名稱表 `payload[7][1][1]`，兩份實錄：`payload_TPE_SHA.json`（2026-10-26，16 家）與 `payload_TPE_NRT_BR_06_12.json`（2026-10-28，50 家）；輔以 `fixture_roundtrip_TPE_NRT.json` 的行程代碼與中文名。查證人 dev-lead，日期 2026-10-28。
- 37 家代碼已出現在上述 Google 代碼表中（逐筆 `verified_note` 標 `GF-SHA`／`GF-NRT`）。
- **4 家未在任何實錄 payload 出現，標 `unverified (IATA code search pending)`：AK 亞洲航空、DL 達美航空、EK 阿聯酋航空、QR 卡達航空**（皆為 PRD 指名必列）。本輪網路只允許一次連線，未能連 IATA code search 頁；請 qa-reviewer 抽查時優先查這 4 筆並回填。
- 中文名以台灣慣用為準；Google 代碼表的名稱有差異者：TW 在 Google 為「泰赫航空」（本表用台灣慣用「德威航空」）、UO 為「香港快運航空」、NH 為「全日空航空」、TG 為「THAI」。代碼一致。
- 原草擬的 AE 華信、B7 立榮因不在任何實錄 payload 中而未收錄；改收 ZE 易斯達、HB 大灣區、VZ 泰越捷（皆在 GF-NRT 表內）。
- qa 抽查（C-41：≥10 筆或 20%，取多者 → ≥10 筆）結果待 qa-reviewer 填入。

### 正式 DB 副本遷移實測

來源 `apps/flight-deals/data/flight-deals.db`（以 sqlite backup API 唯讀複製，未動正式檔）→ `scratchpad/mig3/flight-deals.db`，`FLIGHT_DEALS_DB_PATH` 指向副本、未啟動排程：v2 → v3；遷移前後筆數 watch 3／scan_run 8／price_observation 8／alert_state 0／notification 4／notification_item 2／source_health 1／app_setting 7／scheduler_event 0 全相同；`foreign_key_check` 空、`integrity_check` ok、`sqlite_master` 無 `watch_new`、四張子表 DDL 仍 `REFERENCES watch(id)`；舊欄位逐欄相等、新欄位為預設（1 成人、0 兒童、economy、不限）；revision 不變；2 筆 item_key 補為 `price:2:r1:live:...`；產生 `flight-deals.pre-v3.db` 備份。以副本啟動（不排程）渲染 `/`、`/watches/1..3`、`/watches/2/edit`、`/notifications`、`/watches/new` 皆 200，價格旁顯示「1 人總價」與「經濟艙」。
- 2026-10-28 qa-reviewer → 總經理：FD-5 第一輪 **PASS**（C-37～C-42 全過；Codex 兩項擋件理由複核後降級：INTEGER affinity 放行實數列 medium、children 0～8 依 ADR 正確）。航空公司抽查 20 筆（含 AK／DL／EK／QR、8 家 LCC、2 家數字代碼）依記憶＋Codex 交叉確認全部一致，無錯置。
- 2026-10-28 總經理實測（阻擋 commit 的新發現）：(1) `google_payload.py` 沿襲上游只讀 `payload[3][0]`「其他航班」，漏掉 `payload[2][0]`「最佳航班」，後者常更便宜（TPE→NRT 經濟 1 人 best 4,868 vs other 6,202；SHA fixture best 4,633 vs 記錄的 12,655）→ 自 FD-1 起最低價偏高，交 dev-lead 修為兩段合併去重。(2) 來回＋商務艙＋多人的查詢 Google 不在 HTML 內嵌結果（兩段皆 None），瀏覽器開同一 tfs 連結有結果（非同步載入）→ 新狀態 `no_embedded_results`，不計斷路器。(3) tfs 查票連結實開：顯示「3 位乘客的價格」、商務艙、12/10–12/15、長榮／華航 06–12 時班次（含 12:35，上界含該小時）。(4) API 驗證：合計 10 人、6 家航空、時段反向各回正確訊息。
- 2026-10-28 總經理代跑 C-41 live smoke：`uv run pytest -m live tests/test_live_smoke.py -k airline` → 3 passed（BR、IT、7C 三家代碼 fast-flights 皆接受）。ADR-0002 FD-5 增補補上 Decision 9a（兩段結果區段合併、`no_embedded_results` 狀態）與 C-39 修訂。

## dev-lead 第二批修正（2026-10-28，總經理實測 best 區段漏讀＋qa-reviewer 建議）

1. **best 區段**：`google_payload.parse_payload` 改為同時讀 `payload[2][0]`（最佳航班）與 `payload[3][0]`（其他航班），best 在前合併；去重 key＝航空公司碼＋各航段出發／到達機場碼＋各航段出發時刻＋價格區塊（`itinerary_key`）；形狀無法辨識者不去重。`ParseStats` 新增 `best`、`other`（兩段去重前的原始筆數），`itineraries` 為合併去重後筆數。`payload[2]` 為寬鬆區段（None／非 list／空 → 視為缺席）；`payload[3]` 沿用 FD-3 形狀檢查，但整段 None 也視為缺席。
   - 新契約數字（`payload_TPE_SHA.json`）：itineraries=9、priced=7、unpriced=2、malformed=0、best=5、other=4；金額 463300、463300、622100、783300、882100、1265500、1476300；最低 463300（中國南方 CZ，TPE→SZX→SHA 13:40，時長 130＋135）。兩筆 CZ 4,633 航線不同（經 SZX／經 CAN），不視為重複。
   - `payload_TPE_NRT_BR_06_12.json`（本批 2026-10-28 實錄）：**該次回應 `payload[2]` 整段為 None**，只有 other 段 2 筆（15,911／17,172）；與總經理同條件實測（best=[11348,12721,15911]、other=[12456,17172,24738]）不同，表示兩段的分配每次請求不同。未重錄（本輪連線額度已用）；測試以 docstring 記錄此差異。
   - `fixture_roundtrip_TPE_NRT.json` 是 fast-flights 舊 dataclass 形狀（只供 FixtureSource），不經 payload parser，不受影響、未改。
   - **影響**：FD-1 起所有 google_flights 價格紀錄可能偏高（只取 other 段）；既有歷史不回溯修正。
2. **兩段皆缺席**：`no_data`，`SourceResult.extra={"reason": "no_embedded_results"}`，寫入 `query_results` 的 pair 與 try（`reason`）；不計斷路器、不發維運告警、監看不轉 stale、健康頁不轉異常。詳情的日期組合狀態與列表（`w.no_embedded_note`）顯示「Google 未在頁面內嵌此查詢的結果（多為來回＋商務艙＋多人），無法自動查價；請用查票連結人工查看」。列表以 `list_watches_with_last_results` 一次查詢帶出最新完成掃描結果，list_page SQL 次數仍為 1＋N（C-34）。注意：真正無航班且無 errorHasStatus 的頁面也會落在此狀態（兩者在 HTML 上無法區分）。
3. **qa 建議**：migration 0003 的 adults／children／dep_hour_from／dep_hour_to 加 `typeof(...) = 'integer'`（1.5、0.5、6.5、12.5 被拒，有測試；文字 "2" 會被 INTEGER affinity 轉成整數，屬可接受）；PUT 缺鍵時沿用既有人數、艙等、航空、時段（不升 revision，有測試）；AK 中文名改「馬來西亞亞洲航空」、NH 改「全日空航空」、AK／DL／EK／QR 的 verified_note 改為「qa-reviewer 依記憶＋Codex 官方資料交叉確認 2026-10-28」；`index.html`、`watch_form.html` 移除「經濟艙」fallback 與 `replace("（")`，`trip_view` 新增 `pax_short`（「2 大 1 小總價」）。
4. **正式 DB 注意**：`apps/flight-deals/data/flight-deals.db` 已被 8795 服務以**第一批的 0003**（無 typeof CHECK）升到 v3（4 個 watch，含監看 4：2 大 1 小商務 BR,CI 06–12），備份 `flight-deals.pre-v3.db`（v2，3 個 watch）。schema_version 已是 3，新版 0003 不會再套用；正式 DB 的 watch 表缺 typeof CHECK（應用層驗證仍擋非整數）。如要一致，需由總經理決定：從 pre-v3 備份還原後重跑（會失去監看 4 與其後資料），或接受差異，或另開 0004 重建。副本實測：以 pre-v3 備份（v2）複製到 scratchpad `mig3/` 套用新版 0003：各表筆數不變（watch 3／scan_run 8／price_observation 8／alert_state 0／notification 4／notification_item 2／source_health 1／app_setting 7／scheduler_event 0）、`foreign_key_check` 空、`integrity_check` ok、無 `watch_new`、子表 FK 正確、舊欄逐欄相等、item_key 補 `r1`、schema 含 typeof、`adults=1.5` 被拒。另以正式 DB（v3）副本開頁面 `/`、`/watches/1..3`、編輯、通知、新增、設定皆 200。
- 2026-10-28 dev-lead → qa-reviewer：第二批修畢（兩段合併去重、`no_embedded_results`、typeof CHECK、PUT 缺鍵沿用、AK／NH 名稱、樣板 fallback 移除；592 測試）。總經理裁示：CEO 本機正式 DB 已先以第一版 0003 升到 v3、缺 typeof CHECK，**接受差異**（應用層驗證有擋、資料為測試資料），日後若需一致再開 0004。
- 2026-10-28 總經理代跑 e2e（第二批後重啟服務）：監看 3（TPE→SHA）立即查價後最低價由 7,842 降為 **4,635**（中國南方、出發時刻 13:40 有值）、列表顯示「↓ TWD 3,207」；監看 4（來回商務 2 大 1 小）立即查價 → scan_run `ok`、日期組合 `no_data`／`no_embedded_results`、`consecutive_failed_scans` 0、斷路器 closed，列表顯示「Google 未在頁面內嵌此查詢的結果…請用查票連結人工查看」；列表條件欄「商務艙・2 大 1 小總價／長榮、華航｜去程 06–12 時」。
- 2026-10-28 qa-reviewer → 總經理：第二批 delta 複審 **PASS**（Codex 亦無阻擋）。3 medium：`payload[3]` 整段 None 放寬需限縮（總經理以實錄確認形狀為整段 None，裁定限縮為兩段皆 None 才算，ADR 9a 已改）；去重鍵出發時刻正規化與反例測試（交 dev-lead 收尾）；`no_embedded_results` 的健康頁比例提示（單一監看連續 3 輪、或 24 小時內占比 ≥50% 且 ≥10 筆）列入後續待辦 FD-6。
- 2026-10-28 dev-lead → 總經理：收尾小批完成（`_section` 限縮：payload[3] 整段 None 或 [None] 才算無資料，其餘形狀 blocked；去重鍵出發時刻正規化；反例測試；602 測試）。總經理：狀態 → done，待 CEO 驗收。待辦 FD-6：`no_embedded_results` 健康頁比例提示、表單對「來回＋商務＋多人」的靜態提示、歷史價格偏高不回溯（已知）。
