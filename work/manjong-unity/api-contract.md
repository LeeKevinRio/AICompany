# manjong-unity API 契約 v0.1

- Base URL：開發時 `http://127.0.0.1:7316`；WebGL 與伺服器同源時用頁面 origin。
- 所有路徑前綴 `/api`，請求與回應都是 JSON（`Content-Type: application/json`）。
- 需要登入的端點帶 `Authorization: Bearer <token>`。
- **JsonUtility 相容規則**：回應永遠是物件（不是頂層陣列）；欄位永遠存在、不送 `null`
  （空字串 `""`、空陣列 `[]`、數字用 `-1` 表示「無」）；不使用多型。
- 錯誤：HTTP 4xx/5xx，body 為 `{ "error": { "code": "STRING_CODE", "message": "給人看的繁中訊息" } }`。

## 1. 帳號

### `POST /api/auth/guest`
body：`{}` → `200 AuthResponse`

```json
{ "token": "base64url...", "player": PlayerDto }
```

### `GET /api/me` → `{ "player": PlayerDto }`

### `POST /api/me/nickname`
body：`{ "nickname": "小明" }`（去頭尾空白後 1–12 字）→ `{ "player": PlayerDto }`；不合法回 400 `INVALID_NICKNAME`。

### `POST /api/me/relief`
body：`{}` → `{ "player": PlayerDto }`；金幣 ≥ 1,000 回 400 `RELIEF_NOT_ELIGIBLE`。

```json
PlayerDto = {
  "id": "p_xxx", "nickname": "訪客1234", "coins": 20000,
  "handsPlayed": 0, "handsWon": 0, "selfDraws": 0, "dealIns": 0, "bestTai": 0
}
```

## 2. 排行榜

### `GET /api/leaderboard`（可不帶 token；帶了會標 `isMe`）

```json
{ "entries": [ { "rank": 1, "nickname": "訪客1234", "coins": 23000, "handsWon": 3, "bestTai": 8, "isMe": true } ] }
```

## 3. 牌局

### `POST /api/games` body：`{}` → `200 ActionResponse`（建立新的一場並開始第一局）
金幣 < 1,000 回 400 `NOT_ENOUGH_COINS`。同一玩家已有進行中的牌局時會直接沿用（回傳該局）。

### `GET /api/games/:id` → `ActionResponse`（`steps` 為空陣列，用來斷線續玩）

### `POST /api/games/:id/actions`
body：`{ "actionId": "discard:5m" }` → `ActionResponse`
- `actionId` 必須是目前 `view.options[].id` 之一，否則 400 `ILLEGAL_ACTION`。
- 伺服器套用動作後，自動跑完所有 AI，直到再次需要玩家決定、或該局 / 整場結束。

```json
ActionResponse = {
  "steps": [ { "event": EventDto, "view": GameView } ],
  "view": GameView
}
```

`steps` 依時間順序；每一步的 `view` 是該事件發生**之後**的畫面。用戶端逐步播放（約 0.3–0.5 秒一步），最後套用 `view`。

```json
EventDto = {
  "type": "hand_start | draw | flower | discard | chi | pon | kan | ankan | kakan | win | exhaustive | game_end",
  "seat": 0,            // 事件主角座位，無則 -1
  "tile": "5m",         // 相關牌，無則 ""（別家摸牌時一律 ""）
  "tiles": ["4m","5m","6m"],
  "text": "熊熊 碰 五萬"  // 伺服器產生的繁中描述，用戶端直接顯示
}
```

```json
GameView = {
  "gameId": "g_xxx",
  "phase": "playing | hand_end | game_end",
  "handNo": 1,                 // 本場第幾局（從 1 開始）
  "roundWind": "E",            // 圈風
  "dealerSeat": 2,
  "dealerStreak": 0,           // 連莊次數
  "mySeat": 0,
  "turnSeat": 2,               // 目前輪到誰，無則 -1
  "wallRemaining": 55,         // 還能摸的張數（已扣保留牌）
  "lastDiscardSeat": 1,        // 最後一張打出牌的座位，無則 -1
  "lastDiscardTile": "5m",     // 無則 ""
  "myCoins": 20000,            // 我的持久化金幣（已含本局結算）
  "players": [ PlayerView, PlayerView, PlayerView, PlayerView ],  // 依座位 0..3
  "options": [ OptionDto ],    // 我現在可以做的動作；空陣列 = 等待中 / 無事可做
  "hasResult": false,
  "result": HandResult         // hasResult=false 時為空殼（預設值）
}

PlayerView = {
  "seat": 0, "name": "你", "avatar": "me | bear | cat | rabbit", "isAi": false,
  "seatWind": "E",
  "handCount": 16,             // 手牌張數（含剛摸的牌）
  "hand": ["1m","2m"],         // 只有自己有內容；hand_end 時四家都攤開；不含 drawnTile
  "drawnTile": "",             // 只有自己、且剛摸牌時才有值（UI 把它放在手牌最右邊）
  "melds": [ { "type": "chi | pon | kan | ankan | kakan", "tiles": ["3m","4m","5m"], "fromSeat": 3 } ],
  "flowers": ["F1"],
  "discards": ["9s","E"],      // 河裡的牌（被吃碰槓走的不在內）
  "sessionDelta": 0            // 本場累計輸贏
}
// 別家的暗槓：tiles 一律回傳 4 張真實牌碼（台灣規則暗槓通常蓋牌，UI 可選擇只亮兩張）。

OptionDto = {
  "id": "discard:5m | tsumo | ron | pon | kan | chi:3m | ankan:5m | kakan:5m | pass | next",
  "type": "discard | tsumo | ron | pon | kan | chi | ankan | kakan | pass | next",
  "tile": "5m",                // discard / ankan / kakan 的牌；ron/pon/kan/chi 為被吃碰的牌；其他 ""
  "tiles": ["3m","4m","5m"],   // chi 的順子組成；其他 []
  "label": "吃 三四五萬"
}
// 打牌：每種可打的牌各一個 discard 選項。UI 不必列 discard 按鈕，點手牌即送對應 id。
// 選項 "next"：hand_end 時出現，送出後開下一局。game_end 時 options 為空，回大廳。

HandResult = {
  "kind": "win | exhaustive",
  "winnerSeat": 1,             // 流局 -1
  "loserSeat": 3,              // 自摸 / 流局 -1
  "selfDraw": false,
  "winningTile": "5m",
  "totalTai": 7,               // 不含莊家台
  "items": [ { "name": "門清", "tai": 1 } ],
  "dealerTai": 1,              // 莊家台 + 連莊台（只加在牽涉莊家的支付）
  "deltas": [ -450, 450, 0, 0 ], // 依座位
  "gameOver": false
}
```
