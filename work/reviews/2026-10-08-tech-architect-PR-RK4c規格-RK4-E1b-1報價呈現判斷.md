# tech-architect：PR-RK4c 實作規格（RK4-E1b-1，報價是否乘進呈現數字）（2026-10-08）

> tech-architect（唯讀）出規格；coordinator 轉錄，不含自行判斷。讀碼基準為工作樹（`book.py`／`limits.py`／`book_limits.py`／`snapshot.py`／`engine.py`／`api/advice.py` 與 HEAD 一致；`portfolio/summary.py` 為 PR-RK5b 進行中，本規格不碰）。行號僅供參考，qa 以函式名核對（RK4-C6）。
> 依據：`work/reviews/2026-10-08-E1b卡片與儀表匯率來源並存-RK4-E1b-1-風控.md` 修正要求 (a)～(d)。**本規格須經風控審查後 dev-lead 才可開工。**

## 結論摘要

1. **判斷位置採兩段式（T1）**：book 層照舊判 (A′)，但 (A′) 由「足以揭露」降為「必要條件」；book 層同時備「含報價版」與「不含報價版」兩組內容。「這一面有沒有呈現乘過報價的數字」改由各回應組裝端以**同一判斷式** `app/advice/limits.py::shows_price_input_figure` 決定：決策卡在 `api/advice.py`（讀卡片自己的 `limits_check` 與 `quantity_range`）；推播在 `alerts/engine.py::_limit_outcome`（讀本則訊息實際列出的 violated 條）；`/limits` G1 改呼叫同一函式、行為不變。與 ADR-0023 Decision 8-1（選句讀同一回應的實際判定，不在 `book.py` 重算）同原則。
2. **新發現（比風控推定更廣，需風控知悉）**：推播只列 violated 條細節，所以**只要訊息不含第 4 條**（例如只有第 1 條違反、第 4 條 passed），(A′) 仍附報價句與銜接句。既有 RK2-T3／T10 推播夾具（200 根日線，ATR 約 0.5，第 4 條約 0.5% passed，只有第 1 條違反）——**風控已核可的「報價句＋估值器句＋銜接句」推播本身即 RK4-E1b-1 同型**；tech-architect 在 R4-13／R4-18 亦未抓到，屬其疏漏。修正後**一致帳本 USD 推播（只有第 1 條違反）會多出 W-RK4-1**，現況即可達、使用者可見，須風控明示接受。
3. **輸出組合不需新字面**：(A″) 不成立時 `FX_APPLIED_NOTE` 一併不附，改走 (B) 的「W-RK4-1 → 估值器句」；(B) 也不成立則不附。正式路徑上 `FX_APPLIED_NOTE` 緊鄰 W-RK4-1 的並置**不會出現**（只剩 RK4-C4 test-only 格）；另建議 R4c-5(b) 清掉 O-1 在 book 層預設視圖的同一並置。兩個新格須風控逐格確認。
4. **S-E1b**：修正後 ATR 缺時 `FX_APPLIED_NOTE` 只出現在「ATR 缺但有建議股數區間」卡片格（「價格」屬實、「ATR」不精確，銜接句同）；推播永不含此句（只進 `reason`，S-3）。建議以 low 殘留接受（s-i）；要修須改兩句鎖定句字面（s-ii）。
5. **可達性**：台銀若仍如 2026-09-19 被擋（現況無法查證），帶銜接句的違規格在卡片與推播**目前都到不了**，條件式 VETO 未觸發；但 (i)／(ii) 一旦成立，推播端受影響範圍為「幾乎所有 USD 標的、只有第 1 條違反的風險推播」。建議 PR-RK4c 列為 W11 接線與任何台銀恢復工作的**硬前置**，並把「台銀是否仍被擋」排入定期查證。

## 一、方案比較

**判斷位置**：T1 兩段式（採用）——讀實際判定（含 engine ATR 回填、區間、推播 violated 集合）；內容仍只在 book 層產生（RK4-C3 簽名守門不變）；代價為 `BookContext`、`SymbolSnapshot` 各多一欄、engine 多一判斷點（取代 R4-18 engine 零 diff）；風險為新正式呼叫端忘傳參數回到舊行為，以 R4c-14 行為測試與原始碼掃描釘住。T2 book 層預算（book 層無 budget、規則動作、signals，算不出區間，不知推播監看哪幾條——做不到）；T3 book 層代理 `atr is not None`（被風控 (b) 禁止，「ATR 缺但有區間」少揭露且 W-RK4-1「不含價格」不實，推播只有第 1 條抓不到）；T4 整段揭露組裝搬到 api 與 engine（邏輯兩處各寫、破壞 RK4-C3）；T5 一律不含報價版（第 4 條或區間確實用到報價時無揭露，違反 ADR-0005 F-4／RK2）——皆否決。

**推播判斷集合**：P-strict（採用）＝本則訊息列出的 violated 條（`details` 來源），符合風控 (a)；P-loose＝snapshot 第 4 條有評估結果（第 4 條 passed 但未列進訊息時仍附「價格與 ATR 的換算」銜接句，不實）——否決。

**欄位命名**：`fx_disclosure` 在 `BookContext`、`SymbolSnapshot` 兩層保留原義（含報價版）；兩層新增 `fx_disclosure_without_quote`。代價為 engine 兩則單元測試要改（R4c-13 第 8、9 項）；反向命名需改十幾處 snapshot 斷言，不採。

## 二、決策（不需新 ADR）

ADR-0023 Decision 8-1 finalizer 原則延伸到匯率揭露尾段，加 ADR-0011 卡片／警示揭露條件第 3 次修訂（提議），交 tech-writer 加註 ADR-0011 L131 之後：
- **Context**：RK4-E1b-1。(A′) 以 `priced` 代理「報價乘進呈現數字」，在 ATR 缺、無區間的卡片，與未列出第 4 條的推播上失準。
- **Decision**：報價方法論句、銜接句、`FX_APPLIED_NOTE` 的出現條件改為 (A″) ≡ (A′) ∧ `shows_price_input_figure(該面呈現的判定, sized=該面有建議股數區間)`；不成立時改用 (B) 內容（W-RK4-1 → 估值器句）或不附。判斷由各回應組裝端讀自己的判定；book 層只準備內容。
- **Consequences**：好——W-RK4-1 前提（RK4-E1b-2）在卡片與推播由結構保證。壞——engine 新增判斷點；同一標的卡片與推播可能附不同組合（各自屬實）；一致帳本只有第 1 條違反的 USD 推播多 41 字；混源 log 仍按 context 記錄（RK2-L2 上界口徑不變）。
另由 tech-writer 於 X-3 任務單 KX-10 段補「精確條件第 3 次修訂」指向本規格。

## 三、對實作的約束 R4c-1～R4c-12

- **R4c-1【順序】** base 須含 a553e6c（PR-RK4a）與 2fec1ac（PR-RK4b），排在 PR-RK5b 合併之後；不碰 `portfolio/summary.py`；qa 以 `git merge-base --is-ancestor` 確認。
- **R4c-2【共用判斷式，唯一定義點】** 在 `app/advice/limits.py` 的 `LimitCheck` 定義之後新增：
  ```python
  def shows_price_input_figure(shown: Iterable[LimitCheck], *, sized: bool) -> bool:
      return sized or any(
          check.id in PRICE_INPUT_LIMIT_IDS and check.status != "not_evaluable" for check in shown
      )
  ```
  docstring 寫明「呈現的數字」三類：第 4 條有評估結果（passed 或 violated）、建議股數區間（經 `price_twd`）、日後任何 close×fx 或 ATR×fx 的數字（須加進本函式，見 T-E1b-2）。卡片、推播、`/limits` 三處只能經此函式判斷。app/ 內直接讀 `PRICE_INPUT_LIMIT_IDS` 只准：`limits.py` 本身、`alerts/engine.py::_limit_cause`（既有失敗原因用途，零修改）、本函式。
- **R4c-3【(A″)，禁止代理】** (A″) ≡ (A′) ∧ `quote_shown`。R4-11 的 (A′) 程式碼零修改，只把註解改為「報價到達本 context（必要條件）」。`book.py` 不得計算 `quote_shown` 或任何代理（`atr`、`context.atr`、`close`、`fx_rate`、區間），也不得 import `shows_price_input_figure`。
- **R4c-4【book 層兩組內容】** 於 `build_book_context`：`with_disclosures` 用既有 if／elif 鏈零修改（KX-A11 → `()`；(A′) → `_fx_disclosures`；(B) → `_valuation_disclosures`）。`without_disclosures`：不符列 → `()`；`_valuation_converted(matched)` 成立 → `_valuation_disclosures(matched, summary)`；其餘 → `()`。(B) 只求值一次兩組共用。`BookContext` 新增兩個 frozen 欄位、皆有預設值：`fx_disclosure_without_quote: str | None = None`、`symbol_notes_without_quote: tuple[str, ...] = ()`。不變式（須測）：`disclosed_quote is None ⇒ fx_disclosure == fx_disclosure_without_quote`。`_fx_disclosures` 呼叫條件與次數不變。
- **R4c-5【卡片 notes 尾段】** (a) `symbol_notes_without_quote`：其他 notes 照舊；`fx_note` 只在 `applied is None` 時保留（失敗句照留，`FX_APPLIED_NOTE` 一律拿掉）；最後接 `without_disclosures`；順序照 R4-14（`fx_note` 若有 → W → 估值器句；`MIXED_CURRENCY_NOTE` 緊鄰關係不變）。(b)（建議納入，需風控確認）既有 `symbol_notes`（含報價版）中 `FX_APPLIED_NOTE` 只在 `priced` 時加入——O-1 在 book 層預設視圖也不再有 `FX_APPLIED_NOTE` 緊鄰 W；正式路徑輸出不變（卡片 O-1 走 insufficient 分支本就到不了）；`BookContext.fx_note` 欄位與 `snapshot.reason` 零修改（S-3 不動）。
- **R4c-6【finalizer】** `book_notes(book, *, sector_comparison=None, quote_shown: bool | None = None)`；symbol scope：`None` 或 `True` → `symbol_notes`，`False` → `symbol_notes_without_quote`；book scope：`quote_shown` 非 `None` 即 `ValueError`。`BookContext.notes` 相容屬性維持（正式碼不讀，KD-2）。
- **R4c-7【決策卡，`api/advice.py::get_advice`】** ok 分支於 `build_advice` 之後：`quote_shown = shows_price_input_figure([LimitCheck.model_validate(e) for e in card["limits_check"]], sized=card["quantity_range"] is not None)`，再 `book_notes(book, quote_shown=quote_shown)`；insufficient 分支 `book_notes(book, quote_shown=False)`。不得重算 `evaluate_limits`（卡片判定已含 engine ATR 回填）。response schema 與前端零 diff。
- **R4c-8【推播】** `SymbolSnapshot` 新增 `fx_disclosure_without_quote: str | None = None`；`snapshot.py::build_snapshot` 多傳 `fx_disclosure_without_quote=book.fx_disclosure_without_quote`，`fx_disclosure`、`reason`、`price_cap_cause` 零修改。`engine.py::_limit_outcome` 只改 fired 分支：`disclosure = snapshot.fx_disclosure if shows_price_input_figure(violated, sized=False) else snapshot.fx_disclosure_without_quote`，有值才接在訊息後；skip 與 quiet 分支零修改。判斷**逐則規則**：同一 tick 同一 snapshot，監看第 4 條與監看第 1 條的規則可附不同組合。本條取代 R4-18「engine 零 diff」與 snapshot docstring「不自行設條件」。日後 engine 若把 passed 條細節列進訊息，須一併傳給判斷式（寫進註解）。
- **R4c-9【`/limits`】** `book_limits.py::_compared_quotes` 改為 `shows_price_input_figure(candidate.checks.values(), sized=False)`，行為不變；`book_limits.py` 其餘零 diff；R4-28 E0～E4 測試零修改作回歸證據。`disclosed_quote` 語意不變（只在 (A′) 設定），docstring 改為「報價已到達該 context；是否揭露由各回應依 `shows_price_input_figure` 決定」。
- **R4c-10【log】** `_log_unapplied_quote` 與 `_fx_disclosures` 混源 log 零修改；混源 log 仍按「(A′) 且異源」記錄、不看是否呈現，T-E1b-1 (iii) 照樣有效且更敏感；行數仍只當上界（RK2-L2）。
- **R4c-11【零 diff】** 檔案：`fx_notes.py`、`services/fx.py`、`valuation.py`、`summary.py`、`api/portfolio.py`、`advice/engine.py`、前端。字面常數一字不改：`FX_APPLIED_NOTE`、`FX_MIXED_SOURCES_NOTE`、`FX_VALUATION_SCOPE_NOTE`、W-RK5-1。函式：`_resolve_fx`、`_fx_disclosures`、`_valuation_disclosures`、`limits_fx_disclosures`、`evaluate_limits`、`suggest_quantity_range`。
- **R4c-12【註解與 docstring 改寫】** `BookContext.fx_disclosure`（含報價版之意）；`SymbolSnapshot.fx_disclosure`；`build_snapshot` docstring 講 F-4 的段落；`_limit_outcome` 中「every figure in details passed through the FX rate」註解；`FX_VALUATION_SCOPE_NOTE` 註解「withheld whenever it appears」改指 RK4-E1b-2 實質條件（改註解不改字面）。

## 四、逐格輸出

縮寫：AN＝`FX_APPLIED_NOTE`、Q＝報價句、V＝估值器句、BR＝銜接句、W＝W-RK4-1、FN＝失敗句、MX＝`MIXED_CURRENCY_NOTE`、S＝`quote_shown`。

| 格 | (A′) | (B) | 卡片 S=T（不變） | 卡片 S=F：現況 → 新 | 推播（第 4 條在訊息中） | 推播（第 4 條不在訊息中）：現況 → 新 | 正式路徑 |
|---|---|---|---|---|---|---|---|
| 一致帳本（同源、持有、ok） | T | T | AN→Q | AN→Q → **W→V** | Q | Q → **W V** | 現況可達（Yahoo 同源） |
| 混源（E1b） | T | T | AN→Q→V→BR | AN→Q→V→BR → **W→V** | Q V BR | Q V BR → **W V** | 需 (i)／(ii) |
| 候選（未持有） | T | F | AN→Q[→V→BR] | 同左 → **無匯率句** | 實務不觸發 | — | 可達（需 ATR 缺且無區間） |
| 持有但全未估值（情境 9、2b，報價有） | T | F | （不可能，總資產 0） | AN→Q → **無** | 不觸發 | — | 可達 |
| O-1 | F | T | 卡片到不了 | book 層預設 AN→W→V → W→V（R4c-5(b)） | W V | W V（不變） | 卡片到不了；推播可達 |
| 2a、pair 不符 | F | T | FN→W→V | 不變 | W V | 不變 | 可達 |
| 混雜幣別 | F | T | MX→W→V | 不變 | W V | 不變 | 可達 |
| 2c | — | — | insufficient：NO_FX→W→V（W4-T8） | 不變 | — | — | 可達 |
| TWD、不符列、2b 未套用、估值器 note 為空 | F | F | 無 | 無 | 無 | 無 | — |
| 報價 note 為空（RK4-C4） | F | T | **AN→W→V** | W→V | W V | W V | test-only |
| ATR 缺但有區間 | T | T | AN→Q[→V→BR]（S 恆為 T） | — | — | — | 可達（見 R4c-17） |

- **AN 緊鄰 W**：正式路徑沒有（S=T 需 priced；priced 時 (A′) 不成立只剩 note 為空一種，屬 test-only）。剩 RK4-C4 格，若不採 R4c-5(b) 另有 O-1 book 層預設。不需 creative-lead。
- **須風控逐格確認的新組合**：(α) 卡片上 W 前面無任何匯率句（E1b 新輸出；W 以「此處」指涉後一句，無懸空上下方指涉）；(β) 候選或全未估值的卡上無匯率句（分母其他持倉換算屬 O-3 已接受殘留；原 R2-4 靠 (A′) 帶進的 V 在 S=F 時一併消失）；(γ) 一致帳本、只有第 1 條違反的推播多出 W（已核可形式 `{details} W {來源句}`，但頻率變高；第二十八輪 B-3 推播「一致帳本無 W」期望會變；卡片端在第 4 條有評估時不變）。
- 同一標的卡片（S=T）與推播（S=F）可能附不同組合，各自對自己的數字屬實（比照 RK4-E1b-2）。

## 五、S-E1b

修正後 AN 出現條件為 applied ∧ priced ∧ S。ATR 缺時只剩「有區間」卡片格出現 AN：「價格」屬實（區間經 `price_twd`），「ATR」不精確（同卡第 4 條明示「缺少 ATR(14)」），同格 BR「依序對應價格與 ATR 的換算」同。E1b 原格（hold、無區間）AN 不再出現。推播 AN 永不進 fired 訊息。建議 (s-i) 列 low 殘留接受；(s-ii) 要修須 AN 與 BR 各一個「不含 ATR」變體字面，creative-lead 起草、風控逐字審、重跑 RK2／W4 掃描。

## 六、相容性與 R4c-13 封閉清單

- R4-11 程式不變、角色改為必要條件；R4-13／R4-14 含報價版內容與位置不變；R4-17 不變；R4-18 被 R4c-8 取代；R4-19 五處除第 2 處另受 R4c-5(b) 影響外依然有效；R4-22 `disclosed_quote` 語意不變只改 docstring；R4-23 改呼叫共用判斷式語意相同；W4-T3 book 層預設（S 為 None）各列不變、新增 S=F 欄（R4c-14）；W4-T4 受 R4c-5(b) 影響；W4-T6 字串不變；RK4-R2 互斥：兩組內容各自互斥，不含報價版永無 BR。
- **R4c-13【既有測試期望改寫，封閉清單（讀碼推定，比照 R4-19）】** 清單以外零修改；全套出現清單外失敗時 dev-lead 須停下回報 tech-architect 與風控，不得自行修改。
  1. `test_rk2_fx_source_set_disclosure.py::test_rk2_t3_t4_t10_alert_snapshot_and_fired_message`（4 參數）：推播一半改為 `message.endswith(f" {W} {valuation_note}")`，`quote_note`、BR 各 0 次；snapshot 一半（`snap.fx_disclosure == joined`、`reason`）不變。
  2. `test_rk2_t11_consistent_books_are_unchanged`：推播一半改為精確 `endswith(f" {W} {note}")`、W 恰 1 次；docstring 拿掉「byte-for-byte」、改名；卡片一半不變。
  3. `test_rk2_t7_scenario_9_end_to_end`：卡片一半改為無 AN、無任何 METHODOLOGY、無 W、無 BR；snapshot 一半不變。
  4. `test_rk2_t7_scenario_2b_end_to_end`：同第 3 項。
  5. （R4c-5(b)）`test_rk2_o1_cell_an_unusable_close_carries_no_source_sentence`：`fx_note` 在 notes 中的兩條斷言改為 `book.fx_note not in notes`、`notes[at:] == [scope, V]`；`book.fx_note is not None` 保留（S-3）。
  6. （R4c-5(b)）`test_rk4_fx_attribution.py::test_w4_t4_scope_note_first_then_the_sentences_it_scopes`：O-1 兩格 `before == book.fx_note` 改為 `not before.startswith(APPLIED_HEAD)`。
  7. （R4c-5(b)）`test_w4_t4_the_neighbour_is_the_failure_sentence_it_must_hold_beside`：移除 `o1-applied-note` 參數，改一則反向斷言。
  8. `test_alerts_engine.py::test_a_fired_risk_limit_message_carries_the_fx_disclosure`：拆兩部分——`breaching_context`（只有第 1 條違反）附 `fx_disclosure_without_quote`；新增第 4 條違反變體附 `fx_disclosure`。
  9. `test_alerts_engine.py::test_the_fx_disclosure_does_not_introduce_action_wording`：改設 `fx_disclosure_without_quote`（目前在空字串上空轉通過）。
  10. `tests/alerts_helpers.py::snapshot()`：新增 `fx_disclosure_without_quote` 參數（純加法）。
  11. `test_advice_limits.py` 的 `test_only_the_price_input_caps_depend_on_the_price_or_atr` 與 `test_every_price_input_cap_does_depend_on_the_price_or_atr`：加失敗訊息（T-E1b-2）。
- 判定零修改（附理由）：RK2-T3／T4／T10 卡片與 T10-4 卡片（200 根日線，第 4 條 passed，S=T）；`test_alerts_snapshot.py` 的 `fx_disclosure` 欄位斷言與 `per_trade_loss` fired 測試（第 4 條違反，S=T）；RK2-T9、W4-T10（五條全違反）；`test_w5_t7` 兩則（斷言 W-RK5-1；卡片 S=T）；x3c 混雜格 fired 測試（applied 為 None）；`test_r4_6` 的 2a、混雜、情境 9（applied 為 None）；W4-T9（只斷言 snapshot 欄位）；R4-28 E0～E4。dev-lead 須在 PR 說明附 grep `fx_disclosure`／`APPLIED_HEAD`／`book_notes(` 結果並逐行標注零修改理由。

## 七、測試 R4c-14～R4c-17（新檔 `tests/test_rk4c_quote_shown.py`）

- **R4c-14**：
  - 判斷式真值表：第 4 條 passed → T；violated → T；not_evaluable → F；不含第 4 條 → F；`sized=True` → T；空清單 → F。
  - E1b 卡片格（API）：8 根日線、MIXED 劇本；前提斷言（避免空轉）第 4 條 not_evaluable 且理由「缺少 ATR(14)」、action hold、`quantity_range` null、報價與估值器 id 不同（依 ladder 紀錄推導）；結果無 AN、無報價句、無 BR，尾段恰為 `[W, V]`；同源變體尾段 `[W, V]`、V 恰 1 次。
  - ATR 缺但有區間格（API）：8 根日線、窗內回落超過 20% 或 30%（`drawdown_protection`／`deep_drawdown_stop`）、第 1 條違反；前提 `quantity_range` 非 null、第 4 條 not_evaluable；結果 AN → Q → V → BR 保留（異源）。
  - 推播同型格：(a) MIXED 劇本、預設 budget（只有第 1 條）→ 結尾 `W V`、無 Q 無 BR，`snap.fx_disclosure_without_quote == f"{W} {V}"`；(b) `max_loss_per_trade=0.001`（第 4 條違反）→ 結尾 `Q V BR`；(c) 8 根日線 E1b 推播 → `W V`；(d) 同一 tick 兩條規則（`single_position_weight`、`per_trade_loss`）各附自己的組合；(e) 一致帳本：只有第 1 條 → `W note`，第 4 條違反 → `note`。
  - W4-T3 矩陣擴充：SCOPED／SILENT／APPLIED 每格以 `quote_shown=False` 斷言 `fx_disclosure_without_quote` 與 notes；APPLIED 三格期望 consistent → `(W, BANK)`、split → `(W, YAHOO)`、candidate → None，其餘同既有。不變式：兩版本永不 W 與 BR 同時；S=F 且 applied 非 None 時無 AN；AN 緊接 W 前只准 RK4-C4 格（失敗訊息 `BACK_TO_RISK`）；`disclosed_quote is None ⇒ 兩 disclosure 相等`。
  - 守門：掃 `api/advice.py` 原始碼每個 `book_notes(` 帶 `quote_shown=`；`book.py` 不 import `shows_price_input_figure`、程式碼不讀 `PRICE_INPUT_LIMIT_IDS`；book scope 傳 `quote_shown` 即 `ValueError`。
  - 推播長度：第 1、2、3、5 條違反＋W＋最長來源句＋降級資料層 ≤ 2000（RK4-R10 變體）。
- **R4c-15【mutation，每種須轉紅】** 1 api 永遠傳 `True`；2 engine 永遠用 `fx_disclosure`；3 engine 永遠用 `_without_quote`；4 判斷式拿掉 `sized`；5 判斷式拿掉 status 條件；6 判斷式換成 `book.context.atr is not None` 類代理；7 不含報價版保留 AN；8 不含報價版直接沿用含報價版；9 `_compared_quotes` 改傳 `sized=True`；10 移除 R4c-5(b)。
- **R4c-16【T-E1b-2 絆線】** (1) R4c-13 第 11 項兩則加失敗訊息「回風控重審 W-RK4-1（/limits G1 前提）」；(2) 新增：對 `_PRICED_CONTEXTS` 各格改變 close、atr、`fx_to_twd`（例 31.5 ↔ 29.0、×2），斷言 `PRICE_INPUT_LIMIT_IDS` 以外各條完整 `LimitCheck`（status、detail、observed）不變，訊息同上加「RK4-E1b-1 呈現數字定義」（現有釘選只比 status）；(3) 釘住 `BookLimitCheck` 欄位集合，`/limits` 不得出現股數區間，訊息同上。(suggested，交 frontend-engineer) vitest 掃前端無 `.fx_to_twd`／`["fx_to_twd"]` 屬性讀取。
- **R4c-17【T-E1b-3 構造提示】** 「ATR 缺但有區間」正式路徑可達：8 根日線、窗內回落超過 20%，加第 1 條違反；聚合動作是否 reduce 依 `_aggregate_action` 權重，以 API 回應 `action` 與 `quantity_range` 非 null 作構造前提核對。

## 八、可達性

- 帶銜接句的違規需同一 context 內估值器 fx_now 與報價落在不同 source id；台銀被擋時梯子只剩 Yahoo，兩次成功即同源、任一失敗即走 2a／2b，不出銜接句；FX 無快取層（估值器匯率一律走 ladder），**現況到不了**。
- 現況可達、本 PR 會改變：E1b 型卡片 AN(Yahoo)→Yahoo 句 改為 W→Yahoo 句；一致帳本只有第 1 條違反的推播 Yahoo 句 改為 W＋Yahoo 句；候選或全未估值 S=F 卡片拿掉 AN 與 Q。這些現行輸出不違反 RK2-R2，只有 AN 不精確（S-E1b 類）。
- 急迫性：T-E1b-1 任一成立時，推播端幾乎所有 USD 風險推播（預設 1% 下第 4 條很少違反）都會附不實銜接句，影響面大於卡片。建議 PR-RK4c 排在 W11 接線之前列硬前置，「台銀是否仍被擋」排入定期查證（tech-architect 無法查證）。

## 下一步（tech-architect 原文整理）

1. risk-compliance-officer 審：(A″) 與兩段式判斷位置；推播以 violated 集合判斷與「RK2-T3 推播核可格本身同型」自我更正；新組合 (α)(β)(γ)；R4c-5(b) 是否納入；S-E1b 採 (s-i)；R4c-13 封閉清單；X-10 加註合併後處置。
2. coordinator：轉錄 R4c-1～R4c-17 進 RK-4 任務單；「PR-RK4c 先於 W11 接線」列 W11 前置；安排台銀現況查證。
3. dev-lead：風控核可且 PR-RK5b 合併後依 R4c 開工；清單外失敗即停下回報。
4. tech-writer：ADR-0011 加註「第 3 次修訂（提議）」、X-3 任務單 KX-10 補段。
5. qa-reviewer：逐條核對 R4c、跑十種 mutation、`git diff` 確認 R4c-11 零 diff。
6. qa-e2e：T-E1b-3（R4c-17）；推播另以 (γ) 格補驗。
