# manjong-unity API 契約 v0.2

> v0.2 變更（2026-10-03，CEO 要求）：牌局改走 **WebSocket**；後端主動提供**聽牌資訊**（打哪張會聽、聽哪幾張、各剩幾張）
> 與**胡牌台數預覽**。帳號 / 排行榜仍走 HTTP。牌局的 HTTP 端點（`/api/games*`）已移除，所有牌局操作只能經 WebSocket。
> 決策紀錄見 [`adr/M002-牌局改用-WebSocket.md`](adr/M002-牌局改用-WebSocket.md)。

- 開發時後端：`http://127.0.0.1:7316`（HTTP）與 `ws://127.0.0.1:7316/ws`（WebSocket）。WebGL 與伺服器同源時用頁面 origin（https 頁面用 `wss://`）。
- **JsonUtility 相容規則**：訊息永遠是物件；欄位永遠存在、不送 `null`（空字串 `""`、空陣列 `[]`、數字用 `-1` 表示「無」）；不使用多型。

## 1. HTTP（帳號與排行榜）

需要登入的端點帶 `Authorization: Bearer <token>`。錯誤：HTTP 4xx/5xx，body 為 `{ "error": { "code", "message" } }`。

| 方法 | 路徑 | body | 回應 |
| --- | --- | --- | --- |
| POST | `/api/auth/guest` | `{}` | `{ "token", "player": PlayerDto }` |
| GET | `/api/me` | | `{ "player": PlayerDto }` |
| POST | `/api/me/nickname` | `{ "nickname" }`（去頭尾空白 1–12 字） | `{ "player" }`；不合法 400 `INVALID_NICKNAME` |
| POST | `/api/me/relief` | `{}` | `{ "player" }`；金幣 ≥ 1,000 時 400 `RELIEF_NOT_ELIGIBLE` |
| GET | `/api/leaderboard` | （token 可選，帶了會標 `isMe`） | `{ "entries": [ { "rank", "nickname", "coins", "handsWon", "bestTai", "isMe" } ] }` |

```json
PlayerDto = { "id": "p_xxx", "nickname": "訪客1234", "coins": 20000,
              "handsPlayed": 0, "handsWon": 0, "selfDraws": 0, "dealIns": 0, "bestTai": 0 }
```

## 2. WebSocket（牌局）

連線 `GET /ws`（升級為 WebSocket），每個 frame 是一則 JSON 文字訊息。

### 2.1 用戶端 → 伺服器

```json
ClientMessage = { "type": "auth | start | action | ping", "token": "", "actionId": "" }
```

| type | 說明 |
| --- | --- |
| `auth` | **連線後第一則必須是它**，帶 `token`。10 秒內沒認證或 token 無效 → 伺服器送 `error`（`UNAUTHORIZED`）並以 close code `4401` 關閉。 |
| `start` | 開新的一場，或接續進行中的那場。金幣 < 1,000 且沒有進行中的牌局 → `error`（`NOT_ENOUGH_COINS`）。 |
| `action` | 帶 `actionId`，必須是最近一次 `state.view.options[].id` 之一，否則 `error`（`ILLEGAL_ACTION`），伺服器接著補送一次 `state` 讓用戶端重同步。 |
| `ping` | 伺服器回 `pong`。建議每 25 秒送一次保持連線。 |

同一個玩家開第二條連線時，舊連線會收到 close code `4000`（已在別處登入）。

### 2.2 伺服器 → 用戶端

```json
ServerMessage = {
  "type": "auth_ok | step | state | player | error | pong",
  "seq": 12,                 // 本連線內遞增序號
  "player": PlayerDto,       // auth_ok / player 時有內容，其他為空殼
  "step": StepDto,           // step 時有內容
  "view": GameView,          // state 時有內容
  "code": "",                // error 時：UNAUTHORIZED | NOT_ENOUGH_COINS | NO_GAME | ILLEGAL_ACTION | BAD_MESSAGE | INTERNAL
  "message": ""              // error 時：給人看的繁中訊息
}
StepDto = { "event": EventDto, "view": GameView }
```

| type | 何時送 |
| --- | --- |
| `auth_ok` | 認證成功。 |
| `step` | 牌局中每發生一個事件就**即時**推送（摸牌、補花、打牌、吃碰槓、胡、流局…）。AI 的動作由伺服器控制節奏（預設每個 AI 動作間隔約 0.6 秒），用戶端收到就播放。`step.view` 是該事件之後的畫面，**不含 options**（輪到你之前不能操作）。 |
| `state` | 權威快照：開局 / 接續時、每次輪到你需要決定時、每局結束時、動作被拒時。`view.options` 非空 = 等你做決定。 |
| `player` | 每局結算後送出最新的 PlayerDto（金幣、戰績）。 |
| `error` | 見 `code`。 |
| `pong` | 回應 `ping`。 |

**一次典型流程**：送 `start` → 收到一串 `step`（發牌、補花、AI 摸打…）→ 收到 `state`（options 有你的選項）→ 送 `action` → 收到一串 `step` → 收到 `state` → …

### 2.3 牌局資料

```json
EventDto = {
  "type": "hand_start | draw | flower | discard | chi | pon | kan | ankan | kakan | win | exhaustive | game_end",
  "seat": 0,             // 事件主角座位，無則 -1
  "tile": "5m",          // 相關牌；別家摸牌一律 ""（自己摸牌會告訴你摸到哪張）
  "tiles": ["4m","5m","6m"],
  "text": "熊熊 碰 五萬"   // 伺服器產生的繁中描述（自己摸牌時為空字串）
}

GameView = {
  "gameId": "g_xxx",
  "phase": "playing | hand_end | game_end",
  "handNo": 1, "roundWind": "E", "dealerSeat": 2, "dealerStreak": 0,
  "mySeat": 0,
  "turnSeat": 2,                 // 目前輪到誰，無則 -1
  "wallRemaining": 55,           // 還能摸的張數（已扣保留牌）
  "lastDiscardSeat": 1, "lastDiscardTile": "5m",
  "myCoins": 20000,              // 我的持久化金幣（已含本局結算）
  "myWaits": [ WaitDto ],        // 我目前「聽」哪些牌（手牌差一張就胡時才有；輪到我打牌時為空，改看各 discard 選項的 waits）
  "players": [ PlayerView ×4 ],  // 依座位 0..3
  "options": [ OptionDto ],      // 我現在可以做的動作；空陣列 = 不是我
  "hasResult": false,
  "result": HandResult           // hasResult=false 時為空殼
}

WaitDto = { "tile": "3p", "left": 2 }   // left = 以我看得到的牌（自己手牌 + 全部牌河 + 全部副露）推算還剩幾張

PlayerView = {
  "seat": 0, "name": "你", "avatar": "me | bear | cat | rabbit", "isAi": false, "seatWind": "E",
  "handCount": 16,            // 手牌張數（含剛摸的牌）
  "hand": ["1m","2m"],        // 只有自己有內容；hand_end 時四家都攤開；不含 drawnTile
  "drawnTile": "",            // 只有自己、且剛摸牌時才有值（UI 放在手牌最右邊）
  "melds": [ { "type": "chi | pon | kan | ankan | kakan", "tiles": ["3m","4m","5m"], "fromSeat": 3 } ],
  "flowers": ["F1"], "discards": ["9s","E"],
  "sessionDelta": 0           // 本場累計輸贏
}

OptionDto = {
  "id": "discard:5m | tsumo | ron | pon | kan | chi:3m | ankan:5m | kakan:5m | pass | next",
  "type": "discard | tsumo | ron | pon | kan | chi | ankan | kakan | pass | next",
  "tile": "5m",               // discard / ankan / kakan 的牌；ron / pon / kan / chi 為被吃碰胡的牌；其他 ""
  "tiles": ["3m","4m","5m"],  // chi 的順子組成；其他 []
  "label": "打 五萬（聽 三筒、六筒）",
  "waits": [ WaitDto ],       // 只有 discard：打出這張之後聽哪些牌（空 = 打這張不會聽牌）
  "tai": 5                    // 只有 tsumo / ron：這手胡下去的台數（不含莊家台）；其他 -1
}
```

**每次摸牌後**（`state.view.options`）後端會告訴你：

- 能不能胡：有 `tsumo` 選項，`tai` 是台數。
- 能不能槓、槓哪張、哪一種：`ankan:<牌>`（暗槓）或 `kakan:<牌>`（加槓），一張牌一個選項。
- 打哪張會聽、聽哪些：每個 `discard:<牌>` 選項的 `waits`。
- 別人打牌時：`ron`（含 `tai`）、`pon`、`kan`（明槓）、`chi:<順子最小牌>`、`pass`。
- 不是你的回合時：`view.myWaits` 是你目前聽的牌。

```json
HandResult = {
  "kind": "win | exhaustive", "winnerSeat": 1, "loserSeat": 3, "selfDraw": false, "winningTile": "5m",
  "totalTai": 7, "items": [ { "name": "門清", "tai": 1 } ],
  "dealerTai": 1,              // 莊家台 + 連莊台（只加在牽涉莊家的支付）
  "deltas": [ -450, 450, 0, 0 ],
  "gameOver": false
}
```

- 結算與台數全部由伺服器計算；`next` 選項（hand_end 時出現）開下一局；game_end 時 options 為空，回大廳。
