# README 定稿套用交件（docs/readme-backup-restore）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
16 處已逐字套用並 push，分支 `docs/readme-backup-restore`，一個 commit，只改 `apps/stock-desk/README.md`。行數 332 → 361（淨增 29），與風控預期一致。未開 PR、未合併、未 amend／rebase／force。

- base（`origin/product/stock-desk` 最新 head）：`958ee430e388ae37b05e1e52304b5c154275059a`
- 分支 head：`9f20ad2e476240f0ea225b4bc0b299595748cb4a`
- worktree 路徑：`/home/user/AICompany/.claude/worktrees/agent-a8f22f2289ce5e462`（停在該 head）
- 套用／驗證腳本（未 commit）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/apply.py`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/verify.py`

## 各部門回報（devops-sre）
**16 處逐處結果**：定稿區塊與套用後 README 對應片段逐字比較，全部 `==` True。
定稿區塊由腳本直接從風控檔擷取，不是我手打。

| 處 | base 行 | 套用後行 | 行數增減 |
|---|---|---|---|
| 1 | 14–15 | 14–15 | 0 |
| 2 | 19 | 19–21 | +2 |
| 3 | 21 | 23–24 | +1 |
| 3b | 25 | 28 | 0 |
| 4（刪除） | 26 | 無 | −1 |
| 5 | 34–37 | 36–41 | +2 |
| 6 | 51–53 | 55–60 | +3 |
| 7 | 90–100 | 97–123 | +16 |
| 8 | 102–107 | 125–128 | −2 |
| 9 | 109 | 130 | 0 |
| 10 | 129–131 | 150–154 | +2 |
| 11 | 135–136 | 158–161 | +2 |
| 12 | 148 | 173–175 | +2 |
| 13 | 261–263 | 288–290 | 0 |
| 14 | 280 | 307 | 0 |
| 15 | 292–294 | 319–323 | +2 |

合計 +29。

**我做的判斷**
- **縮排**：轉存檔的區塊與預期完全一致，沒有歧義。第 2 處後兩行以兩個空白開頭，第 5 處每行 `> `，第 7 處續行三個空白，第 13 處無前導空白。我沒有做任何縮排調整。
- **第 3b 處與第 15 處**：我先 assert「原」區塊與 README 第 25 行、第 292～294 行完全相同才替換，都通過。
- **其他 1～14 處的「原」**：我是以行號範圍取代，沒有逐處拿草稿的「原」比對。每處都用逐段比對確認 README 的其餘行零差異，另外 assert 了第 26 行開頭文字。若 qa 要再核，請看 diff hunk。
- **第 15 處**：新區塊結尾的空行屬於定稿本身，結果是 ``` 後接空行、粗體句、原空行，再接「- 寫入三檔標的…」。

## 驗證
1. `git diff 958ee43 --stat`：只有 `apps/stock-desk/README.md`，51 insertions(+)、22 deletions(-)。`--numstat` 為 `51	22	apps/stock-desk/README.md`。`git status` 乾淨，只有這一個檔。
2. 行數：套用前 `len(split('\n'))` = 332，以換行結尾；套用後 361，以換行結尾；淨增 29。
3. 16 處逐字比較：全部 `==`，見上表。
4. 其他行零差異：腳本依序走過 16 個範圍，範圍之間的每一段與 base 相同，尾段也相同。
5. Grep（針對新 README）：
   - `local-run`、`attest`、`必要時由您決定`：零命中。
   - `系統環境優先`：只有第 307 行，原文為「…系統環境優先〔此行為只在 Linux(uv 0.11.32)實測過,未在 Windows 實測〕。」
   - `cp apps/stock-desk/.env.example`：只有第 24 行（工程人員那一句）。
   - `主機部署手冊`、`手冊`：零命中，README 沒有把 CEO 導向手冊的節。
6. 換行字元：base 與套用後都是純 LF，沒有 CR。沒有 BOM。新增行無行尾空白。純 UTF-8。
7. 測試與 CI：
   - 後端：`backend/tests` 沒有測試讀取 `apps/stock-desk/README.md`。命中只有 `tests/fixtures/README.md` 的字樣，是另一個檔。
   - 前端：有兩個 vitest 測試讀取這份 README。
     - `riskRemediationWording.test.ts:132`：要求 README 含 `> ${SITE_FOOTER_DISCLAIMER}`。免責引言在第 6 行，不在 16 處範圍內，diff 沒有動它，不受影響。
     - `inventoryPage.test.ts:570`：要求 README 含 `` `/positions` `` 且不含「匯入 / 新增部位」。base 的 README 就沒有 `` `/positions` ``（我用 `git show` 對 base 計數為 0），所以這個斷言在 base 就不成立，與本次改動無關。我的 diff 也沒有動到含 `positions` 的行。
   - 未執行：`frontend/` 沒有 `node_modules`，我沒有安裝依賴也沒有跑 vitest，以上是靜態比對。
   - `.github/` 下沒有任何 workflow 提到 README。

## 下一步
- 沒有查證的事：
  - `.env.example` 有沒有 `STOCK_DESK_DB_PATH`：未查證（權限拒讀），沒有嘗試任何繞過途徑，由 coordinator 另外處理。
  - 前端兩個 README 測試沒有實跑。`inventoryPage` 那個斷言在 base 已經不成立，建議 coordinator 另外查它在 CI 是否本來就紅或另有處理；這不在本 PR 範圍，我沒有動它。
  - 正式登記是否完成：未查證。依 RC-459，本分支在登記完成前不應合併。
- 交 qa-reviewer 逐字核對（RC-459 的 1～5 點）。
- 合併要等正式登記完成後，由 coordinator 安排；PR 說明建議寫 16 處清單、第 15 處以第 292 行為錨點、不動手冊／`.bat`／`backend/README.md`、合併時點限制，以及上列未查證項目。
- 回滾：該分支尚未合併，捨棄分支即可（`git push origin --delete docs/readme-backup-restore`，需 coordinator 同意）。合併後則 revert 該單一 commit `9f20ad2`。
