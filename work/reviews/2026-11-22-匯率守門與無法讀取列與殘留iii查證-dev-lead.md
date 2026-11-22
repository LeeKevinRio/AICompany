# 匯率守門覆蓋、無法讀取列、ADR-0023 殘留 (iii)、X-3b log 與畫面對應：只讀查證（RC-582 第 1 點、RC-583 第 3 點、RC-586 第 6 點、RC-581 第 4 點）

- 查證者：dev-lead
- 日期：2026-11-22
- 查證時 HEAD：`6e6ac35f54368bd73eeeb7e03bc3308f5dd2cabe`（主工作樹，分支 `product/stock-desk`）
- 方式：全程只讀。只用 Read、Grep、Glob，以及非變更性的 git 指令（`rev-parse`、`status --short`、`log`、`show <commit>:<path>`）。
- 沒有做的事：沒有跑任何測試；沒有改檔、commit、開分支或 checkout；沒有讀 `.env*`；沒有碰 `apps/stock-desk/backend/data/*.db`；沒有執行 `.bat`；沒有看 `.claude/worktrees/`。
- 主工作樹的未追蹤檔都是別人放的，我沒有動。查證前後 `git status --short` 只多出別人新放的 `work/reviews/` 檔，HEAD 不變。
- 下文行號都是 `apps/stock-desk/` 底下的相對路徑，對應上述 HEAD。

---

## 本次結論

1. **RC-582 第 1 點：凡是把匯率乘進數字的路徑，最後都會經過 `usable_rate`。我沒有找到漏掉的路徑。**
   - 守門只有兩個入口，所有下游都繼承這兩處：
     - 估值器：`valuation.py:585`，同時管 `fx_now` 與 `fx_open`。
     - 決策卡、`/limits`、警示共用的 `_resolve_fx`：`book.py:1698`。
   - 有一個中間層本身不守門：`services/fx.py` 的 `resolve_fx_quote` 會把原值原樣傳下去。它的三個呼叫端（`/api/advice`、`/api/portfolio/limits`、警示快照）全都只會把它交給 `build_book_context`，進到 `book.py:1698` 守門，沒有任何呼叫端在守門前拿它算數字。
   - 另外查到三個相鄰的事實，供 tech-architect 評估 RC-582 第 3 點時參考：
     - (a) 決策卡上，匯率 0 和查無匯率**不是**完全看不出差別。詳見下方第 1 節「推論」。
     - (b) 匯率階梯判斷「主來源可用」時不看數值（`data/providers/fx.py:395-397`）。所以主來源回 0 時，系統不會改問備援，直接變成不估值。這是可用性問題，不是數字漏網。
     - (c) ADR-0023 已記的殘留 R1（台銀買價或賣價其中一邊是 0，中價變成真值的一半，仍能通過守門）和 R4（沒有合理範圍檢查）依舊存在，`usable_rate` 本來就不處理這兩種情形。
2. **RC-583 第 3 點：X-3c 完全沒有處理無法讀取的列。這種列不會被略過，也不會在畫面上揭露原因；它會讓整個讀取失敗。**
   - 只要有任何一列的市場不在 `TW`／`US`、或幣別不在 `TWD`／`USD`，`PositionStore.list_all()` 建 `Position` 時就會丟出驗證錯誤。X-3c 的判斷（`valuation.py:385`）根本跑不到。
   - 首頁摘要、庫存頁、決策卡、風險儀表都會回 HTTP 500。畫面上只看得到「無法載入投資組合摘要：請求失敗（HTTP 500）」這類泛用錯誤句，不會說是哪一列、也不會說是什麼原因。
   - 依 RC-583 第 3 點，這屬於「沒有揭露」的情形（畫面有錯誤句，但沒有指出原因），送風控判定；ADR-0017 待決點 2 現在還不能結案。
3. **RC-586 第 6 點：決策卡上沒有任何一句說「無法用風險上限確認加碼」。**
   - (A) 降級句在 `backend/app` 與 `frontend/app`（測試除外）都是零命中。
   - 加碼卡在這種狀態下確實會出現的句子，最接近的是主視圖的 2-O 句「有 N 條上限無法評估，不代表已通過；見下方建議卡。」。這句沒有說原因，也沒有和加碼建議綁在一起。
   - 說明原因的句子（W-a1、SYMBOL_UNVALUED_NOTE、D-d1／D-d2）都放在預設收合的建議卡裡。逐字內容與條件見第 3 節。
4. **RC-581 第 4 點：沒有。** 沒有任何測試在同一個情境裡同時斷言「X-3b 的 log 出現」與「畫面揭露 (a) 或 (b) 出現」。兩半各自有測試釘住，但沒有一支把兩者串起來。依指示，我沒有補寫。

---

## 各部門回報（dev-lead）

### 1. RC-582 第 1 點：匯率守門覆蓋

**事實（檔案:行號）**

守門的定義：
- `backend/app/data/price_guard.py:51-58`：`usable_rate` 把 `None`、0、負值、NaN、±inf 一律判為「沒有匯率」，沒有合理範圍檢查。
- `backend/app/data/providers/fx.py:82-91`：`FxRate.rate` 型別是 `Decimal`，模型接受 0 和負值；NaN 與 ±inf 由模型本身擋掉（測試 `test_unusable_fx_f1b.py:290-300`，KF-6）。

路徑 A：估值器。首頁每列、總覽合計、匯率貢獻、未實現損益，以及所有上限的分母都走這條。
- `backend/app/portfolio/valuation.py:536`（`fx_now`）與 `:545`（`fx_open`）都經過 `_latest_fx_on_or_before` → `_lookup_fx`。
- `:585` 是守門：`if not usable_rate(latest.rate)`。不通過就記 log（`:588-594`），回 `_no_fx_rate`（`:607-626`）。這和查無匯率的回傳完全相同：`UNAVAILABLE`、沒有 `as_of`、`source_note` 為空。
- `:418-434`：只要缺任一匯率，該列就是 `insufficient_data`，所有台幣數字都是 null。
- `:436-457`：`decompose`、`cost_twd`、`market_value_twd` 只在兩個匯率都通過時才會計算。
- `backend/app/portfolio/summary.py:280-291`：總覽的成本、市值、資產貢獻、匯率貢獻只加總 `status == "ok"` 的列；未實現損益是 `market_value - cost`（`:309`）。
- `summary.py:160-175` 的 `valued_market_value_twd` 也只加 `ok` 列。它是淨值量尺的來源（`api/settings.py:505-507`）。
- 上限分母：`book.py:619-659` 的 `_position_rollup` 只加 `ok` 列；`_book_equity`、`_sector_rollup` 同樣讀估值器的結果。

路徑 B：報價換算。決策卡、`/limits`、警示都走這條。
- `backend/app/services/fx.py:84-112` 的 `resolve_fx_quote` **本身不守門**：`rate=float(latest.rate)`（`:107`），`as_of`、`status` 都照實帶出（`:108-110`）。它只挑日期在目標日當天或之前的最後一筆，不往前找替代值。
- 呼叫端只有三個，全都直接交給 `build_book_context`：
  - `api/advice.py:211-226`（決策卡）。`:207` 先擋掉不可用的收盤價；沒有可用收盤價時不查匯率。
  - `api/portfolio.py:187`（`/limits`）→ `advice/book_limits.py:522-531`。
  - `alerts/snapshot.py:131-141`（警示）。排程透過 `scheduler.py:390`、`:405` 進到這裡。
- `backend/app/advice/book.py:1347` 呼叫 `_resolve_fx`。守門在 `:1698`：`if fx.rate is None or not usable_rate(fx.rate)`，不通過就回 `(None, FX_UNAVAILABLE_NOTE, None)`。
- `book.py:1415`、`:1421`、`:1422`：`rate` 是 None 時，`close` 和 `atr` 一起變 None，`fx_to_twd` 填 1.0 佔位，但沒有任何價格會乘到它。
- `book.py:1440`：`BookContext.fx_rate` 只寫入守門後的值。Grep `\.fx_rate\b`，`app/` 底下沒有任何地方讀它。
- `book.py:1373-1375`：揭露句只在 `applied`（通過守門）時附上。`book.py:1655` 也呼叫 `usable_rate`，但那裡只決定要不要記 log，不產生數字。

路徑 C：上限與股數試算。這條路徑只讀 `PortfolioContext.fx_to_twd`。
- `backend/app/advice/limits.py:834`：`fx_to_twd: float = Field(default=1.0, gt=0.0)`。這是第二道防線：0 或負值會讓模型驗證失敗並丟錯，不會靜默通過；+inf 擋不住，但上游已經擋掉。
- 讀它的地方：`price_twd`（`:893`）、`atr_max_shares`（`:1014`，第 4 條與股數試算）、`_check_per_trade_loss`（`:1361`）、`notional_caps`（`:1647`）、`project_position`（`:1685`）、`suggest_quantity_range`（`:1744`）。全部來自路徑 B 守門後的值。
- `advice/engine.py:346-360`：ATR 只在 `close is not None` 時才從訊號層補上，所以匯率被拒時不會讓 ATR 搭上 1.0 的佔位值。

Kelly 與其他會建立 `PortfolioContext` 的地方：
- `api/kelly.py:848`：`PortfolioContext(symbol=..., kelly=inputs)`，不帶匯率，也不讀匯率。`app/kelly/` 底下 Grep fx 是零命中。
- 第 5 條（分數 Kelly）的股數換算同樣經過 `price_twd`，屬於路徑 C。
- `alerts/engine.py:254`：`signal_context` 只帶收盤價（原幣），用預設的 `fx_to_twd`，但不換算任何台幣數字。

其他讀到匯率的地方：
- `data/providers/fx.py:281-291`：台銀買價、賣價取中價。這是在產生匯率，不是使用匯率。
- `data/providers/fx.py:395-397`：`FxRateLadder._is_usable` 只看狀態和有沒有資料，不看數值。
- 其餘有命中的檔案都只是字串或說明，沒有匯率算術：`leverage/drag.py:83`、`leverage/erosion.py:60`、`api/settings.py:144`。
- 前端：`frontend/app/lib/types.ts:157-171` 的 `PositionFx` 不含匯率數值欄位；Grep `rate`／`fx` 的乘法也沒有命中，前端不做匯率換算。

既有測試已經釘住的部分：
- `test_unusable_fx_f1b.py:279-286`：`usable_rate(` 在 `valuation.py` 出現 1 次、在 `book.py` 出現 2 次。
- `:302-310`：「不得在守門函式以外自行比較匯率與 0」的掃描範圍包含 `services/fx.py`、`alerts/snapshot.py`、`api/advice.py`、`api/portfolio.py`、`api/settings.py`。
- `:660-692`：0、負值、NaN、±inf 的報價在卡片上只得到「沒有可用數值」句，`close` 為 None。

**推論**
- 「匯率 0 讓上限靜默錯誤通過」的路徑，在這個 HEAD 已經全部被守門擋下。這符合 RC-582 第 1 點「全部覆蓋」的情形。
- 但「全部覆蓋」只是對 `usable_rate` 的定義而言：0、負值、非有限值。R1（中價只剩一半）與 R4（極大的有限值）仍會通過。這兩項 ADR-0023 `:513` 已列為殘留，不屬於這次的漏網。
- RC-582 的事實段寫：「畫面上，這一筆會和一般的匯率中斷**一樣**顯示為缺匯率」。這句只對首頁成立，決策卡另當別論：
  - **首頁**（估值器）：完全一樣。`_no_fx_rate` 共用同一個回傳，匯率徽章同樣是「資料不足」。
  - **決策卡、`/limits`、警示**（路徑 B）：`resolve_fx_quote` 把壞值的 `status`（例如 fresh 或 backup）與 `as_of`（壞值那天的日期）帶下去。`FX_UNAVAILABLE_NOTE`（`book.py:337-342`）會印出「（資料狀態 fresh、來源 …、匯率日期 2026-11-20）」。查無匯率時印的是「資料狀態 unavailable … 匯率日期 未知」。
  - 也就是說，卡片上的字面不同，但它沒有明說「來源給了壞值」，讀者要靠狀態和日期自己推斷。測試 `test_unusable_fx_f1b.py:639-663` 釘住了 0 匯率在 fresh 狀態下帶日期的句子。
- 匯率階梯的行為（主來源回 0 時不問備援）會讓「本來可以用備援估值」的情形變成不估值。這是保守方向，不會讓數字失真。

**未查證**
- 前端是否逐字顯示卡片的 `context_notes`：我只讀到 `page.tsx:572-580` 逐條渲染 `context_notes`，沒有逐一核對每種狀態。
- 台銀 CSV 實際會不會出現買價或賣價一邊是 0。
- yfinance 匯率會不會回 0 或負值。
- CEO 本機有沒有發生過以上任何一種情形。

### 2. RC-583 第 3 點：X-3c 對無法讀取列的行為

「無法讀取列」依 ADR-0017 `docs/adr/0017-*.md:165` 的定義：市場或幣別不在 Literal 集合內的列。

**事實（檔案:行號）**
- `backend/app/positions/models.py:33-34`：`Market = Literal["TW", "US"]`、`Currency = Literal["TWD", "USD"]`。git 歷史顯示從第一版（`78ac77b`，2026-07-24）起就是這兩組值，沒有改過。
- `models.py:131`：`str_strip_whitespace=True`。所以前後空白會被修掉，但大小寫不同（例如 `us`）、空字串、其他幣別（例如 `EUR`）都會驗證失敗。
- `models.py:119-130`、`:295-300`：讀取時用的 `Position` 繼承 `PositionInput`。市場與幣別是否相符的規則只放在寫入用的 `PositionWriteInput`（`:211-221`），所以「不符列」讀得出來；但 Literal 以外的值在讀取時就會失敗。
- `backend/app/positions/store.py:30-45`：`market TEXT NOT NULL`、`currency TEXT NOT NULL`，第一版就是如此（`git show 78ac77b:.../store.py`，第 30、33 行）。所以 SQL 層的 NULL 在這個 schema 下不可能出現。
- `store.py:195-200`：`list_all()` 對每一列呼叫 `_row_to_position`，中間沒有 try/except。
- `store.py:392-422`：`_row_to_position` 直接建 `Position(...)`。只要有一列不合法，就丟出 pydantic `ValidationError`，整個 `list_all()` 失敗。`Decimal(str(...))` 和 `date.fromisoformat` 遇到壞值也會丟例外。
- X-3c 的判斷在 `valuation.py:385`（`currency_matches_market`）。它的前提是 `Position` 已經建好，所以無法讀取的列根本走不到這裡。
- 經過 `list_all()` 的讀取路徑：
  - `portfolio/summary.py:260`（首頁摘要、決策卡、`/limits`、淨值量尺、警示快照都經過 `build_summary`）；
  - `api/positions.py:47`（庫存頁）；
  - `api/leverage.py:72`；
  - `api/kelly.py:1098`、`:1122`；
  - `api/sectors.py:216`；
  - `scheduler.py:293`。
  - 這些路徑上都沒有攔截 `ValidationError` 的 try/except（Grep `except` 在 `api/advice.py`、`api/portfolio.py`、`api/positions.py`、`portfolio/summary.py`、`alerts/snapshot.py` 零命中）。`main.py` 也沒有註冊 `ValidationError` 的處理器。
- `backend/app/api/server_error.py:44-58`：未處理的例外一律回 `500`，內容是純文字 `Internal Server Error`。
- `frontend/app/lib/api.ts:183-195`：錯誤內容不是 JSON，所以訊息是 `請求失敗（HTTP 500）`。
- 畫面上實際出現的句子：
  - 首頁摘要：`frontend/app/page.tsx:46-53` 顯示「無法載入投資組合摘要：請求失敗（HTTP 500）」。首頁持倉明細表只在成功時渲染（`page.tsx:72-75`），失敗時那一區是空的。
  - 庫存頁：`positions/page.tsx:223-225` 加上 `lib/inventoryWording.ts:58` 與 `components/ErrorPanel.tsx:12`，顯示「載入失敗：請求失敗（HTTP 500）」，旁邊有「重試」。
  - 標的頁建議卡：`position/[symbol]/page.tsx:534-537` 顯示「無法載入建議：請求失敗（HTTP 500）」。
  - 風險儀表：`components/RiskGauge.tsx:287-290` 顯示「無法載入風險儀表：請求失敗（HTTP 500）」。
- 排程：`scheduler.py:63` 的說明寫每個工作都有包覆，例外會帶 traceback 記進 log。這部分我只讀了說明，沒有逐一核對每個工作。
- 測試：Grep `tests/` 裡所有直接寫 positions 表的 SQL（`INSERT INTO positions`、`UPDATE positions`），沒有一支測試寫入 Literal 以外的市場或幣別，再斷言讀取行為。

**推論**
- 無法讀取的列**不會被略過**，**會報錯**。報錯會讓整個帳本讀不出來，不只是那一列。
- 畫面上有錯誤句，但只有 HTTP 500，沒有指出原因是某一列的市場或幣別無法辨識，也沒有指出是哪一列。CEO 也無法從庫存頁找到那一列來修，因為庫存頁本身也載入失敗。
- 方向上這是「全部不顯示」，不是「錯誤的數字」，所以不會讓上限靜默放行。但這種揭露不是 X-3c 提供的，也沒有說明原因。依 RC-583 第 3 點，這應該送風控判定；ADR-0017 待決點 2 現在不能結案。
- 這種列從哪裡來：app 的寫入路徑（`store.py:212-276`）只會寫入通過驗證的值，所以只可能來自 app 以外的寫入，例如手動改 DB 或其他工具。CEO 如果曾經遇過「首頁整個載不出來」，這是可能原因之一，但不是唯一原因。

**未查證**
- CEO 本機 DB 有沒有這種列：依限制沒有碰 `.db`。
- X-3a 腳本（`work/research/X-3-持倉幣別市場不符查證-腳本/`）本身的「unreadable」分類怎麼實作：我沒有讀。
- 前端 react-query 的重試次數與錯誤顯示時機。
- `opened_at` 是未來日期、`quantity ≤ 0`、產業不在清單內這些其他欄位不合法時，同樣會讓 `list_all()` 失敗。這是從同一個建構流程推得的，不在本題「幣別或市場」的範圍內，也沒有逐一實測。

### 3. RC-586 第 6 點：ADR-0023 殘留 (iii) 在決策卡上的呈現

**事實（檔案:行號）**
- (A) 降級句「本標的有持倉無法估值，無法用風險上限確認加碼；加碼建議改為觀望。」（ADR-0023 `:301`）：Grep「無法用風險上限確認」與「加碼建議改為觀望」，在 `backend/app`、`frontend/app`（測試除外）都沒有命中 (A) 的句子。「加碼建議改為觀望」只出現在另外兩個降級原因：
  - `engine.py:107`：風險預算改用預設值；
  - `engine.py:386`：防禦型規則同時命中。
- 加碼卡保留為 add 的條件（`backend/app/advice/engine.py:375-404`）：
  - 不是 insufficient_data；
  - 沒有防禦型規則同時命中；
  - 沒有任何上限 violated；
  - 風險預算不是預設值。
- 本標的有自己的持倉無法估值（`limits.py:1164-1182`，`own_lots > 0`）時：
  - 第 1 條、第 4 條（`limits.py:1081-1082`、`:1377-1378`）與第 5 條（`:1501` 起）在比率算得出來時都改報 not_evaluable，句子是 W-a1；比率算不出來時則是各自原有的「缺少…」句。這三條在這種狀態下都不會 passed。
  - `numerator_complete`（`:1185-1205`）讓第 1、4、5 條不能拿來試算股數；第 2 條的分子含本標的（`:1154`）；第 3 條要求 `book_fully_valued is True`（`:1200`）。所以 `notional_caps` 是空的，`suggest_quantity_range` 回 None（`:1744-1749`）。
- 前端股數判斷：`frontend/app/lib/quantityAbsenceWording.ts:47-58`。持有中的卡、action 是 add、`quantity_range` 是 null，會落到 `unspecified`（C-0）。

在這種狀態下（持有中、本標的持倉無法估值、action 仍是 add、沒有股數），卡片上實際會出現的句子：

| 位置 | 是否預設可見 | 逐字句子 | 出現條件 | 來源 |
|---|---|---|---|---|
| 決策卡主視圖「股數參考」格 | 可見 | 未提供股數 | 持有中、`quantity_range` 為 null、action 不是 hold（所以是 C-0） | `adviceWording.ts:221`；`DecisionCard.tsx:386-391` |
| 決策卡主視圖上限區塊（2-O） | 可見 | 有 {N} 條上限無法評估，不代表已通過；見下方建議卡。 | 第 5 條以外至少一條上限 not_evaluable，而且沒有 violated（有 violated 時開頭改成「另有」，但那時加碼會被擋下）。在這種狀態下第 1、4 條必然 not_evaluable，所以這句必然出現，N ≥ 2 | `riskRemediationWording.ts:84-87`；`limitNotices.ts:76-118`；`DecisionCard.tsx:418-421`、`:503`、`:289-290` |
| 操作摘要的「詳細」 | 預設收合 | 此建議未附帶數量區間（無法從風險上限推導）。 | 同 C-0 | `adviceWording.ts:212`；`operationSummary.ts:290-321`；`OperationSummaryPanel.tsx:242`、`:327` |
| 建議卡「風險預算輸入的假設與限制」 | 整張建議卡預設收合 | 此標的有 {count} 筆持倉無法估值，未計入本標的的部位市值與成本。 | 本標的有未估值的列 | `book.py:327`、`:1305-1306`；`page.tsx:545`、`:572-580` |
| 同上 | 同上 | 組合中有 {count} 筆部位無法估值（缺價格或匯率），未計入總資產；因本標的自身的持倉無法估值，第 1、4、5 條上限（單一標的佔比上限、單筆最大可承受虧損、分數 Kelly 部位上限）的比率會偏低。 | 帳本內未估值的列只有本標的自己的（D-d1）。開頭的成因句依未估值原因而不同：`:191`、`:215-218`、`:230-233` 各有一種，分組見 `:992-1040` | `book.py:191`、`:237`、`:292-297`、`:1067-1074` |
| 同上 | 同上 | （同上的成因句）；因本標的自身與其他標的的持倉皆無法估值，第 1、4、5 條上限（單一標的佔比上限、單筆最大可承受虧損、分數 Kelly 部位上限）的比率方向不定，可能偏高也可能偏低。 | 本標的與其他標的都有未估值的列（D-d2） | `book.py:305-311` |
| 建議卡內的上限清單，第 1、4、5 條各一句 | 同上 | 本標的有持倉無法估值，未計入部位市值與持股數，比率的分子不完整，只以已估值持倉計算的比率可能偏低；因此{上限名稱}本次不計算，回報 not_evaluable，無法判定是否違反。 | 該條上限的比率算得出來（通過前面各個「缺少…」的檢查），而且沒有達到上限 | `limits.py:409-413`、`:1208-1210`；`LimitsCheckList.tsx:51` |

**推論**
- **沒有任何一句說「無法用風險上限確認加碼」，也沒有任何一句把「無法估值」和「這張卡仍是加碼」放在同一句話裡。**
- 主視圖預設可見的只有兩句：「未提供股數」，以及 2-O「有 N 條上限無法評估，不代表已通過；見下方建議卡。」。
  - 2-O 是最接近的同義句，意思是「上限沒有確認通過」。但它不講原因（本標的持倉無法估值），也不講後果和加碼有什麼關係。
  - 2-O 也會在其他 not_evaluable 原因下出現，例如缺 ATR 或缺總資產，所以它不是這個狀態專屬的句子。
- 講原因的 W-a1、SYMBOL_UNVALUED_NOTE、D-d1／D-d2 都只在預設收合的建議卡裡。這和 ADR-0023 殘留 (viii)（`:312`）是同一個結構缺口。
- 依 RC-586 第 6 點，這比較接近「完全沒有」那一邊：沒有專屬句子，只有一句泛用的近義句。要不要算成揭露缺口，由風控判定。

**未查證**
- 有沒有測試釘住「本標的持倉無法估值、action 是 add、沒有股數」這個組合的卡片輸出。我 Grep 了 `tests/` 的「(iii)」與「殘留 1」，沒有找到相關測試，但沒有逐檔讀。
- 規則集實際上多常讓這種狀態保留為 add：這取決於規則命中情形，沒有實測。
- 候選卡不在本題範圍內：候選卡沒有本標的持倉。

### 4. RC-581 第 4 點：「有 log 就一定有畫面揭露」有沒有被測試釘住

**事實（檔案:行號）**

斷言 X-3b log 的測試只有兩處。Grep `does not match market` 在 `backend/tests` 只命中這兩個檔；前端零命中。

- `backend/tests/test_x3_currency_market_warning.py`：
  - 檔頭說明 `:13-17` 寫「Nothing here asserts *what* a mismatched row is valued at: X-3c (KX-A2) changes that on purpose」，明說這個檔不斷言估值結果。
  - `test_each_mismatched_row_is_logged_once_per_pass_with_the_pinned_message`（`:126-139`）：斷言 log 訊息逐字是 `position currency does not match market: id=… market=US currency=TWD` 與 `… market=TW currency=USD`，等級是 WARNING。
  - `test_a_matched_row_is_never_logged`（`:142-151`）。
  - `test_every_pass_logs_again_one_record_per_id`（`:154-166`）。
  - `test_the_log_line_carries_no_quantity_cost_or_note`（`:169-185`）。
  - `test_the_judgement_is_the_models_function_itself`（`:188-191`）。
  - `test_the_valuator_defers_to_the_shared_rule_for_every_row`（`:194-212`）：斷言 log 筆數等於列數。
  - `test_the_valuation_module_keeps_no_copy_of_the_market_currency_table`（`:215-229`）。
  - `test_the_check_changes_no_figure_of_any_row`（`:247-269`）：只比較相符的列。
- `backend/tests/test_x3c_currency_market_mismatch.py`：
  - `test_kxa2_the_x3b_warning_still_names_the_row`（`:361-372`）：只斷言 log 訊息，不斷言 `missing` 或任何畫面字面。

斷言畫面揭露的測試，都沒有用 caplog（Grep `caplog` 在 `test_x3c_currency_market_mismatch.py` 只出現在 `:362`、`:367`、`:369`）：
- `test_kxa2_a_mismatched_row_is_unvalued_without_any_lookup`（`:263-299`）：斷言 `missing == [CURRENCY_MARKET_MISMATCH]`，以及所有數字都是 null。
- `test_kxa2_the_summary_payload_carries_no_fx_for_a_mismatched_row`（`:338-358`）：斷言 API 回傳 `missing` 是這個代號。
- `test_rx4_sentence_b_is_the_same_live_and_cache_only`（`:600-631`）：斷言 (b) 成因句在 notes 裡。
- 前端 `frontend/app/lib/__tests__/currencyMarketMismatchRow.test.ts:130-200`：斷言 `missing` 是這個代號時，首頁列顯示 (a)「幣別與市場不符」（字面在 `lib/valuationWording.ts:29`）。

**推論**
- 程式碼層級的對應確實存在：`valuation.py:385-394` 同一個 `if`，先記 log 再回 `_currency_market_mismatch()`。
- 但測試層級只是「log 有測」「代號和字面有測」各自成立，沒有一支測試在同一個情境裡同時斷言兩者。所以只要有人把 log 移到別的條件下，或在 log 之後加一個提早 return，現有測試不一定會失敗。
- RC-581 第 1 點說「log 一出現，畫面就一定有 (a) 與 (b)」。在程式碼層級這句成立，但要補一個前提：畫面要真的被打開。log 也可能在沒有人看畫面時出現，例如排程的警示快照（`alerts/snapshot.py:130` → `build_summary`）。這不影響 RC-581 的用法，因為它要的是「畫面出現 (a) 或 (b)，就表示有這種列」這個方向，而這個方向成立。

**未查證**
- 依指示沒有補寫測試。要補的話，屬於 RC-581 第 4 點的 suggested 項，需要另外派工。

---

## 驗證

- 查證時 HEAD：`6e6ac35f54368bd73eeeb7e03bc3308f5dd2cabe`，分支 `product/stock-desk`。
- 沒有跑任何測試、lint 或 build。本件全部靠讀碼回答。
- 讀碼範圍：
  - 後端：
    - `data/price_guard.py` 全檔；`data/providers/fx.py` 第 82-130、270-300、356-400 行；
    - `services/fx.py` 全檔；
    - `portfolio/valuation.py` 第 370-681 行；`portfolio/summary.py` 第 160-175、255-315 行；
    - `advice/book.py` 第 191-340、405-430、619-659、976-1160、1197-1233、1244-1721 行；
    - `advice/limits.py` 第 92-98、395-420、820-900、1000-1020、1065-1215、1350-1385、1640-1760 行；
    - `advice/engine.py` 第 340-470 行；`advice/book_limits.py` 第 225-245、500-531 行；
    - `api/advice.py` 第 195-300 行；`api/portfolio.py` 第 160-215 行；
    - `alerts/snapshot.py` 第 100-150 行；`alerts/engine.py` 第 240-270 行；
    - `positions/models.py` 第 22-67、114-240、295-300 行；`positions/store.py` 第 28-50、190-212、388-422 行；
    - `api/server_error.py` 全檔；`data/diagnose.py` 第 378-465 行。
  - 前端：
    - `lib/api.ts` 第 150-230 行；`page.tsx` 第 20-110 行；
    - `position/[symbol]/page.tsx` 第 520-600 行；`position/[symbol]/DecisionCard.tsx` 第 370-520 行；
    - `position/[symbol]/OperationSummaryPanel.tsx` 第 225-330 行；
    - `lib/limitNotices.ts` 第 1-140 行；`lib/quantityAbsenceWording.ts` 全檔；`lib/riskRemediationWording.ts` 第 84-87 行；`lib/types.ts` 第 140-175 行。
  - 測試：`test_unusable_fx_f1b.py` 第 55-80、260-360、632-711 行；`test_x3_currency_market_warning.py` 第 1-30、120-140 行加上 Grep 結果；`test_x3c_currency_market_mismatch.py` 第 255-375、595-655 行加上 Grep 結果。
  - 文件：`docs/adr/0023-*.md` 的 Grep 命中段落（含第 292-312、513 行）；`docs/adr/0017-*.md:165`；tech-architect 盤點第 225-240 行。
- git（非變更性）：`rev-parse HEAD`、`status --short`、`log -- <store.py>`、`log -S'Currency = Literal' -- <models.py>`、`show 78ac77b:<store.py>`、`show 78ac77b:<models.py>`。

---

## 下一步

- **risk-compliance-officer**：
  - 依第 1 節，判定 X-13／F-1b 要不要從 high 改判。要一併考慮第 1 節「推論」的卡片字面差異，以及 R1、R4 殘留。
  - 依第 2 節判定無法讀取列的揭露缺口。這種列會讓整個帳本回 HTTP 500，畫面只有泛用錯誤句。在判定之前，ADR-0017 待決點 2 不結案。
  - 依第 3 節判定殘留 (iii) 是不是不必等 CEO 決定 ADR-0023 的揭露缺口：主視圖只有泛用的 2-O 句，沒有 (A) 句，也沒有同義的專屬句。
- **tech-architect**：
  - RC-582 第 3 點的評估，請納入「決策卡已經因為狀態與日期不同而字面不同，首頁則完全相同」這個現況，以及匯率階梯不看數值這件事。
  - 第 2 節如果要修（例如讀取時容忍無法讀取的列並揭露），規格由 tech-architect 出，這會碰到 C3「讀取不可變 500」的原意。
- **coordinator**：把本檔搬進 `work/reviews/`；追蹤清單補記 RC-581 第 4 點的結果是「沒有」，要不要補測試另外派工。
- **dev-lead**：等派工。這次沒有改任何程式碼或測試。

相關路徑：
- /home/user/AICompany/apps/stock-desk/backend/app/data/price_guard.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/fx.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/fx.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/summary.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/limits.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/positions/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/positions/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/server_error.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/limitNotices.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/quantityAbsenceWording.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/DecisionCard.tsx
- /home/user/AICompany/apps/stock-desk/backend/tests/test_x3_currency_market_warning.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_x3c_currency_market_mismatch.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_unusable_fx_f1b.py
