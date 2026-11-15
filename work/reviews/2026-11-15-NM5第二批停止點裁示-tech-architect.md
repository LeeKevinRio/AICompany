# NM-5 第二批停止點裁示（SP-A～SP-C）與 ADR-0030 補充二

- 審查者：tech-architect
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

我逐題裁示如下。SP-B、SP-C 需要在 ADR-0030 加「補充二」，全文附在下方，性質是釐清，不放寬。四題都不需 CEO，也不需回送風控做語意審。

- **SP-A**：`name` 留在 `rules_logic_sha256` 內，不放進 `RULE_TEXT_FIELDS`。我撤回 G5 註記裡的相反意見。凍結包與 v0.32 一字不改。
- **SP-B**：由 `app.scheduler` 在組裝端把 `app.services.index.load_market_benchmark` 注入 recorder。K-2 照舊依可達性判定，`app.services.index` 不改。
- **SP-C**：D-3 第 2 點與 LA-G2-5 講的是兩種不同情形，不必二選一。分辨方式是看執行時刻是否已過該根 bar 那一天的 15:00。
- **待確認**：`item` 名稱、`fetched_at` 的取法、`OUTLOOK_RULE_FIELDS` 改成 9 個欄位，三項都核可。lax float 要在 CG-2 之前收緊，收緊不得改動規則位元組或任何雜湊。

## 各部門回報（tech-architect）

**1. SP-A：`name` 是否排除在 `rules_logic_sha256` 之外**
- **裁示**：留在雜湊內。dev-lead 用測試釘住現狀的做法是對的；參考值 h3 `ddd3c51a…`、h5 `e5310b8e…` 照用。
- **理由**：
  - 核心期間改任何一字都是新 claim（D-1 第 2 點），所以放不放進去目前沒有行為差異。
  - 但登記的值在 CG-2 之後就不能再改：日後若排除 `name`，重算結果會和登記值不同，執行期核對會判 `gate_closed`。所以現在選「留在雜湊內」是較嚴、fail-closed 的一邊。
  - 驗證層日後若要排除 `name`，依 D-8 第 5 點屬放寬，要走風控與 CEO。
  - 凍結包 4.3 第 2 輪（L629）與 V32-05 已經是這個意思，不必改字，也不必回送風控。
- **qa 檢查**：
  - 只改 `name` 時，`rules_logic_sha256` 會變。
  - `RULE_TEXT_FIELDS` 不含 `name`。
  - 我在 G5 列的檢查改為：「三個集合等於 quant 表 D、D-NL、Y 字面欄減去 `name`」。

**2. SP-B：recorder 怎麼取得輸入**
- **裁示**：在組裝端注入。
  - `app/scheduler.py` 註冊 `forecast_record` 時，把 `app.services.index.load_market_benchmark` 作為參數傳給 recorder 的進入點。
  - `app.forecast`、`app.outlook` 都不 import `app.services.index`。
  - inputs 維持用 `IndexSeriesAnswer` Protocol 接收回傳值。
- **否決的兩個做法**：
  - 「K-2 只看直接 import」：這是放寬。
  - 「讓 `app.services.index` 改成延遲 import `PriceService`」：為了過測試而去改核心外的共用服務，只是把依賴藏起來，而且容易壞。
- **理由**：
  - 這樣 K-2 與 K-3 都不必放寬。
  - 注入的是取數函式，不是 T 或時鐘，K-10 不變。
  - 就算注入過去的資料，`late` 仍由 store 時鐘判定，結果只會是 `late = 1`，或被 UNIQUE 拒絕，屬 fail-closed。
  - D-1 字面寫「只經 `app.services.index`」，所以要用補充二明寫這個讀法，否則 qa 會依字面判為違反 D-1。
- **qa 檢查**：
  - 既有可達性測試不變，仍然全綠。
  - 正式路徑上，recorder 進入點的呼叫端只有 `app/scheduler.py`（AST 檢查）。
  - 傳入的物件就是 `app.services.index.load_market_benchmark` 本身（`is` 斷言）。
  - 進入點的參數沒有 T、`as_of`、`clock` 類參數。

**3. SP-C：未定案 bar 怎麼處理**
- **裁示**：兩條描述的是不同情形，依「執行時刻是否已過該 bar 那一天的 15:00」分流。
  - 判斷依據：store 時鐘讀到的執行時刻 now，對照該 bar 的 session 日 S 的 `publish_cutoff`。
  - **已過**（now ≥ S 日 15:00）：照 D-3 第 2 點。重抓一次，仍不定案就記 `inputs_not_ready`。
  - **未過**：照 LA-G2-5。這根 bar 不進快照，T 不變，照常寫紀錄。
  - 例子：22:10 執行時，當天的 bar 若仍是早上取得的快取版本，屬「已過」，要重抓；若在次日早上補跑，看到當天盤中的 bar，屬「未過」，不收它並照常記前一天。
- **理由**：
  - 只要 S 日已到 15:00，該 bar 就應該定案，所以「不改用前一天」必須成立。
  - 尚未到 15:00 的 session 本來就不在可記錄範圍內，丟掉它不會造成前視偏誤，LA-G2-5 也要求紀錄的 `content_hash` 不受它影響。
- **qa 檢查**：
  - LA-G2-5 的 fixture 要補一個前提：注入時鐘早於 T 次日 15:00。這只是測試前提，不改凍結包的預期結果。
  - 另加一組反例：注入時鐘晚於 T 次日 15:00，重抓後仍不定案時，結果是 `inputs_not_ready`，不寫紀錄。

**4. 待確認四項**
- **`item` 名稱 `inputs_max_fetched_at`**：核可。它和 D-2 的欄位名、V32-10 的 `available` 同義。
  - qa 檢查：`PIT_ITEM` 只定義一次，而且等於這個字串；FX-F5 的預期改用它。
- **`fetched_at` 取 `PriceBar.as_of`**：核可。
  - 條件：`raw_timestamp_available=False`；寫進補充二；資料源或取數路徑更換時依 F-5 重審。
  - qa 檢查：快照裡每根 bar 都是 `fetched_at == as_of`。
- **`OUTLOOK_RULE_FIELDS` 改成 9 個欄位**：核可。ADR-0030 已 accepted，CG-2 明文要求這個集合「已設定」；ADR-0027 FL-78 (j) 已凍結。
  - 條件：原本釘「必須為空」的測試要改成釘「恰好等於凍結包 §3 的 9 個欄位」（相等，不是超集），不能只刪。依 B2D-5，FL-78 (j) 的交集格改為啟用。
- **lax float**：要在 CG-2 之前收緊，跟 recorder 批一起或另開一個小 commit 都可以。`weight`、`value` 沿用 `aggregation` 的同一個 strict float 型別定義：bool 和字串拒收；int 視為同值的 float；`allow_inf_nan=False`。
  - 收緊只會拒絕原本被轉成 1.0 的輸入。兩份 YAML 裡這兩個欄位若沒有 bool，位元組與雜湊都不會變。
  - qa 檢查：兩份 YAML 的 sha256，以及兩個 `rules_logic_sha256` 參考值，收緊前後逐位相同；只要有任何一個不同就停止並回報。另要有 `true`／`false`／`"1"`／`.inf` 拒收的反例測試。

**ADR-0030 補充二（全文）**

檔頭「補充紀錄」那一行之後加一行：

> - 補充紀錄：2026-11-15 append 補充二（SP-B 輸入注入、SP-C 未定案 bar 分流、快照時間欄與 PIT 缺項名；tech-architect 裁示，釐清，不放寬，不改使用者面字面，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第二批交件-dev-lead.md`）。

檔尾 append：

```
## 補充二：大盤輸入的取得方式、未定案 bar 的分流、快照時間欄（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-NM5第二批交件-dev-lead.md` SP-B、SP-C 與待確認事項（已實證：`app.services.index` 在模組層級 import `PriceService`，使 import 它的模組可達 `app.portfolio`、`app.positions`）。
- 性質：釐清 D-1 第 3 點 inputs 列、D-3 第 1～2 點、D-5 第 1 點的讀法。補充本文，不改本文；不放寬 K-2、K-3、K-10、S-4、S-6；不改任何使用者面字面。CEO 可推翻。

1. **取得方式**：正式路徑的大盤輸入，是 `app.services.index.load_market_benchmark` 的回傳值。`app.scheduler` 註冊 job `forecast_record` 時，把這個函式以參數傳入 recorder 的進入點。`app/forecast/**`、`app/outlook/**` 不 import `app.services.index`；`app/outlook/inputs.py` 只依 Protocol 接收回傳值。D-1 第 3 點的「只經 `app.services.index` 取得」以此讀。K-2 依可達性（含遞移 import）判定，不變。這個參數是取數函式，不是 T、`as_of` 或時鐘，K-10 不變；以其他取數函式呼叫 recorder，只限 tests 與 D-7 harness（K-11 不變）。`late` 仍由 store 時鐘判定，所以注入過去的資料只會得到 `late = 1`，或被 UNIQUE 拒絕。
2. **未定案 bar 的分流**：以 store 時鐘讀取執行時刻 now。對每一根未定案 bar（session 日 S）：
   (a) now 不早於 S 日 `TW_POLICY.publish_cutoff`：屬 D-3 第 2 點。recorder 重新呼叫取數函式一次；之後仍有任何一根屬 (a)，就記 `inputs_not_ready`（`candidate_t` 填其中最大的 S），不寫紀錄，也不改用更早的定案 bar 當 T。
   (b) now 早於 S 日 `TW_POLICY.publish_cutoff`：該 session 還不到可以定案的時點，屬 LA-G2-5。這根 bar 不進快照，列入 `dropped_rows_json`；T 為最新一根定案 bar，照常寫紀錄。
3. **快照時間欄**：這條取數路徑上每根 bar 只有一個取回時間，快照的 `fetched_at` 取 `PriceBar.as_of`，`raw_timestamp_available = false`；D-3 第 2 點的「取較早者」因此等於 `as_of`。資料源或取數路徑更換時，依 F-5 重審本點。
4. **PIT 缺項名**：`E-PIT-UNVERIFIED` 的 `item` 為 `inputs_max_fetched_at`，只定義一次。

- **S-4a（逐條可檢查）**：可達性測試不變且全綠；正式路徑上 recorder 進入點只由 `app/scheduler.py` 呼叫，而且傳入的物件就是 `app.services.index.load_market_benchmark`（AST 加 `is` 斷言）；(a) 情形重抓一次後記 `inputs_not_ready`、不寫紀錄；(b) 情形的 `content_hash` 與取數端不回傳該 bar 時相同；快照中每根 bar 都是 `fetched_at == as_of`（測試）。
```

## 驗證

- **我讀過的檔案**：
  - 交件報告 `/home/user/AICompany/work/reviews/2026-11-15-NM5第二批交件-dev-lead.md`
  - ADR-0030 全文 `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
  - 凍結包 `/home/user/AICompany/work/research/2026-11-14-NM5凍結包-大盤h3h5-quant.md`：L8、L235、L263、L278-289、L627-629、L802、L832、L855、L873
  - 我的 G5 註記 `/home/user/AICompany/work/reviews/2026-11-14-G1位置與SP1裁示-tech-architect.md` L48-57
  - ADR-0027 中 FL-78 (j)、B2D-5 的條目位置（只讀到條目位置，長行內文沒有展開）
- **沒有看到的部分**：
  - `5c70a30d` 的程式不在本機工作樹，我沒有讀到。可達性、lax float、`PriceBar` 只有一個時間欄，這三點都以 dev-lead 的實證為準。
  - 沒有執行任何程式。
- **兩項待 dev-lead 實測**：
  - 現行 pydantic 的 strict float 遇到 int 時，輸出型別是否與 lax 模式相同。
  - 兩份 YAML 的 `weight`、`value` 是否確實沒有 bool。
  - 這兩項由 lax float 那一項的 qa 檢查（雜湊前後逐位相同）把關。
- 沒有讀 `.env`，沒有碰任何 `.db`。

## 下一步

1. **tech-writer**：把補充二的檔頭行與全文落檔到 ADR-0030，單一 commit：`docs: ADR-0030 補充二 輸入注入與未定案 bar 分流`。
2. **dev-lead**：recorder 批依補充二第 1、2 點實作，同時補上 LA-G2-5 的時鐘前提與 (a) 的反例；在 CG-2 之前收緊 lax float；FX-F5 的預期改用 `inputs_max_fetched_at`。
3. **quant**：知悉 SP-A 的結論，凍結包不必改。另外，我的 G5 檢查改成「Y 字面欄減去 `name`」。
4. **風控**：這次只是副本知會補充二，不需語意審。RC-143 的定字仍依 dev-lead 的建議，由 quant 與風控處理。
5. **qa-reviewer**：依上面各題的「qa 檢查」與 S-4a 驗收，含 Codex 第二意見。
