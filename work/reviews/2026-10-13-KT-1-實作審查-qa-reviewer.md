# KT-1 實作審查（8155e4d..456519a）— qa-reviewer

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）；KT-R-19 要求的 Codex `/review` 尚未取得。

---

## Summary
KT-1（範圍 `8155e4d..456519a`，3 個 commit，9 檔）本地審查通過：七條字面與風控 §1 逐字相同（我用 Grep 把程式碼中的字串當 pattern，拿去比對裁示檔，七條全命中；(h) 單行全文也命中）。KT-R-13～R-18、R-20、R-21 都落地。F-11 與折幾何零 diff。
第 8 點的測試放寬屬實，但很窄，列為 non-blocking，並附不放寬的寫法。
**Codex 無法執行（見下），KT-R-19 要求的 Codex `/review` 尚未取得，所以本結論只是本地審查通過，不可據此標 done。**
我沒跑 pytest／vitest／ruff／mypy／tsc，只做讀碼。實作者自述的 6449／2248 等數字我沒有獨立驗證。

## KT-R 勾核表
| 條件 | 結果 | 依據 |
|---|---|---|
| 1／R-13 七條逐字 | 通過 | `kelly_wording.py` 的 (h) L318-328；fr5-6 L731-733；fr5-7 L734-736（同檔，約 L731-736）；日期列標籤 L765；三句約 L794-800。標點與全形半形一致。 |
| R-13 收錄與 id | 通過 | `RISK_CONFIRMED_WORDING` 的 `h`、`fr5-6`、`fr5-7` 保留原 id；新增 `kt1-date-label`、`kt1-tail-present`、`kt1-tail-absent`、`kt1-tail-unknown`。`test_kelly_wording.py` 的 `CONFIRMED_VERBATIM` 同步，82→86。常數註解引用本裁示，並保留 4-A（另行計數不加「可查看」）與 4-C（不得折疊）。 |
| R-14 三狀態 | 通過 | `kelly.py` `_tail_notice` L788-817：只看 `window_end`、`oos_end_date` 兩個儲存值。任一為 NULL 回 UNKNOWN；相等回 ABSENT；其餘回 PRESENT。不推測 r，也不查日曆。PRESENT 的兩個日期後端 `.format()` 填好，測試斷言輸出無 `{`、`}`。 |
| R-14 欄位條件 | 通過 | L1064 `tail_notice=_tail_notice(row) if detail is not None else None`，與 `sample_detail` 同進同出；L1012 無 row 時為 `None`。 |
| R-14 前端位置與樣式 | 通過 | `KellyDisclosuresPanel.tsx` L226-231：在 (h)（L221-225）之後、`<ul className="mt-2 text-xs">`（L232）之前，自成一段 `<p className="mt-1 text-sm text-neutral-300">`。不在 tooltip、收合或列內 note。 |
| R-14 F-11 不引用 | 通過 | 前端 `tail_notice` 只出現在 Kelly 面板、types、測試。`kellyDisclosuresPanel.test.ts` 新增測試掃 `backtest/*.tsx`，確認不含 `tail_notice`。 |
| R-15 日期列 | 通過 | `kelly.py` L720-725：緊接 fr5-2 之後，條件 `window_end is not None`，值為 `row.window_end` 原字串。`models.py` L98 的 `^\d{4}-\d{2}-\d{2}$` 擋掉帶時間的值，測試 `test_a_stored_last_bar_date_cannot_carry_a_time_of_day` 釘住這點。位置、NULL 不渲染、不出現 None 或破折號都有測試。 |
| R-16 隔離 | 通過 | 新增 `grep` 無 `backtest_wording` 於 `kelly.py`、`kelly_wording.py`。`git diff --stat` 顯示 `app/api/backtest_wording.py`、`tests/test_backtest_wording.py`、`app/backtest/**`、`app/kelly/**` 零 diff。新測試只做整句比對，沒有子句級比對。 |
| R-17 `REJECTED_LITERALS` | 通過 | 新增 18 條（`test_kelly_wording.py` L656-682）：shipped 13 條、kelly 3 條（持有越久的回合、因此無法呈現該日期、`{window_end} 仍未平倉`）、升 shipped 2 條。範圍與裁示一致。「回測迄日」「回測資料迄日」升 shipped 有依據：我 grep 全 `apps/stock-desk` 的 py／ts／tsx／json／md，除這兩條定義外零出現，與註解宣稱「2026-10-13 grep 無合法用途」相符。`fr5-6` 備案 B 因是子字串未列入，正確。 |
| R-17 註解禁字 | 通過 | 我 grep `app/` 與 `frontend/app/`：無「樣本外內進場」；F-11 的 16 條與 `KT_R_10_PHRASES` 也無命中。 |
| R-18 測試 | 通過，有牙 | `test_kelly_tail_attribution.py`：10 例（#1～#9 加 #3b），斷言走真實 `attribute_round_trips`／`oos_window`，n=360 時窗為 `[252,315)`，n=315 為 r=0。每例另打 GET 斷言 `tail_notice`、日期列值與兩個計數。r>0 斷言 `oos_end_date < window_end`（L169，api 測試 L682 附近另有一處）。NULL 三組合有參數化（`test_api_kelly_disclosures.py` L735 附近）。`KT1_FORBIDDEN_FRAGMENTS` 五項禁字、`KT1_LENGTHS` 的 len 斷言都在。我手算 3 項：日期列 11、r=0 句 22、fr5-6 35、NULL 句 60，與測試一致。 |
| R-20 範圍紀律 | 通過 | `kelly_wording.py` diff 只動 (h)、fr5-6、fr5-7、新增常數與註解。(c)、fr5-2 與其他逐字定稿零 diff。`app/backtest/**` 零 diff（含 `attribute_round_trips` 與折幾何）。 |
| R-21 suggested | 已做 | NULL 時 `logger.error`，帶 symbol、market 與兩個日期；測試斷言。 |
| R-19 | 部分 | Codex 未取得，qa-e2e 尚未做（見下）。 |

## 各檔問題

### `apps/stock-desk/backend/tests/test_api_kelly_disclosures.py`（約 L1117-1131，第 8 點）
- [可維護性][medium][non-blocking] 實作者揭露的改動確實放寬了守門，但範圍很窄。
  - 原本：對整個明細 `str(detail)` 掃五個字元（— 〜 ～ 到 –），標籤也在內。
  - 現在：值與 note 仍五字全掃；標籤改為「`labels - {fr5-7}`」逐個掃。結果是 fr5-7 標籤對**五個字元**全部豁免，不只對「到」。
  - 若有人把 fr5-7 標籤的「到」改成「～」或「–」，這個測試不會紅。實際風險低，因為 `CONFIRMED_VERBATIM` 逐字釘住標籤、改字會在別處紅。但「三個連接符形狀」的守門被 fr5-7 這一列繞過了。
  - 不放寬的替代寫法（建議）：豁免只給「到」，且只給一次、只給定稿的那個片段。
    ```python
    for character in ("—", "〜", "～", "到", "–"):
        assert character not in rendered, character
        for label in labels:
            allowed = 1 if (character == "到" and label == wording.KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL) else 0
            assert label.count(character) == allowed, (label, character)
    assert "，到回測資料最後一根仍未平倉" in wording.KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL
    ```
    這樣 fr5-7 對其他四個字元仍受限，「到」只能出現一次且位置固定。
  - 另外，「值與 note 另掃」的拆法本身是合理的（標籤本來就逐字釘住）。

### `apps/stock-desk/backend/app/api/kelly.py`（`_tail_notice` L803-817）
- [Edge case][low][non-blocking] `oos_end_date > window_end` 沒另外處理，會輸出倒過來的區間（「迄日 B 之後、至 A 為止」）。
  - 依 KT-R-14 字面（兩日期非 NULL 且不同就走 r>0 句），實作與裁示一致。正常流程也不會發生，因為 `oos_end_date = dates[stop-1]`，`window_end = dates[-1]`，後者必大於等於前者；只有手改 DB 或錯誤寫入才會出現。
  - 若要處理，應走 UNKNOWN 句加 `logger.error`，但那會偏離「只看兩日期是否 NULL／相等」的裁示，建議回送風控決定，不要自行改。
- [可維護性][low][non-blocking] 每次 GET 都記一筆 `logger.error`。這與同檔條件 98（`_disclosures` L1037）的既有做法一致，也是 KT-R-21 要求的「比照條件 98」，可接受。

### `apps/stock-desk/backend/tests/test_kelly_tail_attribution.py`
- [可維護性][low][non-blocking] 從 `tests.test_api_kelly_import` 匯入私有 helper `_CLEARS_GATE`、`_import`、`_seed`。repo 有先例（`test_backtest_round_trip_episodes.py` 等多檔跨測試匯入私有 helper），可接受；若來源測試改名會連動斷裂，但會立即紅，不會靜默。

### `apps/stock-desk/frontend/app/lib/__tests__/kellyDisclosuresPanel.test.ts`
- [可維護性][low][non-blocking] 位置斷言用原始碼字串比對（`between.match(/<[a-zA-Z]/g)`），repo 沒有 DOM 測試設施，與既有 B1 測試同一做法，可接受。對 JSX 縮排或換行改動較脆，但失敗時會立即紅。
- 實機位置與樣式仍須 qa-e2e 驗。

### 其他檔
- `kelly_wording.py`、`types.ts`、`KellyDisclosuresPanel.tsx`、`kellyImportDialog.test.ts` 未發現問題。

### 第 9 點其餘項目
- 375 寬長標籤可能使值換行：這是版面問題，讀碼無法判斷，交 qa-e2e（KT-R-19：375 與 1280 寬，三種狀態實機）。標籤很長（fr5-7 共 37 字），務必看值是否仍與標籤相鄰、無截斷。NULL 狀態若無法實機建置，依 `e2e-fallback` 改以元件與 API 測試代驗並明列降級。

## 第二意見（Codex）
**無法執行。** `which codex` 回傳 command not found（exit 127），此環境沒有安裝 Codex CLI，我也不能安裝。依紅線在此明確註記缺席原因。
KT-R-19 要求 Codex `/review` 的 BLOCKING_ISSUES 為 0，這一項**尚未滿足**。請 coordinator 在有 Codex 的環境補跑，補完前不得標 done。

## 唯讀權限判準常數
未觸及。
- 檢查 1：`git diff --stat` 列出的 9 檔都在 `apps/stock-desk/` 下，沒有 `scripts/validate_agents.py`。
- 檢查 2：我讀完全部 diff，沒有 `READONLY_AGENTS`／`READONLY_ALLOWED_BASH`；另外 Grep 整個 `apps/stock-desk`，這兩個符號 0 命中，所以沒有 shadow 定義，也沒有常數值被改。
- 沒有異動的 agent 名單；沒有涉及 ADR。

## 自我揭露
- 沒有跑任何測試或檢查工具，只讀碼與 Grep；實作者的通過數字未驗證。
- 逐字比對方式：先把程式碼字串當 pattern 去 Grep 風控裁示檔，再 Grep 回程式碼確認單行字串；(h) 與三句因拆成多行字串，對 (h) 另用視覺逐段比對。
- 第 8 點的替代寫法我沒有實際執行。
- 沒有驗證歷史上是否真有 `window_end`／`oos_end_date` 為 NULL 的舊列（KT-R-21 的 dev-lead 調查項）。
- 沒有看實機畫面。

## Verdict
PASS（僅限本地審查；Codex 第二意見缺席，KT-R-19 的 Codex 與 qa-e2e 兩關未完成，不得標 done，也不得出貨）。
建議（非阻擋）：處理第 8 點的測試放寬。

BLOCKING_ISSUES=false

相關檔案：
- `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/backend/app/api/kelly.py`
- `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/backend/app/api/kelly_wording.py`
- `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/backend/tests/test_api_kelly_disclosures.py`
- `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/backend/tests/test_kelly_wording.py`
- `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/backend/tests/test_kelly_tail_attribution.py`
- `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/frontend/app/settings/KellyDisclosuresPanel.tsx`
- `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/frontend/app/lib/__tests__/kellyDisclosuresPanel.test.ts`
