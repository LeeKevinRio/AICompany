# N-155 排程台第 1 條衝突揭露前端交件

- 審查者：frontend-engineer
- 日期：2026-10-28
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-155 前端部分已完成並推上 `fix/stock-desk-playbook-cap1-disclosure`。前端 `tsc`、`vitest`、`next build` 全數通過，後端未動。

- commit：`8c2e3b6`（接在 `ae3655a` 之後，一個 commit）
- push 前先 `git fetch`，遠端沒有新 commit，所以沒有 merge，也沒有 rebase 或 force push。
- 依規定仍待 qa-reviewer 審查（含 Codex）與 qa-e2e 實機驗收（375px 與 1280px，confirmed 與 unconfirmed 各一）。我沒做實機驗收。

## 元件與渲染位置
路徑相對於 `apps/stock-desk/frontend/`。

- `app/playbook/Cap1DisclosureBlock.tsx:26-56`
  - 輸入是 `disclosure: PlaybookCap1Disclosure | undefined`，另有 `headingLevel: 2 | 3`。
  - 只渲染 `title`（標題元素）和 `lines`（逐句一個 `<p>`），順序照後端給的。
  - 欄位為 `undefined` 時回傳 `null`（`:37`）。這是唯一的不渲染條件。
  - 元件內沒有字面、沒有 template literal、沒有任何換算。
  - 樣式沿用 §6 區塊：`border-neutral-800 bg-neutral-900/60`，內文 `text-sm text-neutral-300`，標題 `text-sm font-medium text-neutral-200`。
  - 沒有 `<details>`、tooltip、關閉鍵、amber、red、圖示。
- 位置決定在 `app/lib/playbookView.ts:342` 的 `cap1DisclosureHost(mode)`，回傳 `"rule_set_panel"` 或 `"today_page"`。它決定的是放在哪裡，不決定顯不顯示。
- 今日頁 `app/playbook/page.tsx:110-112`
  - 只在 `cap1DisclosureHost(data.mode) === "today_page"` 時渲染，資料取自 `/today` 的 `data.cap1_disclosure`。
  - 順序是 歸屬語 → `page_summary` → warnings → 本區塊 → `DirectiveLedger`。
  - `unconfirmed` 時今日頁不渲染這一份。
- `app/playbook/RuleSetConfirmPanel.tsx:125`
  - 資料取自 `/rule-set` 的 `ruleSet.data.cap1_disclosure`。
  - 位置在「規則參數」`<dl>` 之後、⑥ 同意句之前。
  - 欄位缺失時不渲染，不會改用 `/today` 那一份補。
- 其他檔案
  - `app/lib/__tests__/componentWordingScan.test.ts:349`：把 `Cap1DisclosureBlock.tsx` 加進掃描清單。這是只加嚴，沒有動任何既有斷言。
  - `app/lib/types.ts` 沒有改。後端已加的 `PlaybookCap1Disclosure`（`:1757`）和兩處 optional 欄位，已經符合 F-3。

## F-1～F-4 測試
測試檔是 `app/playbook/__tests__/Cap1DisclosureBlock.test.ts`，共 37 則。fixture 的 `title` 與 `lines` 用 `SENTINEL-*`，pct 用 `"X%"`。

- F-1
  - `F-1 renders exactly the title then each line, in order, and nothing else`
  - `F-1 shows no number: no digit and none of the X% pct sentinels leak out`
  - `F-1 follows the received order and length rather than any fixed shape`
  - `F-1 keeps the title and lines intact on the real screens (today page and confirm panel)`
  - `F-1 does not display rules_version or any pct field of the disclosure`
- F-2
  - `F-2 the component file contains none of the forbidden identifiers`
  - `F-2 the component has no template literal (comments aside) and no string concatenation`
  - `F-2 the component hard-codes no Han text outside comments`
  - `F-2 the callers never wrap a disclosure field in a template literal`
  - `F-2 presentation floor: text-sm on neutral-300, neutral palette, no fold, tooltip, dismiss or icon`
  - `F-2 the rendered markup is a plain always-open section: no details, tooltip, button or icon`
- F-3
  - `F-3 PlaybookCap1Disclosure has exactly the five string-class fields`
  - `F-3 carries no numeric, boolean, comparison or status field (and no rules_version)`
  - `F-3 both responses carry it as an optional PlaybookCap1Disclosure (older backend omits it)`
- F-4
  - `F-4 confirmed (normal): the block renders on the today page`
  - `F-4 unconfirmed: the block renders inside the confirm panel`
  - `F-4 every mode renders its block exactly once (the host differs, the presence does not)`
  - `F-4 the block does not depend on its own content: any title and lines are shown`
  - `F-4 the component takes no mode and its source never mentions one`
  - `F-4 an absent field (older backend) renders nothing and invents nothing, in either host`
  - `F-4 unconfirmed never falls back to the /today copy when /rule-set sent none`
- 位置與順序
  - `unconfirmed 時今日頁不重複出現 /today 那一份`
  - `non-unconfirmed modes show only the /today copy and never the confirm panel's`
  - `today page order: 歸屬語 → page_summary → warnings → 本區塊 → DirectiveLedger (every non-unconfirmed mode)`
  - `confirm panel order: 規則參數 → 本區塊 → ⑥ 同意句 → 資本欄`
  - `the confirm panel renders its own block when mounted alone`
  - `the block is not part of page_summary: the summary block stays exactly the backend's sentences`
- 不得出現的位置
  - `EXIT 流程元件內不出現本區塊（原始碼與渲染輸出）`
  - `the EXIT flow's props carry only exit_confirm, never the disclosure`
  - `only page.tsx and RuleSetConfirmPanel.tsx use the block or read the field (no alerts, ledger row, snapshot, settlement)`
  - `DirectiveLedger rows and the 部位快照 never receive the disclosure`

反向驗證：我暫時把 `page.tsx` 改成一律渲染（沒有 commit，已還原）。F-1、F-4、位置共 4 則轉紅，測試有效。

## ui-delivery-checklist 自檢
- 第 0 節（風控地板）通過。
  - 字級是 `text-sm`，與 §6 區塊同級。
  - 對比是 `neutral-300`，不低於 §6 區塊。
  - 常駐、不摺疊、不在頁尾。
  - 字面沒有任何改動，全部由後端下發。
- 1.1 對比：`text-neutral-300`（#d4d4d4）疊在 `bg-neutral-900/60` 上，遠高於 4.5:1。我是估算，沒有逐值驗算。
- 1.3、1.4：區塊沒有按鈕，也不是深色翻色區塊，不適用。
- 第 2 節（Input 與互動狀態）：區塊沒有互動元素，不適用。
- 3.1、3.2、3.4：區塊是純文字段落，沒有固定寬度，會自然折行，不會橫向溢出。我沒做實機視口驗證，這部分留給 qa-e2e。
- 第 4 節（動效）：沒有動效。
- 第 5 節（誠實內容）：沒有寫死或捏造數字。所有內容來自後端，欄位缺失時不渲染。
- 6.1：只用既有 Tailwind token，沒有 inline 色值或 `font-family`。
- 6.2：間距沿用 `mt-4`、`space-y-1`、`px-3 py-2`，與 §6 區塊相同。
- 另外：標題用 `<section aria-labelledby>` 加 `useId` 連到標題元素，不寫死 id。

## CI 原文數字
- `npx tsc --noEmit`：rc=0。
- `npx vitest run`：Test Files 95 passed (95)，Tests 2568 passed (2568)。
  - 後端交件時是 94 個檔、2533 則；多的 1 個檔、35 則是新測試檔（37 則 `it`，其中 2 則落在既有檔案的計數內）。
- `npx next build`：Compiled successfully in 18.0s，8 頁靜態產生全部成功，路由含 `/playbook`。
- 後端：沒動，沒跑。
- 沒有任何安裝，`package.json` 與 lockfile 沒動。
- `frontend/node_modules` 是從主 checkout `cp -a` 過來的，已被 gitignore。`.next` 建置產物同樣沒有 commit。

## 已知限制與給審查者的提醒
1. **F-4 的字面解讀。** `page.tsx` 裡有 `cap1DisclosureHost(data.mode) === "today_page"` 這個條件，它是補充裁定第 3 節明定的「每個畫面恰好一次」所必需的。我把它當作位置選擇，不是顯示條件：兩個位置都在後端有給時就渲染，元件本身不收 `mode`，測試也釘住元件原始碼不含 `mode`。如果審查者認為任何與 mode 有關的分支都違反 F-4，請回報，這屬於規格之間的解讀問題，我沒有自行選邊。
2. **`rules_version` 刻意不放進前端型別，也不顯示。** 這是後端交件與 F-3 的規定，測試有釘住。
3. 後端交件的已知限制 2、3、5（`batches_per_target ≤ 0` 缺值句、`SettingsStore.load()` 逐段 fallback 到 10%、未確認時兩個版本號不同）與前端無關，仍待風控與 TA 裁定。
4. 沒有跑實機視口（375px 與 1280px）。測試用 `renderToStaticMarkup`，專案目前沒有 jsdom 或 E2E，這一段需要 qa-e2e 驗收。
5. 面向使用者的文字全部由後端下發，前端沒有新增任何自撰文案，所以沒有新的內容需要送風控審查。
