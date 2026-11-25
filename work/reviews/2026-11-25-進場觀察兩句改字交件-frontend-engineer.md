# 進場觀察兩句改字交件（frontend-engineer）

## 本次結論
依 RC-700～RC-705 逐字改完兩句，測試已鎖定，已 push 到 fix/entry-observation-wording（未 push product、未開 PR）。
- base：origin/product/stock-desk = 6d021178a9751d4b1b43412a9cbe882d7bbe81fe
- head：18f566364f2f7747c17b060b6308713e849cb5a5
- numstat：test 7/1、entryObservationWording.ts 5/2，共兩檔
- 注意：worktree 內沒有風控定稿檔，我是照任務單的逐字定稿施作，沒有另外對照原檔。

## 各部門回報
- entryObservationWording.ts：第一句、第二句已改，常數名未變，位置仍在 buildDataAsOfLine 之後；兩處加英文註解註明 RC-700～RC-705。
- componentWordingScan.test.ts：原 toBe 改新句；新增 buildEntryBasisRange(null)/(252).qualifier 逐字 toBe；ENTRY_NO_DATA_STATEMENT not.toContain("不足")；:2822 旁加 expect(fnEnd).toBeGreaterThan(fnStart)。

## 驗證
紅燈證據（暫時改回舊字，未 commit，已還原並以 diff 確認）：
- 指令：用 sed 把新字改回舊字後，在 apps/stock-desk/frontend 跑 `npx vitest run app/lib/__tests__/componentWordingScan.test.ts`
- 只回舊第一句：`AssertionError: expected '目前資料不足，六條條件均無法判定。' to be '目前六條條件均無法判定。'`，Tests 1 failed | 652 passed
- 只回舊第二句：`Expected: "沒有可用日線、未滿 60 根或區間最高最低價相同時，本條無法判定。"` `Received: "未滿 60 根日線或區間最高最低價相同時，本條無法判定。"`，Tests 1 failed | 652 passed
- 兩句與 not.toContain("不足") 在同一個 it 內，先失敗的斷言會擋住後面的，所以兩句分開各回退一次驗證。

依 .github/workflows/stock-desk.yml 的 frontend job（node 在本機版本，CI 為 22）：
- npm ci：成功
- npm run typecheck（tsc --noEmit）：無錯誤輸出
- npm test（全量 vitest）：117 files、3110 tests 全過
- npm run build（next build）：成功，路由表正常輸出

## 下一步
交 qa-reviewer 審查（含 Codex 第二意見）。第二句的 qualifier 是面向使用者字面，風控已定稿；審查時請對照 RC 原檔逐字核一次。
