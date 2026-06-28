# 麻將記分 App — 技術選型與架構說明

> 產品代號：**MahjongScore**（台灣麻將 16 張 記分工具）
> 對象：CEO 個人使用的網頁工具，未來會往原生 app 走。
> 本文件為第一版 MVP 的技術選型、架構、資料模型與範圍說明。

---

## 1. 一句話總結

用 **React + TypeScript + Vite + PWA**，資料先存瀏覽器本機（透過一層抽象的 repository），
計分邏輯抽成純 function（pure function）方便測試，未來要轉原生 app（React Native / Capacitor）或接雲端後端時都不用大改 UI。

---

## 2. 技術選型與理由

| 項目 | 選擇 | 理由 |
| --- | --- | --- |
| UI framework | **React 18 + TypeScript** | 生態最大、未來轉 **React Native** 可大量沿用觀念與部分邏輯；TypeScript 讓計分這種會出錯的邏輯有型別保護。 |
| 建置工具 | **Vite** | 啟動快、設定少、官方 PWA plugin 成熟，個人專案最省心。 |
| 跨平台路線 | **PWA（先）→ Capacitor / React Native（後）** | PWA 讓網頁現在就能「加到主畫面」像 app 一樣用；之後若要上架，**Capacitor** 可直接把這份 web code 包成原生殼，幾乎不用重寫；若要更原生體驗再走 React Native，屆時可重用 model 與計分純函式層。 |
| 樣式 | **原生 CSS（單一 `styles.css`）** | MVP 不引入 UI 套件，避免過度設計與相依膨脹。 |
| 資料儲存 | **localStorage（第一版）**，包在 `StorageRepository` 介面後面 | 個人工具、資料量小，localStorage 最簡單可靠且重整不遺失；介面抽象後，未來換 IndexedDB 或雲端 API 只要換一個實作，UI 不動。 |
| 狀態管理 | **React 內建（useState + 自訂 hook `useSessions`）** | MVP 規模不需要 Redux/Zustand，避免過度設計。 |

### 為什麼不直接用後端？
CEO 指定「不要架後端」。個人工具用本機儲存即可。重點是**資料層抽象**，所以我們定義了 `StorageRepository` interface（見 `src/data/`），
第一版是 `LocalStorageRepository`，未來要換成 `ApiRepository`（打雲端）或 `IndexedDbRepository` 時，UI 與 hook 完全不用改。

---

## 3. 目錄結構

```
apps/web/                      # 麻將記分網頁 app（獨立 npm 專案）
├─ index.html
├─ package.json
├─ tsconfig.json
├─ tsconfig.node.json
├─ vite.config.ts             # 含 PWA plugin 設定（manifest 由 vite-plugin-pwa 自動產生）
└─ src/                       # 註：MVP 尚未建立 public/，PWA manifest 與圖示由 plugin 於 build 時產出
   ├─ main.tsx                # entry
   ├─ App.tsx                 # 主畫面組裝
   ├─ styles.css
   ├─ types.ts                # 核心型別：Player / Round / Session / Settings
   ├─ scoring/
   │  ├─ scoring.ts           # 計分純函式（台灣 16 張規則）★核心
   │  └─ scoring.test.ts      # 計分單元測試（Vitest）
   ├─ data/
   │  ├─ repository.ts        # StorageRepository interface（資料層抽象）
   │  └─ localStorageRepository.ts  # 第一版本機實作
   ├─ hooks/
   │  └─ useSessions.ts       # 串接 repository 的 React hook
   └─ components/
      ├─ SettingsPanel.tsx    # 設定底/台、玩家名字
      ├─ RoundForm.tsx        # 逐局輸入（贏家/台數/自摸或放槍/放槍者）
      ├─ RoundList.tsx        # 每局明細
      └─ Standings.tsx        # 本場每人累計輸贏
```

說明：放在 `apps/web/` 是預留 monorepo 心智模型——未來要加 `apps/mobile/`（Capacitor 殼）或 `packages/core/`（共用計分邏輯）時結構自然。第一版只先有 `apps/web/`。

---

## 4. 資料模型（場 / 局 / 玩家 / 計分）

定義在 `src/types.ts`：

```ts
// 玩家：MVP 固定 4 人，名字可改
interface Player {
  id: string;       // 'p1' | 'p2' | 'p3' | 'p4'
  name: string;
}

// 金額設定
interface Settings {
  base: number;     // 底
  tai: number;      // 每台金額
}

// 一局
interface Round {
  id: string;
  winnerId: string;         // 贏家 player id
  tai: number;              // 台數（預留：未來莊家/連莊加台也是疊在這欄）
  selfDraw: boolean;        // true=自摸；false=胡牌(放槍)
  loserId: string | null;   // 放槍者 id；自摸時為 null
  createdAt: number;
}

// 一場牌局
interface Session {
  id: string;
  name: string;             // 場名（例：2026/06/27 晚場）
  players: Player[];        // 4 人
  settings: Settings;       // 該場的底/台
  rounds: Round[];
  createdAt: number;
}
```

統計（誰最會贏／總輸贏）只是把 `rounds` 餵進計分函式再加總，資料結構已足夠支撐，列為之後的 TODO。

---

## 5. 計分規則（台灣麻將 16 張，預設值可調）

實作於 `src/scoring/scoring.ts`，為**純函式**，輸入一局 + 設定 → 輸出每位玩家該局的 +/- 金額。

- 單注金額 `amount = base + tai × settings.tai`（底 + 台數 × 每台金額）。
- **自摸（selfDraw = true）**：其他三家每人各付 `amount`，贏家收 `3 × amount`。
- **放槍（selfDraw = false）**：只有放槍者付 `amount`，贏家收 `amount`，另兩家 0。
- 全場每人累計 = 各局該玩家金額相加。
- 莊家/連莊加台：**MVP 不自動算**，但台數欄位 `tai` 已預留，使用者可自行把加台數加進去。

> 規則來源：台灣常見家庭/朋友局慣例。金額（底、台）與台數皆可由使用者調整，規則細節寫在 `scoring.ts` 註解。

---

## 6. 第一版 MVP 範圍

✅ 本版要做：
- 設定底/台金額與 4 位玩家名字。
- 建立 / 切換 / 刪除一場牌局（session）。
- 逐局輸入：贏家、台數、自摸或放槍、放槍者，按下新增即自動算分。
- 顯示每局明細（可刪除單局）。
- 顯示本場每人累計輸贏（standings）。
- 資料存 localStorage，重整不遺失。
- 計分純函式有 Vitest 單元測試。

🚫 本版不做（列為 TODO）：
- 莊家/連莊自動加台、花牌、詐胡等進階規則。
- 跨場歷史統計報表（誰最會贏、長期總輸贏）。
- 雲端同步、多人協作、登入。
- 原生 app 打包（Capacitor / React Native）。
- **逐 round 丟棄毀損資料**：目前 `LocalStorageRepository.loadSessions` 採粗粒度策略——只要某個 session 內有一筆 round 毀損，就整個 session 丟棄（並備份原始內容到 quarantine key、用 `console.error` 記下被丟棄的 session id/name）。未來可改成只剔除毀損的 round、保留同場其餘可用 round，降低資料損失。

---

## 7. 怎麼啟動

需要 Node.js（建議 18+，本機實測 v24）。

```bash
cd apps/web
npm install
npm run dev      # 開發伺服器，預設 http://localhost:5173
```

其他指令：

```bash
npm run build    # 產生 production build 到 dist/
npm run preview  # 預覽 build 結果
npm run test     # 跑計分單元測試（Vitest）
```

---

## 8. 未來轉原生 app 的路徑（備忘）

1. **最省力**：在 `apps/web` 之外加 Capacitor，把目前的 web build 直接包成 iOS/Android 殼，計分與資料層完全沿用。
2. **更原生**：開 `apps/mobile`（React Native），重用 `src/scoring`（純 TS，無 DOM 相依）與 `src/types.ts`，重寫 UI 層。
3. **接雲端**：新增 `ApiRepository implements StorageRepository`，在 app 啟動時切換實作，UI / hook 不動。

這也是為什麼第一版就把「計分」與「資料存取」從 UI 切乾淨。
