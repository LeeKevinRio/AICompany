# #61 第一批（fix/stock-desk-cap1-10pct）審查

- 審查者：qa-reviewer
- 日期：2026-10-28
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

# qa-reviewer 審查報告：`fix/stock-desk-cap1-10pct`（HEAD 877f1e1）

審查範圍：`git diff 27a145c origin/fix/stock-desk-cap1-10pct`，67 檔、+3348／-138，逐檔看過。重點放在第 2、3、6 項。依限制只用 Read、Grep 與兩種唯讀 Bash（git diff、codex --version），沒有跑測試。CI 數字採交件者自報，我沒有重跑。

## 結論

- **Verdict：PASS（附 3 項 medium 建議修）。**
- 沒有 critical 或 high。重點項目的實作與風控定稿一致，守門測試沒有超出授權範圍的放寬。
- S2 遷移的並發處理方向正確：BEGIN IMMEDIATE，再於鎖內重讀紀錄。但缺三樣：沒有並發測試、穩態仍取寫鎖、ROLLBACK 沒有 guard。
- UI 必改 6（qa-e2e 在 375／390px 展開建議卡驗收 #2'）仍未做，合併前要補。
- Codex 不可用：`codex --version` 回 `command not found`。**單家審查，Codex 待環境可用時補跑。**

## BLOCKING

無。

## NON-BLOCKING

### medium（建議合併前修，或開 follow-up）

**M1. 遷移在穩態仍取寫鎖，與 N-154 的契約不一致**
- 位置：`apps/stock-desk/backend/app/settings/migrations.py:467`。
- `migrate_cap1_default` 每次建構 store 都先 `BEGIN IMMEDIATE`，連 `migrated` 或 `not_applicable` 的終局狀態也一樣。
- N-154 的 `add_missing_columns`（`app/data/sqlite_util.py`）是先做不取鎖的檢查，只有真的需要動作才取鎖。它的測試 `test_a_database_that_already_has_the_column_is_left_alone` 明定「重開已遷移的檔不取寫鎖」。
- 後果：backend 與 scheduler 每次啟動都要等寫鎖，別的行程持鎖超過 busy timeout 時，`SettingsStore()` 建構會丟 `OperationalError`，settings 路由全部 500。
- 建議：先不加鎖 `read_cap1_migration`，終局就直接 return。否則才 `BEGIN IMMEDIATE`，並在鎖內重讀（現有的重讀邏輯保留）。

**M2. ROLLBACK 沒有 `in_transaction` guard**
- 位置：`migrations.py:476-478`。
- `except BaseException: conn.execute("ROLLBACK")` 是無條件的。
- SQLite 若已自行 rollback（磁碟滿、I/O error），第二次 ROLLBACK 會丟 "cannot rollback - no transaction is active"，蓋掉真正的錯誤。N-154 在 `sqlite_util.py` 已有同型防呆（`if conn.in_transaction:`）。
- 建議：照 N-154 加 guard。

**M3. S2 遷移沒有並發測試**
- `tests/test_settings_migrations.py` 整份沒有 Thread、Barrier、multiprocessing。
- docstring 宣稱「loser 必須找到 winner 的紀錄，不重做」，但沒有測試支撐。
- N-154 的 `tests/test_schema_migration_race.py`（在 agent-ac5a8cf6ab31ef86e worktree）用 spawn 多行程加 Barrier，`_FACTORIES` 裡沒有 settings。
- 建議：N-154 併入後補一個 settings kind，或本分支先寫等價的 threads／processes 測試。
- 斷言：全部建構成功、`settings_migrations` 恰好一筆、`app_settings.risk_budget` 的值是 0.10（恰好一次遷移）、`changed_by_user=0`。
- 另補一個「loser 在鎖內重讀看到 terminal 就不寫」的 stale-read 測試，仿 `_StaleFirstPragma`。

### low

- **L1** `apps/stock-desk/frontend/app/lib/cap1SunsetWording.ts:22`：註解指向不存在的 `tests/test_cap1_sunset_frontend.py`。實際守門是 `tests/test_kelly_freeze.py::test_the_sunset_lead_interpolates_the_same_staleness_window`，請改正。
- **L2** `SettingsForm.tsx`（風險預算 grid）：`sm:grid-flow-row-dense` 讓下一個欄位在視覺上跳到 cap-1 欄位旁、S2 區塊之上，但 DOM 順序是 S2 區塊在前。視覺順序與 Tab 順序不一致（WCAG 2.4.3，低）。「緊接該欄位」勉強成立，建議 qa-e2e 在 1280px 看一眼。
- **L3** 停用按鈕狀態（`KellyManualInputForm.tsx` 約 :178-181、`KellyImportDialog.tsx` 約 :345-350）：
  - `disabled` 屬性、`cursor-not-allowed`、`opacity-50` 三通道齊全（2.6 過）。
  - 但 `hover:bg-white` 在 disabled 時仍生效（2.8）。建議加 `disabled:hover:bg-neutral-100`。
  - 兩顆按鈕的 aria-label 都只有「已暫停」，無上下文。這是風控條件 103 的逐字要求，可接受。
  - 手填欄位與回測帶入的表單欄位仍可輸入，欄位旁沒有說明。導語與按鈕字面已揭露，不阻擋。
  - 對比我估算約 4.7:1，過。
- **L4** `SettingsForm.tsx:90` 第 1 條欄位 description 的範例是「例如 0.15 代表 15%」，那是舊預設值，可能被讀成建議值。這是格式範例，不算違規。若要改，屬文案改動，須送風控。
- **L5** 錨點表 `KELLY_LABEL_EMBEDDING_ANCHORS` 現況恰好一筆，但沒有任何斷言釘住 `len == 1`。日後加第二筆只靠 N-151 的人工授權擋。可選加一行 `assert len(...) == 1`。
- **L6** 前端「暫停的 import 按鈕」測試是 source 字串比對（`kellySunset.test.ts`），強度偏弱，但與該 repo 既有慣例一致。

## 各重點項核查結果

**1. 第 1 條預設改 0.10：通過**
- `DEFAULT_MAX_POSITION_WEIGHT = 0.10`（`limits.py`）；前端 `SettingsForm` 的 `defaultValue: 0.1`。
- `test_cap1_default.py` 用 regex 讀 SettingsForm 原始碼比對後端預設；`cap1Default.test.ts` 單獨釘前端值。
- `MAX_POSITION_WEIGHT_CEILING` 未動，且有測試釘住 0.50。
- 評估處無 `min(stored, default)`（`limits.py:1066`、`:1613` 直接讀 budget）。
- `rules_version` 沒有升（diff 不含規則 YAML 與 `advice/engine.py`）。
- 邊界測試齊全：恰好 10% 為 violated、9.99% 為 passed、加碼上緣 555。

**2. S2 遷移：實作正確，缺口見 M1～M3**
- **只遷移 0.15**：用 `isclose(abs_tol=EPSILON)`。測試涵蓋 0.15、±1e-12、0.1501、0.1499、0.10、0.20。
- **冪等**：`migrated` 與 `not_applicable` 為 terminal，第二次啟動不變（`test_a_second_start_changes_nothing`）。
- **區段損壞不遷移**：先對所有存在的區段做 `model_validate_json`，與 `load` 同一驗證。失敗就寫 `skipped` 紀錄，不碰 `app_settings`。
  - 測試比對 `app_settings` 的 section、payload、updated_at 全等。
  - 「一個 byte 不改」只指 `app_settings` 資料列；DB 檔本身會多一張紀錄表，這是設計。
- **不走 load→save**：直接讀 raw JSON，只改 `max_position_weight` 一個 key，key 順序保留，寫入前再以 `RiskBudget.model_validate` 驗證。
  - 測試 monkeypatch `load` 與 `save` 為拋錯，驗證遷移不經過它們。
  - 只動 `risk_budget` 一列，其他三列的 payload 與 updated_at 不變，有測試。
- **`changed_by_user`**：只在 `migrated` 紀錄上、且寫入值不等於 `new_value`（EPSILON）時設為 true，只有新遷移會清除。`skipped` 紀錄不受 save 影響（U5 逐字「按儲存之後也一樣」）。
  - 這個語意有測試，含 NetWorth 儲存寫回 0.10 不誤觸發。
  - 還原備份後會重新遷移並重新出現告知（F4／F10）。
- **每個行程只建構一次**：全 app 只有 `deps.py:237` 一處 `SettingsStore()`，包在 `lru_cache(maxsize=1)`。scheduler 也走 `get_settings_store`。
  - 注意：lru_cache 不鎖建構，同行程併發首呼可能建構兩次。BEGIN IMMEDIATE 加鎖內重讀可以涵蓋，所以不是問題。
- **並發**：與 N-154 對照，方向相同（BEGIN IMMEDIATE，鎖內重讀）。`settings_migrations` 表在 `CREATE TABLE IF NOT EXISTS` 一次建好完整欄位，不涉及 ALTER，不會有 N-154 的 duplicate column。
  - 缺口見 M1（穩態取鎖）、M2（rollback guard）、M3（無測試）。
  - 與 N-154 無文字衝突：本分支沒碰 `sqlite_util.py`，`store.py` 只 import `enable_wal`。
- **一個行為提醒，風控已簽核，非缺陷**：skipped 狀態下使用者若主動存 0.15，下次啟動會被改成 0.10。U1 與 U5 已逐字揭露此規則。

**3. Kelly 凍結：通過**
- **PUT**：`api/kelly.py` 的 `write_kelly_input` 第一行就是 `if writes_frozen: raise 409`，detail 是「已暫停」。
- **import**：在 `normalize_symbol` 與 `_canonical_spec` 之前就擋，早於任何寫入嘗試紀錄。測試斷言 `k_observed == 0` 且 `list_all() == []`。
- **store 第二道**：`KellyInputStore(accept_writes=False).upsert` 丟 `KellyInputWritesFrozenError`。`deps` 的 process-wide store 以 `accept_writes=not KELLY_INPUT_WRITES_FROZEN` 建構。
  - 全 app 只有 `kelly.py` 兩處呼叫 `store.upsert`，沒有漏網路徑。
  - 測試 `test_the_process_wide_store_refuses_upsert` 釘住。
- **DELETE 與 GET 保留**：`delete_kelly_input` 未動；disclosures 與讀取路徑有測試。
- **fixture 解凍**：`kelly_writes_open` 只覆寫 dependency，作用範圍是當次 app instance。
  - 所有使用它的既有測試只增加 `@pytest.mark.usefixtures("kelly_writes_open")` 或 `pytestmark`，斷言行一行都沒改。
  - 我逐一看過 `test_api_kelly`、`test_api_kelly_import`、`golden`、`adr0023`、`alerts`、`book_context` 各處 diff。
  - 沒加 fixture 的 422 測試仍有效，因為驗證在凍結檢查之前。
- `app.kelly.freeze` 已加入 `test_kelly_boundary` 的 `GUARDED_MODULES`。

**4. 告知字面逐字比對：通過**
- **migrations.py 的定稿**：與風控定稿逐字相同的有 #1 標題與 1-1、1-2、1-3、1-5，1-4 新定稿，#2／#2'，U0～U5，S1／S1'，區段名稱對照。
- **前端 `cap1SunsetWording.ts`**：#3 導語、#4a／#4b 逐字相同。測試是手打一份原文做相等比對，不是 import。
- **數字全部插值**：`old_pct`／`new_pct`／`current_pct`／`default_pct`／`{KELLY_STALE_AFTER_DAYS}`／`{n}`／`{m}`／`{threshold_pct}` 皆插值。
  - 唯一的前端鏡像常數 `KELLY_STALE_AFTER_DAYS = 30` 有後端測試比對三處一致。
- **渲染位置**：
  - 儀表第 1 條列的順序是「觀測值最高」→ 彙總句 → S2 句，全在主視圖，無 `<details>`、`truncate`、`line-clamp`。
  - #2'／S1 在 `LimitsCheckList` 的同一個 `<li>`，位於「觀察值／上限」之下，`text-xs text-amber-300`。
  - `LimitsCheckList` 不在 `AdviceCardView` 的巢狀 `<details>` 內（那個 details 是「資料完整度」）。
  - F-i 與同位原則註解已寫入。
- **設定頁**：橫跨整列、緊接欄位，`text-xs text-amber-300`，不低於 description 的 `text-xs text-neutral-500`。沒有 `<details>`、`role="status"` 或 `aria-live`。
- 前端不組句、不重算 `n`（`violated_count` 由後端下發，`m = excluded.length`）。

**5. D-4（`limitNotices.ts`）：通過**
- 2-V／2-M／2-R 改為只收 `violated`，不再以條號過濾。
- 2-O 仍以條號 `kelly_fraction` 排除第 5 條，由 `NOT_EVALUABLE_EXCLUDED_LIMIT_ID` 保留。
- 測試三條反轉為 D-4 的等價斷言，2-O 的測試沒動。

**6. 守門測試改動：沒有超出授權範圍**
- **`kellyChromeAllowlist.test.ts`**：只刪舊導語那一筆。其餘 diff 是行號註解改成按內容描述（風控建議項 7）與檔頭 N-151 註記。
- **`KELLY_SURFACE`**：加兩檔（`cap1SunsetWording.ts`、`migrations.py`），前端計數 7 改 8。
- **`REJECTED_LITERALS`**：加兩筆，scope 為 `"shipped"`。
- **`KELLY_LABEL_ALLOWLIST`**：只多一筆 `embedded`，逐字同裁示 3-1。
- **檢查迴圈**：開頭有 `assert kind in _LABEL_ALLOWLIST_KINDS`，未知 kind 會轉紅；原本的 `else` 放行 chrome 已拆成 `elif chrome` 加 `else embedded`。
  - embedded 的八項判準齊全，並有 `embedded == set(ANCHORS)` 雙向一致。
- **錨點表**：恰好一筆。
- **短標籤掃描**：沒有被遮蔽的第二個命中，是交件者以全套 CI 實跑確認的自報。
- 其他守門測試的斷言逐一看過：
  - `test_advice_limits.py` 約 14 處改為明傳 `RiskBudget(max_position_weight=0.15)`。算式與期望值（1,176、588、589）不變，斷言文字不動；`test_default_budget_is_conservative` 改 0.10。
  - `test_advice_book.py`、`test_advice_book_limits.py` 同樣是明傳 0.15。
  - `test_api_settings.py` 把預設期望值 0.15 改為 0.10，共 4 處。
  - `test_kelly_wording.py` 的 `CONFIRMED_VERBATIM` 數量 82 改 84，是新增兩條日落字面。
  - `componentWordingScan.test.ts` 的 SCANNED_FILES 加一檔（更嚴）；page.tsx 原始碼守門由精確字串改為等價 regex，仍釘住兩個 prop。
  - 其餘 `__tests__` 都只是 fixture 補 `cap1_migration_notice: null`、`violated_count: 0`、`writes_paused_label: null`，沒有刪或改斷言。
- **有一處要送風控確認**：見下方「需送風控的項目」第 1 點。

**7. #68 測試：通過**
- **`<= cap` 舊斷言**：已刪除（`test_playbook_rebalance.py`），沒有改成 xfail，`RiskBudget` 的 import 一併移除，docstring 已改寫。
- **測試 ①**：n=5 對 0.14、n=7 對 0.10，用 `==`，綠燈，無 skip 或 xfail。
- **測試 ②**：
  - 原只改第 1 條 0.05／0.50 的測試保留，改走 `_lines_with_budget`。
  - 新測試 `test_the_directives_do_not_depend_on_any_risk_cap_setting` 的 TIGHT 與 LOOSE 逐字照裁示。
  - 有窮舉斷言（每個欄位 TIGHT 與 LOOSE 都不同）、`max_position_weight` 不取 0.15、非空斷言（含 buy 與 sell，且 buy 股數大於 0）。
  - 綠燈，無 skip 或 xfail。
- **測試 ③**：
  - `strict=True`、`raises=(AssertionError, KeyError)`；reason 與 `#68裁決補充 第 5 節` 的原文一致（那份裁定明說覆蓋較早的 reason）。
  - 斷言是把 `/today` 與 `/rule-set` 回應序列化後搜尋 title 加 ①～④ 逐字句。
  - 我逐句對照補充裁定第 4 節的定稿，5 句完全相同，插值也正確（70%、5、3、14%、20%、12%）。
  - 因此揭露落地、字面照定稿時會轉 XPASS，strict 會逼著移除標記。
  - 兩個參數案例都是 XFAIL，非 XPASS。

**8. `violated_count` 與 `cap1_migration_notice`：通過**
- `violated_count` 是同一批逐檔 `checks[limit_id].status == "violated"` 的計數，與 `worst_symbol` 同源，沒有重算；兩個帳本層上限固定為 0，並有測試。
- `cap1_migration_notice` 只插入設定值的百分比與時間，沒有估值數字，不經匯率換算。
- `test_rk4c_quote_shown.py` 的欄位集合測試已把兩個新欄位列入，註解改為「風控 2026-10-26 複核核可」。

**9. ui-delivery-checklist**
- **對比（1.x）**：amber-300 於深色底、neutral-400 與 amber-300 皆過；停用按鈕對比約 4.7:1，過。
- **按鈕文字與底色（1.3）**：按鈕沿用既有 token，過。
- **input 狀態（2.x）**：沒有新增 input；停用按鈕見 L3。
- **響應式（3.x）**：S2 區塊 `sm:col-span-2`，窄螢幕單欄；儀表與個股頁無 `truncate`。這項仍有賴 qa-e2e 在 375／390px 實機確認，見 L2。
- **禁捏造數據（5.x）**：過。所有數字來自後端欄位或常數插值，測試中的 stand-in 字串只在 `__tests__` 內。
- **token 紀律（6.x）**：只用 Tailwind class，無 inline 色值。

## 需送風控的項目

1. **請風控補一句確認**：`kellyGuidanceSentencePairing.test.ts` 的守門被實質改寫，雖屬必要，但不在本次授權清單內。
   - (a) 「條號不得裸用」由「每個條號都與名稱配對」改成「首個條號配對，其後裸用的條號由 #3 全文逐字相等比對撐住」。
   - (b) 導語放行「可靠」二字，限恰好一次且必須是「算出的數字不可靠」。
   - 理由：#3 逐字定稿本身含這兩點，改動是不得已的；交件已揭露（2026-10-26 交件 :111），風控 2026-10-26 四項裁定 1.2(c) 所引的行號（:34-35、:53、:56）也屬於改後版本，實質上已看過。
   - 但形式上它仍是放寬一支守門，請補一句明示確認。
2. 若採納 L4 改「例如 0.15 代表 15%」的範例字面，那是面向使用者的文案，須經風控。
3. 現有定稿沒有任何變動，不需要重審。

## 合併建議

1. **先補 qa-e2e 必改 6**：375／390px 展開建議卡，確認 #2' 完整可讀；再加設定頁 S2 區塊在 375／1280px 的畫面，順帶看 L2。這是章程要求的 UI 實機驗收，目前尚未做。
2. **M1～M3 建議在合併前處理**，至少 M2（兩行）與 M1（改動小）。M3 可在 N-154 併入後補，但請開 follow-up 追蹤，不要漏。
3. 風控補確認第 1 點後即可合併。
4. 本分支是產品線的長命分支，N-154 與本分支的合併順序不影響。N-154 併入後，settings 的並發測試最容易接在它的 `_FACTORIES` 上。
5. **期限提醒**：測試 ③ 的 xfail 必須在 #62 第二批（5-K）合併前由 `fix/stock-desk-playbook-cap1-disclosure` 移除，否則風控直接否決。第二批還要同 PR 刪除 `embedded` 條目與其錨點（R-2）。
6. **Codex 待環境可用時補跑**，屆時請另外請它特別看 `migrations.py` 的鎖與 rollback 路徑。

## Codex 第二意見

無法執行：`codex --version` 回 `/bin/bash: codex: command not found`。**單家審查。**

## 唯讀權限判準常數

未觸及。
- 第一道：`git diff 27a145c origin/fix/stock-desk-cap1-10pct --name-only` 的 67 個檔案，全部在 `apps/stock-desk/` 底下，外加 `work/stock-desk-產品說明.md`。不含 `scripts/validate_agents.py`，也不含任何 `.claude/` 路徑。
- 第二道：依唯讀紀律不用 pipe，改在 HEAD 877f1e1 的 worktree `apps/` 下 Grep `READONLY_AGENTS|READONLY_ALLOWED_BASH`，0 筆，故沒有 shadow 定義。
- 三問回答：
  - 改了什麼：無。
  - 為何改：不適用。
  - 對應 ADR：不適用，所以沒有 ADR 編號與狀態。
- 常數值在別處被改動的情形，因 `scripts/` 與 `.claude/` 均未入 diff，也不成立。

## Verdict
PASS（附 M1～M3 建議；合併前需完成 qa-e2e 必改 6 與風控的一句確認）

BLOCKING_ISSUES=false
