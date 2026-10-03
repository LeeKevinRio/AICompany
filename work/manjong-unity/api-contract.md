# manjong-unity API 契約 v0.3

> v0.3 變更（2026-10-03，CEO 要求）：
> - **登入、暱稱、救濟金、排行榜也改走 WebSocket**，HTTP API 全部移除（只留 `/api/health` 與 WebGL 靜態檔）。
> - **金幣下限 0**：玩家最多輸到 0；輸到 0 時整場立即結束，無法打下一局（`view.endReason = "bankrupt"`）。
> - 新增 `requestId` / `replyTo`：用戶端的請求可帶 id，伺服器的回應與錯誤會帶回同一個 id。
>
> v0.2：牌局改走 WebSocket；後端主動提供聽牌資訊與胡牌台數預覽。決策紀錄見 [`adr/M002-牌局改用-WebSocket.md`](adr/M002-牌局改用-WebSocket.md)。

- 開發時後端：`ws://127.0.0.1:7316/ws`。WebGL 與伺服器同源時用頁面 origin（https 頁面用 `wss://`）。
- HTTP 只剩 `GET /api/health`（回 `{ "ok": true }`）與 WebGL 靜態檔；**所有功能都經 WebSocket**。
- **JsonUtility 相容規則**：訊息永遠是物件；欄位永遠存在、不送 `null`（空字串 `""`、空陣列 `[]`、數字用 `-1` 表示「無」）；不使用多型。

## 1. 共用資料

```json
PlayerDto = { "id": "p_xxx", "nickname": "訪客1234", "coins": 20000,
              "handsPlayed": 0, "handsWon": 0, "selfDraws": 0, "dealIns": 0, "bestTai": 0 }
LeaderboardEntry = { "rank": 1, "nickname": "訪客1234", "coins": 23000, "handsWon": 3, "bestTai": 8, "isMe": true }
```

## 2. WebSocket

連線 `GET /ws`（升級為 WebSocket），每個 frame 是一則 JSON 文字訊息。

### 2.1 用戶端 → 伺服器

```json
ClientMessage = { "type": "...", "requestId": "", "token": "", "actionId": "", "nickname": "" }
```

`requestId` 可選（建議用遞增字串），伺服器對這則請求的回應與 `error` 會在 `replyTo` 帶回同一個值。

| type | 需登入 | 說明 |
| --- | --- | --- |
| `auth` | 否 | 用已存的 `token` 登入 → `auth_ok`。token 無效 → `error`（`INVALID_TOKEN`）並以 close code `4401` 關閉（**只有這種情況**用戶端才清掉 token，重連後改送 `guest`）。 |
| `guest` | 否 | 建立新的訪客帳號並登入 → `auth_ok`（含新 `token`，請存起來）。每條連線只能用一次。 |
| `me` | 是 | 取得自己的資料 → `player`。 |
| `nickname` | 是 | 帶 `nickname`（去頭尾空白後 1–12 字）→ `player`；不合法 → `error`（`INVALID_NICKNAME`）。 |
| `relief` | 是 | 領救濟金 → `player`；金幣 ≥ 1,000 → `error`（`RELIEF_NOT_ELIGIBLE`）。 |
| `leaderboard` | 是 | → `leaderboard`（前 50 名，依金幣排序）。 |
| `start` | 是 | 開新的一場或接續進行中的那場。沒有進行中的牌局且金幣 < 1,000 → `error`（`NOT_ENOUGH_COINS`）。 |
| `action` | 是 | 帶 `actionId`，必須是最近一次 `state.view.options[].id` 之一，否則 `error`（`ILLEGAL_ACTION`），伺服器接著補送一次 `state`。 |
| `ping` | 否 | → `pong`。建議每 25 秒送一次。 |

- 連線後 10 秒內沒有完成 `auth` 或 `guest` → `error`（`AUTH_TIMEOUT`）並以 `4408` 關閉。token 仍有效，用戶端應**保留 token** 重連。
- 未登入時送需要登入的訊息 → `error`（`UNAUTHORIZED`）並以 `4401` 關閉（用戶端程式錯誤，token 仍保留）。
- 同一個玩家開第二條連線時，舊連線收到 close code `4000`（已在別處登入）。
- 每條連線每 10 秒最多 100 則訊息，超過以 close code `1008` 關閉。

### 2.2 伺服器 → 用戶端

```json
ServerMessage = {
  "type": "auth_ok | player | leaderboard | step | state | error | pong",
  "seq": 12,                 // 本連線內遞增序號
  "replyTo": "",             // 回應某則請求時，帶回該請求的 requestId；主動推送（step / state / 結算後的 player）為 ""
  "token": "",               // 只有 guest 建立帳號後的 auth_ok 有值
  "player": PlayerDto,       // auth_ok / player 時有內容，其他為空殼
  "entries": [],             // leaderboard 時有內容（LeaderboardEntry 陣列）
  "step": StepDto,           // step 時有內容
  "view": GameView,          // state 時有內容
  "code": "",                // error 時：INVALID_TOKEN | AUTH_TIMEOUT | UNAUTHORIZED | INVALID_NICKNAME | RELIEF_NOT_ELIGIBLE | NOT_ENOUGH_COINS | NO_GAME | ILLEGAL_ACTION | BAD_MESSAGE | INTERNAL
  "message": ""              // error 時：給人看的繁中訊息
}
StepDto = { "event": EventDto, "view": GameView }
```

| type | 何時送 |
| --- | --- |
| `auth_ok` | `auth` 或 `guest` 成功（`guest` 時 `token` 有值）。 |
| `leaderboard` | 回應 `leaderboard`。 |
| `step` | 牌局中每發生一個事件就**即時**推送（摸牌、補花、打牌、吃碰槓、胡、流局…）。AI 的動作由伺服器控制節奏（預設每個 AI 動作間隔約 0.6 秒），用戶端收到就播放。`step.view` 是該事件之後的畫面，**不含 options**（輪到你之前不能操作）。 |
| `state` | 權威快照：開局 / 接續時、每次輪到你需要決定時、每局結束時、動作被拒時。`view.options` 非空 = 等你做決定。 |
| `player` | 回應 `me` / `nickname` / `relief`；另外每局結算後主動推送最新的 PlayerDto（金幣、戰績）。 |
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
  "myCoins": 20000,              // 我的持久化金幣（已含本局結算，最低 0）
  "endReason": "",               // phase=game_end 時："rounds_complete"（一圈打完）或 "bankrupt"（金幣歸零）；其他 ""
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
  "deltas": [ -450, 450, 0, 0 ], // 實際收付（玩家的支付以剩餘金幣為上限，見下方）
  "gameOver": false
}
```

**金幣下限 0**：玩家（真人）每筆支付最多付到金幣歸零，贏家只收到實際付出的金額（四家加總仍為 0）。
這一局結算後玩家金幣為 0 時，整場立即結束：`phase = "game_end"`、`endReason = "bankrupt"`、沒有 `next` 選項，
事件流最後會有 `game_end`（text「金幣歸零，牌局結束」）。AI 的金幣只是本場顯示，沒有下限。

- 結算與台數全部由伺服器計算；`next` 選項（hand_end 時出現）開下一局；game_end 時 options 為空，回大廳。
- 金幣歸零後要再玩：先 `relief` 領救濟金（補到 10,000），再 `start`。
