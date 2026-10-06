# ADR-0020：stock-desk 訊號觀察窗單一來源

- 狀態：proposed
- 日期：2026-10-04
- 決策者：tech-architect
- 提案來源：dev-lead 分析 `work/research/警示-400-日窗與建議卡-540-日窗差異-分析-2026-10-04.md`
- 適用範圍：僅 product/stock-desk 產品線
- 實作時程：**本修正屬 fix 等級，實作不等本 ADR 核可即可進 build**（tech-architect 裁示：「修正可以直接進 build，不必等 ADR」）。本 ADR 記錄的是跨模組不變式，核可與否不擋 fix 合併。
- 編號說明：落檔時 `docs/adr/` 目錄下 0019 為最後一份，查無 0020；repo 內（排除 `.git/`）亦無 ADR-0020 或 `0020-` 的引用，故使用 0020。
- 來源與版本：本檔為 tech-architect 2026-10-04 裁示（「訊號觀察窗單一來源（ADR-0020 草案要點）」，原文落於 scratchpad `adr0020-architect-ruling.md`）的落檔，B 類轉錄，僅做格式調整，技術內容未增補、結論未改動。
  - 「評估摘要」「架構師自行核對的事實」「方案比較」「Context」「Decision」「Consequences」「對實作的約束」K-1～K-8、「測試要求」T-1～T-5、「發版要求」「第 4 題：beta」「未查證」「相關檔案」皆逐字取自該裁示。
  - 檔內所有 `檔案:行號`（例：`app/api/signals.py` L42、`app/scheduler.py` L126、`app/advice/limits.py` L54）、函式名、常數名、數字（例：400、540、10.4pp、約 100 根 bars、14 次變 18 次）均為 tech-architect 所述；tech-writer 落檔時**未重新對 code 驗證**。行號會隨 commit 漂移，引用時以原文定位。
  - 落檔時的快照：分支 `product/stock-desk`，HEAD `93dace3f9db887289507b4d471ddfa9c693954f2`（tech-writer 於落檔時讀取 `.git/refs/heads/product/stock-desk`）。此為快照，之後 HEAD 可能前進。
  - 此為 proposed 狀態；依 ADR-0001，生效前的內容可修訂，生效後不得原地改寫決策。

---

## 關聯

- 依據：`work/research/警示-400-日窗與建議卡-540-日窗差異-分析-2026-10-04.md`（dev-lead）。
- 與 ADR-0018 的關係：不併入 ADR-0018（見「評估摘要」）；與 ADR-0018 K-6 不衝突（見 Consequences）。
- 與 ADR-0004 的關係：不併入、不修訂 ADR-0004（已 accepted，見「評估摘要」）。
- 與 ADR-0012 的關係：C-13 的 `DATA_REFRESH_LOOKBACK_DAYS == 540` 不動（見 K-5）。
- 與 ADR-0010 的關係：第 4 題（beta）若併入本修正，會觸及 ADR-0010 的 IO 預算，故另開單（見「第 4 題：beta」）。

---

## 評估摘要

- 採用 dev-lead 選項 1（統一為 540），屬 fix 等級，修正可以直接進 build，不必等 ADR。
- 另開一則小 ADR-0020「訊號觀察窗單一來源」，專門記錄跨模組不變式，不併到合併前置條件裡。理由：這次的 bug 就是「同一窗」只寫在 docstring 裡，才會漂移。
  - 不併入 ADR-0018：它管關鍵價位，目前是 proposed，而且還卡在 CEO 兩項不相干的裁示上。
  - 不併入 ADR-0004：它已 accepted，不能原地改寫；範圍也不涵蓋 alerts。
- 否決選項 2（改 400）和選項 3（保留差異只做揭露）。
- 第 4 點（beta）另開單，不併入本修正（會帶進新的網路 IO，可能和 ADR-0010 的 IO 預算、ADR-0018 K-6 的計數衝突）。

## 架構師自行核對的事實

1. 540 不只出現在一個地方：
   - app/api/signals.py L42（DEFAULT_LOOKBACK_DAYS），advice、bars、portfolio、scripts/drawdown_rule_diff.py 都從這裡 import。
   - app/data/diagnose.py L39 自己又定義了一份 DEFAULT_LOOKBACK_DAYS = 540。
   - app/scheduler.py L126 的 DATA_REFRESH_LOOKBACK_DAYS = 540，被 ADR-0012 C-13 釘住。
   - app/api/leverage.py L43 的 1200 是另一個領域，不在本約束範圍。
2. 「app.alerts 碰不到 app.api」目前在整條 import 圖上做不到：
   - 路徑是 app.alerts.snapshot → app.advice.limits → app.api.kelly_wording（limits.py L54）。
   - 守門測試不能寫成全面禁止碰到 app.api，要改用白名單寫法（見 K-3）。
   - advice 反向 import app.api.kelly_wording 是既有債，不在本單處理。
3. build_snapshot 的 lookback_days 參數沒有任何呼叫端在用：app/scheduler.py L394、app/api/alerts.py L228，以及 tests 都沒傳。可以直接移除。
4. 另一個輸入差異：advice 呼叫 load_bars 時有傳 calendar_source（advice.py L163），snapshot 沒傳。請 dev-lead 確認它只影響「資料過舊」提示、不影響 bars 本身；確認不影響就列為已知差異，不在本單處理。
5. beta.value 列在 app/advice/context.py L46 的欄位表裡，alerts 透過 build_context／describe_field 也能選到。但 advice 和 alerts 都沒傳 benchmark，所以這個欄位可以選、卻永遠無法評估。

---

## Context（背景）

- 警示 snapshot 用 400 日窗，advice／signals／bars／portfolio 用 540，兩者同在 f4f7baa 進入，沒有任何設計紀錄。
- 受影響的是 drawdown.current、drawdown.max_drawdown、volatility.annualized。構造例中同一標的、同一天差了 10.4pp。
- snapshot docstring 宣稱「同數字」，和實作不符。

## Options（選項比較）

### 第 1 題：要不要 ADR

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A 不寫 ADR，只靠測試加 docstring | 最輕 | 約束沒有編號，qa 無從對照；之後新增的消費端（例如 keylevels）沒有依據 | 再次漂移 |
| B 註記寫進 ADR-0018 | 不用開新檔 | 範圍錯置；核可被 CEO 那兩題綁住 | 耦合不相干的決策 |
| C 修訂 ADR-0004 | — | 已 accepted，不能原地改寫；不涵蓋 alerts | 違反 ADR-0001 |
| D 小 ADR-0020（採用） | 範圍精確，K／T 可以被檢查 | 多一份文件 | 低；不擋 fix 合併 |

### 第 2 題：常數放哪裡

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| app/signals/window.py（或 constants.py），作為葉模組（採用） | 窗長本來就是 signal 層的輸入需求（MA60 加報酬樣本）；alerts、api、scheduler 原本就依賴 app.signals，不新增任何依賴邊 | app.data.diagnose 要 import 它的話是向上依賴 | 低 |
| 放 app/services/market.py | 和 load_bars 放一起 | 「窗多長」變成資料服務的知識，語意錯置 | 中 |
| 留在 app/api/signals.py | 不用動 | alerts 必須反向 import API 層 | 高，否決 |

### 第 4 題：beta

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 併入本修正 | 一次修完 | 新增指數抓取 IO，觸及 ADR-0010 和 ADR-0018 K-6 計數 | 拖住 fix |
| 另開單評估（採用） | fix 範圍保持單純 | 不一致暫時還在 | 低；beta 規則目前本來就評估不到 |

（第 3 題為發版要求，見「發版要求」一節；裁示原文無方案表。）

## Decision（決策）

- 警示、建議卡、訊號頁、bars 圖、portfolio 對同一標的，共用同一個觀察窗常數（值 540，維持不變）。
- 常數由 app.signals 擁有，API 層只 re-export。
- 資料刷新窗必須涵蓋觀察窗。

## Consequences（後果）

- 既有警示的命中行為會一次性改變：lt 只會多響、gt 只會少響、volatility 兩個方向都可能。
- 部署後第一次 tick 可能一次觸發一批「卡片早就命中」的警示，cooldown 擋不住第一次觸發。
- 每檔每次 tick 多算約 100 根 bars。
- 只被警示盯的標的，首次抓取的月請求次數從 14 次變 18 次（一次性）。
- demo 示範門檻的校準理由會失效。
- 與 ADR-0018 K-6 不衝突：K-6 管的是值，值沒變，名稱也仍可 import。

---

## 對實作的約束

### K-x（逐條可檢查）

- **K-1**：新增 app/signals/window.py（名稱可議，落檔時定案），內容為 OBSERVATION_LOOKBACK_DAYS: Final = 540。這個模組不得 import 任何 app.*（純葉模組，AST 檢查）。
  - 定案註記（tech-writer，2026-10-05 更新）：已定案 `app/signals/window.py`，實作 commit `7dd272b`（2026-10-05），qa-reviewer PASS。（來源：任務單轉述，B 類；tech-writer 未重新讀 code 驗證該 commit 內容。）原註記「名稱可議，落檔時定案」之「落檔時定案」一語出自裁示原文，已由此註記取代。
- **K-2**：app/api/signals.py 的 DEFAULT_LOOKBACK_DAYS 改成從 K-1 re-export。既有的 advice／bars／portfolio／scripts import 不必改；改 import 新位置也可以。全 repo 只能有一處整數字面 540 作為觀察窗定義。DATA_REFRESH_LOOKBACK_DAYS、diagnose 依 K-5 處理。
- **K-3**：app.signals.* 碰不到任何 app.api.*。app.alerts.* 能碰到的 app.api 模組必須是白名單 {app.api, app.api.kelly_wording} 的子集（現況債務）；尤其不得碰到 app.api.signals。用 tests/import_graph.py 的 reachable_app_modules 加 offenders 實作，寫法比照 test_market_panel_boundary.py，app.alerts 的模組清單要從原始碼樹列舉。
- **K-4**：移除 build_snapshot 的 lookback_days 參數，函式內直接用 K-1 常數。如果 dev-lead 有理由保留，預設值必須是 K-1 常數，而且 app/ 底下的非測試檔不得傳入這個參數（grep）。
- **K-5**：DATA_REFRESH_LOOKBACK_DAYS >= OBSERVATION_LOOKBACK_DAYS（ADR-0012 C-13 的 == 540 不動）。app/data/diagnose.py 的 DEFAULT_LOOKBACK_DAYS 必須等於 K-1 常數；它可以維持本地定義，避免 app.data 向上依賴 app.signals，但要用測試斷言兩者相等。
- **K-6**：app/alerts/snapshot.py 的 docstring 必須和實作一致。app/demo/seed.py L186–L192 的「400-day」校準說明刪除或改寫；_DRAWDOWN_ALERT_THRESHOLD 要在 540 窗下重新確認。
- **K-7**：不改任何警示、建議的字面與規則門檻（字面若有變動就改走風控閘門）。
- **K-8**：不在本單新增 benchmark 載入，也不改 beta.value 欄位的可選性。
  - 交叉引用：本題由 ADR-0021（proposed）承接，裁示採 b′ 分層詞彙、本期不載入 benchmark。

---

## 測試要求

- **T-1 窗起點不變式**：固定 today，用記錄型 resolver 或 monkeypatch load_bars，斷言 build_snapshot 和 get_advice 傳給 load_bars 的 start、end 相同。
- **T-2 數值一致回歸**：用 dev-lead 的構造例 C（舊高約在 450 日前），同一份 fake bars、同一個 today，斷言 snapshot 和 advice 的 drawdown.current、max_drawdown、volatility.annualized 逐值相等，而且 drawdown_protection 兩邊都命中。修正前這個測試必須紅燈，PR 附上紅轉綠的證據。
- **T-3 import graph**：K-1 是葉模組；K-3 的兩條。
- **T-4 常數關係**：K-2 的 re-export 是同一個值；K-5 的 >= 與相等。
- **T-5**：實際跑 test_seeded_alert_rules_actually_fire、test_alerts_snapshot.py、test_scheduler.py、test_alerts_api.py，還有 ADR-0018 K-6 的計數測試（如果已存在），全部要綠燈。

---

## 發版要求（第 3 題）

- **release note：必要。** 用一般使用者看得懂的話寫。
  - ~~草稿字面（tech-architect 原文，**待風控快審**，在 risk-compliance-officer 審過前不得視為定稿或對外發布）：
    「回撤、波動警示的計算區間改成和建議卡、訊號頁一致（約 18 個月）。升級後，部分回撤警示可能會首次觸發，或觸發時機改變；這反映的是建議卡上早已顯示的狀態。」~~
  - **【已被取代，不得對外】** 本草稿已被風控核可版取代（2026-10-05），以 `work/reviews/2026-10-04-規則集-1.2.0-前置-風控預審.md`「T4／L-6 揭露字面與 release note 審查」核可字面總表 RN-1～RN-6 為準，不得以本草稿對外。否決理由：含安撫語、只寫單一方向、「訊號頁」在 UI 不存在。（原草稿文字保留於上，僅劃記為已取代。）
  - **風控核可版 release note（RN-1～RN-6，依序六句，同一段，逐字）**：
    「警示的計算區間由 400 個日曆日改為 540 個日曆日（約 18 個月）。警示與個股頁的建議卡、技術分析，現在使用同一個計算區間。警示與個股頁分別計算，同一標的的數值仍可能不同。使用回撤或波動度條件的警示，數值與觸發時機可能和升級前不同。部分警示可能多觸發，也可能少觸發。升級後的第一次檢查，可能一次出現多則通知，均依新的計算區間判斷。」
    - 發布條件：只能隨實際含本 ADR 修正的版本發布（release-flow 確認部署狀態）。
    - 來源：風控預審 `work/reviews/2026-10-04-規則集-1.2.0-前置-風控預審.md` 核可字面總表 RN-1～RN-6（tech-writer 已逐句與該檔 L131–L136 核對字面一致）。
    - 註（2026-10-06 風控裁定）：與 ADR-0021 W-6 同版發布時，RN-6 以風控核可甲案為準：「升級後的第一次檢查，可能一次出現多筆警示事件，均依新的計算區間判斷。」不同版或 CEO 決定不改時維持原句。依據：`work/reviews/2026-10-06-ADR-0021-警示欄位可評估性-字面-風控審查.md`「W-6 第二版審查」。
- **風控**：程式碼本身不必過 risk-gate（字面沒變，K-7）。但要送風控：知會這次行為改變，以及請他快審 release note 那一段。風控如果要求在警示訊息裡標出區間，就另開字面單處理。
- **CEO**：知悉即可，不需要裁決。需要 CEO 知道：部署後第一個 tick 可能集中推播一批警示。架構師不建議壓掉這批推播。
- **版本號**：依 release-flow 以 fix（patch）處理。

## 第 4 題：beta（另開單，交 tech-architect 評估）

本題**不併入本修正**，另開單，不擋本修正（K-8）。

- 現況：beta.value 列在 advice 的欄位表裡，alerts 也能選到，但永遠拿不到值。
- 待評估選項：(a) advice、alerts 也載入 benchmark；(b) 把 beta.value 從警示、規則可選欄位拿掉並揭露；(c) 維持現況但 UI 標「此欄位無法評估」。初步傾向 (b) 或 (c)。要先查現行規則集和使用者已建規則有沒有引用 beta.value。這張單不擋本修正。
- 交叉引用：本題由 ADR-0021（proposed）承接，裁示採 b′ 分層詞彙、本期不載入 benchmark。

---

## 未查證

以下三項原為裁示原文所列「未查證」，2026-10-05 已更新為查證結果：

- calendar_source 是否影響 bars 內容：**已查證，不影響 bars。** calendar_source 只影響 meta 的 `trading_days_behind`（`app/services/market.py` L166、L177、L188–L193）。列為**已知差異，本 ADR 不處理**。（tech-writer 已讀 `apps/stock-desk/backend/app/services/market.py` L150–L194：bars 取自 L166 `service.get_daily_bars(...)` 與 L177 `list(result.bars)`，`calendar_source` 僅傳入 L188–L193 的 `trading_days_behind_market(...)`。）
- 現行規則集和使用者已建規則有沒有引用 beta.value：**已查證（部分）。** 現行規則集 `default.yaml` 無任何 `beta.value` 引用；僅 `tests/test_advice_engine.py` 以合成規則測「欄位缺值即 skip」。使用者已建規則存於 DB，依隔離規定**未查**。（tech-writer 以 grep 確認 `apps/stock-desk` 下 `*.yaml` 無 `beta.value`，`apps/stock-desk/backend/tests/test_advice_engine.py` L385、L408、L430、L444 為合成規則。）
- ADR-0018 K-6 的計數測試目前是否已存在：**已查證，目前不存在**（repo 無 keylevels 模組）。（tech-writer 以 glob 確認 `apps/stock-desk/backend/app/**/keylevels*` 無檔案。）

另，本檔其餘 `檔案:行號` 與 code 現況是否相符，tech-writer 落檔時未重新驗證（見檔頭「來源與版本」），待 dev-lead 於實作時以原文定位核對；上列三項所引行號為 2026-10-05 重新讀取者。

## 相關檔案

- work/research/警示-400-日窗與建議卡-540-日窗差異-分析-2026-10-04.md
- apps/stock-desk/backend/app/alerts/snapshot.py（L3–L5 docstring、L39）
- apps/stock-desk/backend/app/api/signals.py（L40–L42）
- apps/stock-desk/backend/app/api/advice.py（L40、L155–L164）
- apps/stock-desk/backend/app/advice/limits.py（L54）
- apps/stock-desk/backend/app/advice/context.py（L46、L136）
- apps/stock-desk/backend/app/scheduler.py（L126、L394）
- apps/stock-desk/backend/app/data/diagnose.py（L39）
- apps/stock-desk/backend/app/demo/seed.py（L186–L193）
- apps/stock-desk/backend/tests/import_graph.py
- apps/stock-desk/backend/tests/test_market_panel_boundary.py
- docs/adr/0018-stock-desk-關鍵價位的生命週期與計算歸屬.md（K-6）
- docs/adr/0012-stock-desk-族群動能與全市場日線.md（C-13）
