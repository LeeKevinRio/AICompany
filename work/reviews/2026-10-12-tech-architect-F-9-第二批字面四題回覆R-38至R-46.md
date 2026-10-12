# tech-architect 對 F-9 第二批字面四題的回覆（TA3；R-38～R-46）

- 唯讀讀碼，coordinator 自 agent 回報原文轉存（2026-10-12）。

## 本次結論

creative-lead 的四題答覆如下，(e) 的理由經讀碼查證成立：

1. **快取閘門拒收時要設 `rejection`**。建議新增一個值 `cache_unit_rejected`，單位不符與空白共用這一個值，因為 T-15 也是一句涵蓋兩者。估值器看到它一樣回新 token，該列歸入 T-11 那一組，庫存頁顯示 T-12 標籤，不會落入「查無價格資料」。這個值絕不寫進 attempt log，D-9 標記只由 live 層寫入。
2. **layer 0 被快取閘門擋下時，依所在分支分流**：
   - 冷卻期內的 R-8 分支：回 `UNAVAILABLE`，reason 只放 T-15，然後結束。
   - 其他分支：回 None，改走梯子，而且這一次停用增量、整段重抓。來源若能回答，就用通過閘門的新列覆寫壞列，序列自行修復，不必等 F-9e。
   - 兩種做法 T-15 都屬實，因為它只講「本機快取中的資料整段不採用」，沒提有沒有問過來源。差別在出現頻率：直接結束的話，T-15 每次點擊都會出現，一直到 F-9e 清理；分流的話，只在梯子失敗或冷卻期內出現。
3. **增量合併讀回被擋時用 T-15，同意 creative-lead**。`MERGE_READBACK_FAILED_REASON` 說「無法讀回」，但實際是讀回了、因單位問題被拒，所以不屬實。T-15 在 reason 中只能出現一次。照第 2 題的設計，這條路徑只剩併發競態時才可能觸發。
4. **T-15 併入 W-d 整組**：不接 `NO_BARS_REASON`，不走 `with_provider_reason`。C-13 的完全相等測試從 6 個情境擴成 10 個。
5. **T-11 不採 (e)「非價格或匯率中斷」**：理由成立，但要補兩點修正。
   - 「AV 中斷」只是 AV 拒答的其中一種原因，不是全部。
   - 真正讓 (e) 不能用的是另一點：一組成因句必須對組內每一列都成立。只要組內有一列屬於混合情境，例如 AV 額度用完加上 yfinance 單位被拒，(e) 對那一列就不成立。
   - 結論：主案或 alt-C（「並非只是…」）都可以。alt-B（照 (e) 逐字）不建議。

R-清單需要增修 9 條（R-38～R-46），列在下方。

## 各部門回報

### tech-architect（唯讀讀碼）

#### 題 1：快取閘門拒收時 `rejection` 怎麼設
- **方案比較**：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 不設值 | 不用改任何東西 | 估值器會回 `price` 或 `price_not_queried`，畫面顯示「查無價格資料」或「本次未查價格」，該列又被算進 W4「缺價格或匯率」，與事實不符 | 正是 F9W-11 要禁止的情形，否決 |
| 沿用 `unit_mismatch`／`unit_missing` | 不必新增值 | 會和 live W-c 的語意混在一起。live W-c 會觸發「本次不讀快取」與 D-9 標記，這兩件事都不該由快取拒收觸發；空白和不符也得在快取路徑多做一次分類 | 日後有人用 rejection 決定要不要寫標記時會寫錯 |
| **新增 `cache_unit_rejected`（採用）** | 語意分得清楚；一個值就對應 T-15 一句；測試容易釘住 | enum 多一個值 | 低 |

- **優先序**：同一次回覆可能同時有好幾種原因，只回一個值，順序是 `unit_mismatch` ＞ `unit_missing` ＞ `cache_unit_rejected`。`symbol_not_admitted` 和其他值不會同時出現。
- 哪個值都一樣：估值器回新 token，`load_bars` 照 W-d 原樣傳出 reason。
- 實例：W-c′ 層加上快取被擋時，reason 是「W-c′。 T-15。」，rejection 是 `unit_missing`。
- W-c 與壞快取不會同時出現：依 F9W-4，W-c 時根本不讀快取，所以 T-15 不會出現。

#### 題 2：layer 0 被擋後的行為
- **讀碼確認**：
  - `service.py` L159-162：layer 0 只要回非 None 就結束。
  - L324：layer 0 一開始就讀了整段 `[start, end]` 的快取，三個出口用的都是這份 `cached`。
- **設計**：閘門檢查放在 L324 讀出之後、所有分支之前，只檢查一次，不放在 `_cached_result` 裡。理由是要先知道被擋才能決定走哪個分支。這修正了 M-8「在 `_cached_result` 設檢查點」的建議。
  - **冷卻期內**（同 R-8 判斷：最後一次提問晚於最後一次完整成功、且在冷卻期內）：回 `UNAVAILABLE`、`bars=[]`、reason 只放 T-15、rejection 為 `cache_unit_rejected`，不打來源。這樣才守得住 ADR-0009 R-8／D-8「每個冷卻窗至多跑一次梯子」。冷卻資訊不寫進 reason，因為 `COOLDOWN_NO_CACHE_REASON` 說「本機尚無此標的的日線資料」，在這裡不屬實；這和 C 版的取捨相同。
  - **其他分支**（HAS_LATEST、CHECKED_RECENTLY、沒有 coverage 但不在冷卻期、REFETCH 但不在冷卻期）：回 None 走梯子，同時把這次的 `fetch_start` 設成 `start`，停用增量。`_incremental_start` 本身三個條件不改，所以 ADR-0019 K-10 不受影響。
- **後果**：
  - 來源能完整回答時，put 會覆寫請求區間內的壞列，序列自行修復。
  - 來源失敗時，最後進 `_fall_back_to_cache`，回 `UNAVAILABLE`，reason 是各層原因加上 T-15。下一次點擊落在冷卻期內，就是上面的第一種情形。
  - 成本上限：每個冷卻窗至多一輪梯子，美股就是每 24 小時至多一次 AV 額度，與 ADR-0009 已接受的上限相同。
  - 請求區間外的壞列仍會留著，等 F-9e 清理。
- **對 T-15 真偽的影響**：兩種做法下字面都屬實。分流的做法讓 T-15 不會一直常駐，也讓 ADR 壞處 5「直到運維清理」必須改寫（見 R-40）。
- **其他三條路徑**：
  - `get_cached_bars`：回 `UNAVAILABLE`，reason 是 T-15（畫面上看不到），rejection 為 `cache_unit_rejected`。
  - `_fall_back_to_cache`：回 `UNAVAILABLE`，reason 依 `_combine_reasons` 合併各層原因並加上 T-15。
- **可達性**：
  - 現況 5 個 adapter 都寫死市場幣別，快取 `currency` 欄是 NOT NULL；D-3 之後，不符的列也不會再寫進快取。
  - 所以壞列只可能來自舊資料、手動改庫，或 `MARKET_CURRENCY` 變動（ADR-0017 X3-F3）。
  - F-9a 盤點會統計數量。

#### 題 3：增量合併讀回被擋
- 用 T-15，不用 `MERGE_READBACK_FAILED_REASON`，因為事實是單位被拒，不是讀不回來。
- 處理方式：
  - 沿用 L192-202 的降級結構（不記 coverage，繼續往下一層），reason 加 T-15。
  - 之後各層一律整段請求。
  - 進 `_fall_back_to_cache` 時，因為已知快取被拒，不再讀快取，直接回 `UNAVAILABLE`；不這樣做，T-15 會被加兩次。
- 照題 2 的設計，layer 0 已經先擋住同一段範圍，所以這條路徑只剩另一個程序在兩次讀取之間寫入壞列的競態時才會發生。

#### 題 4：W-d 與 C-13
- T-15 加入 W-d 整組。
- C-13 原本 6 個情境，新增 4 個，共 10 個，`LoadedBars.reason` 一律用完全相等斷言：
  - (7) 冷卻期內 layer 0 被擋：reason 等於 T-15，provider 呼叫次數為 0。
  - (8) 不在冷卻期、梯子全部失敗、快取被擋：reason 等於「AV 原因句。 yfinance 原因句。 T-15。」，第一個 rung 收到的請求起點等於 `start`。
  - (9) W-c′ 加上快取被擋：reason 等於「W-c′。 T-15。」。
  - (10) W-c 加上壞快取：reason 不含 T-15，快取沒有被讀取。
- 合併讀回被擋時「T-15 只出現一次」另立一個測試，見 C-30。

#### creative-lead 不採 (e) 的理由是否成立
- **成立的部分（讀碼確認）**：
  - 美股梯子是 AV 在前、yfinance 在後（`deps.py` L102-107）。
  - 只有前一層拒答（result 為 None，`service.py` L175-180），才會輪到下一層。
  - F-9c 只讓 yfinance role 1 改讀上游宣告；AV 仍寫死 USD。所以美股的 W-c／W-c′ 只會來自 yfinance，而且每一列在同一次提問中，AV 一定先拒答過。
  - 台股三個來源都寫死 TWD，F-9 範圍內不會出現 W-c。
- **要修正的說法**：
  - AV 拒答不一定是「中斷」。可能是額度用完、網路問題（這兩種屬中斷），沒設 API key（設定問題），也可能是查無代號或資料深度不足。深度不足在 ADR-0009 D-7 下是長區間請求的常態；估值器只抓 10 天，不受影響。
  - 所以「典型情境就是 AV 中斷」說得太滿，應改成「至少在 AV 額度用完或網路中斷時」。
  - 「AV 恢復就能估值」在技術上屬實，但那時用的是 AV 寫死 USD 的價格，也就是殘留 R-a，並不表示估值正確。
- **真正決定性的理由**：成因句是整組共用的，必須對組內每一列都成立。這一組包含准入拒絕、W-c、W-c′、快取被拒（T-15）、冷卻期標記等來源；只要有一列是混合情境，(e) 就不成立。
  - 另外，若不採用我先前「被拒列不查匯率」的建議，這些列還可能同時缺匯率，那麼 (e) 的「非匯率中斷」也不成立。
- **附帶事實**：yfinance 會把代號中的 `.` 換成 `-`（`us_symbols.py` L132-139），像 `VOD.L` 這類帶點的外國代號，到了 yfinance 很可能是查無資料，而不是 W-c。這會影響 W-c 實際發生的頻率，但不影響上面的真偽判斷（待 F-9d 實證）。
- **結論**：主案或 alt-C 在讀碼上都站得住；alt-B 不建議。最後由風控裁示。

#### R-清單增修（交 tech-writer，接在 R-37 之後）

| # | 位置 | 修改 | 來源 |
|---|---|---|---|
| R-38 | D-7 新內文（R-22）中 `rejection` 的列舉 | 「（`symbol_not_admitted`｜`unit_mismatch`｜`unit_missing`｜None）」改為「（`symbol_not_admitted`｜`unit_mismatch`｜`unit_missing`｜`cache_unit_rejected`｜None；同一次回覆有多種時取 `unit_mismatch` ＞ `unit_missing` ＞ `cache_unit_rejected`；`cache_unit_rejected` 由快取閘門設定，永不寫入 attempt log）」；新 token 的涵蓋範圍加「快取舊列幣別不符或空白（T-15）」 | TA3 題 1 |
| R-39 | D-2 (5)（R-13 的 (5)） | 整項改為：「(5) 快取閘門：讀出的列任一根宣告值不符或空白，整條序列 fail-closed、不刪資料、`rejection=cache_unit_rejected`。(a) layer 0 在讀出整段快取後、所有分支之前檢查一次：若符合 ADR-0009 R-8 冷卻條件，回 `UNAVAILABLE`，reason 為 T-15，不打來源；否則回 None 走梯子，且本次停用增量（`fetch_start = start`；`_incremental_start` 本身不改，ADR-0019 K-10 相容）。(b) `_fall_back_to_cache`：回 `UNAVAILABLE`，reason 依 `_combine_reasons` 合併各層原因並加上 T-15。(c) `get_cached_bars`：回 `UNAVAILABLE`，reason 為 T-15。(d) 增量合併讀回被擋：reason 加 T-15，不用 `MERGE_READBACK_FAILED_REASON`；之後各層整段請求；`_fall_back_to_cache` 不再讀快取；T-15 至多出現一次。」 | TA3 題 2、3 |
| R-40 | Consequences 壞處 5（L156） | 「因 D-2 為 fail-closed，該代號的序列會被拒答，直到運維清理（F-9e）」改為「layer 0 讀到不符或空白的舊列時，冷卻期外改走梯子並整段重抓：來源能回答時，以通過閘門的新列覆寫請求區間內的舊列（自行修復）；來源失敗時回 `UNAVAILABLE` 並附 T-15，每個冷卻窗至多重跑一輪梯子（美股每窗至多一次 AV 額度）。請求區間外的舊列仍留存，直到 F-9e。」後句「未被准入規則涵蓋的舊列仍殘留」保留 | TA3 題 2 |
| R-41 | D-7 W-d 句（R-22） | 「W-a、W-b、W-c、W-c′、C、C′ 即完整 reason」改為「W-a、W-b、W-c、W-c′、C、C′、T-15 即完整 reason」；「准入拒絕或任一層為 W-c／W-c′ 時」改為「`rejection` 不為 None 時」 | TA3 題 4 |
| R-42 | 實作約束 C-13 | 「六種情境」改為十種，新增 (7)～(10)，內容照上方「題 4」 | TA3 題 4 |
| R-43 | 實作約束，新增 C-30～C-33 | C-30「合併讀回被擋時 T-15 只出現一次，且不出現 `MERGE_READBACK_FAILED_REASON`」；C-31「`cache_unit_rejected` 永不寫入 attempt log（測試快取被擋後 `rejection` 欄為 NULL）」；C-32「layer 0 被擋：冷卻期內 provider 呼叫 0 次；冷卻期外 provider 被呼叫，請求起點等於 `start`；來源成功後，同一請求下一次由 layer 0 服務」；C-33「W-c 加上壞快取時，reason 不含 T-15，且快取沒有被讀取」 | TA3 |
| R-44 | 失效條件 4（`MARKET_CURRENCY` 變動） | 句尾加「（變動後所有既有快取列都會被快取閘門拒收，每條序列每個冷卻窗各重抓一次；須連同重抓成本一併重審）」 | TA3 |
| R-45 | M-8（C-1）用語 | 「五條快取讀出路徑」改為「四條快取讀出路徑、六個出口」（layer 0 三個出口、`_fall_back_to_cache`、`get_cached_bars`、合併讀回）；「實作建議在 `_cached_result`（L446）與合併讀回兩處各設檢查點」改為「layer 0 在讀出整段快取後檢查一次（D-2 (5)(a)），`_fall_back_to_cache`、`get_cached_bars`、合併讀回各檢查一次」 | TA3，修正 M-8 |
| R-46 | 待決事項 T-15 | 狀態改為「creative-lead 已起草（第二批），待風控；涵蓋四條路徑；F-9b 合併前提；併入 W-d」 | TA3 |

來源標註：TA3 指本次 tech-architect 對 creative-lead 第二批四題的回覆（2026-10-12）。

## 驗證

- **讀過**：creative-lead 第二批提案全文、`ADR-0024-M1-M15-tech-architect核對.md` 的 M-5～M-11 段。
- **讀碼核對**：
  - `service.py`：L159-162（layer 0 回非 None 即結束）、L170、L175-180（只有前一層拒答才往下一層）、L186-203（合併讀回）、L239-242、L324（layer 0 讀出整段快取）、L366-385、L414-426、L438、L521-571；這些是本次評估中已讀過的內容。
  - `us_symbols.py` L132-139：`.` 換成 `-`，標示為 UNVERIFIED。
  - `deps.py` L102-107：AV 在前、yfinance 在後。
- **未做**：沒有執行測試、沒有連網、沒有改任何檔案；沒有讀 `.env` 或 `*.db`。
- **屬推論、尚未實證**：AV 拒答原因的分布、yfinance 對 `-L` 代號的實際反應（待 F-9d）、各類壞列的實際數量（待 F-9a 盤點）。

## 下一步

1. **coordinator**：把 R-38～R-46 併入既有的 R 清單交 tech-writer，和 M 清單一起一次套用（衝突以 R 清單為準；R-45 已直接修正 M-8）。同時把本回覆轉給 creative-lead。
2. **creative-lead**：T-15 主案不必改。第二批提案第九節的待確認 1～4 已由上面四題答覆，可原樣送風控。建議在 Q-1 的說明裡補上「AV 拒答不一定是中斷，但組內只要有一列是中斷，(e) 就不成立」這個說法。
3. **risk-compliance-officer**：審第二批字面時請一併知悉：T-15 會出現在 `_fall_back_to_cache` 的合併 reason 中，例如「AV 原因句。 yfinance 原因句。 T-15。」；冷卻期內 layer 0 被擋時，回覆只有 T-15、不含冷卻資訊。
4. **dev-lead**：F-9b 依 C-30～C-33 與 C-13 的 (7)～(10) 實作快取閘門。T-15 未核可前，用占位常數，不合併。