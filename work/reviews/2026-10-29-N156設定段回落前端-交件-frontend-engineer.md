# N-156 設定段回落前端交件

- 審查者：frontend-engineer
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 交件：N-156 前端（ADR-0032）

**commit：`47388c0`**（`feat: N-156 設定段回落前端揭露與 W-2 覆寫面板（ADR-0032 K-6、K-7、K-11）`）。已 push 到 `origin/fix/stock-desk-settings-fallback`（`aa4e419..47388c0`）。push 前 fetch 過，遠端沒有新 commit，所以沒有 merge。

commit 限定路徑 `apps/stock-desk/frontend/app`。我沒動後端，也沒讀 `.env`，沒碰 `data/*.db`，沒有安裝任何套件，`node_modules` 是從主 checkout `cp -a` 過來的。沒有 merge 或 push `product/stock-desk`。

### 後端結構核對
我拿後端 `fallback_wording.py`、`api/settings.py`、`api/advice.py`、`api/portfolio.py`、`api/kelly.py` 和「介面說明」逐欄對過，全部相符，所以沒有停下回報。
- `settings_fallback` 的欄位：`sections`、`notice`、`section_markers`、`form_overwrite_panel`、`net_worth_overwrite_panel`。
- 面板欄位：`sections`、`title`、`paragraphs`、`checkboxes`、`confirm_label`、`cancel_label`。
- `partial_save_notice`。
- advice、portfolio limits、kelly 的 `settings_fallback_notice`。
- `freshness` 的 `"fallback"`。
- `overwrite_fallback_sections`。

### 改動落點（路徑相對 `apps/stock-desk/frontend/app/`）
- **`lib/types.ts`**
  - `NetWorthFreshness` 加 `"fallback"`，在 :1344。
  - 新增 `OverwritePanelView` :1407、`SettingsFallbackView` :1425。
  - `SettingsResponse.settings_fallback` :1442、`partial_save_notice` :1447。
  - `AppSettingsPatch.overwrite_fallback_sections` :1474。
  - `AdviceResponse.settings_fallback_notice` :695、`PortfolioLimitsResponse.settings_fallback_notice` :763、`KellyDisclosuresView.settings_fallback_notice` :2202。
  - 都是字串類或依後端結構，沒有 `any`，也沒有強制斷言。
- **`lib/settingsFallback.ts`（新）**：純函式。
  - 兩個前端持有的固定字面：「使用預設值」:22、「無法顯示」:25。這兩個詞出自風控第 1 項表格，後端沒有下發。
  - `isFallbackSection` / `sectionMarkerOf` / `formFallbackSections`：判斷只看 `sections`。
  - `carriedFormSections` :58：未勾選的回落段不進 body。
  - `resolveFormSaveStep` :86：先開覆寫面板，再跑放寬確認，最後才寫入。
  - `buildFormPatch` :110、`buildNetWorthPatch` :131。
- **`settings/SettingsFallbackNotice.tsx`（新）**
  - 頁首區塊：`section` 元素、`text-sm`、`amber-200`，沒有 `<details>`、沒有關閉鈕、沒有 `role=status` 或 `aria-live`。
  - `SectionFallbackMarker`：`text-sm`、`amber-300`。
- **`settings/OverwritePanel.tsx`（新）**
  - 兩版面板共用。字面全來自後端。
  - 勾選框由 `checked` 集合決定，初始為空集合，所以預設不勾選。
  - 兩顆按鈕都是 `type=button`，disabled 時三通道齊全。
  - 面板開啟後焦點移到面板。
- **`settings/page.tsx` :43**：頁首區塊放在 `NetWorthSection` 之前。
- **`settings/SettingsForm.tsx`**
  - 標記在三個 h2 下方：:458、:496、:521。
  - `runSave` :368 → `resolveFormSaveStep` :402 → `buildFormPatch` :441。
  - 面板 :563。
  - 409 照錄 `detail`，不加前綴，在 :627。其他錯誤維持原本的「儲存失敗：」。
  - 部分儲存成功改顯示 `partial_save_notice`，沒有就維持「設定已儲存。」，在 :647。
  - 面板開啟時主按鈕 disabled。
- **`settings/NetWorthSection.tsx`**
  - `fellBack` :74，依 `sections` 判斷。
  - 徽章 :124、目前儲存的數值 :176、`FRESHNESS_LABELS.fallback` :43、`freshnessClass` 加 `fallback` :62。
  - 標記 :128。
  - 回落時第一次送出只開面板，確認後才送 `overwrite_fallback_sections: ["net_worth"]`（:103、:111、:203）。
  - 409 和 `partial_save_notice` 照錄。
  - notes 本來就由後端下發，後端已拿掉 `NET_WORTH_ABSENT_NOTE`，前端不用改。
- **`components/SettingsFallbackNoticeLine.tsx`（新）**：`text-sm`、`amber-200`，不收合。
- **`position/[symbol]/LimitsCheckList.tsx` :34**：清單層級，各條之上。
- **`components/RiskGauge.tsx` :212**：首頁清單層級，在共用 `<details>` 之外。
- **`position/[symbol]/DecisionCard.tsx` :515**：個股頁主畫面，緊接在 `LimitNoticeBlock`（CEO #59 的限額區塊）之後，`<details>` 之外。
  - 只在 held 與 candidate 顯示，不依賴任何一條上限的狀態。
  - `AdviceCardView.tsx` 與 `page.tsx` 把同一個欄位傳給清單層級。
- **`settings/KellyDisclosuresPanel.tsx` :222**：放在 `effective_cap` 數值那一行下方，同一個方框內，`text-sm`，與數值同級。
  - 數值區塊沒有顯示時，句子仍然獨立顯示（:228），不會被吞掉。
  - 沒有新增 `) : (`，既有的 B1 結構守門測試不用動。
- **`lib/queries.ts`**：`useUpdateSettings` 成功後多 invalidate `["advice"]` 與 `["kelly-disclosures"]`。這是我加的，規格沒要求。理由是覆寫之後，個股頁與 Kelly 頁不該繼續顯示「使用預設值」。
- **E2**：沒有任何特判。
  - 理由句本來就在 `downgrade_notices`，`AdviceCardView` 現有的渲染會顯示它。
  - `blocked_action` 是 null，所以不會出現「加碼建議被風險上限擋下」。
  - 有測試守住。

### 測試名稱
**新檔 1：`settings/__tests__/settingsFallback.test.ts`（45 個）**
- 描述區塊：「SettingsFallbackNotice — 頁首區塊（風控 第 1 項；K-6 哨兵）」。
  - 渲染結果逐字等於後端下發的 title 與各 item。
  - 不在 `<details>` 內、不能關閉。
  - 至少 `text-sm`、琥珀色。
- 「SectionFallbackMarker」。
- 「OverwritePanel — W-2 覆寫面板」
  - 每段一個勾選框，預設全部不勾選。
  - 只有勾的段是勾選狀態。
  - `net_worth` 版沒有勾選框。
  - disabled 三通道。
- 「回落判斷只看 settings_fallback.sections（K-6）」。
- 「沒勾選的回落段不進 PUT body；勾選的段進 overwrite_fallback_sections（K-11）」：
  - 無回落時三段全送。
  - 全不勾時回落段不在 body。
  - 只勾一段時只有它進 body。
  - 三段全回落且不勾時 body 為 `{}`。
  - `net_worth` 的 body。
- 「先出覆寫面板，再對已勾選的段跑放寬確認（DL-6）」：
  - 面板優先於放寬確認。
  - 放寬確認答完才寫入。
  - 風險預算沒勾就不跑放寬確認。
  - 沒有回落時行為與本案之前相同。
  - `SettingsForm` 只經過 `resolveFormSaveStep` 寫入，只有一個 `mutation.mutate(`。
- 「SettingsForm」：
  - 標記在 h2 正下方。
  - 回落時多出來的只有標記本身。
  - 面板在按儲存前不出現。
  - 409 照錄 `detail`。
  - 非 409 仍走「儲存失敗：」。
  - 部分儲存顯示 `partial_save_notice` 並取代「設定已儲存。」。
- 「NetWorthSection — net_worth 回落時三處改動」：
  - 徽章、目前儲存的數值、不含「尚未輸入」。
  - 標記位置。
  - sections 與數值矛盾時仍依 sections。
  - 反向案例。
  - 其他段回落時不受影響。
  - 409。
  - `partial_save_notice`。
- 「前端不自撰回落字面（K-6）」：新元件原始碼零漢字；`settingsFallback.ts` 只有那兩個詞；頁首區塊在 `NetWorthSection` 之前。

**新檔 2：`lib/__tests__/settingsFallbackNotice.test.ts`（20 個）**
- 「SettingsFallbackNoticeLine」。
- 「LimitsCheckList — 清單層級，各條之上」。
- 「RiskGaugeView — 首頁儀表清單層級」。
- 「DecisionCardBody — 個股頁主畫面再放一份」：
  - held 與 candidate 各出現一份，都不在 `<details>` 內。
  - 與限額區塊同一區。
  - 沒有限額區塊時也出現。
  - 沒有句子時不加。
  - 多出來的只有那一句。
- 「個股頁：主畫面與清單層級各一份，共兩份」。
- 「E2：理由句在 downgrade_notices，blocked_action 為 null，現有渲染照常顯示」。
- 「KellyDisclosuresPanel — effective_cap 數值旁」。

**既有測試的改動（只加嚴或補欄位，沒有放寬）**
- `componentWordingScan.test.ts`
  - `SCANNED_FILES` 加入 4 個新檔：`settingsFallback.ts`、`SettingsFallbackNoticeLine.tsx`、`SettingsFallbackNotice.tsx`、`OverwritePanel.tsx`。
  - 對 `<AdviceCardView>` 的 JSX 釘住，由 3 個 prop 改為 4 個 prop，順序固定。原有三個 prop 的斷言一字未動。
- 另外 14 個既有測試檔的 fixture 補上 `settings_fallback_notice: null`，原因是新欄位為必填，不補 tsc 過不了。

### ui-delivery-checklist 自檢
- **第 0 節**
  - 新揭露都是 `text-sm` 以上、`amber-200` 或 `amber-300`，比 neutral-300 亮。
  - 都不在 `<details>`、不摺疊、不截斷。
  - 字面一律由後端下發，沒有改動任何風控定稿字面。
- **1.1～1.4 對比**
  - 暗底配 amber-200／amber-300，遠高於 4.5:1。
  - 面板主按鈕是 neutral-100 底配 neutral-900 字，取自既有按鈕。
  - 我沒有逐一量測 OKLCH 或對比值，這是目測加 token 比對。
- **2.1～2.8**
  - 新增的按鈕與勾選框有 hover、active、disabled（原生 `disabled` 加 `opacity-50` 加 `cursor-not-allowed`）。
  - `focus-visible` 沿用瀏覽器預設；面板容器自己有 outline。
  - 沒有 transition。
- **3.x 響應式**
  - 按鈕列 `flex-wrap`，勾選框標籤可換行。
  - 沒有固定寬度，沒有 `transition: all`。
  - **375 與 1280 兩種寬度我沒有實機看過**，因為環境沒有瀏覽器，要交 qa-e2e 驗收。
- **5.x** 沒有寫死假資料，所有新字都來自後端回應。
- **6.x** 只用 Tailwind token，沒有 inline 色值或魔術數字。
- **空狀態、載入中、錯誤狀態**
  - 載入中是按鈕 disabled。
  - 409、其他錯誤、部分儲存都有處理。
  - 沒有回落時，畫面與本案之前完全相同，測試用「移除新增節點後逐字相等」證明。

### CI 原文數字
- `npx tsc --noEmit`：無輸出，exit 0。
- `npx vitest run`：`Test Files  97 passed (97)`、`Tests  2650 passed (2650)`。
- `npx next build`：`✓ Compiled successfully in 6.8s`，`✓ Generating static pages using 3 workers (8/8)`，route 清單含 `/settings`、`/position/[symbol]`。
- 後端 CI 沒跑，因為我沒動後端。

### 需要你知悉
1. **commit trailer 與你指定的不同。** 你指定 `Claude Opus 5.5`，但本次執行階段的歸屬規定是 `Claude Sonnet 5.5`，我如實採用後者。`Claude-Session` 那行一致。
2. **`componentWordingScan.test.ts` 的 `<AdviceCardView>` 釘住斷言我動過。** 它原本逐字要求恰好 3 個 prop。新增第 4 個 prop 勢必要改，我改成 4 個 prop 且順序固定，原有的 3 個仍逐字釘住。請 qa-reviewer 複核這處算不算放寬。
3. **`NetWorthSection` 的成功訊息：**
   - 我沒有「取代」它，而是在原本的「帳戶總淨值已更新…」之外，另外顯示後端的 `partial_save_notice`。
   - 原因是規格只明確要求 SettingsForm 取代「設定已儲存。」，net_worth 那句是另一句有資訊量的話，取代會丟資訊。
   - 若風控要求取代，改法很小。
4. **後端契約破損時的處理（fail-closed）：**
   - 後端若回報某段回落但沒給對應面板，前端不會送出回落段。
   - SettingsForm 只送其餘段。
   - NetWorthSection 不帶 `overwrite_fallback_sections` 直接送，讓後端的 409 照錄顯示。
5. 面板互動（勾選、先後順序、PUT body）受限於無 jsdom，是用純函式測試加 SSR 結構測試釘住的，沒有做真實點擊測試，qa-e2e 實機驗收時請實際點一次「儲存設定 → 面板 → 放寬確認 → 儲存」的完整路徑。
