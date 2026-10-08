# tech-architect 評估（2026-10-08，唯讀；coordinator 轉錄）：RK-2 估值器與 snapshot 匯率來源一致性

- 來源：風控 KX-10 S4 單項核對 RK-2（`work/reviews/2026-10-08-KX-10-S4-X3-R1-風控單項核對.md`）。
- **結論：同一次 `evaluate_alerts` 內兩邊確實可能拿到不同 `source`**（估值器以今天為迄日查、snapshot 以最後日線日為迄日再查一次，梯子無記憶）；影響第 1、2、3、5 條全部與第 4 條分母；長連假情境為確定性觸發（不需台銀時好時壞）；ADR-0015 接線後分歧會持續數小時。
- **建議採 (d) 來源集合揭露**：判斷只在 book 層套用分支內，揭露 ＝ 去重後的 [被套用報價 note, 同 pair 可用的估值器 `FxInfo.source_note`]；一致時逐位元組不變；否決 (a) 單獨、(b)、(c1)～(c4)。不需新 ADR；ADR-0015 加註並提議 C-24 前置條件「RK-2 (d) 已合併」（改動 accepted ADR 出貨閘門，**需 CEO 核可**）。
- 約束 R2-1～R2-9；觀察 O-2（缺漏型）、O-3、O-4 交風控判斷是否立項；時機：單獨開 PR-RK2，排在 X-3c 合併前、ADR-0015 W11-5 接線前。
- 升 medium 條件建議：台銀恢復、時好時壞、或 ADR-0015 W11-5 接線、或長連假，任一成立。

全文如下（標題層級各降一級）。

### 本次結論

1. **會，同一次 `evaluate_alerts` 裡兩邊確實可能拿到不同 `source`。風控 RK-2 的疑慮讀碼成立。**
   - 每個標的的 snapshot 都會先重建整本帳的估值：`snapshot.py:122` 呼叫 `build_summary`，估值器在這裡以 `(USDTWD, [今天-7, 今天])` 查一次梯子。
   - 接著 `snapshot.py:123` 再以 `(USDTWD, [最後日線日-7, 最後日線日])` 查第二次。
   - 兩次之間隔著整本帳的即時取價。`FxRateLadder.get_daily_rates`（`fx.py:356-376`）每次都從台銀開始重試，沒有記憶，也沒有固定用哪一層。共用同一個 provider 物件是必要條件，但不足以保證來源相同。
   - 另外有一個**不需要台銀時好時壞也會發生**的情境：台灣長連假。兩個查詢區間迄日相差約一天，一個區間涵蓋到台銀最後（或第一個）營業日、另一個沒涵蓋，就會一邊落台銀、一邊落備援。
2. **影響範圍比 RK-2 描述的再大一點：第 1、2、3、5 條**的數字全部來自估值器的匯率。只有第 4 條的分子（ATR × 匯率）用 snapshot 的報價，而它的分母（總資產）仍來自估值器，所以第 4 條本身就混用兩次查詢的結果。
3. **建議採 (d)「來源集合揭露」**，可以看成 (a) 和 (b) 的合併版：
   - 判斷只放在 book 層，snapshot 和 engine 都不改。
   - 只在已套用報價時才附揭露句（維持 X3-R1 的「若且唯若」條件）。
   - 揭露的是「被套用報價的來源」加上「同一本帳同幣別對估值實際用的來源」，去重。
   - 兩邊一致時輸出逐位元組不變；不一致時兩句都附。
   - 否決 (a) 單獨使用、(c) 和反向傳遞報價，理由在下面方案比較。
4. **不需要新 ADR。** 需要做的是：
   - 在 X-3 任務單加一段補段，修訂 KX-10 的「精確條件」。
   - 在 ADR-0015 加註：它的快取以查詢區間為 key，不能保證兩條路徑讀到同一個匯率，而且會把這個分歧從瞬間競態變成持續數小時。另外把 RK-2 修正列為 W11-5 接線的前置條件，這一點涉及已 accepted ADR 的出貨閘門，需要 CEO 核可。
5. **時機**：建議在原本兩個條件（X-3c 合併前、台銀主源恢復時，先到者為準）之外，**加上「ADR-0015 W11-5 接線前」**。另外「台銀恢復」在產品內沒有任何自動訊號（ADR-0011 條件 (3) 只靠人工跑 `verify_market_data.py`），這個條件實際上觀察不到，所以建議直接排在 X-3c 之前，單獨開一個小 PR。
6. **等級**：同意現況是 low（兩邊都落 yfinance_fx）。台銀恢復、時好時壞、遇到長連假，或 ADR-0015 接線，任一成立就升 medium。

### 各部門回報（tech-architect）

#### 評估摘要

- **採用 (d) 來源集合揭露**：判斷在 `build_book_context` 內進行，資料只讀已傳進來的 `summary.positions[].valuation.fx`，不新增模組相依。決策卡路徑也會一併修正：`api/advice.py:166,184` 有同樣的「先估值、再另查報價」結構。
- **否決**：(a) 單獨使用、(b) 不加判斷就一律附兩句、(c) 請求範圍快取或固定只用一個來源、反向把估值器的 fx_now 當報價。理由見方案比較。
- **兩點交風控判讀**：
  - 不一致時兩句並陳，要不要加一句銜接句（那會是新字面，需要逐字審）。
  - 以下 O-2、O-3 兩種「缺漏型」要不要另開項目。

#### 讀碼確認：兩邊的路徑與時序

警示 tick 裡，每個 `(symbol, market)` 只載一次 snapshot（`engine.py:383-396`）。每個 snapshot 的步驟如下：

1. 載入日線（`snapshot.py:103-109`）。
2. `build_summary(store, valuator)`（`snapshot.py:122` → `summary.py:139` `value_all`）：
   - 每一輪新建一份 `fx_memo`（`valuation.py:312`），範圍只在這一輪估值內。
   - 每個持倉依序：即時取價（`:335`，scheduler 用的是 live valuator，`deps.py:164-168, 293-295`）→ fx_now（`:453`，區間 `[today-7, today]`，today 是 UTC 日期，`:321`）→ fx_open（`:461`，建倉日的區間）。
   - 同一輪內，同一個 `(pair, today)` 只查一次。所以**同一份 summary 裡所有 USD 持倉的 fx_now 來源相同**。
   - `FxInfo` 只記錄 fx_now 的來源（`:453`）；fx_open 只取 `[0]`，來源被丟掉（`:461`）。
3. `resolve_fx_quote(..., on=latest.date)`（`snapshot.py:123` → `services/fx.py:84`），區間是 `[最後日線日-7, 最後日線日]`。
4. `build_book_context`：`fx_disclosure` 只取自被套用的報價（`book.py:1133-1141, 1223-1233`）。
5. fired 訊息只要 `fx_disclosure` 有值就附上（`engine.py:316-317`），**不管違反的是哪一條上限**。

各條上限用的匯率：

| 上限 | 用到的數字 | 匯率來自 | 讀碼位置 |
|---|---|---|---|
| 第 1 條 | `position_market_value_twd / total_equity_twd` | 估值器 fx_now | `limits.py:830-836` |
| 第 2 條 | `sector_market_value_twd / total_equity_twd` | 估值器 fx_now | `limits.py:1162` |
| 第 3 條 | `gross_exposure_twd`（等於 equity） | 估值器 fx_now | `limits.py:1251`；`book.py:1152` |
| 第 4 條 | 分子 `atr * fx_to_twd`（報價）；分母 equity | 報價 ＋ 估值器 | `limits.py:1279-1282` |
| 第 5 條 | `position_weight` | 估值器 fx_now | `limits.py:1418` |

- fx_open 只進 `position_cost_twd`，只被 `unrealized_pnl_pct` 讀到（`limits.py:838-844`），而這個欄位已排除在 `ALERT_RULE_FIELDS` 外（`context.py:73-77`）。所以 **fx_open 的來源跟警示無關**。
- 一次 tick 有 K 個標的，就至少有 2K 次彼此獨立的梯子判斷：每個 snapshot 都重建 summary，各自一份 memo。

#### 給風控直接判讀：情境 → 是否可能來源不同 → 使用者看到什麼

| # | 情境 | 估值器 fx_now（第 1、2、3、5 條；第 4 條分母） | snapshot 報價（第 4 條分子；揭露句） | 來源不同？ | 使用者現在看到的 fired 訊息 | 屬 X3-F8 嗎 | 採 (d) 後 |
|---|---|---|---|---|---|---|---|
| 1 | 台銀持續回挑戰頁（現況），yfinance 正常 | yfinance_fx | yfinance_fx | 否 | yfinance 句，數字也是 yfinance：正確 | 否 | 不變 |
| 2a | 現況，**只有報價**那次 yfinance 失敗 | yfinance_fx | UNAVAILABLE | 不算「不同」 | 第 1、2、3、5 條仍可能 fired，數字用了 yfinance，但**沒有任何來源句**；第 4 條 not_evaluable | 否，屬**缺漏型**，見 O-2 | 不變（受「已套用」條件限制），交風控判斷 |
| 2b | 現況，**只有估值器**那次 yfinance 失敗 | UNAVAILABLE（該持倉未估值） | yfinance_fx | 不算 | yfinance 句；第 1 條附 W-a2 等未估值說明：正確 | 否 | 不變 |
| 3 | 台銀恢復且穩定，不在長假 | bank_of_taiwan | bank_of_taiwan | 否 | 台銀句：正確 | 否 | 不變 |
| 4a | 台銀時好時壞：估值器那次成功、報價那次失敗 | bank_of_taiwan | yfinance_fx | **是** | 附 yfinance 句（含「為本次台灣銀行來源不可用時的備援」），但第 1、2、3、5 條其實是台銀數字；第 4 條混用兩個來源 | **是**（往「較不官方」方向錯，但「台銀不可用」一句為假） | 兩句都附 |
| 4b | 台銀時好時壞：估值器那次失敗、報價那次成功 | yfinance_fx | bank_of_taiwan | **是** | 附**台銀方法論句**，但第 1、2、3、5 條是 yfinance 數字 | **是**（風控所指的危險方向：看起來像官方匯率） | 兩句都附 |
| 5 | 台銀恢復，但遇到台灣長連假的開頭或收尾（連續 ≥ 8 個日曆日沒有台銀牌告；哪些年份的連假會這麼長未查證） | 區間 `[今天-7, 今天]` | 區間 `[最後美股日線日-7, 最後美股日線日]`，迄日約早一天 | **是，而且是確定性的，不需要台銀時好時壞** | 一個區間碰到台銀營業日、另一個沒碰到（台銀那一層沒有任何匯率就落備援，`fx.py:215-222, 359`），方向可能是 4a 或 4b | **是** | 兩句都附 |
| 6 | ADR-0015 快取接線後（目前尚未實作：`app/data/fx_*.py` 不存在） | 今天的區間：暫定值，每 30 分鐘重查 | 前一天的區間：已結算；backup 24 小時重驗、fresh 永久 | **是，而且會持續數小時到一整天** | 台銀剛恢復時：4a 型最長持續 24 小時。台銀恢復後又被擋：報價那邊是永久有效的台銀 fresh 已結算值，估值器那邊每 30 分鐘落 yfinance，形成 **4b 型，整天持續** | **是** | 兩句都附 |
| 7 | 同一個 tick、不同標的 | 每個標的各重建一次 summary | 每個標的各查一次 | 標的之間可能不同 | A 標的訊息附台銀句、B 標的附 yfinance 句 | 每則訊息各自依 4a、4b 判斷 | 每則訊息各自自洽 |
| 8 | fx_open 與 fx_now 來源不同（例如建倉日太久遠，超出台銀可查範圍，未查證） | — | — | 只影響成本 | 不進任何上限，也不進警示欄位 | 否 | 不適用；另列 O-4 |

**風控判讀要點**：
- 現況符合情境 1、2，沒有來源錯標，只有 2a 的缺漏。
- 4b、5、6 是 X3-F8 的觸發型態。其中 5 和 6 **不靠台銀時好時壞**，只要台銀恢復（5）或 ADR-0015 接線（6）就會發生。所以我建議把升 medium 的條件寫成：「台銀恢復、時好時壞、或 ADR-0015 W11-5 接線，任一成立」。

#### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (a) 揭露改取該持倉估值的 `FxInfo.source_note` | 對第 1、2、3、5 條是正確來源；book 層已經拿到 summary，不新增相依 | 第 4 條分子用的報價來源會被藏起來；**候選標的**（沒有持倉，因此沒有 FxInfo）和「持倉未估值但報價有套用」這兩格會從「有揭露」退化成「沒有揭露」；`test_api_advice.py:547-559` 的語意會被破壞 | 中：會製造新的缺漏型。單獨使用否決 |
| (b) 兩邊不同時兩句都附（只在 snapshot 做） | 不藏任何來源 | 如果放在 snapshot，就違反 KX-10「snapshot 只讀不判斷」；決策卡也有同樣問題，還得再複製一份；兩句並陳可能需要銜接字面 | 中：判斷又分散到兩處，正是 KX-10 修掉的成因 |
| (c1) 請求範圍的快取或 memo | 直覺 | 兩個查詢的**區間不同**（迄日一個是今天、一個是日線日），以 key 去重根本對不上；以 pair 去重又會回傳錯誤日期 | 高：沒有效果，或答錯 |
| (c2) 同一次檢查內鎖定同一層來源 | 根治時好時壞的情境 | 梯子或包裝層必須知道有哪幾層，違反 ADR-0015 C-1／C-3 的精神；估值器是 `lru_cache` 單例、建構時就綁定 provider，要做到每個 tick 注入，就得改 `PositionValuator` 的 API（屬 ADR-0010 範圍）；**對情境 5 無效**（鎖在台銀，但台銀在該區間根本沒有資料） | 高：改動大，而且解不完 |
| (c3) 把 book 層的報價傳給估值器 | 來源一致 | 警示路徑的市值會和 `/api/portfolio/summary` 不同，跨入口不一致；只蓋得到 fx_now；要改估值器 API | 高，否決 |
| (c4) 反向：book 用估值器的 fx_now 當報價，刪掉第二次查詢 | 根因修正，同一張帳單只查一次 | `FxInfo` 沒有存匯率數值，要改 `valuation.py` 和 summary API 的 payload（前端契約）；第 4 條改成用今天的匯率，`FX_APPLIED_NOTE` 的匯率日期在一致帳本上也會變，違反逐位元組不變，也違反 `api/advice.py:181-182` 的刻意設計；候選標的仍要另外查 | 中高：列為長期選項，不在 RK-2 處理 |
| **(d) 來源集合揭露（採用）**：book 層在套用分支內，揭露 = 去重並保持順序的 [被套用報價的 note, 同 pair 且可用的估值器 FxInfo note] | 判斷只有一處（延續 S4）；snapshot、engine、估值器、services 都不改；決策卡一起修好；一致時輸出逐位元組不變；X-3c 的不符分支、A 型、混雜幣別自然都是 None；符合 ADR-0005 D-5「跨來源不得靜默拼接，混源須明示」的精神 | 不一致時讀者看到兩句，但分不出哪個數字用哪個來源；yfinance 句裡「本次台灣銀行來源不可用」在 4a 情境下只對其中一次查詢成立 | 低：剩下的歧義交風控判斷要不要加銜接句 |

#### 決策（不出新 ADR；加註草案）

- **Context**：RK-2 讀碼確認。共用 provider 物件（`deps.py:141-160`，其 docstring 寫「Both paths must read the same rates」）只是必要條件。兩個查詢區間迄日不同，梯子又沒有記憶，所以來源可能不同（情境 4、5、6）。
- **Decision**：採 (d)。修訂 KX-10「精確條件」第二點（任務單 L620）：揭露字串 ＝ 被套用報價的 `source_note`，再加上同一份 summary 中、與該報價同 pair、`data_status != UNAVAILABLE`、note 不為空的估值器 `FxInfo.source_note`，依此順序去重。出現與否的條件（只在套用分支）不變。
- **Consequences**：
  - 好處：一致時零變化；fired 訊息與決策卡不再只標其中一個來源；同一處修正同時涵蓋兩個入口。
  - 壞處：不一致時會出現兩句看似矛盾的方法論句，可能需要新字面；「哪一條上限用了哪個來源」仍沒有逐條標示；O-2、O-3 的缺漏型沒有處理。
- **ADR-0015 加註草案（交 tech-writer）**：
  - 附錄最後一列，以及 D-8 關於「包在同一處才能維持兩條路徑讀到同一個匯率」的說法，加註：快取以查詢區間為 key，估值器（迄日今天）和報價（迄日日線日）是不同 key，**不保證**讀到同一個來源；接線後分歧會因已結算、暫定兩種 TTL 不同而持續數小時（見 RK-2 評估情境 6）。
  - 提議在 C-24 加一條前置條件：「RK-2 的 (d) 已合併」。這會改動 accepted ADR 的出貨閘門，**需要 CEO 核可**。
- ADR-0011（proposed）不需要改。ADR-0005 F-4、D-5 由 (d) 強化，沒有衝突。

#### 對實作的約束（逐條可由 qa 檢查）

- **R2-1**：判斷只放在 `app/advice/book.py` 的 `build_book_context`。`alerts/snapshot.py`、`alerts/engine.py`、`api/advice.py`、`portfolio/valuation.py`、`portfolio/summary.py`、`services/fx.py`、`services/fx_notes.py`、`data/providers/*`、前端全部**零 diff**（`deps.py` 只允許修正 docstring 的不實陳述）。`snapshot.py` 仍不得出現 `source_note` 識別字。
- **R2-2**：`book.py` 不得新增 import `app.data.providers.*`（ADR-0005 F-1）。資料只讀 `summary.positions[].valuation.fx`。
- **R2-3**：`applied is None` 時，揭露一律為 None（TWD、混雜、四種失敗分支，以及 X-3c 的不符分支）。X3-R1 的「若且唯若」條件不變。
- **R2-4**：集合規則是 `[applied.source_note] + [p.valuation.fx.source_note for p in summary.positions if fx 不為 None and fx.pair == applied.pair and fx.data_status 不是 UNAVAILABLE and note 不為空]`，依此順序去重。`BookContext.fx_disclosure` 維持 `str | None`，多句時以單一空白串接，讓 snapshot 和 engine 零 diff。`book_notes` 裡則逐句分開 append，位置仍緊接在 `fx_note` 之後。
- **R2-5**：一致帳本逐位元組不變。既有測試的斷言零修改，包括 T10-1～T10-4、`test_alerts_snapshot.py:228-230, 298`、`test_api_advice.py:547-559`、`test_advice_book.py:458`。這是讀碼推估：既有 harness 的估值器和報價共用同一個 provider 類別（`conftest.py:126-150`、`api_helpers.py:184-203`、`test_alerts_snapshot.py:117-121`），或估值器用的是 `UnavailableFxProvider`，會被排除。
- **R2-6**：新增測試。
  - 用「第 N 次呼叫翻轉來源」的假梯子，兩種順序（4a、4b）各一組，同時涵蓋警示 snapshot（含 `evaluate_alerts` fired 訊息）和決策卡 `context_notes`，斷言兩句都在而且順序固定。
  - 情境 5 的確定性測試：假梯子的主源只對某個日期以前有資料，用來證明不需要時好時壞也會觸發。
  - 「估值器 UNAVAILABLE ＋ 報價套用」只出現一句。
  - 一致時恰好一句。
  - 先紅後綠：4b 那組在 base 上一定紅。
- **R2-7**：不一致時是否加銜接句，等風控裁定後才定案。如果需要新字面：由 creative-lead 起草，風控逐字核可，以常數加守門測試釘住；核可前不得出貨不一致時的呈現方式。
- **R2-8（建議，非必要）**：偵測到不一致時記一行英文 WARNING，只含 pair 和兩個 source id，不含金額、數量、symbol 以外的持倉資訊。目的是讓「台銀恢復」這個觸發條件變得觀察得到。不得因為記 log 而在 snapshot 重複判斷；記 log 的位置由 dev-lead 決定。
- **R2-9**：單獨開一個 PR。X-3c 合併前先合，因為兩者都動 `book.py:1120-1141`，X-3c 再 rebase。X-3c 的 KX-A11、`price_withheld_note` 和本 PR 正交：不符分支短路後 `applied` 為 None；KX-A2 讓不符列的 `FxInfo` 為 None，自然排除。T10 和 KX-P1 的口徑不受影響。

#### 觀察（範圍之外，交風控判斷是否另立項）

- **O-2（缺漏型）**：情境 2a。估值器的匯率已經用在第 1、2、3、5 條，但報價失敗，所以 fired 訊息沒有任何來源句。這和 ADR-0011 條件 (1)「不得只在部分端點出現」、ADR-0005 F-4 有張力。補上它需要修改 X3-R1 的「若且唯若」條件，所以不併入 RK-2。
- **O-3**：TWD 標的的第 1、3 條分母（總資產）含有其他 USD 持倉經匯率換算的金額，但訊息不附來源句。這是 X3-R1 當初依「此 context 是否套用報價」劃定範圍的既有結果，這裡只提出，不建議擅自擴張。
- **O-4**：`FxInfo` 和 `summary.fx_disclosures` 不記錄 fx_open 的來源，總覽的成本和損益可能用了未揭露的來源。這不影響警示。

### 驗證

**實際讀過的檔案與行號**（全部在 `/home/user/AICompany/apps/stock-desk/backend/` 之下，除非另外標明）：
- `app/alerts/snapshot.py:1-172`（全文）
- `app/alerts/engine.py:60-119, 280-429`
- `app/data/providers/fx.py:1-410`（全文）
- `app/data/providers/fx_yfinance.py:1-136`（全文）
- `app/services/fx.py:1-113`（全文）
- `app/services/fx_notes.py:1-63`（全文）
- `app/portfolio/valuation.py:1-511`（全文）
- `app/portfolio/summary.py:85-184`
- `app/advice/book.py:300-539, 1060-1234`
- `app/advice/limits.py:70-99, 830-874`（`position_weight`／`held_shares`）、`994-1017, 1147-1303, 1409-1483`
- `app/advice/context.py`：grep `ALERT_RULE_FIELDS` 前後，L15-21、54-77、161-166
- `app/api/deps.py:130-189, 293-306`
- `app/api/advice.py:160-252`
- `app/api/alerts.py:200-253`
- `app/scheduler.py:370-415`
- `tests/conftest.py:95-160`、`tests/api_helpers.py`（grep L21, 172-203）、`tests/test_alerts_snapshot.py`（grep `fx_disclosure`／`PositionValuator`／`fx_provider`）、`tests/test_api_advice.py:530-560`、`tests/test_pr0_cap4_atr_backfill.py:255-292`
- `/home/user/AICompany/docs/adr/0015-stock-desk-匯率跨請求快取.md`（全文）、`/home/user/AICompany/docs/adr/0011-stock-desk-匯率來源梯子與台銀挑戰頁降級.md`（全文）、`/home/user/AICompany/docs/adr/0005-stock-desk-指數來源與美股額度管理.md:270-299`
- `/home/user/AICompany/work/reviews/2026-10-08-KX-10-S4-X3-R1-風控單項核對.md`（全文）
- `/home/user/AICompany/work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md:600-709`，另 grep `X3-F8`／`KX-A`／`price_withheld_note`／`X-3c`

**grep 結果**：
- `app/` 內 `CachedFxRateProvider` 零命中，`app/data/fx_*.py` 不存在，所以 ADR-0015 尚未接線。
- `fx_disclosures` 只出現在 `summary.py`，book 層從未讀取。
- 對 `get_fx_provider` 的 dependency override 共 6 處，都和估值器同一個類別，或估值器是 Unavailable。

**沒有做的**：
- 沒跑測試、沒跑 git（工作樹的 staged 狀態以 caller 描述為準，行號依目前工作樹）、沒碰 DB、沒連網。

**讀碼推定、未實測**：
- 台銀在連假期間的回應（非 200 或空 CSV），以及 yfinance 在台灣連假時是否有 `TWD=X` 的值。
- 情境 4 的實際發生機率。
- R2-5 的「既有測試零修改」。

### 下一步

1. **risk-compliance-officer**：依上表重審 X3-F8，並裁定三點：
   - (i) 升 medium 的條件是否加入「ADR-0015 W11-5 接線」與「長連假」。
   - (ii) 不一致時兩句並陳，是否需要銜接句（新字面）。
   - (iii) O-2、O-3、O-4 要不要另外立項。
2. **CEO**：核可在 ADR-0015 C-24 加入「RK-2 (d) 已合併」這條前置條件。
3. **tech-writer**：風控裁定後，在 X-3 任務單補 KX-10 精確條件修訂段（R2-1～R2-9）；CEO 核可後再落 ADR-0015 加註。
4. **dev-lead**：風控裁定後，從 `product/stock-desk` 單獨開 PR-RK2，排在 X-3c 合併前，依 R2-1～R2-9 實作。
5. **creative-lead**：只有在風控裁定需要銜接句時才起草。
6. **qa-reviewer**：PR-RK2 依 R2-1～R2-9 逐條核對，零 diff 清單用 `git diff` 確認。
7. **devops-sre／CEO**：定期跑 `scripts/verify_market_data.py` 追蹤台銀是否恢復（ADR-0011 條件 (3)）。在 R2-8 的 log 落地之前，這是「台銀恢復」這個觸發條件唯一的觀察來源。

相關檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/summary.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/fx.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/fx.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/advice.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/deps.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/engine.py
- /home/user/AICompany/docs/adr/0015-stock-desk-匯率跨請求快取.md
- /home/user/AICompany/docs/adr/0011-stock-desk-匯率來源梯子與台銀挑戰頁降級.md
- /home/user/AICompany/work/reviews/2026-10-08-KX-10-S4-X3-R1-風控單項核對.md
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md