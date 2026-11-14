# G1 聚合語意位置與 SP-1 裁示

- 審查者：tech-architect
- 日期：2026-11-14
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**G1：修改後採用。** 聚合參數放進 YAML，演算法放在 engine，這兩點照 quant 的提案。但不在 DSL 裡新增「減半」運算子。附錄 B 第 4 票改用規則內容來表達：每條偏多、偏空規則的條件都加上 `vol_ratio_20_120 lte 1.5`。這樣 engine 只需逐字實作 ADR-0025 D-2.3 (a)～(c)，不用修訂任何 ADR。
- 這個做法屬於 ADR-0030 的實作細節，不必補充 ADR。
- 如果照 quant 原案加入 A3 減半與延伸版 A5，會改到 ADR-0025 D-2.3 (b) 的判定式（accepted），依 ADR-0030 檔頭的規定要 CEO 核可，所以我不採用。
- G5 的分配接受，附 4 點註記。

**SP-1：採用 BEFORE INSERT 重複鍵拒絕 trigger，5 張表全部加。** 這是把只增不改的保護做得更嚴，我以 ADR-0030「補充一」處理，不必送 CEO，只列為 CEO 知悉事項（CEO 可推翻）。補充全文在本報告最後。

## 各部門回報（tech-architect）

**G1 聚合語意**

裁示：
- `OutlookRuleSet` 新增必填的 `aggregation: {theta, min_completeness}`，同樣設 `extra=forbid`，沒有預設值。validator 檢查 θ > 0，以及 0 < `min_completeness` ≤ 1。這兩個值會自動算進 `rules_logic_sha256`。
- engine 照 ADR-0025 D-2.3 的字面實作：
  - 完整度＝可評估規則數 ÷ 規則總數；
  - W ＝ Σ 偏多權重 − Σ 偏空權重，以 `Fraction` 運算；
  - `range_basis` 只看有沒有 range 規則命中。
- 第 4 票的寫法：
  - 6 條偏多、偏空規則都加上 `vol_ratio_20_120 lte 1.5`。
  - 高波動時全部方向規則不命中，W＝0，判為震盪。標籤與「trunc(S÷2)，θ＝2」在 54 例中逐例相同。
- 高波動時 `range_basis` 怎麼記，由規則內容決定，請風控在規則文字語意審時二選一：
  - (i) 另加一條 range 規則 `vol_ratio_20_120 gt 1.5`：結果和 quant 的表完全相同，一律記 `range_evidence`。
  - (ii) 不加這條規則：照事先宣告 v0.2 字面（`work/research/2026-10-15-…事先宣告草案.md:2594`），共有 8 例（減半且沒有任何一票投 0）會記成 `conflicting_evidence`。
  - 我推薦 (i)：「互相抵銷」在這 8 例不符事實，而且規則字面直接寫出「高波動改判震盪」，和 quant 必須揭露的那項算術事實一致。
- 事先宣告 v0.32 要寫明：這種寫法和「減半」等價，前提是權重都為 1、θ＝2；以後改了這兩個值，就是新 claim，等價性要重新證明。

理由：
- 1.5 這個值仍在規則雜湊裡，quant 不寫死在 engine 的出發點照樣達到。
- engine 不用另外實作 ADR 沒定義的步驟，A5 也不必延伸解讀，不觸動 accepted ADR。

qa 怎麼檢查：
- 窮舉 27 種投票組合 × 2 種波動狀態，共 54 例；標籤比對 quant 表，`range_basis` 依風控選定的分支比對。
- 波動比剛好 1.5 時，不進入高波動狀態。
- 每次只讓一個欄位不可評估，都要輸出 `insufficient`。
- `app/outlook/engine.py` 裡沒有任何規則參數的數值常數（grep）。
- 少了 `aggregation`，或多出其他鍵，載入都要被拒絕。

**G5 欄位分配：接受。** 註記如下：
1. `f2_variant` 已可定為 F2-B（CEO #145）；`c8_decision_ref` 指向決策包 #145。
2. 原本的 `damping` 列取消，1.5 改寫在規則的 `value` 裡（見 G1）。
3. `N_SNAPSHOT` 用導出的方式可以，但只能由一個函式算（K-6），並加一個「等於 315」的測試。
4. `invalidation` 依 quant 的提議交給 G2，但必須在 CG-2 登記之前定案。

理由：配置和 ADR-0030 D-10 列的欄位一致，`規則 name` 放進 `RULE_TEXT_FIELDS` 也和 explanation 的處理方式一致。

qa 怎麼檢查：
- 有一個測試斷言 dirdef 的邏輯欄位、`DEFINITION_NON_LOGIC_FIELDS`、`RULE_TEXT_FIELDS` 三個集合，恰好等於 quant 表上 D、D-NL、Y 字面欄這三類的列。
- `N_MIN` 有 validator 斷言。

**SP-1 修補方式**

裁示：
- 5 張表各加一個 `{table}_no_replace` 的 BEFORE INSERT trigger：同一張表裡已有任何一個鍵（rowid、PK、UNIQUE）相同的列時，就 `RAISE(ABORT,'append-only')`。
- 既有的 UPDATE、DELETE trigger 不變。
- store 連線的 `recursive_triggers=ON` 保留，當第二層防護。

理由（其他做法都不行）：
- `ON CONFLICT ABORT` 寫在表定義上會被語句裡的 OR REPLACE 覆蓋，擋不住。
- `recursive_triggers` 是連線層級的設定，存不進資料庫檔案。
- 雜湊鏈屬於驗證層的規模，超出核心範圍。
- 這個漏洞不只會改到 label，也能把 `late = 1` 的紀錄連同 `created_at` 一起洗成 `late = 0`。而 `report verify` 的重算不涵蓋這兩欄，查不出來，所以不能接受殘留。

**需不需要 CEO：不需要。** 只是收緊；D-2 第 6 點只規定「至少要有」UPDATE／DELETE trigger，沒有寫「只能有」；不改產品行為或字面。但期限有硬性要求：必須在 CG-3 正式建表之前落地。建表之後再改就是遷移，K-12 禁止。

**範圍：逐表列出可被 REPLACE 利用的鍵（共 9 條路徑，5 張表全部要加）**

| 表 | 會被 REPLACE 利用的鍵 |
|---|---|
| `forecast_run` | `run_id`（INTEGER PK，也就是 rowid） |
| `forecast_run_end` | `run_id`（INTEGER PK，也就是 rowid） |
| `forecast_input_series` | `series_id`（rowid）、`content_sha256` UNIQUE |
| `forecast_claim_registry` | `claim_id` TEXT PK、**隱藏的 rowid** |
| `forecast_record` | `forecast_id` TEXT PK、`UNIQUE(claim_id, data_as_of)`、**隱藏的 rowid** |

後兩張表的 PK 是 TEXT，所以還有一個隱藏的 rowid。用 `INSERT OR REPLACE … (rowid, …)` 指定已存在的 rowid，同樣會把舊列刪掉。dev-lead 交件時沒有列到這條路徑。

qa 怎麼檢查：
- 在預設連線（`recursive_triggers` 為 OFF）上，上表 9 條路徑各自執行 REPLACE，都要被拒絕，而且原列的內容和總列數都不變。
- 現有那個 strict xfail 測試要改成一般的通過測試。
- `schema_status` 的預期物件要有 15 個 trigger；少一個、內容被改或多一個，都判為不完整。
- store 的正常寫入全部通過。

## 驗證

- 讀過的檔案：
  - `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
  - `/home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md:202-209`
  - `/home/user/AICompany/work/research/2026-11-14-NM5-G1聚合語意與G5欄位集合-quant.md`
  - `/home/user/AICompany/work/reviews/2026-11-14-NM5儲存層交件-dev-lead.md`
  - 事先宣告草案的 `:2581-2596`
  - `/home/user/AICompany/apps/stock-desk/backend/app/dirdef/rules.py`
  - `/home/user/AICompany/.claude/worktrees/agent-a7959c61ea012b1e2/apps/stock-desk/backend/app/forecast/schema.py`
- 沒有執行任何程式，沒有讀 `.env` 或任何 DB。
- **未實證、須由 dev-lead 用測試確認的 3 點：**
  - (a) BEFORE INSERT trigger 在 REPLACE 處理衝突、刪除舊列之前就會觸發；
  - (b) 沒有明確指定 rowid 時，`NEW.rowid` 的值，SQLite 文件寫的是「undefined」，實際應為 −1。就算剛好撞到既有的 rowid，結果也只是誤拒寫入，屬於 fail-closed，不會放行；
  - (c) G1 改寫後的 54 例，標籤與 quant 的表逐例相同。

## 下一步

1. tech-writer：把下方補充全文 append 到 ADR-0030 的檔尾；決策包登錄一項 CEO 知悉。
2. dev-lead：在 `feat/nm5-forecast-storage` 實作補充一，交測試證明上面 (a)(b) 與 9 條路徑，再交 qa-reviewer。
3. quant：依 G1 改寫附錄 B 的寫法並寫進 v0.32；重出 54 例的表，`range_basis` 分 (i)／(ii) 兩欄。
4. 風控：在規則文字語意審時選定 (i) 或 (ii)。

---

**可直接 append 到 ADR-0030 的補充全文：**

```
## 補充一：SP-1 預測帳可被 INSERT OR REPLACE 改寫的收緊（2026-11-14）

- 決策者：tech-architect。來源：`work/reviews/2026-11-14-NM5儲存層交件-dev-lead.md` SP-1（已實證：SQLite 預設 `recursive_triggers=OFF` 時，REPLACE 刪除舊列不觸發 BEFORE DELETE trigger，`label` 被改寫）。
- 性質：收緊 D-2 第 6 點與 S-1。補充本文，不改本文；不改任何產品行為與字面，不擴大 CEO 核可範圍。CEO 可推翻。

1. 5 張表各加一個 trigger `{table}_no_replace`：`BEFORE INSERT`，`WHEN EXISTS` 同表中已有任一鍵相同的列，`SELECT RAISE(ABORT, 'append-only')`。須比對的鍵：
   - `forecast_run`：`run_id`；
   - `forecast_run_end`：`run_id`；
   - `forecast_input_series`：`series_id`、`content_sha256`；
   - `forecast_claim_registry`：`rowid`、`claim_id`；
   - `forecast_record`：`rowid`、`forecast_id`、(`claim_id`, `data_as_of`)。
   `WHEN` 子句只比對上列的鍵，不得有其他條件。
2. D-2 第 6 點的 UPDATE／DELETE trigger 不變，仍然沒有 `WHEN`、沒有例外。store 連線維持 `recursive_triggers=ON`，作為第二層防護。
3. `schema_status` 的預期物件含這 5 個 trigger（合計 15 個 trigger）；少一個、內容被改或多一個，都判為不完整，store 拒絕寫入。
4. 本補充必須在 CG-3 正式建表之前落地。正式主 DB 一旦建表，再加這些 trigger 就是遷移，依 K-12 禁止。
5. 未明確指定 rowid 時，SQLite 文件記載 `NEW.rowid` 的值為 undefined。在 D-5 第 6 點鎖定的執行環境下，它若誤中既有列，結果是拒絕寫入（fail-closed），不會放行。
6. 殘留風險（知悉，不處理）：其他程式仍可以 `DROP TRIGGER`、開 `writable_schema` 或直接改檔。`schema_status` 只偵測得到少了或被改過的物件；`report verify` 偵測得到 D-5 第 3 點涵蓋的欄位；但刪掉 trigger 再改寫 `created_at`／`late`，帳內無法偵測。依 ADR-0025 F-1（純自用、單一使用者），蓄意竄改不在威脅模型內。F-4 不變。

- **S-1a（逐條可檢查）**：在預設連線（`recursive_triggers=OFF`）上，第 1 點列出的 9 條鍵路徑各自執行 `INSERT OR REPLACE`，都以 `append-only` 被拒絕，而且原列內容與總列數都不變；store 的正常寫入全部通過（測試）。`sqlite_master` 中恰好有 15 個 ledger trigger（`schema_status`）。
```
