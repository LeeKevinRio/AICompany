# ADR-M002：牌局改用 WebSocket，後端主動提供聽牌與台數預覽

- 狀態：accepted（CEO 2026-10-03 指示：「前端會用 socket 來連線，任何操作都需要過後端」）
- 取代：ADR-M001 決策 2（牌局用 HTTP REST）。ADR-M001 其他決策不變。

## 背景

CEO 要求牌局連線改用 socket，且每次摸牌後由後端告知能否胡、槓（哪張、暗槓或加槓）、聽（打哪張聽哪些）、
摸到哪張牌，台數與結算全部由後端同步。

## 決策

1. 牌局走 WebSocket（`/ws`，`@fastify/websocket`，底層 `ws`）。牌局 HTTP 端點移除，避免兩條路徑。
   **補充（CEO 2026-10-03）：登入、暱稱、救濟金、排行榜也改走 WebSocket**，HTTP API 全部移除，只留健康檢查與 WebGL 靜態檔。
2. 認證：連線後第一則訊息帶 token（不放 URL query，避免 token 進存取紀錄）。同一玩家只保留最新一條連線。
3. **伺服器控制節奏**：AI 動作之間由伺服器等待（預設 600ms，`AI_DELAY_MS` 可調，測試設 0），事件即時推送。
   這和之後真人多人連線的形態一致，引擎與 session 不必再改。
4. 選項上帶出後端算好的資訊：discard 的 `waits`（含剩餘張數）、tsumo / ron 的 `tai`；view 帶 `myWaits`。
   剩餘張數只用該座位看得到的牌推算，不洩漏隱藏資訊。
5. Unity 端：WebGL 用自寫的 jslib 包瀏覽器 `WebSocket`（不引入第三方套件）；Editor / 桌面用 `System.Net.WebSockets.ClientWebSocket`，
   收到的訊息排進佇列，在主執行緒處理。

## 後果

- 新增依賴 `@fastify/websocket`（Fastify 官方外掛）。
- 斷線時伺服器端牌局照常保留；重連並送 `start` 會收到最新 `state`。斷線期間 AI 不會替你出牌（輪到你時會停住等待）。
- WebSocket 沒有 HTTP 的請求 / 回應對應，用戶端要靠 `state` 快照確認目前狀態；動作被拒時伺服器會補送 `state`。
