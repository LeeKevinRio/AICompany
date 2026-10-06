# ADR-0021：stock-desk 規則與警示欄位的可評估性不變式

- 狀態：proposed
- 日期：2026-10-06
- 決策者：tech-architect
- 提案來源：ADR-0020 第 4 題（beta）；tech-architect 受 ADR-0020 另開單評估後的裁示
- 適用範圍：僅 product/stock-desk 產品線
- 編號說明：落檔時 `docs/adr/` 目錄下 0020 為最後一份，查無 0021；repo 內（排除 `.git/`）亦無 ADR-0021 或 `0021-` 的引用，故使用 0021。
- 來源與版本：本檔為 tech-architect 2026-10-06 裁示（「規則與警示欄位的可評估性不變式（ADR-0021 草案要點）」，原文落於 scratchpad `adr0021-architect-ruling.md`）的落檔，B 類轉錄，僅做格式調整，技術內容未增補、結論未改動。
  - 「評估摘要」「查證結果」「方案比較」「Decision」「Consequences」「重啟條件」「對實作的約束」K-1～K-11、「測試要求」T-1～T-7、「需風控審字面」W-1～W-5、「相關檔案」「交接」皆逐字取自該裁示。
  - 檔內所有 `檔案:行號`（例：`engine.py` L146–L149、`store.py` L283–L307、`format.ts` L454–L475）、函式名、常數名、數字（例：540 日 bars、+288 服務呼叫／日、最壞約 20 秒）均為 tech-architect 所述；tech-writer 落檔時**未重新對 code 驗證**。行號會隨 commit 漂移，引用時以原文定位。
  - 2026-10-06 依風控審查結果增補狀態註記（B 類；來源：`work/reviews/2026-10-06-ADR-0021-警示欄位可評估性-字面-風控審查.md`）。
  - 落檔時的快照：分支 `product/stock-desk`，HEAD `28cb65ed1ce14f98beee0dc0c2d40b8550578e40`（tech-writer 於落檔時讀取 `.git/refs/heads/product/stock-desk`）。此為快照，之後 HEAD 可能前進。
  - 此為 proposed 狀態；依 ADR-0001，生效前的內容可修訂，生效後不得原地改寫決策。
  - W-1～W-4 已核可（2026-10-06）、W-5 退回重寫（見「需風控審字面」段與風控審查紀錄）。

---

## 關聯

- 了結：ADR-0020 第 4 題與 K-8（tech-writer 已在 ADR-0020 該兩處加交叉引用）。
- 依據：ADR-0010 D-1、R-6、L133–L134。
- 與 ADR-0018 的關係：K-6（計數測試）見 Consequences 與 T-6；ADR-0018 K-6 計數測試須分開計 index resolver。
- 借鑑：ADR-0017 L26（已記過同一教訓：讀取時重新驗證舊資料）。
- 與 ADR-0004（accepted）不衝突：ADR-0004 L178「build_context 為規則詞彙來源」不變。
- 日後路徑 (a′)：需另開新 ADR，並先修訂 ADR-0010，對照 ADR-0012 C-11／C-13／T-4（見「重啟條件」）。

---

## 評估摘要

採用 **(b) 的安全版 b′**，否決 (a) 與 (c)。

- 否決 (a)：每次 /api/advice 多一次同步、關鍵路徑上的指數抓取，違反 ADR-0010 D-1「整書 0 網路、只有本標的即時」精神，R-6 固定順序多出第三段；alerts 每 tick 服務呼叫加倍，與 US 備援、FX 備援共用 yfinance throttle。成本換來零已知消費者（default.yaml 無引用、使用者規則不可查）。日後若要做，改走 (a′)「benchmark cache-only 讀取＋預熱」並另開 ADR。
- 否決 (c)：自相矛盾——維持可選又要守門「欄位表不得宣告無法評估欄位」，現況必紅；UI 留一個明知永不觸發的選項不誠實。
- 採用 b′：分開「可讀詞彙」與「可新建詞彙」。KNOWN_FIELDS 與 build_context 保留 beta.value（讀既有資料不出錯、skip 訊息有標籤）；advice YAML loader 與警示新建／修改改用各自「可評估子集」驗證，beta.value 不在其中。**絕不能直接從 KNOWN_FIELDS 刪 beta.value**（關鍵發現 1）。
- 同類一併處理：position.weight、position.unrealized_pnl_pct 在警示裡也是「API 收、永遠評估不了」（engine.py L146–L149 註解自承），納入同一不變式。

## 查證結果

1. 前端把 beta.value 列為可選：是。`frontend/app/lib/format.ts` L474（SIGNAL_FIELD_OPTIONS L454–L475）；建立與編輯共用 `settings/AlertParamFields.tsx` L56–L67 的 select（AlertRulesSection、EditAlertRuleModal L331）。附帶：註解自稱「Mirrors FIELD_LABELS (verified)」但漏 drawdown.current 與 position.*；drawdown.current 是否刻意不放待 dev-lead／PM 確認；無測試釘前後端對照。
2. /api/signals 有傳 benchmark：是。`app/api/signals.py` L108 load_market_benchmark、L119–L124 傳入 compute_signals；指數對照 `app/services/index.py` L302–L305（TW ^TWII、US ^GSPC）。前端顯示於個股頁「風險量測」區 Beta 卡（TechnicalIndicatorsPanel.tsx L601–L622、L671）。**UI 沒有「訊號頁」**，揭露字面不得用此詞。
3. 既有含 beta.value 的警示規則：skip 不報錯。engine.py L149–L152 回「缺少輸入欄位：beta.value（相對指標的 beta）」，L253–L254 記 skipped；不觸發也不崩。但措辭暗示暫時缺值，對此欄位非事實；skip 只出現在 /api/alerts/evaluate outcomes 與 scheduler log（L410–L413），使用者看不到。

**關鍵發現 1**：讀取鏈 AlertStore._row_to_rule（store.py L283–L307）→ AlertRule(AlertRuleInput) → Comparison（loader.py L80–L87）對 KNOWN_FIELDS 驗證。若移除 beta.value，DB 有一筆舊規則即讓 list_rules() 拋例外，打掛每 tick 整輪評估（scheduler.py L410）與設定頁規則清單（api/alerts.py L97–L102）。ADR-0017 L26 已記過同一教訓。

**關鍵發現 2**：PATCH 用 stored params 重新驗證整筆（models.py L149–L167、api/alerts.py L134–L145）；若嚴格驗證放在 AlertRuleInput／Comparison，對舊 beta 規則送 {"enabled": false} 會 422，連關都關不掉。

---

## Context（背景）

- beta.value 在 advice／alerts 永遠 None；alerts 的 position.* 亦然。
- 前端可選 beta.value（見查證結果 1）。
- 舊資料讀取時重新驗證（見關鍵發現 1、2）。
- 需要 ADR 的理由：跨模組不變式只存在 docstring 會漂移；「不在 advice／alerts 載入 benchmark」是 IO 決策，需寫明重啟條件。

## Options（方案比較）

| 方案 | 優點 | 缺點 | 風險 | IO |
|---|---|---|---|---|
| (a) live 載入 benchmark | beta 規則真能評估 | 違 ADR-0010 D-1、R-6 要改；fired 訊息多帶指數來源揭露（新字面）；需求未證實 | advice 首次延遲倒退；throttle 爭用；ADR-0018 K-6 基準被改 | 見估算 |
| (a′) cache-only＋預熱（日後路徑） | 0 網路 | 可評估性取決於快取、需預熱動到 ADR-0012 C-11／C-13／T-4 | 需新 ADR | 每市場約每日 1 次 |
| (b) 硬刪 KNOWN_FIELDS | 最簡單 | 舊規則讓 list_rules 崩 | **高，否決** | 0 |
| **b′ 分層詞彙（採用）** | 既有資料不壞；新建擋住；舊規則可關可刪可改；可測；日後接 benchmark 改一行 | 多兩個集合；需新字面 | 低 | **0** |
| (c) 維持可選、UI 標無法評估 | 不動後端 | 保留必死選項；守門與現況矛盾；API 照樣可建 | 中 | 0 |

(a) IO 估算（tick 60 分鐘、S=12、M≤2、cache_first＋ADR-0009 judge、冷卻 TW 1h／US 24h）：alerts 每 snapshot 各抓 +288 服務呼叫／日（網路正常約 ^TWII 1–3、^GSPC 1 次）；每 tick 每市場 memo 一次 ≤ +48；最壞 ^TWII 24 次（碰到 ADR-0009 上限）；advice 每請求 +1，每日第一個未命中請求同步付 yfinance 最壞約 20 秒（ADR-0010 L17）。ADR-0018 K-6 計數測試須分開計 index resolver。ADR-0010 L133–L134 明定擴大 IO 範圍須修訂該 ADR，(a) 不能當 fix。

## Decision（決策）

1. 每個規則消費端有自己的「可新建欄位集合」，且 ⊆ 該管線在資料充足時能產出非 None 的欄位。
2. KNOWN_FIELDS 為讀取相容超集合，只用於讀 DB 與產生標籤。
3. 本期不在 advice／alerts 載入 benchmark。
4. 既有含不可評估欄位的規則不自動刪除或停用，但要讓使用者看得到。

## Consequences（後果）

- 可測、0 IO、舊資料不壞。
- 使用者失去「建得起來」的假象。
- 多兩個常數。
- 前後端對照仍手抄靠測試守。
- 舊 beta 規則存在到使用者自行處理。

## 重啟條件（改走 (a′) 的條件）

- PM 提出 beta 警示需求與驗收；
- cache-only 讀取＋預熱；
- 修訂 ADR-0010 並對照 ADR-0012 C-11／C-13；
- 風控核可 fired 訊息指數來源揭露字面。
- 任何讓 `ALERT_RULE_FIELDS` 納入 `beta.value` 或 position.* 的變更，同一變更內 W-1～W-5 失效並重送風控。（來源：風控審查紀錄 2026-10-06 U-5(iii)、W-R6）

只有 CEO／PM 想要「beta 警示」功能才改走 (a′)＋新 ADR 並先修訂 ADR-0010。CEO 知悉即可。

---

## 對實作的約束

- **K-1**：`app/advice/context.py` 新增兩集合（命名可議）皆 ⊆ KNOWN_FIELDS：ADVICE_RULE_FIELDS = KNOWN_FIELDS − {beta.value}；ALERT_RULE_FIELDS = KNOWN_FIELDS − {beta.value, position.weight, position.unrealized_pnl_pct}。
- **K-2**：KNOWN_FIELDS、FIELD_LABELS、build_context 鍵集合不變仍含 beta.value；Comparison（loader.py L80–L87）仍只對 KNOWN_FIELDS 驗證。
- **K-3**：advice YAML loader（load_rules／RuleSet）用 ADVICE_RULE_FIELDS 驗證每個 field 與 ref，放 RuleSet 或 loader 層，不得放 Comparison。
- **K-4**：警示嚴格驗證只適用使用者新送出的 params：POST、PUT、PATCH 且 params 非 None；違反回 422 用 W-4。AlertRule 與 AlertRulePatch.apply_to 拿 stored params 重新驗證時不得套嚴格集合；只送 enabled／note／symbol 的 PATCH 對舊 beta 規則必須成功。
- **K-5**：store.list_rules()／get_rule() 遇含 KNOWN_FIELDS − ALERT_RULE_FIELDS 欄位的舊規則不得拋例外；DELETE 可用。
- **K-6**：engine 評估此類舊規則仍回 skipped，不得報錯、不得當 quiet；reason 改用 W-2；判斷「欄位不在 ALERT_RULE_FIELDS」不能只看值是否 None。
- **K-7**：不得在 advice、alerts、snapshot 呼叫 load_market_benchmark 或 index resolver；compute_signals 維持不傳 benchmark_bars（api/advice.py L175、alerts/snapshot.py L93）。
- **K-8**：不刪除、停用或改寫任何既有使用者規則（無 data migration）。允許唯讀診斷：scheduler 啟動時 log 一行「引用不可評估欄位的啟用規則數」，只記數量。
- **K-9**：前端 SIGNAL_FIELD_OPTIONS（format.ts L454–L475）移除 beta.value；signalFieldLabel 不得退化成 raw key（舊規則仍顯示「相對指標的 beta」，可另放 legacy 標籤表或後端回傳）；AlertRulesSection 規則清單（L55–L68）對舊規則顯示 W-3；EditAlertRuleModal 開啟舊規則不得讓受控 select 默默顯示第一個選項，須明示原欄位與 W-3，並允許只改 enabled／note 後儲存。
  - 交叉引用：編輯對話框不得靜默吞掉 422（W-R4，required），見風控審查紀錄落地 required 4。
- **K-10**：不改任何既有警示／建議字面與門檻；新字面 W-1～W-5 走風控閘門；snapshot.py L9–L10 與 engine.py L146–L148 docstring 改寫為引用 K-1 集合。
- **K-11**：tests/test_advice_engine.py L385／L408／L430／L437／L444 以 beta.value 當「必缺欄位」的夾具，換成合法但可為 None 的欄位（如 bars 不足時的 ma60.last）或沿用 L420 dict.fromkeys(KNOWN_FIELDS, None)；測試意圖不得削弱。

---

## 測試要求

- **T-1 可評估性動態守門**：合成 540 日 bars＋fake resolver 跑真實 build_snapshot → build_context，斷言 ALERT_RULE_FIELDS 每欄非 None、KNOWN_FIELDS − ALERT_RULE_FIELDS 每欄為 None（反向釘）；advice 端對 ADVICE_RULE_FIELDS 同樣正反兩向。
- **T-2 舊資料相容**：SQL 直插 field="beta.value" 與 ref="beta.value" 規則；list_rules／GET /api/alerts 200；evaluate 回 skipped 且 reason == W-2；PATCH {"enabled": false} 200；DELETE 204。
- **T-3 新建擋下**：POST／PUT／PATCH(params) 帶三個不可評估欄位的 field 或 ref 一律 422，訊息同 W-4。
- **T-4 loader**：YAML 寫 beta.value 載入即報錯；default.yaml 照常（test_advice_loader.py L42 改對 ADVICE_RULE_FIELDS 斷言）。
- **T-5 前後端對照**：後端測試解析 format.ts 的 SIGNAL_FIELD_OPTIONS value 集合 ⊆ ALERT_RULE_FIELDS 且不含 beta.value；label 逐字等於 FIELD_LABELS；用子集斷言（drawdown.current 待 PM）。
- **T-6 IO 不增**：記錄型 index resolver 斷言 get_advice 與 build_snapshot 呼叫次數 0；可與 ADR-0018 K-6 共用夾具。
- **T-7 回歸**：K-11 改寫後 skip 測試、test_alerts_api、test_alerts_snapshot、test_scheduler、前端 format.test 與相關元件測試全綠。

---

## 需風控審字面（W-1～W-4 已核可；W-5 待重寫）

以下五項為裁示列出、須先交 creative-lead 出稿再送 risk-compliance-officer 審的字面需求；下列為各項的範圍與限制，不是文案本身，核可字面見段末所列風控審查紀錄。

- **W-1**：警示表單「訊號欄位」下方常駐說明——Beta 不提供作為警示條件，可在個股頁「風險量測」區看到；禁用「訊號頁」。
  - 狀態：**已核可（2026-10-06）**，逐字以該審查紀錄核可字面總表為準。
- **W-2**：舊規則 skip reason，取代「缺少輸入欄位」；講清楚是常態非暫時，寫出處理方式（編輯或刪除）。
  - 狀態：**已核可（2026-10-06）**，逐字以該審查紀錄核可字面總表為準。
  - 處置句以風控核可字面為準（「可改用其他欄位的條件，或刪除此規則」），取代本文原寫的「編輯或刪除」。
- **W-3**：規則清單與編輯對話框中舊規則的標示。
  - 狀態：**已核可（2026-10-06）**，逐字以該審查紀錄核可字面總表為準。
- **W-4**：422 錯誤訊息（beta 一句；position.* 一句，目前只有 API 用得到）。
  - 狀態：**已核可（2026-10-06）**，逐字以該審查紀錄核可字面總表為準。
- **W-5**：release note 一句，範圍限警示可選欄位變動與既有 beta 規則處置，比照 RN-1～RN-6 中性寫法。
  - 狀態：**現稿 VETO，退回重寫**；須揭露此版本之前 Beta 規則亦不會觸發（待 dev-lead 查證歷史）。

- 風控審查紀錄：`work/reviews/2026-10-06-ADR-0021-警示欄位可評估性-字面-風控審查.md`（risk-compliance-officer 審查、coordinator 轉錄，2026-10-06）。上列各項狀態與 W-2 處置句取自該紀錄的結論、「核可字面總表」與 U-1；本文不重抄字面，避免兩處漂移。

---

## 相關檔案

以下為 tech-architect 本次讀取所列（會漂移；路徑相對於各自所屬的 backend／frontend 目錄，未逐一補全前綴，以原文定位）：

- context.py L22–L51、L113、L136
- loader.py L39、L68–L87
- alerts/engine.py L141–L174、L229–L254、L295–L308
- alerts/models.py L60–L65、L82–L167
- alerts/store.py L117–L124、L283–L307
- alerts/snapshot.py L1–L13、L93
- api/alerts.py L97–L149
- api/advice.py L155–L175
- api/signals.py L12–L17、L108–L124
- services/index.py L285–L400
- api/deps.py L117–L160
- scheduler.py L395–L413、L613–L646
- settings/models.py L104–L106
- tests/test_advice_engine.py L385、L408、L420、L430–L437、L444、L588
- tests/test_advice_loader.py L42
- frontend：format.ts L448–L490；AlertParamFields.tsx L49–L67；AlertRulesSection.tsx L55–L68；EditAlertRuleModal.tsx L23–L61、L323–L336；TechnicalIndicatorsPanel.tsx L601–L622、L662–L671
- ADR-0020 第 4 題／K-8
- ADR-0010 L17、L41–L46、L73–L74、L122、L133–L134
- ADR-0018 L11、L285、L325
- ADR-0017 L26

## 交接

- ADR-0021 落檔：tech-writer（並已在 ADR-0020 第 4 題與 K-8 加交叉引用）。
- K-1～K-11、T-1～T-7 交 dev-lead；K-9 前端交 frontend-engineer。
- W-1～W-5 交 creative-lead 出稿後送風控（risk-compliance-officer）。
- drawdown.current 是否進警示選單交 product-manager。
- CEO 知悉即可；只有 CEO／PM 想要「beta 警示」功能才改走 (a′)＋新 ADR 並先修訂 ADR-0010。
