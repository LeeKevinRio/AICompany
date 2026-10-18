# ADR-0027 補充回報：N-12、兩項確認、判定順序同意、起算日修正（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論（補充回報：回應 coordinator 的三點，以及 quant 對「起算日」的意見；前一份回報的條文全部維持，以下只寫新增與修正的部分）

- **N-12（required）：作廢原因集合存放在 `forecast_outcome` 新增的欄位 `void_reasons_json`。**
  - 由結算或更正的寫入函式，在判定當下用同一次評估填入，之後不能改，也不能事後用重讀的資料推回。
  - 有了這一欄，V12-14 (2) 和 V13-01 (3) 都可以逐列數出，不必另外存。
  - 注意：這和 N-4「診斷標籤不得寫入 `forecast_outcome`」不衝突。原因集合是判定本身的一部分，跟著該列一起寫入；診斷標籤則是作廢之後才補算的。
- **兩項確認：**
  - (1) 族群 claim 層是否只會出現 `basket_coverage_below_90`：成立，但有一個條件。V10-08 如果選「整筆作廢」，claim 層還可能出現 `split_or_reduction_suspected`。V10-08 定案前，寫入驗證先允許這兩個值，定案後再收窄。
  - (2) T+h 缺 bar 時是否用窗內已有的 bar 評估分割：同意，照 D-9.3「任一日」的字面讀。但我另外發現一個缺口：停牌橫跨窗內幾天、復牌後的跳動，不算「單日」報酬，現行字面判不到。T+h 有 bar 時，這種列會以未還原的報酬結算。這屬於定義層，我只指出缺口，交 quant 在凍結前提案。
- **作廢原因順序：我同意 quant 的完整順序**（第五值 → `dividend_factor_unusable` → `split_or_reduction_suspected` → `basket_coverage_below_90` → `missing_bar_after_wait`），撤回 L1835 我原本的建議。我原本的建議沒有附理由；quant 的結構理由成立。ADR 端另有一個更強的理由：
  - R10-3／V12-20 規定作廢列寫入之後原因不再改。
  - 五個原因中，只有 `missing_bar_after_wait` 會因為之後補到資料而變得不準確。
  - 把它排最後，寫定的原因就不會被晚到的資料否定。
- **ADR 同步**：
  - D-9.3 新增三點：判定順序、判定時點、部分窗口。
  - L617 與 L1835 加〔已決〕並指向 V13-01；L1835 的原句保留不改。
  - 順序常數凍結在 dirdef。
  - LG-28 (a)～(h) 逐格對應到 FL-22，(d) 另外對應 FL-50。
- **「起算日」修正我前一份的結論：**
  - ADR D-14 端的結論不變：代入的值符合 D-14，ADR 不要求改詞。
  - 但 quant 指出的殘餘歧義我同意，而且在畫面上會直接看到：LM-111「預測基準日早於紀錄起算日」本身就標在紀錄上。如果把起算日讀成「開始有紀錄的日子」，這句就自相矛盾。
  - 所以前一份的「不觸發重送」只在 creative-lead 與風控決定不改詞時成立。要改的話，畫面上帶這個詞的只有 LM-99、LM-111；LM-84、LM-85 只有占位符名稱。但依字面清單 L3544，四句要一起重送。
- **N-6 與 quant 的 V13-03 一致**：quant 依相鄰兩筆 snapshot 劃分區間，我依 (S_before, S_cover) 分組，兩者得到的遮蔽期與日數相同，WARNING 門檻同為 ≥ 2。我確認 V13-03 可以從 `e_read_event_seq`／`e_read_outcome_seq` 逐列數出。`mask_episodes` 照 V13-03 的區間定義實作，只用一個函式。
- **新發現 O-1（不在這次委派範圍，只轉知）**：
  - D-9.1 第 2 點要求「該日資料的 `recorded_at ≤ cutoff(T+h)`」，D-9.2 也用 `as_of(T+h)` 的 PIT 視圖；但 D-9.3 與事先宣告 L1188 又寫「等 5 個觀察日，期間補到就結算」。
  - 等待期間才補到的 T+h bar，`recorded_at` 必然晚於 `cutoff(T+h)`，照字面不能用來結算，所以「期間補到就結算」這條路徑實際上走不到。
  - 這同時影響 quant 寫的「期間補到 bar 時一次判定」。建議 coordinator 把它列為新的追蹤項，由 TA 與 quant 在凍結前處理。

## 二、逐項條文

### N-12：作廢原因集合的存放處（掛 A-65（D-3 `forecast_outcome`），連帶 A-11（D-9.3）；補定義（收緊）；無被取代原文）

**D-3 `forecast_outcome` 的「狀態」子點（L291）之後新增：**
> - （N-12；事先宣告 v0.13 V13-01、v0.12 V12-14）`void_reasons_json`：作廢判定當下成立的原因集合。
>   - JSON 陣列，值取自 D-9.3 的五值封閉列舉，依 `VOID_REASON_ORDER` 排序、不重複。
>   - `status = resolved` 時必須為 null；`status ≠ resolved` 時必須非空，而且第一個元素等於 `status_reason`。
>   - 由結算或更正的寫入函式，以判定 `status_reason` 的同一次評估填入，不接受呼叫端傳入。寫入後隨該列固定（D-2 第 2 點），不得事後依重讀的資料推回，也不得另表補記。
>   - **寫入驗證**（任一項不成立就拒絕寫入）：
>     - 值在列舉內，排序正確、不重複；
>     - 第一個元素等於 `status_reason`；
>     - 依 scope 的允許集合：
>       - `market` ⊆ {`index_bar_confirmed_erroneous`, `missing_bar_after_wait`}；
>       - `symbol` ⊆ {`dividend_factor_unusable`, `split_or_reduction_suspected`, `missing_bar_after_wait`}；
>       - `sector` ⊆ {`split_or_reduction_suspected`, `basket_coverage_below_90`}。V10-08 定案為「排除該成員」時，`sector` 收窄為 {`basket_coverage_below_90`}，與 V10-08 同批修訂本點。
>   - **§4.2 的資料來源**：
>     - V12-14 (2) ＝ 鏈尾是作廢列、而且 `void_reasons_json` 同時含 `index_bar_confirmed_erroneous` 與 `missing_bar_after_wait` 的筆數；
>     - V13-01 (3) ＝ 鏈尾作廢列依完整集合分類計數；
>     - 兩者都是每筆預測只計一次，由這一欄逐列數出，不另存欄位。

**D-9.3，緊接在 L617 之後新增：**
> - （N-12；事先宣告 v0.13 V13-01）**判定順序**：`index_bar_confirmed_erroneous` → `dividend_factor_unusable` → `split_or_reduction_suspected` → `basket_coverage_below_90` → `missing_bar_after_wait`，第一個成立的就是 `status_reason`。
>   - 順序常數 `VOID_REASON_ORDER` 凍結在 dirdef，屬於 `definition_logic_sha256` 的範圍，字面與 V13-01 逐字相同。
>   - 判定只由 `scoring.py` 的單一函式 `void_reasons(...)` 產生。五個值全部評估、不短路，回傳依 `VOID_REASON_ORDER` 排序的成立集合；`status_reason` 取第一個。
>   - 只讀 bar、除權息事件、因子計算結果與確認紀錄，不讀 label、`hit`、基準命中或任何驗證統計（AST 列舉 import）。
> - **判定時點**（V13-01）：
>   - T+h 有 bar 時，在結算時判定。
>   - T+h 缺 bar 時，在等待期滿或期間補到 bar 時一次判定；等待期間不得先以其他原因寫入作廢列。
>   - 更正作業重算時依同一個函式與同一個順序。依 R10-3，作廢列寫入之後原因集合不再改變。
> - **部分窗口**：T+h 缺 bar 時，`split_or_reduction_suspected` 以判定當下、結算窗內已有的 bar 評估（「任一日」照字面）。
>   - 「單日報酬」指相鄰兩個觀察日都有 bar 的日子。
>   - 跨越缺 bar 日的報酬是否也要比對門檻，現行字面沒有涵蓋，交 quant 在凍結前提案；提案核可之前照現行字面。

**L617 句尾加：**
> 〔已決：完整順序依事先宣告 v0.13 V13-01（第五值的位置依 V12-14），見本點下方「判定順序」（N-12）〕

**L1835 句尾加（原句不改）：**
> 〔已決：事先宣告 v0.13 V13-01。與本句的建議不同，`missing_bar_after_wait` 由第一改為最後；tech-architect 同意，理由見修訂紀錄 N-12〕

**修訂紀錄 N-12 的理由（逐字）：**
> 同意 V13-01 的順序。除了 quant 的三個結構理由，ADR 端另有一點：R10-3／V12-20 規定作廢列一經寫入，原因不因之後補到的資料而改變。五個原因中，只有 `missing_bar_after_wait` 是由「沒有資料」得出的，可能被晚到的資料否定；其餘四個都有正面證據，資料補到之後仍然成立。排在最後，寫定的 `status_reason` 就不會和之後補到的資料矛盾。L1835 原本的建議沒有附理由，撤回。

**FL 對應 LG-28：**
- **FL-22** 加表格驅動格，逐格斷言 `status_reason`、`status`、`void_reasons_json`：
  - LG-28 (a)：market 收盤確認有誤＋T+h 缺 bar；
  - LG-28 (b)：因子不可用＋分割；
  - LG-28 (c)：缺 bar＋因子不可用，另斷言 `diag_last_close` 為 null；
  - LG-28 (d)：缺 bar＋分割，同樣斷言 `diag_last_close` 為 null；
  - LG-28 (e)：三者同時成立；
  - LG-28 (f)：族群成員缺 bar 或因子不可用時，claim 層不出現 `missing_bar_after_wait`、`dividend_factor_unusable`；
  - LG-28 (g)：等待期間不寫入作廢列；
  - LG-28 (h)：label 互換後輸出逐位相同；
  - 另加寫入驗證格：集合排序錯誤、第一個元素 ≠ `status_reason`、超出 scope 允許集合、`resolved` 列非 null，各自拒絕寫入。
- **FL-50** 加一格（對應 LG-28 (d)）：T+h 缺 bar，窗內已有的 bar 中有一日超過 `SPLIT_SUSPECT_ABS_RETURN` → 判為 `split_or_reduction_suspected`。
- V10-08 定案之後，補族群成員分割一格。

### 「起算日」（修正前一份回報的結論）

**ADR D-14 端的結論**：
- 值的部分符合 D-14：T 類日期、逐 claim、D_v 不存在時不代入。前一份提案的三條綁定約束都維持。
- ADR 端沒有要求改詞的理由。

**對 quant 殘餘歧義的回應**：同意，而且這不只是理論上的讀法。
- D_v 之前可以有紀錄（`late=1` 的排程紀錄、on-demand 紀錄），LM-99、LM-111 本身就是標在這些紀錄上的。
- 把「紀錄起算日」讀成「開始有紀錄的日子」，畫面上會出現「一筆紀錄早於開始有紀錄的日子」的矛盾。
- 建議 creative-lead 起草一個指明主統計的說法，例如「主統計起算日」，交風控決定。這只是方向，不是逐字提案。
- 改詞的話，依 L3544，LM-84、LM-85、LM-99、LM-111 同批重送：LM-84、LM-85 在畫面上沒有變化，只改占位符名稱；LM-99、LM-111 要改字面。
- 不改詞的話，維持前一份「不觸發重送」的結論。

## 三、驗證

- **quant 提案** `/home/user/AICompany/work/reviews/2026-10-18-作廢判定四值順序與起算日及遮蔽日數提案-quant.md`：全文（L1-206）。
- **ADR-0027** `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`：
  - 已讀：L1825-1839（L1835）、L1497-1519（FL-22、FL-50）；前一份已讀的 L285-301、L593-623；
  - grep：`疑義裁定第 15 項`、V12-14（ADR 內沒有引用 V12-14）、`cutoff(T+h`／等待期（L596、L616）。
- **事先宣告** `/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md` L1160-1199：`status_reason` 表、作廢規則、V12-14、L1188 的等待規則。
- **沒有做的事**：沒有改檔，沒有讀 `.env` 或 `*.db`，沒有跑 git。commit ff2f639 是依 coordinator 的訊息，我沒有核對。

## 四、下一步

**在前一份「回送風控」清單上追加：**
- **N-12**：`void_reasons_json` 欄位、D-9.3 的三點（順序、判定時點、部分窗口）、L617 與 L1835 的〔已決〕，以及 tech-architect 同意 V13-01 順序的理由。和 quant 的 V13-01 一起送。
- **兩項確認的結論**：族群允許集合綁定 V10-08；跨缺 bar 報酬的缺口交 quant。
- **「起算日」修正**：殘餘歧義成立，是否改詞由 creative-lead 起草、風控裁定；改詞就四句同批重送。

**v0.13 同批（追加）：**
- V13-01 必須和 ADR 的 N-12 同批：順序常數、`void_reasons_json`、FL-22／FL-50 與 LG-28 的對應。coordinator 機械核對時，要比對五值順序在 §6.3、V13-01、LG-28、ADR D-9.3、dirdef 常數五處逐字一致。
- V13-02（起算日改為引用 D-14）、V13-03（遮蔽日數）分別和 ADR 的起算日綁定條文、N-6 同批。

**建議新增追蹤項（交 coordinator）：**
- **O-1**：D-9.1／D-9.2 的 cutoff 與「等待期間補到就結算」互相矛盾。由 TA 與 quant 在凍結前處理，會影響 V13-01 的判定時點。
- 跨缺 bar 報酬是否適用分割門檻，由 quant 在凍結前提案，可以和 V10-08 一起處理。
