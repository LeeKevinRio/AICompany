# F-1b 壞值匯率揭露裁示與無法讀取列修正規格（RC-582 第 3 點追加）

- 審查者：tech-architect
- 日期：2026-11-22
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報（含追加兩題）：R0-2 盤點更正、RC-585 事實摘要、RC-589 閘門普查與規則修訂；追加 (A) RC-582 第 3 點、(B) 無法讀取列的修正規格

全程唯讀，只用了 Read、Glob、Grep，沒有寫任何檔，也沒有讀 `.env*` 或碰 `apps/stock-desk/backend/data/`。
- **越界揭露（原任務）**：普查的第一次 Grep 用的 glob `{work,docs,.claude}/**` 掃到了 `.claude/worktrees/`。輸出只有檔名與命中數，我沒有讀那些檔，結果也不採用，之後改成分路徑重掃。
- 原任務的完整表格（42 列盤點表、41 組普查表、三份規則草案）已經在本 session 上一次 handback 交出。這次只附原任務的結論摘要，加上追加兩題的全文。如果要合成一份檔，請把兩次交件接在一起。

## 本次結論

**原任務（摘要）**
1. **計數更正**：盤點表更正為已被取代 13、內容改變 16、仍有效 13，合計 42，和風控的數字一致。分類一條都沒改。D-4 的取代時點改為 10-13，F-6／W-38 是 10-13 20:41（台灣時間）進 product。
   - 另外請風控核對兩處日期：換算成台灣時間後，`dev-up.bat` 的起點是 10-03 01:09，ADR-0022 PR 是 10-08 03:52。
2. **RC-585 三項事實摘要**：
   - **D-1**：「先不決定」並不中性，PR-2、PR-3 會一直卡在閘門上。
   - **X-11 第 4 點**：重審觸發在現行程式裡都沒有發生。另外，第 4 點之二不在 RC-585 的任何一份清單上，需要風控判定。
   - **E-6 (1)**：沒有可以獨立行動的內容，建議併進 X-11 第 4 點，當作「採納」那一側的代價。
3. **RC-589 普查**：共 41 組。多數可以改讀成「合併進 `product/stock-desk` 之前」，有 4 類不能直接改讀。另外找到 3 道已經落空、但不在 RC-587 名單裡的閘門：F1b-R13、X10-8、RK4c-R11。
   - 章程 §1 規定 main 不得綁定任何產品，所以規則分兩處寫：main 上寫產品中立的版本，放在 handoff-protocol 新的一節，並在 code-review-checklist 加一項檢查；stock-desk 的事實則寫在 product 線的 ADR。
   - 章程沒有規定這類修改要 CEO 核可，建議讓 CEO 知悉即可。

**追加 (A)：RC-582 第 3 點，F-1b 的壞值匯率要不要在畫面上另外揭露**
- 【裁示】**要做，範圍限於揭露**：
  - 估值器在「來源給了值但不可用」時，回傳另設的缺漏代號；
  - 決策卡把現在共用的那一句拆成「查無」與「不可用」兩句。
- 數字行為不變：照樣不估值，也不拿較早的一筆頂替（F-1b D4 不動）。
- 匯率階梯（主來源回 0 時不問備援）這次不改，理由寫在後面。
- 不需要新 ADR。

**追加 (B)：市場或幣別超出 Literal 集合的列，會讓整本帳回 HTTP 500**
- 【裁示】採用混合方案：
  - **庫存頁改成能逐列容錯**：列出無法讀取的列，並且可以用 PUT 更正或刪除；
  - **會產生數字或判定的讀取端，改成「明確失敗」**：不顯示任何數字，但用固定的錯誤代號取代泛用的 500，畫面也有專屬的原因句；
  - 只用來決定預抓哪些代號的內部路徑，改成略過無法讀取的列並記 log。
- 否決「部分計入、其他照常顯示」：無法讀取的列，連歸屬哪個標的都不確定。
- 否決在讀取端正規化：違反 ADR-0017 C3。
- 這個方案會修改 ADR-0017 C4「讀取不崩」的適用範圍，依 ADR-0017 第 105 行，**要另開 ADR**。
- ADR-0017 待決點 2：在這個修正合併進 product 之前不能結案；合併之後可以用 RC-583 的寫法結案，再補一段「無法讀取列由新 ADR 承接」。

## 各部門回報（tech-architect）

### 追加 (A)：RC-582 第 3 點評估

#### 現況（dev-lead 11-22 查證，加上我讀碼補充；HEAD 6e6ac35）
- **首頁與總覽**（估值器）：壞值和查無完全一樣。兩者共用 `valuation.py:607-626` 的 `_no_fx_rate`，缺漏代號都是 `fx_now`、`fx_open`，前端都顯示「查無即期匯率」「查無建倉匯率」（`valuationWording.ts:25-26`）。
- **決策卡、`/limits`、警示**（`book.py:1698-1709`）：兩種情形用的是同一個常數 `FX_UNAVAILABLE_NOTE`（`book.py:337-342`），差別只在填入的狀態與日期。壞值會帶來源原本的狀態與日期，查無則是 `unavailable`／「未知」。另外有兩點：
  - 〔我補的事實〕這一句放在 `context_notes`，也就是**預設收合的建議卡裡**（`page.tsx:547`、`:572-580`）。主視圖的 2-O 句兩種情形完全相同。
  - 句子裡沒有明說「來源給了不可用的數值」，讀者要自己從狀態和日期推斷。
- **匯率階梯**：`FxRateLadder._is_usable`（`data/providers/fx.py:394-396`）只看狀態與有沒有資料，不看數值。主來源回 0 時，系統不改問備援，直接不估值。
- **觀測**：唯一的訊號是 `valuation.py:588-594` 的 log。依 RC-581、RC-582，這條路無法在不叫 CEO 讀 log 的前提下落實。
- 匯率守門已經全部覆蓋（dev-lead 第 1 節），所以「上限靜默錯誤通過」的方向已經關上。剩下的問題是觀測不到。

#### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (a1) 不做，維持 F-1b D3 | 零改動 | 首頁永遠分辨不出；X-13 永久「無法觀測」 | 觀測缺口變成常設，只能照實記錄 |
| **(a2) 另設缺漏代號，決策卡句子拆成兩句（採用）** | 數字行為零差異；畫面有專屬原因句，可以比照 X-9 讓畫面承接，必要時用憑記憶回答的題目 | 要改 API 的缺漏代號集合、前端型別與字面，並改寫 F-1b 釘住「兩者完全相同」的測試；新句子要經風控審 | 中：CEO 看到一句無法自己處理的句子，字面不得暗示要他做什麼 |
| (a3) 階梯改看數值，壞值時改問備援 | 可用性提升 | 壞值被備援蓋掉後，原因反而消失，只剩「備援匯率」徽章；混源頻率上升，會動到 X-10、X-12 現況 low 的前提，也牽動 ADR-0011 的階梯與 ADR-0015 | 本次不採。日後如果要做，必須和 (a2) 同一個 PR，原因句照樣出現，並另出 ADR 修訂 ADR-0011 |
| (a4) 只改決策卡的句子 | 改動最小 | 首頁仍然分不出來；那一句仍在收合區 | 不足 |

#### 決策（不需要新 ADR）
- 數字層的不變式（不估值、不頂替）完全保留，只在「原因」這一層分開；這和 X-3c 新增代號的先例相同（ADR-0017 D-X4）。
- 落檔方式：在 F-1b 任務單 D3，以及 ADR-0023 提到 F-1b 的那一段加註：「D3 的『與查無完全相同』改讀為『數字與頂替規則完全相同，原因代號不同』」。原文保留。
- 合併之前，X-13 維持「有條件、無法觀測」。合併之後，風控可以比照 RC-581 改由畫面承接。
- 10-09 到合併這段期間有沒有發生過，仍然觀測不到，**不得回溯結案**。

#### 對實作的約束（qa-reviewer 可逐條檢查）
1. **新代號**：`fx_now_unusable`、`fx_open_unusable`。
   - 只在「查詢窗內有資料，但最新一筆 `usable_rate` 為假」時使用。
   - 和 `fx_now`、`fx_open` 分別互斥。
   - 查無時照舊用 `fx_now`、`fx_open`。
2. **數字零差異**：
   - 同一筆持倉在兩種代號下，`status`、所有金額欄位、`FxInfo` 的 `data_status`、`as_of`、`source_note` 都要相同；`source_note` 仍為空。
   - 要用參數化測試釘住「除了 `missing` 以外全部相等」。
   - F-1b D4 的不頂替測試不得刪除或放寬。
3. `fx_memo` 的快取值要連同不可用的標記一起存，同一輪估值裡同一個 `(pair, target)` 的代號要一致。
4. `valuation.py:588-594` 的 log 開頭與欄位零差異。F-1b R-3 的 grep 目標就是這一行。
5. **book 層**：
   - 帳本層的成因分組（W4／W5「缺價格或匯率」）先把新代號併進同一組，不另設成因句。
   - 「不可用的數值也算缺匯率」這個讀法要送風控確認；風控如果要求分開，另立一組，字面照常送審。
6. **決策卡**：
   - `_resolve_fx` 在 `fx.rate is None` 時沿用現句；在 `rate` 有值但 `usable_rate` 為假時，改用新常數（暫名 `FX_UNUSABLE_NOTE`）。
   - 句子的位置不變，仍在 `context_notes`；這是 CEO 09-19 裁定的位置，不在本案範圍內移動。
7. **前端**：
   - `valuationWording.ts` 為兩個新代號各加一個標籤；型別聯集同步更新。
   - 實作者要在 PR 說明列出前後端**所有讀 `missing` 代號的地方**，逐處寫明怎麼處理（包括 `book.py:992-1040` 的分組、警示、`diagnose`、匯出）。
8. **字面**：
   - 由 creative-lead 起草、風控逐字審。
   - 不得叫 CEO 做任何事，不得引導他改設定或重抓資料，不得出現「log」，也不得寫成「系統已處理，所以沒有問題」。
   - 字面只說「來源提供的數值不可用，所以未換算、未計入」。
9. 不改 `usable_rate`、`FxRateLadder._is_usable`，也不加合理範圍檢查。R1（中價只剩一半）、R4（極大的有限值）照舊是殘留；PR 說明要寫明新句子不涵蓋這兩種情形。
10. **測試**：`test_unusable_fx_f1b.py` 中斷言「壞值與查無完全相同」的各支，改成「數字相同、代號不同」，並逐支列在 PR 說明裡。斷言「不得在守門函式以外比較匯率與 0」的掃描（`:302-310`）不得縮小範圍。
11. **流程與時點**：
    - 走 qa-reviewer 加 Codex；首頁列的顯示要 qa-e2e 看 375 與 1280 兩種寬度；字面送風控。
    - 這是獨立 PR，不得和 (B)、RC-556、接線、退役等 PR 放在同一個 PR。
    - 本案會改到 `app/`，合併時點受 RC-556 裁示約束 8 (a)～(d) 同樣的限制：在 CG-2 合併 M 到登記完成之間，以及 #156 期間，都不得落地。
    - 不碰 `code_digest` 範圍（`app/forecast`、`app/outlook`、`app/dirdef`、`app/data/session_calendar.py`），要附 diff 為空的證明。

#### 不改匯率階梯的理由（回應派工指定的第二個現況）
- 現在的行為是保守方向：主來源回 0 時直接不估值，數字不會失真，代價是那段期間美元持倉沒有估值。
- 如果改成問備援，壞值的事實會被備援值蓋掉，畫面剩下的「備援匯率」徽章也說不出原因，觀測反而更差。
- 改動會讓混源更常發生，動到 X-10、X-12 的等級前提，以及 ADR-0011、ADR-0015。
- 結論：列為另案選項，前提是 (a2) 已經落地，並且另出 ADR。

### 追加 (B)：無法讀取列的修正方向與規格草案

#### 現況（dev-lead 第 2 節，加上我讀碼補充）
- `positions/store.py:195-200` 的 `list_all()` 逐列呼叫 `_row_to_position`（`:391-422`），中間沒有容錯。只要有一列建 `Position` 失敗，整批就失敗，所有讀取端最後都變成 500（`api/server_error.py:44-58`）。
- 會失敗的不只是市場和幣別：數量、成本、日期解析、產業封閉清單、`_sector_is_tw_only` 也一樣。
- 〔我補的事實〕這種列不一定只來自 app 以外的寫入。ADR-0017 第 105 行寫明，產業封閉清單日後刪減類別時，app 自己寫入的舊列也會變成無法讀取。
- **修正路徑的事實**：
  - `store.update`（PUT，`:242-276`）先 `UPDATE` 再讀，**不會先建構舊列**，所以整列重填的 PUT 可以修好這種列；
  - `delete`（`:387-389`）不讀列；
  - `patch_fields` 寫完會讀回，如果沒有修到失敗的那一欄，仍然會失敗；
  - 但庫存頁現在本身就載入失敗，所以 **CEO 在畫面上找不到修正入口**。
- **ADR-0017 的原意**：
  - C4：「`list_all()` 遇 TW＋USD 舊列不拋例外，範圍僅限本 ADR 新增的規則」；
  - 已接受缺口：「三層保護：讀取不崩」；
  - 第 105 行：其他讀取期 validator 的崩潰屬於「已知不在本案」，**要另外處理時須另開 ADR**。

#### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (b1) 全面逐列容錯：無法讀取的列當成未估值、不計入，各畫面照常顯示並附原因 | 最符合 C4「讀取不崩」的原意；和 X-3c 的處理一致 | 市場可能不明，所以那一列是不是「本標的」無法確定，第 1、4、5 條的方向判定沒有可靠依據；要動到所有讀取端與 book 層的分組；`SummaryPosition` 需要市場、幣別、數量，這種列給不出來 | 中高：會顯示少了一列的數字，但歸屬未知。不採 |
| (b2) 讀取端全部改成明確錯誤（固定代號，不再是泛用 500） | 改動最小，最保守 | 庫存頁也一起失敗，CEO 仍然沒有修正入口，只能手改 DB，而這是禁止的 | 不足 |
| **(b3) 混合（採用）**：庫存頁逐列容錯並列出這種列；會產生數字或判定的讀取端改成明確錯誤；只決定預抓代號的內部路徑略過並記 log | 沒有任何部分數字（保守）；原因明確；CEO 有一步就能完成的修正入口；修好後一切恢復 | 修好之前，首頁、決策卡、風險儀表、警示仍然整體不可用 | 中：警示會持續停止，要在字面與通知上揭露（由風控判定） |
| (b4) DB 自動遷移，例如 `us` 改成 `US` | 不用 CEO 操作 | ADR-0017 D-X2 已否決自動遷移；而且只能處理少數幾種形態 | 否決 |
| (b5) 讀取時正規化，或放寬 Literal | 不用改 store | 等於在 `Position` 上加讀取期規則，違反 C3；像 `EUR` 這種值仍會失敗 | 否決 |

#### 決策（ADR 草案，交 tech-writer 在 `product/stock-desk` 落檔，狀態 proposed）

- 標題建議：「stock-desk 持倉讀取遇到無法讀取的列時，分成列出與明確失敗兩種處理」。
- 這份 ADR **修改 ADR-0017 C4 的適用範圍，不取代 ADR-0017**。
- **Context**：
  - 這種列會讓整本帳回 500，沒有原因，也沒有修正入口（dev-lead 11-22）；
  - 來源包括 app 以外的寫入，以及封閉清單變動；
  - ADR-0017 第 105 行要求另開 ADR。
- **Options**：(b1)～(b5)，見上表。
- **Decision**：採用 (b3)。
- **Consequences**：
  - 好處：
    - 原因明確；
    - 有修正入口；
    - 不產生任何部分數字。
  - 壞處：
    - 只要有一列無法讀取，所有數字畫面和警示都不可用，直到修好為止；
    - 對使用者的阻斷程度和現在相同，只是說得出原因；
    - 新增一組使用者可見字面與一個 API 錯誤契約。
  - 殘留：
    - 修好之前沒有任何數字；
    - 警示停止期間，CEO 只有在開啟畫面時才會知道。

#### 對實作的約束（qa-reviewer 可逐條檢查）
1. **store 介面**：
   - 新增 `scan_all() -> PositionScan`，內容是 `readable: list[Position]` 與 `unreadable: list[UnreadableRow]`。
   - `UnreadableRow` 只帶 `id: int`、`symbol: str | None`（原字串去掉前後空白，用來辨認是哪一列），以及 `failed_fields: tuple[str, ...]`（欄位名稱）。不帶數量、成本、備註，也不帶失敗欄位的原始值；要不要顯示原始值，由風控與 creative-lead 決定，決定之前不提供。
   - 逐列攔截的例外限於：pydantic `ValidationError`、`ValueError`、`decimal.InvalidOperation`、`TypeError`。其他例外照常往外拋。
2. **`list_all()` 的行為**：
   - 先掃完全部列。只要有任何一列無法讀取，就拋出新的具名例外 `UnreadablePositionsError(count, ids)`；不得在第一列失敗就中止，也不得拋出未分類的 `ValidationError`。
   - 全部可以讀取時，回傳值與現行逐位元組相同。
3. **C3 不變**：`Position`、`PositionInput` 零 diff，`positions/models.py` 零 diff。
4. **API**：
   - 註冊 `UnreadablePositionsError` 的處理器，回 JSON `{"code": "positions_unreadable", "count": n}`。狀態碼建議 409，不得是 500。
   - `GET /api/positions` 改用 `scan_all()`，回 200：`items` 是可讀的列，另加 `unreadable` 欄位。
   - 其他所有經過 `list_all()`、產生數字或判定的端點，都走明確失敗：summary、advice、limits、設定頁淨值量尺、leverage、警示快照，以及 sectors 等。
5. **呼叫端逐一分類**：dev-lead 要在 PR 說明列出全部呼叫端並逐一寫明歸類，依據是 Grep 結果：`summary.py:260`、`api/positions.py:47`、`api/leverage.py:72`、`api/sectors.py:216`、`data/diagnose.py:128`、`directory/sector_backfill.py:88`、`scheduler.py:293`、`demo/seed.py:396`、`:492`。
   - 分類規則：會產生使用者可見數字或判定的，走明確失敗；只決定要預抓或回填哪些代號的，改用 `scan_all().readable`，並為無法讀取的列記一行固定開頭的 WARNING，內容只帶 id 與欄位名稱。
   - `api/kelly.py:1098`、`:1122` 讀的是 Kelly 輸入的 store，還是持倉的 store，要先確認；dev-lead 的清單把它列進來了，我從呼叫形式看不出來。
6. **PATCH**：對無法讀取的列，寫入後讀回失敗時，回同一個錯誤代號，不得是 500。PUT 與 DELETE 不改。
7. **前端**：
   - `api.ts` 辨識這個錯誤代號；首頁、建議卡、風險儀表、庫存頁顯示專屬原因句，取代「請求失敗（HTTP 500）」。
   - 庫存頁列出無法讀取的列，提供「整列重填（PUT）」與「刪除」兩個入口。重填的表單不得預填無法讀取的欄位。
8. **字面**：由 creative-lead 起草、風控逐字審。原因句要說明「有 N 筆持倉紀錄無法讀取，修正之前不計算任何數字」，以及警示是否停止（依風控判定）；不得引導 CEO 改 DB 或執行指令。
9. **排程**：警示工作遇到 `UnreadablePositionsError` 時，記一行固定開頭的 WARNING，含筆數與 id，不得拋出未分類的 traceback。要不要經 ADR-0029 告警通道送出，交 devops-sre 與風控決定，本案不實作。
10. **測試**：
    - 每一類失敗各一支，包括：市場小寫、不明幣別、空字串、數量 ≤ 0、日期無法解析、產業不在清單內、US 列帶產業，斷言 `scan_all` 的分類與 `list_all` 拋出具名例外；
    - 端點層斷言錯誤代號，以及「沒有任何數字欄位」；
    - 庫存頁斷言可讀的列照常顯示；
    - ADR-0017 的 T-11 保留。
11. **時點**：和 (A) 一樣是獨立 PR，受同樣的合併時點限制（CG-2 合併 M 到登記完成之間、#156 期間不得落地），也不碰 `code_digest` 範圍。走 qa-reviewer 加 Codex、qa-e2e、風控。

#### 對 ADR-0017 待決點 2 的影響
- **現在不能結案**：RC-583 第 3 點的前提是「無法讀取的列會被略過，而畫面沒有任何揭露」。查證結果比這更差：這種列不會被略過，而是讓整本帳讀不出來，畫面只有泛用錯誤句。這是新的揭露缺口，等級由風控判定。
- **本修正合併進 product 之後**，可以結案為：「本機舊資料清查改由讀取端承接：不符列由 X-3c 承接，無法讀取列由〈新 ADR〉承接；CEO 本機實際筆數未查證，記為未知。」不得寫成「0 筆」或「清查完成」。
- ADR-0017 第 105 行的「已知不在本案」，由新 ADR 承接其中「讀取崩潰」的部分。「把讀取期 validator 移到寫入模型」仍然不在範圍內，不做。
- 〔推論，不得當成證據〕如果 CEO 本機真的有這種列，從那一列出現起，首頁、庫存頁、決策卡都會整體回 500。這只說明可能性偏低，依 RC-583 第 1 點，仍要記為「未知」。
- X-3a 腳本雖然有 `unreadable` 分類，但依 RC-553 P1，不得請 CEO 執行。

## 驗證

**這次追加讀過的檔**
- dev-lead 查證檔全文（277 行）。
- ADR-0017 第 84～180 行加 Grep。
- `valuation.py` 第 370～629 行。
- `data/providers/fx.py` 第 356～405 行。
- `book.py` 第 205～244、326～345、1680～1721 行。
- `store.py` 第 185～277、385～423 行。
- `summary.py` 第 240～320 行。
- Grep：`api/positions.py`；`list_all()`、`get()` 的全部呼叫端；`CURRENCY_MARKET_MISMATCH`；`valuationWording.ts` 的 `fx_now`、`fx_open`。

**原任務讀過的檔**：見上一次 handback 的「驗證」段。

**沒有查證的事**
- 警示推播會不會帶出 `FX_UNAVAILABLE_NOTE`。
- 前端所有讀 `missing` 代號的地方（這是 (A) 約束 7 交給實作者列的）。
- `api/kelly.py` 那兩處讀的是哪一個 store。
- 排程各工作遇到例外時的實際行為（dev-lead 只讀了說明）。
- 所有畫面行為都是讀碼推定，沒有實機看過，也沒有跑任何測試。

## 下一步

- **風控**：
  - (A)：確認約束 5（新代號併入 W4／W5 這個讀法）；之後由你判定 X-13 改判的等級。
  - (B)：判定無法讀取列的揭露等級；判定 (b3) 的殘留，也就是「修好前警示停止」要不要另外通知；判定約束 1 要不要提供原始值。
  - 原任務：見上一次 handback 的下一步。
- **creative-lead**：(A) 的 `fx_*_unusable` 標籤與 `FX_UNUSABLE_NOTE`；(B) 的原因句與庫存頁上這種列的字面。兩組都送風控逐字審，不和新知悉包放在同一批。
- **tech-writer**：
  - (A)：在 F-1b 任務單 D3 與 ADR-0023 的 F-1b 段加註。
  - (B)：在 product 線落檔新 ADR（proposed），並在 ADR-0017 的 C4 與第 105 行加註「由 ADR-NNNN 承接」。
- **dev-lead**：
  - 字面定稿後，(A)、(B) 各開一張任務單、各自一個 PR，照約束實作，並照 RC-556 的時點約束排合併。
  - 先確認 `api/kelly.py:1098`、`:1122` 讀的是哪一個 store。
- **frontend-engineer**：負責 (A) 約束 7、(B) 約束 7 的前端部分。
- **coordinator**：
  - 追蹤清單加三列：(A)、(B)，以及「ADR-0017 待決點 2 等 (B) 合併後才結案」。
  - X-13 在 (A) 合併之前維持「有條件、無法觀測」。
- **CEO**：這次沒有需要決定或操作的事。

相關路徑：
- /home/user/AICompany/work/reviews/2026-11-22-匯率守門與無法讀取列與殘留iii查證-dev-lead.md
- /home/user/AICompany/docs/adr/0017-stock-desk-持倉部分更新與寫入路徑的市場幣別一致性.md
- /home/user/AICompany/docs/adr/0023-stock-desk-風險上限分子不完整時的非對稱判定通則.md
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-F-1b-匯率非正值的估值防護.md
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/fx.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
- /home/user/AICompany/apps/stock-desk/backend/app/positions/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/positions/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/summary.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/positions.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/server_error.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/valuationWording.ts
- /home/user/AICompany/apps/stock-desk/backend/tests/test_unusable_fx_f1b.py
- （原任務相關路徑見上一次 handback）
