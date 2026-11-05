# ADR-0035 補充五 修正一（N-188）

- 審查者：tech-architect
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

「補充五 修正一」全文在下方 code block，可以直接附到補充五檔末。風控確認之前，補充五連同本修正都不得合併、不得部署。

1. **X-4（回應 (c) VETO）**：floor 機制整個拿掉，不採「計數到才升 floor」。legacy 的 NULL 戳記改用列本身的 id 當水位下界：`COALESCE(s.settled_after_id, s.id) >= L.id`。
   - 這樣在構造上保證第一句為真。backend 重啟、`_init_schema` 重複執行，都不再影響判定。
   - 少掉一個 state 鍵，X-14 原本要改的三條斷言只剩一條要改。
   - 代價是新增一種已知漏報 (a-3)「部署／離線修復邊界」。部署條件成立時，這項漏報為零；條件不成立時，後果只是漏報，不會變成不實陳述。
2. **讀碼證實了風控的推論，另外發現一處要注意。**
   - `PlaybookStore` 只在每個 backend process 啟動時建一次（`api/deps.py:311-319`），所以 floor 會在每次重啟時升高。dev 環境用 `--reload`，每次改檔也會升一次。
   - 風控參考方向裡的計數「`settled = 1 AND settled_after_id IS NULL`」照字面會把順延、跳過這類非下單列也算進去。這些列寫入時就是 `settled = 1`（`store.py:584`），新版也不寫戳記。結果 floor 幾乎每次重啟還是會升，回到被否決的狀態。
3. **S2 納入觸發（依 (d)）**，述詞拆成三支，兩種合併先後都有對應版本：
   - S2 列以 claim 為準；
   - 逐批列在 S2 已結算時，以稽核表中「這批移動股數大於 0」為準；
   - 逐批列在 S2「已 claim、還沒結算就中斷」時，以這批在讀取當下是否合格為準。單調性證明在 M1-2 第 2 點。
   - 結果 (a-2) 在兩種先後下都不存在。X-3 仍然是「漏報只限兩種」，但組成改成 (a-1) 加 (a-3)。
4. **ADR-0040 (乙) 的影響**：
   - N-188 note 出現的總次數會從接近 0 回到正常水準，因為 S/P 列恢復產生了。
   - 每一列被觸發的機率不會因 (乙) 而提高：結算不看 `data_status`，同一個請求裡也一律先結算、再寫入新列。
   - 沒有新的漏報路徑。我列了四條給 ADR-0040 起草者的約束。
   - X-10 第 6 點已經被風控兩份裁示取代，這次改寫成不再設 N-190 的上線耦合。
5. 不需要升級 CEO。

## 各部門回報

### tech-architect（本人，唯讀）

**評估摘要**
- X-4 的 floor 方案比較了五個，採 F-3（以 s.id 當水位下界）。比較表在 M1-1 第 2 點。
- 風控的計數方案（F-1）不採。原因有三：
  - 計數必須限定在下單列，否則會失效；
  - 部署條件一旦不成立，F-1 失敗時會產生不實陳述，F-3 只會漏報；
  - F-1 還要多一個 state 鍵。
- 兩份風控裁示有一處不一致，我以 B-(d)1 為準，寫成 R7 送風控確認：
  - N-177 裁示 A-3 寫「照 TA 第 3 節」，也就是 S2 以稽核表「移動股數大於 0」為準；
  - 定稿裁示 B-(d)1 明文禁止只看移動股數。

**補充五 修正一（全文，交 coordinator 附到補充五檔末）**

```
# ADR-0035 補充五 修正一：X-4 legacy 戳記、S2 納入觸發、與 ADR-0040 (乙) 的交互（N-188）

- 日期：2026-11-05
- 決策者：tech-architect（規格）。依據：
  - 風控 `work/reviews/2026-11-05-N168視覺規範R1R3與補充五及N188定稿-風控.md` B-(c) VETO、B-(d) required；
  - 風控 `work/reviews/2026-11-05-N177修復與N190字面裁示-風控.md` A-1、A-3、A-4、B-5；
  - `work/reviews/2026-11-05-N177修正範圍評估-tech-architect.md` 第 3 節；
  - CEO #108。
- 性質：修正補充五，不另立 ADR。本修正取代補充五的下列條文：
  - X-2 第 1 點的 `#:` 註解要求、第 2 點、第 5 點的讀取清單、第 6 點；
  - X-3 全部；
  - X-4 第 3 點的 floor 段與部署條件、第 4 點；
  - X-9 的 N188-T8、T9、T15；
  - X-10 第 4、6 點；
  - X-11 的 QB-18.2、.5、.8、.11；
  - X-12 的對應項；
  - X-14 第 2 點。
  未列出的條文不變。
- 狀態：風控確認本修正之前，補充五（含本修正）與風控 C 節的定稿常數都不得合併、不得部署。
- 程式位置：2026-11-05 本 checkout 的 `apps/stock-desk/backend/app/`。全部是讀碼判定，未執行。

## M1-1 X-4 修正：拿掉 floor，NULL 戳記以列本身的 id 當水位下界

1. 讀碼確認風控 B-(c) 的推論成立：
   - `PlaybookStore()` 由 `api/deps.py:311-319` 的 `lru_cache` 在每個 process 建一次，`__init__` 會呼叫 `_init_schema`（`store.py:664-668`）。所以 floor 每次 backend 啟動都會升高；dev 的 `uvicorn --reload` 每次改檔也會升一次。
   - legacy 列的戳記永遠是 NULL，`COALESCE(NULL, :floor) >= L.id` 對重啟前寫入的 L 恆為真。述詞含 buy，所以凡是曾經有買進成交的 symbol，當日的 S/P 列在重啟後全部觸發，而觸發來源的 claim 可能早於 L 好幾天。第一句因此不為真。
   - 另外發現一處：風控方向參考的計數「`settled = 1 AND settled_after_id IS NULL` 的列數」，照字面會算進非下單列。`_insert_directives` 對順延、跳過、無動作的列以 `settled = 1` 直接寫入（`store.py:584`），新版也不寫戳記，所以每次評估計數都會增加，floor 幾乎每次重啟還是會再升。若要用計數，必須限定 `action IN ORDER_ACTIONS`。
2. 方案比較：
   | 方案 | 內容 | 優點 | 缺點、風險 | 判定 |
   |---|---|---|---|---|
   | F-1 計數門檻 | 記錄 NULL 戳記的下單列數，增加時才升 floor | 沿用 floor，改動小 | 計數沒限定下單列就會失效；部署條件不成立時，失敗方向是不實陳述；多一個 state 鍵；X-14 三條斷言都要改 | 不採 |
   | F-2 NULL 一律不觸發 | 移除 COALESCE | 永遠不會不實 | 漏報比 F-3 多：連 s.id ≥ L.id 這種可以確定為真的情況也丟掉 | 被 F-3 支配，不採 |
   | **F-3 以 s.id 當水位下界** | `COALESCE(s.settled_after_id, s.id) >= L.id` | 依構造為真；沒有 floor、沒有 state 鍵；重啟對判定零影響；部署條件不成立時只會漏報 | 新增 (a-3)，要靠部署條件歸零 | **採用** |
   | F-4 legacy 變體句 | NULL 觸發時改出一句不講先後的句子 | 不漏報 | 要新字面，風控多審一輪；若仍是每次重啟升 floor，大量列同時出現，習慣性忽略的問題還在 | 不採 |
   | F-5 NULL 列改用時間戳 | `settled_at > created_at` | 舊列也能判 | X-4 第 1 點已判定不嚴格，牆鐘倒退時第一句可能為假 | 不採 |
3. 決策（O-3′）：
   - 刪除 `STATE_SETTLED_AFTER_ID_FLOOR`、`_init_schema` 內的 floor 寫入，以及 `:floor` 參數。對 N-188 而言，`_init_schema` 只多 `_MIGRATIONS` 的一個欄位，沒有其他 diff。
   - X-2 第 2 點的水位條件逐字改為 `COALESCE(s.settled_after_id, s.id) >= L.id`。
   - 嚴格性依據：
     - claim 以 `WHERE id = ?` 更新、rowcount 為 1，表示該列在 claim 當下已存在，所以 claim 當下的 MAX(id) ≥ s.id。
     - 因此 s.id ≥ L.id ⇒ 真實水位 ≥ L.id ⇒ claim 晚於 L 提交。
     - NULL 戳記列只會往「不觸發」偏，不會讓第一句不實。
     - 有戳記的列，判定與 O-3 相同。
   - 重啟、`_init_schema` 重複呼叫、多個 process 同時啟動，對判定都沒有影響，因為不再有任何啟動時寫入的狀態。
   - 禁止事項維持：不得回填 `settled_after_id`；不得用時間戳判定 NULL 戳記列的先後；不得新增 state 鍵來代替 floor。
4. 代價：新增已知漏報 (a-3)，見 M1-2 第 5 點。X-4 第 4 點（重啟後多報）刪除。
5. **部署條件（devops-sre；取代 X-4 第 3 點的部署條件）：**
   - **適用時機**：只限從「不寫戳記的版本」換成「寫戳記的版本」：
     - (i) N-188 首次部署；
     - (ii) 回滾到不含 N-188 的 build 之後再重新部署。
     N-188 上線之後，凡是部署不含 N-188 的 build（例如從舊 commit 打的 hotfix 或 ADR-0040 build），一律視為回滾。其他部署與重啟都不需要這項條件。
   - **一律要遵守**：不得同時有新、舊版 backend 處理請求（compose 先停再起）。讀碼確認 scheduler 不碰 playbook：`app/` 內只有 `api/` 與 `playbook/` 引用 `PlaybookStore`。
   - **條件 A（預設）**：停服務後、新版啟動前，以唯讀查詢確認下式為 0：
     `SELECT COUNT(*) FROM playbook_directives WHERE action = 'sell' AND rule_id IN ('S1','S2','P1','P2','P3') AND settled = 0`
     - 依據：`/today` 會顯示的 X-1 列一定還沒結算。L 的預定執行日 E = next_trading_day(data_date)（engine.py:1122）。要結算 L，必須有 L.symbol 在 E 的 bar；data_date 取各序列最新的 bar 日（service.py:1587），所以一旦有了 E 的 bar，data_date ≥ E，頁面就改顯示下一個預定執行日。前提是之後的載入不讓資料日倒退。
     - 所以這個查詢涵蓋部署後所有可能被顯示的 L，而且不必實作交易日曆。
     - 條件 A 成立時，部署後被顯示的 L 都是部署後才寫入，L.id 大於任何舊版 claim 的真實水位，(a-3) 為零。
   - **條件 B（A 不成立時的替代，要風控確認可以用）**：
     - 確認沒有任何舊版 claim 晚於現存未結算的 S/P 賣單，也就是下式為 0：
       `settled = 1 AND settled_after_id IS NULL AND action IN ('buy','sell') AND settled_at >= (上述未結算 S/P 賣單的 MIN(created_at) 往前推 10 分鐘)`
     - 這是運維探針，時間戳只用來判斷部署時機，不進產品判定。時鐘誤差的後果只是 (a-3) 漏報，不會產生不實陳述。
   - **A、B 都不成立**：延後部署，等條件 A 成立；或送風控逐案審。
   - **探針**：比照 `scripts/n172_duplicate_probe.py`：唯讀、對複本執行、不 import app、不連網。結果附在 release 紀錄。
   - **離線修復**：N-177 (B) 這類離線工具若在 N-188 上線之後才 apply，會在沒有 claim 的情況下改動帳冊，同樣歸 (a-3)。apply 前也要符合條件 A 或 B。

## M1-2 X-2／X-3 修正：S2「已判定成交」納入觸發（風控 B-(d)）

1. **共用常數，只有一份定義：**
   - `S2_FILL_ENTRY`：N-177a 的進入條件 `status='executed' AND action='sell' AND rule_id='S2' AND batch_no IS NULL`（N177-C4）。
     - 以一個常數定義。`settle` 的 S2 分支判斷，和 `_read_settled_since` 用的 SQL 片段，都從它導出，不得各寫一份字面。
     - 放在 `BOOK_MOVING_SETTLEMENT_SQL` 旁邊，緊接在 `def settle` 之前。
   - `S2_ELIGIBLE_BATCH_SQL`（別名 `b`）：`b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL`。
     - 這是 N177-C5 的合格批次，與 engine.py:213、:420 同義，由 C5 的 parity property test 綁住。
     - N-177a 的分配查詢與本述詞共用這一份。
   - `<FILL_MOVES>`：N-177a 的 M2 加法表，表名由 dev-lead 定。本述詞只用 `directive_id`、`batch_no`、`shares_moved` 三欄。
   - **定義者**：照計畫 N-177a 先合，三者由 N-177a 定義，N-188 只引用。若 N-188 先合，前兩者由 N-188 定義，N-177a 改為引用。
   - `BOOK_MOVING_SETTLEMENT_SQL` 文字不變：N-177a 不改逐批動帳分支，N-177b 不動帳。它的 `#:` 註解改為：「對應 `settle` 的逐批動帳分支；`settle` 的動帳分支若再修改，必須同步修改本常數與 `S2_FILL_ENTRY`。」
2. **X-2 第 2 點改為（N-177a 已合的版本）：**
   `EXISTS (SELECT 1 FROM playbook_directives AS s WHERE s.symbol = L.symbol AND s.settled = 1 AND COALESCE(s.settled_after_id, s.id) >= L.id AND ((<BOOK_MOVING_SETTLEMENT_SQL> AND (L.batch_no IS NULL OR s.batch_no = L.batch_no)) OR (<S2_FILL_ENTRY 的 SQL> AND (L.batch_no IS NULL OR EXISTS (SELECT 1 FROM <FILL_MOVES> AS m WHERE m.directive_id = s.id AND m.batch_no = L.batch_no AND m.shares_moved > 0) OR (NOT EXISTS (SELECT 1 FROM <FILL_MOVES> AS m WHERE m.directive_id = s.id) AND EXISTS (SELECT 1 FROM playbook_batches AS b WHERE b.symbol = L.symbol AND b.batch_no = L.batch_no AND <S2_ELIGIBLE_BATCH_SQL>))))))`

   各分支：
   - **(A) 逐批動帳**：與補充五相同。
   - **(B1) L 是 S2 列**：同 symbol 有任何一筆 executed S2 被 claim，就觸發。以 claim 為準，不看稽核表（風控 B-(d)1）。
     - 零移動的 S2、claim 之後還沒 settle 就中斷的 S2，都會觸發。這屬於 N2 類多報，第一句「判定了…成交」仍為真。
   - **(B2) L 是逐批列、S2 已結算**：稽核表有這張 S2 在 L.batch_no 移動股數大於 0 的紀錄，才觸發。
     - N-177a 只在合格批次上移動股數，所以這表示 S2 結算時這批屬於合格批次，符合 B-(d)2。
   - **(B3) L 是逐批列、S2 已 claim 但沒有任何稽核紀錄**（claim 後、settle 前中斷）：這批在讀取當下合格，才觸發。
     - 讀取當下合格 ⇒ claim 當時合格。理由（讀碼）：
       - L 是這批的 S/P 賣單，而 engine 只對 open、cost 非 NULL、remaining_shares > 0 的批次發這類單（engine.py:420），所以 L 評估時這批已經是 open；
       - 批次 open 之後不會回到 planned（G1），remaining_shares 只減不增，cost 不再改。
       這個前提由 N188-T19 的 property test 釘住。
     - 所以 (B3) 不會讓「涉及這批」為假。「claim 後當機」也因此不會成為 X-3 之外的新漏報路徑：這是把 B-(d)1 的考量延伸到逐批列。
   - **不觸發的情況**：S2 已結算，但在 L.batch_no 移動 0 股（股數已分配給較舊的批次）。這批的帳冊股數沒有因這張 S2 改變，不屬於 X-3 定義的漏報；B-(d)2 是必要條件，不是充分條件。送風控確認。
   - 只允許 SELECT。讀取點與呼叫次數照 X-2 第 3 點，不變。
3. **X-2 第 5 點（R-4 判定）的讀取清單改為**：
   - 當日 logged 列；
   - `settled = 1` 的列；
   - 批次列的現況（是否存在、status、remaining_shares、cost）；
   - `<FILL_MOVES>`。
   批次現況與稽核表都是已結算的帳冊事實，不是在途資料。(a)～(c) 不變。
4. **與 N-177a 的先後：**
   - **照計畫，N-177a 先合：**
     - N-188 照第 2 點全文實作，以 N-188 分支起點（含 N-177a）的 `settle` 為準，(a-2) 不存在。
     - N-177a 若最後採 M0（不設稽核表），(B2) 無法成立，PR 停住送 TA 與風控。
   - **N-188 先合：**
     - 實作第 2 點去掉稽核表的版本：(B) 改為 `<S2_FILL_ENTRY 的 SQL> AND (L.batch_no IS NULL OR EXISTS (SELECT 1 FROM playbook_batches AS b WHERE b.symbol = L.symbol AND b.batch_no = L.batch_no AND <S2_ELIGIBLE_BATCH_SQL>))`。
     - 這時 S2 不動帳，批次維持 open，(B3) 的論證同樣成立。不得帶著 (a-2) 上線（B-(d)）。
     - 之後 N-177a 的 PR 必須在同一個 PR 內改成第 2 點全文。否則 S2 關閉批次之後，逐批列就失去觸發。同一個 PR 還要改 N188-T9、T18、T19，並送風控確認。沒改，N-177a 不得合併。
   - **不論哪一種先後**，以下都放在 N-188 的 PR 內：
     - W-B2LS 回審；
     - 風控 A-3 的釘住測試（N-177 評估第 3 節第 4 點）；
     - A-4 (b) 的翻轉測試。
5. **X-3 修正：**
   1. **前提改為**：非並發情況下，帳冊股數只由 `settle` 改變，包括 N-177a 的 S2 分支與它的私有 helper。離線修復工具除外，歸 (a-3)。N188-T15 擴充到涵蓋 N-177a 的 SQL 寫入點。
   2. **漏報仍只限兩種，但組成改變：**
      - **(a-1) 並發窗口**：內容不變，仍然「不自癒」。docstring 加寫窗口寬度（風控 B-(b) suggested）：
        - 讀帳點是 `evaluate_today` 在載入序列之後呼叫的 `list_batches()`（service.py:1616）；
        - 窗口到 `commit_evaluation` 的 `BEGIN IMMEDIATE`（:1636）為止；
        - 中間只有本地 DB 讀寫（`portfolio_state`、`symbol_states`、`fast_market_state`、`apply_effects`、`save_fast_market`）和純計算，**不含取資料**；遇到鎖時，最長等到 busy timeout；
        - claim 只在 backend process 裡發生，所以並發來源只有同一個 process 內並行的請求。
      - **(a-2)**：刪除。依第 4 點，兩種先後下都不存在。
      - **(a-3) 部署／離線修復邊界（新增）：**
        - 情況一：不寫戳記的版本做了 claim（NULL 戳記），claim 落在 L 寫入之後，而且被結算那一列的 id 小於 L.id，這時不觸發。
        - 情況二：離線工具在 L 寫入之後改動了帳冊。
        - 只會在 M1-1 第 5 點的時機發生，範圍限於當時仍會被顯示的 L；到下一個預定執行日，這些 L 就不再顯示。
        - 條件 A 成立時為零；只靠條件 B 時，殘留只來自時鐘誤差。
        - 不自癒，理由同 (a-1)。
   3. X-3 第 3 點不變：出現其他漏報路徑，一律 PR 停住。
   4. **已知多報改為下列各項，第一句都為真：**
      - N2；
      - 批次列在結算之後才建立；
      - 零移動的 executed S2 觸發 S2 列；
      - claim 後、settle 前中斷的 S2，觸發 S2 列與 (B3) 的逐批列；
      - S2 列因同 symbol 新批次買進成交而觸發（「也可能少於」那一支為真）。
      legacy 列不再是多報來源。

## M1-3 ADR-0040 (乙) 上線後的影響（依 CEO #108 的條件判斷）

1. (乙) 的範圍（CEO #108）：只改 `is_usable` 與 snapshot／`LoadedSeries` 的欄位；指令列照實記 `cached_stale`；不用 runtime 旗標。
2. 觸發頻率：
   | 項目 | 現況（N-190 預載實測成立、CEO #107） | (乙) 上線後 |
   |---|---|---|
   | X-1 範圍內的 L 數量 | 被預載的持有標的整天都是 `cached_stale`，S/P 不評估，幾乎沒有 L | 回到每天正常評估的數量 |
   | 單一 L 的觸發條件 | — | 不變：L 寫入之後、預定執行日輪替之前，同 symbol 或同批有 claim。實際來源只有兩種：某檔開盤價的 bar 晚到，由之後的請求結算；以及 `POST /settle`。同一個請求內，結算一律在寫入 L 之前（service.py:1572 先於 :1636） |
   | claim 的時點 | 結算不看 `data_status`（service.py:1051-1057 只找預定執行日的開盤價） | 不變，(乙) 不改結算 |
   | `_read_settled_since` 的呼叫次數 | 每次 `/today` 一次 | 不變 |
   - **結論**：N-188 note 出現的總次數，會從接近 0 回到正常水準，因為現在根本沒有 L 可以觸發；但單一 L 被觸發的機率，不因 (乙) 而提高。
   - 「重新評估更常發生」增加的是同一預定執行日內新 K1 的寫入。新寫入的列晚於先前的 claim，依 X-4 不觸發；舊列的判定不受影響。
   - **前提**：N-190 第一包（評估沿用結算那一次的序列）已經上線。若第一包被回退，評估與結算用的序列可能不同，「L 依據的 bar 比結算看得到的 bar 新」會成為 claim 晚於 L 的常見來源，觸發會增加。增加的方向是觸發，字面仍為真。
3. 對 X-3：
   - (a-1)：窗口寬度不變；發生次數與並行請求數成正比，(乙) 不改變請求數。
   - (a-3)：S/P 賣單恢復出現之後，條件 A 比較難成立，會更依賴條件 B。
   - 沒有新的漏報路徑：(乙) 不新增帳冊寫入點，第一點的前提不變，由 T15 守住。
4. 對 X-4：戳記與 (乙) 沒有交互。唯一的交集在部署：N-188 已上線後，若 ADR-0040 的 build 不含 N-188，等同回滾，適用 M1-1 第 5 點。
5. **給 ADR-0040 起草者的約束**（違反任何一條，就回 TA 與風控）：
   - 不得把 `list_batches()`（service.py:1616）移到載入序列之前，也不得在 :1616 到 `commit_evaluation` 之間加入取資料或任何網路 I/O；
   - 不新增任何改動 `playbook_batches` 股數或 cash 的路徑；
   - 不改 `_settle_pending` 取開盤價的方式；
   - N-188 已部署時，ADR-0040 的 build 必須包含 N-188。
6. **X-10 第 6 點改寫：**
   - 原文「N-190 的修正不得早於 N-188」，已被風控 `2026-11-04-N190重裁-風控.md` 第 5 點與 `2026-11-05-N177修復與N190字面裁示-風控.md` B-5 第 2 點取代。
   - 實測已成立，CEO #108 已核可：第一包、第二包 (乙) 都不等第三包。兩包上線到第三包上線之間的殘留，風控已書面接受，期限是第三包緊接在 N-177 之後。
   - 本補充不再設 N-190 的上線耦合。

## M1-4 測試、QB-18、X-12、X-14 的修訂

1. **測試（BLOCKING）：**
   - **N188-T8 改為「legacy 與重啟」：**
     - NULL 戳記、s.id < L.id 的動帳列（buy、逐批 sell、S2 都要測），不論 claim 早晚，都不觸發；
     - NULL 戳記、s.id ≥ L.id 的動帳列會觸發；
     - **VETO 釘住**：舊列 s 早於 L 好幾天、L 今日寫入；重新建 store（呼叫 `_init_schema`）N 次之後打 `/today`，所有列的 `share_notes == []`；
     - `_init_schema` 前後，`playbook_state` 的鍵集合不變。
   - **N188-T9 改為「述詞與 `settle` 等價」：**
     - 矩陣：rule_id ∈ {S1/P, S2, EMERGENCY}、status ∈ {executed, missed}、action、batch_no ∈ {NULL, 存在, 不存在}；
     - 觀察方式改為比對 settle 前後的批次與 cash，不再只靠 `set_cash` spy，因為 N-177a 的 S2 分支在單一交易內寫入；
     - 斷言：(A) ⇔ 逐批動帳；executed S2 ⇔ (B1)；(B2) ⇔ 這批移動股數大於 0；
     - 絆線：batch_no 存在、但批次列不存在 ⇒ 述詞為假、帳冊不變。N-177b 改到這裡時會轉紅。
   - **N188-T18（新）：S2 列。**
     - 較早的 S2 在兩次評估之間被 claim，三種情況都要觸發：已結算且移動股數大於 0、零移動、claim 後未 settle（模擬中斷）；
     - `share_notes == [SETTLED_SINCE_SYMBOL_NOTE]`；
     - W-B2LS 家族不渲染，改出 W-B2LSf 或 None（風控 A-3 BLOCKING）。
   - **N188-T19（新）：逐批列由 S2 觸發。**
     - (B2) 移動股數大於 0：觸發；移動 0 股：不觸發；
     - (B3) 沒有稽核紀錄、批次合格：觸發；沒有稽核紀錄、批次已 closed：不觸發；
     - property test：在任意操作序列下，批次 open 之後不回 planned、remaining_shares 不增、cost 不變；engine 的逐批 S/P 賣單只出現在合格批次上。
   - **N188-T20（新）**：條件 A、B 的探針查詢在 fixture DB 上的結果；探針不 import app。
   - **N188-T15 擴充**：N-177a S2 分支對 `playbook_batches` 的 SQL 寫入，只出現在 `settle` 的私有 helper。
   - 風控 A-4 (b) 的翻轉測試併入 N188-T11。
2. **QB-7 白名單（取代 X-2 第 6 點）：**
   - grep 範圍：`settled_after_id`、`BOOK_MOVING_SETTLEMENT_SQL`、`S2_FILL_ENTRY`、`S2_ELIGIBLE_BATCH_SQL`、`<FILL_MOVES>` 的表名、`_read_settled_since(`。
   - `app/` 內只准出現在：
     - `_SCHEMA`、`_MIGRATIONS`；
     - `claim_directive` 的 UPDATE；
     - 常數定義處；
     - `settle` 與它的私有 helper；
     - `_read_settled_since` 本體；
     - `commit_evaluation` 內唯一的一次呼叫。
   - 刪除 `STATE_SETTLED_AFTER_ID_FLOOR` 與「`_init_schema`（floor）」兩項。
   - 日後 ADR-0039 群組 B 要讀稽核表時，由它的補充擴充白名單。
3. **QB-18 的修訂：**
   - **QB-18.2 追加**：`playbook_state` 沒有新增鍵；對 N-188 而言，`_init_schema` 只多 `_MIGRATIONS` 的一個欄位。
   - **QB-18.5 改為**：
     - `BOOK_MOVING_SETTLEMENT_SQL` 文字不變，緊接在 `settle` 之前；
     - `S2_FILL_ENTRY`、`S2_ELIGIBLE_BATCH_SQL` 各只有一份定義，`settle` 的 S2 分支與 `_read_settled_since` 都由它們取得，不得另寫 `'executed'`、`'S2'` 的條件字面；
     - 水位條件逐字等於 `COALESCE(s.settled_after_id, s.id) >= L.id`，沒有 `:floor`；
     - 實作的述詞版本與 N-177a 的實際先後一致（M1-2 第 4 點）；
     - N188-T8、T9、T18、T19 綠燈；
     - X-2 第 3 點、第 5 點 (a)～(c)；
     - 本修正第 2 點的 QB-7 白名單。
   - **QB-18.8 改為**：N188-T1～T20 都存在且綠燈；(a-1)、(a-3) 的 docstring 都在，寫明「不自癒」，(a-1) 另寫明窗口寬度。
   - **QB-18.11 改為**：檢查 X-10 第 2～5 點；N-177 的先後依 M1-2 第 4 點；X-10 第 6 點依 M1-3 第 6 點，不再檢查 N-190 耦合。
   - **QB-18.13（新）**：PR 說明附上部署條件、探針路徑與適用時機；探針唯讀、不 import app、不連網。實際部署前的探針結果由 devops-sre 附在 release 紀錄。這一項屬於 release gate，qa-reviewer 只在 PR 階段檢查說明與探針，不檢查部署結果。
   - **QB-18.14（新）**：與 N-177a 共用的常數只由其中一個 PR 定義，另一個 PR 只引用，不得出現第二份。
4. **X-14 第 2 點改為**：
   - 具名常數只含「`playbook_directives` 末尾多 `settled_after_id`」；
   - state key 不增加，所以 `after <= PRE_N166_STATE_KEYS`、`declared == PRE_N166_STATE_KEYS` 兩條斷言零 diff、不會轉紅；
   - 只改欄位那一條斷言。
5. **X-12 的修訂：**
   - 刪除代價「每次 backend 重啟後多報」；
   - 新增代價：
     - (a-3) 部署邊界的漏報，以及隨之而來的部署條件；
     - S2 述詞要讀批次現況與稽核表；
     - N-177a 與 N-188 共用常數造成的耦合；
   - 新增好處：重啟對判定零影響；少一個 state 鍵；(a-2) 消失；
   - 交 tech-writer：在 Consequences 的補充中，把 X-3 的「兩種」寫成 (a-1)、(a-3)，不得原地改寫。

## M1-5 送風控確認的項目
- R1：X-4 改採 F-3（NULL 戳記以 s.id 當水位下界），不採 F-1 計數門檻。理由見 M1-1 第 1、2 點，包括「計數會算進非下單列」的讀碼發現。
- R2：X-3 仍然是「兩種」，但組成從 (a-1)、(a-2) 改為 (a-1)、(a-3)。(a-3) 的範圍與期限見 M1-2 第 5 點。
- R3：部署條件 A（未結算的 S/P 賣單為 0），以及替代用的條件 B（以時間戳做運維探針，失敗時只會漏報），是否可以接受。
- R4：N-188 上線之後才 apply 的離線修復，比照部署條件處理。
- R5：逐批列在 S2 結算時移動 0 股不觸發；(B3) 在中斷時以讀取當下的合格狀態判定。
- R6：新增的多報類型（M1-2 第 5 點之 4）。
- R7：N-177 裁示 A-3 寫「照 TA 第 3 節」，即 S2 以稽核表「移動股數大於 0」為準；這與 B-(d)1「以 claim 為準」不一致。本修正以 B-(d)1 為準，S2 列不看稽核表。請確認 A-3 的這部分已被 B-(d)1 取代。
- R8：M1-3 對 (乙) 的判斷，以及給 ADR-0040 的約束。
```

**對實作的約束**：條文在上方 M1-2 第 1、4 點、M1-3 第 5 點、M1-4 第 2、3 點，每一條 qa-reviewer 都可以逐條檢查。

### 其他部門
本輪沒有參與。

## 驗證

- **讀過的文件：**
  - 風控 N-188 定稿裁示全文：`/home/user/AICompany/work/reviews/2026-11-05-N168視覺規範R1R3與補充五及N188定稿-風控.md`
  - 補充五全文（含 X-14）：`/home/user/AICompany/work/reviews/2026-11-04-ADR0035補充五-tech-architect.md`
  - N-177 修正範圍評估：`/home/user/AICompany/work/reviews/2026-11-05-N177修正範圍評估-tech-architect.md`
  - 風控 N-177／N-190 裁示：`/home/user/AICompany/work/reviews/2026-11-05-N177修復與N190字面裁示-風控.md`
  - 風控 N-190 重裁第 1～5 節：`/home/user/AICompany/work/reviews/2026-11-04-N190重裁-風控.md`
  - CEO #108 的紀錄：`/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md:143`、`/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md:362`
- **讀過的程式**（未執行，路徑在 `/home/user/AICompany/apps/stock-desk/backend/app/` 下）：
  - `playbook/store.py`：:440-618、:661-693、:1172-1482；
  - `playbook/service.py`：:940-1114、:1542-1685；
  - `api/deps.py`：:299-329；
  - `playbook/engine.py`：grep `is_usable` 與 open 批次條件（:63-65、:213、:420）；
  - `compose.yaml` 與 `Dockerfile`：單一 uvicorn worker、沒有 `--workers`。
  - 另外 grep 確認：`PlaybookStore` 只在 `api/` 與 `playbook/` 被引用，scheduler 不碰 playbook；`settled = 1` 只在 `claim_directive` 寫入。
- **讀碼確認的事實**：
  - floor 在每次 process 啟動時升高；
  - 非下單列以 `settled = 1` 寫入、沒有戳記；
  - 讀帳點在載入序列之後，(a-1) 窗口不含網路取資料；
  - 結算不看 `data_status`；
  - engine 只對合格批次發逐批 S/P 賣單。
- **沒有查證的部分**：
  - N-177a 還沒實作：稽核表的實際表名、欄位，以及 S2 分支的寫法，是依 N-177 評估推定的；
  - ADR-0040 還沒出稿：M1-3 只依 CEO #108 的條件判斷；
  - 正式 DB 是否符合條件 A，未知，要靠 devops-sre 的探針確認。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案。

## 下一步

1. **coordinator**：
   - 把 code block 逐字附到補充五檔末：`/home/user/AICompany/work/reviews/2026-11-04-ADR0035補充五-tech-architect.md`；
   - 把 M1-5 的 R1～R8 送風控確認；
   - 風控確認之前，C 節的定稿常數不得合併。
2. **risk-compliance-officer**：確認 R1～R8，特別是 R2（(a-3) 取代 (a-2)）、R3（是否接受條件 B）、R7（A-3 與 B-(d)1 的取捨）。
3. **devops-sre**：
   - 寫部署條件的探針，比照 `/home/user/AICompany/apps/stock-desk/backend/scripts/n172_duplicate_probe.py`；
   - 確認 compose 換版是先停再起；
   - 把「N-188 上線後，部署不含 N-188 的 build 一律視為回滾」列入 release-flow。
4. **另一位 TA（ADR-0040 起草者）**：把 M1-3 第 5 點的四條約束納入 ADR-0040。
5. **tech-architect（本人）**：N-177 spec 出稿時，把 `S2_FILL_ENTRY`、`S2_ELIGIBLE_BATCH_SQL` 的單一定義，以及「每張 executed S2 至少寫一列稽核」寫進 C4、C5、C8。若 N-177a 改採 M0，回頭重審 (B2)。
6. **dev-lead／qa-reviewer**：N-188 開分支之後，依修訂後的 QB-18 與 N188-T8、T9、T15、T18～T20 實作與審查。若已經寫了 floor 鍵，要移除，X-14 只改欄位那一條斷言。
7. **tech-writer**：風控確認之後，依 M1-4 第 5 點以補充方式更新 ADR-0035 的 Consequences。
8. **CEO**：本輪不需要裁決。
