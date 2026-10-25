# ADR-0027 第一批落檔審查

- 審查者：qa-reviewer
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

**PASS，BLOCKING_ISSUES=false。** 無 critical／high。有 1 項 medium（非阻擋）、3 項 low，都不需要退回重做。

審查範圍：`git diff -- docs/adr/` 全文（18 個 hunk、約 96 行變動），對照五份核可來源逐項核對，並抽查現行 ADR 與程式碼的交叉引用。

**對核可來源的忠實度**
- 風控重審檔 required 1～9 已全部落實：
  - required 1：FL-78 (h) 的 fail-closed 改用無禁詞 fixture，並補了正向格。
  - required 2：D-1 `app/dirdef/` 列第 (3) 點改為遞迴掃字串值。
  - required 3：D-1 第 (4) 點與 FL-78 (h) 句末，兩處都加了禁 `object.__setattr__`。
  - required 4：N113-1 照實並陳補了 FL-78 (k) 對規則集升版的限制。
  - required 5～7：FL-42 新句 (1) 為進入點判準、(3) 例外限 `ENDPOINT_SURFACES` 中 kind 為 `on_demand` 的 route、(4) 唯讀查詢只回 `forecast_id` 並要求 5xx 回應本體為固定字面。
  - required 8：N115-9 逐項整項以風控定稿取代。
  - required 9：來源行已補。
- 修訂紀錄「風控」那一行，與重審檔第四部分定稿逐字相符。
- N115-9 對 N113-1 的連動句已改為「不是 FL-42 所稱的型別模組（N115-9 明列）」。
- coordinator 的檢查結果與我的讀法一致：10-gram 唯一未覆蓋處是標題插入「FL-42、」，N115-9 §4 第 1 點有明文；被刪片段都仍存在於修訂紀錄引文；17 項計數與預期相符。
- 修訂紀錄的結構與前一段（N-109／N-110，L5500 起）同形。

**交叉引用與事實核對**
- ADR 內的引用都能對上現行文字：D-7 第 8 點、D-8 第 3 點 mark-restored、D-14 G-7／`claim_dv`、A-77 的 D_reg、FL-52b (10)、`tests/test_forecast_boundaries.py`、FL-74／FL-77 (h2) 無重名。
- D-1 `errors.py` 的例外屬性值域，與 D-9／D-8 既有列舉一致（`schedule_window`／`gate_not_passed`／`already_committed`、`pre_validation_abort`／`result_abort`、`failed_gates`、`run_role` 等）。
- 程式碼事實與 ADR 標〔事實〕處相符：
  - `app/advice/loader.py:44` import `app.advice.context`。
  - `app/advice/context.py:29` import `app.advice.limits`。
  - `app/advice/limits.py:54` import `app.api.kelly_wording`。
  - `app/data/cache.py:261` 以 `BEGIN IMMEDIATE` 做讀後寫。
  - `pyproject.toml` 含 `pydantic` 與 `pyyaml`，所以「都是既有依賴」成立。
  - ADR-0025 L201 的規則檔路徑與 `BANNED_PHRASES` 掃描原文相符。
- D-15 第 3 點 3a／3b 確實存在，新增的「比照 3a／3b」沒有懸空。

## 2. 各部門回報：逐條問題

### `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`

1. **[可維護性／忠實度][medium，非阻擋]** D-1 `app/forecast/definitions.py` 列（約 L236）與 FL-78 (l)：定義物件的掃描寫成「全部字串欄位」，沒有採用遞迴「字串值」的寫法。
   - 風控重審檔 suggested 第 2 條建議採 required 2 的遞迴寫法，tech-writer 判斷點 5 沒套用。
   - 同一列的 dirdef 常數裡就有 `BASKET_EXCLUSION_REASON_ORDER` 這類很可能是 `tuple[str, ...]` 的欄位。照字面讀「字串欄位」，tuple 內的字串會漏掃，與同批 (3) 的遞迴寫法不一致。
   - 這不是核可來源遺漏，而是 suggested 未採。
   - 建議：dev-lead 實作 `definitions.py` 之前，由 TA 補一句「全部字串值，依欄位定義遞迴列舉」，同步改 FL-78 (l)。這屬收緊且是風控已寫出的建議，輕量確認即可。

2. **[可維護性][low]** 追蹤項尚未登入。
   - 風控重審檔第 4 節第 4 點要求納入後續追蹤清單：禁詞比對正規化、FL-78 (k) 升版阻擋的解除條件。
   - TA 另有兩項：舊版規則集的保存與重新載入、前瞻 claim 登記齊全的機器檢查。
   - 上述四項沒有落檔字句，而 N115-3 照實並陳（約 L5579）寫了「另列後續追蹤清單」，目前沒有對應條目。
   - 建議：coordinator 在合併前把四項登入追蹤清單（清單在 `work/`，不在 ADR 內）。

3. **[Edge case／可維護性][low]** FL-42 (4) 要求「`app/api/outlook.py` 不 import `display.py`」，同時 `OnDemandGateClosedView` 要經 `views` 產生。
   - 現行 ADR 沒有指明這個封閉 schema 型別定義在哪個模組（D-14 只說 `ON_DEMAND_CLOSED_DISCLOSURES` 在 `display.py`）。
   - 若型別在 `display.py`，route 的 `response_model` 會逼 `outlook.py` 去 import `display.py`，與這條打架。
   - 這是核可字句本身留下的空隙，不是落檔錯誤。
   - 建議：登入追蹤清單，在 on-demand 實作前定位型別所在模組。

4. **[可維護性][low]** 待決事項第一子項句序（判斷點 4）：「修訂紀錄（本段）最後落檔。」之後才接「N115-9 與 N115-5、N113-1 必須同一個 commit。」
   - 這符合 N115-9 §4 第 4 點「句末接上」的指示，語意無誤，只是讀起來略跳。
   - 可維持原樣。若要動，由 TA 一併調到「N113-1～N113-5 不得早於 N115-3」那句之後。

**其他**
- tech-writer 判斷點 6 屬實：`/home/user/AICompany/work/reviews/2026-10-24-N115-9-FL42衝突改字-tech-architect.md` 的 L21、L64、L126、L130 仍寫「直接 import／第一跳」。ADR 本文已是「進入點」，所以不影響 ADR，但該來源檔已與 ADR 不一致。建議 TA 同步，免得日後被當成判準的依據。

**tech-writer 判斷點 1～6 逐點評估**
- 判斷點 1（`〔轉存檔名〕` 填為「coordinator 轉存 `<檔名>`」）：可接受，與 required 9 的行同形。
- 判斷點 2（修訂紀錄前置「空行、`---`、空行」）：可接受，與 L5500 的前例相同。
- 判斷點 3（N115-9 的照實並陳新項放在 N115-6 項之後、N117-4 項之前）：可接受，來源只說「新增一項」，未指定位置，該位置合理。
- 判斷點 4（待決句序）：可接受，見上方 low 4。
- 判斷點 5（未套用的項目）：
  - 可接受：RC2 三條、RC1 的 N115-1 與 N115-6 suggested、TA 的「注意」說明。這些都是 suggested，或屬畫面、字面範圍，不在本批。
  - 有條件接受：
    - 重審檔的三條 suggested 中，「`definitions.py` 遞移掃描」建議補上，見 medium 1。
    - 重審檔的「FL-78 (h) 各格照舊適用」可有可無。
    - 重審檔的「比對正規化」只需登入追蹤清單，見 low 2。
  - 四個追蹤項：不由 tech-writer 自撰是正確的，但要有人登入清單，見 low 2。
- 判斷點 6：見上方「其他」，屬實，是 TA 側的待辦。

**風控要求列為 qa 實作檢查項**（本批僅文件，實作批時由 qa 檢查）：
- FL-42 進入點的 import 走法。
- `app/forecast/__init__.py` 不 import 任何 `app.*`。
- kind 為 `on_demand` 的 route 列舉。
- 5xx 回應本體為固定字面。

## 3. 驗證

- **Codex 第二意見未執行（環境不可用），依 CEO #53 合併前補跑。** `codex --version` 回傳 `bash: line 1: codex: command not found`，結束碼 127。
- 讀過：完整 diff（`git diff -- docs/adr/`，約 87KB）、coordinator 預產檢查檔、tech-writer 交件檔、風控兩份審查檔全文，以及 TA 的 N115-9 與 N113-1 修訂稿相關段落。
- 用 Read／Grep 抽查 ADR 現行段落（D-1、D-10、D-14、D-15、修訂紀錄前段）與 `apps/stock-desk/backend` 的程式碼事實，結果見第 1 節。
- 沒有實測 pydantic validation context 的行為。這點 ADR 已標〔未查證〕，風控已確認失敗方向為 fail-closed。
- 沒有讀 `.env`，沒有碰 `*.db`，沒有改任何檔案。

## 4. 下一步

1. 合併前由具備 Codex 的環境補跑 `/review`，依 CEO #53。
2. TA 處理 medium 1：補遞迴字串值寫法，連同 FL-78 (l)，輕量送風控確認。最遲在 dev-lead 實作 `definitions.py` 之前完成。
3. coordinator 登入四個追蹤項與 low 3 的 `OnDemandGateClosedView` 定位問題。
4. TA 把 N115-9 來源檔 §6 的「直接 import」同步為「進入點」。
5. 本批為純 ADR 文件、不涉 UI，PASS 後回報 CEO 即可，不需 qa-e2e。

## 唯讀權限判準常數

未觸及。
- 本次為 `docs/adr/` 的文件批，`git diff -- docs/adr/` 內沒有 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH` 的 `+`／`-` 行。
- 兩道機械檢查的指令未逐字執行：本次指令範圍限定為 `git diff -- docs/adr/` 與 `codex --version`。依 diff 全文閱讀判定未命中。
- 三問回答：改了什麼，無；為何改，不適用；有無對應 ADR，不適用。
- 常數 shadow 定義與值異動：diff 僅含 ADR-0027 一個檔案，全文閱讀中沒有看到相關常數出現。

## 實際執行過的 Bash 指令（逐字）

1. `git diff -- docs/adr/`（輸出過大，自動存成檔案後以 Read 讀取）
2. `codex --version`（失敗：`bash: line 1: codex: command not found`，結束碼 127）

其餘均使用 Read／Grep 工具，沒有執行其他 Bash 指令。

## Verdict
PASS
BLOCKING_ISSUES=false
