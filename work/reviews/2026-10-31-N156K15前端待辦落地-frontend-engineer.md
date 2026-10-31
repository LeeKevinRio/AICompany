# N-156 K-15 前端待辦落地

- 審查者：frontend-engineer
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# 回報：N-156 K-15 前端待辦落地

## 本次結論
裁示列給前端的 1 項 required 與 2 項 suggested 都做完了。前端 `npm run typecheck`、`npm test`、`npm run build` 三項全綠，已 push 到 `origin fix/stock-desk-settings-fallback`。origin HEAD 由 `b1e639d` 變為 `2ee5f8d`。

- **required：琥珀框**。`partial_save_notice` 不為 null 時，改用琥珀框直接渲染後端字串。
- **suggested：死分支**。已移除，揭露句只剩 effective_cap 數值旁一處。
- **suggested：改字**。「S1/S1'」只出現在 JSDoc 註解，不是使用者可見字面，所以照改，沒有需要回報給你的字面問題。

## 各部門回報
**frontend-engineer**

開工前 `git fetch` 確認 origin HEAD 為 `b1e639d`。作業期間只有我在這條分支 commit。

| commit | 內容 |
|---|---|
| `90ecd4d` | `fix: N-156 設定頁部分儲存提示改用琥珀框並逐字渲染後端句（K-15 裁示）` |
| `cf27fc2` | `refactor: N-156 移除 Kelly 揭露面板 cap 為 None 時的獨立揭露句分支（K-15 裁示二-5）` |
| `2ee5f8d` | `docs: LimitsCheckList 註解的「S1/S1'」改為「S1」（K-15 裁示）` |

三個 commit 都限定路徑，結尾兩行 trailer 照你給的內容。

路徑相對於 `/home/user/AICompany/apps/stock-desk/frontend/app/`，行號為改後行號：

1. **琥珀框（`90ecd4d`）**
   - `settings/SettingsForm.tsx:647-660`：拆成兩個分支。
     - null 時：綠框「設定已儲存。」，維持原樣。
     - 不為 null 時（:656-660）：`<p role="status" className="mt-3 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-3 text-sm text-amber-200">{mutation.data.partial_save_notice}</p>`。
     - 邊框寬、圓角、padding 與 `NetWorthSection.tsx:239-245` 的琥珀框一致，只多一個 `mt-3`，這與同頁其他提示框的間距一致。
     - 前端沒有任何組句或變體判斷，直接渲染後端字串。
   - `settings/__tests__/settingsFallback.test.ts:515-546`：
     - 用 `it.each` 帶兩句後端真句，逐字寫在測試裡。
       - 原句：「設定已儲存。風險預算、警示排程沒有寫入，仍使用預設值。」
       - 新句：「沒有儲存任何變更：風險預算、費率、警示排程沒有寫入，仍使用預設值。」
     - 兩句都斷言 `role=status` 文字與後端字串完全相等，且 class 含 `border-amber-800`、`bg-amber-950/40`、`text-sm`、`text-amber-200`，不含綠框 class。新句另斷言頁面沒有「設定已儲存。」。
     - 擴充既有的 null 測試（:535 起）：只有綠框「設定已儲存。」、綠框 class 齊全、沒有 `amber-950/40`。
   - 這個測試檔原本通篇用 `SENTINEL-*` 哨兵字串，只在這個案例改用真句。這是你要求的「逐字渲染」所需，真句與後端 `fallback_wording.py:210`、`:215` 一致。
2. **死分支（`cf27fc2`）**
   - 行號內容確認過再刪。`settings/KellyDisclosuresPanel.tsx` 原 225-229 是 `(f_star_interval === null || effective_cap === null) && <SettingsFallbackNoticeLine .../>`，就是那個獨立分支，已刪除。
   - 原 :213-219 的註解補一句說明：揭露句只放在數值旁，後端契約測試是 `test_the_value_and_its_line_never_appear_apart`，所以沒有獨立分支。
   - `lib/__tests__/settingsFallbackNotice.test.ts:419-425`：原測試「數值區塊不顯示時，揭露句仍然獨立出現」已改寫。新測試用 `kellyView(null, false)`，斷言數值區塊不顯示時，不渲染區塊、揭露句與琥珀框。
   - 這個移除有一個行為後果。若日後後端違反契約，送出「cap 為 None 但揭露句存在」，前端會吞掉該句。這是裁示二-5 的取捨，靠後端契約測試守門。
3. **改字（`2ee5f8d`）**：`position/[symbol]/LimitsCheckList.tsx:28` 的 JSDoc，「(#2', S1/S1', I-2)」改為「(#2', S1, I-2)」。
   - 此外還有兩處測試標題含「S1/S1'」：`lib/__tests__/cap1Notices.test.ts:104`、`:143`。裁示只點名 LimitsCheckList，我沒動。要統一的話告訴我。

NetWorthSection 維持並列，沒改（二-3）。

## 驗證
在 detached worktree、`cp -al` 硬連結的 `node_modules` 下跑，沒有執行任何安裝。

- `npm run typecheck`：`tsc --noEmit`，exit 0。
- `npm test`：`Test Files  97 passed (97)`、`Tests  2659 passed (2659)`。前一輪是 2658，淨增 1：琥珀框新增 2 個案例（`it.each`），原本的 partial 測試與 Kelly 獨立分支測試各被改寫。
- `npm run build`：`✓ Compiled successfully in 14.1s`、`✓ Generating static pages using 3 workers (8/8)`，exit 0。
- 後端：沒有改動，不需要跑後端 CI。

**ui-delivery-checklist 自檢**
- 琥珀框與 NetWorthSection 既有的琥珀框用同一組 class，那組配色已被風控核可，沒有新增色值。
- 揭露句仍與主結論同區塊常駐，字級沒有降低。
- 沒有數字、幣別或時間戳的新增。
- 沒有硬編碼假資料，新句與原句都來自後端字面。
- 375px 版面：只有 `<p>` 換 class，沒有改版面結構，我沒有實機量測，留給 qa-e2e。

紅線：沒讀 `.env`，沒碰 `data/*.db`，沒寫入祕密，沒有 merge 或 push `product/stock-desk`，沒有 force push。push 用 `timeout 120`。

## 下一步
1. **qa-reviewer**：逐字比對新句與原句的琥珀框。
   - 檢查 `SettingsForm.tsx:647-660`。
   - 確認 `KellyDisclosuresPanel.tsx` 移除後沒有其他地方依賴獨立分支。
   - 注意 `origin` 的 `fix/stock-desk-settings-fallback` 已是 `2ee5f8d`。
2. **qa-e2e**：在 375 與 1280 兩種寬度實機驗收。
   - 部分儲存的琥珀框。
   - 三個表單段都回落、全不勾就儲存時，出現「沒有儲存任何變更：…」。
3. **你需決定**：是否一併把 `cap1Notices.test.ts:104`、`:143` 的測試標題「S1/S1'」改為「S1」。
4. **環境提醒**：主 repo 本地分支 `fix/stock-desk-settings-fallback` 仍停在 `b1e639d`，另有兩個舊 agent worktree 檢出了這個分支。因為同一分支不能同時被兩個 worktree 檢出，我用 detached worktree，並以 `git push origin HEAD:refs/heads/fix/stock-desk-settings-fallback` 推送。下一位要在本地工作的人，請先 fetch 並更新該分支。我的工作樹與硬連結的 `node_modules` 已移除。"}
