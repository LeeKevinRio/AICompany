# ADR-0028 r3′ 補正（依風控 R-1～R-3、S-1～S-5，tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0028 r3′ 補正（依風控單項確認 R-1～R-3、S-1～S-5）— tech-architect

這次只讀不寫：沒改任何檔案，沒跑程式、測試或 git，也沒讀 `.env` 或 `*.db`。

## 一、結論

**三項 required 全部採用。** 不採用的項目為 0，所以不必再送風控單項確認。**五項 suggested 也全部採用**，其中 S-5 改了寫法，結果比風控的建議更嚴。各條方向是收緊、揭露或中性編修，沒有任何一條放寬。依 R-2 改寫後的 CS-21，收緊不必再送風控。

- **R-1 採用。** 判斷是否定案的時間，改成 `min(as_of, fetched_at)`，SE-2 和 R3 共用。定案判準集中在 CS-17 的一個函式 `is_final` 裡。
  - 查證的程式事實：
    - 日線轉接器在呼叫開始、還沒發請求時就蓋了 `as_of`（`providers/twse.py:88` 是 `now = datetime.now(UTC)`；其他轉接器 grep 結果相同）。
    - `fetched_at` 是 provider 回傳之後才讀的服務時鐘（`service.py:352-353`）。
    - upsert 會一起覆寫這兩欄（`cache.py:207-208, 227-228`）。
  - 所以取兩者中較早的值，不需要改 DDL。
- **R3 另外有一個更大的洞，這次一併補上（推論）。** R3 的 `acquired_at` 是序列層的 `ProviderResult.as_of`，走快取路徑時等於 `tail_fetched_at`（ADR-0019 D-4、D-5）。
  - 情境：14:00 某一級（例如備援來源）寫進 D 日的暫定列；16:00 另一級完整抓取成功，但回傳結果沒有 D 日 bar。這時 `tail_fetched_at` 會推進到 16:00，D 日那一列卻沒有被覆寫。
  - 照 r3 的寫法，R3 會判成 `close`，把暫定值當成定案收盤。
  - R3 改取 `min(acquired_at, 當日 bar 的 PriceBar.as_of)` 之後，這個情境會落到 R3′（`provisional_today`）。
  - 當日 bar 在估值器裡是現成的 `PriceBar`（`portfolio/valuation.py:495` 的 `latest`；快取讀回時會還原 `as_of`，見 `cache.py:582-596`），不需要多讀資料。
- **R-2 採用。** CS-21 改成通則。風控列的 7 類全部寫入，我另外補了 4 類（R-1、S-1、S-5 帶出來的反向改動）。
- **R-3 採用。** A-48 (b) 加上三項回報最低內容。美股的週末另外列出，但不當作翻轉條件。
- **順帶修正 r3 本身的一個遺漏。** r3 的 A-46 第 8 點改寫了 D-4 的 R3 條件，A-53 卻沒有把 R3 原文列進「逐字保留」。A-53′ 已補上。
- R-4（ADR-0027 的暫定大盤 bar）照指示不在本報告處理。

## 二、補正條文（給 tech-writer：套用 r3 時一起套用；「整句取代」「新增」都以 r3 提案的文字為基準）

**A-42′｜文首**
- 「r3 修訂」那一行改成：
  `- r3 修訂：2026-10-17，依 tech-architect 修訂提案 A-42～A-53（附件 B'-3：觀察交易日集合的輸入來源），含 r3′ 補正（風控 r3 單項確認 R-1～R-3、S-1～S-5）`
- 「與既有 ADR 的關係」中 **ADR-0019** 那一點，整點取代成：
  - **ADR-0019**：D-9 讀列層的 `as_of` 與 `fetched_at`，R3 另外讀當日 bar 的 `PriceBar.as_of`。這些時間都只用來判斷「是否定案」，一律取較早者（CS-17）。它們不是序列的取得時間，不取代 `acquired_at`（ADR-0019 D-5），也不得顯示（K-13）。K-9 不受影響。

**A-43′｜Context「觀察日曆現況」新增兩點**
- 每列另有 `as_of`。它是日線轉接器在呼叫開始、送出請求之前讀的時鐘〔事實：`app/data/cache.py:50、207、227`；`app/data/providers/twse.py:88`〕。`fetched_at` 則是 provider 回傳之後才讀的服務時鐘〔事實：`app/data/service.py:352-353`〕。所以一次跨越 VS-4 的抓取，`fetched_at` 會晚於資料實際被取得的時間。
- R3 的 `acquired_at` 是序列層的 `ProviderResult.as_of`，走快取路徑時是 `tail_fetched_at`〔事實：ADR-0019 D-4、D-5〕。如果後來那次完整抓取沒有回傳當日 bar，當日那一列不會被覆寫，`acquired_at` 就會晚於該列實際寫入的時間〔推論〕。

**A-46′｜D-9**
- **第 1 點**：`market_session_evidence` 回傳的欄位改成 `(symbol, trade_date, open, high, low, close, volume, source, as_of, fetched_at)`。
- **SE-2，整條取代**：
  - **SE-2**（r3′）：`is_final(market, trade_date, as_of, fetched_at)` 成立，也就是 `final_after(market, trade_date) ≤ min(as_of, fetched_at)`；另外要 `max(as_of, fetched_at) ≤ now`。
    - `final_after` ＝ `trade_date` 當地日期的 VS-4（引用 `policy_for(market).publish_cutoff`），時區用 VS-1。
- **SE-5，整條取代**：
  - **SE-5**（r3′）：symbol 不在 `INDEX_SERIES_SYMBOLS` 內，**而且**不以 `^` 開頭。
    - `INDEX_SERIES_SYMBOLS` 是指數登記集合的鍵（現為 `app/data/providers/yfinance.py:122-126` 的 `INDEX_SYMBOL_METADATA`），定義見 CS-25。
    - 兩個條件是聯集排除（fail-closed）。只改用登記集合、拿掉 `^` 判定，會讓不在登記內的 `^` 代號重新成為證據，那是放寬。
- **SE-6，整條取代**：
  - **SE-6**（r3′）：`as_of` 與 `fetched_at` 都能解析，而且都帶時區。任一不符，該列就不算證據。
- **SE-6 之後新增一段**：
  - **「通過品質檢查」的範圍**（r3′）：`check_price_bars` 的五類檢查（`app/data/quality.py:41-63`）對日曆證據的對應如下：
    - OHLC_INVALID 由 SE-3 涵蓋；
    - FUTURE_DATE 由 SE-2 涵蓋（`final_after(trade_date) ≤ now`）；
    - DUPLICATE_ROW 因為 PK `(symbol, market, trade_date)`〔事實：`cache.py:52`〕，結構上不會發生；
    - MISSING_TRADING_DAY（跨列）與 CURRENCY_MISMATCH 和「那天有沒有開市」無關，不適用。
    - 本 ADR 說的「通過品質檢查」只指以上範圍。
- **第 4 點，整點取代**：
  - **confirmed**：見第 3 點；
  - **unconfirmed**（r3′）：那天在 `[start, end]` 內至少有一列（任何 source，**包括示範資料**），但沒達到 confirmed；
  - **absent**：那天沒有任何列。
- **第 8 點，整點取代**：
  - **和 R3 同一個判準**（r3′）：D-4 的 R3 條件改成「交易日、`price_date == D`，而且 `is_final(market, D, acquired_at, bar_as_of)`」。
    - `bar_as_of` 是 `price_date == D` 那根 bar 的 `PriceBar.as_of`。
    - `acquired_at` 或 `bar_as_of` 任一為 None，就不成立，落到 R3′。
    - R3 和 SE-2 呼叫同一個 `is_final`（CS-17）。
  - D-2 末尾同時新增一點：「`bar_as_of`（當日 bar 的 `PriceBar.as_of`）比照 `acquired_at`，以不序列化的內部欄位傳遞；只用於 R3，不得顯示（ADR-0019 K-13）。」

**A-47′｜R2‴ 那一列的「狀態」欄，括號內文字整句取代**
- 新文：「（列的日期落在日曆不認為是交易日的日子，例如週末，或 official basis 下的官方休市日）」
- 理由：採用 S-1 後，只有示範列的平日改走週一至週五規則，非 official 模式下不會再落進 R2‴。

**A-48′｜D-5 表後三點**
- **第一點新文的第二子點，整句取代**：
  - 「D-9 實作之後，SE-2 要求 `min(as_of, fetched_at) ≥ final_after(D)`、`max(as_of, fetched_at) ≤ now`，而 R4b 要求 now < VS-3 < VS-4，所以只有時鐘或參數出錯時才可能出現。」
- **第一點第三子點之後新增**：
  - 「不得以『照建構走不到』為由，刪除或降級這一列的對應、WARNING 或 CS-11 的窮舉（含 CST-7 的性質測試）。」
- **第二點 (b) 的回報最低內容，在「SE-4、SE-5 的確認」之後新增三項**：
  - (i) §6.4 的試算必須用已合併版本的 `PriceBarCache.market_session_evidence` 讀唯讀複本，再交給已合併版本的 `classify_session_evidence` 分類。不得另寫 SQL，也不得重寫判準。回報要附所用 commit SHA 與呼叫方式。
  - (ii) 列出樣本期（§6.4 唯讀複本涵蓋的全部日期）內被判成 confirmed、但其實是週末（依 VS-1 的當地日期）或 TWSE 官方休市日的台股日子。休市表要註明官方出處與查證日期。**台股這個數字必須為 0，否則不得翻轉。** 美股同時列出被判成 confirmed 的週末，應為 0；不為 0 時列入回報，但不屬於 R4c 翻轉條件。
  - (iii) §6.3 判讀矩陣 F-7 那一欄的結果：逐來源、逐輪列出「VS-4 之後的當日 bar 是否已定案」。任何一格為否，F-7 即觸發，不得翻轉。

**A-49′｜D-6**
- **第 10 點，整點取代**：
  - 10.（r3′）`check_price_bars` 只在讀取側用於日曆證據，不擋寫入；寫入側的品質閘門另案處理。「通過品質檢查」的範圍見 D-9 第 2 點。
- **新增第 11、12 點**：
  - 11.（r3′）R 內完全沒有任何列（包括示範列）的平日，會判為休市（observed）。P 會跳過那一天，`lag_sessions` 可能少算。現行 `market_trading_days` 口徑也一樣，不是退步。
  - 12.（r3′）`as_of` 是轉接器在呼叫開始時讀的時鐘。跨月份的抓取，`as_of` 早於實際取得當月資料的時間，所以 15:00 前開始、15:00 後才回來的抓取一律不算證據。方向保守。日線轉接器目前讀的是行內 `datetime.now(UTC)`，不是注入的時鐘，所以測試 fixture 要明確指定 `as_of`，不得依賴轉接器自己蓋的章。

**A-50′｜對實作的約束**
- **CS-17，整條取代**：
  - **CS-17**（r3′）：`final_after(market, trade_date)` 與 `is_final(market, trade_date, *stamps)` 各只有一個定義，都放在 `session_calendar.py`，引用 VS-1、VS-4。
    - `is_final` 的語意：stamps 至少一個，全部不為 None 而且帶時區，並且 `final_after ≤ min(stamps)`。不符合就回 False。
    - SE-2 呼叫 `is_final(m, d, as_of, fetched_at)`，R3 呼叫 `is_final(m, D, acquired_at, bar_as_of)`。
    - 其他模組不得出現 `publish_cutoff` 與 `trade_date`、`acquired_at`、`as_of`、`fetched_at` 的行內比較。`final_after(` 只能在 `is_final` 內被呼叫（grep）。
- **CS-21，整條取代**：
  - **CS-21**（r3′）：`NON_EVIDENCE_SOURCES`、`SESSION_EVIDENCE_MIN_SERIES`、SE-5 的判定式各只定義一次。測試斷言 `NON_EVIDENCE_SOURCES ⊇ {app.demo.series.DEMO_SOURCE}`。
  - **通則**：任何會讓更多列成為證據，或讓更多日子成為 confirmed 或 basis＝observed 的改動，合併前都要先經風控單項確認。下列只是舉例，不是窮舉：
    1. 降低 `SESSION_EVIDENCE_MIN_SERIES`；
    2. 從 `NON_EVIDENCE_SOURCES` 移除來源；
    3. 納入指數，或縮小 SE-5 的排除範圍（包括從 `INDEX_SERIES_SYMBOLS` 移除代號、拿掉 `^` 判定）；
    4. 放寬或移除 SE-2、SE-3、SE-4、SE-6；
    5. 讓 `final_after` 提早（包括改 VS-4，或改成 (market, source) 鍵後某來源提早）；
    6. 改動三態表，讓 unconfirmed 或 R 外的日子變成 observed；
    7. 新增 CS-20 寫入者；
    8. 把 `is_final` 從「取較早者」改成取較晚者或單一時鐘（包括 SE-2 只看 `fetched_at`、R3 只看 `acquired_at`）；
    9. 改動 unconfirmed 與 absent 的界線，讓更多日子落到 R 內 absent（例如讓只有示範列的日子回到 absent）；
    10. 讓 R 擴大（R 的定義不再是 confirmed 的區間）；
    11. 替換或增加 `ObservedSessionCalendar` 的輸入來源（D-9 第 7 點列為不採用的輸入）。
  - 往收緊方向改不必送風控。方向判斷不了的，一律視為放寬。
  - 這幾個常數與 `is_final` 的註解都要寫明這條通則。
- **新增 CS-25**：
  - **CS-25**（r3′）：SE-5 的指數登記集合只有一個定義。
    - D-9 的實作 PR 要把 `INDEX_SYMBOL_METADATA` 搬到不依賴 HTTP 的純常數模組（暫定 `app/data/index_registry.py`，名稱 dev-lead 可以改）。`app/data/providers/yfinance.py` 改成 import 它，不得留兩份。
    - `session_calendar.py` 不得 import `app.data.providers.*`（import graph）。
    - 測試要斷言兩件事：`app.services.index.MARKET_BENCHMARK` 的每個 `series_symbol`，以及 `app.leverage.index_mapping` 中所有非 None 的 `series_symbol`，都屬於 `INDEX_SERIES_SYMBOLS`；CS-1 的 import graph 測試維持綠燈。

**A-51′｜測試要求**
- **CST-5 新增 fixture**：
  - **R-1**：`as_of` 14:59:58+08:00、`fetched_at` 15:00:01+08:00，這一列不算證據。反向的 `as_of` 15:00:01、`fetched_at` 14:59:58 也不算。
  - TW、US 的邊界 fixture，`as_of` 與 `fetched_at` 都設成同一個邊界值。
  - `as_of > now`，不算證據。
  - `as_of` 沒有時區，不算證據（SE-6）。
  - `trade_date` 晚於 now 的當地日期，不算證據（S-3：FUTURE_DATE 由 SE-2 涵蓋）。
  - 「10:30 寫入、16:00 被 upsert 覆寫」這一例，覆寫後 `as_of`、`fetched_at` 兩欄都要 ≥ 15:00 才算證據。
  - **S-5**：`INDEX_SERIES_SYMBOLS` 內的代號不算證據；不在登記集合內、但以 `^` 開頭的代號也不算證據。
- **CST-6 新增**：
  - 只有示範列的平日：unconfirmed，`is_session` 為 True，basis 是 weekday_assumed；
  - 只有示範列的週六：unconfirmed，`is_session` 為 False，basis 是 weekday_assumed；
  - R 內完全沒有列的平日：absent，False，observed（D-6 第 11 點）。
- **CST-7 的 R4c 子點，整句取代**：「R4c × observed：台股 15:00:00 時，有兩個序列的證據列，而且 `as_of`、`fetched_at` 都 ≥ 15:00:00+08:00，就成立。」R4b 子點的前提改成「`max(as_of, fetched_at) ≤ now`，而且 CS-24 成立」。
- **新增 CST-9**（r3′，R3 同口徑）：
  - `acquired_at` 15:00:01+08:00、`bar_as_of` 14:59:58+08:00：R3′（`provisional_today`）；
  - `acquired_at` 16:00+08:00、`bar_as_of` 14:00+08:00（快取路徑，當日列沒有被後來的抓取覆寫）：R3′；
  - 兩者都是 15:00:00+08:00：R3（`close`）；
  - `acquired_at` 或 `bar_as_of` 為 None：R3′；
  - grep：`close_state.py` 不出現 `publish_cutoff`。

**A-52′｜失效條件、待決事項、未查證事項**
- **未查證事項**：原本的「SE-5 以 `^` 開頭判定指數〔推論〕」，整項取代成：
  - 「快取中是否有指數序列既不在 `INDEX_SERIES_SYMBOLS`、也不以 `^` 開頭〔未查證，待 data-engineer〕」
- **未查證事項新增**：
  - 「所有日線轉接器都在送出請求前蓋 `as_of`〔已查 `twse.py:88`，其餘轉接器只 grep 了 `now = datetime.now(UTC)` 的位置，推論〕」
  - 「快取路徑下 `acquired_at` 晚於當日列寫入時間的情境〔推論，CST-9 釘住〕」
- **待決事項，data-engineer 新增**：
  - (f) 確認所有寫入 `price_bars_cache` 的轉接器，`PriceBar.as_of` 都不晚於第一個請求送出的時間；
  - (g) A-48 (b) (i)～(iii) 的回報內容。

**A-53′｜修訂紀錄**
- r3 區塊的那一句改成：「r3（2026-10-17）依 tech-architect 修訂提案 A-42～A-53（附件 B'-3），含 r3′ 補正（風控 r3 單項確認 R-1～R-3、S-1～S-5）套用。」
- 逐字保留的原文，除了 r3 原本列的三項，**再補一項**：D-4 R3 的原條件「交易日、`price_date == D`，而且 `acquired_at ≥ D 的 VS-4`」（被 A-46′ 第 8 點取代）。
- r3′ 修改的是 r3 還沒落檔的提案文字，不是已落檔的條文，所以不另外保留 r3 提案原文。

## 三、suggested 採用表

| 項 | 採用 | 寫入位置 | 方向 | 說明 |
|---|---|---|---|---|
| S-1 只有示範列的日子歸 unconfirmed | 採用 | A-46′ 第 4 點、A-47′、CST-6 | 收緊（observed 變少） | R 不變；R 內 absent 只剩完全沒有列的日子 |
| S-2 R 內完全沒有列的平日 `lag_sessions` 可能少算 | 採用 | A-49′ 第 11 點、CST-6 | 揭露 | 配合 S-1，改成「完全沒有任何列（包括示範列）」 |
| S-3 「通過品質檢查」的範圍 | 採用 | A-46′（SE-6 之後）、A-49′ 第 10 點、CST-5 | 揭露，並加測試（收緊） | 照風控二-(a) 的四類寫入 |
| S-4 不得以「走不到」刪除或降級 | 採用 | A-48′ 第一點 | 收緊 | 範圍擴到 CST-7 的性質測試 |
| S-5 改用指數登記集合 | 採用（修改） | A-46′ SE-5、CS-21 第 3 類、CS-25、CST-5 | 收緊（比建議更嚴） | 登記集合與 `^` 前綴聯集排除，不是只換成登記集合，因為只換會放寬 r3。另外要求登記搬到純常數模組，避免 `session_calendar.py` 依賴 HTTP 轉接器（`yfinance.py:98-100` import 了 `httpx` 與 `RateLimitedClient`） |

## 四、方向統計（本次 r3′ 共 27 處改動）

| 方向 | 數量 | 條目 |
|---|---|---|
| 收緊 | 15 | SE-2（R-1）、SE-5（S-5）、SE-6、D-9 第 4 點（S-1）、D-9 第 8 點＋D-2（R-1，含快取路徑的洞）、A-48′ 第一點（min＋S-4）、A-48′ (b) (i)～(iii)（R-3）、CS-17、CS-21（R-2）、CS-25、CST-5、CST-6、CST-7、CST-9、待決事項 data-engineer (f)(g) |
| 揭露 | 7 | A-42′ ADR-0019 點、A-43′ 兩點、D-9 品質檢查範圍（S-3）、D-6 第 10、11、12 點 |
| 中性（編修、紀錄） | 5 | A-42′ r3 行、D-9 第 1 點欄位（R-1 的前提）、A-47′ R2‴ 括號、A-52′ 未查證事項、A-53′ 修訂紀錄（含補上 R3 原文） |
| 放寬 | **0** | — |

需要你轉知的事：
- **給 coordinator**：機械核對 R-1、R-2、R-3 時，請一併核對三處：A-53′ 補上的 R3 原文、CST-9、CS-25。
- **要知會風控**：R-1 的 R3 端除了風控指出的 14:59:58 邊界，還補了「快取路徑的 `acquired_at` 晚於當日列寫入時間」這個情境（推論，CST-9 釘住）。這是收緊，不需要確認。
- **給 data-engineer**：風控建議的「§6.4 統計 volume 為 0 的占位列數量，以及它們被當成 `price_date` 的次數」，我沒有寫進 ADR 條文，因為那是給 data-engineer 的 suggested。建議 data-engineer 放進同一份回報。

**驗證範圍**：
- 讀過：
  - 風控 r3 單項確認全文、r3 提案全文；
  - ADR-0028 L60-149、L186-225；ADR-0019 D-2～D-5（L84-108），並 grep 了 K-11、K-13、L280；
  - T1 評估中 `acquired_at` 的定義（grep L236、L249、L273）；
  - 程式：`cache.py:30-59、195-231`、`service.py:320-369`、`interface.py:40-79、645-664`、`providers/twse.py:70-154`、`yfinance.py:90-131`、`portfolio/valuation.py:490-514`；
  - grep：`as_of`（app/data、demo）、`now = `（providers）、指數代號登記（app）。
- 沒有跑任何程式或測試。其餘轉接器蓋 `as_of` 的時點只 grep 了位置，屬於推論。

**相關檔案**
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028修訂提案r3觀察日來源-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md（L77-81、L103-116、L186-220）
- /home/user/AICompany/docs/adr/0019-stock-desk-日線-coverage-判定與取得時間單一基準.md（L84-108）
- /home/user/AICompany/work/reviews/2026-10-16-T1-01與T1-02-tech-architect評估.md（L236、L273）
- /home/user/AICompany/apps/stock-desk/backend/app/data/cache.py（L50、L195-231、L582-596）
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py（L352-353）
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse.py（L88）
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py（L98-101、L122-126）
- /home/user/AICompany/apps/stock-desk/backend/app/services/index.py（L302-305）
- /home/user/AICompany/apps/stock-desk/backend/app/leverage/index_mapping.py（series_symbol 各處）
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py（L495-511）
