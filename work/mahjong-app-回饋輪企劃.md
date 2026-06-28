# MahjongScore — CEO 回饋輪企劃（v2.1）

> 產品代號：**MahjongScore v2.1**
> 企劃人：creative-lead
> 日期：2026-06-28
> 現況基礎：v2 已上線（`apps/web/`），本文件為 CEO 實測回饋後的第一輪迭代企劃。
> 上游文件：`work/mahjong-app-v2-企劃.md`、`work/mahjong-app-v2-視覺規範.md`

---

## 0. 企劃背景

CEO 實測 v2 後提出五大方向的回饋與新需求。本輪企劃目標：

1. 把「玩家」從依附 session 的名字升級為真正的獨立實體（玩家名冊）。
2. 新增兩個開桌規則選項：自摸加台、東錢。
3. 設計「開桌規則組」機制，每場可獨立設定，並與全域預設整合。
4. 在前一版 6 項創意延伸的基礎上，再發想一批新功能點子。

本文件的「東錢規則提案」部分需 **CEO 確認後**，dev-lead 方可開始實作計分邏輯。

---

## 1. 玩家管理移至「玩家」頁籤 + 玩家名冊（Roster）

### 1-1. 現況痛點分析

讀程式碼後確認現況：
- `PlayersPage.tsx`：玩家清單從 `collectPlayerNames(sessions)` 動態彙整，玩家**不是**獨立實體，沒有自己的 id，跨場以「名字字串完全比對」聚合。
- `SettingsPage.tsx`：常用玩家（`knownPlayers`）是 `GlobalSettings.knownPlayers: string[]`，只是「可快速帶入的名字清單」，功能獨立，不與玩家頁掛勾。
- 新增玩家入口：隱藏在「設定 > 常用玩家」或「開桌時的玩家輸入欄」，無獨立管理入口。
- 玩家頁只能看統計，無法從此頁新增管理玩家。

### 1-2. 核心設計決策：要不要升級成獨立實體？

**建議：是。引入 `RosterPlayer`（玩家名冊成員）作為跨場識別單位。**

理由：
- CEO 需要「每位玩家各自的戰績查找」，這要求跨場能精準辨識「同一個人」。
- 目前以名字聚合有歧義（改名、同名不同人都會造成資料錯亂）。
- 玩家名冊統一管理後，「開桌選人」流程更快（從名冊點選，不用每次打字）。

**資料模型建議（給 dev-lead 參考，需 CEO 最終確認模型方向）：**

```ts
/** 玩家名冊成員：跨場的獨立實體 */
interface RosterPlayer {
  id: string;          // uuid，全域唯一，不隨名字改變
  name: string;        // 顯示名稱（可改）
  createdAt: number;
  /** 備用：若同一人曾用過其他名字，存在這裡方便查歷史合併 */
  aliases?: string[];
}
```

`GlobalSettings` 新增：
```ts
interface GlobalSettings {
  defaultBase: number;
  defaultTai: number;
  knownPlayers: string[];   // 舊欄位，v2.1 後可逐步廢棄
  roster: RosterPlayer[];   // 新增：玩家名冊
}
```

`Session.players` 的 `Player` 介面新增可選欄位 `rosterId`，建立跨場連結：
```ts
interface Player {
  id: string;          // 'p1'~'p4'（局內識別，不變）
  name: string;        // 顯示名稱（場內可改）
  rosterId?: string;   // 連結到 RosterPlayer.id（若從名冊選入則有此值）
}
```

**向下相容策略（重要，防舊資料爆掉）：**
- 舊 session 的 `Player` 沒有 `rosterId`，視為「無掛勾的歷史玩家」。
- 玩家頁的統計彙整邏輯優先以 `rosterId` 聚合，若無 `rosterId` 則 fallback 用名字字串（維持 v2 現有行為）。
- 聚合函式 `aggregatePlayerStats` 需擴充一個 `aggregateByRosterId` 版本。

### 1-3. 玩家頁 UI 規劃

#### 主頁（Tab 2 - 玩家）

```
┌─────────────────────────────────────┐
│  玩家                      [+ 新增] │  ← 右上新增按鈕（或用 FAB）
├─────────────────────────────────────┤
│  搜尋玩家名字…                       │  ← 玩家多時用得到
├─────────────────────────────────────┤
│ ▌ 小明   出場 12 場   +15,200  ~~~ │  ← 左側玩家色條、Sparkline 右側
│ ▌ 阿美   出場 10 場   -3,400   ~~~  │
│ ▌ 老王   出場 8 場    +800     ~~~  │
│   …                                 │
└─────────────────────────────────────┘
```

- 新增按鈕：點擊 → 底部 Sheet 彈出（輸入名字，建立 `RosterPlayer`，立即出現在清單）。
- 清單排序：預設依出場次數降序；可改為依總輸贏、名字排序（下拉切換）。
- 清單中有歷史資料但未建立名冊條目的玩家：以「灰色標記（非名冊成員）」方式顯示，提示用戶可點選「加入名冊」。

#### 新增玩家 Bottom Sheet

```
┌─────────────────────────────────────┐
│  拖把         [新增玩家]             │
│                                     │
│  姓名  [________________]           │
│                                     │
│  [取消]          [確認新增]         │
└─────────────────────────────────────┘
```

#### 玩家詳情頁（現有 PlayerDetailPage.tsx 擴充）

現有已有：總輸贏、出場場次、胡牌/自摸/放槍局數、勝率、連贏/連輸、跨場走勢圖、場次歷史。

**v2.1 新增：**
- 頁面頂部加「編輯名字」鈕（鉛筆 icon），點選可修改 RosterPlayer 名稱（同步更新歷史顯示名稱）。
- 統計卡新增「近 5 場均輸贏」（最近 5 場的場均）。
- 場次歷史列表：每行顯示場名 + 日期 + 輸贏金額，沿用現有；點入可跳轉至該 SessionDetailPage。

### 1-4. 開桌流程中「選玩家」的改動

新增牌局 Bottom Sheet（`SessionsPage.tsx` 的 `NewSessionSheet`）現有欄位：4 個玩家名字文字輸入 + 常用玩家快速帶入。

**v2.1 改動：**
- 保留文字輸入（手動輸入仍可）。
- 常用玩家快速帶入改成從名冊選入：點選名冊成員 chip 後，同時帶入名字與 `rosterId`。
- 沒有名冊時 fallback 到目前的 `knownPlayers` chips（相容舊設定）。

---

## 2. 自摸自動加一台（開桌規則選項）

### 2-1. 功能說明

自摸時自動在玩家輸入的台數上再加 1 台，讓計分系統處理，玩家不需手動加。

**預設：開啟**（CEO 指定的預設狀態）。

### 2-2. 資料模型

自摸加台屬於「開桌規則」，放進 `SessionRules`（見第 4 節）：

```ts
interface SessionRules {
  selfDrawBonusTai: number;  // 自摸自動加台數，預設 1；若不要加則設 0
  // ... 其他規則（東錢見第 3 節）
}
```

### 2-3. 計分影響

`scoreRound` 目前計算：`amount = base + tai × 每台`。

加入 `SessionRules` 後，自摸時：

```
effectiveTai = round.tai + rules.selfDrawBonusTai  （僅自摸時）
amount = base + effectiveTai × 每台
```

放槍不受此規則影響，`effectiveTai = round.tai`。

**範例（底 100、台 50、自摸加 1 台）：**
- 玩家輸入「2 台」自摸
- effectiveTai = 2 + 1 = 3 台
- amount = 100 + 3 × 50 = 250
- 贏家收 250 × 3 = 750，其他三家各付 250

**範例（關閉自摸加台，同樣 2 台自摸）：**
- effectiveTai = 2 + 0 = 2 台
- amount = 100 + 2 × 50 = 200
- 贏家收 200 × 3 = 600，其他三家各付 200

### 2-4. UI

開桌時（新增牌局 Bottom Sheet）新增規則區（詳見第 4 節）：
- 開關：「自摸加台」（預設 ON）
- 加台數：數字 input（預設 1，可設 0、1、2）

---

## 3. 東錢功能規劃

### 3-1. 東錢機制說明（CEO 提供的背景）

自摸贏家除正常底 + 台金額外，還會額外「收東錢」。東錢是台灣麻將的地區性規則，各地玩法略有差異。

### 3-2. 規則提案（需 CEO 確認）

以下是 creative-lead 提出的**建議機制**，基於「讓計分加總仍為 0」與「與現有底+台疊加不衝突」兩個原則設計。

---

**提案：東錢為固定額外費用，僅在自摸時收取，三家各付一份東錢給贏家。**

| 項目 | 建議值 | 說明 |
|---|---|---|
| 東錢金額 | 可設定，預設 100 | 一個固定值，與底/台無關，不隨台數變化 |
| 誰付 | 其他三家每人各付一份（3 × 東錢） | 贏家淨收 3 × 東錢 |
| 觸發條件 | 僅自摸時 | 放槍不收東錢 |
| 與底+台的關係 | 額外疊加，不影響底+台計算 | 東錢是單獨一筆，不併入台數 |

**「需 CEO 確認」項目：**
1. 東錢金額是否為固定值（不隨台數變化）？還是跟台數連動？
2. 是三家各付，還是只有某一家（例如只有「東家」或「莊家」）付？
3. 若本場沒有莊家制度，「東錢」是否就是每局三家各付的固定額？

---

### 3-3. 計分範例（待 CEO 確認後以實際規則為準）

**以下以「建議提案」為基礎示算：**

場景：底 100、台 50、自摸加 1 台開啟、東錢 100

**某人自摸 2 台：**

```
步驟 1：計算底+台金額
  effectiveTai = 2（輸入）+ 1（自摸加台）= 3 台
  amount = 100 + 3 × 50 = 250

步驟 2：底+台收款
  贏家收：250 × 3 = 750（三家各付 250）

步驟 3：東錢收款
  贏家另收：100 × 3 = 300（三家各付 100）

步驟 4：合計
  贏家本局 +1,050
  其他三家各 -350（250 底台 + 100 東錢）

驗算：+1,050 + (-350) × 3 = +1,050 - 1,050 = 0 ✓（加總為零）
```

**同場放槍 2 台（不觸發東錢與自摸加台）：**

```
  amount = 100 + 2 × 50 = 200
  贏家 +200，放槍者 -200，另兩家 0
  驗算：+200 - 200 + 0 + 0 = 0 ✓
```

**東錢關閉時的自摸 2 台（僅自摸加台）：**

```
  effectiveTai = 3 台，amount = 250
  贏家 +750，其他三家各 -250
  驗算：0 ✓
```

### 3-4. 資料模型

```ts
interface SessionRules {
  selfDrawBonusTai: number;   // 自摸加台，預設 1（0=關閉）
  eastMoney: number;          // 東錢金額，0=關閉，預設 100（待 CEO 確認）
  // 未來預留：dealerBonusTai（莊家加台）
}
```

### 3-5. 對 `scoreRound` 的擴充方向（給 dev-lead）

`scoreRound` 現有簽章：
```ts
scoreRound(round: Round, players: Player[], settings: Settings): RoundDelta
```

建議擴充為可接受可選的 `rules` 參數：
```ts
scoreRound(
  round: Round,
  players: Player[],
  settings: Settings,
  rules?: SessionRules,
): RoundDelta
```

- `rules` 未傳入時行為與現有完全一致（向下相容所有舊場次）。
- 內部邏輯：
  1. 若 `round.selfDraw && rules?.selfDrawBonusTai` → effectiveTai = round.tai + selfDrawBonusTai
  2. 若 `round.selfDraw && rules?.eastMoney > 0` → 在底+台金額之外，贏家再收 eastMoney × 3，其他三家各再扣 eastMoney
  3. 每局加總必須驗算為 0（建議加一個 dev-only 的 assert）

---

## 4. 開桌規則設計（SessionRules 整合）

### 4-1. 設計目標

- 每場牌局可有自己的規則組（不同場可打不同規則）。
- 全域有「規則預設」，開桌時自動套用，開桌時仍可調整。
- 規則存進 `Session`，不隨 `GlobalSettings` 變動而影響歷史場次。

### 4-2. 完整資料模型擴充

```ts
/** 開桌規則組（存進 Session，跨場可不同） */
interface SessionRules {
  selfDrawBonusTai: number;  // 自摸加台，預設 1（0=關閉）
  eastMoney: number;         // 東錢額，0=關閉（待 CEO 確認預設值）
  // 預留擴充（本次暫不實作）：
  // dealerBonusTai?: number;    // 莊家加台
  // maxTai?: number;            // 最高台數上限
}

/** Session 介面新增 rules 欄位 */
interface Session {
  id: string;
  name: string;
  players: Player[];
  settings: Settings;
  rules: SessionRules;       // 新增：開桌規則（舊場次 migration 用預設值補入）
  rounds: Round[];
  createdAt: number;
  endedAt?: number;
}

/** GlobalSettings 新增規則預設欄位 */
interface GlobalSettings {
  defaultBase: number;
  defaultTai: number;
  knownPlayers: string[];
  roster: RosterPlayer[];        // 新增（第 1 節）
  defaultRules: SessionRules;    // 新增：全域規則預設
}
```

**舊資料遷移（Migration）：**
- 讀取舊 `Session`（無 `rules` 欄位）時，自動補入 `defaultRules` 或 hardcode 預設值：
  ```ts
  const DEFAULT_SESSION_RULES: SessionRules = {
    selfDrawBonusTai: 0,  // 舊場次不追溯加台（行為維持原始計分）
    eastMoney: 0,          // 舊場次無東錢
  };
  ```
- **重要**：舊場次補入的 `selfDrawBonusTai` 必須是 `0`（不是 `1`），否則所有舊場次的分數會被改變，造成資料錯亂。

### 4-3. 開桌時的規則設定 UI

**新增牌局 Bottom Sheet 新增「規則設定」區塊：**

```
┌─────────────────────────────────────┐
│  拖把         [新增牌局]            │
│                                     │
│  場名  [2026/06/28 場____________]  │
│                                     │
│  玩家 1  [___________]              │
│  玩家 2  [___________]              │
│  玩家 3  [___________]              │
│  玩家 4  [___________]              │
│  常用玩家：[小明] [阿美] [老王]     │
│                                     │
│  ──── 規則設定 ────────────────── │
│                                     │
│  自摸加台   [  ON  ]  加 [1] 台    │
│  東錢       [ OFF  ]  每份 [___]   │
│                                     │
│  底 [100] 台 [50]                   │
│  （可改，不影響全域預設）           │
│                                     │
│  [取消]          [建立牌局]         │
└─────────────────────────────────────┘
```

- 自摸加台開關預設 ON，加台數預設 1（數字可調整）。
- 東錢開關預設依全域規則預設（等 CEO 確認後設定）；金額文字輸入。
- 底/台預設帶入全域預設，開桌時仍可改（沿用現有行為）。

### 4-4. 進入牌局後能否改規則？

**建議：進入牌局後允許修改規則，但給警示提示。**

原因：打到一半發現設錯規則是現實情境。但修改後會影響所有已輸入局次的計分，需要警告。

現有的 `SettingsPanel` 元件（底/台調整）可作為模板，擴充成含規則欄位。

---

## 5. 更多功能發想（新一批，分級）

以下在 v2 企劃的 6 項之外，再發想 12 個新點子。

### 建議做（高價值、實作成本低）

| 功能 | 價值說明 |
|---|---|
| **玩家大頭照 / Emoji 頭像** | 玩家清單與排名條不只是名字，加一個 emoji 或圓形頭像，打牌現場辨識更快、更有趣，一行 CSS 即可顯示 |
| **快速重開同組牌局** | 場次歷史頁新增「再開一場（同組玩家）」按鈕，自動帶入本場 4 人名單建立新局，省去每次手打 4 個名字 |
| **每場「最快結束局」統計** | 走勢圖頁下方顯示本場最快結束（台數最低）與最大台局次，讓無聊的「一台胡」也有記憶點 |
| **本場前後換算（匯率）** | 明細頁下方顯示「折合每局平均底台金額、平均台數」，讓玩家一眼知道今天牌風是大台還是小台 |
| **輸贏警戒線設定** | GlobalSettings 新增「提醒我單場輸超過 N 元」，達標時在排名條顯示紅色警示，讓玩家自律 |
| **放槍者標記警示** | 記局頁新增一局後，若同一玩家本場已放槍 3 次以上，在放槍者欄旁顯示「本場已放槍 N 次」，方便追蹤 |

### 可做（中價值，成本適中）

| 功能 | 價值說明 |
|---|---|
| **場次標籤（Tag）** | 場次可自訂標籤（如「週三例會」「過年」「小組賽」），清單頁可按標籤篩選，有固定牌局的人超有用 |
| **「今晚最大咖」跨局統計** | 某玩家若同時出現在多場（同一天），提供「今日跨場累計」快速摘要，不用自己加總 |
| **玩家 vs 玩家對戰紀錄** | 玩家詳情頁新增「與誰同場次數 / 同場時勝率」，兩人直接點看對戰成績，在固定班底中最有說服力 |
| **局次難度分類（大台 / 普通 / 小台）** | 每局依台數自動標色（例如：≥5 台 = 金色「大台」，1 台 = 灰色「小台」），明細頁一眼看出今晚牌型分布 |
| **負值封頂告警（止損模式）** | 開桌選項新增「封頂損失 N 元，達標後停止記局」，到達上限自動鎖定記局按鈕並提示，幫助自律 |
| **牌局倒計時 / 計時器** | 開桌後可選「這場打 X 圈」，App 計算剩餘局次提示，讓「幾點要結束」有依據 |

### 未來（長期、成本高或需雲端）

| 功能 | 價值說明 |
|---|---|
| **賽季制度** | 建立「賽季」跨多個月份、多場次的累計排行，讓固定班底有長期競爭動力 |
| **局次照片備忘** | 記局時可附拍一張牌面照片（存 base64 或 IndexedDB），重新回顧時看當時的牌型 |
| **多設備同步（PWA + 後端）** | 換手機或朋友想看同一場排名，目前只有 localStorage 無法跨設備 |
| **AI 牌運分析** | 跨場輸贏數據丟進 AI，生成「你的放槍高峰期在第 X 局後」「你最常胡幾台」等個性化洞察 |

---

## 6. 給 art-lead 的重點提示

以下是本輪新增功能需要視覺設計的部分，請 art-lead 補充對應規範：

### 需要設計的新元件 / 畫面

| 元件 / 畫面 | 說明 |
|---|---|
| **玩家頁 FAB 或新增按鈕** | 玩家頁現無新增入口，v2.1 需設計入口樣式（與牌局頁 FAB 風格統一或差異化） |
| **名冊玩家 vs 非名冊玩家** | 清單中區分「已加入名冊」與「歷史唯名字」玩家的視覺差異（建議：名冊成員顯示完整色條，歷史玩家淡化或虛線框） |
| **開桌規則區塊（Bottom Sheet）** | 自摸加台 Toggle + 數字輸入、東錢 Toggle + 金額輸入的排版，需與既有場名 / 玩家欄位設計風格一致 |
| **Toggle 開關元件** | 現有設計規範無 Toggle 規範，需定義 ON/OFF 狀態色（建議：ON 用 `--color-primary`，OFF 用 `--color-border`） |
| **規則提示 chip（開桌後排名條旁）** | 進入記局頁時，若有特殊規則開啟（自摸加台、東錢），在 RankBar 附近顯示規則 chip 提示（例如「自摸 +1 台」「東錢 $100」），讓玩家確認規則正確 |
| **「非名冊玩家 → 加入名冊」引導** | 玩家清單中，歷史唯名字玩家旁顯示「+ 加入名冊」小按鈕或 tooltip |

### 視覺一致性注意事項

- 規則 Toggle 的 ON 狀態語意：ON = 功能開啟 = 正向，使用 `--color-primary`（綠色），不用 `--color-win`（語意上「功能開啟」不等於「贏」）。
- 東錢金額輸入框：若東錢 Toggle 關閉，金額輸入框應 disabled（opacity 0.4），避免設了金額但未開啟的混淆。

---

## 7. 給 dev-lead 的重點提示

### 7-1. 技術風險 / 資料遷移問題

| 風險點 | 說明 | 建議 |
|---|---|---|
| **舊 Session 無 `rules` 欄位** | 現有所有 session 的 `rules` 為 undefined，需在讀取時補入預設值 | 在 `AppData` 的 localStorage 讀取層做一次 migration：讀出後若 `!session.rules`，補入 `DEFAULT_SESSION_RULES`（`selfDrawBonusTai: 0, eastMoney: 0`），不改 localStorage 原始資料 |
| **自摸加台改變舊場次計分** | 若 migration 預設錯誤地填入 `selfDrawBonusTai: 1`，會讓所有舊場次的自摸分數改變 | **強調**：`DEFAULT_SESSION_RULES.selfDrawBonusTai` 必須是 `0`，否則會破壞歷史資料正確性 |
| **東錢規則尚未確認** | CEO 尚未確認東錢機制，不可先實作計分邏輯 | 先實作 UI 選項與資料模型，計分邏輯等 CEO 確認規則後再寫 |
| **RosterPlayer UUID 生成** | `RosterPlayer.id` 需要全域唯一，localStorage 環境無後端生成 | 使用 `crypto.randomUUID()`（現代瀏覽器原生支援）或 `nanoid`（已在 v2 deps 中，確認一下） |
| **名字改了跨場統計會斷** | `RosterPlayer.name` 改動後，舊 session 的 `Player.name` 不同步，`aggregateByRosterId` 邏輯需以 `rosterId` 為主，不以名字 | `aggregateByRosterId(sessions, rosterId)` 要跨 session 找 `p.rosterId === rosterId`，不用名字比對 |
| **`scoreRound` 簽章擴充** | 新增 `rules?: SessionRules` 參數，呼叫端需更新（`scoreSession`、`buildCumulativeTimeline`、`calcSessionHighlights`、`aggregatePlayerStats` 都用到 `scoreRound`） | 參數設 optional，預設值 `undefined` = 舊行為，逐步更新呼叫端即可，不會一次全爆 |
| **名冊「同名＝同一人」（CEO 定案的已知限制）** | 名冊以名字為識別，不支援「同名不同人」：對同名未連結場次點「加入名冊」一律歸入既有同名成員，兩個現實中不同但同名的人會被合併計分 | `addRosterPlayer` 名字重複時回傳既有成員、不重複建立；`aggregateBy` 對每場 **加總所有符合座位**（同一場多個同名座位不漏帳）。日後若要支援同名不同人，須改以穩定 id 而非名字作識別 |

### 7-2. 建議實作順序

```
Phase A（不影響現有計分，可先做）：
  1. RosterPlayer 資料模型 + GlobalSettings.roster
  2. 玩家頁新增按鈕 + 建立名冊成員 Bottom Sheet
  3. 開桌時名冊選人（PlayersPage + NewSessionSheet 改動）
  4. Session.rules 資料模型 + localStorage migration（補 DEFAULT_SESSION_RULES）
  5. 開桌 Bottom Sheet 加入規則設定 UI（Toggle + 數字輸入）

Phase B（等 CEO 確認東錢規則後）：
  6. scoreRound 擴充（接受 rules 參數，實作自摸加台 + 東錢計算）
  7. scoreSession / buildCumulativeTimeline / calcSessionHighlights 更新呼叫端
  8. 進入記局頁後的「規則提示 chip」顯示

Phase C（後續體驗優化）：
  9. aggregateByRosterId（以 rosterId 聚合取代名字聚合）
  10. PlayerDetailPage 連結到 session（場次歷史點入跳轉）
  11. 玩家詳情頁「編輯名字」功能
```

### 7-3. `scoreRound` 擴充設計（供參考）

```ts
const DEFAULT_RULES: SessionRules = {
  selfDrawBonusTai: 0,
  eastMoney: 0,
};

export function scoreRound(
  round: Round,
  players: Player[],
  settings: Settings,
  rules: SessionRules = DEFAULT_RULES,  // 預設不加任何規則
): RoundDelta {
  assertValidSettings(settings);
  assertValidRound(round, players);

  const delta: RoundDelta = {};
  for (const p of players) delta[p.id] = 0;

  // 自摸加台：僅 selfDraw 時生效
  const effectiveTai = round.selfDraw
    ? round.tai + (rules.selfDrawBonusTai ?? 0)
    : round.tai;

  const amount = calcUnitAmount(settings, effectiveTai);

  if (round.selfDraw) {
    for (const p of players) {
      if (p.id === round.winnerId) {
        delta[p.id] += amount * (players.length - 1);
      } else {
        delta[p.id] -= amount;
      }
    }
    // 東錢：各家再多付一份（CEO 確認規則後補入）
    if (rules.eastMoney > 0) {
      for (const p of players) {
        if (p.id === round.winnerId) {
          delta[p.id] += rules.eastMoney * (players.length - 1);
        } else {
          delta[p.id] -= rules.eastMoney;
        }
      }
    }
  } else {
    delta[round.winnerId] += amount;
    delta[round.loserId as string] -= amount;
    // 放槍不收東錢（依建議提案；待 CEO 確認）
  }

  return delta;
}
```

---

## 8. 東錢規則確認清單（請 CEO 逐項回覆）

以下三個問題的答案會直接影響計分邏輯，dev-lead **等待 CEO 確認後才動工 Phase B**。

| # | 問題 | creative-lead 建議預設 | CEO 確認 |
|---|---|---|---|
| Q1 | 東錢金額是固定值（不隨台數變化），還是跟台數 × 某個倍率？ | 固定值，預設 100 元/份 | 待確認 |
| Q2 | 東錢由誰付？三家各付一份？還是只有特定角色（如東家、莊家）？ | 三家每人各付一份（最常見、最對稱） | 待確認 |
| Q3 | 放槍時是否收東錢？還是只有自摸才收？ | 只有自摸收東錢 | 待確認 |

---

## 9. 後續步驟

1. **CEO 確認東錢規則**（第 8 節三個問題）：這是 dev-lead Phase B 的前提。
2. **CEO 確認玩家名冊方向**：是否同意引入 `RosterPlayer`？或繼續維持以名字聚合（較簡單但有歧義）？
3. **art-lead 補充規範**：依第 6 節清單，補充 Toggle 元件、規則 chip、名冊相關視覺規範。
4. **dev-lead Phase A 開工**：在 CEO 確認模型方向後，Phase A 不涉及計分改動，可先行實作。
5. **QA 審查**：每個 Phase 完成後交 qa-reviewer 審查（含 Codex 第二意見），通過後方視為完成。
