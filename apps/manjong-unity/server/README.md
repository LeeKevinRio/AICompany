# manjong-unity server

台灣 16 張麻將的權威伺服器（TypeScript / Node.js 22 / Fastify）。規則、洗牌、AI、聽牌計算、台數與結算全部在這裡；
Unity 用戶端只送「選了哪個合法動作」。帳號 / 排行榜走 HTTP，牌局走 WebSocket（`/ws`），見 API 契約 v0.2。

- 規則與台數表：`work/manjong-unity/規則與台數表.md`（數值在 `src/engine/rules.ts`）
- API 契約：`work/manjong-unity/api-contract.md`
- 架構決策：`work/manjong-unity/adr/M001-架構與前後端切分.md`

## 開發

```bash
npm install
npm run dev        # http://127.0.0.1:7316，存檔自動重啟
npm test           # 單元 + HTTP + WebSocket 整合測試
WS_GAMES=200 npx vitest run test/socket.test.ts   # 長時間驗證：透過 WebSocket 打 200 場，逐步比對聽牌 / 槓 / 胡 / 台數
npm run typecheck
npm run simulate -- 1000   # 1000 場全 AI 對打：檢查牌數守恆、零和，並輸出台型統計
```

## 環境變數

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `PORT` | `7316` | |
| `HOST` | `127.0.0.1` | 要讓同網段其他裝置連線時設 `0.0.0.0` |
| `DATA_FILE` | `data/players.json` | 玩家資料（已被 `.gitignore`） |
| `WEBGL_DIR` | `../client/Build/WebGL` | 有 Unity WebGL build 時，伺服器同源提供網頁（開 `http://127.0.0.1:7316/`） |
| `CORS_ORIGIN` | （全部允許） | 逗號分隔的允許來源（同時用來檢查 WebSocket 的 Origin）。`NODE_ENV=production` 時必填 |
| `AI_DELAY_MS` | `600` | 每個 AI 動作前的等待（毫秒），控制牌局節奏 |

## 目錄

```
src/engine/   規則引擎：牌碼、牌型分析（向聽 / 聽牌 / 拆解）、台數計算、狀態機
src/ai/       AI（牌效：向聽數 + 有效牌，三種吃碰個性）
src/game/     一人對三 AI 的 session、每座位的畫面（隱藏資訊不外流）、全 AI 模擬
src/api/      HTTP 路由、WebSocket 牌局協定（socket.ts）、訪客帳號、金幣與排行榜、牌局管理
src/store/    玩家資料儲存（JSON 檔，原子寫入）
```

## 已知限制（v0.1）

- 牌局狀態放記憶體，伺服器重啟會中斷進行中的牌局（金幣結算是每局即時寫入，不受影響）。
- HTTP 沒有 rate limit（WebSocket 有每 10 秒 100 則的簡易限制）；正式部署前要補。
- 中途離開不會被判輸；目前排行榜只有自己，之後做多人時再處理。
