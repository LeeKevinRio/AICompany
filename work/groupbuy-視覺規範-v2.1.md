# 揪購 GroupBuy — 視覺規範 v2.1（配色修訂）

- **版本**：v2.1
- **日期**：2026-08-05
- **修訂原因**：CEO 回饋 v2.0「顏色有點暗，請重新配色；底色維持偏黑，主色用橘色 OK」
- **基準版本**：v2.0 暖橙炭黑（`apps/groupbuy/src/styles.css`，commit `2b6eb44`）
- **修訂範圍**：僅動 Dark Mode 色彩 token 與其直接使用者（CSS 規則的 `var(--color-*)` 取值來源）。
  版面 / 字體 / 圓角 / 間距 / 動畫 / Light Mode 附錄一律不動，見第 5 節「不變項」。
- **作者**：art-lead　**執行**：frontend-engineer（本文件不含程式碼修改，只是規範）

## 修訂記錄

| 日期 | 內容 |
|---|---|
| 2026-08-05 | v2.1 初版發布（20 項 before→after，見 3.2 節） |
| 2026-08-05 | **勘誤**：frontend-engineer 完成 20 項施工（commit `8651302`）後回報 `.stepper button.increment`（數量步進器「＋」圓形按鈕，`styles.css:351-354`）與 `.btn.primary` 同型的「白字疊 primary 填底」問題，未列在原施工表。art-lead 裁決比照 #14/#15 修正，追加為 3.2 節 #21，見下方裁決說明。 |

---

## 0. 為什麼 v2.0 會「看起來暗」——診斷結論

盤點 `apps/groupbuy/src/styles.css` 的 v2.0 dark token 後，用 WCAG 相對亮度公式（sRGB → linear → `L`）
與 CIELAB `L*`（更適合判斷「近黑色之間是否分得出層次」的指標，因為兩個近黑色的 WCAG contrast ratio
即使色值差很多，算出來也會被公式裡的 `+0.05` 項壓到接近 1:1，不能用它判斷背景層次夠不夠開）
逐一還原實際數值，找到三個具體成因（非主觀「感覺暗」，是可量測的）：

1. **背景三層幾乎疊在一起。** `--color-bg` (#0C0A09) → `--color-surface` (#171210) →
   `--color-surface-tint` (#1E1912) 的 CIELAB `L*` 分別約 **2.8 / 5.9 / 9.1**，相鄰層級之間的 `ΔL*`
   只有 **3.1 / 3.2**，遠低於一般人眼能輕鬆分辨層次的落差（經驗值 `ΔL* ≥ 5` 才算穩定可辨）。
   結果：卡片、統計摘要區「幾乎焊死在背景上」，整體看起來是一片沒有層次的黑。
2. **次要文字實測未達 AA。** `--color-text-secondary` (#8A7268) 對 `--color-surface` 只有
   **≈4.15:1**（正文 AA 門檻是 4.5:1），對 `--color-bg` 也只有 **≈4.4:1**，雙雙未達標。
   這個顏色用在標籤、次要說明、table header、`.muted`——覆蓋率很高，讀起來偏灰霧，放大了「暗」的觀感。
3. **主色橘彩度/亮度不足，而且當按鈕底色時對白字對比不夠。** `--color-primary` (#E8621A) 的
   `Y`（相對亮度）只有 0.26，作為強調色時不夠「跳」；更嚴重的是它同時被拿來當 `.btn.primary` 的
   **填底色**，白字（`--color-text-inverse`）在上面只有 **≈3.39:1**，未達 4.5:1 正文 AA
   （v2.0 已存在但未被抓到的問題，這次一併修正）。
4. **邊框幾乎隱形。** `--color-border` (#2C2218) 對 `--color-surface` 只有 **≈1.19:1**，卡片外框、
   表格分隔線幾乎看不出來，進一步強化「糊成一片」的觀感。

修訂策略：**底色 `--color-bg` 維持不動（CEO 要求偏黑）**，把 `--color-surface`／
`--color-surface-tint`／新增的 `--color-raised`／`--color-border` 這幾層往上拉開，讓卡片、統計區、
邊框有明確層次；次要文字與 `closed` 語意色提亮到全層過 AA；主色橘拆成「強調色（文字/邊框用，更亮更飽和）」
與「按鈕填底色（較深，確保白字過 AA）」兩個角色，取代 v2.0 兩者共用一個 token 的做法。

---

## 1. 新色票（v2.1）

### 1.1 背景 / 表面（3 層 + 新增浮起層 + 輸入凹陷層）

| Token | v2.0 | v2.1（新） | CIELAB `L*` | 說明 |
|---|---|---|---|---|
| `--color-bg` | `#0C0A09` | **`#0C0A09`（不變）** | 2.8 | 頁面底，維持偏黑（CEO 要求） |
| `--color-surface` | `#171210` | **`#1E1712`** | 8.4 | 卡片表面，`ΔL*` 對 bg 從 3.1 拉大到 **5.6** |
| `--color-surface-tint` | `#1E1912` | **`#2A2016`** | 13.1 | 統計摘要區（`.summary-block`），`ΔL*` 對 surface 從 3.2 拉大到 **4.7** |
| `--color-raised`（新增） | 無 | **`#362819`** | 17.3 | 浮起元素（未來 modal / dropdown / toast 用，目前無元件套用，見第 4 節） |
| `--color-input-bg` | `#100D0B`（幾乎貼著 bg，凹陷感很弱） | **`#14100D`** | 5.0 | 輸入框凹陷底，介於 bg 與 surface 之間，凹陷感更明確 |

> 背景層之間的落差用 `ΔL*`（CIELAB 明度差）判斷，不是 WCAG contrast ratio——近黑色的 WCAG
> 公式在此區間不敏感，用它會誤判「差很多也算差不多」。v2.1 的總跨距從 v2.0 的 `ΔL*≈6.3`
> （bg→tint）拉大到 `ΔL*≈14.5`（bg→raised），層次感提升超過一倍。

### 1.2 文字四階

| Token | v2.0 | v2.1（新） | 對比（vs bg / vs surface / vs tint / vs raised） | 判定 |
|---|---|---|---|---|
| `--color-text`（主文字） | `#F0E8E0` | **不變** | 16.30 / 15.33 / 13.16 / 11.75 | 全部 AAA，維持 |
| `--color-text-secondary`（次文字） | `#8A7268` | **`#A89083`** | 6.57 / 5.89 / 5.30 / 4.74 | **全部 ≥4.5 AA**（v2.0 在 surface 只有 4.15，未達標） |
| `--color-text-disabled`（停用/placeholder） | `#4A3C34` | **`#6B5B4E`** | 對 input-bg 2.91 / 對 surface 2.72 | 裝飾性文字，WCAG 不強制 AA，但需可辨識（v2.0 幾乎不可見） |
| `--color-text-inverse`（反白） | `#FFFFFF` | 不變 | — | 用在有色底上，見 1.3 按鈕填底驗證 |

### 1.3 品牌色：主色橘（拆成「強調文字/邊框」與「按鈕填底」兩個角色）

v2.0 用同一個 `--color-primary` 兼職「文字/邊框強調色」和「按鈕填底色」，這次拆開，
因為兩個角色需要的亮度方向相反（強調色要夠亮夠跳；按鈕填底要夠深才能讓白字過 AA）。

| Token | v2.0 | v2.1（新） | 角色 | 對比驗證 |
|---|---|---|---|---|
| `--color-primary`（強調色：文字/邊框/icon） | `#E8621A`（Y=0.26，偏悶） | **`#FF7A29`**（Y=0.35，更亮更飽和） | 連結、`section-title`、`badge.open`、`ghost-primary`、`stepper` 按鈕框字、卡片左側狀態條 | vs bg 7.59:1／vs surface 6.80:1／vs tint 6.13:1／vs raised 5.47:1，**全部遠超 AA** |
| `--color-primary-fill`（新增：按鈕填底） | 借用 `--color-primary` `#E8621A` | **`#C64A0D`** | `.btn.primary` 預設底色 | 白字在上 **4.79:1**（AA 過關；v2.0 借用 primary 只有 3.39:1，**不過**） |
| `--color-primary-fill-hover`（新增：hover/pressed 底色） | `--color-primary-dark` `#C04D10` | **`#A83D0A`** | `.btn.primary:hover`、按下狀態 | 白字在上 6.29:1，比預設底更深，hover 回饋方向正確 |
| `--color-primary-muted`（選中狀態淡底） | `#251408` | **`#2E1B0C`** | `product-card.selected` 底、focus box-shadow、`ghost-primary:hover` 底 | 裝飾性色塊，非文字對比需求，僅配合新背景階層微調 |
| `--color-primary-light`（動畫閃光幀，非常態色） | `#FF8A45` | 不變 | 目前程式碼未使用，預留 | — |

> **舊 `--color-primary-dark` 這個 token 名稱在 v2.1 停用**，職責一分為二：文字/邊框強調色留在
> `--color-primary`（變亮），按鈕填底新增 `--color-primary-fill` / `--color-primary-fill-hover`。
> 這是本次唯一的「改名」，理由見第 0 節第 3 點與第 3.2 節 before→after 表。

### 1.4 邊框兩階

| Token | v2.0 | v2.1（新） | `L*` | 對比 vs surface / vs bg | 用途 |
|---|---|---|---|---|---|
| `--color-border`（一般） | `#2C2218` | **`#4A3524`** | 24.1 | 1.54:1 / 1.72:1 | 卡片外框、badge 外框、table 分隔線、縮圖框、share-link 框（結構性分隔，非唯一辨識手段） |
| `--color-border-strong`（新增：強調） | 無 | **`#6B4E32`** | 35.6 | 2.33:1 / 2.60:1 | 輸入框邊界、表格總計列分隔線——這兩處邊界本身承載「這是可互動欄位／這是總計」的訊息，需要更明顯 |

> 這兩個都是**結構性邊框**，不是文字，WCAG 1.4.11（Non-text Contrast）的 3:1 門檻只在
> 「邊框是理解內容的唯一手段」時強制適用；本例卡片/表格另外還有間距與底色差異輔助辨識，
> 不算唯一手段，故不強制對照 3:1，但 v2.1 仍把兩層都大幅提亮（`border` 對比從 1.19→1.54，
> `border-strong` 到 2.33），肉眼可見度明顯提升，其中 `border-strong` 已相當接近 3:1。

### 1.5 語意色（成功 / 警示 / 錯誤 / 金額）

這四組在 v2.0 就已經很亮（Y 都在 0.25–0.44 之間），對比全部 AA 以上（見下表），**不是「暗」的成因，
v2.1 維持不變**，只有 `--color-closed`（已截止的灰階，跟次要文字同源問題）提亮。

| Token | 值（不變） | 對比 vs bg | 對比 vs surface | 判定 |
|---|---|---|---|---|
| `--color-success`（收款打勾/已完成） | `#1DB974` | 7.74:1 | 6.94:1 | AAA |
| `--color-success-muted`（打勾動畫底） | `#143D26` | — | — | 底色，success 文字在其上 4.77:1，AA |
| `--color-warn`（即將截止） | `#F59E0B` | 9.20:1 | 8.25:1 | AAA |
| `--color-warn-muted` | `#291E08` | — | — | 不變 |
| `--color-danger` / `--color-unpaid`（錯誤/未收款） | `#F05252` | 5.68:1 | 5.08:1 | AA |
| `--color-danger-muted` | `#2A0D0D` | — | — | 不變 |
| `--color-amount`（金額文字） | `#F07830` | 6.99:1 | 5.64（vs tint） | AA+ |
| `--color-amount-strong`（總計大字） | `#FF9050` | 8.80:1 | 7.11（vs tint） | AAA |
| `--color-closed`（已截止/靜態） | `#8A7A70` → **`#AC9689`** | 舊 4.80→新 **7.04** | 舊 4.30(fail)→新 **6.30** | 舊版對 surface 未達 AA，新版全層過 |

---

## 2. 對比度驗證總表（逐組列數字，供 qa-e2e / frontend 直接核對）

| 文字 token | 背景 token | 對比值 | 是否 ≥4.5:1（正文 AA） | 是否 ≥3:1（大字/次要 AA） |
|---|---|---|---|---|
| `--color-text` | `--color-bg` | 16.30 | 過 | 過 |
| `--color-text` | `--color-surface` | 15.33 | 過 | 過 |
| `--color-text` | `--color-surface-tint` | 13.16 | 過 | 過 |
| `--color-text` | `--color-raised` | 11.75 | 過 | 過 |
| `--color-text-secondary` | `--color-bg` | 6.57 | 過 | 過 |
| `--color-text-secondary` | `--color-surface` | 5.89 | 過 | 過 |
| `--color-text-secondary` | `--color-surface-tint` | 5.30 | 過 | 過 |
| `--color-text-secondary` | `--color-raised` | 4.74 | 過（低空） | 過 |
| `--color-primary` | `--color-bg` | 7.59 | 過 | 過 |
| `--color-primary` | `--color-surface` | 6.80 | 過 | 過 |
| `--color-primary` | `--color-surface-tint` | 6.13 | 過 | 過 |
| `--color-primary` | `--color-raised` | 5.47 | 過 | 過 |
| `--color-text-inverse`（白） | `--color-primary-fill` | 4.79 | 過 | 過 |
| `--color-text-inverse`（白） | `--color-primary-fill-hover` | 6.29 | 過 | 過 |
| `--color-text-inverse`（白，對照組） | `--color-primary`（若誤用當底色，**不建議**） | 2.60 | **不過** | 不過 |
| `--color-success` | `--color-bg` | 7.74 | 過 | 過 |
| `--color-success` | `--color-surface` | 6.94 | 過 | 過 |
| `--color-success` | `--color-success-muted` | 4.77 | 過 | 過 |
| `--color-warn` | `--color-bg` | 9.20 | 過 | 過 |
| `--color-warn` | `--color-surface` | 8.25 | 過 | 過 |
| `--color-danger` / `--color-unpaid` | `--color-bg` | 5.68 | 過 | 過 |
| `--color-danger` / `--color-unpaid` | `--color-surface` | 5.08 | 過 | 過 |
| `--color-amount` | `--color-bg` | 6.99 | 過 | 過 |
| `--color-amount` | `--color-surface-tint` | 5.64 | 過 | 過 |
| `--color-amount-strong` | `--color-bg` | 8.80 | 過 | 過 |
| `--color-closed` | `--color-bg` | 7.04 | 過 | 過 |
| `--color-closed` | `--color-surface` | 6.30 | 過 | 過 |
| `--color-closed` | `--color-surface-tint` | 5.68 | 過 | 過 |
| `--color-closed` | `--color-raised` | 5.07 | 過 | 過 |
| `--color-text-disabled`（裝飾性，非 AA 強制） | `--color-input-bg` | 2.91 | 未達（設計上刻意較低，仍比 v2.0 清楚） | 未達 |

**唯一需要注意的臨界值**：`--color-text-secondary` 對 `--color-raised` 只有 4.74:1，貼著 4.5
門檻。目前 app 沒有元件會把次要文字放在 raised 層（raised 是預留給未來 modal/toast），
若之後真的要在 raised 層放大量次要說明文字，請改用 `--color-text`（主文字，11.75:1）而不是
`--color-text-secondary`，不要再壓字重找更暗的灰。

---

## 3. 使用規則 + Before → After 施工對照表

### 3.1 色票對應到現行元件

| 色票 | 對應功能 / 元件 |
|---|---|
| `--color-bg` | app 最外層頁面底 (`body`) |
| `--color-surface` | 所有 `.card`、`.product-card`、`.btn`（一般狀態）、`.product-thumb` 底 |
| `--color-surface-tint` | 後台統計表摘要區 `.summary-block`（DashboardPage.tsx） |
| `--color-raised` | 目前無元件使用，預留給未來浮層（modal/dropdown/toast） |
| `--color-input-bg` | 開團表單 / 買家填單頁的 `input` `textarea`（CreateGroupPage.tsx、JoinPage.tsx）、`.share-link`、`.receipt-code` |
| `--color-text` / `-secondary` / `-disabled` / `-inverse` | 全站文字階層，`.muted`／`.stat-label`／`label`／placeholder／按鈕反白字 |
| `--color-primary` | 連結 `.link`、`.section-title`、`.badge.open`、`.ghost-primary`、`.stepper` 圈按鈕框字、`.card.status-open` 左側狀態條、`.product-card.selected` 左側狀態條、`.receipt-code` 虛線框 |
| `--color-primary-fill` / `-fill-hover` | `.btn.primary` 按鈕填底（開團表單「建立」、買家填單頁「送出訂單」等主 CTA） |
| `--color-primary-muted` | `.product-card.selected` 底色、`input:focus` box-shadow、`.ghost-primary:hover` 底 |
| `--color-success` / `-muted` | 收款打勾動畫（DashboardPage.tsx `.check-pop` `.row-flash`）、`.badge.settled`、`.banner.success` |
| `--color-warn` / `-muted` | 倒數計時文字（DashboardPage.tsx / GroupsPage.tsx / JoinPage.tsx 內 inline `color: var(--color-warn)`）、`.badge.warn`、`.banner.warn` |
| `--color-danger` / `-muted` / `--color-unpaid` | 未收款金額、`.btn.danger`、`.banner.error` |
| `--color-closed` | 已截止狀態（`.badge.closed`、倒數計時文字截止後、`.card.status-closed` 左側狀態條） |
| `--color-amount` / `-strong` | 金額數字（`.stat-table td.amount`、`.member-row .member-amount`、`.total-line .amount`） |
| `--color-border` / `-strong` | 見下方 3.2 表 |

### 3.2 Before → After（styles.css，逐行對照，frontend 照表施工；共 21 項，#21 為 2026-08-05 勘誤追加）

| # | 位置 | Before | After | 原因 |
|---|---|---|---|---|
| 1 | `styles.css:11` `--color-surface` | `#171210` | `#1E1712` | 拉開卡片與頁面底的層次（`ΔL*` 3.1→5.6） |
| 2 | `styles.css:12` `--color-surface-tint` | `#1E1912` | `#2A2016` | 拉開統計摘要區層次 |
| 3 | `styles.css:13` `--color-border` | `#2C2218` | `#4A3524` | 邊框從幾乎隱形提升到可辨識 |
| 4 | `styles.css:14` `--color-input-bg` | `#100D0B` | `#14100D` | 恢復「凹陷底」的層次定位（v2.0 此值比 bg 還接近，等於沒凹陷） |
| 5 | 新增於 `styles.css` 背景區塊末（原 L14 之後） | 無 | `--color-raised: #362819;` | 新增第三層背景，供未來浮層使用 |
| 6 | `styles.css:18` `--color-text-secondary` | `#8A7268` | `#A89083` | 修正 AA 未過（surface 上僅 4.15:1） |
| 7 | `styles.css:19` `--color-text-disabled` | `#4A3C34` | `#6B5B4E` | placeholder/disabled 幾乎不可見 |
| 8 | `styles.css:24` `--color-primary` | `#E8621A` | `#FF7A29` | 提亮強調色，作為視覺錨點 |
| 9 | `styles.css:25` `--color-primary-dark` | `#C04D10` | **改名為 `--color-primary-fill-hover`，值 `#A83D0A`** | 職責拆分，見下列 #11 |
| 10 | `styles.css:26` `--color-primary-muted` | `#251408` | `#2E1B0C` | 配合新背景階層微調 |
| 11 | 新增於 `--color-primary` 附近 | 無 | `--color-primary-fill: #C64A0D;` | 按鈕填底專用，確保白字達 AA（見 0 節第 3 點） |
| 12 | `styles.css:44` `--color-closed` | `#8A7A70` | `#AC9689` | 修正 AA 未過（surface 上僅 4.30:1） |
| 13 | 新增於邊框區塊 | 無 | `--color-border-strong: #6B4E32;` | 表單邊界 / 總計列分隔線需要更高辨識度 |
| 14 | `styles.css:223-224` `.btn.primary` | `background: var(--color-primary); border-color: var(--color-primary-dark);` | `background: var(--color-primary-fill); border-color: var(--color-primary-fill-hover);` | v2.0 用強調色當按鈕底，白字僅 3.39:1 未過 AA；改亮後若不拆分會惡化到 2.60:1 |
| 15 | `styles.css:228` `.btn.primary:hover` | `background: var(--color-primary-dark);` | `background: var(--color-primary-fill-hover);` | 同上，token 改名同步 |
| 16 | `styles.css:282-295` `input/textarea` 邊框 | `border: 1px solid var(--color-border);` | `border: 1px solid var(--color-border-strong);` | 表單欄位邊界需要比一般卡片框更明顯（開團表單、買家填單頁皆吃到） |
| 17 | `styles.css:406` `.stat-table tfoot td` | `border-top: 2px solid var(--color-border);` | `border-top: 2px solid var(--color-border-strong);` | 總計列分隔線需要更強視覺重量（後台統計表） |
| 18 | 其餘所有 `var(--color-border)` 用法（`.card` L143、`.badge` L204、`.btn` L216、`.stat-table` L387、`.member-row` L417、`.product-edit` L490、`.product-thumb` L499、`.share-link` L512） | — | **class 名稱不用改**，token 數值已在 #3 提亮，自動套用 | 一般結構分隔，不需升級到 strong 階 |
| 19 | 所有 `var(--color-primary)` 用在文字/邊框角色的地方（`.badge.open` L207、`.link` L260、`.section-title` L306、`.stepper button` L333/L335、`.ghost-primary` L242-243、`.card.status-open` L149、`.product-card.selected` L366、`.receipt-code` L536） | — | **class 名稱不用改**，token 數值已提亮，自動套用 | 這些都是強調文字/邊框角色，不是按鈕填底，沿用 `--color-primary` 即可 |
| 20 | tsx 內 inline `style={{ color: 'var(--color-warn)' }}` / `'var(--color-closed)'`（DashboardPage.tsx:125、GroupsPage.tsx:63、JoinPage.tsx:147） | — | **不用改程式碼**，token 數值變化自動生效 | 倒數計時文字色不用動 class/inline 寫法 |
| 21（勘誤，2026-08-05 追加） | `styles.css:351-354` `.stepper button.increment` | `background: var(--color-primary); color: var(--color-text-inverse);` | `background: var(--color-primary-fill); color: var(--color-text-inverse);` | 與 #14 同一類問題：白字疊在填底 `--color-primary` 上。詳細裁決見 3.3 節 |

#### 3.3 裁決說明：`.stepper button.increment`（2026-08-05 勘誤）

**問題**：`.stepper button.increment`（數量步進器「＋」圓形按鈕，開團表單商品數量、買家填單頁選品數量皆會用到）
是 `background: var(--color-primary); color: var(--color-text-inverse);`——白字疊在「強調色」`--color-primary`
上，跟 v2.0 的 `.btn.primary` 是同一種誤用（強調色 token 被拿去當填底色）。原 3.2 施工表只列了 `.btn.primary`
（#14/#15），漏列了這個同樣受影響的元件，這次補齊。

**是否可以用「小字/圖示例外」豁免，不用改？** 評估後**不採用**這個豁免，理由：
- `+` 字符雖然只有 18px，但 `font-weight: 700`（粗體）。WCAG 大字豁免（3:1 即可）門檻是「粗體 ≥14pt
  （≈18.66px）」，18px 嚴格算**未達**這個門檻（差 0.66px），不能穩妥地主張大字例外。
- 就算真的踩線用大字標準（3:1），也不划算：這顆按鈕是「增加數量」的主要操作熱點，比一般文字更需要
  清楚可讀，沒有理由把它做得比 `.btn.primary` 更難讀。
- 修法成本極低（只是換一個已經定義好的 token），沒有理由留下不一致。

**裁決**：`.stepper button.increment` 背景改用 `--color-primary-fill`（`#C64A0D`），文字色維持
`--color-text-inverse`（白），與 `.btn.primary` 用同一套填底邏輯。

**對比數值**：
- 修正前（若照原樣沿用 v2.1 提亮後的 `--color-primary` `#FF7A29`）：白字對比 **2.60:1**，比 v2.0 用
  `#E8621A` 時的 3.39:1 還要**更差**（frontend 回報的機制成立，且已用第 0 節第 3 點論證過的同一公式重新算過一次確認）。
- 修正後（`--color-primary-fill` `#C64A0D`）：白字對比 **4.79:1**，過 AA，與 `.btn.primary` 數值完全一致
  （本來就是同一個 token，理應一致）。

**同時檢查過的相鄰元件（確認不需要一併修）**：`.stepper button`（非 `.increment` 的預設「－」按鈕）是
`border: 1.5px solid var(--color-primary); background: var(--color-surface); color: var(--color-primary);`——
主色橘在此是**文字/邊框角色**，不是填底，套用的是本文件 1.3 節已驗證過的 `--color-primary` 文字對比數字
（對 `--color-surface` 6.80:1，對 `--color-primary-muted` 選中底色 6.31:1），全部過 AA，**不需要修改**。

**是否需要 hover/pressed 變體**：目前 `.stepper button.increment` 沒有定義 `:hover`／`:active`，只有
`:disabled`（`opacity: 0.3`，沿用既有「停用降低不透明度」慣例，不受本次裁決影響）。本次裁決**不新增**
hover 樣式，維持現狀範圍，避免施工表外再擴大改動；若之後要幫按鈕加 hover/pressed 回饋，比照
`.btn.primary:hover` 用 `--color-primary-fill-hover`（`#A83D0A`，白字 6.29:1）即可。

---

## 4. 不變項（這次刻意不動，frontend 請勿擴大解讀）

- **版面結構**：`.app-shell` `max-width: 640px`、所有 flex/grid 排列、`.page-header`、
  `.summary-block` 排列方式全部不動。
- **字體**：`font-family` 清單、各元件 `font-size`（20px 標題 / 16px 內文 / 13px 標籤等）、
  `font-weight` 全部不動。
- **圓角**：`--radius-sm/md/lg/pill` 四個數值不動。
- **間距**：`--space-1` ~ `--space-8` 六個數值不動。
- **動畫**：`checkPop` / `rowFlash` 的 timing、easing、`prefers-reduced-motion` 處理不動；
  只有它們引用的顏色（`--color-success-muted` 等）因為本來就沒問題，維持原值。
- **語意色本體**：`--color-success` / `--color-warn` / `--color-danger` / `--color-unpaid` /
  `--color-amount` / `--color-amount-strong` 的色值不動（本來就已通過 AA/AAA，不是「暗」的成因）。
- **Light Mode（附錄一，`[data-theme="light"]` 區塊）**：這次 CEO 只談 dark mode，Light Mode
  token 完全不動，之後若要一併修訂需另外開任務。
- **QR 區塊白底**（`.qr-box { background: #ffffff; }`）：因應 QR 掃描需求的功能性白底，
  不屬於色彩規範調整範圍，不動。

---

## 5. 給 frontend-engineer 的驗收清單

- [ ] `styles.css` 第 3.2 節 20 項逐一核對，其中 #14/#15/#16/#17 是**唯一需要動到 CSS 規則本身**
      （不只是改 token 值）的地方，其餘都只是改 `:root` 裡的 hex 值。
  - [ ] `.btn.primary` 底色改用 `--color-primary-fill`，hover 改用 `--color-primary-fill-hover`，
        白字在上肉眼確認清楚可讀（對照 4.79:1 / 6.29:1）。
  - [ ] 表單輸入框邊界（開團表單、買家填單頁）目視比 v2.0 明顯。
  - [ ] 後台統計表總計列分隔線比一般分隔線粗/亮。
  - [ ] `.stepper button.increment`（數量步進器「＋」圓形按鈕）底色改用 `--color-primary-fill`，白字在上肉眼確認清楚可讀（對照 4.79:1，見 3.3 節勘誤裁決）。
- [ ] 卡片（`.card` / `.product-card`）與頁面底色目視有明確分層，不再是「一片黑」。
- [ ] 次要文字（`.muted`、table header、`.stat-label`）在卡片與統計摘要區上都清楚可讀。
- [ ] `.badge.closed` / 已截止倒數文字目視不再霧灰，跟其他 badge 一樣清楚。
- [ ] 完成後交 qa-e2e 用瀏覽器實機截圖比對本文件色票，過關才算 done（依 CLAUDE.md「通過審查才算完成」原則）。
