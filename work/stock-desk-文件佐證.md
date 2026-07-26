# Stock Desk 文件佐證清單

本檔案逐條列出三份修正文件中的**每一個技術性事實宣稱** 及其代碼來源，供風控與 CEO 抽驗。

---

## 一、stock-desk-產品說明.md 佐證

### 產品定位與頁面

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L12-13 | 離線示範模式（合成資料集，不適用於決策） | `app/demo/seed.py:1-38` |
| L20 | 五個頁面 `/` `/position/[symbol]` `/settings` `/backtest` | `frontend/app/` 路由結構 |
| L33 | 首頁只抓 health、投資組合摘要、設定、待處理警示，不抓建議卡 | `frontend/app/page.tsx:12-13,67-68` |
| L42-44 | 摘要卡四項：總資產（已估值部位市值）、未實現損益、標的貢獻、匯率貢獻 | `frontend/app/SummaryCards.tsx:41,50,64,72` |
| L48 | 風險儀表五項皆恆為 not_evaluable | `frontend/app/RiskGauge.tsx:31-69,76` |
| L52 | 待處理警示列出未確認警示（unacknowledged=true），預設限制 200 筆 | `backend/app/api/alerts.py:108-119` |
| L58 | 日K線均線：5 日、20 日、60 日線 | `backend/app/signals/technical.py:43` |
| L77-79 | sufficient_data 條件：評估規則少於 50%、全不命中、無規則被評估 | `backend/app/advice/engine.py:308-311` |

### 建議卡與風險上限

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L96 | **五項上限中第 2、3、5 條目前恆為 not_evaluable，實際生效者僅第 1、4 條** | `backend/app/advice/limits.py:40-54`（五項定義） |
| L101-105 | 上限評估：第 1 條違反時 >= 上限；第 4 條基於 ATR×停損倍數 | `backend/app/advice/limits.py:9-16,566-578` |
| L69 | Quantity Range 欄位含 `restores_compliance` 布林 | `backend/app/advice/limits.py:166-183` |
| L77-79 | insufficient_data：防禦型建議即使資料不足 50% 仍會輸出；但 add 會停止評估 | `backend/app/advice/engine.py:308-311` |
| L156-158 | matched_rules 含 id、name、action、weight、weight_meaning、explanation | `backend/app/advice/engine.py:343-359` |

### 回測

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L177-178 | 策略側已計交易成本（台股手續費 0.001425 雙邊、證交稅 0.003／ETF 0.001、美股賣出監管費）；Buy & Hold 為未計成本的被動基準 | `backend/app/backtest/costs.py:49-92` + `api/backtest.py:51-55` |
| L179 | 費率尚未經主要來源查證（verified_on 為 null） | `backend/app/backtest/costs.py:57` |
| L181 | Train/Test Split：train_size 預設 252 交易日、test_size 預設 63 交易日；walk-forward 必須同時指定 | `backend/app/api/backtest.py:47-50,70-71` |
| L176 | MA Cross 策略：20/60 日窗口（不可調） | `backend/app/backtest/strategies.py:24-25` + `api/backtest.py:61`（extra="forbid"） |

### 警示系統

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L208 | **四種規則類型**：price_above / price_below / signal_condition / risk_limit_breach | `backend/app/alerts/models.py:3,33` |
| L232 | 警示規則只能新增/刪除，無編輯端點（無 PUT/PATCH） | `backend/app/api/alerts.py:84-120` |
| L241 | 祕密不寫進設定頁，只來自環境變數（ALERT_DISCORD_WEBHOOK_URL、ALERT_TELEGRAM_BOT_TOKEN、ALERT_TELEGRAM_CHAT_ID） | `backend/app/alerts/notify.py:3-9,89-91` + `settings/models.py:88-90` |

### 技術層

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L280-285 | 指標：MA 5/20/60、ATR(14)、RSI(14)、KD、MACD、Bollinger Bands、Beta、成交量 Z-score、回撤率、波動率 | `backend/app/signals/technical.py:43-51` + `advice/context.py:25-48` |
| L310 | `leverage_etf` 觸發槓桿專章；**不含 `futures_etf`** | `backend/app/leverage/detect.py:26-28` |
| L318-319 | FX：已實作台灣銀行 USD/TWD 日線匯率 adapter，估值層已接線；建議卡層的風控輸入尚未接 FX | `backend/app/data/providers/fx.py:1-30,103` + `portfolio/valuation.py:48,163,178` + `advice/book.py:180-193` |
| L330 | 當前規則集：1.0.2 版本，12 條規則 | `backend/app/advice/rules/default.yaml:24,27-194` |
| L333-334 | 硬性上界：max_position_weight ≤ 0.50、max_gross_exposure ≤ 1.50；修改需程式碼變更與風控、CEO 同意 | `backend/app/advice/limits.py:73,78` + `81-93` |
| L352-355 | 排程非由 app/main.py 啟動，獨立 process；interval trigger（非 cron）：資料更新 1440 分鐘、警示評估 60 分鐘 | `backend/app/scheduler.py:3,64,171-196` + `app/main.py` |

### 離線示範模式

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L371-378 | 示範資料標記 `source="demo_synthetic"`；持倉與規則帶 `[demo_synthetic]` 前綴；合成價格寫進正式 DB；CLI 警告 | `backend/app/demo/seed.py:1-85` + `series.py` |
| L383-387 | 用法：`uv run python -m app.demo.seed` 啟動，`--reset` 清除 | `backend/app/demo/seed.py:3-4` |
| L390-391 | 示範內容：持倉 3 筆（2330、0050、00631L），警示規則 3 條，日線 60 根 | `backend/app/demo/seed.py:93-99` |

---

## 二、stock-desk-已知限制與後續.md 佐證

### 限制 #1-7

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L19 | US 市場無任何 adapter；嘗試查詢會回 unavailable | `backend/app/data/providers/__init__.py` + `positions/models.py` |
| L36-40 | **Drag 同樣需要指數日線，兩區都回 insufficient_data** | `backend/app/leverage/drag.py:291-296` + `leverage/service.py:163-166` |
| L54-58 | 槓桿 ETF registry：17 筆硬編碼，verified 欄位永遠為 false，來源為「模型訓練知識」 | `backend/app/leverage/detect.py:26-28,44,87-88,93-215` |
| L61 | FX adapter 完整實作（台灣銀行 USD/TWD 日線）；估值層已接線；風控層未接 | `backend/app/data/providers/fx.py:1-216` + `portfolio/valuation.py` + `advice/book.py:180-193` |
| L87 | 回測策略僅 `ma_cross`；未知策略回 422 | `backend/app/backtest/strategies.py:66-69` + `api/backtest.py:79-81` |
| L100 | 警示規則無 PUT/PATCH，只有 GET/POST/DELETE | `backend/app/api/alerts.py:84-120` |

### 限制 #10：風控官 required 項目

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L216-220 | `concentration_watch` 規則硬寫 12% 門檻；已改寫文案只陳述自身算得出的事實 | `backend/app/advice/rules/default.yaml:19-23,183-193` |
| L221 | 硬性上界：`max_position_weight` ≤ 0.50、`max_gross_exposure` ≤ 1.50；已實裝回傳 422 | `backend/app/advice/limits.py:70-93` |

---

## 三、docs/adr/0004-stock-desk-建議引擎採規則式.md 佐證

### 決策與架構

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L112 | 當前規則集：1.0.2 版本，12 條規則 | `backend/app/advice/rules/default.yaml:24,27-194` |
| L119 | 規則檔案聲明版本 semver；個別規則無 version 欄位 | `backend/app/advice/loader.py:141,163-167` + `133-159`（Rule model） |
| L125 | 禁用詞共 10 個：保證、必漲、必賺、必跌、穩賺、穩賠、一定會、包賺、零風險、無風險 | `backend/app/advice/loader.py:45-56` |
| L143 | 規則輸出 `action` 欄位；方向由引擎推導（ACTION_DIRECTION 對照表）；規則作者無法指定 | `backend/app/advice/loader.py:60` + `engine.py:76-82` |
| L149 | 方向優先序：先比累計權重，DIRECTION_PRECEDENCE 只在權重相等時作 tie-break | `backend/app/advice/engine.py:198-216` |
| L189 | matched_rules 含 id、name、action、weight、weight_meaning、explanation；counterarguments 和 invalidation_conditions 為卡片層級獨立去重清單 | `backend/app/advice/engine.py:343-359` |

### 規則範例

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L154-165（現行版） | 規則結構示例（rsi_oversold_with_trend）：條件是 RSI < 30 且 close > MA60，action 為 add，weight 0.4 | `backend/app/advice/rules/default.yaml:63-77` |

### 廢棄規則與監測

| 文件位置 | 事實宣稱 | 代碼來源 |
| --- | --- | --- |
| L204 | 廢棄規則機制尚未實作；當前 Rule model 無 deprecated 欄位 | `backend/app/advice/loader.py:141`（extra="forbid"） |
| L253-267 | 監測與優化改為「規劃中」；目前尚未上線「回溯統計」「使用者反饋」「定期審查」等機制 | 全 `frontend/app/` 與 `backend/app/api/` 無相關實裝 |

---

## 四、跨文件事實驗證摘要

### 一致性檢查

| 事實宣稱 | 出現位置 | 驗證結果 |
| --- | --- | --- |
| MA 窗口 5/20/60 | 產品說明 L58、L285 | ✓ 確認：`technical.py:43` |
| 警示四種類型 | 產品說明 L207、已知限制無特別說明 | ✓ 確認：`alerts/models.py:33` |
| 規則 12 條 | 已知限制無明指、ADR-0004 L112 | ✓ 確認：`default.yaml:27-194` 逐條計數 |
| FX 完整實作 | 產品說明 L319、已知限制 L61、ADR-0004 無提 | ✓ 確認：`fx.py:1-216` |
| 風險上限硬上界 | 產品說明 L333-334、已知限制 L221 | ✓ 確認：`limits.py:70-93` |
| 離線示範模式 | 產品說明 L371-392 | ✓ 確認：`seed.py:1-85` |

---

## 五、無法驗證或修改為「規劃中」的項目

| 項目 | 原因 | 文件位置 |
| --- | --- | --- |
| 使用者行為（P1 #3 中「許多使用者已手動輸入 US 部位」等） | 本機單人工具無遙測，無使用者群體數據 | 已刪除 |
| 監測與優化（ADR-0004 L213-221） | 全 repo 無「報告異常」UI、無抽樣回溯模組 | 改為「規劃中」 |
| `deprecated` 規則機制（ADR-0004 L204） | Rule model `extra="forbid"`，無此欄位 | 改為「尚未實作」 |

---

## 六、修正清單執行進度

### 已完成

- [x] A1：回測成本敘述方向修正（策略有完整成本模型、只有 Buy&Hold 是 gross of cost）
- [x] A1b：新增費率未查證段落
- [x] A2：刪除「Train/Test Split 可選」描述
- [x] A3：刪除「MA window 可調」
- [x] A4：新增離線示範模式完整章節
- [x] A5：更正 FX 實作狀態（已完整實作 adapter 與估值層接線，風控層未接）
- [x] A6：修正槓桿 ETF 觸發條件（排除 futures_etf）
- [x] A7：更正 drag 需要指數日線
- [x] A8：刪除「flat_index」標籤說法
- [x] A9：移除「Black-Litterman 拖曳公式」錯誤名稱
- [x] A10：改為 MA 5/20/60
- [x] A11：移除勝率、補 KD 與 beta
- [x] A12：刪除編輯規則的說法
- [x] A13：刪除設定頁填祕密的說法
- [x] A14：刪除紅綠燈說法
- [x] A15：更正規則版本顯示在個股頁
- [x] A16：改為 7 個風險預算欄位（加 atr_stop_multiple）
- [x] A17：刪除「24 小時窗」、改為「待處理警示」
- [x] A18：改為「風險儀表」
- [x] A19：改為正確的四張摘要卡（總資產、未實現損益、標的貢獻、匯率貢獻）
- [x] A20：更正 insufficient_data 條件（防禦型即使不足 50% 仍輸出）
- [x] A21：matched_rules 不含 counterarguments / invalidation_conditions（那是卡片層級）
- [x] A22：改為「四種」規則類型
- [x] A23：改為獨立 process、interval trigger、無「UTC 00:00」
- [x] A24：改為 5 條路由
- [x] A25：改為比率而非金額
- [x] A26：改為 fresh / backup / cached_stale / unavailable
- [x] A27：更正推播訊息格式
- [x] A28：首頁只抓 health/summary/settings/alerts，不抓建議
- [x] A29：降級鏈**每次都先打** live provider，快取最後一層
- [x] A30：新增 `restores_compliance` 欄位與說明

### 已知限制部分

- [x] B1：FX 改寫為「adapter 完整實作，估值層已接、風控層未接」
- [x] B2：drag 也需指數日線
- [x] B3：原因字串更正
- [x] B4：槓桿檢測改為「17 筆硬編碼註冊表」
- [x] B5：verified 永遠為 false
- [x] B6：未知策略回 422（非 no-op）
- [x] B7：刪除「許多使用者」的行為描述
- [x] B8-B10：表格與檔案參考更新
- [x] B11：列舉六種回 None 的路徑
- [x] B12：硬上界已實裝，無待辦

### ADR-0004 部分

- [x] C1：12 條規則（非 20 條）
- [x] C2：無個別規則 version 欄位
- [x] C3：deprecated 機制尚未實作
- [x] C4：matched_rules 與 action_weights 結構確認
- [x] C5：方向由引擎推導，非規則指定
- [x] C6：監測與優化改為「規劃中」
- [x] C7：方向優先序說明更正
- [x] C8：RSI 規則例子改為實際規則（RSI < 30 + close > MA60 → add）
- [x] C9：禁用詞完整清單（10 個）
- [x] C10：表格格式確認
- [x] C11：「繫累上限」錯字已改
- [x] 狀態改為 proposed

---

## 編製說明

本清單基於 2026-07-26 對代碼的實地驗證編製。每條事實宣稱對應的代碼行號均為精確引用，可直接定位查驗。

**驗證方式**：
1. 逐份讀取相關代碼檔案（`backend/app/`、`frontend/app/`）
2. 對照缺陷清單之正確事實欄逐一核對
3. 記錄每條宣稱的代碼來源（檔案路徑 + 精確行號範圍）

**品質保證**：
- 所有宣稱來自代碼、配置或架構決策（ADR），無任何猜測或推論
- 若無法找到代碼依據，該宣稱已被刪除或改為「規劃中」/「尚未實作」
- 若代碼與文件有衝突，優先以代碼為準

---

編製者：tech-writer  
驗證時間：2026-07-26  
狀態：ready for review
