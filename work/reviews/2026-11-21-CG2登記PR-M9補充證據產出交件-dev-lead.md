# RC-496 補充核對證據產出交件

- 審查者：dev-lead
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

RC-496 證據檔已經產出：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/rc496_evidence_cc9e302.txt`。(a)～(e) 都照 11-17 證據檔的格式：先列指令，再列原始輸出；路徑用 `core.quotepath=false`，沒有八進位轉義。(b)(c)(d) 都符合預期。repo 沒有任何改動，也沒有 commit：worktree 是乾淨的，HEAD 仍是 `cc9e30239ad8acbb76706d2bef71b2379b4fac86`。

## 各部門回報（dev-lead）

**(a)** 有變動的只有先前交件那 6 個檔，全部是 `M`。

**(b)** 符合預期。六條路徑的 diff 沒有輸出，`| wc -c` 是 0。我另外用 `git ls-files` 確認這六條路徑在新 head 都存在，所以不是因為路徑不存在才沒有差異。

**(c)** 符合預期，兩份文件都和 11-17 的值相同：

| 文件 | blob id | sha256 |
|---|---|---|
| 事先宣告 v0.32 | `d1e4d06a…` | `7c45b0ba…b406e` |
| C-8 紀錄 | `e664f147…` | `c942642c…a54f` |

`ls-files --eol` 兩份都是 `i/lf w/lf attr/text eol=lf`。

**(d)** 符合預期，用的是 Python 3.12.3。h3、h5 的結果都是：
```
hits 0 rules_strings 159 definition_strings 12 phrases 10
```
說明行和 11-17 逐字相同。
- 做法：用 `git archive` 把新 head 的 backend 解到 scratchpad，在那裡跑 `uv sync --frozen --python 3.12 --no-dev`，再用 `-I -B` 執行掃描腳本。
- 掃描腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/rc496_tools/phrase_scan.py`，全文已附在證據檔裡。
- 腳本會斷言 `app` 確實是從解出來的那份載入。沒有連任何資料庫。

**(e)** `cg2_register.py` 的 diff 全文已附。改動共四處：
- `ENV_KEY_PATTERN` 和它上方的註解；
- `app_tree_id`；
- `review_refs` 上方的註解；
- `review_refs` 末尾加兩條。

`frozen_files`、`definition`、`rules`、`_TELL` 和各 STOP 句都沒有變。RC-496 (e) 原本寫「review_refs 不變」，依 tech-architect 補充裁示，應改讀成「只在最後加兩條」。

**檔尾的說明行：我同意你的理解。**
- 執行期的 `check_review_refs` 查的是執行一鍵檔那個 checkout 的 `HEAD`。R-1 又要求 HEAD 必須在 `origin/product/stock-desk` 上，所以實際執行時，HEAD 就是 CG-2 合併進 product 之後的 commit。
- 我查證過：product（fetch 當時是 `d56cd7d1`）上確實有那兩份 11-17 的 M-9 紀錄。
- 因此要**更正我前一份交件**：coordinator 不需要 commit 4 份，只要在合併前把 11-21 那兩份 commit 到 product。
- 在還沒合併的 CG-2 分支上，`test_the_review_refs_all_exist_at_head` 會一直列出 4 條缺漏。原因是分支本身不含這些紀錄，不是缺陷。這兩點都寫進了證據檔末尾。

## 驗證

- 證據檔由 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/rc496_tools/make_evidence.py` 產生。它只執行唯讀的 git 指令，執行前會斷言 HEAD 等於 `cc9e302` 而且工作樹是乾淨的。
- 沒有查證：
  - 遠端 `product/stock-desk` 在我這次工作期間前進了好幾次（`5d7056ac` → `0f490885` → `d56cd7d1`），都不是我推的。
  - CG-2 合併進 product 時會不會有衝突，我沒有試合併。

## 下一步

- **coordinator**：把證據檔轉給風控做 RC-496 補充核對。(f) 的確認句由 qa 提供。
- **qa-reviewer**：審查 `cc9e302`。
