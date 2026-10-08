# tech-architect（2026-10-08，唯讀；coordinator 轉錄）：PR-RK4a／RK4b 實作規格 R4-10～R4-29、RK-5 約束 R5-10a～d／R5-11、S-L3 NaN 匯率查證

- **RK-4**：RK4-R12 採 (R12-a)「依賴 X-3c」（(B) 的 `status=="ok"` 結構上排除不符列，不另加判斷點）；(A′)、(B) 逐字條件、W-RK4-1 常數名 `FX_VALUATION_SCOPE_NOTE`、位置與互斥、既有測試期望改寫清單（R4-19 四處，第 4 處超出風控原範圍需確認）；qa low 補測 R4-20。`/limits` 第一組 G1／第二組 G2 predicate、組態 E0～E4；**E4（第一組 ≥ 2 不同來源）可達**，建議 (α) 退回不附匯率句＋WARNING，須風控明示接受。
- **RK-5**：R5-10a（N-2 徽章 helper 與 W11-5 同 PR、表格列）、R5-10b（N-3 快取命中 source 為原列 id）、R5-10c（`fx_open` 為完整 FxInfo、失敗時 UNAVAILABLE 非 None）、R5-10d（PR-RK5a rebase 到 X-3c 後、KX-A2 明寫 `fx_open=None`）、R5-11（W-RK5-1 常數放 `app/portfolio/summary.py`）。
- **S-L3**：NaN 正式路徑不可達（pydantic Decimal `allow_inf_nan=False`）；+inf 理論可達（≥1.8e308 有限值 `float()` 溢位）；low，併入 F-1b；**新增 KF-15**：`book.py` `_log_unapplied_quote` 的 `fx.rate > 0.0` 也須改經 `usable_rate`；ADR-0015 交叉註記：快取讀取端須經驗證建構 `FxRate`，不得 `model_construct`。
- 待風控確認四點：E4 採 (α)、G1／G2 跨組依 id 去重的解讀、W4-T6 在 same-source 格的解讀、R4-19 第 4 項期望改寫。

全文如下（標題層級各降一級）。

### 本次結論

（我是唯讀角色，以下行號取自讀檔當下的工作樹。dev-lead／frontend-engineer 正在實作 X-3c，`book.py`、`valuation.py` 的行號可能會漂移。我沒辦法跑 git，所以無法確認工作樹與 HEAD cf9619e 是否一致。讀檔當下 `valuation.py` 裡還沒有 `currency_market_mismatch`，X-3c 的後端還沒進這個檔。）

1. **RK-4**：(A′)、(B) 與 `/limits` 兩組來源的 predicate 都寫成可直接實作的條文，見 R4-10～R4-29。
   - **RK4-R12 選「依賴 X-3c」，不在 (B) 另做排除。** 理由：X-3c 之後不符列一定是 `insufficient_data` 且 `fx` 為 None，(B) 的 `status=="ok"` 條件在結構上就會排除它。(B) 裡再呼叫一次 `currency_matches_market` 會變成死碼，也會在 KX-A1 的單一判斷點之外多出第二個判斷點。
   - **`/limits` 第一組有兩個以上不同來源（E4）時**：建議整份回應不附任何匯率句（等於現況，風控已列 low），另記一行固定開頭的 WARNING 作為偵測。**這個退路要風控明示接受**；不接受的話，PR-RK4b 不得出貨。
2. **R5-10 補段**：RK5-R4（N-2）、RK5-R5（N-3）、fx_open 須記錄 `data_status`、R5-6（rebase 到 X-3c 之後，KX-A2 分支同時令 `fx_open=None`）都寫成可核對條文（R5-10a～d），另把 W5-T1 常數的位置定為 R5-11。
3. **S-L3**：
   - **NaN 在正式路徑上到不了**（讀碼推定）。上游的 `FxRate.rate: Decimal` 受 pydantic Decimal 預設 `allow_inf_nan=False` 擋下；`float()` 作用在有限 Decimal 上不會產生 NaN。
   - **+inf 理論上可達**：要有 ≥ 約 1.8e308 的荒謬有限值，經 `services/fx.py:107` 的 `float()` 溢位成 inf。-inf 已被 `<= 0.0` 擋下。
   - **建議等級 low**（潛在問題，不另開單）。最小修法是併入 F-1b：D5／KF-7 本來就會把 L1329 改用 `usable_rate`。
   - **新發現**：PR-RK2 在 `_log_unapplied_quote`（`book.py:1287`）又寫了一處 `fx.rate > 0.0`，F-1b 要一起改，否則遇到 inf 時 2a 計數會漏記。
4. **qa low**：`shown[0][0] == applied.source` 的補測位置定在 `test_rk2_fx_source_set_disclosure.py` 的 RK2-T5 段，直接呼叫 `book_module._fx_disclosures`（R4-20）。

### 各部門回報（tech-architect）

#### 一、PR-RK4a（book 層，卡片與推播）

**方案比較（RK4-R12）**
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **(R12-a) 依賴 X-3c（採用）** | 不符列一定是 insufficient、`fx=None`（KX-A2），(B) 在結構上就不成立；判斷只有 KX-A1 一處；`/limits` 第二組也自動排除 | PR-RK4a 被 X-3c 卡住（coordinator 已排 X-3c 在前，實際成本約為 0） | 低；X-3c 若退版會靠 W4-T9 抓到 |
| (R12-b) (B) 明確呼叫 `currency_matches_market` | 不依賴順序 | X-3c 合併後成為死碼；book 層多一個判斷點；B 型列被放大的市值仍在總資產與第二組裡，只拿掉句子而沒處理失真 | 中 |

**對實作的約束（R4-10 起；接在既有 R4-1～R4-9 之後）**

- **R4-10【順序】** PR-RK4a 的 base 必須已含 X-3c（KX-A2、KX-A11）與 PR-RK2；照 coordinator 排序也含 PR-RK5a。
  - qa 用 `git diff <base>` 確認 base 的 `valuation.py` 已有 `currency_market_mismatch` 短路。
- **R4-11【(A′)，逐字條件】** `a_prime = applied is not None and priced and applied.source_note != ""`。
  - `applied` 只取 `_resolve_fx` 的回傳值；`priced` 就是 `book.py:1114` 那個既有變數。
  - 不得另寫匯率判斷。這樣 F-1b 改用 `usable_rate` 之後，(A′) 會自動收緊。
  - 混雜幣別時 `applied` 恆為 None，維持現況。
- **R4-12【(B)，逐字條件】** `b = any(p.valuation.status == "ok" and p.valuation.fx is not None and p.valuation.fx.data_status is not DataStatus.UNAVAILABLE and p.valuation.fx.source_note != "" for p in matched)`。
  - `matched` 就是 `_matching(summary, symbol, market)`，也就是 `book.py:1124` 的同一個變數。
  - 只能讀 `valuation.status` 與 `valuation.fx`。**不得讀 `fx_open`**，也不得讀持倉的 `currency`／`market`（RK4-R12 採 R12-a）。
  - 未持有時 `matched` 為空，(B) 恆為 False（對應 W4-T3 的「O-1 但未持有」與「未持有的候選標的」）。
- **R4-13【內容】**
  - (A′) 成立：沿用 `_fx_disclosures(applied, summary)`，零修改（RK2 內容、R4-4 逐位元組不變）。
  - (A′) 不成立且 (B) 成立：`(W-RK4-1,) + 估值器句`。
    - 估值器句的 pair 依成立 (B) 的 matched 列 `fx.pair` 首次出現順序；對每個 pair 取 `_valued_rates(summary, pair)`，濾掉空 note，依 **source id** 去重（S-1），保持 summary 順序。
    - **永遠不附 `FX_MIXED_SOURCES_NOTE`。**
  - 其他情形：`()`。
- **R4-14【位置與互斥】**
  - `disclosures` 的第一項是 W-RK4-1。`fx_disclosure = " ".join(disclosures)`，所以推播是 `{details} W-RK4-1 {來源句}`。
  - 卡片 notes 沿用 `book.py:1167-1169` 的順序：`fx_note`（若有）→ W-RK4-1 → 估值器句，三者索引連續。混雜格的 `MIXED_CURRENCY_NOTE` 在 L1143 加入，中間不會插入其他句子。
  - 銜接句與 W-RK4-1 分屬互斥的 if／elif 分支，結構上不可能同時出現；W4-T5 跑遍所有格來釘住。
- **R4-15【KX-A11 分支】** X-3c 的「不混雜但有不符批次」短路分支內，`disclosures` 一律是 `()`，(B) 不在該分支求值（W4-T9）。
- **R4-16【常數】**
  - W-RK4-1 的 41 字常數放在 `book.py`，緊鄰 `FX_MIXED_SOURCES_NOTE`。名稱建議 `FX_VALUATION_SCOPE_NOTE`。
  - 旁邊加註「風控核可文案,修改須重新送審(2026-10-08)」與裁定檔路徑。
  - `fx_notes.py` 零 diff；這個常數不得出現在 `SOURCE_NOTES`（W4-T1）。
- **R4-17【2a 計數 log】** `_log_unapplied_quote` 的呼叫條件（`applied is None and not mixed_currencies`）與訊息字串零修改。O-1（applied 但不 priced）不呼叫它，`_fx_disclosures` 也不呼叫，所以不會記混源 log。
- **R4-18【docstring】** `BookContext.fx_disclosure`（`book.py:428-437`）改寫成「(A′) 或 (B)」；`snapshot.py:94-100` 的 docstring 照 R4-1 准許改寫，其餘 snapshot、engine、`api/advice.py`、`api/portfolio.py` 零 diff。
- **R4-19【既有測試期望改寫清單（RK4-R2）】** 除下列 4 處外，其餘測試零修改。dev-lead 在 PR 說明附上 grep `fx_disclosure is None`／`METHODOLOGY`／`SOURCE_NOTES` 的結果，交 qa 核對。
  1. `test_rk2_t7_unapplied_branches_stay_silent_whatever_the_book_used`（約 L614-637）：
     - TWD 段零修改（O-3／T10-5）。
     - K-1 段改成 `disclosure == f"{W} {BANK_NOTE}"`；notes 依序連續為 `MIXED_CURRENCY_NOTE`、W、`BANK_NOTE`；沒有 `YAHOO_NOTE`、沒有銜接句。
     - 2a 段改成 `disclosure == f"{W} {BANK_NOTE}"`；notes 依序連續為 `FX_UNAVAILABLE_NOTE…`、W、`BANK_NOTE`；沒有銜接句。
     - docstring 由「R2-3」改為「RK4-R1 (B)」。
  2. `test_rk2_o1_cell_an_unusable_close_carries_no_source_sentence`（約 L653-697）：
     - split 參數：`fx_disclosure == f"{W} {YAHOO_NOTE}"`，而且 `BANK_NOTE not in notes`。
     - same-source 參數：`f"{W} {BANK_NOTE}"`。
     - `context.close`、`context.atr` 為 None，`fx_note` 照舊（S-3），`_book_records == []`，以上全部維持。
     - 新增一個變體：summary 只有 MSFT 的 USD 列（未持有 AAPL）時，`fx_disclosure is None`。
  3. `test_rk2_t7_scenario_2a_end_to_end`（約 L733-755）：
     - snapshot `fx_disclosure == f"{W} {note(紀錄到的估值器來源)}"`（比照 RK2-T4／W4-T6，依 ladder 紀錄推導）。
     - 卡片 notes 依序連續為 `FX_UNAVAILABLE_NOTE…`、W、估值器句。
     - S-4 的 log 斷言零修改。
  4. **超出風控「2a／混雜／O-1」範圍、需風控機械確認**：`test_rk2_t5_no_bridge_unless_exactly_two_items_remain` 的第一段（約 L573-576，報價 `note=""`）。依 (A′) 的「note 非空」字面，這一格改走 (B)，期望值變成 `f"{W} {YAHOO_NOTE}"`。
     - 這一格只存在於測試：`source_note()` 只對 `"none"` 回空字串（`fx_notes.py:60-61`），而 `"none"` 一定沒有 rate（`fx.py:385-392`、`services/fx.py:87-102`）。
     - 新輸出比舊輸出更準確：舊輸出單獨一句 Yahoo，可能被讀成涵蓋價格與 ATR。
  - 確認零修改的：T10-1～T10-4（A 型列在估值器是 `fx=None`；`_position` 不帶 FxInfo）、RK2-T3／T4／T10（MIXED 都走 (A′)）、RK2-T5 其餘、RK2-T7 的情境 9 與 2b（單元與端到端）、候選兩則、RK2-T11、RK2-R4、`test_alerts_snapshot.py:233-252`、`test_advice_book.py:504-513`、`test_x3_fx_disclosure.py:315-324`。
- **R4-20【qa low 補測】** 在 `tests/test_rk2_fx_source_set_disclosure.py` 的 RK2-T5 段（`test_rk2_t5_no_bridge_unless_exactly_two_items_remain` 之後）新增 `test_rk2_t5_the_bridge_needs_the_quote_as_its_first_item`。
  - 直接呼叫 `book_module._fx_disclosures(_quote(BANK, note=""), book_summary(_usd(1, source=YAHOO), _usd(2, source="fx_other", symbol="MSFT")))`，斷言結果 `== (YAHOO_NOTE, GENERIC_SOURCE_NOTE)`。
  - 用途：如果拿掉 `book.py:1269` 的 `shown[0][0] == applied.source`，這一格會附上銜接句、測試轉紅。
  - PR-RK4a 之後，`_fx_disclosures` 只在 (A′) 下被呼叫，這個子條件會變成縱深防護。**保留它**，docstring 寫明「前置條件 `applied.source_note` 非空」，不得刪除。
- **R4-21** 2c 只在 API 回應層測（RK4-R7、W4-T8），前端零 diff。
- **測試位置**：W4-T1～T11 放新檔 `tests/test_rk4_fx_attribution.py`；T10-5 放 `tests/test_x3_fx_disclosure.py`。

**W4-T3 出現條件格（供測試矩陣對照）**
| 格 | (A′) | (B) | disclosures |
|---|---|---|---|
| 一致帳本已套用、候選已套用 | T | — | RK2 內容（不變） |
| 2a（`FX_UNAVAILABLE`）、PAIR_MISMATCH、2c、混雜（USD 批 ok）、O-1 且持有 ok 的 USD | F | T | W, 估值器句 |
| O-1 未持有、TWD 標的（O-3）、情境 9、2b 且未套用、note 空、不符列（X-3c 後） | F | F | None |

#### 二、PR-RK4b（`/limits`）

- **R4-22【資料面】** 加法式變更，frozen、有預設值：
  - `BookContext.disclosed_quote: FxQuote | None = None`：只在 `build_book_context` 內、(A′) 成立時設為 `applied`。
  - `BookContext.valued_fx_sources: tuple[tuple[str, str], ...] = ()`：只在 `build_book_level_context` 設定，也就是 RK4-R5 准許的唯一判斷點，位置在 `book.py:1052` 的 return 之前。
  - `_Candidate` 加 `disclosed_quote`；`_symbol_context`（`book_limits.py:486-506`）改成回傳整個 `BookContext`，或回傳 `(context, disclosed_quote)`。
  - snapshot、engine、`api/*` 都不讀這兩個欄位。
- **R4-23【第一組 G1 predicate】** `P1(c) ≡ c ∈ candidates（_split_by_valuation 的回傳，也就是全部批次 ok）∧ c.disclosed_quote is not None ∧ ∃ id ∈ PRICE_INPUT_LIMIT_IDS: c.checks[id].status != "not_evaluable"`。
  - 理由：報價只換算 close 與 ATR，而讀這兩者的上限只有 `per_trade_loss`（`limits.py:83-90`，有測試釘住）。(A′) 成立但 ATR 缺時，第 4 條會把該標的排除，報價沒有乘進任何呈現的數字，所以不計。
  - G1 依候選順序（`_group_positions` 的帳本順序）取 `(source, source_note)`，依 source id 去重。
- **R4-24【第二組 G2 predicate（book scope 的 (B)）】** 全帳 `summary.positions` 中，`status=="ok"`、`fx` 非 None、非 UNAVAILABLE、note 非空的列，取 `(fx.source, fx.source_note)`，依 source id 去重，保持 summary 順序。只讀 `fx`，不讀 `fx_open`。
  - 這一組會涵蓋「該標的因部分批次未估值而被排除，但已估值批次仍算進總資產」的情形（RK4-R5 的理由）。
- **R4-25【彙整】** `book.py` 新增純函式 `limits_fx_disclosures(book_level: BookContext, quotes: Sequence[FxQuote]) -> tuple[str, ...]`。
  - `book_limits` 只負責篩出 P1 的報價，再把結果接在 `book_notes(...)` 之後（`book_limits.py:400`）。
  - **跨組也依 source id 去重**：G2 裡與 G1 同 id 的項目不重複列出（與 `_fx_disclosures` 的 `seen` 語意一致）。風控寫的「各自去重」我解讀為「不得重複」，**請風控確認這個解讀**。
  - 本條部分取代 R4-7 的「以句為單位去重」。
- **R4-26【組態枚舉】** 令 k1、k2 為 G1、G2 的不同 id 數。正式路徑上 k2 ≤ 1：同一份 summary 出自同一次 `value_all`，memo 以 `(pair, target)` 為 key（`valuation.py:480-485`）。
  | 組態 | 條件 | 輸出 |
  |---|---|---|
  | E0 | k1=0、k2=0（純台幣帳本，或 USD 列全部不是 ok） | `()`，逐位元組不變 |
  | E1 | k1=0、k2=1 | `(W-RK4-1, G2 句)` |
  | E2 | k1=1、G2 ⊆ G1 的 id（同來源） | `(G1 句,)` |
  | E3 | k1=1、k2=1、id 不同 | `(G1 句, G2 句, FX_MIXED_SOURCES_NOTE)` |
  | E4 | k1≥2，或 k2≥2（後者結構上不可達，列入是為了讓函式全域有定義） | `()`，並記 WARNING |
  - **E4 是可達的**：`api/portfolio.py:177` 對每個標的以各自的 `latest.date` 分別呼叫 ladder，台銀時有時無時，兩個 USD 標的就可能落在不同來源。
  - **E4 的偵測方式**：logger `app.advice.book` 記一行英文 WARNING，開頭固定為 `fx quote sources differ across compared holdings:`，後接 `pair=%s sources=%s`（排序後的 id）。每次請求最多一行；不含 symbol、金額、匯率；用 caplog 釘住開頭字串。
  - 方案比較：
    - (α) 建議採用：退回現況（不附任何匯率句）加 WARNING。理由是不產生未經審查的組態字面，而且現況已由風控列為 low。
    - (β) 在風控裁定 E4 字面前，PR-RK4b 整體不出貨。
    - (γ) `/limits` 改成同一 pair 只查一次報價。這會改變「依 bar 日期換算」的語意，否決。
  - **(α) 須風控明示接受**；不接受就走 (β)。
- **R4-27** 純台幣帳本的 `/limits` 回應逐位元組不變，`PortfolioLimitsResponse` schema 不變，前端零 diff；`api/portfolio.py` 零 diff。
- **R4-28【W4-T7 對應】** 四種組態各一則測試：E1、E3、E4（兩個 USD 標的，fake ladder 依日期分別回 BANK／YAHOO；斷言 notes 裡沒有任何 `SOURCE_NOTES`／`GENERIC`／W／銜接句，WARNING 恰好一行）、E0 純台幣。另補 E2。期望值依 ladder 紀錄推導（W4-T6）。
- **R4-29【既有測試改寫】** `test_rk2_t7_limits_and_overview_never_carry_the_bridge`（約 L782-798）：`/limits` 那一半改成 E3 的期望（FOUR_B 下報價為 BANK、估值器 fx_now 為 YAHOO，依紀錄推導）；overview 那一半零修改；測試改名。
- **待風控確認的解讀**：W4-T6 的「(A′) 不成立時不得包含報價的 source_note」。在 same-source 格（O-1 或 2a，報價與估值器同一個 id），那句會以**估值器**的身分出現一次。我建議把 W4-T6 解讀為「不得因報價而出現」，請風控確認。

#### 三、RK-5 約束增補（R5-10 改寫為 R5-10a～d，新增 R5-11）

- **R5-10a【N-2／RK5-R4，W11-5 同 PR】**
  - PR-RK5c 從 `page.tsx:62-64` 抽出的總覽徽章 helper，必須在 W11-5 的**同一個 PR** 加上 `origin_status === "backup"` 分支。
  - 判斷對象是 ok 持倉的 `fx` 與 `fx_open` 兩者。
  - C-22 表格驅動的 vitest 要為總覽 helper 加上下列各列：
    - `(backup, null, null)` → 有
    - `(cached_stale, true, backup)` → 有
    - `(cached_stale, false, backup)` → 有
    - `(cached_stale, true, fresh)` → 無
    - `(fresh, null, null)` → 無
    - `(unavailable, …)` → 無
    - 以上每一列分別套在 `fx`、`fx_open`；非 ok 的列一律無。
  - qa：W11-5 的 PR diff 沒有這個分支或這些列，就依風控預先否決，不得合併。
- **R5-10b【N-3／RK5-R5】**
  - ADR-0015 D-4 的表格加 `source` 欄：快取命中與舊值退回時，`FxRateResult.source` 等於所選列（視窗內日期最新的那一列，也就是消費端 `max(date)` 會選到的列）的 `fx_rate_cache.source` 原始 id。不得是 `fx_ladder`、`none`，或快取層自己的 id。
  - 視窗內各列來源不同時，取日期最新那一列的 id。
  - 測試：每一種情境都斷言 `result.source == 該列 source`；經過 `_lookup_fx` 之後，`valuation.fx.source` 與 `fx_open.source` 也相同；`source_note(result.source)` 等於該來源的 `SOURCE_NOTES` 項。
- **R5-10c【W-RK5-1 定稿段：fx_open 必須記錄 data_status】**
  - PR-RK5a 的 `Valuation.fx_open` 必須是 `_latest_fx_on_or_before(pair, opened_at, memo)[1]` 那個**完整的 `FxInfo`**（pair、as_of、source、data_status、source_note、is_within_ttl、reason），不得縮減成 source id。
  - 查詢失敗時，`fx_open` 是 `data_status=UNAVAILABLE` 的 FxInfo，不是 None。只有 TWD 持倉、`opened_at is None`、KX-A2 短路這三種情形才是 None。
  - 測試：
    - yfinance 備援層的 fx_open 是 `DataStatus.BACKUP`（ladder 會重新標記，`fx.py:368-376`），這是 W5-T5 的前提。
    - 台銀是 FRESH。
    - 失敗時是 UNAVAILABLE，而且 `missing` 含 `fx_open`。
    - `/api/portfolio/summary` 的 JSON 含 `valuation.fx_open.data_status`。
- **R5-10d【R5-6 與 X-3c】**
  - PR-RK5a rebase 到 X-3c 之後；KX-A2 短路分支建構 `Valuation` 時**明寫 `fx_open=None`**（可 grep）。
  - X-3c 既有的 KX-A2 測試只准追加 `valuation.fx_open is None` 這一條斷言：A 型與 B 型列都要有；`missing == ["currency_market_mismatch"]` 與 provider 呼叫 0 次的斷言不變。
  - 不符列不得觸發 R5-4 的混源 WARNING，也不得進 `fx_disclosures`。
- **R5-11【W5-T1 常數位置】**
  - W-RK5-1 放在 `app/portfolio/summary.py` 的模組層（使用點就在 `fx_disclosures_for`），加風控核可註記。
  - 不得放進 `app/services/fx_notes.py`，也不得放進 `app/advice/*`（`app.portfolio` 不得 import advice，玩法手冊邊界）。
  - 測試：斷言這個常數不在 `SOURCE_NOTES.values()` 裡，而且對已知 id 與任一未知 id，`source_note()` 都不會回傳它。

#### 四、S-L3 查證

- **NaN：正式路徑到不了**（讀碼推定，要靠 F-1b 的 KF-6 pin 測試落實）。
  - 唯一的 `FxQuote` 產生點是 `services/fx.py:75, 95, 105`；`rate=float(latest.rate)`，而 `latest.rate` 是 `FxRate.rate: Decimal`（`fx.py:89`，只設了 `frozen`）。
  - pydantic 只在明確設定時才把 `allow_inf_nan` 傳進 core config（`_config.py:207`），Decimal schema 的預設是 False（`core_schema.py:759`）。
  - 台銀：`Decimal("NaN")` 不會丟 InvalidOperation，中價成為 NaN，但 `FxRate(...)` 會丟 ValidationError。sNaN 則在 `fx.py:291` 相加時丟 InvalidOperation。兩者都在 try 之外，例外穿出 `get_daily_rates`，被 ladder 的 `_safe_call`（`fx.py:399-409`）接住，改走備援（既有殘留 R3）。
  - Yahoo：JSON 的 `NaN` 經 parse_constant 變成 float nan，再變成 `Decimal('NaN')`，`PriceBar` 驗證失敗，在 `yfinance.py:355` 被接住、整列略過，結果是退用較早一天（既有殘留 R2，屬 F-2）。
  - 估值器用的是同一個 `FxRate`，同樣受這道驗證保護。
- **+inf：理論上可達**。要有 ≥ 約 1.8e308 的有限 Decimal（例如格子寫 `1E+400`）通過驗證，再經 `services/fx.py:107` 的 `float()` 溢位成 inf。之後 `inf <= 0.0` 為 False，走套用分支，印出「匯率 inf」。實務上不會出現，屬 R4（匯率沒有範圍檢查）。-inf 會被 `<= 0.0` 擋下。
- **若 NaN 被注入**（測試、`model_construct`，或日後 ADR-0015 快取讀取端繞過驗證）：
  - book 層：走套用分支後，`PortfolioContext.fx_to_twd`（`limits.py:791` 的 `gt=0`）會讓驗證失敗。`/api/advice` 與 `/limits` 回 500；警示由 `engine._load_isolated` 略過該標的這一輪。不會把錯誤的揭露送到使用者面前，但 PR-RK2 的混源 log 可能先記一行。
  - 估值器：NaN 市值會讓 `total_equity_twd` 的 `ge=0` 失敗，同樣回 500。
- **等級建議：low**（潛在問題；F-1b 本身是 medium，已涵蓋）。最小修法（不改碼，併入 F-1b）：
  1. KF-7 照原規劃，把 `book.py:1329` 改成 `fx.rate is None or not usable_rate(fx.rate)`。F-1b 任務單引用的行號 725-761 已經過時。
  2. **新增 KF-15**：`book.py:1287` 的 `fx.rate > 0.0` 同樣改經 `usable_rate`。不改的話，遇到 inf 時 `_resolve_fx` 判為不可用，`_log_unapplied_quote` 卻提早 return，2a 計數漏記；KF-9 的 regex 守門也可能轉紅。
  3. KF-6 的 pin 測試（`FxRate` 拒絕 NaN／Infinity）就是「到不了」的證據，F-1b 合併前這只是讀碼推定。
  4. ADR-0015 的交叉註記補一句：快取讀取端必須經驗證建構 `FxRate`，不得用 `model_construct`。
- PR-RK4a 會自動受益：(A′) 取自 `applied`，F-1b 之後 inf 報價會落入 2a 格（W-RK4-1 加估值器句）。

### 驗證

讀過的檔案（`/home/user/AICompany/` 之下；行號取自當下工作樹）：
- `work/reviews/2026-10-08-RK-4-RK-5-風控裁定附條件APPROVE與X-10核對.md`（全文）
- `work/reviews/2026-10-08-W-RK4-1-W-RK5-1逐字審與X-11-X-12核對-風控審查.md`（全文）
- `work/reviews/2026-10-08-tech-architect-RK-4-RK-5-缺漏型評估.md`（全文；完整檔名為 `…缺漏型揭露與fx_open來源評估.md`）
- `work/dispatch/2026-10-07-任務單-F-1b-匯率非正值的估值防護.md`（全文）
- `work/dispatch/2026-10-08-coordinator定案-下一步排序與X-3c開工.md`（全文）
- `work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md:236-265`，另 grep KX-A／A 型／B 型
- `apps/stock-desk/backend/` 之下：
  - `app/advice/book.py:280-469, 1000-1352`；grep `def`
  - `app/advice/book_limits.py:90-109, 230-242, 300-347, 370-579`
  - `app/advice/limits.py:70-99, 840-859`；grep `fx_to_twd`
  - `app/portfolio/valuation.py:160-511`
  - `app/services/fx.py`（全文）、`app/services/fx_notes.py`（全文）
  - `app/data/providers/fx.py:80-119, 177-226, 250-409`
  - `app/data/providers/fx_yfinance.py`（全文）
  - `app/data/providers/yfinance.py:290-399`
  - `app/data/price_guard.py`（全文）
  - `app/data/interface.py`（grep PriceBar）
  - `app/alerts/snapshot.py:85-172`、`app/alerts/engine.py:296-323`
  - `app/api/advice.py:165-234`、`app/api/portfolio.py:130-206`
  - `app/positions/models.py:114-134`
  - `.venv/.../pydantic/_internal/_config.py:180-209, 290`；`pydantic_core/core_schema.py`（grep `allow_inf_nan`）
  - `tests/test_rk2_fx_source_set_disclosure.py:1-110, 176-295, 468-807`
  - `tests/test_x3_fx_disclosure.py:150-330`
  - `tests/test_adr0022_sector_unvalued.py:850-877`
  - grep tests：`fx_disclosure is None`、`notes ==`、NaN
- `docs/adr/0015-stock-desk-匯率跨請求快取.md`（grep C-22／D-4／RK-5／origin_status；確認 tech-writer 已落了「提議」加註）

沒有做的事：
- 沒跑測試、沒跑 git、沒碰 DB、沒連網。
- 工作樹與 HEAD cf9619e 是否一致，沒有確認。
- 「既有測試零修改」都是讀碼推估。`test_pr0_cap4_atr_backfill.py`、`test_adr0023_w_a2_formal_path.py`、`test_api_portfolio_limits.py` 沒有逐行讀，要靠 dev-lead 附 grep 結果交 qa 核對。
- pydantic float `gt=0` 對 NaN 會判失敗，這是推定，沒有實測。

### 下一步

1. **risk-compliance-officer** 確認四點：
   - E4 的退路採 (α)；
   - G1／G2 跨組依 id 去重的解讀；
   - W4-T6 在 same-source 格的解讀；
   - R4-19 第 4 項（報價 note 為空的那一格，只存在於測試）的期望改寫。
2. **coordinator**：把 R4-10～R4-29、R5-10a～d、R5-11 轉錄進 RK-4、RK-5 任務單；把 KF-15 與 ADR-0015 交叉註記的增補轉錄進 F-1b 任務單。
3. **dev-lead**：X-3c → PR-RK5a（R5-10c、R5-10d）→ PR-RK4a（R4-10～R4-21）→ PR-RK4b（R4-22～R4-29，E4 要等風控回覆）。
4. **tech-writer**：ADR-0015 D-4、C-22 的加註依 R5-10a／b 改成可核對的寫法（仍屬待 CEO 核可的提議）。
5. **qa-reviewer**：逐條核對 R4-x、R5-x；用 `git diff` 確認零 diff 清單，以及 base 已含 X-3c。

相關檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book_limits.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/fx.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/fx.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_rk2_fx_source_set_disclosure.py
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-F-1b-匯率非正值的估值防護.md
- /home/user/AICompany/work/dispatch/2026-10-08-任務單-RK-4-匯率已換算卻無來源句的缺漏型揭露.md
- /home/user/AICompany/work/dispatch/2026-10-08-任務單-RK-5-fx_open來源未記錄與總覽匯率貢獻混源.md
- /home/user/AICompany/docs/adr/0015-stock-desk-匯率跨請求快取.md