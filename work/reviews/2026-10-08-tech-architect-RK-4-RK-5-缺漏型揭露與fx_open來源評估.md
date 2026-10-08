# tech-architect 評估（2026-10-08，唯讀；coordinator 轉錄）：RK-4 缺漏型揭露、RK-5 fx_open 來源與總覽混源

- **RK-4**：採 (ii-a)「本標的持倉經換算即附句」（X3-R1 閘門加 (B)：對應持倉至少一筆 ok 且 fx_now 乘進市值），補 O-2（2a）、新發現 2c（決策卡無收盤價仍用估值器匯率）與混雜格；O-3 採 (i) CEO 知悉＋總覽揭露；**`/limits` 查證：完全沒有任何匯率句**，採 (L-ii) 彙整各標的揭露附進 notes；需新字面 W-RK4-1（歸屬句，是否需要由風控定）；改寫 X3-R1、推翻 K-1 混雜不附句——**需風控重新裁定**；R4-1～R4-9；排在 PR-RK2 合併後（PR-RK4a book 層、PR-RK4b `/limits`）。
- **RK-5**：採 (a) `Valuation.fx_open: FxInfo | None`（`FxInfo` 零 diff）、`fx_disclosures_for` 只算 ok 持倉（修 O-5）、混源記 WARNING；聯集與銜接句 W-RK5-1 另開 PR；不併入 ADR-0015 D-8 但形狀對齊；R5-1～R5-10；PR-RK5a 現在可開（無新字面、與 PR-RK2 無檔案交集）、PR-RK5b／5c 於 W11-5 前；建議 C-24 再加 RK-5 前置條件（需 CEO 核可）。
- **新發現 N-1～N-3（W11-5 前必處理）**：首頁「備援匯率」徽章（`page.tsx:62-64`）同 O-5 破口且不看 fx_open；ADR-0015 接線後徽章只比對 `=== "backup"` 在快取命中時會消失（危險方向，C-22 未涵蓋）；ADR-0015 D-4 未寫明快取命中／舊值退回時 `FxRateResult.source` 的值。
- **事實更正（影響 X-10）**：總覽匯率揭露在「詳細說明與依據」`<details>` 內非常駐（`SummaryCards.tsx:45-50, 124-133`）；`/limits` notes 亦在 `<details>` 內。
- coordinator 定案（CEO 可推翻）：RK-4／RK-5 皆 low，dev 工作待風控裁定與 CEO 排序後再開，PR-RK5a 不搶在 PR-RK2／X-3c 之前。

全文如下（標題層級各降一級）。

### 本次結論

**RK-4（缺漏型揭露）**
- **建議採 (ii-a)「本標的持倉經換算即附句」。** 揭露條件從「已套用報價」放寬為「已套用報價，**或**本 context 對應的持倉中至少一筆估值為 ok 且 fx_now 實際乘進市值」。這樣可以補上 O-2（2a），也一併補上決策卡無收盤價（2c）與混雜幣別兩格。
- **O-3（TWD 標的的分母）採 (i)**：CEO 知悉加總覽揭露。不採 (ii-b)「整本帳任一外幣持倉就附句」，理由有兩個：
  - 它會讓每則 TWD 警示都帶上長句（`test_alerts_snapshot.py:236-237` 的設計理由是「每則都附會讓讀者學會跳過」）。
  - 帳上同時有一致的 USD 持倉時，A 型卡會出現匯率方法論句，旁邊卻是以 1.0 換算的自身數字。這正是 X3-R1 當初要移除的不實揭露，危險方向又回來了。
- **`/limits` 查證結果：完全沒有任何匯率句，連 `FX_APPLIED_NOTE` 也沒有。**
  - `/limits` 的 notes 只來自整本帳層級的 context（`book_limits.py:397-401` → `book.py:858` 只有總資產基礎句、總曝險句、未估值句）。
  - 各標的的 context 只取 `.context`（`book_limits.py:496-506`），揭露被丟掉。
  - 第 1、2、3、5 條用估值器匯率，第 4 條用逐檔報價（`api/portfolio.py:177`），兩者都沒有來源句。
  - 建議 (L-ii)：把各標的 book 層的判斷結果彙整後附進 `/limits` notes。
- 這會修改 X3-R1 的「若且唯若」，**需要風控依 2026-09-19 標準重新裁定**。另外，貼在 2a／2c／混雜格的來源句旁邊，現有的 `FX_UNAVAILABLE_NOTE`／`NO_FX_QUOTE_NOTE`／`MIXED_CURRENCY_NOTE` 會跟它看起來矛盾，**我判斷需要一句歸屬句（新字面 W-RK4-1）**，是否需要由風控定。
- 不需要新 ADR；PR-RK2 內不動（R2-3 照舊）；排在 PR-RK2 合併之後。

**RK-5（fx_open 來源、總覽混源）**
- **最小方案**：`Valuation` 新增一個與 `fx` 並列的 `fx_open: FxInfo | None`，**不改 `FxInfo` 本身**。`fx_disclosures_for` 只算估值為 ok 的持倉（修 O-5）。混源時記一行英文 WARNING。
- 混源時需要「明示」（ADR-0005 D-5），需要一句新銜接字面 W-RK5-1。這句另開 PR，核可前不得出貨聯集。
- **不併入 ADR-0015 D-8 的工作**：該工作卡在 W-1～W-8 等多項風控閘門，併進去會讓 RK-5 無限期延後。改成在 W11-5 之前獨立落地，並讓資料形狀與 D-8 對齊：fx_open 也由同一個 `_lookup_fx` 產生，D-8 的 `origin_status`／`is_within_ttl` 會自動帶上。
- **新發現 3 點，都必須在 W11-5 前處理：**
  - N-1：首頁「備援匯率」徽章（`page.tsx:62-64`）和 O-5 是同一種破口，而且不看 fx_open。
  - N-2：ADR-0015 接線後，這個徽章只比對 `=== "backup"`，在快取命中（`cached_stale` 加 origin backup）時會**消失**。這是危險方向，C-22 沒有涵蓋。
  - N-3：ADR-0015 D-4 沒有寫明快取命中或舊值退回時 `FxRateResult.source` 的值。這會讓 RK-2 (d) 與 RK-5 的來源比對失準。

### 各部門回報（tech-architect）

#### 讀碼事實（兩案共用）
- 所有可能乘進數字的匯率只有一種：Currency 只有 TWD／USD（`positions/models.py:34`），所以只有 USDTWD。
- 同一輪 `value_all` 的 memo 以 `(pair, target)` 為 key（`valuation.py:480-485`）。所以同一份 summary 內所有 USD 持倉的 fx_now 來源相同；fx_open 依建倉日不同，來源可以各自不同。
- `FxInfo` 只記錄 fx_now（`valuation.py:453`）；fx_open 只取 `[0]`（`:461`），來源被丟掉。
- 拆解公式（`valuation.py:149-151`）：
  - 匯率貢獻 ＝ q·p0·(fx_now − fx_open)，兩個來源的口徑差會全部落在這一項。
  - 成本 `cost_twd` 只用 fx_open（`:388`），未實現損益也混用兩者。
- 2a 的 fired 訊息只帶違反條的 details 加 `fx_disclosure`（`engine.py:309-317`），`FX_UNAVAILABLE_NOTE` 只進 `reason`（skip 路徑），所以推播裡**完全沒有任何匯率句**。
- 決策卡無可用收盤價時（`api/advice.py:183-187, 206-226`），fx 為 None，所以卡上出現 `NO_FX_QUOTE_NOTE`「本次沒有取得任何匯率報價」，但第 1 條的市值其實已用估值器匯率換算。我把這格記為 **2c**，是 O-2 的同型。
- **總覽的匯率揭露不是常駐顯示**：CEO 2026-09-19 第二次裁定已把它收進「詳細說明與依據」的 `<details>` 裡（`SummaryCards.tsx:45-50, 124-133`）。`/limits` 的 notes 也在 `<details>` 內（`RiskGauge.tsx:203-236`），兩者在同一頁（`page.tsx:55-83`）。X-10 的「請以總覽的揭露為準」應改成「總覽匯率貢獻卡的詳細說明」。

---

#### RK-4

#### 評估摘要
- 採用 (ii-a)；O-3 採 (i)；`/limits` 採 (L-ii)。
- 否決 (ii-b)、(iii-a) 指引句、(iii-b) 根治方案（列長期）。

#### 方案比較
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (i) 維持現狀，加 CEO 知悉與總覽揭露 | 零改碼 | 2a／2c 推播與卡上的換算數字沒有任何來源句，違反 ADR-0011 條件 (1)「不得只在部分端點出現」；總覽揭露已摺疊進 `<details>`，而且來自另一次 `build_summary`，來源可能不同 | 低，但缺漏持續存在。**只建議用在 O-3** |
| **(ii-a) 本標的持倉經換算即附句（採用，用於 O-2／2c／混雜）** | 延續 S4 與 (d)：判斷只在 `build_book_context`，snapshot、engine 零 diff；只改閘門，內容沿用 R2-4 加 RK2-R1 的集合；A 型持倉的 FxInfo 為 None（`valuation.py:448-451`），自然不附；不會造成 TWD 警示的雜訊 | 改變 K-1 對混雜幣別的裁定（USD 那批 ok 時會附句）；與相鄰的失敗句看起來矛盾，需要歸屬句（新字面） | 低 |
| (ii-b) 整本帳任一 ok 外幣持倉就附句（O-2 加 O-3） | 最符合「本則數字經任何匯率換算」的字面 | 所有 TWD 標的警示與卡都會附長句；**帳上另有 USD 持倉時，A 型卡會出現方法論句**，危險方向回來；要避免就得在 book 層再複製一份 TWD 判斷（KX-10 的 S5，已否決） | 中高，否決 |
| (iii-a) 固定短句指向總覽（例：「部分金額經匯率換算，來源說明見總覽」） | 推播短 | 新字面；指向的是摺疊區，而且是另一次請求的結果；不含 ADR-0005 F-4 要求的未查證聲明 | 中，否決 |
| (iii-b) 根治：同一張帳單只查一次匯率（風控 S-2，book 層直接用估值器的 fx_now） | 2a 在結構上消失 | 要改 `FxInfo`／summary 的 payload，第 4 條的匯率日期語意與 `FX_APPLIED_NOTE` 字面會變（`api/advice.py:181-182` 的設計是刻意的） | 中高，列入 ADR-0015 落地後重評 |
| (L-ii) `/limits`：彙整各標的 book 層的揭露句，附進 `report.notes` | 判斷沿用 book 層，不另寫條件；涵蓋第 4 條的報價來源（總覽揭露沒有這一項）；前端零 diff（notes 原樣渲染） | `book_limits.py` 要改 `_symbol_context` 的回傳；同一頁可能和總覽揭露重複 | 低 |

#### 決策草案（不出新 ADR；給風控重新裁定的條件文字）
- **Context**：X3-R1 以「已套用報價」為閘門，留下 2a、2c、混雜、`/limits` 四格缺漏。RK2-R1 把精神具體化為「每一句方法論句都對應實際乘進數字的來源」，這是單向的，不要求反方向。
- **Decision（給 X3-R1 的新條件草案）**：
  - 方法論句出現在決策卡 `context_notes` 與警示 `fx_disclosure`，**若且唯若**下列任一成立：
    - (A) `_resolve_fx` 走套用分支，且該報價的 `source_note` 不為空；或
    - (B) 本 context 對應的持倉中，至少一筆 `valuation.status == "ok"`，且 `valuation.fx` 不為 None、`data_status` 不是 UNAVAILABLE、`source_note` 不為空。
  - 內容 ＝ 依序去重：先放 (A) 成立時的 `applied.source_note`，再放 summary 中所有 ok、同 pair、非 UNAVAILABLE、note 不為空的 `fx.source_note`。
  - 反方向的保證範圍：**本標的持倉市值或被套用的報價**經匯率換算時，一定有來源句。**總資產分母中其他持倉的換算（O-3）不在保證範圍內**，由總覽揭露加 CEO 知悉承擔。
- **Consequences**：
  - 好處：2a、2c、混雜三格都有來源句；判斷仍只在一處。
  - 壞處：
    - 需要新字面 W-RK4-1，並列入 ADR-0015 W-4 重審範圍。
    - TWD 卡的分母仍未揭露來源。
    - K-1 的「混雜幣別不附句」被推翻。
    - 哪一個數字用哪一個來源，仍然沒有逐條標示。

#### 對各項既有決策的影響
| 項目 | 影響 |
|---|---|
| X3-R1「若且唯若」 | **改寫**（加入 (B)），風控重新裁定 |
| KX-10 S4 | 精神保留：單一判斷點、snapshot 只讀；精確條件第 2 次修訂由 tech-writer 補段 |
| PR-RK2 (d)、R2-3 | PR-RK2 內不動；PR-RK4 合併後 R2-3 由新條件取代；R2-4 的集合規則與 RK2-R1 的 ok 篩選原樣沿用 |
| RK2-R2 銜接句 | 不受影響；W-RK4-1 是另一句（2a 只用到一個來源，RK2-R2 的「兩個不同來源」不成立，不能沿用） |
| X-3c／KX-A2 | 不符列的 `FxInfo` 為 None 且狀態為 insufficient，(B) 自然不成立；KX-A11 短路後 (A) 也不成立，相容 |
| ADR-0005 F-4 | 強化（多三格常駐）；D-5 不受影響（(B) 只用到一個來源） |
| ADR-0011 條件 (1) | 補上「部分端點缺漏」中的卡片、警示與 `/limits`；O-3 為明示接受的殘留 |

#### 對實作的約束（R4-x，風控裁定後生效）
- **R4-1**：判斷只放在 `app/advice/book.py` 的 `build_book_context`。
  - 下列檔案零 diff：`alerts/snapshot.py`（只允許改 L94-100 的 docstring，因為「qualifies a rate that *was* applied」會變不實）、`alerts/engine.py`、`api/advice.py`、`portfolio/valuation.py`、`portfolio/summary.py`、`services/fx*.py`、`data/providers/*`、前端。
  - `snapshot.py` 仍不得出現 `source_note` 識別字。
  - 不得新增 import `app.data.providers.*`（F-1）。
- **R4-2**：閘門與內容依上方 (A)／(B) 規則，而且只讀 `summary.positions[].valuation`。`BookContext.fx_disclosure` 的 docstring 改寫成新條件。
- **R4-3**：以下各格維持 None 且輸出逐位元組不變：TWD 持倉、A 型、未持有的候選標的、對應持倉全部不是 ok、對應持倉的 FxInfo 為 None 或 UNAVAILABLE。
  - **T10-1～T10-3 零修改且全綠。** A 型列的估值器 FxInfo 為 None（`valuation.py:448-451`），單一持倉夾具在 (B) 下仍不成立。
  - 新增 **T10-5**：A 型卡所在的帳本另有一筆 ok 的 USD 持倉時，仍然沒有任何 `SOURCE_NOTES`／`GENERIC_SOURCE_NOTE`。這條用來釘住 (ii-a) 而不是 (ii-b)。
- **R4-4**：已套用報價的一致帳本，輸出逐位元組不變（R2-5 清單與 T10-4 第一條零修改）。
- **R4-5**：W-RK4-1（若風控裁定需要）：
  - 由 creative-lead 起草，風控逐字審；以常數加守門測試釘住，核可前只能用占位字面，且不得出貨。
  - 只在「(B) 成立、(A) 不成立」時出現。卡片與 fired 訊息都要有，同樣式，順序固定（緊鄰方法論句）。
  - 不帶變數、不寫條號。角色用語沿用 RK2-R2 的「持倉市值與總資產」。
- **R4-6**：新增測試，2a 必須先紅後綠：
  - 2a：估值器 ok 加上報價 UNAVAILABLE，涵蓋 snapshot、`evaluate_alerts` 的 fired 訊息、決策卡。
  - 2c：卡無可用收盤價，但持倉為 ok。
  - 混雜幣別且 USD 那批為 ok：期望值依風控對 K-1 的重新裁定。
  - 情境 9 同型：對應持倉為 insufficient、估值器 fx 有值、報價失敗，結果仍為 None。
- **R4-7**：`/limits`（PR-RK4b）：
  - `book_limits` 彙整各標的的揭露句，以句為單位去重，依帳本順序附在 `book_notes` 之後。
  - 純 TWD 帳本的 response 逐位元組不變；`limits` 與各條判定零變化；前端零 diff。
- **R4-8**：從 PR-RK2 合併後的 `product/stock-desk` 開出，不得併入 PR-RK2。若 X-3c 先合併就 rebase，兩者都動 `book.py:1120-1141`。
- **R4-9**：依風控 S-4，PR-RK2 的 RK2-R4 log 要順帶計數 2a；這是 RK-4 升 medium 的依據。

#### 既有測試影響（讀碼推估，未實測）
- **零修改且全綠**：
  - T10-1～T10-4。單元夾具 `_position` 不帶 FxInfo（`test_advice_book.py:67-105`）；API 與警示夾具的 A 型列是 TWD。
  - `test_alerts_snapshot.py:221-252, 284-300`。L244-252 是估值器與報價兩邊都 Unavailable，(B) 不成立。
  - `test_api_advice.py:547-559`、`test_portfolio_summary.py`。
- **注意**：
  - `test_x3_fx_disclosure.py:315-324` 的混雜測試在 (ii-a) 下仍綠，但那只是因為夾具沒有 FxInfo，等同沒驗到東西；要另加真實估值器的混雜測試（R4-6）。
  - 有沒有其他「估值器成功、報價失敗或為 None，且斷言沒有來源句」的測試，我沒有全部讀完（`test_pr0_cap4_atr_backfill.py`、`test_adr0023_w_a2_formal_path.py` 只確認有使用混雜幣別）。dev-lead 須在 PR 說明列出 grep 結果，由 qa 核對。

#### 是否需要 ADR 或加註
- 不需要新 ADR。
- X-3 任務單補「KX-10 精確條件第 2 次修訂」段（tech-writer）。
- ADR-0011（proposed）在「條件 (1) 落實」段加註：卡片、警示、`/limits` 的新條件。
- ADR-0015 W-4 的重審範圍加入 W-RK4-1：加註有 RK2-R9 前例，是否動到 C-24 閘門文字由 CEO 判定。

#### 落地時機
- 順序：風控重新裁定 → PR-RK2 合併 → （X-3c）→ PR-RK4a（book 層）→ PR-RK4b（`/limits`）。
- 不列入 W11-5 前置：快取接線後有舊值退回，2a 的發生率只會下降。

---

#### RK-5

#### 評估摘要
- 採用：`Valuation.fx_open: FxInfo | None`（與 `fx` 並列）；總覽揭露只算 ok 的持倉；聯集與銜接句分成兩個 PR。
- 不併入 ADR-0015 D-8 的工作，但資料形狀與 D-8 對齊。

#### 方案比較
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **(a) `Valuation.fx_open: FxInfo \| None`（採用）** | `FxInfo` 的欄位集合不變：`test_fx_info_freshness.py:40-48, 239-241` 零 diff，ADR-0015 C-15「只因 origin_status 而改」照樣成立；同一個 `_lookup_fx` 產生，D-8 的新欄位自動帶上；前端可以直接重用 `PositionFx` 型別；符合 ADR-0005 D-5「每列保留自身 source」；零額外 provider 呼叫（memo 已存在） | payload 多一個 key（加法式變更，前端執行期會忽略） | 低 |
| (b) 在 `FxInfo` 內加 `open_source`／`open_as_of` 等純量欄位 | 少一個物件 | 破壞 `FxInfo`「只描述 fx_now」的語意（`valuation.py:181`）；欄位集合測試與 C-15 都要改；`FxStatusBadge` 會讀到不屬於它的欄位 | 中，否決 |
| (c) 只在 summary 層加 `fx_open_sources: list[str]` | payload 最小 | 無法逐列追溯，也無法判斷哪一列混源 | 中，否決 |
| (d) 混源時拒絕拆解，或把 fx_open 鎖定到和 fx_now 同一來源 | 數字純淨 | `Totals` 欄位不得為 null、「資產貢獻＋匯率貢獻＝總額」恆等式會被打破；鎖定來源違反 ADR-0015 C-1／C-3 的精神，而且在情境 5 下根本鎖不到（台銀查無資料） | 高，否決 |
| (e) 併進 ADR-0015 D-8 的 PR 一起做 | 只改一次 | 被 W-1～W-8 與 C-24 卡住，W11-5 前很可能做不完；PR 範圍膨脹 | 中，否決（形狀對齊即可） |

#### 決策（不出新 ADR）
- **Context**：
  - fx_open 的來源被丟掉，總覽「匯率貢獻」在兩邊來源不同時會把口徑差算進去，這是 D-5 所說的靜默拼接。
  - O-5：未估值持倉的來源也被列進總覽揭露。
  - ADR-0015 接線後，台銀 fresh 的已結算值永久有效，混源會長期存在。
- **Decision**：
  - 採 (a)。總覽揭露 ＝ ok 持倉的 fx_now 來源句，加上 fx_open 來源句，依序去重。
  - 任一 ok 持倉的 fx_now 與 fx_open **來源 id** 不同時（依 S-1 比 id 不比句子），附銜接句 W-RK5-1，以明示混源。
- **Consequences**：
  - 好處：每列可追溯；D-5 明示；D-8 自動涵蓋 fx_open。
  - 壞處：
    - payload 多一個 key。
    - 多一句新字面，而且要列入 W-4 重審。
    - log 量隨警示 tick 次數增加（每次 `build_summary` 每種組合最多記一行）。
    - 匯率貢獻中混源的部分仍然沒有量化（ADR-0011 尚缺事實 3）。

#### 對實作的約束（R5-x）
- **PR-RK5a（dev-lead，後端，沒有新字面；現在就可以開，與 PR-RK2 沒有檔案交集）**
  - **R5-1**：`Valuation` 新增 `fx_open: FxInfo | None = None`。
    - 值取自 `_latest_fx_on_or_before(pair, opened_at, memo)` 的第二個回傳值。
    - TWD 持倉為 None；`opened_at` 為 None 時也是 None，且不做查詢、不捏造。
    - `FxInfo` 類別零 diff。
    - provider 呼叫次數不變，`test_valuation_cache_only.py:116`「two asks」零修改。
  - **R5-2**：`cost_twd`、`market_value_twd`、拆解數值逐位元組不變：`test_valuation_golden.py`、`test_valuation.py` 零修改。
  - **R5-3**：`fx_disclosures_for` 只算 `status == "ok"` 的持倉，在本 PR 仍只收 fx_now 的來源句（修 O-5）。
  - **R5-4**：任一 ok 持倉的 `fx.source != fx_open.source` 時，記一行英文 WARNING。
    - 內容只能有 pair、兩個 source id、兩個 as_of。
    - 不得含 symbol、id、金額、匯率數值，不得轉發到推播。
    - 每次 `build_summary` 每種 (pair, now_src, open_src) 組合最多一行。
  - **R5-5**：前端、`book.py`、`snapshot.py`、`engine.py` 零 diff。
  - **R5-6**：X-3c 的 KX-A2 短路必須同時讓 `fx_open` 為 None，並把這點寫進 KX-A2。兩個 PR 都動 `valuation.py`，後合併的那個要 rebase。
  - **R5-7**：新增測試：
    - fx_open 的 FxInfo 內容正確。
    - 不同建倉日落在不同來源時，各自記錄。
    - O-5：同 pair 全部 insufficient 時 `fx_disclosures == []`（先紅後綠）。
    - WARNING 用 caplog 驗證內容與次數。
- **PR-RK5b（後端，W-RK5-1 經風控逐字核可後才可出貨）**
  - **R5-8**：`fx_disclosures` 改為 ok 持倉的 [fx_now 句, fx_open 句] 依序去重；混源時在最後附 W-RK5-1。
    - 字面限制比照 RK2-R2：不帶變數；不比較數值；不用安撫語；不出現 source id 或「估值器」等內部用語。
    - 必須說到兩件事：匯率貢獻與成本用到了兩個來源；口徑差會算進匯率貢獻。
    - 以常數加守門測試釘住，核可前不得出貨。
    - 只放在 `fx_disclosures` 清單內，前端零 diff。
- **PR-RK5c（frontend-engineer；需要風控裁定徽章規則，徽章字面不變）**
  - **R5-9**：`page.tsx:62-64` 的判斷抽成純函式 helper：任一 ok 持倉的 `fx` 或 `fx_open` 的 `data_status === "backup"` 就顯示。
    - `types.ts` 新增 `fx_open: PositionFx | null`。
    - 用 vitest 寫表格驅動測試。UI 有變，要走 qa-e2e。
- **R5-10（ADR-0015 加註，W11-5 必須遵守）**：
  - C-22 的範圍擴及 R5-9 的 helper：要加上 `origin_status === "backup"` 的分支（N-2），與 W11-5 放在同一個 PR。
  - D-4 寫明：快取命中與舊值退回時，`FxRateResult.source` 是該列原本的 source id（N-3），並以測試釘住。
  - D-8 的傳遞同樣適用 `Valuation.fx_open`。
  - W-4 的重審範圍加入 fx_open 揭露與 W-RK5-1。

#### 既有測試影響
- 零修改：
  - `test_portfolio_summary.py:280-309`：同一個 provider，fx_now 與 fx_open 的句子相同，去重後一句。
  - `test_portfolio_summary.py:312-324`。
  - `test_fx_info_freshness.py` 全檔：只對 `valuation.fx` 斷言欄位集合。
  - `test_adr0023_w_a2_formal_path.py`：ok 那批與 insufficient 那批同 pair，fx_now 來源相同。
  - `summaryCardsFxDisclosures.test.ts`。
- tests 內 `fx_disclosures` 只出現在上述兩處，O-5 修正不會打破既有斷言。

#### 與 ADR-0015 D-8 的關係與時機
- D-8 尚未實作（RK-2 評估時 `app/data/fx_*.py` 不存在）。
- (a) 讓 D-8 不需要為 fx_open 多做任何事，只需在 C-15 的測試加一列 fx_open。
- 時機：
  - PR-RK5a：現在就做。
  - PR-RK5b、PR-RK5c：W11-5 之前。
- 建議 C-24 再加一條前置條件：「PR-RK5a、PR-RK5b（W-RK5-1 已逐字核可）、PR-RK5c 已合併」。這會改動 accepted ADR 的出貨閘門，**需要 CEO 核可**。CEO 若不核可，W11-5 出貨時須附 CEO 書面知悉「匯率貢獻可能長期混源」。
- 等級建議比照 RK-2：W11-5 先於 PR-RK5b 合併 → medium，由風控裁定。

#### 是否需要 ADR 或加註
- 不需要新 ADR。
- ADR-0011（proposed）加註：`fx_disclosures` 的新定義。
- ADR-0015 加註 R5-10（D-4、D-8、C-22、W-4）；C-24 的變更需 CEO 核可。

### 驗證

**實際讀過的檔案與行號**（`apps/stock-desk/backend/` 之下，除非另外標明）：
- 任務單與審查檔：
  - `work/dispatch/2026-10-08-任務單-RK-4-…md:1-14`
  - `work/dispatch/2026-10-08-任務單-RK-5-…md:1-12`
  - `work/reviews/2026-10-08-RK-2-風控重審X3-F8-來源集合揭露附條件APPROVE.md:1-193`（全文）
  - `work/reviews/2026-10-08-tech-architect-RK-2-估值器與snapshot匯率來源一致性評估.md:1-196`（全文）
  - `work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md:405-429, 590-709`，另 grep X3-R1／KX-A2／KX-10／X3-F8
- `app/advice/book.py`：
  - L118-121（總資產基礎句）、L293-305（`NO_FX_QUOTE_NOTE`、`FX_UNAVAILABLE_NOTE`）
  - L300-499
  - L843-880（`_book_level_notes`）
  - L940-1234
- `app/advice/book_limits.py`：L440-529；grep notes（L293-297、L397-401）
- `app/portfolio/summary.py`：L1-210（全文）
- `app/portfolio/valuation.py`：L137-157、L170-511
- `app/services/fx_notes.py`：L1-63（全文）
- `app/api/advice.py:150-252`、`app/api/portfolio.py:80-206`
- `app/alerts/snapshot.py:90-164`、`app/alerts/engine.py:295-323`
- `app/positions/models.py:34`（grep）
- 前端（`apps/stock-desk/frontend/app/`）：
  - `page.tsx:30-83`
  - `components/SummaryCards.tsx:35-138`
  - `components/RiskGauge.tsx:185-274`
  - `lib/types.ts:150-272`
  - `lib/__tests__/summaryCardsFxDisclosures.test.ts`（全文）
- 測試：
  - `tests/test_x3_fx_disclosure.py:1-345`
  - `tests/test_alerts_snapshot.py:100-259`，另 grep
  - `tests/test_advice_book.py:60-128`
  - `tests/test_portfolio_summary.py:270-325`
  - `tests/test_fx_info_freshness.py:36-55, 215-245`
- ADR（`docs/adr/`）：
  - ADR-0015：L140-264、L300-429，另 grep D-8／C-24／W11-5
  - ADR-0011：L95-138
  - ADR-0005：L265-304

**grep 結果**：
- PR-RK2 尚未合併：`book.py:1137` 仍是單一報價的條件。
- tests 內 `fx_disclosures` 只出現在 `test_portfolio_summary.py:308, 324`。
- 沒有任何測試對整個 `valuation` 物件或欄位集合斷言相等，只有 `valuation.fx` 的欄位集合斷言。
- ADR-0015 內沒有 RK-2 字樣（RK2-R9 的加註尚未落檔）。

**沒有做的**：
- 沒跑測試、沒跑 git、沒碰 DB、沒連網。
- 決策卡前端是否顯示 `position_cost_twd`（`types.ts:642` 有宣告，未查渲染）；playbook 是否呈現由 fx_open 衍生的數字。
- `test_pr0_cap4_atr_backfill.py`、`test_adr0023_w_a2_formal_path.py` 中有沒有 2a 形狀的斷言，沒有全部讀完。
- 「既有測試零修改」全部是讀碼推估。

### 下一步

1. **risk-compliance-officer**：
   - RK-4：
     - 裁定 X3-R1 的新條件（(A) 或 (B)）。
     - 是否推翻 K-1 對混雜幣別的裁定。
     - 是否需要 W-RK4-1。
     - O-3 採 (i)。
     - `/limits` 採 (L-ii) 還是 (i)。
   - RK-5：
     - 裁定 O-5 修正。
     - 銜接句 W-RK5-1 的起草約束。
     - 首頁徽章規則（N-1）。
     - 「W11-5 先於 PR-RK5b → medium」是否成立。
2. **creative-lead**：等風控裁定後起草 W-RK4-1、W-RK5-1。不得延誤 RK2-R2。
3. **CEO**：
   - 核可 ADR-0015 C-24 新增 RK-5 前置條件。
   - 知悉「總覽匯率揭露在摺疊區內」，並據此更正 X-10 的措辭。
4. **dev-lead**：現在就可以開 PR-RK5a（R5-1～R5-7）；PR-RK4a、4b 等風控裁定且 PR-RK2 合併後再開。
5. **frontend-engineer**：PR-RK5c（R5-9）。
6. **tech-writer**：
   - X-3 任務單補 KX-10 精確條件第 2 次修訂段，KX-A2 補上「fx_open 為 None」。
   - ADR-0011 加註。
   - ADR-0015 依 R5-10 加註（D-4、D-8、C-22、W-4）。
7. **qa-reviewer**：依 R4-x、R5-x 逐條核對；零 diff 清單用 `git diff` 確認。

相關檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book_limits.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/portfolio.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/advice.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/summary.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/engine.py
- /home/user/AICompany/apps/stock-desk/frontend/app/page.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/components/SummaryCards.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/components/RiskGauge.tsx
- /home/user/AICompany/apps/stock-desk/backend/tests/test_x3_fx_disclosure.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_fx_info_freshness.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_portfolio_summary.py
- /home/user/AICompany/docs/adr/0015-stock-desk-匯率跨請求快取.md
- /home/user/AICompany/docs/adr/0011-stock-desk-匯率來源梯子與台銀挑戰頁降級.md
- /home/user/AICompany/docs/adr/0005-stock-desk-指數來源與美股額度管理.md
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md