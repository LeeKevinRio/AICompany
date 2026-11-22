# T-3 關鍵價位壞值拒算交件（frontend-engineer）

## 一、實作摘要
- `computeKeyLevels`：任一根 bar 的 close、high、low 非有限值或 <= 0，整條序列回 null（不濾壞 bar 續算）。函式註解（英文）已同步。
- 不改任何使用者可見字面（entryObservationWording.ts:92、:107 未動，另案）。
- 改寫 decisionCard.test.ts witness 與 describe 註解；新增測試涵蓋 keyLevels、entryObservation、KeyLevelsPanel null 分支、DecisionCard「—」格、priceUnitBadge close "0"。
- base：`origin/product/stock-desk` @ 6e6ac35f54368bd73eeeb7e03bc3308f5dd2cabe（開工前 fetch 所得；之後本機遠端追蹤 ref 已前進到 80e5c8b，本分支未 rebase，須合併者自行處理）。
- head：49c2ca3259d0ddaa334a55419f40aa9624af70b0，分支 `fix/keylevels-nonpositive-bars` 已 push（未 push product、未開 PR、未合併）。

## 二、變更檔案（相對 base 6e6ac35，皆在 apps/stock-desk/frontend/app/）
numstat（增 刪）：
- 6 4 lib/keyLevels.ts：加 <= 0 拒收與註解
- 22 14 lib/__tests__/decisionCard.test.ts：witness 改 toBeNull、移除 witness 值比對、describe 註解、新增 DecisionCard 壞 bar「—」格案例
- 26 0 lib/__tests__/keyLevels.test.ts：close/high/low × (0, -1) × (首、中、最新一根) = 18 案例，另加極小正數仍可算
- 13 0 lib/__tests__/entryObservation.test.ts：levels null 時 range/trend/pullback unavailable、observationBand null
- 42 0 lib/__tests__/keyLevelsNonPositivePanel.test.ts（新檔）：KeyLevelsPanel null 分支，面板句照舊
- 2 0 lib/__tests__/priceUnitBadge.test.ts：close "0" 案例

## 三、驗證結果
紅燈證據（暫時拿掉守門：`sed -i 's/ || n <= 0))/))/' app/lib/keyLevels.ts`，在 apps/stock-desk/frontend 跑 `npx vitest run`，未 commit，已還原；完整輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/red.txt`）：
- `Test Files 4 failed | 113 passed (117)`、`Tests 29 failed | 3081 passed (3110)`
- 紅的：keyLevels.test.ts 18 案例、decisionCard.test.ts 7 案例（R-2-a witness 6 + 新增 DecisionCard「—」格 1）、keyLevelsNonPositivePanel.test.ts 3 案例、priceUnitBadge.test.ts 1 案例。
- 失敗範例：`AssertionError: expected '<section ...' to contain '目前沒有可用的日線資料，本面板無法計算任何關鍵價位。'`（無守門時面板渲染出「收盤 0.00」與階梯）。
- 例外（誠實揭露）：entryObservation 新測試拿掉守門仍綠，因其直接傳入 levels = null，測的是 null 之後的行為，不經 computeKeyLevels；守門的牙由其他測試負責。

守門還原後（apps/stock-desk/frontend）：
- `npm run typecheck`（tsc --noEmit）：通過。
- `npm test`（vitest run）：Test Files 117 passed (117)；Tests 3110 passed (3110)。
- `npm run build`（next build）：成功。
- lint：package.json 與 stock-desk.yml 前端 job 均無 lint script，故未跑（CI 前端 job 為 npm ci、typecheck、test、build）。

## 四、ui-delivery-checklist 自檢
- 色值、字級、間距：未改任何樣式，無需對照。
- 使用者可見字面：未改。
- 空/載入/錯誤狀態：null 分支行為經元件層測試釘住（面板句照舊、DecisionCard「—」格、無單位 chip、無距離）。
- 數字單位與時間戳：未動。
- type check 嚴格：通過，無新增 any/強制斷言（decisionCard 測試移除了 witness! 斷言）。
- 375px 與桌面：無版面變更，未做實機視口驗證（交 qa-e2e）。
- 建議類文案：無新增，不需風控審查。

## 五、已知限制
- 壞值與空序列在面板顯示同一句，使用者無法區分（字面另案，見前置清單與 RC-584/598）。
- 未做實機視口驗證。
- 分支基於 6e6ac35，product/stock-desk 之後已前進到 80e5c8b。
