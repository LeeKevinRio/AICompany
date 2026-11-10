# N-212 盤點腳本實作（feat/n212-n207-preflight）

- 審查者：data-engineer
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-212（N-207p 盤點腳本單）已完成並 push，未 merge 進 product，也沒有 push 到 product/stock-desk。
- 分支：`feat/n212-n207-preflight`
- head SHA：`b3c59247241ef59344bbe2310b5e87759fb561ed`
- 改動範圍只有 `apps/stock-desk/backend/scripts/n207_preflight/`（15 個 SQL 檔加 `run_preflight.py`）與 `apps/stock-desk/backend/tests/test_n207_preflight.py`，沒動 app/。
- 未讀 `.env`，未碰任何 `data/*.db`。測試全用 `tmp_path`。

## 各部門回報（data-engineer）
**接入摘要**：14 項盤點加 P-4b。runner 只用標準函式庫，以 `file:<db>?mode=ro` 開啟，不 import app、不連網，DB 路徑由 CLI 第一個參數傳入。輸出一項一行 `<項目>\t<值>`。出錯印 `<項目>\tERROR` 並以非 0 結束，且不回顯例外內容。`p4b_LOCAL_ONLY.sql` 檔頭有警語，且不在 runner 的 `ITEMS` 內。

**輸出格式（需 TA 確認）**：多值項目用逗號串接。
- P-2 輸出 `a,b,c,d,e`。
- P-3 輸出 `distinct 檔數,n_targets`。
- 所以「空表每項皆 0」對 P-3 是 `0,5`，因為 n_targets 是參數預設值而非資料。測試斷言的是檔數為 0、n_targets 等於 `RuleParams()` 預設值。
- 若 TA 要 P-3 也只輸出單一數字，改法很小。

**額外加的防呆**：p1、p2、p3 加了 CASE 守衛，強制讀取 bpt / n_targets。原因是 SQLite 惰性求值：空的批次表會跳過 `json_extract`，壞 JSON 就變成沒報錯。測試實測發現這點後補上。守衛同時要求 bpt 的 typeof 必須是 integer，否則回 NULL，runner 判為 ERROR。

### 各項 SQL 全文
p1.sql
```sql
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
bpt AS (
  SELECT COALESCE((SELECT json_extract(payload, '$.batches_per_target') FROM cur), 3) AS v
)
SELECT CASE WHEN typeof((SELECT v FROM bpt)) <> 'integer' THEN NULL ELSE (
  SELECT COUNT(*) FROM (
    SELECT symbol FROM playbook_batches
    GROUP BY symbol
    HAVING COUNT(*) <> (SELECT v FROM bpt)
  )
) END;
```
p2.sql（cur、bpt 兩個 CTE 與 p1 相同）
```sql
WITH cur AS (...同 p1...),
bpt AS (...同 p1...),
per_symbol AS (
  SELECT MIN(batch_no) AS mn, MAX(batch_no) AS mx, COUNT(*) AS cnt
  FROM playbook_batches
  GROUP BY symbol
)
SELECT
  CASE WHEN typeof((SELECT v FROM bpt)) <> 'integer' THEN NULL
       ELSE COALESCE(SUM(mx > (SELECT v FROM bpt)), 0) END,
  COALESCE(SUM(mn <> 1), 0),
  COALESCE(SUM(mn < 1), 0),
  COALESCE(SUM(cnt <> mx - mn + 1), 0),
  (SELECT COUNT(*) FROM playbook_batches WHERE typeof(batch_no) <> 'integer')
FROM per_symbol;
```
p3.sql
```sql
WITH cur AS (...同 p1...),
nt AS (
  SELECT COALESCE((SELECT json_extract(payload, '$.n_targets') FROM cur), 5) AS v
)
SELECT COUNT(DISTINCT symbol),
       CASE WHEN typeof((SELECT v FROM nt)) <> 'integer' THEN NULL ELSE (SELECT v FROM nt) END
FROM playbook_batches;
```
p4a.sql
```sql
SELECT COUNT(*) FROM playbook_symbols WHERE high_volatility <> 0;
```
p4c.sql
```sql
SELECT COUNT(*) FROM playbook_symbols
WHERE typeof(high_volatility) <> 'integer' OR high_volatility NOT IN (0, 1);
```
p4b_LOCAL_ONLY.sql（檔頭警語：LOCAL ONLY，runner NEVER executes，輸出不得貼回對話、work/、紀錄或任何 agent，另有中文警語）
```sql
SELECT symbol FROM playbook_symbols WHERE high_volatility <> 0 ORDER BY symbol;
```
p5.sql（TA 指定原文）
```sql
SELECT COUNT(*) FROM playbook_batches
WHERE status IS NULL OR status NOT IN ('planned', 'open', 'closed', 'skipped');
```
p6.sql
```sql
SELECT CASE WHEN
  (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
   OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND NOT EXISTS (SELECT 1 FROM playbook_batches)
THEN 1 ELSE 0 END;
```
p7.sql
```sql
SELECT CASE WHEN
  NOT (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
       OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND EXISTS (SELECT 1 FROM playbook_state WHERE key = 'total_deploy')
THEN 1 ELSE 0 END;
```
p8.sql
```sql
SELECT CASE WHEN
  (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
   OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND NOT EXISTS (SELECT 1 FROM playbook_state WHERE key = 'cash')
THEN 1 ELSE 0 END;
```
d1.sql（1d）
```sql
SELECT COUNT(*) FROM playbook_directives AS d
WHERE d.settled = 0
  AND d.batch_no IS NOT NULL
  AND (d.batch_no < 1
       OR NOT EXISTS (SELECT 1 FROM playbook_batches AS b
                      WHERE b.symbol = d.symbol AND b.batch_no = d.batch_no));
```
d1_2.sql（1d-2）
```sql
SELECT COUNT(*) FROM playbook_directives
WHERE settled = 0 AND batch_no IS NULL
  AND action IN ('buy', 'sell') AND rule_id <> 'S2';
```
p9a.sql、p9b.sql、p9c.sql：照修一-5 的 SQL 原文。三者都以 `FROM (SELECT symbol FROM playbook_batches UNION SELECT symbol FROM playbook_symbols) AS u` 為資料來源。
- p9a：`typeof(u.symbol)='text' AND substr(u.symbol,-1)='K' COLLATE BINARY`。
- p9b：`typeof(u.symbol)<>'text'`。
- p9c：TEXT、非 K 結尾，且不符 9 條 GLOB（`[1-9][0-9][0-9][0-9]`、`[1-9]…[A-JL-Z]`、`00` 加 2～4 位數字各附可選字母後綴、`91[0-9]{4}`）。

## 驗證
- `ruff check .`：All checks passed。
- `ruff format --check .`：496 files already formatted。
- `mypy app tests`：Success, no issues found in 486 source files。
- 全套 pytest（`--cov=app --cov-fail-under=90`）：10013 passed, 1 skipped, 2 xfailed。覆蓋率 97.62%，達標。
- 新測試檔 `tests/test_n207_preflight.py` 共 105 個測試，涵蓋：
  - 唯讀連線寫入必定失敗（`readonly`）。
  - 種入代號後輸出不含任何代號字串。
  - 空表每項回 0（P-3 的 n_targets 是 5）。
  - SQL 預設值字面常數等於 `RuleParams()`，並釘住 WHERE / ORDER BY 與 `active_params` 逐字相同。
  - 每項各有正例與反例。
  - P-4：T30 種入 0、1、2、-1、'x'、0.5，得 P-4a=5、P-4c=4。
  - P-9：K 結尾、BLOB（`x'30303632354B'`）、形狀規則 P01～P20 與 N01～N27（N28 為 None，不適用），另有 400 組 seed 的性質測試，對照 Python 規則。
  - 錯誤路徑：缺表、壞 JSON、非 DB 檔、DB 不存在、CLI 用法錯誤，一律 ERROR 並以非 0 結束。
  - 以 stdlib import 的 AST 檢查證明 runner 不 import app、不連網。

## 下一步 / 待 TA 覆核（P-1、P-2、P-3、P-5 語意）
1. **P-1 / P-2 / P-3 的資料表**：我以 `playbook_batches` 依 symbol 分組，不含 `playbook_symbols`。
   - 依據是約束 3，以及 R-14 的「啟用檔數」。
   - 請 TA 確認「啟用」是否要排除只有 closed / skipped 批次的標的。我的寫法是全部算，方向偏保守，會多停不會少停。
2. **P-2 的「斷號」定義**：我定為 `COUNT(*) <> MAX - MIN + 1`，沒有特別排除 min<1 的情形，例如 0,1,2 不算斷號，只算 min≠1 與 min<1。min≠1 的計數涵蓋 min<1，請確認是否符合「最小值不等於 1 的檔數」與「最小值小於 1 的檔數」可重疊的讀法。
3. **P-2 第五個計數**：`typeof(batch_no) <> 'integer'` 的列數，依列計而不是依檔計。請確認。
4. **P-3 輸出形狀**：輸出 `檔數,n_targets` 兩值，見上方說明。
5. **P-5**：用 TA 指定原文。注意 `playbook_batches.status` 在 schema 是 NOT NULL，所以 NULL 路徑在真實 schema 下不會出現，我用無約束的臨時表測 NULL 計數。
6. **on_date**：寫死為 `date('now','+8 hours')`。v3.1 §3 若定義鎖內讀現行參數的 on_date 不是台北今日，P-1、P-2、P-3 要跟著改，並回 TA。
7. **參數值型別**：若現行參數列的 `batches_per_target` / `n_targets` 不是 integer（例如被外部改成文字），目前判為 ERROR，不靜默套預設值。請確認這是否符合預期。
8. **覆核交接**：devops-sre 覆核 SQL 文字，qa-reviewer 審查（含 Codex 第二意見）。
   - 目前 CI 的覆蓋率只量 `app/`，不含 `scripts/`，所以 runner 本身不計入覆蓋率，只靠這 105 個測試驗證。
   - 合入前 N-207 對 `scripts/n207_preflight/**` 須零 diff（M1 清單加 N-207p 的 merge commit）。
