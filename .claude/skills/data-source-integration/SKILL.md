---
name: data-source-integration
description: 接入新外部資料源的標準步驟：adapter 介面、契約測試、快取、rate limit、離線 fixture、降級策略。data-engineer 接任何資料源時必用。
---

# Data Source Integration — 資料源接入標準

## 原則

- 所有外部資料源都包成可替換的 adapter，實作同一個抽象介面；上層 code 不知道資料從哪家來。
- 每筆回傳資料一律帶 `as_of`（資料時間戳）與 `source`（來源識別）欄位。
- 免費資料源會壞，降級路徑是設計的一部分，不是例外處理。

## 接入步驟

1. **調查與比較**：額度、rate limit、資料範圍、穩定度、授權條款。多來源擇一時寫成比較表放 `docs/adr/`，由 tech-architect 拍板主來源與備援。
2. **定義介面**：先寫抽象介面與回傳物件 schema（含 `as_of`、`source`），再寫 adapter。
3. **實作 adapter**，必要條件缺一不可：
   - **快取**：本機快取，TTL 可設定。
   - **Rate limit**：客戶端節流，不打爆對方。
   - **重試**：指數退避（exponential backoff），有次數上限。
   - **離線 fixture**：錄下真實回應存成 fixture，測試一律用 fixture 不打外網。
   - **逾時**：所有外部呼叫都有 timeout。
4. **契約測試**：驗 adapter 輸出符合 schema（欄位、型別、時間戳存在）；fixture 過期格式改變時測試要會抓到。
5. **資料品質檢查**：缺漏日期、重複列、型別 / 幣別錯置、未來日期、新鮮度。任一觸發要浮上檯面（UI 或 log 明示），不得靜默補值。
6. **降級策略**：主來源失敗 → 備援來源 → 快取（明示「資料延遲 X 分鐘」）→ 明確錯誤狀態。每一層的使用者可見狀態都要定義。

## 紅線

- 憑證只走環境變數；不進 code、設定檔、fixture。
- 不用假資料或內插值冒充真實資料。
- 不憑記憶寫死費率、額度或 API 規格——查證當下文件並記錄查證日期。
