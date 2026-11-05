# N-168 前端停止點：視覺規範缺口

- 審查者：frontend-engineer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
停在規範缺口，尚未動任何程式，沒有 commit 也沒有 push。原因是 `work/art/` 與 `work/dispatch/` 都沒有 N-168 或「出清前買進」的視覺規範。
- `work/art/` 只有兩份：`2026-10-29-出清後回饋畫面-視覺規範.md` 和 `2026-11-04-待執行出清指令區塊-視覺規範.md`。
- 後者只涵蓋 N-171 區塊內的 `entry_before_exit_note`，其餘 surface 都沒有規定。
- `work/dispatch/` 對 `entry_before_exit` 的命中只有兩份 2026-10-17 的追蹤清單，不是視覺規範。
- 依任務指示與紅線「不自創視覺」，我退回請 art-lead 補規範，補完我再實作。

## 各部門回報
**已確認的現況（worktree head 5d6056c）**
- `apps/stock-desk/frontend/app/playbook/PendingExitBlock.tsx` 已經渲染 `entry_before_exit_note`，且含 ISO 日期 nowrap 處理。
  - 順序是 `text` → `notes` → `entry_before_exit_note`，樣式是 `<p className="mt-1 break-words text-sm text-neutral-300">`，null 不渲染。
  - 這一塊有 N-171 規範 r2 §1.3、§2 L6 可依據。
  - 但 E-26 第 3 點要求的「從 `DirectiveLine` 複製的 note」，這一塊現在只吃後端 `PendingExitRowResponse.entry_before_exit_note`，我還沒核對複製這一步是否完整。
- 以下 surface 目前沒有渲染 `entry_before_exit_note`，也沒有規範：
  - `DirectiveLedger.tsx`：帳冊列 `DirectiveRow`。它用 `splitDirectiveLine` 只取 `parts[0..2]` 和 `[4..6]`，所以 note 不能靠 `line`，必須另外渲染。
  - `ExitReceiptBanner.tsx`：出清橫幅的 `directives` 與 `pending_directives`。
  - `SettlementPanel.tsx`：`{item.line}` 兩處。我還沒確認結算資料型別有沒有這個欄位。
  - `PositionSnapshotTable.tsx`：`BatchSnapshot` 的批次列，要在 label（W-B2）後緊接 note（W-B2L）。
  - S2 列（W-B2LS、W-B2LSr、W-B2LSf）：約 310 字長句。

**需要 art-lead 補的規範項目**
1. 帳冊列（`DirectiveRow`）：note 放在哪一層（`rule_summary` 之後、`limit_note` 之前或之後），字級、色階（現有是 `text-xs text-neutral-400`，N-171 note 是 `text-sm text-neutral-300`），上間距，以及 375px 下的換行行為。
2. 出清橫幅內 `directives`／`pending_directives` 列：同上。
3. 批次列：label 與 note 的相對版面（同一行還是 label 下方緊接），label 與 note 的字級、色階，以及 label 被長句擠壓時的處理。風控要求排版容不下時回審，所以請 art-lead 先定「容得下」的標準。
4. S2 列長句（W-B2LSf，約 310 字）：375px 下的預期行高，以及是否允許整列變高。
5. 結算面板：是否在範圍內。
6. ISO 日期：除 N-171 已有的 nowrap span 外，其他 surface 是否同一規則。

**可以比照、但需 art-lead 書面確認的選項**
- 若直接採 N-171 規範 §2 L6（`mt-1 break-words text-sm text-neutral-300`，無圖示、無底色、不縮排、同列）套到上述所有 surface，我可以立刻實作。
- 但在帳冊列和批次列，周圍元素是 `text-xs text-neutral-400`，整體會出現 note 比鄰近字更大、更亮的層級反轉，這是視覺決定，不由我拍板。

## 驗證
未執行 `tsc`、`vitest`、`next build`，因為尚未改任何檔案。目前只做了唯讀盤點，包括規範搜尋與四個元件的原始碼閱讀。

## 下一步
1. art-lead 補 N-168 各 surface 的視覺規範，或書面確認「全面比照 N-171 L6」，並回答上列第 1～6 項。
2. 規範到位後我再實作：
   - 帳冊列、橫幅、批次列、S2 列、結算面板（若在範圍）渲染 note。
   - vitest 涵蓋：有／無 note、批次列 label 加 note、310 字不截斷不摺疊、舊 body 缺鍵照常渲染且 SEAM-T8 維持綠燈。
   - 跑前端完整 CI，綠燈後 push，再交四段式與 qa-e2e 驗收重點。
3. 請指示是由我去向 art-lead 取規範，還是由你協調。
