# MahjongScore（MaJong）— 企劃 vs 程式碼 實作狀態盤點

> 盤點人：dev-lead（唯讀盤點，機會清單 M1「企劃與程式碼無對帳紀錄」）
> 日期：2026-08-10
> 盤點基準：分支 `mahjongapp` @ `c4d7fa5`
> 對帳來源：`work/mahjong-app-架構.md`、`work/mahjong-app-v2-企劃.md`、`work/mahjong-app-v2-視覺規範.md`、`work/mahjong-app-回饋輪企劃.md` vs `apps/web/` 實際程式碼（26 個 commits）

---

## 0. 結論摘要

- **企劃列出的功能完成度約 85%**：MVP 與 v2「必做」13 項全數完成；v2.x「可做」約 7/10；回饋輪企劃（v2.1）主體（名冊、開桌規則、自摸加台、東錢）全數完成，且東錢已由 CEO 定案為「公基金（kitty）」機制實作。
- **反向缺口更大**：程式碼有 **8 個以上的大型功能批次完全沒有企劃文件紀錄**（眼牌、連莊/圈風/流局、中途換人、備份匯入、結算儀式頁、數據系統 A/B、快速記局改版、頭像系統），這些功能的規則定案（多為「CEO 拍板」）只存在於 commit message 與程式碼註解中。
- **測試現況良好**：8 個測試檔、220 個測試全數通過（2026-08-10 實測，Vitest 2.x）。測試集中在計分/資料層純函式；UI 層（pages/components）零測試、無 E2E。

---

## 1. 逐功能對帳表

圖例：✅ 已完成｜🟡 部分完成/變形實作｜❌ 未實作｜⭐ 程式有、企劃無紀錄

### 1-1. MVP（`mahjong-app-架構.md`）

| 功能 | 狀態 | 程式碼對應 |
|---|---|---|
| 底/台設定、4 玩家名字 | ✅ | `SettingsPanel.tsx`、`Session.settings` |
| 建立/切換/刪除牌局 | ✅ | `SessionsPage.tsx`、`useSessions.ts` |
| 逐局輸入（贏家/台數/自摸/放槍者） | ✅ | `RoundForm.tsx`（已改版為快速記局，見 3-7） |
| 每局明細（可刪單局） | ✅ | `RoundList.tsx` |
| 本場累計 standings | ✅ | `Standings.tsx`、`scoreSession` |
| localStorage 持久化 | ✅ | `localStorageRepository.ts`（+quarantine 備援） |
| 計分純函式 + Vitest 測試 | ✅ | `scoring/scoring.ts` + 492 行測試 |
| PWA | ✅ | `vite.config.ts`（vite-plugin-pwa） |

### 1-2. v2 必做（`mahjong-app-v2-企劃.md` §4）

| 功能 | 狀態 | 程式碼對應 / 備註 |
|---|---|---|
| Splash Screen（min-display-time） | ✅ | `Splash.tsx`（品牌已定名 MaJong） |
| 底部 Tab Bar + 路由 | ✅ | `TabBar.tsx`、`App.tsx`（react-router-dom v6，採企劃首選） |
| 牌局清單（卡片、冠軍、選單） | ✅ | `SessionsPage.tsx` |
| 新增牌局 FAB + Bottom Sheet | ✅ | `Fab.tsx`、`BottomSheet.tsx`（含 portal 修復 b60ab69） |
| 牌局詳情三子頁籤（記局/走勢/明細） | ✅ | `SessionDetailPage.tsx` |
| 即時排名條 | ✅ | `RankBar.tsx`（含 rolling number、winner-flash、警戒線） |
| 分數走勢折線圖 + Tooltip | ✅ | `ScoreChart.tsx`（React.lazy 動態載入 recharts，照企劃技術風險建議）、`buildCumulativeTimeline` |
| 玩家頁基礎統計 | ✅ | `PlayersPage.tsx`、`aggregatePlayerStats` |
| 設定頁全域預設 | ✅ | `SettingsPage.tsx`、`GlobalSettings` |
| 常用玩家快速帶入 | ✅ | `knownPlayers` → v2.1 起改由名冊 chips 帶入 |
| 資料匯出（JSON） | ✅ | `backup.ts`（且超出企劃：匯入也做了，見 3-4） |
| 左滑刪除局次 | 🟡 | `RoundList.tsx` 用刪除鈕＋確認，**無 swipe 手勢**（功能等價、UX 未照企劃） |

### 1-3. v2.x 可做 + 創意延伸（v2 企劃 §4/§5）

| 功能 | 狀態 | 備註 |
|---|---|---|
| 結算時間戳 + 結算本場鈕 | ✅ | `Session.endedAt`、SessionDetailPage（可取消結算） |
| 玩家詳情跨場走勢圖 | ✅ | `PlayerDetailPage.tsx` |
| 莊家/連莊自動加台 | ✅ | 超出企劃範圍：完整圈風/連莊系統（見 3-2） |
| 圖例點擊隱藏玩家線 | ✅ | `ScoreChartInner.tsx`（hidden set + toggle） |
| 本場統計摘要（胡/自摸/放槍） | ✅ | `calcSessionHighlights.perPlayer` |
| 圖表局次範圍拖曳篩選 | ❌ | 未實作 |
| 牌局搜尋/篩選 | ❌ | SessionsPage 無搜尋（玩家頁有） |
| 暗黑模式切換 | 🟡 | 全 App 僅深色主題（視覺規範以 dark 為主、light「預留」）；無 light mode、無切換 |
| PWA 推播提醒 | ❌ | 未實作 |
| 5-1 結算分享圖卡 | ✅ | `ShareCard.tsx`（html2canvas 動態載入、PNG 下載） |
| 5-2 趣味統計標籤 | ✅ | `Highlight`：冠軍/放槍王/自摸王/最慘烈一局＋**企劃外加「最快一局」**（smallestRound） |
| 5-3 排名變化動畫 | ✅ | RankBar rolling number + winner-flash（註解自承實作待重構） |
| 5-4 快速輸入模式 | 🟡 | 已做且**直接取代**表單（企劃原設計為「切換鈕」雙模式）＋台數滑桿粗調（企劃外） |
| 5-5 玩家手氣分析 | ✅ | 近 5 場均、勝率、連贏/連輸、Sparkline（`PlayerStats`） |
| 5-6 局次備註 | ✅ | `Round.note`（20 字上限） |
| 長期 backlog（雲端同步/語音/賽季/Capacitor…） | ❌ | 依企劃預期未排入；成就徽章已部分被「稱號系統」覆蓋（見 3-6） |

### 1-4. 回饋輪企劃 v2.1（`mahjong-app-回饋輪企劃.md`）

| 功能 | 狀態 | 備註 |
|---|---|---|
| 玩家名冊 RosterPlayer + rosterId 連結 | ✅ | `types.ts`、`useSessions.roster.test.ts`；同名＝同一人限制照 CEO 定案實作 |
| 玩家頁新增/搜尋/排序 | ✅ | PlayersPage：新增 Sheet、搜尋框、三種排序 |
| 非名冊玩家標示＋加入名冊 | ✅ | `aggregateUnlinkedByName` + 名字聚合 fallback |
| 玩家詳情編輯名字 | ✅ | 數據系統批次 A 補上 |
| 開桌從名冊選人 | ✅ | NewSessionSheet 頭像 chips |
| SessionRules + 全域 defaultRules + migration 補 0 | ✅ | `DEFAULT_SESSION_RULES` 全 0、`DEFAULT_NEW_SESSION_RULES` 照 CEO 定案 |
| 自摸加台（預設 1） | ✅ | `effectiveTai`，測試齊 |
| 東錢 | ✅⭐ | **實作機制與企劃提案不同**：企劃提案「三家各付給贏家」；CEO 定案為「自摸者單向付入公基金 kitty，不入零和」（`calcDong`、`SessionHighlights.kitty`）。定案僅記於程式註解，企劃文件第 8 節三個問題仍寫「待確認」，**未回寫** |
| 進場規則提示 chip | ✅ | SessionDetailPage：自摸/東錢/眼牌/連莊 chips |
| 場中改規則（含警示） | ✅ | `RulesFields.tsx` + SettingsPanel 擴充 |
| 新一批發想：emoji 頭像 | ✅⭐ | 升級為 9 張 PNG 頭像系統（企劃只提 emoji） |
| 快速重開同組牌局 | ✅ | Sessions/SessionDetail/Settle 皆有「再開一場」 |
| 最快結束局統計 | ✅ | smallestRound highlight |
| 匯率換算（平均底台/台數） | ✅ | `avgRoundAmount` / `avgTai` |
| 輸贏警戒線 | ✅ | `loseAlertThreshold` + RankBar 紅色警示 |
| 放槍者標記警示 | ✅ | RoundForm 放槍達門檻警示 |
| 場次標籤 Tag / 今晚最大咖 / 難度分類 / 止損封頂 / 計時器 | ❌ | 「可做」層級皆未實作 |
| 玩家 vs 玩家對戰紀錄 | ✅ | 冤家榜 `selectRivalBoard` / `EnemyEntry`（數據系統批次 B） |

---

## 2. 做了但企劃沒記錄（⭐ 反向缺口，M1 核心發現）

以下功能**只存在於 commit message 與程式碼註解**，四份企劃文件皆無對應章節；其中多項含「CEO 拍板」的計分規則定案，屬於應留痕的產品決策：

| # | 功能批次 | Commit | 程式碼 | 未留痕的關鍵決策 |
|---|---|---|---|---|
| 3-1 | **眼牌（加台制）** | f24bb40 | `Round.eyeTile`、`rules.eyeTileEnabled/eyeTileTai`、`calcEyeTileTai` | CEO 拍板：加 1 台、自摸/放槍都算、預設開 |
| 3-2 | **連莊 / 圈風 / 流局系統** | 01c51d4 | `dealer.ts`（deriveTableState）、`Round.drawn`、`Session.dealerStartSeat` | CEO 拍板：做莊 1 台、連 N 拉 N＝2N 台、只加在牽涉莊家的支付；流局採方案 A（winnerId=''） |
| 3-3 | **中途換人（座位時間軸）** | b500512 | `Substitution`、`substitution.ts`（seatOccupantAt）、`SubstitutionPanel.tsx` | CEO 拍板：只換人不換位、接手者自成一帳 |
| 3-4 | **備份匯入 + 原子寫入** | c4d7fa5、47c9edf | `backup.ts`（validateBackup/parseBackupText）、SettingsPage 匯入流程 | 企劃只列「匯出」；匯入格式版本（BACKUP_VERSION 'v2'）、覆蓋語意、rollback 皆無企劃 |
| 3-5 | **結算儀式頁（P6）** | 8f879e5 | `SettlePage.tsx`、路由 `/sessions/:id/settle` | 全螢幕結算動線、Highlights 徽章化、圖卡整合 |
| 3-6 | **數據系統批次 A/B** | 0efd4f5、9f6eecd | `computePlayerTitles`（5 種稱號）、`trendDirection`、`rateWithThreshold`、冤家榜、三率卡、結算快照 | 稱號門檻與演算法無企劃 |
| 3-7 | **快速記局取代表單 + 台數滑桿** | 74a28df、b8e40df | `RoundForm.tsx` 重寫 | 企劃 5-4 是「可切換的快速模式」，實作為唯一輸入方式；滑桿粗調、送出歸零、台數不封頂 |
| 3-8 | **頭像系統（PNG）+ MaJong 品牌定名** | f71abeb、f43785b | `PlayerAvatar.tsx`、`public/avatars/`、`assets/avatars` | 品牌名 MaJong、9 張頭像資產無 art brief 歸檔對應 |
| 3-9 | 資料毀損防護（quarantine + ErrorBoundary） | 47c9edf 等 | `localStorageRepository.ts`、`ErrorBoundary.tsx` | 架構文件僅在 TODO 提過粗粒度策略，現況已進化（可選欄位 null 寬容、備份保證） |

**東錢定案未回寫**（1-4 表已述）也屬此類：`回饋輪企劃.md` §8 的三個「待 CEO 確認」問題實際已定案且已實作，文件仍停在「待確認」。

---

## 3. 半成品 / 已知妥協

| 項目 | 現況 | 位置 |
|---|---|---|
| RankBar rolling number 實作方式 | 程式註解自承「待辦另立獨立任務改用穩定作法」 | `RankBar.tsx` 頂部註解 |
| 左滑刪除 | 以刪除鈕替代，swipe 手勢未做 | `RoundList.tsx` |
| 快速輸入雙模式 | 只有快速模式，舊表單已移除（若 CEO 想要精細輸入需回頭補） | `RoundForm.tsx` |
| Light mode | 視覺規範預留章節（§2-3），程式零實作 | `styles.css` |
| `dealerTaiScope: 'table'` | 型別預留但 UI 不開放切換 | `types.ts` |
| 同名＝同一人 | CEO 定案的已知限制（企劃有記），日後支援同名不同人需改識別鍵 | 回饋輪企劃 §7-1 |

---

## 4. 測試現況（2026-08-10 實測）

```
指令：cd apps/web && npx vitest run
結果：Test Files 8 passed (8)｜Tests 220 passed (220)｜Duration ~1.9s
```

| 測試檔 | 測試數 | 覆蓋範圍 |
|---|---|---|
| `scoring/scoring.test.ts` | —（與 repository 合計 81） | 計分：底台、自摸/放槍、規則疊加、零和驗算 |
| `scoring/timeline.test.ts` | 56 | 走勢、highlights、聚合、稱號、冤家榜 |
| `scoring/dealer.test.ts` | 18 | 圈風/連莊/流局推導 |
| `scoring/substitution.test.ts` | 19 | 換人座位時間軸 |
| `data/localStorageRepository.test.ts` | —（同上合計 81） | 持久化、migration、毀損隔離 |
| `data/backup.test.ts` | 31 | 匯出/匯入驗證 |
| `hooks/useSessions.*.test.ts` | 15 | 名冊、刪局 |

**缺口**：pages / components（UI 層）零單元測試；無 E2E（章程要求 UI 需 qa-e2e 實機驗收，本盤點未見驗收紀錄檔）；`npm run build`（tsc + vite）未納入本次唯讀盤點驗證。

---

## 5. 建議下一步（優先級）

| 優先 | 事項 | 理由 |
|---|---|---|
| **P0** | 把 3-1～3-3 的「CEO 拍板」計分規則回寫成正式規則文件（或補一份《牌桌規則定案書》），並回寫回饋輪企劃 §8 東錢定案 | 計分規則是本產品正確性核心，目前唯一出處是程式註解，換人接手或改寫即失傳 |
| **P1** | 建立本對帳表的維護機制：每個功能批次 merge 時同步更新（可入 handoff-protocol 的 done 條件） | M1 的根因是「企劃與程式碼無對帳紀錄」，一次性盤點會再次過期 |
| **P1** | RankBar rolling number 重構還債（程式內自留待辦） | 已知技術債，實作者自己標記不穩 |
| **P2** | 決策：快速輸入是否需要保留精細表單模式；左滑刪除是否還要做 | 兩處實作與企劃有意識偏離，需 CEO 認可或補做 |
| **P2** | UI 層測試補強（至少 SettlePage / 匯入流程的整合測試）＋ qa-e2e 實機驗收留痕 | 220 測試全在純函式層，UI 迴歸風險裸奔 |
| **P3** | 未做清單排期或明確棄案：圖表範圍篩選、牌局搜尋、場次 Tag、止損封頂、Light mode、PWA 提醒 | 避免「企劃列了但沒人知道是棄案還是排隊中」 |

---

## 6. 驗證方式

- 企劃四份文件逐節與 `apps/web/src` 全目錄（10,582 行）交叉比對；功能狀態以實際程式碼為準，非以 commit message 為準。
- 測試以 `npx vitest run` 實跑（220/220 綠）。
- 本盤點為唯讀作業，除本文件與 `work/.gitignore` 放行外未動任何程式碼。
