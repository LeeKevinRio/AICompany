# RC-695 medium 修正重審

- 審查者：qa-reviewer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 結論
**PASS_WITH_NOTES**（無 BLOCKING_ISSUES，BLOCKING_ISSUES=false）。單家審查，Codex 依決策 #58 不可用。

## 一、四項確認
1. **medium 已修好。** `technicalCollapsed` 現在是 `bars.isSuccess && bars.data.status === "ok" && evaluateDailyBarsUsability(...) === "unusable"`。我對照 head 檔案，三處渲染條件都一致：
   - 摘要區（原 :391）在 `page.tsx:393`，是 `bars.isSuccess && status === "ok"`，裡面用 `technicalCollapsed` 切換。
   - 原 :441 在 `:443`，是 `bars.isSuccess`。
   - 原 :474 在 `:476`，是 `bars.isSuccess && ok && !technicalCollapsed`。
   - 指標卡在 `:469` 和 `:470`，用 `!technicalCollapsed` 判斷。
   - 現在 refetch 失敗但留著舊的壞資料時，`technicalCollapsed` 為 false。`:389` 顯示錯誤面板，指標卡照舊顯示，也不會出現半收起的狀態。
2. **新測試可以接受。**
   - 它用 `setState({status:"error"})` 模擬「有舊資料加 isError」，這個情境成立。
   - 它斷言：不出現收起句、不出現 `CHART_LABEL`、指標卡仍在、出現「無法載入日K線」。
   - fixture 有 100 根（test 第 47 行），所以斷言「共 100 根日線」不出現不是空轉。`:476` 的 `isSuccess` 條件讓這一行在 isError 時本來就不會顯示，實作者的說明正確。
   - 回歸抓得到：若拿掉 `isSuccess`，`technicalCollapsed` 會變 true，指標卡消失，「指標卡仍在」的斷言就會失敗。
   - 小備註（low）：「共 N 根」這條斷言對這次回歸沒有鑑別力。它只是在鎖定「isError 時不顯示」這個既有行為，不影響可接受性。
3. **字面變動與範圍。** 只動 2 個檔案，共 +20/−3。使用者看得到的字面沒有新增，只改了條件判斷。註解是英文，符合規範。測試檔裡的字串都在測試內。沒有超出範圍。
4. **上一輪結論仍成立。** 上輪那項 medium 已消除，其餘結論不變。這個 commit 只收窄了 `technicalCollapsed` 的觸發條件，不影響 isSuccess 路徑，所以沒有新增問題。

## 唯讀權限判準常數
未觸及。本 commit 只動 `page.tsx` 和一個測試檔，沒有 `scripts/validate_agents.py`，diff 中也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。我是讀完整份 diff 後目視確認，沒有另跑那兩道 grep（權限只允許兩條 git diff）。

## 未獨立重跑
typecheck、vitest、build 都未獨立重跑。

## 我跑過的指令
- `git diff --stat fba26f8f... 1dd244c3...`
- `git diff fba26f8f... 1dd244c3...`
- 另外用 Read 和 Grep 讀了 head worktree 的 `page.tsx` 和測試檔：`/home/user/AICompany/.claude/worktrees/agent-ac1b2db2a6f4826f8/apps/stock-desk/frontend/app/position/[symbol]/page.tsx`，以及同 worktree 下 `app/lib/__tests__/technicalSectionUnusableBars.test.ts`。
