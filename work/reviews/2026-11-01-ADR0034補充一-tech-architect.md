# ADR-0034 補充一（鎖內分類、計數口徑、W-B2L API 形狀）與 P1 並行切面

- 審查者：tech-architect
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

| 項目 | 裁示 |
|---|---|
| **P2(e)** | **沿用**補充一 S-1 的條件：批次列存在、且 `status <> 'planned'`，才歸為「G1 擋下類」。G1 和 N-168 的鎖內分類**共用同一段 SQL 條件**，不得各寫一份。找不到批次列、或 `batch_no` 為 NULL 的列，歸 **W-B1 類**，與 G1 放行的列一致。這兩種情況以正常程式路徑碰不到，不另立第三類、不加字面。 |
| **P2(f)** | **要打 L4 戳記。** 打戳記的條件照 Decision 1，一字不改。戳記陳述的事實是「出清當時尚未結算、不在出清範圍」，對這類列同樣成立。G1 會擋下 claim，C-B6 的複製步驟永遠不會執行，所以戳記不會傳到批次上。 |
| **P3** | 技術口徑是**計列數**，因為字面寫的是「筆」。`{entry_items}` 逐列列出，股數逐列顯示，**不得依批次加總**。ADR-0035 Consequences:192 寫的「去重計批數」由我撤回，改以本口徑為準（ADR-0035 補充二）。和風控待對齊的地方有一處：同一個 planned 批次有多筆待成交列時，W-B1 寫的「判定成交即記為持有批次並扣除帳冊現金」只對最先成交的那一筆成立，其餘會被 G1 擋下。 |
| **P6** | **採 (a) 結構化欄位。(b) 拼進 `line` 標 VETO。** 前端 `DirectiveLedger` 依位置切 `line`：`splitDirectiveLine` 以「｜」分段（`playbookView.ts:190-192`），只渲染 `parts[0..2]` 與 `parts[4..6]`（`DirectiveLedger.tsx:25`、`:37`、`:48-50`）。拼在尾段，W-B2L 會被**靜默丟掉**；不加分隔符，又會混進「參考價」那一格。欄位名、`pending_directives` 的處理、與 ADR-0037 receipt store 的介面，見補充一 S-3。 |
| **P1** | Decision 12 的「N-171 → N-168」**可以靠介面切分讓兩者並行實作**，條件見下文。這項是否送 CEO，由 coordinator 判斷。 |
| **前端分工** | 分工照 coordinator 的預設：dev-lead 做後端加 `types.ts`，UI 另派 frontend-engineer。**有一點異議：合併時點。** W-B2 與 W-B2L 的同列顯示是風控 required，若後端單獨合進 product，CEO 立刻會看到少了這兩項揭露的頁面。所以 **UI 就緒前，N-168 不得合併進 product。** |

ADR-0034 確實需要補充一，ADR-0035 需要補充二。可直接貼上的文字見「各部門回報」。

## 各部門回報

### tech-architect（本人，唯讀）

#### P1：並行實作的條件

先說 Decision 12 的理由現況。「N-171 排在 N-168 之前」最早出自我的 4xx 評估（:24），當時的理由是「N-168 因 F5 暫停，N-171 不依賴 F5」。F5 已由 N-172a 定調，這個理由已經失效。剩下的耦合有三處，都可以切開：
- 兩者都在 `evaluate_today` 的結算之後讀取資料；
- 兩者都要在 `/today` 新增欄位；
- W-B2L 要套到 N-171 的清單上。

條件：
1. **先合一個切面 commit**，由 dev-lead 做，只動結構、不加字面、不改行為。內容如下：
   - `TodayResponse` 與 service 結果，加上三個預設 `[]` 的欄位：`pending_exit_directives`（N-171）、`entry_before_exit_directives`、`entry_before_exit_blocked_directives`（N-168）。
   - `evaluate_today` 在 `settle_pending` 之後，**只有一個讀取點**：同一個 conn、同一個快照，讀出「在途清單」。這一點讓兩案讀到一致的快照，也就是我 4xx 評估:124 的要求。
   - 所有 `DirectiveLine` 一律經由同一個 helper `_lines(directives, labeled_batches)` 建立，`labeled_batches` 先傳空集合。
2. 切面之後，N-171 與 N-168 只各自填入自己的清單與自己的 store 查詢，不改切面的形狀。
3. **合併仍然逐一進行**。後合併的一方 rebase 之後要重跑完整 CI。qa-reviewer 要實查兩份清單出自同一個讀取點。
4. N-171 仍需另立 ADR（補充 0033）並經風控定字面。它的 ADR 要引用這個切面與 S-3 的 W-B2L 規則。
5. 只要任一條件不成立，就回到 Decision 12 的順序。

#### P2(e) 補充說明

- 找不到批次列的 buy，`settle()` 不會動帳（`store.py:1068-1074`）。所以把它歸入 W-B1 類時，W-B1「記為持有並扣除帳冊現金」那句對它不成立。
- 這個落差的根因是 `settle()` 把沒有批次的列記為 executed，和 F8 同根。**要修應該修在 `settle()`（F8），不是在揭露端另立第三類。**
- 依據：目前沒有程式路徑會產生這種列。`ensure_batches` 只做 `INSERT OR IGNORE`（`store.py:450-457`），grep `DELETE FROM playbook_batches` 為 0 筆。

#### P3：口徑與風控對齊

| 字面 | 單位詞 | 技術口徑 | 狀態 |
|---|---|---|---|
| W-B1、W-B1p、W-B6 的 `{entry_count}` | 筆 | 列數 | 一致 |
| W-B3 的 `{count}` | 筆 | 列數。有 G1 時，同一批次最多只有一列成交，所以列數等於批數 | 一致 |
| G1 類揭露的 `{blocked_count}` | 筆 | 列數 | 一致 |
| S10 的 `{stale_batches}` | 批 | (symbol, batch_no) 去重 | 一致（既有規則：單位詞是「批」才去重） |
| W-B1 的語意 | — | 同一個 planned 批次有 2 列以上時，只有一列會成交 | **待風控**：要不要加一句「同一批次有多筆時，帳冊最多依其中一筆判定成交」 |

通則：**計數單位跟著字面的單位詞走。「筆」計列數，「批」計 (symbol, batch_no) 去重。股數一律逐列顯示，不跨列加總。**

### 可直接貼上的文字

**A1. ADR-0034 檔頭補充行**（貼在「狀態」行之後；本檔其餘原文不改）

```
- 補充一（tech-architect 2026-11-01，回應 `work/reviews/2026-11-01-N168開工前解讀點-dev-lead.md` P2(e)(f)、P3、P6）：Decision 1 的待成交買單於鎖內再分「W-B1 類／G1 擋下類」、L4 戳記範圍、計數口徑、W-B2L 的 API 形狀與欄位名、合併時點，以補充一為準；C-B3、C-B4、C-B8、C-B9 依補充一細化。全文見 `work/reviews/2026-11-01-ADR0034補充一-tech-architect.md` 第「B. 補充一全文」節；本檔原文不改（比照 ADR-0033、0035、0037 補充先例，CEO 可推翻改為另立取代 ADR）。
```

**A2. ADR-0035 檔頭補充行**

```
- 補充二（tech-architect 2026-11-01）：Consequences「N-168 的 W-B1 清單以 (symbol, batch_no) 去重計批數」一語由 ADR-0034 補充一 S-2 取代（計數單位隨字面單位詞：「筆」計列數）；「股數逐列顯示、不得加總」維持。本檔原文不改。
```

**B. ADR-0034 補充一全文**

```
# ADR-0034 補充一：待成交買單的鎖內分類、計數口徑、W-B2L 的 API 形狀

- 日期：2026-11-01
- 決策者：tech-architect
- 性質：補充 ADR-0034，不取代；同時細化 C-B3、C-B4、C-B8、C-B9。ADR-0034 原文不改。
- 依據：ADR-0035 補充一 S-1（G1 拒絕條件）；風控 `work/reviews/2026-10-31-CEO87回審與N172新字面-風控.md` 第三節（G1 擋下的列排除於 W-B1／W-B1p／W-B6）。

## S-1 鎖內分類與 L4 戳記（P2(e)(f)）

1. 待成交買單的界定照 Decision 1，一字不改：`action='buy' AND settled=0 AND status='pending'`，在 C-1 transaction 內用同一個 conn 讀取。
2. 讀出的列再分成兩類：
   - **G1 擋下類**：存在 (symbol, batch_no) 相同的批次列，且該批次列 `status <> 'planned'`。
   - **W-B1 類**：其餘所有列，包括批次為 planned、找不到批次列、`batch_no` 為 NULL。
3. 上述 G1 擋下類的條件與 ADR-0035 補充一 S-1 的 G1 拒絕條件，**必須出自同一個 store 常數或函式**，不得各寫一份；並有守門測試證明兩處引用同一來源。
4. **L4 戳記照 C-B3，對兩類都打**（條件照 Decision 1，`WHERE 戳記 IS NULL`）。G1 會擋下 G1 擋下類的 claim，C-B6 的戳記複製永遠不會對它們執行。
5. 讀取端（W-B1、W-B1p、W-B6、W-B3、C-B9）一律在讀取當下依第 2 點重新分類，**不得只看戳記**。出清當時屬 W-B1 類的列，之後可能轉成 G1 擋下類（例如同一批次的另一列先成交）。
6. 已知落差（範圍外，歸 F8）：找不到批次列的 buy 歸入 W-B1 類，但 `settle()` 對它不動帳。要修應修在 `settle()`，不在揭露端另立類別。
7. 測試：
   - (a) G1 擋下類的列被打上戳記，claim 被拒，批次標示不變；
   - (b) 同一批次一列 planned、一列成交後，重新分類正確；
   - (c) 兩處條件出自同一來源的守門測試。

## S-2 計數口徑（P3）

- 計數單位隨字面的單位詞：「筆」計列數，「批」計 (symbol, batch_no) 去重。股數一律逐列顯示，不跨列加總。
- 因此 W-B1、W-B1p、W-B6、W-B3 的 `{entry_count}`／`{count}` 與 G1 擋下類的 `{blocked_count}` 都計列數；`{entry_items}` 逐列列出，排序照風控（execution_date、symbol、batch_no 遞增）。
- 取代 ADR-0035 Consequences 中「以 (symbol, batch_no) 去重計批數」一語（見 ADR-0035 補充二）。
- 待風控：同一個 planned 批次有多筆 W-B1 類時，「判定成交即記為持有批次並扣除帳冊現金」只對最先成交的一筆成立，是否加註由風控定。

## S-3 W-B2／W-B2L 的 API 形狀與欄位名（P6）

1. **VETO：不得把 W-B2L 拼進 `DirectiveLine.line`。** 前端依「｜」分段、按位置渲染 `line`，拼接會被靜默丟棄或混進參考價那一格。
2. **DB 欄位**（經 `_MIGRATIONS` 加入，nullable TEXT，不回填）：
   - `playbook_directives.exit_stamped_on`（L4 戳記，值為出清 as_of 的 ISO 日期）；
   - `playbook_batches.entry_before_exit_on`（批次標示，`settle()` 成交時由戳記複製）。
   - 後者須貫穿 `BatchState`、`_BATCH_COLUMNS`、`_row_to_batch`、`save_batch`（C-B7）。
3. **`BatchSnapshot`**（C-B8 細化），新增三個欄位，預設皆為 None：
   - `entry_before_exit_on: date | None`：engine 只照抄 `BatchState`；
   - `entry_before_exit_label: str | None`：W-B2；
   - `entry_before_exit_note: str | None`：W-B2L。
   - 後兩者由 service 以 `wording.py` 常數渲染，engine 不得設定。
4. **`DirectiveLine.entry_before_exit_note: str | None = None`**，內容為 W-B2L 渲染結果，套用規則如下：
   - 只套在 `action='sell'` 的列（S、P、EMERGENCY）；
   - 該列的 (symbol, batch_no) 在建立回應時帶有標示，就套用；
   - S2（`batch_no` 為 NULL）：同一 symbol 有任一帶標示的 open 批次，就套用；
   - 所有 `DirectiveLine` 一律經由單一 helper `_lines(directives, labeled_batches)` 建立，並有守門測試（靜態掃描沒有其他 `DirectiveLine(` 建構點）。
5. 套用範圍：
   - `/today` 的 `directives`；
   - 出清回應的 `directives`；
   - **出清回應的 `pending_directives`（覆蓋列也要帶）**；
   - N-171 的 `pending_exit_directives`。
   - `SettledLineResponse`／`UnsettledLineResponse` 不帶（結算端由 W-B3 揭露）；風控若另有要求，以風控為準。
6. **清單欄位名**：
   - 出清回應（C-B4）與 `/today`（C-B9）一律用：`entry_before_exit_directives: list[DirectiveLine]`（W-B1 類）、`entry_before_exit_blocked_directives: list[DirectiveLine]`（G1 擋下類）。
   - 兩者預設 `[]`，不得混入 `directives`、`pending_directives`、`pending_exit_directives`（VETO-2）。
   - `/today` 版本只列已打戳記且未結算的列，在 `settle_pending` 之後讀取。
   - 刻意避開 `pending_entry_*`，以免和 N-171 的 `pending_exit_directives` 只差一字。
7. 出清回應的標示，由 C-2 第一項（open 批次）讀取時一併帶出標示欄，不另開讀取。回應必須自足。
8. **與 ADR-0037 receipt store 的介面**：
   - `ExitReceiptSink.accept(response)` 與 store state `{receipt, scrolledSeq}` 都不變。新資料只以加法欄位存在於 `response` 內。
   - 橫幅只從 `receipt.response` 渲染 `entry_before_exit_note`，不得用 `/today` 查詢補查標示（FE-C3 精神）。
   - `types.ts` 同步 `PlaybookDirectiveLine`、`BatchSnapshot`、`PlaybookEmergencyExitResponse`、`PlaybookTodayResponse`。

## S-4 前端與合併時點

1. 分工：dev-lead 做後端加 `types.ts`；W-B2、W-B2L 的同列 UI 由 frontend-engineer 在 ADR-0037 出清畫面包合進 product 之後實作。
2. **合併閘門**：W-B2、W-B2L 是風控 required 的同列揭露，UI 就緒前 N-168 不得合併進 product。後端可先完成並通過審查，但與 UI 一起合併，或在 UI 之後合併。
3. 前端守門：每個渲染 `PlaybookDirectiveLine` 的元件，都要渲染 `entry_before_exit_note`，並由測試證明。對象包括帳冊、出清橫幅的 `directives` 與 `pending_directives`、N-171 的清單。批次列要在 W-B2 之後緊接渲染 W-B2L。排版容不下時回審。
```

### 應經手但尚未經手
- **risk-compliance-officer**：P2(a)～(d)、P4、P5 由風控裁示。S-2 的待對齊項（同一批次多筆的 W-B1 加註），以及 S-3 第 5 點「結算清單不帶 W-B2L」，請風控確認。
- **CEO**：P1 的並行切面，由 coordinator 判斷是否送 CEO。
- **frontend-engineer**：S-4。

## 驗證

- 讀過：
  - `work/reviews/2026-11-01-N168開工前解讀點-dev-lead.md` 全文
  - 風控 CEO87 回審第三節與二-1（grep）、N-168 方案裁示的 W-B1／W-B2L 段落（grep）
  - ADR-0035 Decision 12 與 Consequences:192
  - ADR-0037 receipt store 條款（grep）
- 讀過的程式，對象是工作樹 product 線，N-172a 尚未合入：
  - `api/playbook.py`：80-86（`DirectiveLine`）、220-289（`TodayResponse`、`EmergencyExitResponse`）、292-296（`_lines`）
  - `models.py`：330-376（`Directive`、`BatchSnapshot`）
  - `wording.py`：960-984（`directive_line` 以「｜」組句）
  - 前端 `DirectiveLedger.tsx` 全文、`playbookView.ts:190-192`、`SettlementPanel.tsx:28`、`:37`
- P6 的 VETO 依據是讀碼判定：`DirectiveLedger` 只渲染 `parts` 的固定索引。我沒有實測拼接後的畫面。
- 沒有執行程式，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 下一步

1. coordinator 或 tech-writer：把 A1 貼進 ADR-0034 檔頭、A2 貼進 ADR-0035 檔頭；B 存成 `work/reviews/2026-11-01-ADR0034補充一-tech-architect.md`。
2. coordinator：決定 P1 是否送 CEO。若核准，我再給 ADR-0035 補充三，處理 Decision 12 與切面規格。
3. 風控：完成裁示之後，dev-lead 再開工。開工時以補充一的 S-1、S-3 為準。
4. qa-reviewer：S-1 第 3 點（單一來源）、S-3 第 4 點（單一 helper）、S-4 第 3 點（前端守門），列為 BLOCKING。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-01-N168開工前解讀點-dev-lead.md
- /home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md
- /home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md
- /home/user/AICompany/docs/adr/0037-stock-desk-排程台出清流程的狀態擁有層.md
- /home/user/AICompany/work/reviews/2026-10-31-CEO87回審與N172新字面-風控.md
- /home/user/AICompany/work/reviews/2026-10-31-N168方案裁示-風控.md
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/wording.py
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/DirectiveLedger.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/playbookView.ts
