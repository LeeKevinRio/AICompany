# N-190 停止點裁示（ADR-0040 補充一）

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**兩點都裁示了，dev-lead 可以接續。不需要產品碼 diff，也不擴大 CEO #110 的核可範圍。**

1. **T15 衝突**：第 699 行 `>= 2` 是 (i) 之前的實作細節。它只是測試前提，確認「第二次載入」真的存在，本身不是 T15 要守的不變式。(i) 之後，T15 守的「區塊分類 == 結算判 N1 用的序列」在產品層更強了。
   - 不過只翻成 `== 1`（選項 1）不夠：T15 會變成 QB-9 的重複，而且抓不到「`evaluate_today` 把 `loaded` 誤接給 `_pending_exit_lines`」這種錯誤。
   - **採選項 (3)**：(1) 加上接線斷言 `loaded is run.loaded`，再把 N1b 的前提寫成斷言。第 700～703 行逐字不改。
   - 選項 (2) 不採，理由見下方方案比較。
2. **QB-20**：9253032 對 engine.py 的 3 行（2 行註解，加 1 行 `entry_before_exit_on=batch.entry_before_exit_on,`）**不違反 C-B11**。這是 ADR-0034 C-B8 與其補充一 S-3 第 3 點明文授權的照抄。QB-20 原本寫「為空」是我起草 ADR-0040 時漏算了 C-B8，錯在條文，N-168 沒有越界。口徑改成「只含 C-B8 照抄 hunk」，並給出可逐條檢查的條件。
3. **`SETTLED_SINCE_RULE_IDS`**：確認和補充五 X-1、修正一都不衝突，放在 store.py 是對的。N-188 必須引用它。
   - **另外發現一處要先釐清，否則 N-188 會被誤判 BLOCKING**：補充五 QB-18.6 寫「`SETTLED_SINCE_*` 只在 `wording.py`」，照字面這個萬用字元會套到這個名稱。已寫進 E-3。

條文全文在下方：ADR-0040 補充一（E-1～E-3）、ADR-0040 檔頭一行、ADR-0039 加註一行。

---

## 各部門回報

**tech-architect（本人，唯讀）**

讀過的檔案：
- dev-lead 停止點交件；
- ADR-0001、ADR-0034（C-B8、C-B11）、ADR-0039（含補充一）、ADR-0040 全文；
- ADR-0034 補充一 S-3、ADR-0035 補充五與修正一、[風控-0040] M-1；
- worktree 中 `service.py`：`_evaluation_series`、`_settle_pending`、`_pending_exit_lines`、`classify_exit_batches`、`exit_line_still_covers`、`evaluate_today`；
- `engine.py` 的 `_snapshot_rows`；
- `store.py:257-261`；
- `tests/test_playbook_pending_exit_block.py:668-703`、`tests/test_playbook_n190_reuse.py`。

### 評估摘要

**T15**

T15 的不變式出自 ADR-0039 Decision 3／C2″：authored 路徑的分類用 `run.loaded`，所以與 N1 一致（風控 P-1）。

讀碼判定在 (i) 之下這件事從構造上成立：
- 能被判為 stale 的列，一定是 `execution_date <= as_of` 的到期列。這些列都進了 `_settle_pending` 的 `pending_directives(on_or_before=as_of)`，所以它們的 symbol 一定在 `run.loaded`。
- `_evaluation_series` 回傳的是同一個物件（`settled[symbol]`）。
- 未到期的列，在任何序列上都判為仍涵蓋：`exit_line_still_covers` 要求有 `day > execution` 才會不涵蓋。
- 因此同一請求內「結算與評估看到不同序列」已經造不出來。換一個未到期的 symbol 也造不出差異。

但 `loaded` 和 `run.loaded` 是兩個不同的 dict。測試若只看結果，就證明不了接線，所以要加 identity 斷言。

**QB-20**
- worktree 的 `engine.py` 中，`entry_before_exit` 前綴恰好出現 1 次，就在 `_snapshot_rows:1102` 的 kwarg，沒有任何條件讀它。
- `entry_before_exit_label`、`entry_before_exit_note`、`exit_stamped_on` 出現 0 次。

**`SETTLED_SINCE_RULE_IDS`**
- 值與順序等於補充五 X-1 第 1 點。
- store 是唯一兩邊都能引用的模組：service 會 import store；N-188 的 `_read_settled_since` 在 store 內；store 不得 import wording（N172-C7）。
- 「先合者定義、後合者引用」與修正一 M1-2 第 1 點的定義者規則同一個模式。
- 修正一條件 A 的探針依規定不 import app，所以帶字面。這不算第二份，由 N188-T20 斷言兩者相等（[風控-0040] M-1）。

### 方案比較：T15

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| (1) 只把 699 行翻成 `== 1` | diff 最小 | 變成 QB-9 的重複；`_ShiftingPrices` 的第二次回答永遠不會被要求，名不副實 | 接線誤接漏網；(i) 日後回退時會變成實際錯誤 | 不單獨採，併入 (3) |
| (2) 在 `_pending_exit_lines` 層布置兩份序列 | 保留「分得出」的形式 | 該函式只收一份序列（`loaded=`），兩份序列只能驗它用了自己的引數，與 T16、`classify_exit_batches` 等價測試重複；丟掉同一回應裡 N1 與區塊一致的端到端檢查 | 測試綠，接線卻錯 | 不採 |
| **(3) = (1) 加接線 identity 斷言加 N1b 前提斷言** | 保留「證明用的是結算那一份」，不依賴第二次載入；(i) 回退後仍有效 | 用 spy，綁住 keyword 名稱 `loaded`；diff 略多 | 重構改名時要同步改測試 | **採用** |
| (4) 刪掉 699 行 | — | 靜默弱化，絆線也沒了 | — | 否決 |
| (5) 改情境讓評估再載入一次 | — | 違反 N190-C2／QB-9；換別的 symbol 也造不出差異（見上） | — | 否決 |

### 方案比較：QB-20

| 方案 | 結論 |
|---|---|
| (a) 判違反，要求退掉 N-168 的這 3 行 | 否決：與 C-B8 直接衝突，而且 W-B2、W-B2L 會失去來源 |
| **(b) 判不違反，QB-20 改為「只含 C-B8 照抄 hunk」的可檢查口徑** | **採用** |
| (c) 判不違反，直接刪除 QB-20 第 4 小點 | 不採：會失去「N-168 沒碰 R/S/P 判斷」的事後查核 |

### 決策（ADR 草案）：附加在 ADR-0040 檔末

```
## 補充一：N-190 實作停止點的裁示（2026-11-07）

- 日期：2026-11-07
- 決策者：tech-architect。依據：QB-17「若必須改，PR 停下來送 TA」、Decision 13「不為空時送 TA 判斷」。兩處都授權 TA 裁示，本補充只記錄裁示結果。
- 來源：`work/reviews/2026-11-07-N190停止點QB17-dev-lead.md`
- 性質：補充本文，不改本文。標「取代」或「改為」的地方，以本補充為準。不擴大 CEO #110 的核可範圍，不改任何產品行為與字面。CEO 可推翻。
- 程式位置：`fix/stock-desk-n190-usable-cache` 分支 086c223 的快照，以內容定位。全部是讀碼判定，未執行。
- 用語：本 ADR 附錄 B 也有一條「T15」。為避免混淆，下文把 ADR-0039 附錄 B 的 T15 記為 39-T15，也就是 `tests/test_playbook_pending_exit_block.py::test_t15_classification_follows_the_series_the_settlement_judged_n1_on`。

### E-1 39-T15 與 Decision 7 (i) 的衝突（QB-17 的例外）

1. 判定：
   - 39-T15 要守的不變式是 ADR-0039 Decision 3／N171-C2″：authored 路徑上，`/today` 區塊的分類用的是同一次請求 `_settle_pending` 載入的序列（`run.loaded`），所以與 N1 一致（風控 P-1）。
   - `assert len(prices.calls) >= 2` 不是這個不變式，而是測試的前提檢查：確認情境裡「第二次載入」真的存在，分類才分得出用的是哪一份序列。它描述的是 (i) 之前 `evaluate_today` 會重新載入的實作細節，也就是 ADR-0039 Options 二 (ii) 的前提。
   - (i) 之後：
     - 能被判為不涵蓋的列，一定是到期列（`execution_date <= as_of`），它們的 symbol 一定在 `run.loaded`，評估沿用同一個物件；
     - 未到期的列，在任何序列上都由 `exit_line_still_covers` 判為仍涵蓋。
     - 因此同一請求內「結算與評估看到不同序列」已經無法構造。產品層的不變式由 ADR-0039 Decision 3 與本 ADR 的 (i) 兩道機制同時保證，比原先強。
   - 但只把前提翻成 `== 1`，39-T15 會變成 QB-9 的重複，失去「證明用的是結算那一份」的能力：`evaluate_today` 把評估的 `loaded` 誤接給 `_pending_exit_lines` 時，在 (i) 下結果相同，測試抓不到；(i) 日後若回退，這個誤接就會變成實際錯誤。

2. 准改範圍：只限 39-T15 這個測試函式，加上 `_ShiftingPrices` 的 docstring。QB-17 對其他測試照舊。
   - (a) `assert len(prices.calls) >= 2` 改為 `assert len(prices.calls) == 1`。旁註寫明：自 ADR-0040 Decision 7 (i) 起，結算與評估從構造上就是同一份序列。
   - (b) 原第 698 行註解改寫成與 (a) 相符的敘述。
   - (c) 新增接線斷言：
     - 用 monkeypatch 包住 `book.service._settle_pending`，取得回傳的 `run`；
     - 包住 `service_module._pending_exit_lines`，記錄 `loaded` 引數；
     - 斷言 `_pending_exit_lines` 恰好被呼叫一次，而且 `loaded is run.loaded`。必須用 `is`，不得用 `==`。
   - (d) 新增前提斷言：`run.loaded["2330"].bars` 的日期不含 WEDNESDAY。這是 N1b 的前提，原本只寫在註解裡。
   - (e) 原第 700～703 行的四條斷言逐字不改。`_ShiftingPrices` 的程式不改；docstring 可以補一句：「(i) 之後，同一請求內不會要求第二次回答；保留作為回退 (i) 時的絆線。」
   - (f) 不得把 39-T15 移到 `tests/n190_helpers.py`，也不得換成其他 fake。fixture 零 diff。39-T15 不屬本 ADR 附錄 B，QB-7 不適用於它。

3. 回退：日後若回退 (i)（依 Decision 13 必須回 TA 與風控），(a) 恢復為 `>= 2`，(c)(d) 保留。

4. 不需要的事項：產品碼 diff；修改 ADR-0039 v2 本文或其補充一；重錄 golden；風控回審（字面、行為都不變，不變式只變強）。

5. 檢查（qa-reviewer，BLOCKING）：
   - `tests/test_playbook_pending_exit_block.py` 的 diff，hunk 只落在 39-T15 函式內與 `_ShiftingPrices` 的 docstring；
   - 原第 700～703 行的四條斷言逐字存在；
   - (c) 用 `is`，並斷言呼叫次數恰好為 1；
   - PR 說明引用本節。

### E-2 QB-20 事後查核的口徑（修正 Decision 13 的「事後查核」與 QB-20 第 4 小點）

1. 判定：9253032 對 `app/playbook/engine.py` 的 diff，是在 `_snapshot_rows` 的 `BatchSnapshot(...)` 呼叫內，新增 2 行註解加 1 行 `entry_before_exit_on=batch.entry_before_exit_on,`。這**不違反** ADR-0034 C-B11。理由：
   - ADR-0034 C-B8 及其補充一 S-3 第 3 點明文要求 `BatchSnapshot` 帶出標示，engine 只照抄 `BatchState`。這 3 行就是該授權的實作。
   - C-B11 管的是 R、S、P 的判斷邏輯。這個欄位在 engine.py 只出現在這一處，不被任何條件讀取。W-B2、W-B2L 由 service 渲染，engine 不設定。
   - C-B8 與 C-B11 同屬 ADR-0034 附錄 C。把 C-B11 讀成禁止 C-B8，清單就會自相矛盾。
   - 原本寫「為空」，是本 ADR 起草時漏算 C-B8，錯在條文，不是 N-168 越界。

2. QB-20 第 4 小點改為：
   「確認 `git diff 9253032^1 9253032 -- app/playbook/engine.py` 只含 ADR-0034 C-B8 授權的照抄 hunk，也就是以下四項全部成立：
   - (a) 每個 hunk 都落在 `_snapshot_rows` 的 `BatchSnapshot(...)` 呼叫內；
   - (b) 新增行只有 `entry_before_exit_on=batch.entry_before_exit_on,` 與 `#` 註解行；刪除行為 0；
   - (c) 在 9253032 與 N-190 的 HEAD 上，engine.py 中 `entry_before_exit_on` 恰好出現 1 次（即上述 kwarg），`entry_before_exit_label`、`entry_before_exit_note`、`exit_stamped_on` 都出現 0 次；
   - (d) 這個 kwarg 的值是 `batch.entry_before_exit_on` 原樣，不經任何運算或條件。
   任一項不成立時，送 TA 判斷是否違反 C-B11。」

3. Decision 13「事後查核」一句改讀為：「qa-reviewer 在 N-190 PR 審查時，依補充一 E-2 第 2 點確認 9253032 對 engine.py 的 diff 只含 C-B8 照抄。」

4. QB-1 的 `<base>` 定義不變。N-168 的 hunk 本來就不計入 QB-1，本節不影響 QB-1。

### E-3 `SETTLED_SINCE_RULE_IDS` 的定義者（補充 Decision 9 第 5 點、N190-I；對 N-188 有約束）

1. 確認：
   - N-190 在 `app/playbook/store.py` 定義唯一一份 `SETTLED_SINCE_RULE_IDS: tuple[str, ...] = ("S1", "S2", "P1", "P2", "P3")`。值與順序等於 ADR-0035 補充五 X-1 第 1 點，與補充五修正一不衝突。
   - 位置理由：store 是唯一兩邊都能引用的模組。service（N190-I、本 ADR 的 (甲)）引用 store；N-188 的 `_read_settled_since` 在 store 內；store 不得 import wording（N172-C7）。
   - 定義者比照修正一 M1-2 第 1 點「先合者定義、後合者引用」：N-190 先合，由 N-190 定義。
   - 修正一 M1-1 條件 A 的運維探針依規定不 import app，所以必須寫字面。這不算第二份定義，由 N188-T20（[風控-0040] M-1）斷言探針 SQL 的 rule_id 字面等於本常數。

2. 對 N-188 的約束（併入 QB-18 檢查）：
   - 必須引用 `app.playbook.store.SETTLED_SINCE_RULE_IDS`。
   - `app/**` 內不得再定義第二份，也不得另寫這五個 rule_id 的 tuple、set 或 SQL `IN (...)` 字面。SQL 的 placeholders 由本常數產生。
   - 補充五 X-6 第 5 點與 QB-18.6 所稱的 `SETTLED_SINCE_*`，指 `wording.py` 的字面常數（`SETTLED_SINCE_SYMBOL_NOTE`、`SETTLED_SINCE_BATCH_NOTE` 及其組成常數），**不含** `SETTLED_SINCE_RULE_IDS`。QB-18.6 的 AST 或 grep 檢查必須排除這個名稱，不得因它定義在 store.py、或在 service 被引用而判為 BLOCKING。

3. 增減 rule_id 屬於補充五 X-1 的修訂，要回 TA 與風控。這會同時影響 N190-I、(甲)／B-4 的「S/P sell 列」、N-188，以及條件 A 的探針。

4. 檢查（qa-reviewer，BLOCKING）：
   - `app/**` 內 `SETTLED_SINCE_RULE_IDS =` 的指派恰好 1 次，在 `app/playbook/store.py`；
   - `app/**` 內沒有其他恰好由這五個 rule_id 組成的字面集合；
   - `scripts/n172_duplicate_probe.py` 屬 N-172 的既有分類，不在範圍內。
```

### ADR-0040 檔頭新增一行（放在「狀態」之後）

```
- 補充一（tech-architect 2026-11-07，回應 `work/reviews/2026-11-07-N190停止點QB17-dev-lead.md`）：ADR-0039 T15 的 QB-17 例外（E-1）、QB-20 事後查核的口徑（E-2）、`SETTLED_SINCE_RULE_IDS` 的定義者與對 N-188 的約束（E-3），以本檔末「補充一」節為準；本文不改。不擴大 CEO #110 的核可範圍；CEO 可推翻。
```

### ADR-0039 是否加註：**要，只加一行指標，不改內文**

理由：qa-reviewer 會直接依 ADR-0039 附錄 B 檢查 T15。不加指標的話，「第二次載入回傳不同資料」會被讀成仍是必要前提。ADR-0001 禁止原地改寫，這裡比照 ADR-0034、ADR-0039 檔頭列補充的先例。

```
- 加註（2026-11-07，見 ADR-0040 補充一 E-1）：ADR-0040 Decision 7 (i) 之後，`evaluate_today` 不再重新載入結算已載入的 symbol，所以附錄 B T15「第二次載入回傳不同資料時」的前提，在同一請求內已無法構造。T15 的前提斷言改為「僅載入一次」，並新增「分類用的就是 `run.loaded`」的接線斷言，依 ADR-0040 補充一 E-1。Decision 3 的不變式、v2 本文與補充一都不改。
```

### 對實作的約束（逐條可檢查）

1. 39-T15 的改動只限 E-1 第 2 點 (a)～(f)；第 700～703 行逐字不改；(c) 用 `is`。
2. 產品碼為這件事零 diff。
3. QB-20 依 E-2 第 2 點的 (a)～(d) 檢查。
4. `SETTLED_SINCE_RULE_IDS` 依 E-3 第 4 點檢查。N-188 的 QB-18.6 依 E-3 第 2 點排除這個名稱。

**其他部門**：本次未參與（純架構裁示）。
- 風控：不需回審。字面、行為都不變；E-3 只把 QB-18.6 的範圍講清楚。
- CEO：知悉即可。本補充依 QB-17、Decision 13 原有的授權作出，CEO 可推翻。

---

## 驗證

- **我沒有執行任何指令**：沒有 Bash，`git diff` 沒有跑。
  - QB-20 的 diff 內容，依據的是 dev-lead 的回報，加上 worktree HEAD 的 `engine.py` 內容一致（讀碼加 Grep：`entry_before_exit` 前綴在 engine.py 恰好 1 次）。
  - qa-reviewer 必須用 `git diff 9253032^1 9253032 -- app/playbook/engine.py` 親自核對 E-2 第 2 點的 (a)～(d)。
- **E-1 的「無法構造」是讀碼判定**，依據：
  - `service.py:1403-1416`：到期列全部載入；
  - `:1312-1316`：沿用的是同一個物件；
  - `:273`：涵蓋的判定式。
  - 我也考慮了並發的 EMERGENCY_EXIT：它在結算讀取與 `read_in_flight` 之間新增的列，執行日晚於 as_of，所以仍判為涵蓋。
- **dev-lead 改完後的驗收**：
  - 39-T15 為綠，而且 diff 只落在准改範圍內；
  - 全量 pytest 回到 0 failed；
  - 刻意把 `evaluate_today:2055` 的 `run.loaded` 改成 `loaded` 時，39-T15 必須轉紅，證明 (c) 有效。這個紅綠對照請附在 PR 說明。
- **本次未做**：沒有讀 `.env`；沒有碰 `data/*.db`；沒有寫任何檔案。

## 下一步

1. **coordinator → tech-writer**：上面三段 code block 落檔。
   - ADR-0040 檔頭一行、檔末補充一，放進 `docs/adr/0040-stock-desk-排程台以交易日判定為最新的快取日線視為可用.md`；
   - ADR-0039 檔頭的加註一行，放進 `docs/adr/0039-stock-desk-today常駐揭露待執行與近期已結算的出清指令.md`。
   - 同步通知 N-188 的負責人 E-3 第 2 點。
2. **coordinator → dev-lead**：在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190fix` 依 E-1 第 2 點改 39-T15，獨立成一個 `test:` commit，附上述紅綠對照。之後依原計畫接續 (甲)、P-B，用 merge 吸收 `8db5cab`，跑完整 CI。
3. **qa-reviewer**：PR 審查時加入 E-1 第 5 點、E-2 第 2 點、E-3 第 4 點三組檢查。其中 E-2 要親自跑 `git diff`。

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-07-N190停止點QB17-dev-lead.md`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190fix/apps/stock-desk/backend/tests/test_playbook_pending_exit_block.py`（:668-703）
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190fix/apps/stock-desk/backend/app/playbook/service.py`（:1299-1316、:1403-1416、:1968、:2055）
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190fix/apps/stock-desk/backend/app/playbook/engine.py`（:1077-1105）
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190fix/apps/stock-desk/backend/app/playbook/store.py`（:257-261）
- `/home/user/AICompany/work/reviews/2026-11-04-ADR0035補充五-tech-architect.md`（X-1、X-6 第 5 點、QB-18.6）
- `/home/user/AICompany/work/reviews/2026-11-05-ADR0035補充五修正一-tech-architect.md`（M1-1 條件 A、M1-2 第 1 點）
