# ADR-δ 前提查證：code_digest import 圖與 S2 可評估規則數

- 審查者：dev-lead
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. `app/data/quality.py` **不在** code_digest 範圍，也不在範圍內模組的遞移 import 裡。草案 2.1 的前提成立，V-3 可以直接呼叫 `quality.py` 公開化之後的函式。
2. `app/signals/*` 全部 6 個模組（`__init__`、`frame`、`models`、`risk`、`service`、`technical`、`window`）**都不在**範圍內，也不會被遞移 import。所以 2.2「不改 `compute_signals`」和 2.7「`last_defined` 不改」兩處以「未查證」當理由的部分，已經不成立。在呼叫端套用仍然可行，但改不改 `compute_signals`，現在純粹是設計選擇，跟 digest 無關。
3. `app/advice/context.py`、`app/advice/engine.py` **都不在**範圍內。從範圍內可以到達的 advice 模組只有 `app.advice`（`__init__`）和 `app.advice.banned_phrases`，和 ADR-0030 補充三第 3 點的規定一致。
4. 有一個概念要更正：`code_digest` **只對清單內的檔案取雜湊，不涵蓋遞移 import 到的檔案**。`interface.py`、`freshness.py`、`banned_phrases.py` 雖然會被 import 到，但改了它們，digest **不會變**。這也強化了草案 2.1「不得寫在 `PriceBar`／`freshness.py`」的理由：改在那裡，outlook 的語意會變，跨 commit 重算卻偵測不到。
5. 另外發現一個草案 2.4 第 4 點沒處理到的情況：S2 判定為 `unusable` 時，持有部位比重超過 12% 的卡會輸出 `hold`／low，完整度只有 1/12。細節見下方 S2 推算。

## 發現

**A. code_digest 實際涵蓋的檔案**
- `app/forecast/canonical.py:77-78`：`CODE_DIGEST_PACKAGES = ("forecast", "outlook", "dirdef")`、`CODE_DIGEST_FILES = ("data/session_calendar.py",)`。
- `canonical.py:214-231`：`code_digest_files` 只對上面這些套件做 rglob `*.py`，再加上那一個單檔。
- `canonical.py:234-249`：由路徑和 LF 正規化後的 sha256 組成 manifest。不追任何 import。
- 和 ADR-0030 D-2 第 1 點（第 136 行）一致。

**B. 遞移 import 閉包**

我用 AST 掃了範圍內每個檔案的全部 import 節點，包含函式內的 import，也檢查了相對 import 和 `__import__`／`import_module`，兩者都是 0。閉包是：
- digest 涵蓋的：forecast 11 個模組、outlook 7 個、dirdef 7 個，加上 `data/session_calendar`。
- 會被 import 但**不在 digest 內**的，只有 6 個：`app`、`app.data`、`app.advice`（三個 `__init__` 都沒有任何 import）、`app.data.freshness`、`app.data.interface`、`app.advice.banned_phrases`。

連到範圍外的邊只有這幾條：
- `data/session_calendar.py:27` → `freshness`；`:28` → `interface`
- `data/freshness.py:50` → `interface`
- `data/interface.py:11-21` 只 import stdlib 和 pydantic；`advice/banned_phrases.py` 沒有任何 import
- `forecast/definitions.py:63` → `banned_phrases`
- `forecast/recorder.py:81-82`、`forecast/report.py:78`、`forecast/store.py:99` → `freshness`／`interface`
- `outlook/inputs.py:53-54` → `freshness`／`interface`

另外 grep 了範圍內有沒有提到 `app.signals`、`data.quality`、`advice.(context|engine|limits|loader)`，只在 docstring 裡出現（`definitions.py:21`、`banned_phrases.py:5`），沒有 import。

**C. 反方向（範圍外 import 範圍內，這是允許的）**
- `data/quality.py:19` 只 import `app.data.interface`。
- `signals/frame.py:21`、`risk.py:35-37`、`service.py:20-22`、`technical.py:27-39` 只 import `app.data.interface` 和 `app.signals.*`。
- `advice/context.py:29` → `advice/limits.py`。ADR-0030 第 414 行已證實 `limits.py` 會連到 `app.api.kelly_wording`，所以 context 一旦被範圍內 import，K-2 就會破。
- 現有測試 `tests/test_forecast_boundaries.py:1128-1131` 已經斷言 outlook 連不到 `app.advice.context`。`quality` 和 `signals` 目前沒有對應的 import 圖測試，草案 K-5 新增的測試可以把這兩者一起列進去。

**D. 第 4 題的幾項確認**
- `MIN_COMPLETENESS_FOR_ACTION = 0.5`，定義在 `advice/engine.py:113`。
  - 同一處還有 `HIGH_COMPLETENESS = 0.8`（`:115`）、`MEDIUM_COMPLETENESS = 0.5`（`:118`）。
  - 閘門在 `engine.py:372-375`：`if not evaluated or (completeness < MIN_COMPLETENESS_FOR_ACTION and (action == "add" or not matched))` → `insufficient_data`。
  - 完整度算法在 `:364`：`len(evaluated) / len(rules.rules)`。
- `take_profit` 歸在 `defensive`（`engine.py:93`）。
- `PriceBar` **有**驗證 volume ≥ 0（`data/interface.py:77-82`），型別是 `int`（`:65`）。
  - 它只驗 `as_of` 帶時區、volume、`symbol`／`source`／`currency` 不可空白。
  - OHLC 的正值和 high ≥ low 這類一致性**完全沒驗**。

**E. `rules/default.yaml`（1.1.0）12 條規則用到的欄位**

| # | id | action | 欄位 |
|---|---|---|---|
| 1 | uptrend_ma_stack | add | ma5、ma20、ma60、close |
| 2 | macd_histogram_positive | add | macd.histogram（EMA）、close、ma20 |
| 3 | rsi_oversold_with_trend | add | rsi14（Wilder）、close、ma60 |
| 4 | downtrend_ma_stack | reduce | ma5、ma20、ma60 |
| 5 | price_below_ma60 | reduce | close、ma60 |
| 6 | rsi_overbought | reduce | rsi14 |
| 7 | kd_high_level_weakening | reduce | kd.k、kd.d（遞迴 1/3 平滑，`technical.py:333-380`） |
| 8 | bollinger_upper_breach | take_profit | bollinger.percent_b（20 根） |
| 9 | drawdown_protection | reduce | drawdown.current（整個觀察視窗） |
| 10 | deep_drawdown_stop | stop_loss | drawdown.current |
| 11 | volume_spike_watch | hold | volume_z.last（20 根） |
| 12 | concentration_watch | hold | position.weight |

- **完全不靠歷史日線的只有第 12 條**。`position.unrealized_pnl_pct` 沒有任何規則用到。
- **沒有任何一條規則只靠 close**：用到 close 的規則都同時需要 ma20 或 ma60。所以 2.4 第 2 點保不保留 close，都不會讓可評估的規則數增加。
- 注意：`close` 來自 `PortfolioContext.close`（`context.py:142`），不是 signals；`position.weight` 來自 `portfolio/summary` 的估值（`limits.py:873-879`、`book.py:1403`）。那個估值用的價格會不會也是同一根壞的最新 bar，這次沒有查。

**F. S2 下可評估規則數的推算**
- **`unusable`**：最多 **1/12 ≈ 0.083**，只剩第 12 條，前提是 `total_equity_twd` > 0 且有市值。
  - 尚未持有的標的（weight 0）或比重未超過 12%：第 12 條評估了但沒命中 → 走既有閘門變成 `insufficient_data`。這是正確的結果。
  - **持有比重超過 12%**：第 12 條命中，動作是 `hold`（屬 neutral），`matched` 不是空的，動作也不是 `add`，所以**不會被 `:372-375` 擋下**。結果是 `hold`，信心依 `_confidence`（`engine.py:296-299`）為 `low`，完整度 0.083。
  - 草案 2.4 第 4 點只處理「0 條命中」和「防禦型命中」，**沒有涵蓋「只有 neutral 規則命中」這種情況**。
  - 卡上的風險上限仍照常評估：cap 4 不可評估，cap 1 不受影響。
- **`gap`**（H_f 凍結前，遞迴類一律視為受影響；回撤用整個視窗，一律受影響）：

| 可疑的那一對落在哪裡 | 剩下可評估的規則 | 完整度 |
|---|---|---|
| 最近 20 根以內 | 只剩第 12 條 | 1/12 |
| 21～60 根 | 第 8、11、12 條 | 3/12 |
| 61 根以前，但仍在視窗內 | 第 1、4、5、8、11、12 條 | **6/12 = 0.5** |

  最後一種情況剛好等於門檻，0.5 不小於 0.5，所以 `add`（第 1 條）的路徑仍然開著。邊界是否差一根，要看 H_f 的精確定義。這一點建議 tech-architect 明文規定。

## 驗證

- 讀過的檔案：
  - `docs/adr/0030-*.md`（Grep code_digest，以及第 414-428、437-446 行）
  - `app/forecast/canonical.py`（第 1-30、60-90、200-260 行）
  - `app/data/interface.py` 全文
  - `app/advice/engine.py`（第 1-125、280-300、330-380 行）
  - `app/advice/context.py` 第 1-166 行
  - `app/advice/limits.py` 第 795-890 行
  - `app/advice/rules/default.yaml` 全文
  - `app/advice/book.py` 第 1262-1420 行節錄
  - `app/signals/technical.py`、`frame.py` 節錄
  - `tests/test_forecast_boundaries.py` 第 1110-1135 行
  - 草案第 186-235、399-457 行
- 在範圍內各檔、`freshness.py`、`interface.py`、`banned_phrases.py`、三個 `__init__`、`quality.py`、`signals/*.py` 上，用 grep 列出 import 開頭的行。
- AST 閉包腳本放在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/closure.py`，只解析原始碼、不 import。
  - 第一次用 `python3.11 -I` 跑，失敗：`SyntaxError`，原因是 `type _Scalar = ...` 是 3.12 才有的語法。
  - 改用 `python3.13 -I` 跑成功，輸出就是 B 節的閉包和邊清單。沒有出現任何相對 import 或動態 import。
- 沒跑 pytest，沒裝套件，沒連外網，沒碰 `data/` 和 `.env*`，沒對 `apps/` 做遞迴搜尋。`git status --short` 是空的，分支 `product/stock-desk`，HEAD 是 `3c1386bd`，沒有任何變更。

## 下一步

1. **tech-architect**：
   - 草案「範圍限制」第 76 行改寫成兩層：「digest 涵蓋的檔案」和「會被 import 但不在 digest 內：interface／freshness／banned_phrases」。
   - 2.1 的前提已查證成立，可以刪掉「如果在」的備案。
   - 2.2、2.7 的理由改成「已查證不在範圍內」，要不要改 `compute_signals` 改為設計取捨。
   - 補上 2.4 第 4 點沒涵蓋的「判定不是 usable、只有 neutral 命中」的處置。
   - 明文規定 gap 情況下完整度剛好 0.5 時的處理。
2. **qa-automation 或 dev-lead**（登記後的 PR）：K-5 的 import 圖測試要明列 `app.data.quality`、`app.signals`、`app.advice.context`、`app.advice.engine`，以及新的 `app.barverdict`，都不得被 digest 範圍連到。可以沿用 `tests/import_graph.py` 的 `reachable_app_modules`／`offenders`。
3. **data-engineer**：`PriceBar` 的 volume 已經驗證，這一項可以從未決事項移掉。OHLC 一致性沒有任何驗證，這一項仍待處理。
4. 還沒查證：`position.weight` 用的估值價格是否來自同一根最新 bar。如果是，S2 下第 12 條也可能吃到壞值。建議 tech-architect 決定要不要派人只讀查證 `app/portfolio/valuation.py`。
