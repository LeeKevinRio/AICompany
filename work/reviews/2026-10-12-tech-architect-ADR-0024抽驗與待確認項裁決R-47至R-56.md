<!-- tech-architect 唯讀回報原文；coordinator 轉存，2026-10-12 -->

# tech-architect 回報：ADR-0024 抽驗與待確認項裁決（TA4；R-47～R-56）

唯讀。讀碼基準是 product/stock-desk 工作樹現況（F-9a 已合併）。沒有讀 `.env` 和任何 `*.db`，也沒有改任何檔案。

## 本次結論

1. **抽驗結果**：D-2、D-4、D-6、D-7、D-9、C-11～C-33、失效條件、PR 拆分都抽了，轉錄大致忠實。**沒有曲解原意的誤植**，但有 **6 處範圍不精確或漏句**（R-53～R-56 與 C-19／C-13 兩處），最重要的兩處：
   - D-2 (5)(a) 第 4 子項「其餘情形」沒限定在「快取被擋」。照字面讀，連通過閘門的快取在冷卻期內也會回 T-15，這是錯的。
   - D-2 (5)(a) 第 2 子項把「照現行 R-8」寫死成「一律以 `RECENT_ATTEMPT_FAILED_REASON` 回快取」，和 C-26「照現行 R-8 行為」不一致。
2. **待確認項裁決**：
   - **題 1**：W-c′ 標記有效＋冷卻期內＋快取被擋 → **只回 C′**，不回 T-15。在風控 F9W-23 授權範圍內，不必再送審，但要把擇定結果轉知風控。
   - **題 2**：定一條不變式：**`rejection` 不為 None ⇔ `UNAVAILABLE` 且 `bars=[]`**，由 `ProviderResult` 的 model validator 強制。帶 bars 的回覆一律 `rejection=None`。估值器只看 `rejection`。
   - **題 3**：指數路徑的快取閘門結構上可能觸發，正式設定下不可達。指數服務不帶任何字面，T-14、T-15 也一樣，而且不讀也不寫標記。**有一點需送風控知悉**。
   - **題 4**：(9) 和「C′。 T-15。」是不同組合，(9) 已在 F9W-22 的審查範圍內。
   - **題 5**：失效條件 5 應補 T-14、T-15，另外加 T-17。
   - **題 6**：兩項衝突處置都同意。我順帶更正自己在 TA2 寫的 C-19：cache_only 不會產生 W-c′。
3. **另有一項需送風控確認（不是新字面）**：W-c′ 層＋通過閘門的快取，經 `_fall_back_to_cache` 回快取時，K 線區的 reason 會是「各層原因（含 W-c′）」配上快取價格和 F-7 單位標籤。這是既有的合併機制，但風控先前只就估值面（F9W-18）審過這個情境。

## 各部門回報

### tech-architect

#### 一、抽驗（逐項）

| 範圍 | 結果 | 說明 |
|---|---|---|
| D-2 (1)～(4)、(6) | 忠實 | R-13 的失效條件編號 7→11 已隨重編更正，正確。PriceBar.currency 型別是 `str`，所以沒寫 F9W-3 的「None」不構成誤植。 |
| D-2 (5)(a) | **不精確** | 第 2 子項過度具體化（見 R-53）。第 4 子項沒限定在快取被擋（R-53）。先後清單漏了「W-c′ 標記＋冷卻期內＋無快取 → C′」，只寫在 D-9（R-47 已併入）。 |
| D-2 (5)(c)／D-2 (3) | **漏句** | TA2「一」寫明 cache-only 遇有效 W-c 標記時 reason 為 None，ADR 漏了；和快取閘門的先後也沒寫（R-54）。 |
| D-4 | 忠實 | R-14、R-15、R-16、M-5 都正確；tech-writer 註由 R-49 取代。 |
| D-6 | 忠實 | R-18～R-20 正確；role 2 排除的處置同意（題 6）。 |
| D-7 | 忠實 | R-22、R-38、R-41、F9W-17／18／25／28 都正確；(7) 的註由 R-48 取代。 |
| D-9 | 忠實 | R-24、F9W-20／21／24／26 都正確。C′ 適用條件要依 R-47 改。 |
| C-11～C-33 | 大致忠實 | C-13 (6) 沒寫 T-14 的替代（R-50）；C-17 要擴充（R-49）；C-19 還留著「若採」，而且組合數本身有誤，是我在 TA2 原本就寫錯的（R-52）；C-26 依 R-47 更新。 |
| 失效條件 1～14 | 忠實 | 去重、合併和出處註記都正確；第 10 條補 F-9b2 的延伸我同意。第 5 條見 R-51。 |
| PR 拆分 | 大致忠實 | F-9b 的「前提」欄漏了 F9W-18 工程條件（只寫在 T-11 狀態欄）（R-55）。F-9b2 列依 R-47 更新。 |
| 程式實況 vs D-5 | 不是誤植，是給 F-9b 的提醒 | F-9a 實作是 `expected_currency: str \| None`，每個服務固定一個幣別，指數服務傳 None（`deps.py` L144-149）。D-5／M-6 要求的是每次依 `market` 查表的函式、必填、keyword-only。**F-9b 必須改掉**，C-6 要釘住（R-56）。 |

#### 二、裁決與建議字句（交 tech-writer）

**R-47〔TA4；題 1，F9W-23 擇定：C′〕**

理由：
- (i) 和 F9W-23 第一款對稱：有效標記＋冷卻期內＋沒有可採用的快取 → 回冷卻句。W-c 回 C／T-14，W-c′ 回 C′。這樣守門只需要一個概念：「有沒有可採用的快取」。
- (ii) C′ 首句「本機尚無此標的可採用的日線資料」本來就是為「沒有可採用的資料」寫的，風控也確認它在這裡屬實。
- (iii) 保留冷卻期長度和「不會自動重試」的揭露，延續 ADR-0009 D-8 的取捨。
- (iv) T-15 在前一次點擊已經以 C-13 (9) 的形式顯示過，取捨和 C 版相同。

代價：這次點擊不會再顯示快取舊列有單位問題，要等冷卻期過後重跑梯子，失敗時才會再出現。

D-2 (5)(a) 整段改為：

> (a) **layer 0**：在讀出整段快取後、所有分支之前檢查一次（不放在 `_cached_result` 裡），得出「可採用的快取」（快取存在且通過快取閘門）。再依下列順序判定，先命中者為準〔TA3 R-39、R-45；F9W-23、F9W-24；TA4 R-47、R-53〕：
> 1. 有效 W-c 標記、冷卻期內：不論快取有無、是否被擋，回 C 版（採用 T-14 時回該市場句），`bars=[]`、`rejection=unit_mismatch`，reason 不含 T-15。
> 2. 有效 W-c 標記、冷卻期外：回 None 走梯子、不服務快取；快取被擋時，本次停用增量。
> 3. 有效 W-c′ 標記、冷卻期內、本機無可採用的快取（無快取，或快取被快取閘門擋下）：回 C′（T-13），`bars=[]`、`rejection=unit_missing`；reason 完全等於 C′，不含 T-15，不打來源。
> 4. 快取被擋，且不屬於 1～3：符合 ADR-0009 R-8 冷卻條件（最後一次提問晚於最後一次完整成功、且在冷卻期內）時，回 `UNAVAILABLE`，reason 完全等於 T-15，`rejection=cache_unit_rejected`，不打來源；否則回 None 走梯子，本次停用增量（`fetch_start = start`；`_incremental_start` 本身不改，ADR-0019 K-10 相容）。
> 5. 其餘（快取通過閘門，或無快取且不屬於 3）：照現行 layer 0 分支行為（ADR-0009 R-8／D-8）。有效 W-c′ 標記不改變任何分支；落在以 `RECENT_ATTEMPT_FAILED_REASON` 回快取的分支時即 T-17（F9W-24）。回覆 `rejection=None`，該列照 D-7 正常估值。

連帶修改：
- D-9「冷卻字面」第 2 子項改為「有效 W-c′ 標記、冷卻期內、本機無可採用的快取（無快取或快取被擋）→ C′ 版（F9W-20；適用範圍依 F9W-23 擴及快取被擋）」。刪除第 4 子項的「待擇一」。
- C-26 改為「W-c′ 標記：無快取或快取被擋 → reason 完全等於 C′、`bars=[]`、provider 呼叫 0 次、`rejection=unit_missing`，不含 T-15；快取通過閘門 → 照現行 R-8 行為（閘門檢查在 R-8 分支之前，測試釘住），該列正常估值」。
- 待決事項最後一列改為「已擇定：C′（TA4 R-47）」。
- F-9b2 列刪掉「須先由 tech-architect 擇定」。

**R-48〔TA4；題 2〕**

D-7 (2) 句尾加：

> **不變式**：`rejection` 不為 None ⇔ 該回覆為 `UNAVAILABLE` 且 `bars=[]`，以 `ProviderResult` 的 model validator 強制，違反即 raise。任何帶 bars 的回覆一律 `rejection=None`，包括：W-c′ 加上通過閘門的快取而回快取、T-17、合併讀回被擋後由其他層整段成功、W-c 層之後有層整段成功。各層的拒收類別只用於 D-9 標記的寫入判斷，不帶到帶 bars 的回覆上。

D-7 (7) 的「注意…待 tech-architect 確認」改為：

> `load_bars` 三分流：(i) 有 bars → 走既有成功路徑，`reason` 原樣傳出，不接 `NO_BARS_REASON`、不加前綴；(ii) 無 bars 且 `rejection` 不為 None → W-d，reason 原樣傳出；(iii) 無 bars 且 `rejection` 為 None → 既有 `NO_BARS_REASON`＋`with_provider_reason`。
> 估值器：`rejection` 不為 None → 新 token（不變式保證 `bars=[]`），不查匯率；否則照既有規則。估值器不得自行用「bars 是否為空」另做第二套判斷。
> 合併讀回被擋後由其他層整段成功時，回傳的 bars 全是該層新抓的列（整段請求，不讀回快取），reason 照既有成功路徑只帶 `mixed_sources_reason`，不含 T-15。

新增 **C-34**：

> (a) 違反不變式時 `ProviderResult` 建構即 raise；
> (b) W-c′＋通過閘門的快取（`_fall_back_to_cache`）：`rejection` 為 None、`LoadedBars.reason` 等於服務層 reason（完全相等）、估值正常；
> (c) 合併讀回被擋後他層整段成功：`rejection` 為 None、reason 不含 T-15、估值正常；
> (d) T-17 回快取：`rejection` 為 None、估值正常。
> (b)～(d) 都斷言該列不進 T-11 組、不顯示 T-12。

**R-49〔TA4；題 3〕**

讀碼：指數服務和股票梯子共用同一個 `_default_cache()`（`deps.py` L146）。指數列的幣別取自 `INDEX_SYMBOL_METADATA`（`yfinance.py` L122-126，`^NDX`／`^GSPC` 為 USD，`^TWII` 為 TWD），和 `MARKET_CURRENCY` 一致。所以 T-15 的路徑結構上存在，正式設定下不可達。指數服務不寫標記，因此 C／T-14 也不可達。

D-4 的「tech-writer 註」改為：

> **指數路徑**〔TA4〕：指數服務的閘門設定為「只檢查幣別、不檢查形狀、不帶任何使用者面字面、不讀也不寫 D-9 標記」，因此 W-a、W-b、W-c、W-c′、C、C′、T-14、T-15 皆不適用指數路徑。
> 指數服務的快取閘門照常 fail-closed（D-1 所有出口皆過）。被擋時回 `UNAVAILABLE`、`bars=[]`、`rejection=cache_unit_rejected`，reason 只含各 live 層的既有原因（可為 None），不加任何字面；layer 0 冷卻期內被擋時 reason 為 None。
> 以測試釘住 `INDEX_SYMBOL_METADATA` 每一列的幣別都等於 `MARKET_CURRENCY[market]`，故正式設定下指數快取閘門不可觸發；只有手動改庫或 `MARKET_CURRENCY` 變動（失效條件 4）會觸發，一觸發即適用失效條件 13（T-16 須先核可）。

C-17 擴為：

> `services/index.py` 與指數服務的建構點不引用 W-a、W-b、W-c、W-c′、C、C′、T-14、T-15 常數（grep）。預置任何 D-9 標記不改變指數回覆（測試）。以假快取壞列觸發指數快取閘門 → `bars=[]`、reason 不含 T-15（測試）。`INDEX_SYMBOL_METADATA` 幣別一致（測試）。role 2 的 live 幣別檢查不可觸發（測試）。

**需送風控知悉**：上述非正式設定的觸發情境下，`index.py` L265／L385 會接既有的指數版 `NO_BARS_REASON`「（來源與快取皆無）」。快取其實有列、只是被拒，所以「快取皆無」並不精確。我的建議是列為殘留：正式設定下不可達、以測試釘住，觸發時依失效條件 13 處理。是否接受由風控裁示。

**R-50〔TA4；題 4〕**

C-13 的 tech-writer 註改為：

> (9) 是 live 梯子路徑：某 live 層為 W-c′、其餘層都拒答、`_fall_back_to_cache` 快取被擋（D-2 (5)(b)），reason 依 `_combine_reasons` 為各層原因＋T-15，`rejection=unit_missing`，D-9 寫入 `unit_missing`。測試用單一 rung 梯子，使字串恰為「W-c′。 T-15。」。
> 這和 F9W-23 禁止的冷卻期「C′。 T-15。」不同：C′ 是冷卻期內的整句回覆（D-2 (5)(a) 第 3 項），不與任何句合併。
> (9) 在 TA3 題 4 已列出，風控 F9W-22 要求 (7)～(10) 用完全相等斷言，屬已審範圍。

另外，(6) 改為「C 版（採用 T-14 時為美／台兩句，各一測）」。

**R-51〔TA4；題 5〕**

失效條件 5 改為：

> 風控否決或撤回任一新字面或字面用法（W-a、W-b、W-c、W-c′、C、C′（T-13）、T-11、T-12、T-14、T-15，以及 T-17「W-c′ 有快取時沿用 `RECENT_ATTEMPT_FAILED_REASON`」）→ 重審 D-7／D-9 與對應 PR 範圍。T-14 若被否決，只退回 C 版，不影響其餘。

出處欄加「T-14、T-15、T-17 為 TA4 R-51 補列」。

**R-52〔TA4；題 6〕**

- **D-6 以 TA2「五」的「role 2 排除」為準：同意。** TA2 內部一致：R-20 把 role 2 列為寫死的假設值，R-15 要求 role 2 誠實回報前指數幣別檢查不可觸發，「五」的硬性前提 5 也是。初稿「role 1／2 改用」已被取代。
- **「不查匯率」由建議升為條件：同意。** F9W-18 要求 `missing` 只有一個 token。若查了匯率又不記 fx token，結果毫無用處，還會多打 FX 來源；不查是唯一乾淨的做法，也和 X-3c 先例一致。
- C-19 改為（含我對 TA2 原文的自我更正）：

> 新 token：live 下准入、W-c、W-c′、快取被擋（T-15）各一測；cache_only 下准入、快取被擋各一測（W-c 標記屬 F-9b2，見 C-25）。cache_only 不打來源、W-c′ 標記也不適用 cache-only，不會產生 W-c′，不設此測試。每測斷言 `missing == [新 token]`，不含 `price`、`price_not_queried`、`fx_now`、`fx_open`；`fx`／`fx_open` 為 None；匯率 provider 零呼叫（F9W-18 條件，不是建議）。帶 bars 的情境見 C-34。

**R-53〔TA4；抽驗〕** D-2 (5)(a) 第 2、4 子項的範圍修正，已併入 R-47 的整段改寫。

**R-54〔TA4；抽驗〕** D-2 (5)(c) 改為：

> `get_cached_bars` 依序：准入 → 有效 W-c 標記（不論冷卻）回 `UNAVAILABLE`、reason 為 None、`rejection=unit_mismatch`〔TA2「一」〕→ 快取閘門被擋回 `UNAVAILABLE`、reason 為 T-15、`rejection=cache_unit_rejected`。W-c′ 標記不適用。

**R-55〔TA4；抽驗〕** PR 表 F-9b「前提」欄加「F9W-18 工程條件（D-7 (2)(3) 不變式與互斥、C-19、C-34）」。

**R-56〔TA4；抽驗，給 F-9b 實作〕** 「實作約束」加一條，或在 C-6 加註：

> F-9a 的 `expected_currency: str | None`（指數傳 None）在 F-9b 改為 keyword-only 必填的 market→幣別查表函式（D-5、M-6）。三個建構點各自顯式傳入准入規則（指數：只檢查幣別、不檢查形狀）和字面組（指數：無）。不得保留 None 預設值。

### 給其他部門（經 coordinator 轉達）

- **tech-writer**：套用 R-47～R-56。移除 D-4 L166、D-7 L204、C-13 L246、失效條件 5、待決事項末列、佐證 L501 的「待 tech-architect 確認」註記，改標〔TA4 R-x〕。佐證清單加上本回覆的來源列。
- **risk-compliance-officer**（需送審或知悉）：
  - (a) R-47 擇定 C′：屬 F9W-23 授權範圍，只需知悉。
  - (b) R-49 指數路徑在非正式設定下觸發時，會沿用既有指數版 `NO_BARS_REASON`，「快取皆無」不精確；我建議列為殘留，請裁示。
  - (c) R-48 情境：W-c′ 層＋通過閘門的快取經 `_fall_back_to_cache` 回快取時，K 線區 reason 是「AV 原因句。 W-c′。」這類合併句，配上快取價格與 F-7 單位標籤。這是既有合併機制，不是新字面，但先前只審了估值面，請確認可接受。
- **dev-lead／data-engineer**：F-9b 依 R-48 不變式、C-34、R-54、R-56 實作。F-9b2 依 R-47 的五步先後實作，並以完全相等測試釘住。

## 驗證

- **讀過的文件**：
  - ADR-0024 全文（502 行）
  - TA1（M-1～M-15 與失效條件意見）、TA2（R-1～R-37、C-11～C-29、「一」「四」「五」）、TA3（R-38～R-46、題 1～4）
  - 風控 F9W-1～F9W-16、F9W-17～F9W-29 全文
- **讀碼核對**（工作樹現況，F-9a 合併後）：
  - `app/data/service.py`：`_REASON_SEPARATOR` L34；`RECENT_ATTEMPT_FAILED_REASON` L43；`MERGE_READBACK_FAILED_REASON` L60；`COOLDOWN_NO_CACHE_REASON` L70；`get_daily_bars` L185（`cache.put` L211、成功 `record_attempt` L213、合併讀回 L220-231、成功路徑只帶 `mixed_sources_reason` L265-273、全層拒答 `record_attempt` L277）；`get_cached_bars` L282-323；layer 0 L392-523（快取讀出 L404，三個冷卻／快取出口 L426、L459、L500，一般服務 L518）；`_try_provider` L556（`source_id` 退回類別名稱 L581）；`_fall_back_to_cache` L601-651。
  - `app/data/interface.py`：`ProviderResult` L87-130，目前沒有 `rejection` 欄。
  - `app/services/market.py`：`load_bars` L147-194，有 bars 時 reason 原樣傳出。
  - `app/portfolio/valuation.py`：`value_position` L353-431、`_resolve_price` L433-468。
  - `app/services/index.py`：L255-269、L377-389 接 `with_provider_reason`。
  - `app/api/deps.py`：L101-115、L144-151（指數 `expected_currency=None`，共用 cache）。
  - `app/data/providers/yfinance.py`：`INDEX_SYMBOL_METADATA` L122-126。
- **行號漂移**：ADR 引用的 `service.py` L182／L184／L191／L241 對應現況約為 L185／L213／L220／L277。ADR 已聲明會漂移，不必改正文。
- **屬推論、尚未實證**：
  - 指數快取閘門「正式設定下不可達」，是依 `INDEX_SYMBOL_METADATA` 和 `MARKET_CURRENCY` 一致推得，須用 R-49 的測試釘住。
  - R-48 各情境的 reason 字串是依現行合併機制推得。
- **未做的事**：沒有執行測試、沒有連網、沒有改檔；沒有讀 `.env` 和 `*.db`。

## 下一步

1. **coordinator**：把 R-47～R-56 交 tech-writer 一次套用到 `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`。同時把 R-48 情境 (c)、R-49 殘留、R-47 擇定轉給 risk-compliance-officer。
2. **risk-compliance-officer**：裁示 R-49 殘留可否接受，並確認 R-48 情境 (c)。R-47 只需知悉。
3. **tech-writer**：套用後回報；我可以再抽驗一次 D-2 (5)(a) 的五步改寫和 C-19、C-34。
4. **dev-lead**：F-9b／F-9b2 實作依 R-47、R-48、R-54、R-56；qa-reviewer 增勾 C-34 和擴充後的 C-17、C-19、C-26。
5. **CEO**：T-10 核可時一併知悉 R-49 的指數殘留（風控裁示後）。

相關檔案（絕對路徑）：
- /home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md
- /home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024落檔核對M-1至M-15.md
- /home/user/AICompany/work/reviews/2026-10-12-tech-architect-F-9-風控裁定工程評估與ADR-0024修改清單R-1至R-37.md
- /home/user/AICompany/work/reviews/2026-10-12-tech-architect-F-9-第二批字面四題回覆R-38至R-46.md
- /home/user/AICompany/work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md
- /home/user/AICompany/work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/interface.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/market.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/index.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/deps.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py