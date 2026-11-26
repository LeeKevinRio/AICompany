# RC-695 qa medium 修正交件

- 審查者：frontend-engineer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
qa 的 medium 已修，另開一個新 commit 在 `fix/technical-section-unusable-bars` 上，沒有 amend、rebase、push。

- 新 commit SHA：`1dd244c3`，其上一個 commit 是 `fba26f8f`。
- `page.tsx:144-147`：`technicalCollapsed` 的第一個條件由 `bars.data !== undefined` 改成 `bars.isSuccess`，和 `:391`、`:441`、`:474` 的渲染條件一致。
- 同處補了一段英文註解，說明為什麼要用 `isSuccess`。

## 各部門回報（frontend-engineer）
`git diff --stat fba26f8f HEAD`
```
 .../lib/__tests__/technicalSectionUnusableBars.test.ts | 17 ++++++++++++++++-
 apps/stock-desk/frontend/app/position/[symbol]/page.tsx |  6 ++++--
 2 files changed, 20 insertions(+), 3 deletions(-)
```
`git diff --numstat fba26f8f HEAD`
```
16	1	apps/stock-desk/frontend/app/lib/__tests__/technicalSectionUnusableBars.test.ts
4	2	apps/stock-desk/frontend/app/position/[symbol]/page.tsx
```
檔案範圍就是這兩個檔，backend 零差異。

**新測試**
- 測試名稱：「bars query in isError while keeping stale BAD data…」（在 `technicalSectionUnusableBars.test.ts`）。
- 做法：把壞值 data 塞進快取，再把該 query 的狀態設成 `error`。React Query 於是回報 `isError`，同時保留舊的壞值 data。
- 斷言：
  - 定稿句不出現。
  - 圖表不出現。
  - `<details>` 裡的指標卡照舊顯示。
  - 主視圖是「無法載入日K線」的錯誤面板。

## 驗證
- `npm run typecheck`：無錯誤。
- 全量 vitest：120 個檔案、3192 個測試全部通過，比上一版多的 1 個就是新測試。
- `npm run build`：成功。
- 改回舊條件（`bars.data !== undefined`）的實測：新測試變紅，其餘 41 個仍綠。改回 `bars.isSuccess` 後 42 個全綠，上面三項是在還原後的最終版重跑的。

## 下一步
送 qa-reviewer 複審，之後 qa-e2e 與 risk-gate。

**偏離**
- 你說「根數行照舊顯示」。實際上「共 N 根日線」那一行本來就由 `bars.isSuccess` 控制，所以 `isError` 狀態下它原本就不會顯示。
- 我的測試因此斷言這一行不出現，也就是和修改前的現況一致，而不是斷言它出現。
- 指標卡由 signals 的狀態控制，所以照舊顯示，測試有斷言這點。
- 沒有被拒的動作。
