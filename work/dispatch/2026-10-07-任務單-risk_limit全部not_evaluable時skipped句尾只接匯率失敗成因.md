# 任務單：risk_limit 全部 not_evaluable 時 skipped 句尾只接匯率失敗成因（S-B2 §7 另案）

- 日期：2026-10-07　狀態：**draft**　等級：low　依賴：S-B2 落地之後（同一函式 `_limit_outcome`）
- 來源：風控 S-B2 審查列管 1（否決 creative-lead「一律不接 snapshot.reason」，前提有誤）→ tech-architect 唯讀評估（HEAD 5f57551 工作樹）。
- 流程：dev-lead 實作 → qa-reviewer（Codex 環境不可用時註明）→ risk-compliance-officer **單項核對**（無新造字面，creative-lead 知會即可）→ done。

## 問題
全部 not_evaluable 的 skipped 字面「監看的上限（{names}）缺少輸入，無法判定是否違反。」句尾接整個 `snapshot.reason`（`snapshot.py:130-149` ＝ `join(layer_note, loaded.reason, book.fx_note)`）。真偽矩陣：
| 情境 | 句尾內容 | 當成因 |
|---|---|---|
| FRESH＋TWD | 空；多來源拼接時有 `loaded.reason` | 拼接句為錯誤歸因 |
| cached | `layer_note` | 錯誤歸因 |
| 外幣匯率成功 | `FX_APPLIED_NOTE` | 錯誤歸因且方向相反 |
| 外幣匯率失敗 | 三種失敗句之一（可能黏 layer／loaded） | 對 `per_trade_loss` 為真；對第 1 條方向對範圍不準；指定 Kelly／產業／總曝險時錯誤歸因 |
| A′（close 0／負／NaN） | 視情境 | 比照 R-B1：不接 |
| 無 bars／loader 例外 | 不走此分支（L234-235 固定句） | 沿用 10-06 裁定 |

**補充事實**：只有第 4 條 `per_trade_loss` 用到 snapshot 的 close／ATR（`limits.py:974-985`；`held_shares` 僅 quantity 缺值時 fallback 用價格 L686-693）；第 1／2／3／5 條不碰 close／ATR。valuator 匯率失敗會讓第 1 條 not_evaluable，但其真成因句 `UNVALUED_POSITIONS_NOTE`／`SYMBOL_UNVALUED_NOTE` 只在 `book.notes`，從未進 reason。持倉多幣別時 `fx_note=None`，成因句只在 `book.notes`（既有缺口，列管）。

## 方案（tech-architect 定案：(A) 收斂版）
- **(A)**：snapshot 新增專用欄位只放匯率失敗成因；engine skipped 句尾只讀該欄位，加 **A′ 閘門**（close 存在但不可用 → 不接）與 **範圍閘門**（監看且 not_evaluable 的上限含吃價格／ATR 者才接）。
- 否決 (B) 字串比對白名單（佔位符切不乾淨、engine 需 import `book` 或複製字面、文案一改即 fail-open、解決不了範圔）。
- (C) 不動可為暫態，但四類錯誤歸因持續存在於 API JSON；F-4 若把 skipped 原因拉進 UI 風險升級。
- (D) 另案：skipped 改接各上限自己的 `check.detail`（最精確、可順帶解決風控列管 2「缺少輸入」對 ETF／淨值過期不精確），需 creative-lead 起草＋風控逐字審。

## 對既有約束
ADR-0020 K-6：`snapshot.py` docstring（L57-59、L71-75）、`SymbolSnapshot.reason` 註解（`engine.py:77-80`）、`test_alerts_snapshot.py` 模組 docstring（L3-8）須同步。K-3：常數放 `app.advice.limits`（engine 已 import），engine 不 import `app.advice.book`。API schema：`RuleOutcome.reason` 仍單字串，`_evaluation_response` 逐欄位組裝不外露新欄位。字面：主句一字不動，句尾只會是三個既有失敗常數之一或空白，不新造；仍屬 API 可見字面變動 → 風控單項核對。不需新 ADR。

## 實作約束（逐條可檢查）
- **K-1**：`SymbolSnapshot` 新增 `str | None` 欄位預設 None（建議名 `price_cap_cause`）；`build_snapshot` 設值固定為 `book.fx_note if book.fx_rate is None else None`，只能是 `NO_FX_QUOTE_NOTE`／`FX_UNAVAILABLE_NOTE`／`FX_PAIR_MISMATCH_NOTE`（格式化後）或 None；不得混入 `layer_note`、`loaded.reason`、`FX_APPLIED_NOTE`、`book.notes` 其他句。
- **K-2**：`reason`、`fx_disclosure`、`data_disclosure` 組成與值不變；既有 `test_alerts_snapshot.py` L142、L186、L196-211、L234、L245 斷言不得修改且須綠。
- **K-3**：`_limit_outcome` 全部 not_evaluable 分支：先判 A′（`snapshot.close is not None and usable_close(snapshot) is None`，同 price／signal 路徑的 `usable_close`）→ 句尾空白；非 A′ 時僅當 `watched` 中 not_evaluable 的 id 與 `PRICE_INPUT_LIMIT_IDS` 有交集才接 `" " + 新欄位`；主句不改；此分支不得再讀 `snapshot.reason`。
- **K-4**：`app/advice/limits.py` 新增 `PRICE_INPUT_LIMIT_IDS: Final[frozenset[str]] = frozenset({"per_trade_loss"})`（名稱可議）＋防漂移測試：同一 context 將 close／atr 設 None 前後比較 `evaluate_limits`，狀態有變的上限 id 必為此集合子集；engine 不得寫死 `"per_trade_loss"`。
- **K-5**：engine 不得 import `app.advice.book`，不得字串比對 note 種類。
- **K-6**：同步 docstring／註解（`snapshot.py`、`SymbolSnapshot` reason 與新欄位、`_limit_outcome` S-B1 註解改寫為兩道閘門、`test_alerts_snapshot.py` 模組 docstring）。
- **K-7**：只動 risk_limit 全部 not_evaluable 的 skipped 分支；S-B2 quiet、fired、price／signal skip、L234-235、L241-242 字面不動。
- **K-8**：排在 S-B2 落地後；落地後跑 `test_advice_wording.py`、`test_alerts_snapshot.py`、`test_alerts_api.py`。

## 驗收條件
1. **Given** 外幣持倉、close 可用、匯率失敗（三種失敗句參數化）、資料層 cached_stale 且帶 `loaded.reason`，`limit_id` 為 `per_trade_loss` 或全部 not_evaluable 的 `any`。**When** 評估。**Then** skipped，reason 完全等於主句＋一個半形空格＋該失敗句（逐字），不含 `layer_note`／`loaded.reason` 任何片段。
2. **Given** 監看上限全部 not_evaluable 且 (a) 匯率成功、(b) TWD＋cached 或拼接、(c) 匯率失敗但 `limit_id` ∈ {kelly_fraction, sector_weight, gross_exposure, single_position_weight}。**Then** reason 完全等於主句（以「無法判定是否違反。」結尾），負向斷言不含 `FX_APPLIED_NOTE`、「資料來自」、拼接句片段。
3. **Given** A′（close 0／-1）× FRESH／cached × TWD／外幣成功／外幣失敗。**Then** risk_limit skipped reason 完全等於主句；迴歸：`snapshot.reason`、price／signal skip、fired、S-B2 quiet 字面不變；K-4 防漂移測試綠。

## 與 R-B1／S-B1／S-B2 的一致性
R-B1 原則（已知成因為他事時不讓 reason 句尾冒充成因、回既有固定字面、閘門用同一 `usable_close`）原樣套用到第三條路徑；S-B1 的 `cause` 無關附註由 K-3 消除、註解依 K-6 改寫；不碰 S-B2 quiet，主句口徑不變，不觸發 S-B2 失效條件 4／8。

## 列管（不在本單）
1. (D) skipped 接 `check.detail`，與風控列管 2 合併評估（creative-lead＋風控）。
2. 持倉多幣別成因句未送到 snapshot。
3. 本單後 `FX_APPLIED_NOTE` 在 reason 幾乎無讀者且 A′ 時為不實陳述；可另案自 reason 移除（同步改 `test_alerts_snapshot.py:203-211`、送風控）。
4. snapshot `fx_provider` 與 valuator 匯率來源是否同一來源（scheduler／API 接線），請 dev-lead 確認。
5. F-4 若把 skipped 原因拉進 UI，本單字面隨失效條件重審。

---

## 進度（coordinator 轉錄）
- **2026-10-07 落地 commit（本 commit 之後一筆）**：dev-lead 依 (A) 收斂版實作，K-1～K-8 自檢全符合；519 passed、全套 4496 passed、ruff／format／mypy 綠；四組突變皆被測試擋下。列管 4 已確認 snapshot 與 valuator 的 fx_provider 同為 `deps._default_fx_provider()` 單例。
- **qa-reviewer PASS**（無 BLOCKING）。low：AST import 檢查漏 `from app.advice import book` 寫法（建議併入 alias）；AST 字面檢查為 best-effort；測試註解含中文編號引用（有先例，建議改英文）。
- **風控單項核對 APPROVE**：落地符合方向；代價（valuator 匯率失敗使第 1 條 not_evaluable 時匯率提示消失）接受——原提示「價格與 ATR 相關的上限不計算」對第 1 條本是錯誤成因，主句仍誠實且 skipped 不被讀成 passed；API 可見字面變動放行（主句不變、句尾值域三個既有核可失敗句或空白）。suggested：per_trade_loss 且 valuator 亦失敗時匯率句非唯一成因（併 (D)）；`test_alerts_snapshot.py` docstring L11「last two tests」描述漂移順手修。失效條件錨點 7 項：`PRICE_INPUT_LIMIT_IDS` 變動或任何上限開始／停止讀價格（以 `test_advice_limits.py` L189-204 為錨）；`snapshot.py:158` 賦值條件改變或欄位可被設成三常數以外；三失敗常數字面變動（特別是拿掉自我限定範圍）；主句變動／重讀 reason／拿掉任一閘門／A′ 不用共用 usable_close；skipped reason 進 UI 或推播；(D) 落地取代；S-B2 quiet 被附加句尾。
- 狀態：**done**（審查通過）。列管 1～5 照舊；(D) 併風控 S-B2 列管 2 與本次 suggested。
