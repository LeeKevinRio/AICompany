# 補充六附記四落檔核對

- 審查者：qa-reviewer
- 日期：2026-11-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**PASS_WITH_NOTES**，沒有 BLOCKING_ISSUES。ADR-0030 補充六附記四的落檔，三點核對全部通過。我也確認了 `--stat` 的另外兩檔都在 `work/` 底下，且沒有 `app/`、frontend 或 scripts 的變動。有一項限制，見註記。

## 各部門回報（qa-reviewer，單家審查，Codex 依決策 #58 不可用）

**核對 1：原第 1～976 行沒有改動，通過**
- diff 只有兩個 hunk，沒有任何 `-` 行（檔頭的 `---` 標頭除外）。
- 第一個 hunk 是 `@@ -18,6 +18,7 @@`，第 20 行之後新增 1 行（補充紀錄行）。
- 第二個 hunk 是 `@@ -974,3 +975,74 @@`，第 976 行之後新增 71 行（74 減 3 行 context）。這 71 行是 1 個空行加 70 行正文，與 TA 定稿第 95～164 行的行數一致。

**核對 2：逐字比對，通過**
- Q-1～Q-8 與記號段（G、M、D）與 RC-721（風控檔第 45～74 行）逐字相同。
- 適用範圍與 RC-720（風控檔第 41 行）逐字相同。
- 過渡規則兩條與 RC-722（風控檔第 79～80 行）逐字相同。
- 正文整體（Context、Decision、過渡規則、Consequences、回滾，以及「Q-4、Q-7 中的『我』」那一行）與 TA 定稿第二節的第 95～164 行逐字相同。
- 檔頭補充紀錄行與 TA 定稿第 89 行逐字相同。
- 這是我逐段肉眼對讀的結果，沒有用機械逐字元比對。

**核對 3：三句標示，通過**
- 檔頭紀錄行含「窄幅寬於字面」「經風控審查（RC-720～RC-723）」「CEO 可推翻」。
- 「性質」行也含這三句。

**`--stat` 其他檔**
- 共 3 檔，共 121 行新增，沒有刪除。
- ADR-0030 新增 72 行，等於 1 加 71。
- 另一檔是「…蹤清單.md」，新增 1 行。
- 另一檔是「…落檔-tech-writer.md」，新增 48 行。
- 這兩檔的路徑在 `--stat` 裡被截斷。我用 Glob 比對檔名，只對得到 `work/dispatch/2026-10-17-後續追蹤清單.md` 和 `work/reviews/2026-11-25-補充六附記四落檔-tech-writer.md`，都在 `work/` 底下。
- stat 列的檔案裡沒有 `app/`、frontend 或 scripts。

## 驗證
- **註記（限制）**：`--stat` 的路徑被截斷，所以「另兩檔在 `work/` 底下」是靠檔名推定，不是直接由 stat 看到完整路徑。我也沒有讀那 48 行與 1 行的內容。要完全確認，可在 stat 之外另跑完整路徑的 name-only 檢查。
- 唯讀權限判準常數：兩道機械檢查是 `scripts/validate_agents.py` 路徑，以及 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH` 的 diff。這次權限限定只能跑兩條指令，這兩道檢查沒有跑。可以確定的是，`--stat` 沒有列出 `scripts/validate_agents.py`，ADR diff 也沒有出現這兩個常數。判定為未觸及，沒有 `READONLY_AGENTS` 成員異動。
- 我沒有跑 `/review`，因為 Codex 不可用，依任務指示處理。

**跑過的指令（只有這兩條）**
1. `git diff --stat 1563b91f 547f8c39`
2. `git diff 1563b91f 547f8c39 -- docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`

**讀過的檔案**
- `/home/user/AICompany/work/reviews/2026-11-25-補充六附記四讀法與高優先修正排程CEO題RC720至RC729-風控.md`（前 130 行）
- `/home/user/AICompany/work/reviews/2026-11-25-RC728確認與補充六附記四定稿-tech-architect.md`（全文）
- Glob 只用來列檔名，沒有讀內容：`work/**/*落檔*tech-writer.md`、`**/*蹤清單.md`。第二個 Glob 的結果列出了 `.claude/worktrees/` 下的兩個路徑，我沒有開啟。

## 下一步
- coordinator 可以放行落檔，並解除 RC-722 的暫緩：前端合併與 `merge origin/main` 的暫緩，改成跑 RC-721 全套。
- 若要消除上面那項註記，請 coordinator 或 devops-sre 補一次完整路徑的 name-only 清單。
- CG-2 PR 時，qa 照 Q-1～Q-8 逐條核對。
