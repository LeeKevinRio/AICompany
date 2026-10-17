# PLAN_OUTPUT_SURFACES／SURFACE_PERMISSIONS 初版值與頁面歸屬（product-manager）

- 審查者：product-manager（只讀，未修改檔案）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## Phase 4 版面確認：PLAN_OUTPUT_SURFACES／SURFACE_PERMISSIONS 初版值與頁面歸屬（product-manager）

> 本報告只讀不改。以下數值都是「建議值」，等 CEO 回覆 #10、#16 以及風控確認後才定案。
> 標示慣例：〔事實〕是我這次讀到的檔案內容；〔推論〕是我的判斷。

---

## 一、結論

**做完了，但有一個取捨要 CEO 與風控拍板。** 建議值如下。

1. **`PLAN_OUTPUT_SURFACES` 建議 = {first_layer, symbol_detail, api}。** 比 tech-architect 草案的五項少了 `alert`、`export`。
   - 理由：新 PRD 沒有任何功能把建議放進推播或匯出。〔事實：PRD §2 L64 與 §3.2 L114 把「分享、匯出建議給他人」列為範圍外；NP-B3a 匯出的只有庫存；AC-X1b-2 的推播內容待 #16，PV-51 現行條文是「不帶」。〕
   - 重要的連鎖：如果 `alert`、`export` 留在這個集合裡，個股展望要等這兩格的伴隨揭露字面都核可，plan 才能用它（r2' A-26 第 2b 點）。推播放不下徽章、PV-45 固定句、PA-4、區間與 n，所以這兩格實際上不會被核可。〔推論〕結果是個股展望在「優於基準」之後仍然永遠對 plan 不可用。這遠超出 D-20 ③ 原意（只管「優於基準之前」）。
   - 這是縮窄 D-20 ① 的初版文字，要送風控單項確認。備選方案（維持五項）與後果見五之 2。
2. **適用欄位**：除了 `position_action`、`reasons`、`pending_triggers`，建議再列入 `add_conditions`、`entry_conditions`、`outlook_refs`。
   - 依據：ADR-0027 FL-43（L656）把「各項 conditions」列入標籤不變性的輸出；ADR-0025 D-4.4／D-4.5 的趨勢條件與候選條件都含 `category=outlook` 的 `Condition`。
   - `levels`、`risk_from_close`、`pnl_vs_cost`、`quantity_range`、`execution_caveats` 不由展望推導，不歸 D-20 管。我另列在 2.3，只作 PM 對顯示面的建議。
3. **`SURFACE_PERMISSIONS` v1 只列有實際用途的格子**（見 2.2）。
   - 大盤與族群各開 `first_layer`、`api`；個股開 `symbol_detail`、`api`。
   - 個股 `first_layer` 是「優於基準，加伴隨揭露核可，再送審」才生效的條件格，v1 實際不生效。
   - 所有 scope 的 `alert`、`export` 在 v1 一律不許可。
   - 這比 tech-architect r2 草案（大盤、族群五面都許可）窄，與風控 B-3 第 3 點「揭露字面未核可前維持不許可」一致。
4. **頁面歸屬**：不新增 DisplaySurface 值。族群列表與族群詳細頁歸 `first_layer`（回答 r2' B'-2），細節見三。
5. **我發現的問題**：
   - 我自己 PRD 的 NP-A3 第 (5) 項（持有時 5 日展望偏空進「最需要處理」）與 D-19、D-20 衝突，必須改。〔事實：PRD L631〕
   - 「首頁決策卡」在現行程式裡不在首頁。〔事實：`DecisionCard` 在 `app/position/[symbol]/page.tsx` L221，首頁 `app/page.tsx` 沒有〕
   - 「首層」一詞在 PRD、視覺規範（頁面內的展開層級）與 ADR（`first_layer` 顯示面）有兩種意思，要統一。

**各部門回報**
- product-manager（本人）：讀了兩份 tech-architect 提案、風控 r2 附件 B 單項確認、PRD 全文、視覺規範第 0 到 5 節與第 8、9 節、事先宣告 D-19／D-20（現行檔 L884、L885）、ADR-0025 D-4、ADR-0027 L415 到 440、決策包 #10、#16、前端 `page.tsx` 與後端路由清單。
- 其他部門：本次未參與。這是規格確認，沒有程式碼，所以 qa-reviewer 與 Codex 不適用。
- 風控：本報告涉及使用者面的顯示配置，需要風控單項確認（五之 2、4）。

**驗證**
- 〔事實〕ADR-0027 本文目前還沒有 `DisplaySurface`、`SURFACE_PERMISSIONS`、D-20（grep 無命中）。這些只存在於 r2／r2' 提案，所以下表是「提案層」的確認，不是對已生效 ADR 的確認。
- 〔事實〕後端路由清單裡目前沒有 outlook、forecast、plan 相關的 route，Phase 4 的歸屬都是預定位置。
- 〔事實〕事先宣告現行檔已含 v0.9 的 V9-03；D-19／D-20 在 L884／L885，與提案引用的 v0.8 行號（L849／L850）不同。
- 我沒有讀 `.env`，也沒有碰 `*.db`。沒有執行任何程式。

---

## 二、允許表

### 2.0 讀法與前提

- 「允許」：該欄位可出現在該顯示面，且該顯示面屬於 plan 一次判定時要一起考慮的集合。「禁止」：不得出現。「有條件」：括號內寫條件。
- **`PLAN_OUTPUT_SURFACES` = 把所有 2.1 欄位允許出現的顯示面取聯集。** 每個 (symbol, T) 只有一份 plan（D-20 ②），所以集合是整份 plan 一次判定的最嚴格範圍。欄位層級的「禁止」是額外的渲染限制，由前端契約測試釘住，不改變可用性的計算。
- 〔事實〕v0 政策表只引用同一檔個股的 `symbol|h5` claim（ADR-0027 D-11.4 第 8 點，L428）。所以 plan 只受個股 scope 的許可格影響，大盤與族群格與 plan 無關。
- `api` 欄的「允許」都以該端點登記了非空 `SERVES`（含 `api` 以外的值）為前提（r2' A-26 第 2 點）。

### 2.1 受 D-20 管轄的欄位（建議值：集合 = {first_layer, symbol_detail, api}）

| plan 欄位 | first_layer | symbol_detail | alert | export | api | PRD 驗收條件出處 |
|---|---|---|---|---|---|---|
| `position_action` | 允許（最小形式：一句結論加原因加連結，且附資料日期；保留容量，Phase 4 是否真的渲染由版面決定） | 允許 | 禁止 | 禁止 | 允許 | AC-D4D-1、AC-D4D-5（詳細頁）；AC-A3-1／A3-2（最需要處理）；AC-D4-1～D4-6；PV-52 |
| `reasons` | 允許（只放主要原因的狀態句） | 允許 | 禁止 | 禁止 | 允許 | AC-D4-3、AC-D4D-1；D-19「理由只能寫狀態、不能寫方向」 |
| `pending_triggers` | 禁止（詳細頁才放） | 允許 | 禁止 | 禁止 | 允許 | AC-D4-2（說明哪幾項未滿足）；ADR-0025 D-4.5；D-19（下架或暫停時不得列成「等待中」） |
| `add_conditions`（建議新增） | 禁止 | 允許 | 禁止 | 禁止 | 允許 | AC-D4-2、AC-D4-3、AC-D4-4；FL-43 的「各項 conditions」 |
| `entry_conditions`（建議新增） | 禁止 | 允許 | 禁止 | 禁止 | 允許 | AC-D4-5；FL-43 |
| `outlook_refs`（建議新增，內部指標） | 禁止 | 允許（只在 `evaluated` 時有值） | 禁止 | 禁止 | 允許（同左） | ADR-0027 D-11.4 第 10 點（L430）；AC-A2-9 |

「最需要處理」的排序與成員、提醒 payload、`plan_record` 的顯示欄位、API 回應，也算 plan 衍生輸出，適用同一份集合（FL-43，L656）。

### 2.2 `SURFACE_PERMISSIONS` v1 初版（建議值）

鍵為 (scope_kind, surface)，只在 `display_state = shown` 時查。**fail-closed：沒列的格子不許可。**

| scope \ surface | first_layer | symbol_detail | alert | export | api |
|---|---|---|---|---|---|
| 大盤 | 許可 | 不列入（v1 無用途） | 不列入 | 不列入 | 許可 |
| 族群（150 閘門已由 `gated` 處理） | 許可 | 不列入 | 不列入 | 不列入 | 許可 |
| 個股 | 條件格：需 `better_than_baseline` 且伴隨揭露全核可，再送審才生效。v1 不生效 | 許可 | 不列入 | 不列入 | 許可 |

- 每一格都要登記 `required_disclosures`（r2' A-26 第 2b 點）。個股另加 PA-4；「優於基準」時另加 D-2 開盤基準句與 D-4 區間、n、期間。
- 與 tech-architect r2 草案的差異：
  - 大盤、族群的 `alert`、`export` 由「許可」改為「不列入」。
  - 個股的 `alert`、`export` 由「需要 BTB」改為「不列入」。
  - 兩處的依據都是 v1 沒有對應功能，也沒有核可的揭露字面。
- 之後任何格子要開，都要送風控並升 `policy_version`（風控 B-3 第 4 點）。

### 2.3 不受 D-20 管轄的 plan 欄位（PM 對顯示面的建議，僅供參考）

這些欄位不經 `outlook_view`，限制來自 PV-51、PRD §2 與 AV-15。

| plan 欄位 | first_layer | symbol_detail | alert | export | api | PRD 出處 |
|---|---|---|---|---|---|---|
| `levels` | 禁止（只有「已越過失效價」狀態句可入最需要處理，並須附 `execution_caveats`） | 允許 | 禁止 | 禁止 | 允許 | AC-D4D-1、AC-D4D-4、AC-E1-6 |
| `risk_from_close` | 禁止 | 允許 | 禁止 | 禁止 | 允許 | AC-D4D-2；PV-51（金額與占比不外送） |
| `pnl_vs_cost`（僅持有） | 禁止（首頁沿用既有庫存彙總，不是這個物件） | 允許 | 禁止 | 禁止 | 允許（本機） | AC-D4D-2；PV-51、AV-9；AC-B6-2 |
| `quantity_range` | 禁止 | 允許 | 禁止 | 禁止 | 允許 | PV-51（股數不外送）；AC-B6-3 |
| `execution_caveats` | 有條件（凡出現失效價或停損類價位的畫面都必附） | 允許 | 禁止 | 禁止 | 允許（與 `levels` 同一回應） | AC-D4D-3、AC-E1-7；AV-15 |

---

## 三、頁面歸屬

「顯示面」按**頁面或載體**判定，不按頁面內的展開層級判定。個股詳細頁整頁（決策卡、行動計畫卡、價位面板、展開區）都屬 `symbol_detail`。

| 頁面／元件 | 現況〔事實〕 | Phase 4 預定 | DisplaySurface | 可出現的展望／plan 內容 |
|---|---|---|---|---|
| 市場總覽 `/`：市場天氣區塊（目前盤勢與大盤 3、5 日展望） | 首頁現有摘要卡、持倉表、風險儀表、警示列、族群動能卡 | NP-A1／A2、視覺規範 5.4 | `first_layer` | 大盤展望標籤，須附驗證徽章；目前盤勢（已發生）不經展望閘門。AC-A1-1、AC-A2D-1／1b／1c／1d |
| 市場總覽：「最需要處理」清單 | 無 | NP-A3 | `first_layer` | 只放事件類（資料缺口、越過失效價、風險上限、警示）。不得引用個股展望標籤，也不得有「該先賣誰」措辭 |
| 首頁持倉表、摘要卡、風險儀表 | 不含展望或 plan | 不變 | `first_layer`（若日後加「動作」欄） | 若加，只能放 `position_action` 的最小形式，不放展望標籤 |
| 族群列表（現為首頁 `SectorMomentumCard`，Phase 4 為獨立列表） | 族群動能卡 | NP-C4 | `first_layer`（指定歸屬，不新增值） | 150 閘門前只顯示「未驗證（n／150）」；通過後不得依展望排序或篩選。AC-C4-3、AC-C4-7 |
| 族群詳細頁 | 尚不存在 | NP-C5 | `first_layer`（指定歸屬） | 族群 3、5 日展望（AC-C5-3）。**成員列不得顯示個股展望或 plan 結論**（見驗收條件草案 AC-S-7） |
| 個股詳細頁 `/position/[symbol]`（決策卡、行動計畫卡、價位面板、展望區、PA-4 說明） | `DecisionCard`、`AdviceCardView`、價位面板現已在此頁 | NP-D4／E1～E5、視覺規範 5.6 | `symbol_detail` | 2.1 與 2.3 全部欄位；個股 3、5 日展望只在此頁（AC-D4D-6） |
| 預測紀錄清單 `ForecastLedgerList`（視覺規範 9.2 問我放哪一頁） | 尚不存在 | 建議**不設跨 scope 的總頁**，改為：大盤紀錄放市場總覽展開區、族群紀錄放族群詳細頁、個股紀錄只放個股詳細頁 | 依 scope 分屬 `first_layer`／`first_layer`／`symbol_detail` | 個股紀錄的標籤只能在 `symbol_detail`（R-5）。作廢與逾時列留在清單（AC-V5-3b／3d） |
| 警示與推播（`alert`）：提醒事件列表、外送推播 | 首頁 `AlertStatusStrip`、`alerts/notify.py` | NP-X1b | `alert`；首頁警示列同時屬 `alert` 與 `first_layer` | v1 不含任何 plan 或展望內容。推播只能是「有 N 則新評估」類（PV-51、#16 未回覆即「不帶」） |
| CSV 匯出（`export`）：現有範本下載、NP-B3a 庫存匯出 | `GET /api/positions/template.csv` | NP-B3a | `export` | 只含庫存資料，不含 plan 欄位與展望標籤（AC-B3a-1／2；PRD §2） |
| 對外 API（`api`） | 現有 advice、portfolio 等 route 沒有 `OutlookView` 衍生欄位 | Phase 3 起新增 | `api`（載體），`consumer = SERVES ∪ {api}` | 建議登記：個股展望與 plan 端點 `SERVES={symbol_detail}`；大盤與族群展望端點 `SERVES={first_layer}`；`POST /api/outlook/symbols/{symbol}` 與 A-36 一致 |
| `/positions`（庫存頁）、`/playbook`、`/backtest`、`/settings` | 不含展望 | 不變 | **無歸屬**，fail-closed | 不得渲染展望標籤、天氣或 plan 結論（r2' A-26 第 2a 點） |

**歸屬說明**
- 族群頁歸 `first_layer` 的理由：
  - 大盤與族群的許可格在 `first_layer` 與 `api` 相同，不新增值不改變任何行為；
  - 新增值要修訂列舉並送審，成本高、收益是零。
- 缺點是 `first_layer` 的語意被放寬成「跨標的總覽類頁面」，ADR 與 PRD 的定義文字要同步。
- 預測紀錄清單拆開，是因為 A-26 規定端點登記單一 `SERVES`。若同一端點同時服務 `first_layer` 與 `symbol_detail`，個股紀錄會被首層的許可格擋掉。〔推論〕

---

## 四、一致性檢查

| 對照項 | 結果 | 說明 |
|---|---|---|
| **#10**（決策包建議：選 (a)；個股方向先只放詳細頁，首層天氣先放大盤） | 一致 | 〔事實〕PRD §4 把 #10 定義為顯示閘門 (a)／(b)；「個股只放詳細頁、大盤可上首層」是風控 R-5 的裁定，不隨 #10 改變（PRD §4 #10 列）。決策包把兩者合寫在 #10 的建議欄，所以本表的格子與兩者都相容 |
| 若 CEO 選 (b) 或「全程隱藏」 | 表格不變 | 只改變 `display_state` 何時進入 `shown`（ADR-0027 L417，#10 作為參數注入）。全程隱藏時大盤首層也看不到展望，AC-A2D-1b 走 (ii) 路徑 |
| 若 CEO 要個股也上首層 | 需風控重審 | 這不是決策包的選項，等於推翻 R-5。就算把 (symbol, first_layer) 改成 `shown` 即許可，只要 `alert`、`export` 還在集合裡，plan 仍然不可用。這再次顯示集合成員才是關鍵 |
| **#16**（決策包建議：不帶） | 一致 | 〔事實〕PV-51：推播維持較嚴禁用清單，帶建議須 CEO 另行同意；PRD §4 #16 列寫明未回覆即「不帶」。所以 `alert` 的 plan 欄位全部禁止 |
| 若 CEO 答 #16「帶」 | 需改配置 | `alert` 要加入集合並升 `policy_version`；個股 `alert` 格要伴隨揭露字面全核可，推播長度放得下的字面要重寫；內容仍不得含股數、成本（AV-9）。個股展望對 plan 的可用性會再次綁到推播字面核可 |
| **PV-51** | 一致 | `pnl_vs_cost`、`quantity_range`、`risk_from_close` 在 `alert` 與 `export` 一律禁止；`api` 為本機回應，但仍須通過 AC-B6-2 的 HTTP client spy 檢查 |
| **D-19**（不能顯示，就不能引用） | 一致，但有一處要補 | plan 只經 `outlook_view` 取展望，理由只寫狀態，`pending_triggers` 不列「等待中」。**缺口**：`add_conditions`／`entry_conditions` 裡 `category=outlook` 的 `Condition` 帶 `observed`、`threshold`，ADR 目前沒寫 `unavailable` 時這兩欄必須為 None，否則方向可能從條件欄位漏出。建議由 tech-architect 補一句，並納入 FL-43 |
| **D-20 ①** 靜態列舉、初版待 PM 確認 | 有調整 | 事先宣告 D-20 ① 寫的初版對應包含提醒與匯出。我建議移除，需風控單項確認，quant 登記時同步改文字 |
| **D-20 ②** 每個 (symbol, T) 一份 plan | 一致 | 集合是所有欄位的聯集，欄位層級差異只是渲染限制 |
| **D-20 ③** 個股展望在「優於基準」前對 plan 不可用 | 一致 | `first_layer` 在集合內，且 (symbol, first_layer) 需 BTB，所以 BTB 前個股展望對 plan 一律是 `surface_not_permitted`。AC-D4D-6 同向 |
| **D-20 ⑤** 兩面後果 | 一致 | 不改變：`consider`、`add_conditional` 長期無法成立；序位 7 第一項與 `avoid` 的展望項也不會觸發；畫面只寫「5 日展望目前不可用（原因），本判斷未納入」 |
| **PV-52** 首層可見驗證狀態、資料日期、證據不足 | 一致，要加驗收 | `position_action`、`reasons` 若在 `first_layer` 渲染，每列必須帶資料日期與「本判斷未納入 5 日展望」類狀態句，否則使用者會以為結論含展望。見 AC-S-2 |
| **PA-9／PV-40**（族群不得依展望排序篩選） | 一致 | 歸屬為 `first_layer` 不改變排序禁令；禁令由前端測試釘住（視覺規範 5.5） |
| **PRD NP-A3 第 (5) 項** | **衝突，需修訂** | 「持有時 5 日展望為偏空，進最需要處理」會讓個股展望方向透過首層清單出現，違反 D-19、D-20 ③ 與 R-5。我會刪除或改寫該項，寫變更紀錄並通知下游。這次未修改，等授權 |

---

## 五、待決事項

1. **CEO 加風控：plan 是否出現在 `first_layer`？（本次最大取捨，不屬 PM 可定）**
   - 方案 A（建議）：保留 `first_layer` 在集合內。後果：維持 D-20 ③，個股展望在「優於基準」之前對 plan 不可用（A-35 的兩面後果不變）。
   - 方案 B：plan 不上首層，集合改為 {symbol_detail, api}。後果：個股展望在 `shown`（尚未驗證）時就能進政策表，未驗證的標籤會間接影響行動結論（需 D-18 同處附驗證狀態）。D-20 ⑤ 允許「送審後調整顯示面配置」，但這是放寬，須風控審。
   - 我建議 A，理由是 #10 未回覆，且風控明示不得放寬 D-20。
2. **風控單項確認**：
   - (a) 集合縮窄為 {first_layer, symbol_detail, api}（本報告建議）。
   - (b) 備選：維持五項。後果是個股展望永遠不可用，除非 `alert`、`export` 的伴隨揭露字面被核可，需 CEO 知悉。
   - (c) 族群列表與詳細頁歸 `first_layer`。
   - (d) 預測紀錄清單拆分放置。
   - (e) 個股詳細頁的 plan 卡與展望區並列時，是否需要額外的並列揭露（Q-10(c) 仍待風控）。
3. **CEO 待回覆**：#10（影響見四）、#16（影響見四）。兩者都未回覆時，本報告採 PV-51 現行條文與 R-5 的保守讀法。
4. **tech-architect**：
   - 在 ADR 補 `unavailable` 時 outlook 類 `Condition` 的 `observed`、`threshold` 必為 None。
   - 紀錄清單端點的 `SERVES` 如何依 scope 拆分。
   - 增設契約測試：`alert`、`export` 渲染路徑沒有讀取 2.1 欄位的路徑（縮窄集合的前提）。
   - 統一 `first_layer` 的定義文字，避免與頁面內展開層級混淆。
5. **PM 自辦（需 coordinator 授權後執行）**：
   - 修訂 NP-A3 第 (5) 項，寫變更紀錄，通知 qa-reviewer、qa-automation、qa-e2e、tech-architect、quant-researcher、risk-compliance-officer、creative-lead、art-lead、frontend-engineer。
   - 新增下列驗收條件草案。

   | 編號 | Given／When／Then |
   |---|---|
   | AC-S-1 | Given `PLAN_OUTPUT_SURFACES` 與 `SURFACE_PERMISSIONS` 已登記；When 檢查政策表 v0 與 ADR；Then 值與本報告 2.1、2.2 一致，變更須升 `policy_version` 並送風控 |
   | AC-S-2 | Given 個股展望尚未「優於基準」；When 開啟個股詳細頁與任何會渲染 plan 的首層列；Then `reasons` 只寫「5 日展望目前不可用（原因），本判斷未納入」，不含方向；首層列帶資料日期 |
   | AC-S-3 | Given #16 未回覆或為「不帶」；When 任何提醒或推播觸發；Then 內容不含 2.1、2.3 任一欄位，只有「有 N 則新評估」類 |
   | AC-S-4 | Given 任何 CSV 匯出；When 檢查檔案；Then 不含 plan 欄位與展望標籤 |
   | AC-S-5 | Given 全部對外 route；When 列舉；Then 含展望衍生欄位的 route 都有非空 `SERVES`，沒有登記者回 `surface_not_permitted` |
   | AC-S-6 | Given `/positions`、`/playbook`、`/backtest`、`/settings`；When 掃描；Then 沒有展望標籤、天氣或 plan 結論 |
   | AC-S-7 | Given 族群詳細頁的成員列；When 檢視；Then 沒有個股展望標籤與 plan 結論 |
   | AC-S-8 | Given 個股的預測紀錄；When 檢視；Then 只出現在個股詳細頁，不出現在任何首層頁面 |
   | AC-S-9 | Given 「最需要處理」清單；When 檢視；Then 不引用個股 5 日展望 |

6. **creative-lead**：`surface_not_permitted` 字面（R5-06 重送）仍是 D_v 的卡點。若日後開放 `alert`／`export`，需另起草推播與匯出的伴隨揭露字面。
7. **quant**：D-20 ① 的初版對應文字，在風控確認縮窄後同步修訂；D-19 補 `Condition.observed` 的處理。
8. **art-lead**：預測紀錄清單按 scope 分散放置後，視覺規範 4.3 與 5.4 的版位需更新。

**相關檔案**
- `/home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028修訂提案A22至A41-tech-architect.md`（L148 到 L170，A-26）
- `/home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028修訂提案r2prime-tech-architect.md`（A-26、B'-2）
- `/home/user/AICompany/work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md`（B-3）
- `/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`（D-19 L884、D-20 L885）
- `/home/user/AICompany/work/stock-desk-新定位-PRD-2026-10-16.md`（§2、§3.2、§4、NP-A3 L629 到 L634、NP-C4、NP-D4／E1、NP-X1b）
- `/home/user/AICompany/work/stock-desk-新定位-視覺規範-2026-10-16.md`（§5.4 到 §5.6、§9.2）
- `/home/user/AICompany/work/dispatch/2026-10-15-決策包-ADR-0025與新定位.md`（#10 L41、#16 L47）
- `/home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md`（D-4，L256 到 L314）
- `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`（L415 到 L440、L656）
