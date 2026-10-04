# ADR-0018：stock-desk 關鍵價位的生命週期與計算歸屬

- 狀態：proposed（待 CEO 對「需要 CEO 決定」兩項裁示後方可 accepted）
- 日期：2026-10-04
- 決策者：tech-architect（草案）；待 CEO 核可（見「需要 CEO 決定」）
- 適用範圍：僅 product/stock-desk 產品線
- 與既有 ADR 的關係（不取代任何一則）：
  - ADR-0004 §4（accepted）：不衝突；於 ADR-0004「相關 ADR 與依賴」加交叉引用註記（D-9 文字）。
  - ADR-0016 K-5（accepted）：「前端不自算 pct」精神延伸至關鍵價位（D-1、K-8）。
  - ADR-0012 C-7（accepted）／ADR-0016 K-16：`app.keylevels` 納入不可達 `app.data.market_panel` 名單（K-5）。
  - ADR-0009／ADR-0010：不改 `DEFAULT_LOOKBACK_DAYS`、不增任何網路 IO（K-6）。
  - ADR-0014：關鍵價位只用日線收盤，不用盤中報價（K-7）。
  - ADR-0006：不改 `five_conditions` 語意；移動停利回測以新策略 id 呈現（D-8）。
  - ADR-0017：基準價讀持倉時沿用市場／幣別一致性（D-5）。
- 編號說明：0013 為員工線佔用；草案撰寫時 `docs/adr/` 查無 0018。
- 來源與版本：本檔為 tech-architect 2026-10-04 handback（ADR-0018 草案）的落檔，B 類轉錄，僅做格式調整，技術內容未增補、結論未改動。
  - 「評估摘要（結論先行）」、Context、Options、Decision、字面影響清單、Consequences、對實作的約束、測試要求、需要 CEO 決定、未查證事項、相關檔案，皆逐字取自該 handback。
  - 草案內 Context／Options／Consequences 原寫「同本評估 …，tech-writer 原樣轉錄」，本檔已將 handback 評估部分的對應原文放入各段。
  - 檔內所有 `檔案:行號`、公式與數字（例：3037 的 1,191.62、1,232.71）均為草案作者所引；行號為草案作者 2026-10-04 讀到的工作目錄狀態，未對照特定 commit。tech-writer 落檔時未重新對 code 驗證；行號會隨 commit 漂移，引用時以原文定位。
  - 草案中的「第一期（案 A）」落地狀態請見「關聯」段（來源為任務單轉述的 CEO 2026-10-04 裁示）；Context 第 10 點為草案撰寫時的敘述，保持原文。
  - 此為 proposed 狀態；依 ADR-0001，生效前的內容可修訂，生效後不得原地改寫決策。

---

## 評估摘要（結論先行）

- **採用的方向：**
  1. 關鍵價位整組搬到後端新套件 `app/keylevels/`，不只停損與停利，位階、MA、ATR 也一起搬。
  2. 以 `AdviceResponse.key_levels` 回傳，放在 `advice` 的同層、不放進卡片內。
  3. 前端只渲染，不再計算任何價位、狀態或百分比。
  4. 停利生命週期分「成本期 → 移動停利期」兩期；缺 `opened_at` 或日線窗涵蓋不到時，退回案 A。
  5. P 取 `opened_at` 起的最高收盤，ATR 取最新一根，不做棘輪（ratchet）。
- **建議統一為 ×1.2，否決 2R**，這點需要 CEO 裁定（見「需要 CEO 決定」#1）。理由如下：
  - 2R 會跟著 ATR 每天跳動，判斷是否越過必須逐日重播並鎖住狀態。
  - ATR 很小時 2R 會退化成 A + 4×ATR，例如 ATR 為 A 的 0.5% 時只剩 +2%。
  - 既有回測方法論 §2.2 早就因為「隱性路徑相依」而拒用 2R。
  - 選 ×1.2 的話，`five_conditions` 與風控核可的 `FIVE_CONDITIONS_NOTE` 都不用改；移動停利改用新的策略 id 並列呈現。
- **與 accepted ADR 沒有衝突。** ADR-0004 §4 只需要加一行交叉引用註記，不取代任何一則 ADR。

---

## 待 CEO 裁示（2026-10-04 尚未決定）

本 ADR 狀態為 proposed 的理由：待 CEO 對下列兩項裁示後方可 accepted。完整原文見文末「需要 CEO 決定」。

1. **停利基準統一為 ×1.2 或 2R？** 架構師建議 ×1.2、否決 2R。
2. **移動停利期是否同時提高停損格？** 架構師建議：不提高。

---

## 關聯

- CEO 2026-10-04 裁示：案 A（已越過水位字面）先行，已落地 commit `66ed876`；案 B（移動停利）排下一輪，並需本 ADR。（來源：任務單轉述 CEO 2026-10-04 裁示；commit `66ed876` 由任務單提供，tech-writer 未另行查驗。）
- 研究依據：`work/research/決策卡-停利參考低於現價-評估-2026-10-04.md`。
- 風控列管：「案 B 成本停損 −27.6% 無保護意義」，見 `work/reviews/2026-10-04-決策卡-已越過水位-風控審查.md`。
- ADR-0004 §4 交叉引用註記：待本 ADR accepted 後，由 tech-writer 於 ADR-0004 §4 加註（註記文字見 D-9）。本 ADR 落檔時未修改 ADR-0004。

---

## Context（背景）

1. **計算位置。** 關鍵價位全部在前端計算：`apps/stock-desk/frontend/app/lib/keyLevels.ts::computeKeyLevels`（L99–169，常數在 L78–83）。檔頭 L10–16 自己寫明「正式歸屬應在後端，列為後續」。
   - 使用者有五處：`DecisionCard.tsx`、`KeyLevelsPanel.tsx`、`keyLevelsVisuals.ts`（價位階梯，L102–121，2R 標為 headline）、`entryObservation.ts`（六項觀察條件讀位階與 MA）、`page.tsx`。
   - 基準價的三種狀態由 `page.tsx::resolveKeyLevelsAnchor`（L66–87）在前端判斷，依據是風控 R10／R11／R13／R14：多批持倉以數量加權，任一批成本不可用就判「狀態未知」。
2. **現行公式。**
   - 基準價 A：持有且成本可得時用平均成本，否則用最新收盤。
   - 停損：`max(A − 2×ATR14, 0.92A)`。
   - 卡上停利：`target2R = A + 2(A − 停損)`，恆 ≤ 1.16A。
   - 面板次列：`1.2A`。
   - ATR14 用 14 個 TR 的簡單平均，不是 Wilder。
3. **停損停利是靜態括號，價格走出去後就失去意義。** 3037 的例子：停利參考已經在最新收盤下方，停損距現價 −27.6%。出處：`work/research/決策卡-停利參考低於現價-評估-2026-10-04.md`。
4. **卡上停利與回測停利不一致。** 回測 `app/backtest/strategies.py::_replay_with_stop_levels`（L382–424）在收盤 ≥ 1.2×進場價時出場，卡上大字卻是 2R。
   - 方法論 `work/stock-desk-五條件回測-方法論.md` L86–88 明說不用 2R，因為它「依賴每日變動的停損水位……隱性的路徑相依參數」。
   - 風控逐字核可的 `FIVE_CONDITIONS_NOTE`（`app/api/backtest.py` L96–105）釘死了「開倉基準價 × 1.2」的寫法。
5. **2R 的退化情形。** 當 2×ATR < 0.08A 時，2R = A + 4×ATR。ATR 若是 A 的 0.5%，停利只剩 +2%。
6. **「移動停利」這個詞已經被占用。** 「移動停利觀察」目前顯示的是 MA20（`KeyLevelsPanel.tsx` L143–146、L216–222），而且字面明寫「系統並未另行計算移動停利水位」。
7. **既有 ADR 的覆蓋。** ADR-0004 §4 規定規則層「無目標價」。目前沒有任何 ADR 涵蓋關鍵價位公式。
8. **資料面。**
   - `positions.opened_at` 允許 null（`positions/models.py` L141）。
   - `SummaryPosition` 帶 `id`、`avg_cost`、`opened_at`（`portfolio/summary.py` L48–61）。
   - `/api/advice` 已用 `DEFAULT_LOOKBACK_DAYS=540` 個日曆日載入該檔日線，並組好 summary 與 `held`（`api/advice.py` L154–165、L183–195）。
9. **另有一套移動停利。** 快市排程 playbook 有自己的有狀態移動停利：存 `peak_close`，比例 ×0.88 或跌破 25MA（`playbook/models.py` L107、`engine.py` L582–613）。那是使用者自訂的規則集，與本面板是不同領域。
10. **第一期（案 A）進行中。** 僅前端，字面草稿在 `work/stock-desk-決策卡-已越過水位-起草-2026-10-04.md`，待風控審。判定採嚴格大於／小於、用未四捨五入值比較，越過後距離改以水位為分母。

---

## Options（選項比較）

採用：A3、B2、C1〔待 CEO #1〕、D1、E1、F1。（**粗體**為採用或建議方案。）

**A. 計算歸屬與 API 位置**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A1 維持前端 | 不用改 | 回測與畫面各寫一份；P 要在前端跑歷史；與 K-5 精神相反 | 兩份實作漂移（已發生：2R 對 ×1.2） |
| A2 後端，放 `/api/signals` | 已經是指標端點 | signals 本來與持倉無關，會為了成本錨點把持倉耦合進來 | 破壞 signals 的無持倉語意 |
| **A3 後端 `app/keylevels/`，以 `AdviceResponse.key_levels` 同層回傳（採用）** | advice 已有同一份日線、summary 與 `held`，零額外 IO；決策卡的動作與價位出自同一快照 | 面板閘門改依 advice；advice 端點職責變寬 | 讀者可能誤以為價位屬於建議引擎，用 K-3／K-4 封住 |
| A4 新端點 `/api/key-levels/{symbol}` | 失敗彼此隔離 | 多一次載入日線與讀持倉；決策卡要拼兩個快照 | 卡上收盤與動作可能不同源 |

**B. 搬遷範圍**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| B1 只搬停損、停利、移動停利 | 改動小 | 價位階梯混用前端 MA 與後端錨點，兩個快照混在一起 | 不同源數字並列 |
| **B2 整個 `KeyLevels` 都搬（採用）** | 單一來源、單一快照；回測可共用 `_panel_atr` | 前端約 6 個檔案加測試要改 | 必須用 golden parity 測試確認搬遷前後數字一致 |

**C. 統一停利基準（需 CEO 決定 #1）**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **C1 ×1.2（建議）** | 與 ATR 無關、持有期間固定；判斷是否越過只要比 P，單調所以不必鎖狀態；既有回測與 `FIVE_CONDITIONS_NOTE` 不變；移動停利恆 ≥ 0.92×1.2A = 1.104A > 成本 | 卡上大字從 ≤+16% 變 +20%；2R 字面要拿掉或改寫，需送風控 | 使用者看到數字改變，要靠揭露吸收 |
| C2 2R | 卡上數字不變；與停損連動 | 每日跳動，要用 ATR 序列逐日判斷並鎖狀態；ATR 很小時退化；回測出場、`FIVE_CONDITIONS_NOTE` 與 Kelly 帶入的 strategy 語意都要改；移動停利可能低於成本（0.92P，而 P 可接近 A） | 回測要三版並列才能歸因；look-ahead 的風險面變大 |

**D. P 的定義**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **D1 `opened_at` 起（含當日）的最高收盤（採用）** | 綁定這筆部位；收盤可在收盤時點交易，與回測逐 bar 以收盤檢查一致；point-in-time | 依賴 `opened_at`；受 540 日窗限制 | 持有很久的部位退回案 A |
| D2 近 252 根區間最高（用 high） | 不需 `opened_at` | 會納入建倉前的高點，移動停利可能一開始就在現價之上 | 語意錯誤 |
| D3 持有期間最高「最高價」 | 反應盤中高點 | 收盤時點做不到；雜訊大；與回測不一致 | 回測與畫面分叉 |

**E. ATR 的日期與是否棘輪**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **E1 最新 ATR、不棘輪（採用）** | 與現行成本停損同語意（固定錨點、最新 ATR）；給定 P 時無狀態，只是 bars ≤ t 的函數 | ATR 放大時水位可能下移，幅度受 0.92P 下限約束 | 讀者以為「移動停利只會上移」，須在依據中揭露 |
| E2 棘輪：`max(前值, 今值)` | 符合一般語感 | 多一層路徑相依；等於新增方法論選擇 | 屬變體，不得在看過回測後才挑 |
| E3 凍結在 P 當日的 ATR | 只隨 P 上移 | 要回溯 P 日的 ATR，多一個隱性自由度 | 同上 |

**F. 越過後原成本停利是否保留**

| 方案 | 優點 | 缺點 |
|---|---|---|
| **F1 保留：面板詳細列照列，卡上附註「已越過」（採用）** | 計畫水位可追溯，與 quant 建議一致 | 多一個數字，要有字面 |
| F2 隱藏 | 畫面較簡潔 | 讀者看不到原計畫，也無法核對狀態切換 |

---

## Decision（決策）

**D-1 計算歸屬**：新增後端套件 `app/keylevels/`，為關鍵價位（位階、MA20／MA60、近 60 日低點、ATR14、基準價、停損、成本停利、移動停利、生命週期狀態、決策卡兩格之距離）唯一計算來源。前端 `computeKeyLevels` 與 `resolveKeyLevelsAnchor` 於第二期刪除；前端只渲染後端值。回測 `app/backtest/strategies.py` 的停損／停利／ATR 改 import `app.keylevels` 的同一批函式與常數。

**D-2 API 形狀**：`AdviceResponse` 新增同層欄位 `key_levels: KeyLevelsPayload | None`（不放進 `advice` 卡片，`advice` 仍為 `build_advice` 原樣輸出）。日線不足（`status=="insufficient_data"`）時為 null。JSON 數值一律十進位字串；價位 quantize 0.0001、百分比（百分比單位）quantize 0.0001。欄位名為規範性，變更須 tech-architect 覆核：

```
class LevelPoint(BaseModel):           # frozen
    price: Decimal
    pct_vs_close: Decimal              # (price / close - 1) * 100
    pct_vs_anchor: Decimal             # (price / anchor_price - 1) * 100  (ladder)

class CardCell(BaseModel):             # frozen; one decision-card cell
    level_kind: Literal["cost_stop", "cost_target", "trailing"]
    price: Decimal
    relation: Literal["not_crossed", "crossed"]
    distance_pct: Decimal              # not_crossed: (price-close)/close*100 ; crossed: (close-price)/price*100
    distance_basis: Literal["close", "level"]

class TargetLifecycle(BaseModel):      # frozen
    phase: Literal["cost", "trailing"]
    fallback: Literal["not_cost_anchored", "opened_at_missing",
                      "opened_at_before_window", "no_bars_since_opened_at"] | None
    holding_start: date | None         # earliest lot opened_at actually used
    peak_close: Decimal | None         # P; non-null iff fallback is None
    peak_close_date: date | None
    trailing_level: Decimal | None     # non-null iff phase == "trailing"

class KeyLevelsPayload(BaseModel):     # frozen
    formula_version: str               # bump on any formula/constant change
    close: Decimal; close_date: date
    bar_count: int; range_bar_count: int
    range_high: Decimal | None; range_low: Decimal | None
    range_position_pct: Decimal | None
    range_unavailable_cause: Literal["too-few-bars", "flat-range"] | None
    ma20: Decimal | None; ma60: Decimal | None; ma60_deviation_pct: Decimal | None
    recent_low60: Decimal | None
    atr14: Decimal | None              # as of close_date
    anchor_source: Literal["cost", "close_not_held", "close_unknown"]
    anchor_price: Decimal
    stop_atr: LevelPoint | None; stop_fixed: LevelPoint; stop_suggested: LevelPoint
    cost_target: LevelPoint
    lifecycle: TargetLifecycle
    card_stop: CardCell | None         # None iff anchor_source == "close_unknown" (風控決策卡條件 7)
    card_target: CardCell | None       # same
```

**D-3 公式（規範性；常數集中於 `app/keylevels/params.py`，`Final`，不得由環境變數／設定檔決定）**
- `ATR_PERIOD=14`（TR 簡單平均，需 15 根）、`ATR_STOP_MULTIPLE=2`、`FIXED_STOP_RATIO=0.92`、`COST_TARGET_RATIO=1.2`（C1；見需要 CEO 決定 #1）。
- 停損 `stop_suggested = max(A − 2×ATR_t, 0.92A)`；ATR 不可得時 `0.92A`。
- 成本停利 `cost_target = 1.2A`。2R 不再計算、不再回傳。
- 移動停利 `trailing_level = max(P − 2×ATR_t, 0.92P)`；ATR 不可得時 `0.92P`。參數沿用停損公式，不新增可調參數。
- `ATR_t` 一律為最新一根（`close_date`）的 ATR14；不棘輪、不凍結（E1）。
- 位階／MA／近 60 日低點沿用現行前端定義逐字移植。
- 計算以 float64 進行（與回測共用），狀態判定以未量化值比較，序列化時才量化。

**D-4 生命週期（判定全在後端）**
1. `anchor_source != "cost"` ⇒ `phase="cost"`、`fallback="not_cost_anchored"`；`card_target` 為成本停利。
2. 否則取持有窗（D-5）；不可得 ⇒ `phase="cost"`、`fallback` 為對應原因；`card_target` 為成本停利，`relation="crossed"` 當且僅當 `close > cost_target`（案 A 行為）。
3. 持有窗可得：`P = max(close_i | holding_start ≤ date_i ≤ close_date)`。
   - `P ≥ cost_target` ⇒ `phase="trailing"`；`card_target` 為 `trailing_level`，`relation="crossed"` 當且僅當 `close < trailing_level`。
   - 否則 `phase="cost"`；`card_target` 為成本停利（此時必為 not_crossed）。
4. `card_stop` 恆為成本停損，`relation="crossed"` 當且僅當 `close < stop_suggested`（需要 CEO 決定 #2 的建議項）。
5. 距離：`not_crossed` ⇒ `(price − close)/close×100`、`basis="close"`；`crossed` ⇒ `(close − price)/price×100`、`basis="level"`（與第一期案 A 字面一致）。
6. 等號：狀態切換用 `≥`（與回測出場事件 `close >= entry×1.2` 一致）；`relation` 用嚴格 `>`／`<`（與案 A 字面「高於／低於」一致）。兩者只在恰好相等時不同，以測試釘住。
7. C1 下 `trailing_level ≥ 0.92 × 1.2A = 1.104A > A ≥ stop_suggested`，移動停利恆高於成本與成本停損。

**D-5 持有窗與 fail-closed**
- 基準價：由 `/api/advice` 已組好的 summary 中，與 `book.position_ids` 相同的那組持倉算出（同 symbol、market），以數量加權原幣 `avg_cost`（風控 R13／R14）。任一批數量或成本不可用，或各批幣別不一致，或與日線幣別不一致 ⇒ `close_unknown`。沒有持倉 ⇒ `close_not_held`。
- `holding_start` = 各批 `opened_at` 最早者；任一批為 null ⇒ `opened_at_missing`。
- 涵蓋判定：載入日線的第一根日期 > `holding_start` ⇒ `opened_at_before_window`（不擴大回看窗；寧可退回，不用部分窗冒充「持有以來」）。`holding_start` > `close_date`，或窗內無 bar ⇒ `no_bars_since_opened_at`。
- 持倉紀錄以「目前紀錄」為準（加碼改變平均成本、原地編輯成本都會改變狀態），不做持倉歷史快照；日線部分為 point-in-time。

**D-6 統一停利基準**：卡片大字、面板、價位階梯與回測一律以成本停利 `1.2A` 為唯一停利基準（**待 CEO 裁示 #1**）。若 CEO 改裁 2R，本 ADR 須修訂 D-3、D-4、D-8：狀態切換改為「持有窗內存在 i 使 `close_i ≥ target2R_i`（以 ATR_i 計）」並鎖住狀態；`five_conditions` 不得原地改語意，另開策略 id，並三版並列（×1.2／2R／2R＋移動停利）。

**D-7 移動停利期的停損格**：維持成本停損，不提升（**待 CEO 裁示 #2**）。

**D-8 回測**
- 第二期：`strategies.py` 改用 `app.keylevels` 的函式與常數，屬純重構；`five_conditions` 在固定 fixture 上的輸出須逐位元不變。`FIVE_CONDITIONS_NOTE` 不動。
- 第三期：新增策略 id（暫名 `five_conditions_trailing`），只改一處：把「收盤 ≥ 1.2×進場價 ⇒ 出場」改為「持有以來最高收盤 ≥ 1.2×進場價 ⇒ 轉入移動停利，之後收盤 ≤ trailing_t ⇒ 出場」。成本停損與 MA60 出場不變。
- 由 quant 事先在 `work/` 登記方法論與標的範圍後才可跑；新舊兩版依 backtest-protocol 全欄位並列（含 Buy & Hold、樣本內／樣本外分列），不擇優。
- 棘輪、Wilder ATR、其他倍數等變體一律須先修訂本 ADR，不得看過結果才加。
- 新策略在真實資料結果經審查前，不進 Kelly 帶入選單（比照 `format.ts` L387–388 的 REQ-3 路徑 b），並要有自己的風控核可說明句。

**D-9 與 ADR-0004 §4 的關係**：關鍵價位是固定算式的參考水位，不是規則引擎輸出；規則不得讀取。移動停利參考恆低於或等於持有以來最高收盤，只在成本停利參考被達到後出現，屬保護性參考水位，不構成 §4 所稱目標價。成本停利參考是既有面板算式，本 ADR 只移動其計算歸屬。於 ADR-0004「相關 ADR 與依賴」加入註記（不改決策內容）：
「〔2026-10-xx 交叉引用〕關鍵價位（停損參考、成本停利參考、移動停利參考）由 `app/keylevels/` 依固定算式計算，經 `/api/advice` 的同層欄位 `key_levels` 回傳，不是規則引擎輸出，規則與 `app.advice.*` 不得讀取；移動停利參考屬保護性參考水位，不構成本 ADR §4 所稱目標價。見 ADR-0018。」

（落檔註記：上述 ADR-0004 加註待本 ADR accepted 後由 tech-writer 於 ADR-0004 §4 加註；本檔落檔時未修改 ADR-0004。）

**D-10 字面治理**：第二期所有新增與改寫字面（見「字面影響清單」）由 creative-lead 起草、risk-compliance-officer 逐字核可，與功能同一 PR 上線；核可前不得合併。

**D-11 分期**
- 第一期（案 A，進行中，非 ADR 層級）：前端判定「已越過」與字面。前置條件：風控核可 creative-lead 草稿。約束：越過判定集中在單一純函式，第二期一處刪除。
- 第二期（後端化＋移動停利）：前置條件為 (a) 本 ADR accepted，含 CEO #1、#2；(b) 第一期已上線；(c) 字面清單全數經風控核可；(d) data-engineer 交出持倉 `opened_at` 為 null 或早於日線窗的檔數比例，用於界定退回揭露，不擋上線。
- 第三期（回測重跑）：前置條件為 (a) 第二期已合併，公式同源；(b) quant 的事先登記文件已在 `work/`；(c) 依 backtest-protocol 的資料品質檢查。結果無論好壞照實呈現；據結果改變畫面行為須另立 ADR。

### 字面影響清單（給 creative-lead 與風控）

第二期上線後會變成不實，或與新行為矛盾的字面：

1. `KEY_LEVELS_TARGET_ROW_TRAILING_NOTE`：「系統並未另行計算移動停利水位」會變成不實。
2. `KEY_LEVELS_BASIS_TARGET`：qualifier 裡的同一句不實；算式行的「2R=…」在 C1 下被移除；還要新增移動停利、P、`opened_at` 的算式行。
3. `KEY_LEVELS_TARGET_ROW_TRAILING_LABEL`「移動停利觀察」（MA20）：與新的「移動停利參考」撞名，必須改名或拿掉這列（K-12）。
4. `KEY_LEVELS_TARGET_STANDING_NOTICE`：「以下數字皆由固定算式自基準價推得」不實，因為移動停利來自 P；2R 賺賠比那句在 C1 下也不實。
5. `KEY_LEVELS_TARGET_ANCHOR_CROSS_REF`：「本卡數字所用之基準價，與停損參考卡片相同」在移動停利期不實。
6. `KEY_LEVELS_BASIS_CLOSE_DISTANCE`（含第一期改寫版）：「停損參考與停利參考皆由基準價推得」在移動停利期不實。
7. `KEY_LEVELS_TARGET_ROW_2R`，以及價位階梯 `target-2r` 那一階（headline）：C1 下要移除，headline 改為成本停利或移動停利。
8. `KEY_LEVELS_HEADER_UNADJUSTED_NOTICE`、`KEY_LEVELS_BASIS_UNADJUSTED_XREF`：列舉的失真項沒有包含「持有以來最高收盤／移動停利參考」，內容不完整。
9. 第一期草稿 §6 的前提「系統並未另行計算…仍為真」會失效。
10. 決策卡停利格的標籤：移動停利期要新增「移動停利參考」與「成本停利參考 X（已越過）」附註字面。
11. 第三期的新策略需要自己的說明句（比照 `FIVE_CONDITIONS_NOTE`）；方法論 L86–88、L97–99 那段「未做的變體」要更新（屬文件，非 UI）。

在 C1 下仍然成立、不必改的字面：`FIVE_CONDITIONS_NOTE`、`KEY_LEVELS_PANEL_DISCLAIMER`、`KEY_LEVELS_LADDER_NOTE`、`buildStopBasisHeldWithCost`（後者成立的前提是 CEO #2 採建議項）。

---

## Consequences（後果）

**好處**
- 單一來源：畫面與回測共用同一組函式和常數，2R 與 ×1.2 的分叉從構造上消除。
- 決策卡的收盤、價位與動作出自同一個 advice 快照。
- 移動停利期的水位恆高於成本（1.104A 以上），停損距現價 −27.6% 那種無保護意義的畫面，在停利格上不再出現。
- 狀態判定集中在後端並可測試；前端沒有比較邏輯。
- 選 C1 時，既有回測、`FIVE_CONDITIONS_NOTE` 與 Kelly 的 strategy 語意都不變。

**代價與壞處**
- 卡上停利大字從 ≤+16% 變 +20%，3037 的例子從 1,191.62 變 1,232.71，使用者會看到數字改變；2R 這個概念整個消失。
- 面板與價位階梯改依 advice envelope：advice 失敗時，原本只靠 bars 就能顯示的關鍵價位也會一起消失（失敗面變大）。
- 前端約 6 個檔案加上一批 vitest 要重寫；`componentWordingScan.test.ts` 有大量逐字釘住的字面要隨風控核可同步更新。
- **持有超過約 540 個日曆日，或 `opened_at` 為 null 的部位會退回案 A，拿不到移動停利。** 偏偏長期大賺的部位最需要這個功能。不擴大回看窗是刻意的取捨，擴大須另案評估 ADR-0009 的 coverage 與 IO。
- 用未還原收盤：除權息或分割後，P 仍停在除權前的高點，可能出現假的「已低於移動停利參考」。只能靠揭露承擔；成本錨點本身也是未還原值，兩邊口徑一致。
- E1 不棘輪：P 不變而 ATR 放大時，水位會下移（以 0.92P 為下限），與一般人對「移動停利」的語感不同，必須揭露。
- 持倉以目前紀錄為準：原地修改成本或加碼都會讓狀態回跳，不是歷史快照。
- float64 計算後量化，與搬遷前的前端數字在末位可能有微小差異，由 parity 測試設容差界定。
- 頁面上會有兩種「移動停利」：本面板的參考水位，與 playbook 使用者規則的 P2 移動停利。兩者定義不同，讀者可能混淆；本 ADR 只禁止兩者共用程式，不統一兩者。

---

## 對實作的約束（逐條可檢查）

**後端（dev-lead；回測部分 quant 協同）**
- **K-1**：`app/keylevels/` 是唯一實作。`app/backtest/strategies.py` 不得再定義 2、0.92、1.2、ATR 期數等數值常數，也不得保留 `_panel_atr` 的本地副本，一律 import（grep 加 import 測試）。
- **K-2**：常數放在 `app/keylevels/params.py`，型別為 `Final`；`app/keylevels` 內不得讀環境變數或設定檔（grep）。改任何常數就要升 `formula_version`，並修訂本 ADR。
- **K-3**：`app.advice.*`（engine、context、rules、loader）不得 import `app.keylevels`；規則的 `KNOWN_FIELDS` 不得含任何關鍵價位欄位（import graph 加 loader 測試）。
- **K-4**：`key_levels` 是 `AdviceResponse` 的同層欄位，不得放進 `advice` 字典。`build_advice` 輸出不變，既有 advice 測試的斷言不改也要能過。
- **K-5**：`app.keylevels` 不得 import `app.data.market_panel`、`app.dividends.adjust`、`app.playbook`、`app.backtest`（依賴方向只能是 backtest 引用 keylevels）。另外要把它加入 ADR-0016 K-16 的 import graph 測試。
- **K-6**：不得改 `DEFAULT_LOOKBACK_DAYS`；關鍵價位只用 `/api/advice` 已經 `load_bars` 的那一份日線，價格服務呼叫次數不得增加（計數測試）。
- **K-7**：`close` 一律取最新一根日線收盤，不得使用盤中報價或 `PriceInfo`。
- **K-8**：前端拿到的每一個價位、百分比、狀態、距離都必須來自後端欄位（見 K-11）。
- **K-9**：不變式：`anchor_source == "close_not_held"` 若且唯若 `held is False`；`anchor_source == "cost"` 時，所用持倉 id 集合等於 `position_ids`。
- **K-10**：`app.keylevels` 不得讀 playbook 的 `peak_close`；playbook 也不得讀 `app.keylevels`。

**前端（frontend-engineer）**
- **K-11**：刪除 `computeKeyLevels` 的計算本體與 `resolveKeyLevelsAnchor`；`app/lib` 與 `app/position` 的非測試檔中，不得出現 `0.92`、`1.2`、`ATR_STOP_MULTIPLE`、`FIXED_TARGET_RATIO`、`FIXED_STOP_RATIO`，也不得出現對價位做 `/ close`、`/ anchor` 的百分比運算（grep）。
- **K-12**：同一頁不得有兩個不同的數字都標「移動停利」字樣（vitest）。
- **K-13**：`key_levels` 為 null，或 `lifecycle.phase`、`relation`、`distance_basis` 不在已知集合時，對應格子一律顯示「—」且不畫距離（fail-closed）。
- **K-14**：面板閘門不得比圖表寬鬆（風控 R12）：必須同時滿足 `bars ok`、`advice ok`、`key_levels != null`。
- **K-15**：前端不得自行比較收盤與價位來決定狀態，只讀 `relation` 與 `phase`。

**第一期**
- **K-16**：案 A 的越過判定集中在一個純函式，第二期可以一處刪除。

---

## 測試要求

**後端（pytest）**
- **T-1 公式 golden parity**：在搬遷前，用現行 TS 實作對固定 fixture 產生 golden 值；後端對同一份 fixture 算出的位階、MA、ATR、停損、`1.2A` 須一致（相對誤差 ≤ 1e-9，再量化）。
- **T-2 生命週期表格驅動**：
  - 四種組合：成本期未越過、案 A 退回且已越過、移動停利期且 close > trailing、移動停利期且 close < trailing。
  - 四種 fallback 各至少一例。
  - 等號邊界：`P == 1.2A` 時切換到移動停利期；`close == cost_target` 或 `close == trailing` 時 `relation` 為 `not_crossed`。
  - ATR 不可得時退回 0.92P。
  - 多批持倉：取最早的 `opened_at`；任一批為 null ⇒ missing；幣別不一致 ⇒ `close_unknown`。
- **T-3 時間對齊**：
  - `opened_at` 前一天那根 bar 是全段最高，P 也不得等於它。
  - `opened_at` 當天的 bar 要計入 P。
  - ATR_t 只用 t−14..t 的資料。
  - 在 t 之後補上一根創新高的 bar，對 bars[:t+1] 的計算結果不得改變（截斷不變性）。
- **T-4 性質測試（property）**：
  - `0.92P ≤ trailing ≤ P`。
  - 持有窗內 P 對 t 單調不減。
  - C1 下 `trailing ≥ 1.104A`。
  - 持倉紀錄固定時，一旦進入移動停利期，往後任何 t 都不會回到成本期。
- **T-5 量化與序列化**：所有數值都是十進位字串，`distance_pct` 依 `distance_basis` 驗算。
- **T-6 回測重構零差異**：`five_conditions` 在既有 fixture 上，`weights` 與報告數字逐位元等於重構前；`FIVE_CONDITIONS_NOTE` 逐字不變。
- **T-7 守門測試**：import graph（K-1、K-3、K-5、K-10）、grep（K-2、K-11）、價格服務呼叫計數（K-6）、不變式（K-9）、advice 卡片欄位集合不變（K-4）。

**第三期（quant 主責，qa 審）**
- **T-8**：新策略的向量化路徑與逐 slice 重播逐 bar 一致（比照 `FiveConditionSeries` 的既有做法）。
- **T-9 shift 偵測**：
  - 把 P 或 ATR 整體往前 shift 一格（偷看 t+1）時，績效應明顯改變。若幾乎不變則判為失敗。
  - 另設 canary fixture：t+1 創新高、t 收盤 ≤ 用 t+1 的 P 算出的 trailing。正確實作在 t 不得出場。
  - 新策略要納入 `tests/test_lookahead_detection.py`。
- **T-10**：轉入移動停利期的那根 bar 不得同時出場（close == P > trailing）。

**前端（vitest）**
- **T-11**：四種狀態各渲染後端值且原樣顯示；「—」的 fail-closed 情形（K-13）；K-12 的撞名掃描；新字面逐字釘住並通過禁用詞掃描。

---

## 需要 CEO 決定（共 2 點）

**待 CEO 裁示（2026-10-04 尚未決定）**

1. **停利基準統一成哪一個？** 我建議 ×1.2（+20%）：回測、說明句與 Kelly 都不必改，切換判斷也最單純，移動停利一定高於成本。代價是卡上停利大字會從最多 +16% 變成 +20%，3037 會從 1,191.62 變 1,232.71，2R 這個概念拿掉。另一個選項是 2R：卡上數字不變，但回測要改語意並三版並列，而且低波動股票的停利會貼近成本（可能只有 +2%）。
2. **股價進入移動停利期後，停損格要不要跟著提高？** 我建議不提高，維持成本停損；移動停利已經顯示在停利格，停損格若改成同一個數字會重複，也會改變「停損參考」的意思。另一個選項是顯示 `max(成本停損, 移動停利)`。

（另有一個不需 CEO 現在決定、但已列管的事項：持有超過約 540 天的部位會退回案 A。是否擴大回看窗，等 data-engineer 交出比例後另案評估。）

---

## 未查證事項與作者揭露（tech-architect 原文，轉錄）

- 檔案行號是 2026-10-04 讀到的工作目錄狀態，沒有對照特定 commit。
- 以下內容未查證：
  - 沒有讀 `componentWordingScan.test.ts`、`decisionCard.test.ts` 全文。
  - 沒有讀 `app/advice/book.py::build_book_context` 的配對細節，只看到 `position_ids` 來自 `matched`。
  - 沒有確認 `/api/bars` 與 `/api/advice` 的日線在同一頁載入時是否必定相同。
  - 沒有量測持倉 `opened_at` 為 null 或早於日線窗的比例。
  - 3037 套用 ×1.2 的數字只用評估文件反推的 A＝1,027.26 計算，沒有實際資料。
- 價格精度採 quantize 0.0001 是我的設計選擇，沒有對照 TW 或 US 的報價最小跳動單位查證。

---

## 相關檔案（絕對路徑）

- /home/user/AICompany/work/research/決策卡-停利參考低於現價-評估-2026-10-04.md
- /home/user/AICompany/work/stock-desk-決策卡-已越過水位-起草-2026-10-04.md
- /home/user/AICompany/work/stock-desk-五條件回測-方法論.md
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/keyLevels.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/keyLevelsVisuals.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/entryObservation.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/format.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/KeyLevelsPanel.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/DecisionCard.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/PriceLadder.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/page.tsx
- /home/user/AICompany/apps/stock-desk/backend/app/backtest/strategies.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/backtest.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/advice.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/signals.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/summary.py
- /home/user/AICompany/apps/stock-desk/backend/app/positions/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/docs/adr/0001-record-architecture-decisions.md
- /home/user/AICompany/docs/adr/0004-stock-desk-建議引擎採規則式.md
- /home/user/AICompany/docs/adr/0006-stock-desk-kelly-輸入來源與模組邊界.md
- /home/user/AICompany/docs/adr/0009-stock-desk-日線快取以交易日判定新鮮度.md
- /home/user/AICompany/docs/adr/0016-stock-desk-持倉漲跌欄的計算基準與-fail-closed.md
- /home/user/AICompany/.claude/skills/backtest-protocol/SKILL.md
