# RC-7 判定與 ADR-0043 修訂一補遺

- 審查者：tech-architect
- 日期：2026-11-09
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

這份是追加範圍的回報。Q-3、Q-4 的主體已在前一份交付，本份只修正其中一條（約束 F-6）。

- **RC-7：** 照我前一份的 F-6 實作，REBALANCE 完成後會自動送出 `/today`，`/today` 會先結算。我**撤回 F-6**，改為 F-6′：REBALANCE 完成後只 invalidate `["playbook-rule-set"]`，絕不碰 `["playbook-today"]`。
  - 照 F-6′ 做，N-209 不會新增任何 `/today` 觸發，所以不必依 RC-7 回風控。
  - 不更新 `/today` 也不會漏掉任何顯示：`/today` 沒有 TOTAL_DEPLOY 欄位，而且當日指令表是已落檔的列，重新讀取也不會改變。
- **修訂一補遺：** RC-2、RC-3、RC-5 (a)、RC-5 (b)、S-1 的修訂文字都在第二節，可以直接貼上。我沒有改動任何檔案。
- **S-1 查證：0 號批次不是靜默沿用。**
  - `BatchState.batch_no` 是 `Field(ge=1)`，在 models.py:213；風控寫的 :207 是 class 那一行。
  - 讀到 `batch_no` 小於 1 的列時，每一條讀取路徑在建構 `BatchState` 時就會 raise。`/today` 與 `/rebalance` 會回 500。
  - 因此 ADR-0043 D3 第 5 點與 Consequences R-1 寫的「從 0 起編……靜默沿用」與事實不符，要一併更正。STOP-1 的處置不變。

## 二、各部門回報

### tech-architect（唯讀）

#### RC-7：invalidate／refetch 鏈路（讀碼結果）

1. `["playbook-today"]` 會打 `GET /today`（queries.ts:417-424，api.ts:437-439）。
   - `/today` 在 `evaluate_today` 中，只要已確認規則集，就先結算（service.py:2153）。
   - 只有未確認時，在 :2150-2152 提前返回，不結算。
2. `invalidateQueries` 會帶 `cancelRefetch: true` 重抓（query-core queryClient.ts:319）。
   - query 已有資料、又正在抓取時，會先在前端無聲取消，再送一次新的（query.ts:405-413）。
   - `getPlaybookToday` 沒有接 `signal`，HTTP 請求不會真的中止，後端照樣跑完（主 spec :2628-2634）。
   - 結果是後端同時有兩個 `/today`，正是 R-6′ 那一類並發。
3. 只要有新元件訂閱 `["playbook-today"]`，`staleTime` 是 0、預設 `refetchOnMount` 為真，掛載時就會送一次 `/today`。所以確認畫面與結果畫面都不能用這個 query。
4. 現有會 invalidate `/today` 的地方只有兩處：資金確認（queries.ts:450-452）與出清（:522-525）。兩者都不屬 N-209。視窗聚焦與重新連線時的重抓是既有行為，N-209 不新增。
5. 不更新 `/today` 也沒有損失。
   - `TodayResponse` 沒有 TOTAL_DEPLOY 欄位；這個欄位只在 `RuleSetResponse`（api/playbook.py:258-261）。
   - `/today` 列出的是當日已落檔的指令列，K1、K2 不會重複落檔，每次重新整理都是同一張表（service.py:2139-2141、:2259）。REBALANCE 之後重抓 `/today`，指令表不會改變。

**方案比較：**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **(i) 用 `GET /rule-set`（`["playbook-rule-set"]`），採用** | 已經存在。在 playbook 端只有讀取（service.py:1976-1985）。確認畫面、結果畫面、FR-10 的「目前讀到的值」共用同一個來源 | 鍵不存在時回 `"0"`，ok 結果也沒有寫入時間。這兩點由我前一份提的 N-209b 加法欄位補上 | 低 |
| (ii) 新增 `GET /total-deploy` | payload 較小 | 與 (i) 重複，多一條讀取路徑 | 中，不採 |
| (iii) invalidate `/today` | 不需新寫程式 | 會結算；N-198（即 N-169F2）不在 base 時，會造成 `/today` 對 `/today` 的並發；而且不會改變任何顯示 | 高，否決 |
| (iv) 用 POST 回應做 `setQueryData` | 不送任何請求 | 回應格式和 rule-set 不同，混進同一個快取不清楚 | 中，可作為 (i) 的補充，不取代 |

**F-6′（取代前一份的 F-6；qa 可逐條檢查）：**
- REBALANCE mutation 在 hook-level 的 `onSettled`（成功或失敗都會跑）只做 `invalidateQueries({ queryKey: ["playbook-rule-set"] })`，不 await。
- N-209 新增或修改的程式（api.ts、queries.ts 的 REBALANCE 段、入口元件、確認元件、結果元件）都不得出現：
  - `playbook-today`、`usePlaybookToday`、`getPlaybookToday`；
  - 沒有帶 `queryKey` 的 `invalidateQueries(`、`refetchQueries(`、`resetQueries(`。
- 以結構測試釘住，比照 exitFlowStructure.test.ts。
- 排程台頁上的 TOTAL_DEPLOY 顯示，只讀 `["playbook-rule-set"]`。

#### S-1 查證

| 項目 | 結果 |
|---|---|
| 驗證規則 | `batch_no: int = Field(ge=1)`（models.py:213）。schema 只有 `batch_no INTEGER NOT NULL`，沒有 CHECK（store.py:72），所以 DB 裡可以存在 0 號或負號的列 |
| 會 raise 的讀取路徑 | 全都經 `_row_to_batch` 建構 `BatchState`（store.py:897），會 raise pydantic `ValidationError`：<br>• `list_batches`（store.py:875）<br>• `get_batch`（:955）<br>• `read_in_flight` 的 open 批次（:1469） |
| `/today` | 全表讀取在 :2158 與 :2199。結算在 :2153，比讀取早，所以結算的部分寫入可能已經 commit，之後回 500 |
| `/rebalance` | 在 :1828 就 raise，回 500，不寫入任何值 |
| 待結算列指向 0 號批次 | 推論：claim 之後動帳時 raise，等同 R-6′ 的失敗變體（N-198 之前）。未實跑，也未逐一追查 settle 路徑 |
| 規格面的影響 | N-207 規格的等價性說的是「從 0 起編也與舊算法逐式相同」。但 0 號 `BatchState` 根本建不出來，所以這句不可測，也到不了 engine。N207-T1、T2 的 seed 空間必須排除 `batch_no` 小於 1 的情況 |

#### 修訂一補遺（可直接貼上；tech-writer 照位置替換或插入）

````markdown
# ADR-0043 修訂一補遺（tech-architect 2026-11-09，依風控 `work/reviews/2026-11-09-ADR0043修訂一單項確認與N209Q2裁示-風控.md` RC-2、RC-3、RC-5、S-1）

## 補遺-1（RC-2）：ADR-0043 Consequences「壞處與代價」，插在「『規則已全數評估』的範圍（R-8）」一點之後

  - **已停止、沒有 open 的標的，S1 不會被評估（風控 2026-11-09 RC-2）**：
    - 已停止、沒有 open 的標的整檔不在 engine 輸入內。S1「站回 25MA 恢復」與資料缺漏警示都不會對它評估，暫停狀態維持到重新納入輸入為止（engine 只對輸入中有批次的標的逐檔評估：`engine.py:1201-1203`、`:1215`；資料缺漏 `:1218-1233`；S1 恢復 `:1236-1255`）。
    - 方向保守：該檔的 R 系列本來就不評估。
    - 名單頁不得把這種標的的 S1 狀態呈現成當日評估的結果。
    - 這一點屬 J-8「以 `engine_batches` 過濾」的承載範圍。

## 補遺-2（RC-3）：N-207 規格 丁、N207-C17「攜帶」第 4 個子彈，整條取代

    - **提前返回路徑**：`evaluate_today` 只有一條提前返回，即未授權路徑（`service.py:2150-2152` → `_unauthored_evaluation`，`:2037-2114`；`snapshot=[]` 在 `:2097`，`rules_fully_evaluated=False` 在 `:2102`）。這條路徑完全不評估，`engine_exclusions` 維持 None，不顯示揭露行（風控 2026-11-09 確認）。`service.py:1944` 的 `snapshot=[]` 在 `rebalance()` 裡，是記錄 REBALANCE 超額指令列時建立、交給 `record_directives` 的 `PlaybookEvaluation`（`:1925-1946`），不是 `/today` 的回應，與本條無關。
    - **未來路徑規則**：日後 `evaluate_today` 新增任何不跑 engine 的返回路徑，必須 `rules_fully_evaluated=False`、`engine_exclusions=None`；該路徑若會呈現批次快照（`snapshot` 非空），要回 TA 與風控。
    - **可檢查的形式（併入 N207-T22，新增斷言 7）**：
      - AST 列出 `evaluate_today` 內所有 `return` 敘述，以具名常數釘住 baseline 兩處：`return self._unauthored_evaluation(as_of)` 與末尾的 `return evaluation.model_copy(...)`。新增任何 `return` 就讓測試失敗，回 TA。
      - 未授權路徑的回傳值：`engine_exclusions is None`、`rules_fully_evaluated is False`、`snapshot == []`；`/today` 回應的 `engine_exclusion_note` 與 `round_note` 都是 None。

## 補遺-3（RC-5 (a)）：N-207 規格 丙、N207-M4「理由」子彈，整條取代

  - 理由：R-17 要求 N-209 在 N-207 上線前合入。依追蹤清單第 409 列已查證的事實「CEO 以 dev-up 拉 product 即等於部署」，產品線沒有與合併分離的上線步驟，所以「N-209 的 merge commit 在 N-207 的 base 內」就等於「N-209 上線不晚於 N-207」。這是 R-17 唯一可以檢查的形式，不比 R-17 嚴（風控 2026-11-09 接受）。兩者同一次部署可以接受。產品線日後若新增與合併分離的上線步驟，放寬要回風控，並在該上線步驟設可檢查的閘取代，再經 CEO 同意。

## 補遺-4（RC-5 (b)）：N-207 規格 丙、N207-M4，在「N-209 未合入時……」子彈之後新增

  - **N-209 未被回退的檢查**（風控 2026-11-09 RC-5 (b)；執行與判斷分離，比照 N196-C8）：
    - **錨點登錄**：N-209 合入時，coordinator 在派工紀錄中記錄 `<M_209>`（完整 40 碼），以及 N-209 PR 說明所列的錨點清單：N-209 新增的檔案路徑，加上 3～5 條定義的 regex（例如 `^export function postPlaybookRebalance\(`）。錨點清單要修改，須回 TA。
    - **執行者**：由 coordinator 指定，不得是 N-207 的實作者。在 N-207 送 qa 審查的 commit 上執行以下每條指令，每條之後都接 `; echo "exit=$?"`，指令原文、完整輸出與 `exit=` 行原樣記入 `work/reviews/` 的本案審查紀錄，附讀取時間（到分鐘，Asia/Taipei）。`<base>` 的定義與 N207-M1 相同。
      - (R1) `git merge-base --is-ancestor <M_209> <base>`
      - (R2) `git rev-list <M_209>^1..<M_209>^2`，列出 N-209 帶入的 commit，令集合 S = (R2 的輸出) ∪ {`<M_209>`}。
      - (R3) `git log --format='%H%x09%s' <M_209>..<base>`（全列）；`git log -i -E --grep='^revert' --format='%H%x09%s' <M_209>..<base>`；並對 S 的每一個 SHA s 各跑一次 `git log -F --grep=<s> --format=%H <M_209>..<base>`。
      - (R4) `git diff --name-status --diff-filter=D <M_209> <base> -- <錨點檔案路徑>`
      - (R5) 對每條錨點 regex 跑 `git grep -c -E '<regex>' <base> -- <對應路徑>`。
    - **判斷者**：qa-reviewer 只依上述原始輸出，自行獨立判定，不採用執行者的結論。以下任一情況判 BLOCKING：
      - R1 不是 `exit=0`；
      - R3 的任一條 `--grep=<s>` 有輸出；
      - R3 的 revert 掃描有輸出，且經判讀與 S 相關；
      - R4 有輸出；
      - R5 有任一條計數為 0。
      判讀不了就回 TA。檢查綁定 qa 審查的那一個 commit；head 一變動，全部重做。
    - **已知限制**：R3 抓的是 `git revert` 留下的訊息，R4、R5 抓的是刪檔與刪除定義。以一般 commit 局部讓入口失效、但保留定義的情形，這幾條抓不到，仍由 qa 的 code review 承擔。
    - **連動規則**：
      - 產品線上，回退 N-209 一律以 revert commit 進行，不得以 reset 或 force push 移除，否則 R3 無從偵測。
      - N-207 合入之前，N-209 若被回退，N207-M4 不成立，N-207 停在 review 之後。N-209 重新合入時，以新的 merge commit 作為 `<M_209>`，重跑 R1～R5。
      - N-207 合入之後，N-209 若要回退，必須在同一次 push 同時回退 N-207，或者先回風控裁示；不得單獨回退 N-209。合併就是部署，單獨回退會讓 N-207 的字面變成不實。
      - 〔TA 追加，風控可刪〕N-209 的前提單（N-177a、N-195、N-196、N-197a）任一被回退時，N-209 並發提醒的事實範圍（風控 2026-11-09 F-1～F-3）就失去前提，須回風控。

## 補遺-5（S-1）

### 5a：N-207 規格 乙、§9 表 P-2 列，「停止條件」欄取代
任一檔最大值大於 bpt、**最小值不等於 1**，或斷號數大於 0 → **STOP-1**

### 5b：N-207 規格 乙、§9「說明」，新增一點
  - `batch_no` 小於 1 的列，不是靜默沿用，而是在讀取時就失敗：`BatchState.batch_no` 是 `Field(ge=1)`（`models.py:213`），而 `list_batches`、`get_batch`、`read_in_flight` 都經 `_row_to_batch` 建構 `BatchState`（`store.py:875`、`:897`、`:955`、`:1469`），讀到這種列就 raise `ValidationError`。`/today` 在結算（`service.py:2153`）之後的全表讀取（`:2158`）失敗並回 500，`/rebalance` 在 `:1828` 失敗。這是現況就有的行為，不是 N-207 引入的。P-2 以 SQL 直接讀表，不經 `BatchState`，所以看得到這種列。

### 5c：ADR-0043 D3 第 5 點「等價性」與「舊資料異常的靜默沿用」兩個子彈，取代（事實更正，STOP-1 處置不變）
   - **等價性**：所有批次都是第 1 輪時，`round_batches == symbol_batches`、`offset == 0`，整個函式與修改前逐式相同。斷號、批數多於 bpt 的舊資料也一樣。由 N207-T1、T2 的差分測試（各至少 300 組 seed）釘住；seed 空間只含 `batch_no ≥ 1`，因為 `BatchState` 不允許更小的值。
   - **舊資料異常（風控 R-1）**：等價不代表正確。
     - 有斷號的資料，可能沒有末批補足；
     - 批數多於 bpt 的資料，從第 bpt 批起每一批都走末批分支，有可能只買 1 股；
     - 這兩種是使用者事前不會知道的靜默沿用；
     - `batch_no` 小於 1 的列到不了 engine：讀取時就 raise，`/today`、`/rebalance` 回 500（現況就是如此）。
     - 部署前唯讀盤點發現第 1 輪批數不等於 bpt、`batch_no` 最大值大於 bpt、最小值不等於 1，或有斷號時，停止部署，回報 TA 與風控（N-207 §9 STOP-1）。

### 5d：ADR-0043 Consequences「舊資料異常的靜默沿用（R-1）」一點，取代
  - **舊資料異常（R-1）**：斷號、批數多於 bpt 的舊資料原樣沿用舊算法，可能沒有末批補足，或每批只買 1 股；`batch_no` 小於 1 的列在讀取時就 raise，`/today`、`/rebalance` 回 500。部署前盤點發現就停止部署，不以揭露代替（N-207 §9 STOP-1）。

## 補遺-6：修改處索引（交付 4）同步更正
- C 節「§9 順序；N207-M4」列的「對應」欄，改為：R-17；R-17 唯一可以檢查的形式（風控 2026-11-09 接受）；RC-5 (a)(b)。
- D 節第 4 項改為：N207-C17：唯一的提前返回（未授權）不顯示揭露行；`service.py:1944` 屬於 `rebalance()`（RC-3 更正）。
````

**補遺注意事項：**
- 5c、5d 改動的是風控 R-1 已看過的字句。性質是事實更正，方向是改為明確失敗，STOP-1 不變。是否要再送風控做單項確認，由 coordinator 決定；TA 建議送一份給風控知悉。
- 補遺-1 依 RC-2「不必回送」辦理。只加了程式行號，沒有偏離風控列的事實。

## 三、驗證

- **讀過：**
  - 風控回審全文；
  - TA 修訂一檔 :228-239、:460-756；
  - `service.py` :1555-1644、:2123-2272；
  - `engine.py` :1200-1244；
  - `models.py` :195-224；
  - `store.py` 的 schema（:72）與 `_row_to_batch`、`get_batch`；
  - `deps.py` :387-412；
  - query-core `queryClient.ts`、`query.ts` 中與 cancelRefetch 相關的段落。
- **未驗證：**
  - 沒有執行任何指令或測試（沒有 Bash）。
  - 「後端同時有兩個 `/today`」與「0 號批次在 settle 路徑造成 claim 後未動帳」都是讀碼推論。
  - 補遺-4 的 git 指令沒有實跑。
  - N-209 尚無程式，錨點清單要等它合入時才能確定。
  - `GET /rule-set` 的 cap-1 依賴在第一次建立 settings store 時會跑 migration（deps.py:400-409）。這是既有行為，不寫 playbook 的資料。
- 未讀 `.env`，未碰 `data/*.db`，沒有修改任何檔案。

## 四、下一步

1. **tech-writer：** 依補遺-1～3、5c、5d、6 併入 ADR-0043 與 N-207 規格，以 proposed 落檔。5c、5d 先等 coordinator 決定是否送風控確認。RC-1 的機械替換照風控指示辦理。
2. **dev-lead：** N-207 規格併入補遺-2、3、4、5a、5b。N207-T1、T2 的 seed 範圍改為只含 `batch_no ≥ 1`。
3. **frontend-engineer：** N-209 以 F-6′ 取代前一份的 F-6，其餘 F 條不變。
4. **coordinator：**
   - 登錄 N-209 錨點清單與 `<M_209>` 的記錄責任，並指定補遺-4 的執行者；
   - 決定 5c、5d 要不要送風控；
   - 通知風控：照 F-6′ 做，N-209 不會觸發 `/today`，RC-7 不必在字面定稿前回審。
5. **風控：** 補遺-4 末條的 TA 追加條款，要保留或刪除。
