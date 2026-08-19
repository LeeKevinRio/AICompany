# C5 Kelly — tech-architect 架構收斂裁決(D-9 意見整合)

- **日期**:2026-08-19
- **作者**:tech-architect(協調人代為落檔)
- **輸入**:`work/stock-desk-C5-Kelly-D9-量化意見.md`、ADR-0006、`work/stock-desk-C5-Kelly-架構評估.md`,以及 `engine.py`/`report.py`/`limits.py`/`api/backtest.py`/`app/alerts/store.py`/`app/settings/net_worth.py`(既有慣例對照)

---

# 評估摘要(結論先行)

1. **f\* 信賴區間**:不放 `app/api/kelly.py` 做數值運算(否決 quant 的第一建議),也不放 `app/advice`(否決第二建議)。**採第三方案:新增 `app/backtest/episodes.py`,回合抽取+p/b 估計+bootstrap 都在那裡,f\* 算式以「注入 `fraction_fn`」取得**,由 `app/api/kelly.py` 傳入 `limits.kelly_fraction`。三個既有邊界(D-5 唯一算式、約束 13、advice 與 backtest 互不相依)全數保住,且不新增任何跨域 import。
2. **`kelly_import_attempts`**:**與 D-2 相容,採納**。D-2 管的是「生效輸入」的單列規則,attempts 記的是「使用者嘗試事件」,兩者是不同實體;repo 已有 append-only 先例(`alert_events`)。歸 `app/kelly/`,但**必須獨立檔案 `app/kelly/attempts.py`**,且與生效值讀寫路徑硬隔離。
3. **21 條增補**:修改 3 條全數 accept(其中 2 條 with-changes)、新增 10 條 accept 8/accept-with-changes 2、reject 0;D-2 追溯欄位修訂 accept。另加 **32–37 共 6 條**(quant 未觸及的邊界風險)。
4. **`report.py` 微額 fill 污染**:**C5 依回合層計算足以隔離**,前提是再補兩個封口(gate 不得用 `num_closing_trades`;揭露不得取用 fill 層數字)。既有欄位修復:**在 report 層修=bug fix,不需 ADR**;**若改到 engine(no-trade band/再平衡門檻)=需新 ADR**。
5. **ADR-0006**:**原地出修訂版,不出 ADR-0007、不用附錄補記**。理由:ADR-0006 狀態是 `proposed`,ADR-0001 只禁「生效後原地改寫」;附錄補記會讓本文的 D-2/D-5/D-6 留下已知錯誤文字,讀者只讀本文。**唯一例外**:若 CEO 在修訂落檔前已核可現行版本,則改走 ADR-0007(supersedes)。

---

# 裁決 1|f\* 信賴區間的計算位置

## 方案比較

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| A. `app/api/kelly.py` 直接組裝 bootstrap(quant 首選) | 不新增模組;D-8 已允許 api 觸及兩邊 | 路由層變胖;數值邏輯要靠 HTTP 測試才測得到;本 repo 路由一律薄 | 迴圈日後被複製到第二處,f\* 算式唯一性靠人自律 |
| B. `app/advice/kelly_estimate.py` 純函式(quant 次選) | 可直接 import `kelly_fraction`,唯一性最直觀 | p/b 估計量會出現第二份,否則得開 `advice → backtest` 邊 | 風控政策模組開始依賴回測模組;manual 路徑被綁進 pandas/numpy 堆疊 |
| C. `app/kelly/estimate.py` | 與儲存同模組,好找 | 仍受約束 13 限制、一樣要注入;讓「儲存模組」依賴回測引擎 | `app/kelly` 從 source-agnostic 變成 backtest-coupled |
| **D. `app/backtest/episodes.py` + 注入 `fraction_fn`(採用)** | 樣本定義、p/b、bootstrap 三者同源同檔;不新增任何跨域 import;純函式可單測;api 仍是唯一組裝點(符合 D-8) | 多一層注入的間接性 | 注入被人補上 default 實作就破功 → 以「keyword-only 必填、無 default」+守門測試封住 |

## 決策(D-5a,取代約束 28 的暫置)

- 新增 `app/backtest/episodes.py`,負責四件事且**只有**這四件事:
  1. 由 `BacktestResult` 抽出持倉回合(entry/exit index、回合已實現損益、回合報酬率);
  2. OOS 完全包含歸屬與各項計數;
  3. 由回合報酬率清單算 **p 與 b(全 repo 唯一定義)**;
  4. Wilson 區間與 joint bootstrap 區間。
- **f\* 算式不進入這個模組**。bootstrap 以注入取得:

```python
def bootstrap_fraction_ci(
    returns: Sequence[float],
    *,
    fraction_fn: Callable[[float, float], float | None],  # keyword-only, no default
    seed: int,
    draws: int,
    alpha: float = 0.05,
) -> FractionInterval: ...
```

- `app/api/kelly.py` 是唯一組裝點,傳入 `app.advice.limits.kelly_fraction`;點估計 f\* 也走同一個 callable。
- 依賴方向維持不變且不新增邊:`app/backtest` 不 import `app/advice`/`app/kelly`;`app/advice` 不 import `app/backtest`;`app/kelly` 不 import `app/advice`/`app/backtest`;**只有 `app/api/kelly.py` 同時觸及三者**(D-8 擴充為 `advice ← api → {kelly, backtest}`)。
- `report.py` 的新顯示欄位(回合層 p/b)也從 `episodes.py` 取,因此 p/b 估計量在 repo 中只有一份。

## f\* 唯一性怎麼維持(三道,皆可被 qa-reviewer 檢查)

1. `fraction_fn` 為 keyword-only、無 default、無 fallback 分支;`episodes.py` 內不得出現任何 `p - (1 - p) / b` 形式的算術。
2. **守門測試(必要)**:傳入回傳常數 0.5 的 `fraction_fn`,斷言 CI 為退化區間 `[0.5, 0.5]`;再傳入計數用 spy,斷言呼叫次數 == `draws`(+1 次點估計)。內部若偷藏算式,這兩個測試必掛。
3. qa-reviewer checklist 增一項:`rg -n "1(\.0)? - .*win_rate|1(\.0)? - p\b" apps/stock-desk/backend/app` 命中處只允許 `advice/limits.py`。

## 附帶裁定(quant 未問但非決不可)

- **退化抽樣**:某次重抽 `n_loss == 0` 時 b 未定義。**禁止靜默丟棄**(丟棄會截斷上尾、系統性低報區間寬度)。預設規則:以 `b → ∞` 之極限記 `f* = p̂`,並落地 `bootstrap_degenerate_draws` 計數。**此為統計處理,請 quant 回覆確認或改規則**;架構上的不可讓步點只有「不得靜默丟棄、必須落地計數」。
- **區間是揭露專用**:`p_ci_*` / `f_star_ci_*` 一律不得進入 `kelly_allowed_weight`、不得改寫生效 p/b、不得作為任何 clamp 依據(與約束 6 同級)。
- **seed**:`bootstrap_seed = int(spec_hash[:8], 16)`,與 attempts 的 `spec_hash` 同源。可重現性宣告範圍必須寫明是「同一份 spec **且** 同一批 bars」——bars 會被重抓,這點不能對使用者謊稱。

---

# 裁決 2|`kelly_import_attempts`

## 與 D-2 是否相容:相容,理由三點

1. **D-2 管的是不同實體**。D-2 的「不保留歷史」解決的是「哪一個值現在生效」只能有一個答案,並用同列的 `backtest_*` 原始值滿足追溯。`kelly_import_attempts` 記的是**使用者的嘗試事件**(含從未成為輸入的 422),不是生效值的版本鏈。
2. **repo 已有同性質先例**:`app/alerts/store.py` 的 `alert_events` 就是 append-only,理由與此處完全一致;`provider_quota_usage` 同型。
3. **不相容的那條線已封住**:張力所在是「attempts 事實上可反推出生效值的歷史」。硬約束:**任何回答『目前生效輸入是什麼』的程式路徑,禁止讀 attempts;attempts 的唯一讀取用途是計數(K_observed / K_distinct_specs)與未來 P1 的分佈顯示**。

## 歸屬模組

`app/kelly/`,但**必須是獨立檔案 `app/kelly/attempts.py`(`KellyAttemptStore`)**,不得與 `store.py`(`kelly_inputs`)共用同一個 class(讓讀寫隔離用 grep 就能檢查)。同時新增 `app/kelly/sample_gate.py`,**比照 `app/settings/net_worth.py` 的既有型態**(門檻常數+拒收訊息常數+`review_*` 回傳),介面只吃純量 `(n, n_win, n_loss)`,因此 `app/kelly` 不需要 import `app/backtest`。

## Schema 要點

```sql
CREATE TABLE IF NOT EXISTS kelly_import_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,              -- upper-normalized, same rule as kelly_inputs
    market TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    request_spec TEXT NOT NULL,        -- canonical JSON of the validated BacktestRequest
    spec_hash TEXT NOT NULL,           -- sha256 of request_spec; also the bootstrap seed source
    outcome TEXT NOT NULL,             -- 'ok' | 'rejected'  (gate verdict, NOT storage result)
    reason_code TEXT,                  -- NULL when ok
    win_rate REAL, payoff_ratio REAL, kelly_fraction REAL,
    oos_round_trips INTEGER, oos_win_trips INTEGER, oos_loss_trips INTEGER,
    oos_excluded_boundary_trips INTEGER, oos_open_trip_at_end INTEGER,
    oos_start_date TEXT, oos_end_date TEXT, oos_observations INTEGER,
    f_star_ci_low REAL, f_star_ci_high REAL,
    attempted_at TEXT NOT NULL         -- server UTC ISO
);
CREATE INDEX IF NOT EXISTS idx_kelly_attempts_symbol_time
ON kelly_import_attempts (symbol, market, attempted_at DESC);
```

要點六條:
- **同一個 DB 檔、同一套連線紀律**(`STOCK_DESK_DB_PATH` / `contextlib.closing` / 每次操作一條連線),比照 `app/alerts/store.py`。
- **模組內不得出現 `UPDATE` 或 `DELETE` 語句**(grep 可驗)。`DELETE /api/kelly-inputs/{symbol}` **不得**連帶刪 attempts——刪了就是把 K 往低報。
- **`outcome` 定義為「閘門判定」而非「是否寫入成功」**:attempts 可先寫、輸入列後寫,不需跨 store 交易。
- **422 必寫**:任何走到 import-backtest 的請求(通過 request 模型驗證後)都必須產生一列;attempts 寫入失敗則整個 import 失敗(500),不得靜默放行。
- **K 的定義寫死並顯示定義**:`K_observed = COUNT(*) WHERE symbol=? AND market=?`(含 rejected、含所有策略、不設時間窗);同時落地 `K_distinct_specs = COUNT(DISTINCT spec_hash)`。**兩個都存、以 K_observed 為主顯示,並把定義寫進揭露**——不得只顯示對系統比較好看的那個。
- **無祕密**:`request_spec` 不含任何金鑰,可安全落地。

## 是否需要 ADR-0006 修訂版

需要,併入同一次修訂(見裁決 5),不單獨開 ADR。CEO 核可標的即為修訂後全文。

---

# 裁決 3|quant 增補逐條裁定

## 3.1 修改既有條文

| 條 | 裁定 | 理由 |
| --- | --- | --- |
| 7 | accept-with-changes | 計數單位改「完整回合數」正確且必要;但 20 是 CEO 風險胃納裁決,約束只能寫成具名常數+分項 reason_code,不得寫死成既成事實。 |
| 9 | accept-with-changes | 計量單位補述全採;但欄位名改為 `round_trip_payoff_ratio`/`round_trip_win_rate` 成對,避免與 fill 層 `win_rate` 被讀者配成一組。 |
| 19/20 | accept-with-changes | 追加送審句全採,並補:422 訊息本身是常態路徑文案、一併送審;選擇偏誤句 MVP 只能定性,引用 §3.1 具體數字需先把模擬表固化為版控常數(P2)。 |

## 3.2 新增條文 22–31

22 回合定義 accept-with-changes(ε 為具名常數 `POSITION_EPSILON`);23 歸屬規則 accept-with-changes(`oos_start/oos_stop` 取自 fold 幾何,禁由報表日期字串回推);24 計量分母 accept;25 禁用既有欄位 accept-with-changes(追加禁 `num_closing_trades` 當門檻計數、禁揭露文案取用 fill 層數字);26 四項測試 accept-with-changes(追加三項守門測試);27 區間落地 accept-with-changes(補退化抽樣、seed、宣告範圍、不得回饋計算);28 單一算式位置 accept-with-changes(定案為 episodes.py+注入);29 attempts 表 accept-with-changes(補檔案歸屬、schema、隔離);30 選擇偏誤顯示 accept-with-changes(K 定義寫死、兩種 K 都落地、K=1 顯示短版);31 同源約束 accept。**reject:0 條。**

## 3.3 D-2 追溯欄位修訂

**accept。**`oos_closing_trades` 受微額 fill 污染,落地它會讓追溯欄位本身誤導稽核者。改為五個回合層計數,並連帶修 D-6 的 `KellyInputs`。ADR-0006 仍為 proposed,屬核可前修訂,不觸犯 ADR-0001。

---

# 裁決 4|`report.py` 微額 fill 污染

**(a) C5 回合層計算足以隔離:是,加兩個封口即足。**污染是**分段/計數**的假象,不是損益的假象——回合層把區間內所有 fill 的 `realized_pnl` 加總,損益仍完整計入,只是不再各自算成獨立交易。滿足:①樣本單位=回合(約束 22–24);②`n / n_win / n_loss` 全部來自回合;③揭露文案不得引用 fill 層 `win_rate`/`profit_factor`——則 C5 與污染完全脫鉤。quant 的加總不變量測試就是隔離的證明。

**(b) 既有欄位修復定性:**
- **在 `report.py` 層修(改 `_trade_stats` 統計單位)= bug fix,不需 ADR**;但它改變了已對使用者顯示、風控已核可脈絡下的數字,必須:PM 立任務排期、risk-compliance-officer 重審顯示語意、附回歸對照(新舊數字並陳)。
- **若動到 engine(no-trade band/再平衡最小門檻)= 需新 ADR**:改變全系統所有回測結果、使先前報告不可比、使 quant §2.1 證據失效。
- 兩者都**不阻擋 C5 開工**;C5 只需遵守約束 25。

---

# 裁決 5|ADR-0006 修訂方式

**原地出修訂版(同檔、同編號),不出 ADR-0007,不用附錄補記。**理由:(1) ADR-0006 為 `proposed`,ADR-0001 只禁「生效後原地改寫」;(2) 附錄補記會讓本文 D-2/D-5/D-6 留下已知錯誤文字;(3) 讓 CEO 核可一份「本文與附錄互相矛盾」的 ADR 是不負責任的。**唯一例外**:CEO 已核可現行版本時改走 ADR-0007(supersedes),請協調人先確認核可狀態再落檔。

修訂要點(全文由 tech-writer 依本檔與增量清單施工):

- **Context 事實 5**:`report.py` 的 `win_rate`/`profit_factor` 以 fill 為統計單位,每日再平衡使滿倉期間每日產生微額賣出,實測 10 次真實進出產生 72 筆 closing fill(中位 NT$0.02),fill 層與回合層 p 最大差 21pp、風控額度差 50%(quant D-9 §2.1)。此問題超出 C5 範圍,但決定了 C5 的 p/b 必須另立回合層欄位。
- **Options 追加兩組方案列**:f\* CI 位置三案+attempts 表兩案(含「不記錄嘗試」對照案),優缺點風險如裁決 1/2 之表。
- **D-2 改寫**:`app/kelly/`(models.py + store.py + sample_gate.py + attempts.py);追溯欄位改回合層五計數(`oos_round_trips`/`oos_win_trips`/`oos_loss_trips`/`oos_excluded_boundary_trips`/`oos_open_trip_at_end`),刪 `oos_closing_trades`;新增 p_ci_low/p_ci_high/f_star/f_star_ci_low/f_star_ci_high/bootstrap_seed/bootstrap_draws/bootstrap_degenerate_draws/spec_hash/low_sample_warning/k_observed_at_write;落地的 `f_star` 僅供稽核,**上限計算一律以生效 p/b 重新呼叫 `kelly_fraction`,禁止讀取此欄位**;新增 append-only `kelly_import_attempts`(含 422 被拒者),禁 UPDATE/DELETE、DELETE 輸入不連坐、禁用於回答生效值;過期列不自動刪除。
- **D-3 422 條件**:加 `n < MIN_OOS_ROUND_TRIPS`、`n_win < 5`、`n_loss < 5`,分項 reason_code+實際數字;`MIN_OOS_ROUND_TRIPS` 待 CEO 裁決(quant 建議 20,並列 50;20≤n<50 軟性警示帶寫入但強制 `low_sample_warning`);**422 是常態路徑而非錯誤**,UI 與文案照此設計。
- **D-5 補寫**:report.py 新增 `round_trip_win_rate`/`round_trip_payoff_ratio`(回合層,分母=進場前一日 equity),既有欄位語意不動但 C5 禁止取用,任何以 PF 充當 b 或以 fill 層數字充當 p/b 視為 BLOCKING;新增 `app/backtest/episodes.py`(唯一 p/b 與回合定義,f\* 以 keyword-only 必填 `fraction_fn` 注入);區間為揭露專用。
- **D-6 KellyInputs**:win_rate / payoff_ratio / source / age_days / anchored_at / strategy_id / oos_start_date / oos_end_date / **oos_round_trips** / **ci_includes_no_edge**(`f_star_ci_low <= 0` 的布林事實,由 `app/api/kelly.py` 算好傳入);`oos_closing_trades` 移除;CI 數值、bootstrap 參數與其餘樣本結構欄位**不進 PortfolioContext**,`limits.py` 只得分支、不得計算統計量。
- **D-9 改為已解除**:quant 2026-08-19 出具意見(`work/stock-desk-C5-Kelly-D9-量化意見.md`):(a) 硬門檻採完整回合數,n_win/n_loss 各 ≥5,n 值待 CEO 裁決;(b) b=回合報酬率均值比,OOS 完全包含歸屬、以 index 判定,跨界與期末未平倉排除並分別計數;(c) 揭露七要點,MVP 緩解=attempts+K_observed+區間落地。回測帶入路徑在 `MIN_OOS_ROUND_TRIPS` 定值後即可開工;其餘結論已納入 D-2/D-3/D-5/D-6。
- **Consequences 追加**:attempts 單調成長且永不刪除是刻意的(刪除會讓 K 低報);「樣本外」在本系統只代表區段位置、不代表已防過擬合(walk-forward 不做參數擬合),此事實成為強制顯示內容;排除跨界回合優先移除存續較長回合(實測 1.73 倍),照實寫進已知限制、不得包裝成保守作法;report.py 既有欄位污染另立任務(report 層修=bug fix 不需 ADR、engine 層修需新 ADR)。

---

# 對實作的約束|最終增量清單(併入 `work/stock-desk-C5-Kelly-架構評估.md`)

> tech-architect 2026-08-19 收斂 quant D-9 意見後的定版增量。只列有變動與新增者,其餘 1–6、8、10–18、21 條不變。

**第 7 條改為**:import-backtest 422 且不寫入之情況:`status != ok`、OOS p/b 為 None、body symbol/market 與路徑不符、**OOS 完整回合數 `n < MIN_OOS_ROUND_TRIPS`、獲利回合 `n_win < MIN_OOS_WIN_TRIPS(=5)`、虧損回合 `n_loss < MIN_OOS_LOSS_TRIPS(=5)`**。三常數宣告於 `app/kelly/sample_gate.py`(比照 `net_worth.py` 型態),`MIN_OOS_ROUND_TRIPS` 之值為 CEO 裁決(quant 建議 20、並列 50)。每道閘門有各自 `reason_code`(`low_round_trips`/`low_win_trips`/`low_loss_trips`/`pb_none`/`symbol_mismatch`/`insufficient_data`),422 訊息指名閘門並附實際數字。本檔中「成交筆數」一詞全面改為「完整回合數」。

**第 9 條改為**:禁以 `profit_factor` 當 b(含變數命名混用);`report.py` 的 PerformanceMetrics **新增** `round_trip_win_rate` 與 `round_trip_payoff_ratio`,統計單位為**完整持倉回合**(非 closing fill),分子分母為**回合報酬率**(回合已實現損益 ÷ 進場前一日 equity)。兩新欄位成對命名(禁止只叫 `payoff_ratio`)。既有 `win_rate`/`profit_factor` 的值與語意不得更動。

**第 19/20 條追加送審句**:(a) 區間顯示句,含「此區間涵蓋『沒有優勢』的可能」;(b) `K_observed` 選擇偏誤句(K=1 亦須顯示短版);(c)「本系統 walk-forward 不做參數擬合,`out_of_sample` 僅代表區段位置」句;(d) 422 樣本不足說明句——**422 是常態路徑,其訊息屬面向使用者文案,一併送審**;(e)「歷史頻率不等於下一筆的機率」正面處理句。**限制**:MVP 選擇偏誤句只能定性,不得引用 quant §3.1 具體數字,除非模擬表已固化為版控常數且產生腳本入版控(P2)。

**新增第 22 條(回合定義)**:以累計持股跨越 `POSITION_EPSILON`(具名常數,值 1e-9,絕對股數容差,須註明理由)判定進出場;回合已實現損益為 `[entry_idx, exit_idx]` 區間內所有 fill 的 `realized_pnl` 之和。

**新增第 23 條(歸屬規則)**:OOS 回合須 `entry_idx >= oos_start` 且 `exit_idx < oos_stop`(完全包含)。跨界回合與期末未平倉回合排除且分別計數落地。**禁止以日期字串比較判定歸屬**;`oos_start`/`oos_stop` 一律取自 fold 幾何(`folds[0].test_start`/`folds[-1].test_stop`),不得由報表日期回推(`report.build_segment_report` 現行的日期字串篩選不得被新路徑沿用)。

**新增第 24 條(計量分母)**:回合報酬率分母固定為 `equity_curve[entry_idx - 1]`(`entry_idx == 0` 時取 `initial_cash`)。**禁止對原始 TWD 損益直接取平均**。

**新增第 25 條(禁用既有欄位)**:禁以 `report.py` 既有 `win_rate`、`profit_factor`(含任何換算)作為 C5 的 p 或 b,變數命名亦禁混用;**禁以 `num_closing_trades` 作為任何門檻的計數**;**Kelly 揭露文案不得引用 fill 層的 `win_rate`/`profit_factor` 任一數字**。違反視為 BLOCKING。

**新增第 26 條(測試)**:七項缺一即視為未完成——(1) 歸屬純度;(2) 邊界敏感度(`oos_start` 前後各移 1 根,回合集合變化至多一筆);(3) look-ahead 位移偵測(價格整體前移 1 根,p 與 b 必須顯著改變);(4) 加總不變量(起訖皆空手區段的回合損益總和 == 該區段權益變化);(5) **f\* 注入守門**(常數 `fraction_fn` 產生退化區間、spy 呼叫次數 == draws + 1);(6) **`Trade.bar_index` 不變量**(每筆 trade 滿足 `dates[t.bar_index] == t.date`);(7) **attempts 完整性**(422 亦落一列;`DELETE` 輸入後 K_observed 不變)。

**新增第 27 條(區間落地)**:帶入必須同時落地 `n / n_win / n_loss / 跨界排除數 / 期末未平倉數 / oos_observations / p 的 Wilson 95% CI / f* 的 joint bootstrap 95% CI / bootstrap_seed / bootstrap_draws / bootstrap_degenerate_draws / spec_hash / low_sample_warning / k_observed_at_write`。bootstrap 可重現:`bootstrap_seed = int(spec_hash[:8], 16)`;對外宣告範圍限定「同一 spec **且** 同一批 bars」。**退化抽樣(`n_loss == 0`)禁止靜默丟棄**,預設以 `b → ∞` 極限記 `f* = p̂` 並計入 `bootstrap_degenerate_draws`(待 quant 確認;不可讓步者為「不得丟棄、必須落地計數」)。

**新增第 28 條(單一算式與計算位置,取代原暫置)**:新增 `app/backtest/episodes.py`,負責回合抽取、OOS 歸屬計數、p/b 估計、Wilson 區間、joint bootstrap 區間,為全 repo 唯一一份 p/b 與回合定義。**f\* 算式不得出現在此模組**,經 keyword-only、無 default 的 `fraction_fn` 注入;`app/api/kelly.py` 傳入 `app.advice.limits.kelly_fraction`;點估計與 bootstrap 走同一 callable。`report.py` 的回合層顯示欄位亦由此模組供給。

**新增第 29 條(嘗試紀錄)**:新增 append-only 表 `kelly_import_attempts`,實作於**獨立檔案 `app/kelly/attempts.py`**(`KellyAttemptStore`,不得與 `kelly_inputs` 共用 class),同一 DB、同一連線紀律(比照 `app/alerts/store.py`)。每一次 import-backtest(**含 422 被拒者**)寫一列,欄位見本檔裁決 2 schema。`outcome` 定義為**閘門判定**而非寫入結果。attempts 寫入失敗即整個 import 失敗(500),不得靜默放行。`kelly_inputs`「只存最新一筆」規則不變。

**新增第 30 條(選擇偏誤顯示)**:`K_observed = COUNT(*) WHERE symbol=? AND market=?`(含 rejected、含所有策略、不設時間窗);同時落地 `K_distinct_specs = COUNT(DISTINCT spec_hash)`。以 `K_observed` 為主顯示並在揭露中寫明其定義與兩者偏誤方向;`K_observed >= 2` 必顯示完整選擇偏誤揭露句,`K_observed == 1` 顯示短版。

**新增第 31 條(同源約束)**:p 與 b 必須來自同一次 run、同一 `adjust_dividends` 狀態、同一 cost model;由構造保證——單一 request handler 內只存在一個 `BacktestResult` 物件,且 request body **禁止**接受 p / b / f\* 任一數字。

**新增第 32 條(單一回測管線)**:`POST /api/kelly-inputs/{symbol}/import-backtest` 必須重用 `app/api/backtest.py` 的 `BacktestRequest` 與**同一個 run 編排函式**(將現行 endpoint 內的編排抽為模組級函式,行為零變更、附回歸測試)。禁止在 kelly 路徑另建第二套請求模型或第二條 run 管線。import 方向單向:`api/kelly → api/backtest`,反向禁止。

**新增第 33 條(trade 索引)**:`app/backtest/engine.py` 的 `Trade` 新增必填欄位 `bar_index: int`(無 default),由唯一建構點填入。C5 新路徑一律以 index 做歸屬,禁止任何日期字串比較。

**新增第 34 條(區間只用於揭露)**:`p_ci_*`、`f_star_ci_*`、`low_sample_warning` 一律不得進入 `kelly_allowed_weight`、不得改寫生效 `win_rate`/`payoff_ratio`、不得作為 clamp 依據(與第 6 條同級)。落地的 `f_star` 僅供稽核與區間對照;**上限計算必須以生效 p/b 重新呼叫 `kelly_fraction`,禁止讀取落地的 `f_star`**。

**新增第 35 條(attempts 讀寫隔離)**:任何回答「目前生效輸入是什麼」的路徑禁止讀 `kelly_import_attempts`;唯一讀取用途為 K 計數與後續分佈顯示。`app/kelly/attempts.py` 內不得出現 `UPDATE`/`DELETE` 語句。`DELETE /api/kelly-inputs/{symbol}` 不得連帶刪除 attempts。生效值顯示一律讀 `kelly_inputs` 自身欄位,禁止由 attempts 反推。

**新增第 36 條(風險層介面收斂)**:`KellyInputs`(D-6)欄位為 win_rate / payoff_ratio / source / age_days / anchored_at / strategy_id / oos_start_date / oos_end_date / **oos_round_trips** / **ci_includes_no_edge**;`oos_closing_trades` 移除。CI 數值、bootstrap 參數與其餘樣本結構欄位**不得進入 `PortfolioContext`**;`ci_includes_no_edge` 由 `app/api/kelly.py` 算好傳入,`limits.py` 只得分支、不得計算任何統計量(延續第 12 條)。

**新增第 37 條(模組邊界擴充,延續第 13 條)**:`app/backtest` 禁止 import `app/advice` 與 `app/kelly`;`app/advice` 禁止 import `app/backtest`;`app/kelly` 禁止 import `app/advice` 與 `app/backtest`(`sample_gate` 只吃純量,不得吃回測型別)。三者的組裝點只有 `app/api/kelly.py`。依賴方向:`advice ← api → {kelly, backtest}`。

**升級 CEO/PM 事項追加**:
- `MIN_OOS_ROUND_TRIPS` 取 20 或 50(風險胃納;quant 建議 20+強制揭露)——**未定值前回測帶入路徑不得開工**,手動路徑與儲存層不受阻擋。
- `kelly_import_attempts` 新表需 CEO 核可(已納入 ADR-0006 修訂版)。
- `report.py` 既有 `win_rate`/`profit_factor` 微額 fill 污染:另立任務、PM 排期、知會 risk-compliance-officer;report 層修=bug fix 不需 ADR,engine 層修(no-trade band)=需新 ADR。
- P3 保守帶入(90% 信賴下界+獨立 source 值)是否納入路線圖;若採納需 ADR-0006 新增 source 值。

**待 quant 回覆(不阻擋開工)**:bootstrap 退化抽樣的處理規則(本裁決預設 `f* = p̂` 並計數)。

---

# 參考位置

- `limits.py`:`kelly_fraction` :595;`PortfolioContext` 裸欄位 :527-528
- `report.py`:`_trade_stats` :121-137;`build_segment_report` 日期字串篩 trade :242-246
- `engine.py`:`Trade` :43-53(須加 `bar_index`);微額 fill 成因 :140-173
- `api/backtest.py`:run 編排待抽出 :319-424
- `app/alerts/store.py`(append-only 型態)、`app/settings/net_worth.py`(`sample_gate.py` 仿照對象)
