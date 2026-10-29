# N-156 前端 qa 退修交件

- 審查者：frontend-engineer
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## qa 審查退修交件（NB-1、NB-3、NB-4、NB-5、NB-7）

**commit：`f38b2d4`**（`fix: N-156 前端審查退修，覆寫勾選不跨次殘留與回落徽章不受矛盾 payload 影響（ADR-0032 DL-6）`）。已 push 到 `origin/fix/stock-desk-settings-fallback`（`47388c0..f38b2d4`）。

- push 前 fetch 過，遠端 HEAD 仍是 `47388c0`，dev-lead 沒有新 commit，所以沒有 merge。
- commit 限定路徑 `apps/stock-desk/frontend/app`。
- trailer 實際填的是 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`，以及 `Claude-Session: https://claude.ai/code/session_01WfgD8MUGHNitQHywjXPu4E`。這是本執行環境的歸屬規定。
- 紅線照舊：沒動後端，沒讀 `.env`，沒碰 `data/*.db`，沒安裝任何東西，沒碰 `product/stock-desk`。

**備註**：你提到的審查全文 `work/reviews/2026-10-29-N156設定段回落前端-審查-qa-reviewer.md`，我 grep 時找不到 NB 編號的內容，所以全程照你訊息裡的描述做，沒有對照原文。

### 改動落點（路徑相對 `apps/stock-desk/frontend/app/`）
- **NB-1（required）**，`settings/SettingsForm.tsx`
  - `closeOverwriteFlow`（約 :356）現在一併 `setOverwriteChecked(new Set())`。
  - 取消、放寬取消、解析錯誤、寫入成功、寫入失敗（含 409）都走這個函式。
  - 寫入成功原本單獨清勾選的那段刪掉，改成 `onSuccess: closeOverwriteFlow`。
  - `confirmOverwritePanel` 會先關面板，但刻意不清勾選，因為這次要送出的答案還在使用，這次嘗試是靠 `onSuccess` 或 `onError` 收尾的。
- **NB-3**，`settings/NetWorthSection.tsx` 徽章
  - `fellBack` 時配色強制用 `fallback`（琥珀色）。
  - 略過「（已 N 天未更新）」後綴。
- **NB-4**，`position/[symbol]/LimitsCheckList.tsx`：fragment 內的縮排改成與檔案其餘部分一致。
- **NB-7**，`components/SettingsFallbackNoticeLine.tsx`：`text === ""` 與 `null` 一樣回傳 null。
- **NB-5**：只補測試，`queries.ts` 沒有再改。

### 測試名稱
**`settings/__tests__/settingsFallback.test.ts`（45 → 52 個）**
- 「取消或出錯之後，下一次開啟面板時勾選集合是空的（預設不勾選）」，3 個：
  - `closeOverwriteFlow 同時關面板、清確認狀態、清空勾選`
  - `面板只經 closeOverwriteFlow 關閉：取消、放寬取消、解析錯誤、寫入成功、寫入失敗（含 409）全走它`
  - `勾選集合只有兩處會被設值：使用者勾選，與 closeOverwriteFlow 的清空`
  - 沒有 jsdom，所以是原始碼掃描。
- 「NetWorthSection — 回落時徽章配色與後綴不受矛盾 payload 影響」，2 個：
  - `徽章只寫「使用預設值」，沒有「（已 N 天未更新）」`
  - `配色是回落的琥珀色，不是 expired 的玫瑰色（也不是 fresh 的綠色）`
  - 矛盾案例是 `settings_fallback` 說 `net_worth` 回落，但 payload 帶著 `expired`、`age_days: 58`、金額 5,000,000。
- 「useUpdateSettings 成功後重新抓取依設定判定的畫面」，2 個：
  - `使 advice、kelly-disclosures 失效…`
  - `原有的 portfolio-limits、portfolio-summary 失效仍在`

**`lib/__tests__/settingsFallbackNotice.test.ts`（20 → 21 個）**
- `空字串與 null 一樣不渲染，不會留下空框（NB-7）`。

### CI 原文數字
- `npx tsc --noEmit`：無輸出，exit 0。
- `npx vitest run`：`Test Files  97 passed (97)`、`Tests  2658 passed (2658)`。上一輪是 2650。
- `npx next build`：`✓ Compiled successfully in 644ms`、`✓ Generating static pages using 3 workers (8/8) in 375ms`。
- 後端沒動，沒跑。

### 照指示先不動
- NB-2：部分儲存句用綠框還是琥珀框。
- `NetWorthSection` 成功訊息要並列還是取代。
- NB-6：Kelly 揭露的語意。
- 這三項等風控裁示。
