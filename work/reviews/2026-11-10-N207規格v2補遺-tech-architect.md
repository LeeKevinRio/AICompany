# N-207 規格 v2 補遺（待 TA 10 項＋P-4 拆分＋set_capital 影響）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

10 項加上第 11 項都已寫成條文，可以直接貼進規格，見第二段的「N-207 規格 v2 補遺（TA 2026-11-10）」。補充題「`set_capital` 的修改會不會影響 N-207」也一併回答，編為補遺-12。全程唯讀：沒有執行指令，沒有改檔，沒有讀 `.env`，也沒有碰 `data/*.db`。

**評估摘要（結論先行）**
- **M1 清單統一為 8 條**：N-177a、N-195、N-196、N-197a、N-177b、N-198、N-209b、N-209。
  - CEO 若採 C-8（N-210a、N-210b 在 N-207 部署前合入），再加 N-210a、N-210b。
  - CEO 若接受殘留，不加這兩條，改在 M3 加一項：CEO 書面接受 R-a～R-g，逐項列名。
  - CEO 未裁示前，M1 清單無法確定，N-207 停在 review 之後。
- **執行者固定為 devops-sre**。dev-lead 一律不擔任，另開的 dev-lead 執行個體也不算「非實作者」，因為無法檢查兩者是不同的人。devops-sre 不能執行時，N-207 就等，不改派其他職能。
- **RC-38 所列的指令是例示，不是窮舉**。凡不在 `READONLY_ALLOWED_BASH` 內的 git 指令（M1、R0～R6、控制組、M5）都由執行者執行。`git cat-file -e` 的 exit 不是 0 時，判 **BLOCKING**；控制組結果不符預期時，也判 BLOCKING。
- **N9-07 第二句的處理**：§0 增列一個很窄的例外，只准改 N-209 那一個常數的字串值。
  - 只有當 N-209 合入的程式裡，這句是單一定義時才成立；不是時停下回 TA，N-207 不得重構 N-209 的元件。
- **簽名**：
  - `portfolio_frozen` 回傳 `PortfolioFreeze(frozen, until)`，型別是 NamedTuple；
  - `plan_change` 的參數改為 `frozen: PortfolioFreeze`；
  - 名單路徑不需要凍結的種類。
- **K 結尾代號的分支**：
  - 新增純函式 `symbol_k_suffix(symbol) = symbol.endswith("K")`，先於形狀檢查判定；
  - 這類代號一律不送網路驗證；
  - 拒絕結構改成逐筆列出問題（`SymbolIssue`），這樣才做得到 AC-91 要的「同一請求裡 K 與形狀錯誤各用各的句子」。
- **要出 v3**：依 PRD v3.4、RC-40～55、ADR-0044 修訂一，加上本補遺。差異清單有 19 項，見補遺-8。其中一項是更正我自己在補遺三寫的 P-6 舊句。
- **測試**：新增 T24～T29；T6 加 (j) unauthored、(k) cash_unrecorded；T17、T11 加 K 的情境。
- **1d-2 的 grep 要在 N-207 實際送審的 commit 上重跑**，定為交件檢核 N207-M5。
- **第 11 項（RC-54）**：
  - P-4 拆成 P-4a（只回檔數）、P-4b（代號，只在 CEO 本機看）；
  - 另外增列 P-4c（欄值異常 → STOP-4）；
  - §9 全部的 DB 盤點只由 CEO 在本機執行，agent 只收布林值或計數；
  - RC-55 的移除方式只登錄為待辦。
- **補充題（ADR-0044 Decision 7 第 3 款）**：不改 N-207 任何條文的字面，但有三個實際影響：
  1. **同一次讀取的方法重複**：N-207 的 `portfolio_and_stamp()`、ADR-0044 (iii-c) 的 `portfolio_with_stamp()`、N-209b 的 `capital_record()` 都是同一次 `_state_map()` 讀取，定義有三份，要收斂。我新增約束 N207-C20 處理。
  2. **測試不得再用 `at=`**：N-207 的測試（例如 T6 的 ABA 情境）不得用 `at=` 種入 set_at，改用直接 SQL 種入。
  3. **T9 的等待點**：涉及 confirm 的交錯測試，等待點移到 `BEGIN IMMEDIATE`。斷言不變。

**方案比較（關鍵取捨）**

| 議題 | 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|---|
| 第 3 項 執行者 | (a) 只限 devops-sre | 兩條件同時成立，而且可以檢查 | devops-sre 不能執行時要等 | 低 | **採用** |
| | (b) 允許另一個 dev-lead 執行個體 | 有彈性 | 任務單與 commit 都分辨不出是不是同一個實作者，qa 無從檢查 | 中 | 否決 |
| | (c) 擴大到 frontend-engineer、qa-automation | 有彈性 | 超出 RC-38 的名單；frontend-engineer 本身可能是實作者 | 中 | 否決，要擴大須回風控 |
| 第 5 項 N9-07 | (a) §0 加窄例外，只改常數值 | 符合 N9-07「由 N-207 PR 接上」 | 要靠 N-209 是單一定義 | 低 | **採用** |
| | (b) 另開一張後續單 | N-207 的 diff 更乾淨 | N-207 合入到後續單之間，字面不符風控定稿 | 中 | 否決 |
| 第 7 項 拒絕結構 | (a) 單一 Literal 原因 | 改動小 | 做不到 AC-91 的混合請求 | 高 | 否決 |
| | (b) 逐筆列出 `symbol_issues` | 符合 AC-91 與 RC-50 | 拒絕型別要改 | 低 | **採用** |
| 第 11 項 P-4 判定 | (a) `= 1` | 與原文相同 | 遇到 app/ 以外寫入的非 0／1 值會漏算 | 中 | 否決 |
| | (b) `<> 0`，加上 P-4c 異常檢查 | P-4c 為 0 時與 (a) 等價，異常值另外停下 | 多一條查詢 | 低 | **採用** |

**ADR**：不需要新 ADR，也不取代任何 accepted 或 proposed ADR。本補遺沒有改 `READONLY_ALLOWED_BASH`，所以不觸發 CLAUDE.md §4 的 ADR 程序。補遺-12 只約束 N-207 怎麼和 ADR-0044 的實作對齊。

## 二、各部門回報

### tech-architect（本人，唯讀）

---

# N-207 規格 v2 補遺（TA 2026-11-10）

- **疊加對象**：`work/reviews/2026-11-10-N207實作規格v2彙整-dev-lead.md`。本補遺覆蓋該檔「待 TA」第 1～10 項，加上 coordinator 追加的第 11 項與補充題（補遺-12）。
- **依據**：
  - PRD v3.4（3c1de93）；
  - 風控 RC-36～RC-47（`2026-11-10-交付B裁示ADR0044審查與字面定稿-風控.md`）；
  - 風控 RC-48～RC-51（`2026-11-10-補擬四句裁定-風控.md`）；
  - 風控 RC-52～RC-55（`2026-11-10-N207部署通知定稿-風控.md`）；
  - ADR-0044 修訂一（`2026-11-10-ADR0044修訂一與RC42C1W25f確認-tech-architect.md`）；
  - CLAUDE.md §4。
- **標記**：標「〔TA 追加，送風控知悉〕」的條文都屬加嚴，風控可以刪。

## 補遺-1：前置依賴清單統一（取代 §9.1 兩欄並列的表，以及 N207-M1 的清單）

1. **唯一清單**：§9.1 與 N207-M1 以本條為唯一清單。派工指示的清單不是規格來源，coordinator 依本條更正派工紀錄。
2. **固定項，共 8 條**：N-177a、N-195、N-196、N-197a、N-177b、N-198、N-209b、N-209。
   - **N-177b、N-198 列入**。修一 丙是最後生效的 TA 來源，之後沒有任何來源撤回它。N-207 的 T5、T21（N198-T5、ADR-0041 T27）與 N207-C3（`claim_and_settle` 零 diff），都以 ADR-0041、ADR-0042 已經落地為前提。
   - **N-209b 列入，以 `<M_209b>` 直接驗證**。N-207 旗標為真版的字面「規則集確認前，REBALANCE 不會執行」，以及 T6 (j)(k) 兩個情境，只有在 N-209b 的 authorship 閘與現金鍵閘在 base 內時才成立。「N-209b 是 N-209 的前提單」並不等於已經檢查過 `<M_209b>` 是 `<base>` 的祖先。
   - **先後**：各單合入的先後依各自規格。M1 只驗證祖先關係，不驗證彼此先後。
3. **N-210 的條件項**（CEO 的裁示見補遺-2）：
   - **情況 A**（CEO 採 C-8：N-210a、N-210b 在 N-207 部署前合入）：M1 加 N-210a、N-210b。CEO 若採 (iii-c)、拆成 N-210c，而且指定 N-210c 也要在 N-207 部署前合入，再加 N-210c。
   - **情況 B**（CEO 接受殘留，N-207 先上線）：M1 不加。改依補遺-2 在 N207-M3 加第 (4) 項。
   - **CEO 未裁示**：M1 清單無法確定，N-207 停在 review 之後，不得合併。
4. **M1 指令**：清單中每一個 `<M_x>`（完整 40 碼）各跑一次 `git merge-base --is-ancestor <M_x> <base> 2>&1; echo "exit=$?"`，全部都要是 `exit=0`。執行者依補遺-3。
5. **〔TA 追加，送風控知悉〕回退偵測，比照 R2、R3**：
   - **範圍**：N-209b 一律適用；情況 A 時，N-210a、N-210b（及 N-210c）也適用。
   - **做法**：對每一個 `<M_x>` 跑 `git rev-list <M_x>^1..<M_x>^2`，令 S_x = 輸出 ∪ {`<M_x>`}。再對 S_x 的每一個 s 跑 `git log -F --grep=<s> --format=%H <M_x>..<base>`。
   - **判定**：BLOCKING 條件與 R2、R3 相同（R2 沒有輸出時回 TA 定替代的 S，不得自行補）。
   - **已知限制**：同補遺-4 的已知限制。
6. **連動規則**：
   - N-207 合入之前，清單中任一單被回退，M1 不成立；
   - N-207 合入之後，N-209b 被回退時依補二 2b 第 3 點處理；
   - 情況 A 下，N-210a 或 N-210b 在 N-207 合入後被回退，必須先回風控並由 CEO 重新裁示，因為 CEO 裁示的前提已經失效。

## 補遺-2：N-210（條件式條文，取代 §9.1 的 N-210 段）

1. **共同條件（兩種情況都要成立）**：
   - AC-84 所說的「風控審過」，以 **ADR-0044 修訂一全文**為準，包括 Decision 7 第 3 款與 (iii-c)。風控 11-10 的 CONDITIONAL APPROVE 審的是草案；修訂一回送風控確認完成之前，AC-84 不成立。
   - CEO 的書面裁示必須寫明三件事：(a) 修正或接受殘留；(b) (iii-c) 採不採；(c) N-210a、N-210b 與 N-207 部署的先後。
   - 裁示沒有涵蓋這三件事時，視為未裁示（補遺-1 第 3 點）。
2. **情況 A（N-210a、N-210b 先於 N-207 部署）**：
   - M1 依補遺-1 第 3 點加列。
   - N-210 各單的合入前提依 ADR-0044 Decision 6，不在本規格範圍。
3. **情況 B（N-207 先上線；包括「選修正，但 N-210 晚於 N-207」）**：
   - N207-M3 加第 (4) 項：CEO 書面接受 ADR-0044 殘留 R-a～R-g，逐項列名，而且寫明 ADR-0044 Decision 6 那一句：「N-210a／b 合入之前，`/today` 沒有標示，REBALANCE 結果沒有清單，只有 N-209 前端的 N9-05、N9-06 兩句靜態字面」。
   - 這份書面記入交件紀錄；qa-reviewer 檢查紀錄存在，而且七項都有列名。
4. **兩種情況都適用**：
   - N-207 的字面只有一個版本，不得引用 N-210 的標示或清單；
   - N-207 的 diff 不得碰 `KEPT_PENDING_ENTRY_SQL`、`td_rewritten_since`、`kept_pending_entries`、`td_basis`。

## 補遺-3：檢查指令的執行者（取代補遺-4 與 RC-38 的執行者句，兩者同時成立）

1. **「N-207 實作者」的定義**：N-207 任務單列名的實作職能，加上在 `<base>..<head>` 範圍內有 commit 的職能。依現行派工，是 dev-lead（後端）與 frontend-engineer（前端）。
2. **執行者固定為 devops-sre**。dev-lead 一律不擔任，另開的 dev-lead 執行個體也一樣。理由是職能以角色辨識，任務單與 commit 紀錄都無法分辨同一角色的不同執行個體，qa 也就無從檢查。
3. **devops-sre 本身是實作者時**（在 N-207 任務單列名，或範圍內有它的 commit）：停下，回 TA 與風控，不得改派其他職能。
4. **devops-sre 不能執行時**：N-207 停在 review 之後等待。不得改由 dev-lead、frontend-engineer、qa-automation 或其他具 Bash 權限的職能執行。RC-38 只列了 dev-lead、devops-sre，要擴大名單須回風控。
5. **紀錄與檢查**：
   - coordinator 在派工紀錄中指定執行者；
   - 審查紀錄的每一段輸出都標明執行職能；
   - qa-reviewer 檢查兩件事：執行職能是 devops-sre，而且 devops-sre 不在第 1 點的實作者範圍內。不符合時判 **BLOCKING**。
6. **適用範圍**：補遺-4 表中的全部指令（M1、M4、M5，以及補遺-1 第 5 點）。

## 補遺-4：RC-38 的執行範圍補齊，以及 R6 的判定

1. **條文**：RC-38 列出的 R3 `git log`、R5 `git grep`、`git cat-file` 是例示。依 CLAUDE.md §4，凡不在 `READONLY_ALLOWED_BASH`（`codex`、`git diff`）內的指令，一律由補遺-3 的執行者執行；唯讀職能只判讀。
2. **指令格式**：每條指令後面都接 ` 2>&1; echo "exit=$?"`（加上 `2>&1`，讓錯誤訊息也進到完整輸出）。原文、完整輸出、`exit=` 行與讀取時間（到分鐘，Asia/Taipei）原樣記錄。

| 編號 | 指令 | 在 `READONLY_ALLOWED_BASH` 內？ | 執行者 |
|---|---|---|---|
| R0〔TA 追加〕 | `git rev-parse --verify <head>^{commit}`；`git rev-parse --verify <base>^{commit}` | 否 | devops-sre |
| M1-x | `git merge-base --is-ancestor <M_x> <base>`（補遺-1 的每一條） | 否 | devops-sre |
| R1 | `git merge-base --is-ancestor <M_209> <base>` | 否 | devops-sre |
| R2 | `git rev-list <M_209>^1..<M_209>^2` | 否 | devops-sre |
| R3a～c | 補遺-4 原文的三種 `git log` | 否 | devops-sre |
| R3d〔TA 追加〕 | 補遺-1 第 5 點的 `git rev-list` 與 `git log -F --grep=<s>` | 否 | devops-sre |
| R4 | `git diff --name-status --diff-filter=D <M_209> <base> -- <路徑>`（不得加 `--exit-code`、`--quiet`） | 是 | devops-sre 執行並記錄；qa-reviewer 可用自己的 `git diff` 權限逐字重跑同一條 |
| R5 | `git grep -c -E '<regex>' <base> -- <路徑>` | 否 | devops-sre |
| R6 | `git cat-file -e <M_209>:<路徑>` | 否 | devops-sre |
| 控制組 | `git log -F --grep=0000000000000000000000000000000000000000 --format=%H <M_209>..<base>` | 否 | devops-sre |
| M5 | 補遺-10 的 `git grep` | 否 | devops-sre |

3. **判斷者的 BLOCKING 清單，增列以下幾點**：
   - **R0**：`<head>` 不等於 qa 審查的那一個 commit，或任一條不是 `exit=0`。
   - **M1**：任一條不是 `exit=0`。
   - **R6**：任一條不是 `exit=0`，判 **BLOCKING**。
     - 理由：R6 用來證明錨點路徑在 `<M_209>` 存在。exit 不是 0（路徑不存在時，依 git 文件推論是 exit 128）就表示錨點路徑打錯或從未存在，R4 會因此靜默放行。
     - 處置：回 TA 修正錨點登錄，執行者與 qa 都不得自行改路徑。
   - **控制組**：有輸出，或不是 `exit=0`，判 BLOCKING。零命中語意沒有被實證時，R3 無法判讀。
   - **R4 重跑**：qa 重跑的輸出與執行者的紀錄不同，判 BLOCKING，回 TA。
   - **執行者**：不符合補遺-3，判 BLOCKING。
4. qa-reviewer 除了 R4 的逐字重跑之外，不得執行表中任何指令。

## 補遺-5：§0 diff 範圍補齊 N9-07，新增約束 N207-C19

1. **§0「允許」增列一項**：
   - 範圍：N-209 的入口停用事實句（N9-07）的**唯一定義**。不論它在前端常數檔還是 `wording.py`，以 N-209 錨點登錄的「N9-07 位置」為準。
   - 只准做一件事：把該常數的字串值由第一階段全文，換成風控 11-10 第三部分 N9-07 第二階段全文。
   - 同檔其他行零 diff。
2. **錨點登錄加項（補遺-4 錨點清單的變更，由 TA 在此定義）**：N-209 合入時，coordinator 在錨點登錄加記「N9-07 位置：檔案路徑加識別名」。
3. **N207-C19（BLOCKING）**：
   - (a) **diff 範圍**：以 AST 比對該常數，只有字串值不同，其餘節點與 base 相同。顯示條件、後端停用旗標、停用邏輯都零 diff（N-209 FR-2 (b)、RC-34）。
   - (b) **逐字比對**：新值以程式從風控原檔逐字比對，N207-C16 的逐字比對適用。這是 C16「新字面只放在 `wording.py`」的唯一例外。
   - (c) **grep 計數**：在 frontend 與 backend 的原始碼中（不含 tests），第一階段全文作為獨立常數值出現 0 次，第二階段全文出現恰好 1 次。
   - (d) **前提**：N-209 合入的程式中，N9-07 必須是單一定義。若是內嵌在 JSX、有兩份以上，或停用狀態根本沒有實作，就停下回 TA，N-207 不得重構 N-209 的元件。
   - (e) **R5 regex**：N-209 登錄的 R5 regex 不得命中 N9-07 常數的值所在的那一行。命中時，coordinator 在 N-207 送審前回 TA 修改錨點。
   - (f) **commit**：放在 §10 第 6 個 commit（字面）。N-207 被回退時，這一處也一起回到第一階段。這是正確的，因為沒有 N-207 就沒有「待生效」。
4. **測試**：見補遺-9 的 N207-T29。

## 補遺-6：`portfolio_frozen` 與 `plan_change` 的簽名（取代 §2 兩行；補二 C-T05-1 的實作形式）

```python
# app/playbook/models.py
class PortfolioFreeze(NamedTuple):
    frozen: bool
    until: date | None

# app/playbook/roster.py
def portfolio_frozen(*, emergency_until: date | None, freeze_until: date | None,
                     today_tpe: date) -> PortfolioFreeze: ...
def plan_change(*, op: RosterOp, facts: RosterFacts, params: RuleParams,
                window: QuarterWindow, frozen: PortfolioFreeze) -> RosterPlan | RosterRefusal: ...
```

1. **不變式**（以參數化表加性質測試釘住，見 T24）：
   - `frozen` 為真，等價於兩個值中有一個不為 None 且 ≥ `today_tpe`；
   - `frozen` 為真，等價於 `until is not None`；
   - `frozen` 為真時，`until` 等於兩個非 None 值的最大值。
2. **`today_tpe`**：
   - 鎖內取自唯一一次時鐘讀取（D4 第 3 點 (b)）；
   - API 預檢取自 service 注入的時鐘；
   - 兩者與 D8 第 6 點同一個來源。
3. **解析**：`emergency_until`、`freeze_until` 在 store 內，以與 `portfolio_state()` 相同的 parse helper 解析。解析失敗就 raise，依 C-11 ROLLBACK，零寫入。
4. **`plan_change` 的行為**：
   - 首次設定、重新加入、開新輪、季度提交：在 `frozen.frozen` 為真時回 `RosterRefusal("portfolio_frozen", until=frozen.until)`；
   - 停止新進場、高波動標記：不看 `frozen`（D4 矩陣）。
   - `plan_change` 不得直接讀 `emergency_until`、`freeze_until`。
5. **不需要凍結種類**：
   - 名單路徑（`roster.py`；名單的 store、service、API 方法；名單前端）不讀取、也不回傳凍結種類；
   - 名單 API 的回應 schema 不含 `mode_reason`；
   - 依據是 RC-24：字面不得重述 mode_reason，而且凍結拒絕只有一個原因。

## 補遺-7：K 結尾代號的拒絕分支（RC-43、RC-50；取代 N207-C12 的〔待 TA 第 7 項〕，並修改 §6 的拒絕型別）

1. **判定函式**：`roster.py` 新增 `def symbol_k_suffix(symbol: str) -> bool`。
   - 本體恰好是 `return symbol.endswith("K")`，判定的是最後一個字元是否為 ASCII 大寫 `K`（U+004B）。
   - 本體不得有任何 strip、upper、lower、casefold、replace、`unicodedata`、`re` 呼叫，以 AST 檢查。
   - 判定前不做任何正規化（RC-50）。
2. **拒絕型別**：

```python
SymbolIssueKind = Literal["k_suffix", "shape", "duplicate"]
class SymbolIssue(NamedTuple):
    input: str          # raw submitted string, byte-identical to what is displayed
    kind: SymbolIssueKind
```

   - `RosterRefusal` 的原因 Literal 用 `"symbol_input"` 取代原本的「形狀」「重複」兩個原因，並帶 `symbol_issues: tuple[SymbolIssue, ...]`。只有在原因是 `"symbol_input"` 時，這個欄位才非空。
   - 每一種 kind 對應一個 `wording.py` 識別名：`k_suffix` 對 W-05m，`shape` 對 W-05g，`duplicate` 對既有的重複句。識別名由 dev-lead 定，但必須一對一。
3. **判定順序**（只對新代號，也就是首次設定與季度提交的新增組，C12）：
   1. API 層的窗口判定，然後是凍結判定；
   2. 本地代號檢查，全部是純函式，依輸入順序逐筆判定：
      - `symbol_k_suffix` 為真 → `k_suffix`；
      - 否則 `symbol_shape_ok` 為假 → `shape`；
      - 通過這兩項的輸入之間，以原始字串完全相等判定 `duplicate`，每個重複值列一次。
      - 本步驟的所有問題一起回傳。
   3. 第 2 步有任何問題時，整批拒絕，**零網路呼叫**（K 結尾與形狀不符的代號都不得送進 `load_bars`）、零寫入；
   4. 第 2 步沒有問題時，才做既有的 `load_bars` 驗證（確定性失敗與暫時性失敗）；
   5. 之後才進鎖。
4. **與形狀規則的關係**：
   - data-engineer 的 regex 本來就讓所有 K 結尾字串不符形狀；
   - 因為 K 檢查排在前面，形狀分支不會對 K 結尾的代號觸發，滿足 AC-91 的「兩條分支各自獨立」；
   - `symbol_shape_ok` 的函式層反例（N14、N15）維持不變。
5. **RC-50 接受的殘留**：`ABCK` 一類輸入只會收到 W-05m。
6. **呈現**：
   - API 回傳 `SymbolIssue.input` 原字串；
   - 前端以純文字呈現，放在 `white-space: pre-wrap` 的元素內，空白不被折疊；
   - 前端不做任何 K 判定或形狀判定，以 grep 檢查名單前端沒有 `endsWith("K")` 與形狀 regex。
7. **字面**：W-05m 依 RC-50 定稿全文，以程式逐字比對。K 分支的回應不含「不符合台股代號格式」。
8. **測試**：見補遺-9 的 T17、T11。

## 補遺-8：出 v3，差異清單（dev-lead 據此出 v3）

結論：**出 v3**。

1. **來源表**：
   - PRD 由 v3.3 改為 v3.4（3c1de93）；
   - 加入 RC-40～47、RC-48～51、RC-52～55；
   - 加入 ADR-0044 修訂一（含 RC-42 單調性確認與 W-25f 確認）；
   - 加入本補遺；
   - 附錄 C 的內容全部吸收，附錄 C 刪除。
2. **§9.1、M1、M3**：依補遺-1、2 改寫。
3. **M4 執行者與指令表**：依補遺-3、4 改寫。R6 列入 BLOCKING；AC-94 對應。
4. **§0 與約束**：依補遺-5，加 N207-C19。
5. **§2 簽名**：依補遺-6 改寫。
6. **N207-C12、§6 拒絕型別、T11、T17**：依補遺-7 改寫（RC-43、RC-50、AC-91）。
7. **§9 P-6 處置（更正 TA 補三）**：
   - 補三 B-4 寫的「CEO 部署通知要寫明『首次設定後，只能經 REBALANCE 解開待生效』」，依 RC-45(a) 判為不實，刪除。
   - 改為：P-6 為真時，發出 RC-52 定稿的「N-207 部署通知」第一段（FR-53、AC-92）。CEO 第一次使用「設定標的名單」之前，必須送達並有書面確認收到。
8. **§9 P-7**：改為「風控書面回覆記入交件紀錄之前不得部署」（RC-45(b)、AC-90）。
9. **§9 P-8**：
   - 加上「SQL 出錯視為未完成盤點」（AC-93）；
   - 加上殘留說明：賣出成交建立的現金鍵，P-8 偵測不到，交 CEO。
10. **§9 P-4、STOP-3、執行方式**：依補遺-11 改寫（RC-52～55）。STOP-3 的通知改為「RC-52 第二段」，不列代號。
11. **C-T24 與 W-24**：
    - 採 RC-48 的預核全文；
    - C-T24 加上「只適用於待進場的批次計算股數時」的限定；
    - 「被跳過」指 status 為 skipped 的批次；
    - RC-48 的 suggested（輪內已經沒有 planned 時要不要顯示）待 PM 決定，決定前照 PRD。
12. **W-10**：依 RC-51 刪除 `{SHAPE_RULE_DESC}` 與它的標籤。§6 加一條約束：畫面上沒有形狀規則欄位，以 Vitest 檢查。
13. **W-25f**：
    - 依 TA 修訂一交付 3 定稿；
    - §6 加後端顯示條件 W25f-1～3（判定式、參考日 `today_tpe`、{M}/{D} = `next_trading_day(changed_on)`）；
    - O-1、O-2 待風控，不擋 W-25f。
14. **W-27**：改用 RC-46 定稿全文；顯示旗標的規則不變。
15. **FR-46、D7 第 6 點**：用「適用」（RC-44），交 tech-writer 同步 ADR-0043。
16. **N207-M3 的狀態行**：
    - W-24：預核定稿（RC-48）；
    - W-05m：定稿（RC-50）；
    - W-10：B 版定稿（RC-51）；
    - W-25f：定稿；
    - W-19：仍待 `round_spans` 落地；
    - N9-07 第二階段：由 N-207 PR 接上。
17. **FR-21、AC-57**：status 名稱一律用 `cash_unrecorded`。
18. **補遺-12**：加 N207-C20，並加上測試種入方式的約束。
19. **補遺-9 的測試編號**：併入 §8；刪除 T13 的〔dev-lead 推導〕標記，該斷言移到 T24。

另外，RC-40～42、RC-49 屬 N-209 與 N-209b 的範圍，v3 只在來源表登錄，不改 N-207 的條文。

## 補遺-9：測試編號（併入 §8，全部 BLOCKING）

- **N207-T6 增列 (j)、(k)**（AC-57；需要 N-209b 在 base 內，見補遺-1）：
  - **(j) unauthored**：
    - 情境：未確認狀態（沒有確認鍵，也沒有參數列）下完成首次設定，接著呼叫 REBALANCE，得到 `unauthored`。
    - 斷言：
      - `playbook_state` 全表傾印前後逐位元相同，所以戳記不變；
      - 各批 `entry_gate` 不變；
      - 以讀到的戳記直接呼叫 `engine_batches` 與 `entry_gate_open`，新批次不在輸入內，閘為關；
      - 之後跑 `confirm_rules` 成功，閘才開。
    - 注意：未授權時 `evaluate_today` 走提前返回，不經 engine，所以本情境直接呼叫上述兩個純函式。
  - **(k) cash_unrecorded**：
    - 情境：以直接 SQL 種入「已確認而且沒有現金鍵」（P-8 狀態），完成名單寫入，接著呼叫 REBALANCE，得到 `cash_unrecorded`。
    - 斷言：
      - state 逐位元相同，閘為關；
      - `evaluate_today` 的 engine 輸入不含新批次；
      - `/today` 的 `rules_fully_evaluated` 為 false，排除揭露行屬第 (4) 類。
  - 實際合入的 status 名稱若不同，以實際名稱為準，並回 TA。
- **N207-T24 凍結截止日（C-T05-1～3；RC-24；AC-59、60）**：
  - 以參數化表測 `portfolio_frozen`：兩個都是 None；只有一方 ≥ 今日；兩方都 ≥ 今日（`until` 取較晚者）；一方已過、一方未過；until 等於今日（凍結）；until 等於昨日（不凍結）。
  - 性質測試至少 300 組 seed，驗證補遺-6 第 1 點的不變式。
  - 凍結期間，停止新進場與高波動標記都成功。
  - 以 AST 檢查：API 預檢與鎖內都只透過 `portfolio_frozen` 判定。
  - 名單 API 的 `until` 等於函式的回傳值。
  - 字面含「（含當日，台北日期）」，不含「之後即可變更名單」，也不含任何 mode_reason 字串。
  - SQL trace：凍結判定沒有任何寫入。
  - 原 T13「`until` 為兩者較晚者」的斷言移到本條。
- **N207-T25 `first_confirmation_pending`（C-T09-1、C-T09-2；RC-30）**：
  - 四種 authorship 狀態（沒有確認鍵也沒有參數列、只有確認鍵、只有參數列、兩者都有）下，旗標分別為 True、False、False、False，而且等於 `not rule_set_authorship(today).user_authored`。
  - W-04b、W-08a、W-09c、W-09d、W-12b：
    - 旗標為真版：含「確認規則集並設定資本額」與「規則集確認前，REBALANCE 不會執行」，不含「重算部署資金（REBALANCE）」；
    - 旗標為假版：含「「重算部署資金（REBALANCE）」執行成功」與子句 F 的全文，不含「確認規則集並設定資本額」；
    - 兩版都以程式從風控原檔逐字比對。
  - Vitest 效力證明：mock 旗標為 true、`mode` 為 confirmed 時，仍然呈現旗標為真版。這證明前端沒有自行推斷旗標。
- **N207-T26 差額與多重分類計數（C-T13-1、C-T13-2；RC-21）**：
  - X、W、X−W 以及四類計數都由後端給；四類的謂詞依 C-T13-2；同一檔可以同時算進多類，各類加總可以大於差額。
  - 名單頁的 S2 以注入時鐘的 `today_tpe` 判定：資料日落後時，名單頁與 `/today` 的結果可以不同，斷言兩者各自正確。
  - 改變黑名單時，`roster_digest` 與 `plan_change` 的結果不變（S2 只用於顯示）。
  - W 只經 `engine_batches` 計算（C8）。
  - Vitest：mock 一個故意不一致的差額（≠ X−W），前端照後端的值呈現。
- **N207-T27 最新一輪與 bpt 不一致（C-T24-1、C-T24-2；RC-36、RC-48）**：
  - 只依最新一輪判斷：舊輪不一致、最新一輪一致時，不出現 W-24。
  - actual 依 (symbol, batch_round) 從帳冊計數。
  - `round_size_vs_bpt` 的 less／greater 兩個方向都測；相等時沒有這個欄位。
  - greater 時的顯示批號 N = 該輪 `min(batch_no) − 1 + bpt`。
  - W-24 兩版與 RC-48 預核全文逐字比對。
  - W-11 在第 1 輪也用實際批數與輪次。
  - Vitest：前端不比較 actual 與 bpt。
- **N207-T28 `later_round_keys` 與 `round_spans`（C-T19-1、C-T19-2）**：
  - `later_round_keys` 等於 `book` 中 `batch_round ≥ 2` 的全部 `(symbol, batch_no)`，包括不在 engine 輸入內的批次；
  - `round_spans` 只列 `/today` 有引用的 (symbol, round)，各欄與帳冊一致；
  - 以 AST 檢查 `engine.py` 不出現 `round_spans`。
- **N207-T29 N9-07 第二階段（補遺-5）**：
  - Vitest：後端停用旗標的 mock 為真時，呈現第二階段全文（逐字）；為假時不呈現；
  - 加上 N207-C19 (a)(c) 的 AST 與 grep 檢查。
- **N207-T17 增列（補遺-7）**：
  - 走 `k_suffix` 的輸入：`00625K`、`2330K`、`ABCK`、` 00625K`（開頭有空白）；
  - 走 `shape` 的輸入：`2330k`、`00625Ｋ`（全形 K）、`00625K `（結尾有空白）、`00625K\n`；
  - 混合請求 [`00625K`, `2330.TW`, `2330`]：回 `symbol_issues == ((00625K, k_suffix), (2330.TW, shape))`，零寫入，loader spy 呼叫 0 次；
  - 性質測試至少 300 組 seed：任一字串 s 只要 `s.endswith("K")`，分類一定是 `k_suffix`，不會是 `shape`；
  - W-05m 代入 `{input}` 後與 RC-50 原文逐字相同。
- **N207-T11 增列**：
  - `k_suffix` 列入逐一跑的拒絕原因，零寫入；
  - 原本的「形狀」「重複」兩個原因，改為 `symbol_input` 下的兩種 kind。

## 補遺-10：交件檢核 N207-M5（1d-2 前提在 N-207 實際送審的 commit 上重跑）

1. **時點與對象**：
   - 對象是 `<head>`，也就是 qa 審查的那一個 commit，在 M2 merge 最新 product 之後；
   - 時點是 §9 盤點之前；
   - head 一變動，就重做。
2. **指令**（執行者依補遺-3；每條後接 ` 2>&1; echo "exit=$?"`）：

```
git grep -n -E '(^|[^A-Za-z0-9_])Directive\(' <head> -- apps/stock-desk/backend/app/
git grep -n -E '_make_directive\(' <head> -- apps/stock-desk/backend/app/
git grep -n -E 'batch_no[[:space:]]*=[[:space:]]*None' <head> -- apps/stock-desk/backend/app/
git grep -n -E 'model_copy\(.*batch_no|"batch_no"[[:space:]]*:' <head> -- apps/stock-desk/backend/app/
git grep -n -E 'INSERT INTO playbook_directives' <head> -- apps/stock-desk/backend/app/
```

   - 寫法說明：不用 `\b`，因為 ERE 的 `\b` 依實作而定，不可攜。第 3 條是附錄 A 寫法的超集，涵蓋等號兩邊有空白的情形。
3. **判讀**（由 qa-reviewer 判讀，不採用執行者的結論）：
   - 第 1、2、5 條必須是 `exit=0`。`exit=1` 表示路徑或 pattern 有錯，判 BLOCKING。
   - 第 4 條預期是 `exit=1`（零命中）。是 `exit=0` 時，逐筆判讀。
   - 與附錄 A 的基準（a624250）相比，每一筆新增的命中，qa-reviewer 都要讀碼，照附錄 A-2 的格式填表（位置、規則與 action、`batch_no` 來源、可不可能為 None）。
   - 第 5 條除了 `_insert_directives` 之外還有其他 INSERT 時，回 TA。
4. **結論與處置**：
   - 只要出現 S2（`_evaluate_symbol_stop`）以外、action 為 buy 或 sell、`batch_no` 可能為 None 的建構點，就回 TA 與風控（RC-37），不得自行加排除條件。
   - 1d-2 的前提在此成立之前，§9 的 1d-2 SQL 不得照原文使用，部署暫停。
   - 判讀結果記入交件紀錄。
5. **已知限制**：這是靜態檢查。以變數傳入 None 的情形，由逐筆讀碼承擔。

## 補遺-11：§9 盤點的執行邊界與 P-4 拆分（RC-54、RC-55）

1. **§9「執行方式」改寫**（取代修一 乙「只回傳數字與代號」一句）：
   - **執行**：§9 全部對 CEO DB 的盤點，一律由 CEO 在本機執行，以唯讀模式開啟連線（T-20 第 1 步）。範圍是 P-1～P-8、P-4a～P-4c、1d、1d-2。RC-54 寫的是 P-2～P-8；P-1 若以每檔一列輸出就會帶出代號，所以一併納入，屬加嚴。
   - **回報**：只回傳布林值或計數，不回代號、不回金額，沒有例外。
   - **P-4b 的處理**：輸出只留在 CEO 本機的畫面，不回傳。
   - **不得執行的人**：任何 agent（包括 devops-sre、data-engineer、TA、實作者）都不得對 CEO DB 執行任何查詢（R12）。
   - **SQL 的準備**：判定 SQL 由 data-engineer 打包成腳本、devops-sre 覆核。覆核只看 SQL 文字，不接觸 DB。
2. **與 RC-38 的區分**：

| | 對象 | 執行者 | agent 收到什麼 |
|---|---|---|---|
| M1、M4（R0～R6、控制組）、M5 | git 物件，不碰 DB | devops-sre（補遺-3） | 完整輸出 |
| §9 盤點 | CEO 本機的 DB | 只有 CEO | 只有布林值或計數 |

3. **輸出形狀的要求**（P-1、P-2、P-3、P-5 的 SQL 要在盤點前改成這個形狀）：
   - P-1：批數不等於 bpt 的檔數；
   - P-2：最大值大於 bpt 的檔數、最小值不等於 1 的檔數、最小值小於 1 的檔數、有斷號的檔數；
   - P-3：distinct symbol 的檔數，以及 `n_targets` 的值；
   - P-5：例外的列數。
   - 不得有「每檔一列」的輸出。
4. **P-4 拆分**（判定 SQL 由 TA 給；P-4a 大於 0 時，RC-52 第二段送出之前，拆分與腳本必須已經完成）：

```sql
-- P-4a: count only; may be reported and recorded
SELECT COUNT(*) FROM playbook_symbols WHERE high_volatility <> 0;

-- P-4b: CEO local screen only; output must never be pasted into chat, work/, records, or any agent
SELECT symbol FROM playbook_symbols WHERE high_volatility <> 0 ORDER BY symbol;

-- P-4c: anomaly count; may be reported
SELECT COUNT(*) FROM playbook_symbols
WHERE typeof(high_volatility) <> 'integer' OR high_volatility NOT IN (0, 1);
```

   - **判定**：
     - P-4a 大於 0 → STOP-3，處置依 RC-52 第二段與 RC-22；
     - P-4c 大於 0 → STOP-4，回報 TA。
     - P-4c 為 0 時，`<> 0` 與原定義 `= 1` 等價（`store.py:124`：INTEGER NOT NULL DEFAULT 0，symbol 是主鍵，所以列數就是檔數）。
   - **N-207 的讀取要一致**：讀 `high_volatility` 時，非 0 一律判為 True，與 P-4a 一致。
   - **執行方式**：
     - P-4b 放在獨立的腳本檔，檔頭註明「輸出不得貼回」；
     - 只有 P-4a 大於 0 時才跑；
     - 與 P-4a 在同一個唯讀 session 中接連執行。
   - **交叉核對**：CEO 核對 P-4b 的列數是否等於 P-4a。不一致時，只告知 coordinator「不一致」與檔數（RC-52）。CEO 的回覆若含代號，coordinator 記錄前先遮蔽，並回報風控（RC-54 第 3 點）。
   - **交件紀錄可以記的內容**：盤點時間、各布林值與計數、P-4a 的檔數、CEO 確認收到的時間與選項。
5. **STOP-3 的處置欄改寫**：
   - 通知改用 RC-52 第二段的定稿：不列代號，以 `{P4_COUNT}` 交叉核對；
   - 「取消標記」照 RC-55 必含的五點揭露。
6. **待辦登錄 TA-TODO-RC55**（只在 CEO 選「取消標記」時觸發，現在不擬方案）：
   - 由 TA 擬高波動標記的移除方式，送風控審。內容必須包括：執行者、是否可回溯、移除後如何驗證（CEO 在本機重跑 P-4a 得 0）。
   - 不以手動修改 DB 的方式進行。
   - 擬稿時要對照 N207-C5（`high_volatility*` 只由名單 store 方法寫入）與 ADR-0043 D7。
   - 風控審過、執行完成、重新盤點確認之前，STOP-3 不解除，部署維持暫停。

## 補遺-12（補充題）：ADR-0044 修訂一 Decision 7 第 3 款對 N-207 的影響

1. **條文字面不變**：
   - N207-C3（`set_capital` 零 diff）是對 N-207 自己的 base 比較，N-210a 不論先合入或後合入都成立；
   - N207-T19（拒絕時 `set_capital` 沒有被呼叫）不受影響；
   - ADR-0043 D5「名單 × confirm-rules」等於某一個循序，仍然成立：兩邊都取寫鎖，只是 confirm 的等待點由第一句 upsert 提前到 `BEGIN IMMEDIATE`。
2. **測試的種入方式（新約束）**：
   - N-207 的測試不得對 `set_capital` 或 `set_total_deploy` 傳 `at=`；
   - T6 的 ABA 情境，以及其他需要指定 set_at 的情境，一律以直接 SQL 種入 `playbook_state`，比照 `tests/test_n172_duplicate_probe.py:135`；
   - 理由：N-210a 合入後 `at` 參數會被移除，ADR-0044 D7 第 3 款的 AST 也禁止這種參數。
3. **T9 的釐清**：「在名單交易 COMMIT 之前」完成 confirm 或 REBALANCE 的那一種交錯，另一個寫入者必須在另一條 thread 執行，等名單交易 COMMIT 後再 join。這和現行 REBALANCE 的情形相同；斷言（結果等於兩種循序之一）不變。
4. **N207-C20（新增，BLOCKING）同一次讀取的單一定義**：
   - 名稱統一為 `portfolio_and_stamp()`（ADR-0044 寫的 `portfolio_with_stamp()` 只是暫稱）。
   - 它、`portfolio_state()`、N-209b 的 `capital_record()`、N-197a 的 `_total_deploy_stamp` 共用同一個 parse helper，每一個都只呼叫一次 `_state_map()`。
   - 不論 N-207 或 N-210a 哪一個先合入，後合入的一方沿用既有方法，不得另寫一份。N-210a 若先合入，§0 的「新增 `portfolio_and_stamp()`」改讀為「沿用」。
   - 在 `evaluate_today` 中：交給 `evaluate()` 的 portfolio、交給 `engine_batches` 與 `entry_gate_open` 的 stamp，以及採用 (iii-c) 時交給 `commit_evaluation(td_basis=…)` 的 stamp，三者來自同一次 `portfolio_and_stamp()` 呼叫的回傳值（AST 同名變數，T7 擴充）。
   - ADR-0044 (iii-a) 的原始字串 set_at 讀取，不得用於閘的判定或 engine 輸入。
5. **ADR-0044 D7 第 1、2 款對 N-207 store 新增程式碼的約束**：
   - 不得出現以 `STATE_TOTAL_DEPLOY*` 為鍵的 dict 字面值，也不得以它們作為 subscript 賦值的目標，只能讀；
   - 含 `playbook_state` 的 SQL 只能出現在 `store.py`；
   - 依現行規格，N-207 本來就符合這兩點，由 T15 增列 AST 釘住。

---

### 其他部門
本次沒有參與。各自的待辦見第四段。

## 三、驗證

- **讀過的文件**：
  - 全文：
    - dev-lead 彙整稿與交件說明；
    - 風控 RC-36～47、RC-48～51、RC-52～55 三份；
    - TA ADR-0044 修訂一；
    - PM v3.4 交件。
  - 部分：
    - PRD v3.4（:1-20、:266-295，以及 grep FR-5、AC-04、AC-57、AC-84、AC-90～94）；
    - TA 補三（:1-120、:240-320）；
    - 補遺-4（grep 執行者）；
    - 修一 乙、丙（:596-625）；
    - 補二（grep T-20）；
    - 原規格（grep T6、T11、T13、T19、N-198）；
    - ADR-0043 D4～D6（:215-275）；
    - N-209 PRD（grep 停用、RC-34）；
    - N-209 字面草稿（:50-99）；
    - data-engineer 形狀規則（grep K）。
- **讀過的程式**（唯讀）：
  - `store.py:120-125`：`high_volatility INTEGER NOT NULL DEFAULT 0`，symbol 是主鍵；
  - grep `app/` 的 `high_volatility`：現行 store 對這一欄沒有任何讀寫；
  - `scripts/validate_agents.py:52-65`：`READONLY_ALLOWED_BASH`；
  - `.claude/agents/*.md` 的 tools：確認 devops-sre、dev-lead 有 Bash，TA、qa-reviewer、風控沒有。
- **沒有查證的部分**：
  - 我沒有 Bash，以上全部是讀碼推論。`git cat-file -e` 遇到不存在的路徑時是 exit 128、ERE `\b` 不可攜，這兩點都是依 git 文件推論，由控制組與 R6 在執行紀錄中實證。
  - N-209、N-209b、N-210 都還沒合入，所以 N9-07 的實際位置、它是不是單一定義、status 的實際名稱都不明。補遺-5 第 3 點 (d) 與 T6 已寫好退路。
  - 補遺-11 的 P-4a～P-4c 只有讀過 schema，沒有實跑。
  - CEO 本機 DB 的狀態不明。
- **沒有讀 `.env`，沒有碰 `data/*.db`，沒有執行任何指令，也沒有改任何檔案。**

## 四、下一步

1. **dev-lead**：依補遺-8 出 N-207 實作規格 v3，把補遺-1～12 併入正文，附錄 B 增列覆蓋紀錄。
2. **risk-compliance-officer**：
   - 知悉並可刪除的〔TA 追加〕：補遺-1 第 5 點（N-209b、N-210 的回退偵測）、補遺-4 的 R0 與「控制組不符判 BLOCKING」、補遺-11 的 P-4c；
   - 確認補遺-3：dev-lead 執行個體不算非實作者，只限 devops-sre；
   - 確認補遺-7 的拒絕結構與判定順序；
   - 確認 ADR-0044 修訂一（AC-84 依補遺-2 第 1 點，以這份確認為前提）。
3. **coordinator**：
   - 依補遺-1 更正派工紀錄的前置清單；
   - 在派工紀錄指定 devops-sre 為執行者；
   - N-209 合入時，錨點登錄加記「N9-07 位置」；
   - 送 CEO 裁示補遺-2 第 1 點的三件事；
   - 依補遺-11 請 CEO 在本機盤點。
4. **data-engineer 與 devops-sre**：依補遺-11 第 3、4 點，把 P-1～P-5 的 SQL 改成計數形狀，P-4b 獨立成一個腳本檔。這件事要在 P-4a 大於 0、RC-52 第二段送出之前完成。
5. **devops-sre**：在 N-207 送審的 commit 上，執行補遺-4 表中的全部指令與 M5，輸出原樣記錄。
6. **product-manager**：
   - AC-73 依 RC-54 第 4 點加註；
   - AC-91 寫進 RC-50 的觸發定義與補遺-7 的判定順序；
   - 決定 RC-48 的 suggested（輪內已經沒有 planned 時要不要顯示 W-24）。
7. **tech-writer**：ADR-0043 D7 第 6 點改用「適用」（RC-44、RC-22）。
8. **CEO**：
   - 裁示 ADR-0044：修正或接受殘留、(iii-c) 採不採、N-210 與 N-207 部署的先後；
   - 在本機執行 §9 盤點，只回時間、布林值與計數。

相關檔案：
- /home/user/AICompany/work/reviews/2026-11-10-N207實作規格v2彙整-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-10-N207實作規格v2彙整交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-10-ADR0044修訂一與RC42C1W25f確認-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-10-交付B裁示ADR0044審查與字面定稿-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-補擬四句裁定-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-N207部署通知定稿-風控.md
- /home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py（:120-125）
- /home/user/AICompany/scripts/validate_agents.py（:52-65）
