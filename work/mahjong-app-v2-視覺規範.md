# MahjongScore v2 — 美術方向與視覺規範

> 文件類型：Art Brief / Style Guide
> 作者：art-lead
> 日期：2026-06-28
> 配合企劃：`work/mahjong-app-v2-企劃.md`（creative-lead 出品）
> 服務對象：dev-lead（CSS 實作參考）、未來 image 模型（插圖 / 圖示出圖）

---

## 1. 整體風格定位

### 五個定調關鍵詞

**沉穩牌桌綠 · 暗夜質感 · 數字清晰 · 台式溫度 · 耐看簡潔**

### 為什麼這樣定調？

| 關鍵詞 | 理由 |
|---|---|
| 沉穩牌桌綠 | 現有 `#1f6f43` 是很好的文化錨點，象徵台灣麻將桌布，有識別度且不突兀，沿用並強化 |
| 暗夜質感 | 麻將通常在室內、晚間打；深底色護眼，長期使用不疲勞；個人工具 dark mode 優先是合理決策 |
| 數字清晰 | 記分 app 的核心是「正確讀出金額」，所有字級、對比、字體設計都以數字的可讀性為最高優先 |
| 台式溫度 | 不是賭場 LED 感，也不是極簡科技感——帶一點人情味的個性，靠偏暖的輔助色（金色點綴）達到，不靠插圖堆砌 |
| 耐看簡潔 | 個人工具長期使用，過度裝飾會疲勞；元件乾淨、空白充足、視覺階層分明，才是長跑設計 |

### 要刻意避免的方向

- 賭場 neon 霓虹感（太刺眼、廉價）
- 大紅大金（台灣喜慶感很強，容易有廉價牌坊聯想）
- 過白的 light mode 主場景（輸贏金額頻繁出現紅綠，白底更刺眼）
- 繁複陰影疊加（扁平 + 微陰影即可，不需要 neumorphism 等重質感）

---

## 2. 色彩系統

### 2-1. 整體設計決策

**主場景採 Dark Mode**，Light Mode 為備用。理由：v1 已是暗色系，使用者（CEO）長期使用已習慣；記分在晚間打牌現場使用，暗色護眼；轉原生 app 後暗色在 iOS / Android 都有良好支援。

---

### 2-2. Dark Mode 色票（主要）

#### 背景色階（Background Scale）

| 用途 | Token 名稱 | Hex | 說明 |
|---|---|---|---|
| 最底層頁面背景 | `--color-bg` | `#0d1510` | v1 的 `#0f1410` 稍微更暗、偏冷綠，更沉穩 |
| 卡片 / 底部 sheet 背景 | `--color-surface` | `#17211a` | 接近 v1 的 `#18211b`，小幅調整統一 |
| 輸入框 / 行內欄位背景 | `--color-surface-low` | `#0f1a12` | 比 surface 再暗一階，用於 input 凹陷感 |
| 分隔線 / 邊框 | `--color-border` | `#253328` | 接近 v1 `#2a3a30`，稍微降飽和度 |
| Splash 全畫面背景 | `--color-splash-bg` | `#0a1209` | 最深，讓 Logo 浮出感最強 |

#### 文字色階（Text Scale）

| 用途 | Token 名稱 | Hex | 對比比（vs `--color-bg`）|
|---|---|---|---|
| 主文字 | `--color-text` | `#e4ede7` | ≥ 11:1（AAA） |
| 次要文字 / 說明 | `--color-text-secondary` | `#8a9e90` | ≥ 4.5:1（AA） |
| 停用 / 佔位文字 | `--color-text-disabled` | `#4a5e50` | 僅裝飾用，不承載資訊 |

#### 品牌色（Brand Color）

| 用途 | Token 名稱 | Hex | 說明 |
|---|---|---|---|
| 主品牌色 / CTA 按鈕 / Tab 選中 | `--color-primary` | `#1f6f43` | 沿用現有，不改動 |
| Primary Hover / 深壓 | `--color-primary-dark` | `#185534` | 按鈕 hover 態 |
| Primary 淡化背景（選中 tab 底色 chip） | `--color-primary-muted` | `#1a3d29` | 12% opacity 的 primary |

#### 語意色（Semantic Color）

**台灣麻將語意規則說明**：
台灣習俗中，「紅色」代表喜氣、贏錢是好事。但本 App 同時要顯示輸（負值）和贏（正值），且圖表已使用紅色作為某位玩家代表色，語意混淆風險高。設計決策如下：

- **贏（正值）= 綠色**：綠色是牌桌色，App 原生主色調，代表「穩、贏、好」；且和傳統「紅字」相比，綠色在暗底上對比更舒適，適合長期閱讀。
- **輸（負值）= 紅色**：紅色雖然傳統有喜氣，但在「虧損金融數字」的脈絡下，台灣使用者已普遍接受「紅字代表虧損」（證券 App、記帳 App 皆如此）。在記分工具的金融語意框架下，紅色表示輸不會造成混淆。
- **此原則全 App 貫穿，不可例外**。

| 語意 | Token 名稱 | Hex | 使用場合 |
|---|---|---|---|
| 贏 / 正值 / 成功 | `--color-win` | `#34c47a` | 正數金額、成功確認、胡牌標示；比 v1 `#38c172` 稍微偏冷更融入整體 |
| 輸 / 負值 / 警示 | `--color-lose` | `#f05252` | 負數金額、放槍標示；比 v1 `#ef5350` 稍微降飽和降亮 |
| 中性 / 持平 | `--color-neutral` | `--color-text-secondary` | 零值、未變化的數字 |
| 警告 / 注意 | `--color-warn` | `#d4a030` | 刪除確認、資料風險提示 |
| 資訊 | `--color-info` | `#4a9eca` | 規則說明、空狀態提示 |

#### 強調色（Accent）

| 用途 | Token 名稱 | Hex | 說明 |
|---|---|---|---|
| 金色點綴（冠軍、MVP 標籤） | `--color-gold` | `#c9a535` | 克制使用，只用於「第一名」「趣味標籤獎牌」等少數場合 |
| 銀色（第二名） | `--color-silver` | `#8f9fa3` | 玩家排名標示用 |
| 銅色（第三名） | `--color-bronze` | `#a0654a` | 玩家排名標示用 |

---

### 2-3. Light Mode 方向（預留，v2.x 實作）

Light Mode **不是直接反色**，需重新定義背景色階：

| Token | Light Mode Hex | 說明 |
|---|---|---|
| `--color-bg` | `#f5f7f5` | 帶一點綠調的米白，不刺眼 |
| `--color-surface` | `#ffffff` | 純白卡片 |
| `--color-border` | `#d4ddd6` | 淺灰綠分隔線 |
| `--color-text` | `#1a2a1f` | 深墨綠字，比純黑更有品牌調性 |
| `--color-text-secondary` | `#5a7060` | 中等對比 |
| `--color-primary` | `#1f6f43` | 沿用，light mode 主色不變 |
| `--color-win` | `#1a8f52` | 深化綠色以維持 light mode 對比 |
| `--color-lose` | `#d63b3b` | 深化紅色 |

> dev-lead 實作時用 `@media (prefers-color-scheme: light)` 或 `data-theme="light"` attribute 切換。

---

## 3. 四位玩家代表色（折線圖）

### 設計原則

1. **色盲友善**：避免僅靠紅/綠區分（紅綠色盲最常見）；使用色相距離夠大、亮度也有差異的組合。
2. **在暗底 `#0d1510` 上清晰可辨**：飽和度偏中高，亮度要夠亮（明度 L* > 55 in LCH）。
3. **不與語意色混淆**：玩家色不能和 `--color-win`（綠）、`--color-lose`（紅）、`--color-warn`（金黃）主色相太近。
4. **線條粗細 2.5px 時仍清晰**：在 375px 寬的手機螢幕折線圖上辨識無誤。

### 玩家代表色

| 玩家 | Token 名稱 | Hex | LCH 近似 | 色相描述 |
|---|---|---|---|---|
| 玩家 A | `--color-player-a` | `#5b9cf6` | L≈65 C≈60 H≈270 | 天藍（鮮明、辨識度最高） |
| 玩家 B | `--color-player-b` | `#f6c55b` | L≈82 C≈65 H≈80` | 鮮黃橙（亮、與藍形成最強對比） |
| 玩家 C | `--color-player-c` | `#c47ef5` | L≈62 C≈68 H≈295` | 紫色（對紅綠色盲者與藍色亦可區分） |
| 玩家 D | `--color-player-d` | `#5bcfc4` | L≈75 C≈42 H≈192` | 青綠（中性、不與 --color-win 的黃綠衝突） |

### 色盲友善驗證說明

- 紅綠色盲（Deuteranopia / Protanopia）：藍 / 黃 / 紫 / 青 四色在色盲模擬下仍可區分，因色相分布避開了紅綠軸。
- 全色盲（Achromatopsia）：亮度差異足夠（L: 65 / 82 / 62 / 75），灰階下仍可辨識相對順序。
- dev-lead 實作時，折線末端加上玩家名稱 label 或圖例，確保不只靠顏色傳遞資訊（accessibility 要求）。

### 玩家色的延伸用途

- 排名條（即時排名）：玩家名字欄左側 4px 色條，使用對應玩家色。
- 玩家頁卡片：左側 3px border-left 色條。
- Sparkline 小圖：使用對應玩家色。
- 圖例 pill：玩家色填底，白色文字。

---

## 4. 字體與排版

### 4-1. 字體堆疊

```css
font-family: -apple-system, "SF Pro Text", "Helvetica Neue",
             "Noto Sans TC", "PingFang TC", "Microsoft JhengHei",
             system-ui, sans-serif;
```

- 優先使用裝置系統字（iOS 用 SF Pro / PingFang TC，Android 用 Roboto / Noto Sans TC）。
- 不引入額外 web font，減少首次載入耗時（記分 app 用戶不會欣賞字體差異，但會感受到載入速度）。

### 4-2. 數字字體（關鍵）

**金額與分數必須使用 Tabular Nums（等寬數字）**，確保上下對齊。

```css
.score-number,
.amount,
.tabular {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}
```

- 金額欄、排名條分數、折線圖軸標籤、明細欄位：一律加上此 class 或 CSS property。
- 正負號一律顯示：`+1,200` / `-800`；零顯示 `0`（不顯示 `+0`）。
- 金額 ≥ 1000 加千位分隔符（逗號），例如 `+12,500`。

### 4-3. 字級階層（Type Scale）

| 層級 | 用途 | Size | Weight | Line Height |
|---|---|---|---|---|
| Display | Splash 品牌主標「麻將記分」 | 32px / 2rem | 700 | 1.2 |
| H1 | 頁面標題（牌局、玩家、設定） | 24px / 1.5rem | 700 | 1.3 |
| H2 | 卡片標題、子頁籤大標 | 18px / 1.125rem | 600 | 1.3 |
| H3 | 區塊小標、表單 label | 14px / 0.875rem | 500 | 1.4 |
| Body | 一般說明文字 | 15px / 0.9375rem | 400 | 1.5 |
| Caption | 日期、次要資訊、說明 | 13px / 0.8125rem | 400 | 1.4 |
| Micro | 備註、Tooltip 細節 | 11px / 0.6875rem | 400 | 1.4 |
| Score-Large | 排名條大金額、結算總額 | 28px / 1.75rem | 700 | 1.1 |
| Score-Medium | 每局金額、折線圖 label | 17px / 1.0625rem | 600 | 1.2 |

### 4-4. 金額 / 分數呈現規則

1. **正值**：`+1,500` ——色彩用 `--color-win`，font-weight: 700。
2. **負值**：`-800` ——色彩用 `--color-lose`，font-weight: 700。
3. **零值**：`0` ——色彩用 `--color-text-secondary`，font-weight: 400（視覺上退縮，不搶眼）。
4. **進行中累計**：排名條顯示即時累計，數字對齊右側。
5. **結算頁**：金額文字放大到 Score-Large（28px），搭配玩家名稱（Body 15px）。
6. **折線圖 Y 軸**：輕量 Caption（13px）、`--color-text-secondary` 色、不加 +/- 符號（只顯示數值，正值在 0 線上方已有視覺位置提示）。

---

## 5. Splash / 載入畫面

### 5-1. 視覺概念

**定調**：沉穩入場，不張揚。像掀開牌桌布的一刻——安靜、有分量。

**背景**：全畫面 `--color-splash-bg`（`#0a1209`），最深調，讓 Logo 浮現感最強。

**Logo 構成**：
- 主圖示：一張麻將牌的正面簡化圖示（方形圓角輪廓，內有「麻」字或抽象牌面線條），線條寬度 2px，填色 `--color-primary`（`#1f6f43`）加一層薄薄的金色描邊光 `--color-gold`（`#c9a535`，5% opacity glow 即可，不要刺眼）。
- 字體標誌：「麻將記分」四字，Display 字級（32px），font-weight 700，`--color-text`（`#e4ede7`）。
- 副標：「台灣麻將 · 個人記分工具」，Caption 字級（13px），`--color-text-secondary`（`#8a9e90`），字間距 0.08em 增加空氣感。

**版面佈局（垂直居中）**：
```
[全畫面 #0a1209]

          ┌──────────┐
          │  麻將牌   │   ← 圖示 72×72px，四角圓角 12px
          │  圖示區   │     描邊 #1f6f43，內填 #17211a
          └──────────┘

         麻  將  記  分     ← 32px, weight 700, #e4ede7

     台灣麻將 · 個人記分工具  ← 13px, #8a9e90, letter-spacing 0.08em
```

**動態時序**：
- T=0ms：`--color-splash-bg` 全屏出現（無動畫，瞬間黑屏比白屏好）
- T=0～400ms：圖示從 scale(0.85) + opacity(0) → scale(1) + opacity(1)，easing: `cubic-bezier(0.16, 1, 0.3, 1)`（spring 感）
- T=400～700ms：主標「麻將記分」從 opacity(0) + translateY(6px) → opacity(1) + translateY(0)
- T=600～900ms：副標漸入，同樣 translateY(6px) → 0
- T=1500ms：整體 Splash 元素 opacity(1) → opacity(0)，duration 300ms，淡出進入主畫面
- **最短顯示時間**：1500ms（資料讀取比這快也要等足）

**不要的動畫**：旋轉、bounce、色彩爆炸、粒子特效。一律拒絕。

---

## 6. 底部頁籤（Tab Bar）

### 6-1. Tab Bar 外觀

```
[--color-surface #17211a 底色]
┌─────────────────────────────────┐
│  [ 牌局 ]   [ 玩家 ]   [ 設定 ] │
│   ████       ○          ○      │  ← active 有色，inactive 灰
└─────────────────────────────────┘
```

- 高度：56px（iOS safe area 以上），含 padding-bottom 適配 Home Indicator（iOS：`env(safe-area-inset-bottom)`）。
- 底部加一條 `1px solid --color-border` 分隔主內容區（分隔線放在 Tab Bar 上方）。
- Tab Bar 背景：`--color-surface`（`#17211a`），加 `backdrop-filter: blur(12px)` 搭配 `background-color: rgba(23,33,26,0.92)` 做半透明毛玻璃效果（iOS 原生感）。

### 6-2. 三個 Tab 的圖示方向

| Tab | 中文名 | 圖示建議 | 語意說明 |
|---|---|---|---|
| Tab 1 | 牌局 | 麻將牌（一張方形圓角牌，側視角）| 最直接對應「牌局」概念 |
| Tab 2 | 玩家 | 人像半身輪廓（單人圖示）| 標準 profile icon，清楚易懂 |
| Tab 3 | 設定 | 齒輪（gear）| 通用設定圖示，不需要創意 |

圖示尺寸：24×24px SVG，stroke-width 1.5px。

### 6-3. 選中 / 未選中狀態

| 狀態 | 圖示色 | 文字色 | 文字字級 | 額外處理 |
|---|---|---|---|---|
| Active（選中）| `--color-primary` `#1f6f43` | `--color-primary` | 11px weight 600 | 圖示下方加 4px 高、24px 寬的 pill 底色（`--color-primary-muted` `#1a3d29`），圓角 2px |
| Inactive（未選中）| `--color-text-disabled` `#4a5e50` | `--color-text-disabled` | 11px weight 400 | 無底色 |
| Pressed（觸碰瞬間）| `--color-primary` | `--color-primary` | — | scale(0.92) duration 80ms，手感反饋 |

### 6-4. Tab 切換動畫

- 頁面切換：**fade（opacity 0→1，duration 150ms）**，不用 slide（避免和 push 到詳情頁的 slide 動畫混淆）。
- 圖示色變化：`transition: color 120ms ease`。

---

## 7. 關鍵畫面視覺指引

### 7-1. 牌局清單卡片（Sessions List Card）

```
┌─────────────────────────────────────┐  ← border-radius: 14px
│  2026/06/27  週六    [進行中●]       │  ← Caption 13px, 右側狀態 chip
│  下午場                              │  ← H2 18px, weight 600
│                                      │
│  小明 +2,500  阿美 +800              │  ← Score-Medium 17px
│  老王 -1,200  小芳 -2,100            │     正值 --color-win，負值 --color-lose
│                                      │
│  12 局                    › 進入     │  ← Caption + link chevron
└─────────────────────────────────────┘
```

- 背景：`--color-surface`（`#17211a`）
- 外框：`1px solid --color-border`
- 圓角：`14px`（比 v1 的 `12px` 稍大，更現代）
- 內距：`16px 16px 14px`
- 卡片間距：`12px`
- 狀態 Chip「進行中●」：背景 `--color-primary-muted`，文字 `--color-primary`，border-radius `100px`，padding `2px 8px`，12px 字
- 「結束」狀態 Chip：背景 `rgba(138,158,144,0.15)`，文字 `--color-text-secondary`
- 「...」選單觸發點：右上角，icon 24px，觸控範圍 44×44px

### 7-2. 即時排名條（Rank Bar，記局頁頂部）

排名條是打牌當下最常看的元件，要「大、清晰、有動感」：

```
┌─────────────────────────────────────┐
│ ▌ 小明   +3,600           1st ↑    │  ← 左側 4px 玩家色條
│ ▌ 阿美   +1,200           2nd ─    │
│ ▌ 老王   -800             3rd ↓    │
│ ▌ 小芳   -4,000           4th ↓↓  │
└─────────────────────────────────────┘
```

- 容器背景：`--color-surface-low`（`#0f1a12`），border-radius `12px`，padding `10px 0`
- 每行高：52px（手機觸控友善）
- 左側色條：4px 寬，高度撐滿行高，使用玩家代表色
- 玩家名字：Body 15px，weight 500，`--color-text`
- 金額：Score-Medium 17px，weight 700，tabular-nums，對齊右側
- 名次：Caption 13px，weight 600，`--color-text-secondary`
- 變化箭頭（↑ / ─ / ↓）：14px，color 依方向 = win / neutral / lose；`↓↓` 表示本局放槍
- 動畫（配合企劃 5-3）：金額從舊值滾動到新值（CSS counter animation 或 JS requestAnimationFrame），duration 400ms

### 7-3. 分數折線圖（Score Chart）

**整體容器**：
- 背景：`--color-surface`，border-radius `12px`，padding `16px`
- 圖表區佔容器的 `calc(100% - 32px)`，高度建議 220px（手機直向適中）

**座標軸**：
- X 軸（局次）：Caption 11px，`--color-text-secondary`，每隔若干局顯示（避免擠）
- Y 軸（金額）：Caption 11px，`--color-text-secondary`，靠左對齊
- 格線（Grid Lines）：`1px solid --color-border`，opacity 0.5，水平線即可（垂直格線太多太吵）
- 基準線（Y=0）：`1.5px solid --color-text-secondary`，opacity 0.7，顯著但不壓過折線

**折線**：
- 線條粗細：2.5px
- 折點圓點：diameter 5px，fill 對應玩家色，stroke 2px `--color-surface`（白邊讓點浮出）
- 終點（最後一局）：diameter 8px，加「終」文字 label（Micro 11px，同玩家色）

**Tooltip**：
- 觸發：觸碰 / hover 圖表區，顯示對應局次垂直指示線
- 垂直指示線：`1px dashed --color-text-secondary`，opacity 0.7
- Tooltip 框：背景 `--color-surface`，border `1px solid --color-border`，border-radius `8px`，padding `8px 10px`，`box-shadow: 0 4px 12px rgba(0,0,0,0.4)`
- Tooltip 內容：局次標題（Caption 12px weight 600）+ 每位玩家一行（名字 + 金額，依 win/lose 上色）
- Tooltip 位置：自動判斷靠左或靠右（避免超出螢幕邊界）

**圖例（Legend）**：
- 位於圖表上方，單行水平排列
- 每個 pill：玩家色小圓點（8px）+ 玩家名字（Caption 12px），間距 16px
- 點擊圖例可 toggle 顯示/隱藏對應折線（隱藏時 opacity 0.25）

### 7-4. 結算分享圖卡（Share Card）

分享圖卡設計原則：**在 LINE 聊天室縮圖的 4 秒內讓人看懂「誰贏多少」**。

```
┌─────────────────────────────────────┐ 寬 390px, 高 520px
│                           MahjongScore│ ← 右上浮水印 11px, --color-text-disabled
│  2026/06/27 下午場                  │ ← Caption 12px
│                                      │
│  🏆 小明    +3,600                  │ ← 金色#c9a535，Score-Large 28px
│     阿美    +1,200                  │ ← --color-win，Score-Medium 20px
│     老王    -800                    │ ← --color-lose，Score-Medium 20px
│  4️⃣ 小芳    -4,000                  │ ← --color-lose，Score-Medium 20px
│                                      │
│  [迷你折線走勢圖 390×120px]          │ ← 4 色折線，無軸標籤，只看走勢
│                                      │
│  12 局 · 底 100 · 台 50              │ ← Caption 12px, --color-text-secondary
└─────────────────────────────────────┘
```

- 背景：`--color-splash-bg`（`#0a1209`），營造高質感感受
- 邊框：無（直接黑底，分享後在白底聊天室有自然邊界）
- 圓角：16px（html2canvas 輸出前 clip）
- 不使用 emoji，改用金色文字「冠」「亞」「三」「殿」標示排名（更有東方感）

---

## 8. 元件與間距規範

### 8-1. 基礎間距節奏（4px 基準格）

所有間距使用 4 的倍數：

| 用途 | 大小 |
|---|---|
| 最小內距（icon 到文字）| 4px |
| 元件內部 padding | 8px / 12px |
| 卡片 padding | 16px |
| 卡片間距 | 12px |
| 區塊間距（section gap）| 24px |
| 頁面 padding（左右）| 16px |
| 頁面 padding（頂部，避開 status bar）| 16px |
| 頁面 padding（底部，Tab Bar 以上）| `56px + env(safe-area-inset-bottom)` |

### 8-2. 圓角（Border Radius）

| 元件類型 | 圓角 |
|---|---|
| 大卡片（Sessions Card、Chart 容器）| 14px |
| 一般卡片 / 輸入框容器 | 12px |
| 輸入框（input / select）| 8px |
| 按鈕（Button）| 8px |
| FAB（浮動新增鈕）| 50%（全圓） |
| Tag / Chip | 100px（pill） |
| Bottom Sheet | 頂部 16px，底部 0 |
| Tooltip | 8px |
| 排名條行 | 0（無圓角，行間無縫）|

### 8-3. 陰影（Box Shadow）

輕量原則：深底色不需要強調陰影層次，只在需要「浮起」效果時使用。

| 元件 | 陰影 |
|---|---|
| FAB 按鈕 | `0 4px 16px rgba(31,111,67,0.5)`（品牌色暈染） |
| Tooltip | `0 4px 12px rgba(0,0,0,0.4)` |
| Bottom Sheet | `0 -4px 20px rgba(0,0,0,0.5)` |
| 卡片 | 無陰影（靠 border + 背景色差即可） |

### 8-4. 按鈕規範

#### Primary Button（主 CTA）

```
背景：--color-primary (#1f6f43)
文字：#ffffff，15px，weight 600
padding：12px 20px
border-radius：8px
hover：--color-primary-dark (#185534)
active：scale(0.97) duration 80ms
disabled：opacity 0.4，cursor not-allowed
最小觸控高度：44px
```

#### Secondary Button（次要）

```
背景：transparent
邊框：1px solid --color-border (#253328)
文字：--color-text (#e4ede7)，15px，weight 400
hover：border-color: --color-primary-muted
```

#### Danger Button（刪除、清空）

```
背景：transparent（不用紅底，避免過於刺激）
邊框：1px solid --color-lose (#f05252)
文字：--color-lose，15px，weight 500
hover：background rgba(240,82,82,0.1)
```

#### FAB（浮動新增按鈕）

```
尺寸：56×56px
背景：--color-primary (#1f6f43)
圖示：+ 符號，24px，#ffffff
border-radius：50%
位置：右下，距右 20px，距 Tab Bar 上方 20px
陰影：0 4px 16px rgba(31,111,67,0.5)
pressed：scale(0.92) duration 80ms
```

### 8-5. 輸入框

```
background：--color-surface-low (#0f1a12)
border：1px solid --color-border (#253328)
border-radius：8px
padding：10px 12px
font-size：15px
color：--color-text
focus border-color：--color-primary (#1f6f43)
focus outline：none（用 border-color 替代）
placeholder color：--color-text-disabled (#4a5e50)
```

### 8-6. Bottom Sheet

```
背景：--color-surface (#17211a)
頂部圓角：16px
頂部 drag handle：寬 36px、高 4px、圓角 2px、color --color-border
padding：20px 16px
配合 safe-area-inset-bottom 加底部 padding
進場動畫：translateY(100%) → translateY(0)，duration 280ms，easing cubic-bezier(0.32, 0.72, 0, 1)
退場動畫：translateY(0) → translateY(100%)，duration 220ms，easing ease-in
backdrop：rgba(0,0,0,0.5)，blur(4px)
```

---

## 9. 風格一致性原則

以下是讓未來功能擴充也維持一致的核心規則，dev-lead 與 art-lead 擴充時皆需遵守：

### 原則一：Token 優先，不寫裸色值

所有顏色引用 CSS custom property（`--color-xxx`），禁止在元件中直接寫 `#xxxxxx`。這樣 light mode / dark mode 切換只需修改 `:root`。

### 原則二：數字必然 Tabular

凡是金額、分數、局次、統計數字，一律加 `font-variant-numeric: tabular-nums`。不允許例外（會破壞對齊）。

### 原則三：語意色意義不可替換

- 綠 = 贏 / 正值 / 成功：`--color-win`
- 紅 = 輸 / 負值 / 危險：`--color-lose`
- 金 = 第一名 / MVP / 冠軍：`--color-gold`

**這三個語意不可以在 App 中出現反向使用**（例如：不可以用紅色標示「成功新增」）。

### 原則四：最小觸控目標 44×44px

所有互動元件（按鈕、Tab、List Row、圖示按鈕）的觸控熱區最小為 44×44px。視覺元件可以更小，但用 padding 或 pseudo-element 擴大觸控面積。

### 原則五：動畫不超過 400ms，且尊重 prefers-reduced-motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 原則六：資訊層級最多三層

任何畫面的視覺重量不超過三個層級：**主體（一件事） > 輔助（支撐資訊）> 退場（次要說明）**。若一個畫面同時有四件事想搶眼，必須取捨。

### 原則七：圓角語意對應元件層級

- 最大（14px）= 最外層容器（卡片、圖表）
- 中（12px）= 卡片內區塊
- 小（8px）= 輸入框、按鈕、Tooltip
- 全圓（pill / 50%）= Chip、FAB

不要把大圓角用在小元件上，反之亦然。

---

## 附錄 A：CSS Custom Property 完整清單（供 dev-lead 直接實作）

```css
:root {
  /* === 背景 === */
  --color-bg:           #0d1510;
  --color-surface:      #17211a;
  --color-surface-low:  #0f1a12;
  --color-border:       #253328;
  --color-splash-bg:    #0a1209;

  /* === 文字 === */
  --color-text:          #e4ede7;
  --color-text-secondary: #8a9e90;
  --color-text-disabled:  #4a5e50;

  /* === 品牌 === */
  --color-primary:       #1f6f43;
  --color-primary-dark:  #185534;
  --color-primary-muted: #1a3d29;

  /* === 語意 === */
  --color-win:    #34c47a;
  --color-lose:   #f05252;
  --color-warn:   #d4a030;
  --color-info:   #4a9eca;

  /* === 強調 === */
  --color-gold:   #c9a535;
  --color-silver: #8f9fa3;
  --color-bronze: #a0654a;

  /* === 玩家代表色 === */
  --color-player-a: #5b9cf6;  /* 天藍 */
  --color-player-b: #f6c55b;  /* 鮮黃橙 */
  --color-player-c: #c47ef5;  /* 紫 */
  --color-player-d: #5bcfc4;  /* 青綠 */

  /* === 間距（參考用，實際可直接寫數值）=== */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-6:  24px;
  --space-8:  32px;

  /* === 圓角 === */
  --radius-sm:   8px;
  --radius-md:   12px;
  --radius-lg:   14px;
  --radius-pill: 100px;
  --radius-full: 50%;

  /* === 動畫 === */
  --ease-spring: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-sheet:  cubic-bezier(0.32, 0.72, 0, 1);
}
```

---

## 附錄 B：圖示（Icon）出圖 Brief（供 image 模型）

若未來需要產出 App Icon 或 Splash 圖示，以下為可餵給 image 模型的 prompt 草稿：

**English Prompt（App Icon）：**
> A clean, minimal mahjong tile icon for a mobile app. Single tile viewed slightly from the front, with rounded corners (radius ~12% of tile width). Dark forest-green background (#1f6f43). The tile face shows a simplified "中" or abstract line pattern in off-white (#e4ede7). Subtle gold (#c9a535) border outline, 1.5px stroke. No gradients, no glow effects. Flat design with slight depth via inner shadow only. Style: modern iOS app icon, Material You influence. —no realistic texture, no casino feel, no neon, no shiny reflections, no gradient backgrounds.

**English Prompt（Splash Logo Tile）：**
> Centered mahjong tile illustration for a splash screen. Background: very dark near-black green (#0a1209). Tile: 72×72dp, border-radius 14px, stroke #1f6f43 2px, fill #17211a. Inside the tile: a minimalist "麻" character or abstract four-dot pattern, color #e4ede7. Around the tile: subtle gold glow (#c9a535, 8% opacity, blur 20px). No animation cues in the static image. Clean, composed, premium-quiet feel.

---

*本文件由 art-lead 產出，最終視覺決策由 CEO 驗收。dev-lead 如遇規範未涵蓋的情境，以「最接近既有 token 組合」為原則，並回報 art-lead 補充。*
