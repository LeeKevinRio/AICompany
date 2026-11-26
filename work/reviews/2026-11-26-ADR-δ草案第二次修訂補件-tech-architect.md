# ADR-δ 草案第二次修訂補件（併入 position.weight 查證）

- 審查者：tech-architect
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. dev-lead 對 S2 前提 (b) 的查證結論已併進修訂稿。修訂稿新增 2.9 一節，dev-lead 要我決定的兩題，答案如下：
   - **(a) 不把整份判定套到估值路徑本身**，`valuation.py` 和 `summary.py` 都不改。改成在建議卡這一層做兩項窄幅檢查，只影響本標的這一張卡：
     - (a-1) 本卡日線的最新一根本身涉入判定時，整張卡走 `insufficient_data`。「涉入」指：最新一根違反任一條 V 規則，或疑似跳空的那一天就是最新一根。
     - (a-2) 估值用的最新價格（日期和 close）要和本卡日線最新一根逐位相等。只要有一筆不等，本卡的比重就當成 None，`concentration_watch` 記為 skipped。
   - **(b) 0.0 改成 None**：只要本標的已持有，而且有任何一筆持倉沒估到值（全部沒估到或只估到一部分都算），本標的的持倉市值就回 None。
     - 這是獨立的缺陷，不管日線判定、也不管 CEO 選 S1 還是 S2 都存在，所以另開 B-5，登記後做。
     - 它會牽動所有讀這個值的消費端。我推測 cap 1 也在其中，但沒有讀碼確認。消費端清單由 dev-lead 列出，送風控。
2. 第 8 節的 CEO 題目，選項二有一句已經不成立：「它會不會也被同一筆錯價影響還在查證」。查證結果是：
   - 歷史日線有錯，不會影響比重；
   - 最新一根本身有錯時，兩案都是整張卡回資料不足；
   - 兩次讀取不一致時，比重提醒會被跳過。
   - 我在對照表標了這一點，題目文字沒有改，請風控重寫。改寫前，這題不能送 CEO。
3. 加了 (a-2) 和 (b) 之後，就算判定是 `usable`，結果也可能和現況不同。所以「usable 時和現況逐欄相同」的回歸鎖改成附條件：判定是 usable、一致性檢查通過、而且本標的沒有未估值的持倉時，才要求逐欄相同。

## 發現

### 修訂對照表（第二次修訂，接在第一次修訂表第 37 項之後）

| # | 來源 | 修訂位置 | 改成什麼 |
|---|---|---|---|
| 38 | [DL3] 本次結論第 1～3 點；RC-905 第 4 點 (b) | 2.4「S2 前提」(b) | 從「待查前提」改成已查證的結論：比重只讀各持倉最新一根的快取 close，和本卡日線是兩次獨立讀取；守門只有 `usable_price`。處置見 2.9 |
| 39 | [DL3] 下一步 1(a) | 新增 2.9 第 1、2 點；Options H 新增 | 不把判定套到估值路徑；在建議卡層加 (a-1) 最新一根涉入判定、(a-2) 一致性檢查 |
| 40 | [DL3] 下一步 1(a) | 2.4 第 2 點 | 「最新一根涉入判定」的範圍擴大，`gap` 而且 j = n（k = 0）也算；這種情形 close 改成 None，整卡走 `insufficient_data` |
| 41 | [DL3] 發現 C；下一步 1(b) | 新增 2.9 第 3 點；5.3 新增 B-5 | 已持有但有任何一筆未估值時，`position_market_value_twd` 回 None，`concentration_watch` 記為 skipped，讀這個值的上限走 not_evaluable。部分估值也算在內（fail-closed） |
| 42 | 同上 | 2.6；6.1 回歸鎖 | 「usable 時逐欄相同」改成附條件，見本次結論第 3 點 |
| 43 | 同上 | 6.1 新增 B-5 測試 | 列出 10 個情境 |
| 44 | 同上 | K-14、K-15 新增 | `valuation.py`、`summary.py` 零差異；(a-2) 用精確比較；未估值時回 None，不得回 0.0 |
| 45 | [DL3] 發現 B | Consequences | 殘留風險：分母含其他持倉的最新快取 close，正數但錯誤時仍會汙染比重；不在本 ADR 範圍 |
| 46 | [DL3] | Options B 的 S2 列、表下說明；Consequences 的 S2 那一條 | 拿掉「取決於前提 (b)」，改寫成已查證的事實 |
| 47 | [DL3] | 未決事項 | 刪除 (b) 的查證；新增：讀 `position_market_value_twd` 的消費端清單、是否有 accepted ADR 定義過 0.0、兩次讀取不一致的頻率、W-17 |
| 48 | [DL3] | 5.6 W 編號表 | 新增 W-17：`valuation_bar_mismatch` 的跳過原因 |
| 49 | **RC-906 選項二** | 第 8 節 | **標記：選項二「它會不會也被同一筆錯價影響還在查證」已不成立**。實際情形見本次結論第 2 點。題目文字**沒有改**，交風控重寫；重寫前不得送 CEO。另外，選項二的「多保留下來的只有兩樣」仍然成立，但比重提醒在一致性不符時也會被跳過，這點也請風控一起評估要不要寫進題目 |
| 50 | [DL3] | 與既有 ADR 的關係 | 新增 ADR-0010 D-1：cache-only valuator 不改 |

### 修訂稿的替換段落

以下各段取代第一次修訂稿的同名段落，或依指示插入。其他段落和第一次修訂稿逐字相同。標頭第一行的狀態要改成：「proposed（第二次修訂，2026-11-26，併入 [DL3]）」。來源清單加一行：
`- [DL3] reviews/2026-11-26-position.weight估值價來源查證-dev-lead.md`

**（取代）Options B 的 S2 列與表下說明**

```markdown
| S2 逐欄位拒算，並套用 2.4 第 4 點的替代規則 | 保留 cap 1～3（依部位計算）和 `concentration_watch`；cap 4 無法評估。比重只讀各持倉最新一根的快取 close，**歷史日線有壞值不影響比重**（[DL3]） | 改動比較多；標題和 S1 一樣是「資料不足」；持有卡最多 1/12 可評估，候選卡 0/12 | 最新一根本身涉入時，兩案都整卡回資料不足（2.4 第 2 點）。比重和本卡日線是兩次獨立讀取，不保證一致，所以用 2.9 的一致性檢查，不一致就跳過比重規則 |

- 兩案在標題層面相同，差別只在上限清單和集中度提醒（RC-905 第 4 點）。S2 多保留的集中度提醒，只在「歷史日線有錯、最新一根正常、兩次讀取一致」時才出現。
- tech-architect 傾向 S2，理由是上限清單本身就是風控揭露；但實際多保留的東西很少，所以交 CEO 決定（第 8 節）。
```

**（新增）Options H：比重的估值價格（放在 Options G 之後）**

```markdown
### H. `position.weight` 的估值價格要不要套用判定

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| H1 不處理 | 零改動 | 最新 close 是正數但錯誤，或兩次讀取不一致時，比重會靜默出錯 | 集中度提醒出現假的「沒命中」 |
| H2 在估值路徑（`valuation.py`）套用整份判定 | 全產品一致 | 估值是全產品共用的（持倉頁、整書總額、各上限），會改變全產品的估值語意，屬於 ADR-0010 D-1、ADR-0016 的範圍；而且估值只讀 10 天、只看最新一根，沒有可以判定的整批日線 | 範圍外的行為改變 |
| **H3（採用）在建議卡層做兩項窄幅檢查（2.9）** | 只影響本標的這張卡；估值模組零差異；能擋住「最新一根有錯」和「兩次讀取不一致」 | 擋不住分母裡其他持倉的錯價 | 殘留風險，見 Consequences |
```

**（取代）2.4 第 2 點**

```markdown
2. **最新一根涉入判定**（以下任一情形）時，`close` 改成 None，走既有的 `insufficient_data` 路徑（`advice.py:234-258`）：
   - 最新一根違反任一條 V 規則；
   - 判定為 `gap`，而且有任何一對可疑的相鄰 bar 滿足 j = n（k = 0，可疑那一天就是最新一根）。
   - `reason` 帶原因代號 `daily_bars_unusable` 或 `corporate_action_suspected`。
   - 這種情形下卡片不會進引擎，比重也不會被評估。依 [DL2] E 節，保不保留 close 不影響可評估的規則數；只有最新一根沒有涉入時保留 close，目的是讓上限能計算。
```

**（取代）2.4「S2 轉 accepted 之前要成立的前提」(b)**

```markdown
- (b) **已查證**（[DL3]）：
  - `position.weight` 不依賴 `/api/advice` 這批日線。它來自 portfolio summary 另外做的一次純快取讀取（回看 10 天，只取各持倉最新一根的 close；`valuation.py:484-517`）。
  - 歷史日線有壞值、或最新一根只有 low 有問題時，比重都不受影響；最新一根的 close 是正數但數值錯誤時，比重會直接被汙染。
  - 守門只有 `usable_price`（有限且 > 0，`price_guard.py:31-48`）。
  - 已持有但沒估到值時，比重會被寫成 0.0，而不是 None（`book.py:639-655,1403`）。
  - 處置見 2.9。
```

**（新增）2.9 `position.weight` 的估值價格（S2 前提 (b) 的處置）**

```markdown
**2.9 `position.weight` 的估值價格**（採 Options H3；本節第 3 點不論 S1 或 S2 都適用）

1. **範圍**：`portfolio/valuation.py`、`portfolio/summary.py` 零差異；判定不套用到估值路徑本身。理由見 Options H。
2. **建議卡層的兩項檢查**（只作用在本標的這張卡）：
   - (a-1) 最新一根涉入判定時，照 2.4 第 2 點整卡走 `insufficient_data`，比重不進引擎。
   - (a-2) **一致性檢查**：本標的每一筆已估值的持倉，估值價格的日期（`valuation.price.as_of`）和 close，都必須等於本卡日線最新一根的日期和 close。
     - close 用 `Decimal` 逐位比較，不經浮點。
     - 只要有一筆不等，本卡的 `position_market_value_twd`，以及由它算出的 `position.weight`，都當成 None。
     - 結果：`concentration_watch` 記為 skipped，原因代號 `valuation_bar_mismatch`（字面 W-17）；讀這個值的上限走 ADR-0023 的 not_evaluable 路徑。
     - 不論判定是不是 usable，本檢查都適用，因為兩次讀取不一致和日線品質無關。
   - 實作位置在 `api/advice.py` 或 `advice/book.py` 組裝本卡 context 的那一步，兩者都不在 digest 的兩層內。不得改估值模組。
3. **已持有但沒估到值時回 None，不回 0.0**：
   - 條件：本標的已持有，而且至少一筆持倉沒有估到值（`valuation.status != "ok"` 或 `market_value_twd` 是 None）。
   - 處置：`position_market_value_twd` 回 None。全部沒估到值、只估到一部分，**都**適用；部分加總會低估比重，對集中度提醒和依比重計算的上限來說是放心型的偏誤，所以採 fail-closed。
   - 結果：`concentration_watch` 記為 skipped，用既有的「缺少輸入欄位」原因（這次確實是缺值，不違反 K-9）；讀這個值的消費端走各自的 None 路徑。
   - `SYMBOL_UNVALUED_NOTE` 保留。
   - 改的是 `advice/book.py`（`:639-655` 的 rollup，或 `:1403` 的填值），不在 digest 範圍內。登記後以獨立的 B-5 實作，不和 B-2 綁在一起。
   - **B-5 開工前要先做的事**：
     - dev-lead 列出 `backend/app` 裡讀 `position_market_value_twd` 或 `position_weight()` 的全部消費端，例如各上限、`suggest_quantity_range`，並逐一確認它們的 None 路徑存在而且是 fail-closed，清單送風控；
     - 確認有沒有 accepted ADR 明定過 0.0 的語意。有的話，本節改寫成「補充或取代該 ADR 的某一條」。
4. **殘留風險**：分母 `total_equity_twd` 加總了全部持倉的最新快取 close（`summary.py:160-175`）。其他持倉的 close 如果是正數但錯誤，仍會汙染本標的的比重。這屬於全書估值的品質問題，不在本 ADR 範圍，交 ADR-0016 或 portfolio 另案處理。
```

**（取代）2.6 的回歸鎖那一句**

```markdown
- 判定為 `usable`、2.9 第 2 點 (a-2) 的一致性檢查通過、而且本標的沒有 2.9 第 3 點所說的未估值持倉時，輸出由回歸鎖保證和現況逐欄相同（6.1）。這三個條件之外的差異，就是本 ADR 有意造成的行為改變，記在「變更紀錄」。
```

**（取代）5.3 的後端 PR 列表（插在 F-3 之後）**

```markdown
- **後端（登記後）**：B-1 特性測試和判定模組；B-2 `/api/advice`、`/api/signals` 的套用和引擎閘門，含 2.9 第 2 點；B-3 警示；B-4 H_f 和 G-4；**B-5 已持有但沒估到值時回 None（2.9 第 3 點），不受 CEO 第 8 節的選擇影響**；F-4 前端改讀後端判定。
```

**（新增）6.1「B-5 與 2.9 測試」（接在「其他後端測試」之後）**

```markdown
- **2.9 的測試（B-2、B-5）**：
  1. 歷史日線有壞值、最新一根正常、兩次讀取一致，採 S2：比重照常評估，`concentration_watch` 可以命中。
  2. 最新一根 low = 0：整卡 `insufficient_data`（2.4 第 2 點）。
  3. `gap` 而且 k = 0：整卡 `insufficient_data`。
  4. 估值價格的日期和本卡最新一根不同：比重是 None，`concentration_watch` 記為 skipped（`valuation_bar_mismatch`）。
  5. 日期相同但 close 不同（例如差十倍）：同第 4 項。
  6. 兩者完全相同：和現況逐欄相同（回歸鎖）。
  7. 已持有，全部持倉都沒估到值：`position_market_value_twd` 是 None，`concentration_watch` 記為 skipped，讀這個值的上限走 not_evaluable，`SYMBOL_UNVALUED_NOTE` 存在。
  8. 已持有，部分持倉沒估到值：同第 7 項。
  9. 沒有持有：比重照舊是 0 或依現行定義，不受第 3 點影響。
  10. B-5 開工前列出的每個消費端，各有一則 None 路徑測試。
- 回歸鎖依 2.6 的三個條件建立 fixture。
```

**（新增）K-14、K-15**

```markdown
- K-14：本 ADR 的所有 PR 中，`portfolio/valuation.py`、`portfolio/summary.py` 零差異；(a-2) 的 close 比較用 `Decimal` 逐位比較。
- K-15：已持有、而且至少一筆持倉沒估到值時，`position_market_value_twd` 是 None，不得是 0.0（B-5 測試第 7、8 項）。
```

**（取代）Consequences 的 S2 那一條，並新增兩條**

```markdown
- **S2 的實際收益很小**：持有卡最多 1/12，候選卡 0/12。集中度提醒只在「歷史日線有錯、最新一根正常、兩次讀取一致」時才保留。
- **2.9 (a-2)**：就算判定是 usable，兩次讀取不一致時也會跳過比重規則。實際頻率沒有查證，由 qa-e2e 或 data-engineer 另行查證。
- **2.9 第 3 點**：已持有、只要有一筆持倉沒估到值，本標的的集中度提醒和依比重計算的上限就不評估。比起顯示假的 0%，這樣比較保守；代價是少一項檢查。
- **殘留風險**：其他持倉的 close 是正數但錯誤時，仍會經由分母汙染比重（2.9 第 4 點）。
```

**（新增）與既有 ADR 的關係**

```markdown
- **ADR-0010 D-1（accepted）**：cache-only valuator 不改（K-14）。2.9 的檢查只作用在建議卡組裝那一步。
- **ADR-0023**：2.9 第 2、3 點讓讀比重的上限走 not_evaluable 路徑。
- 2.9 第 3 點如果和某則 accepted ADR 定義的 0.0 語意衝突，以該 ADR 為準；B-5 開工前要查證，並改寫成補充或取代。
```

**（取代）5.6 W 編號表，加一列**

```markdown
| W-17 | 跳過原因 `valuation_bar_mismatch` | 2.9 第 2 點 |
```

**（取代）未決事項的 dev-lead、風控兩項，並新增 qa-e2e 或 data-engineer**

```markdown
- **risk-compliance-officer**：
  - 核對修訂過的段落；
  - 確認 2.4 第 4 點 (i) 的讀法和 (iv) 的新增；
  - **重寫第 8 節選項二**（「它會不會也被同一筆錯價影響還在查證」已不成立，見修訂對照表第 49 項）；
  - 判斷 2.9 第 3 點「部分估值也回 None」的取捨；
  - W-1～W-17 的逐字審；
  - F-4 的上限違規句位置；候選卡覆蓋度句的改寫。
- **dev-lead**：
  - H_f 凍結的數值，以及各欄位實際的 W_f；
  - B-5 開工前列出讀 `position_market_value_twd` 或 `position_weight()` 的消費端清單；
  - 查證有沒有 accepted ADR 定義過 0.0 的語意。
- **qa-e2e 或 data-engineer**：兩次讀取（`load_bars` 和 cache-only 估值）實際不一致的頻率；`_cache_refuses` 在 cache_only 層拒收的條件。
```

**（取代）變更紀錄，加一條**

```markdown
- 2026-11-26 第二次修訂：依 [DL3]。
  - 2.4 的 S2 前提 (b) 改成已查證；
  - 2.4 第 2 點加入 `gap` 且 k = 0 的情形；
  - 新增 2.9（建議卡層的一致性檢查；已持有但沒估到值時回 None）；
  - 回歸鎖改成附條件；
  - 新增 K-14、K-15、W-17；
  - 第 8 節選項二有一句已不成立，題目待風控重寫。
```

**第 8 節**：題目文字不改。送出條件加一條：「選項二已經有一句不成立（修訂對照表第 49 項），風控重寫完成之前不得送出。」

## 驗證

- 讀了 `/home/user/AICompany/work/reviews/2026-11-26-position.weight估值價來源查證-dev-lead.md` 第 1-94 行全文。
- 引用的行號都出自 dev-lead 的報告，我沒有親自讀，包括 `valuation.py:484-517`、`book.py:639-655,1403`、`price_guard.py:31-48`、`summary.py:160-175`、`advice.py:152-154`（我在第一輪讀過這幾行，確認有 `valuation.price.as_of`）。
- **沒有查證的事項**：
  - 讀 `position_market_value_twd` 的實際消費端。cap 1 是否在其中，我沒有讀碼確認，所以寫成 B-5 開工前要先做的事。
  - 有沒有 accepted ADR 定義過 0.0 的語意。
  - `valuation.price.as_of` 的型別，以及它能不能直接和 bar 的 date 比較，交實作確認。
  - 兩次讀取不一致的頻率。
- 沒有寫檔、沒有執行指令；沒有讀 `.env*`、沒有碰 `backend/data/`、沒有對 `apps/` 搜尋。

## 下一步

1. **coordinator**：
   - 把本回報的替換段落併進第一次修訂稿，標頭改成「第二次修訂」；
   - 把修訂對照表第 38～50 項連同替換段落送風控核對；
   - 請風控重寫第 8 節選項二。重寫完成、而且核對通過之前，題目不得送 CEO。
2. **risk-compliance-officer**：
   - 重寫選項二；
   - 判斷 2.9 第 3 點「部分估值也回 None」的取捨；
   - 判斷 (a-2) 在判定為 usable 時也適用是否可以接受。
3. **dev-lead**：
   - 列出讀 `position_market_value_twd` 或 `position_weight()` 的消費端清單；
   - 查證有沒有 accepted ADR 定義過 0.0 的語意。
   - 兩項都屬於 B-5 開工前的前提，不擋 ADR 落檔。
4. **qa-e2e 或 data-engineer**：查證兩次讀取不一致的頻率，以及 `_cache_refuses` 的拒收條件。
5. **creative-lead**：風控核對後，把 W-17 加入起草清單。

**相關路徑**
- /home/user/AICompany/work/reviews/2026-11-26-position.weight估值價來源查證-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-26-ADR-δ草案-日線壞值與跳空的判定與處置-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-26-ADR-δ草案行為審查-RC900至RC908-風控.md
