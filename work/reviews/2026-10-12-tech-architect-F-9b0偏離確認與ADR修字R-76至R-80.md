<!-- tech-architect 唯讀回報原文（TA7）；coordinator 轉存，2026-10-12 -->

# tech-architect 回報（TA7）：F-9b0 兩處偏離的確認與 ADR 修字（R-76～R-80）

全程唯讀。沒有讀 `.env` 或任何 `*.db`，沒有改檔，沒有執行測試，也沒有做 git 操作。

## 本次結論

1. **偏離 1（不變式只做單向）：dev-lead 是對的，R-48 的「⇔」是我寫錯的。**
   - 反方向「`UNAVAILABLE` 且 `bars=[]` ⇒ `rejection` 不為 None」不成立。一般失敗、`COOLDOWN_NO_CACHE_REASON` 這兩種回覆都是 `UNAVAILABLE`、`bars=[]`、`rejection=None`（D-2 (5)(a) 第 5 步，TA5 R-57）；D-7 (7) 三分流的 (iii) 也預設這種回覆存在。照「⇔」實作的話，validator 會拒絕這兩種既有回覆。
   - F-9b0 的 validator（`interface.py` L158-169）和測試（`test_f9b0_rejection.py`，含「逆命題不成立」的正向測試）都符合正確語意，**不用改程式**。
   - dev-lead 提議的「等價地，任何帶 bars 的回覆 `rejection` 必為 None」只對了一半。「⇒」的對偶命題是「帶 bars **或** 狀態不是 `UNAVAILABLE` → `rejection` 為 None」。實作與測試（`backup-without-bars` 那組）已經涵蓋，正式字句以 R-76 為準。
   - C-34 (a) 要同步加一句，把「逆命題不成立」改成可勾核的測試項（R-77）。

2. **偏離 2（市場查不到幣別時的記錄格式）：F-9b0 的做法追認；F-9b 的處置改寫 M-5。**
   - **F-9b0 追認**：記成 `expected=<none> verdict=mismatch mismatched=<n>/<n>`、bars 為空時不記，這樣可以接受。理由有三：
     - R-60 規定 `verdict` 只能是 `mismatch` 或 `missing`；
     - 查不到預期幣別時，沒有任何一根能確認相符，依 D-2 (1)「不符優先於空白」記為 `mismatch`，與 R-60 的優先序一致；
     - `<none>` 與 `<blank>` 分得開，也能 grep。
     F-9b0 不用改。
   - **F-9b 改寫 M-5**：原句「回 `UNAVAILABLE`」**不採用**。理由：這個情境是組態錯誤，不是資料事件，而目前沒有任何已核可、又描述屬實的字面可以用：
     - 回 W-c（`unit_mismatch`），等於宣稱「來源宣告幣別與市場不符」，不實，F-9b2 還會寫入 W-c 標記；
     - 回 `rejection=None`，會接 `NO_BARS_REASON` 並產生 `price` token，宣稱「查無資料」，正是 F9W-11 否決的語意。
   - **M-5 的改法**（R-78、R-79）：
     - 由 CI 測試確認 `MARKET_CURRENCY` 涵蓋 `Market` 的每個值；
     - F-9b 起，`MarketDataService` 建構時逐一查表，查不到就 raise；
     - 執行期若仍查不到（只有查表函式本身會變動結果時才可能發生），在該檢查點 raise，不轉成 `UNAVAILABLE`，也不帶任何 `rejection` 或使用者面字面。
     - 結果仍是 fail-closed（不出價格），只是改在建構期與 CI 擋下。

3. **對 T-10 的影響：建議 R-76～R-80 在 CEO 核可前一次落字，但不必重送 T-10 的實質審查。**
   - 若照現行字面核可，accepted ADR 的 D-7 (2)「⇔」會與 D-2 (5)(a) 第 5 步、D-7 (7) (iii) 自相矛盾，也與已實作的 F-9b0 衝突。依章程「與 accepted ADR 衝突時以 ADR 為準」，F-9b0 反而會變成違規。M-5 若照原句核可，F-9b 依 R-78 實作時也會違反 accepted ADR。
   - 兩處修正都不新增、不改動任何使用者面字面，也不改變 CEO 須知悉的事項，因此不需重開風控審查，也不需在 T-10 加列知悉項。R-78 送風控知悉即可（不需裁示）。

## 各部門回報

### tech-architect

**讀碼核對（worktree `/home/user/AICompany/.claude/worktrees/agent-af8fe673a54e77432`）**

- `apps/stock-desk/backend/app/data/interface.py`
  - L28 `Rejection` 四個值與 D-7 (2) 一致。
  - L158-169 validator 只檢查「`rejection` 不為 None ⇒ `UNAVAILABLE` 且無 bars」，docstring 已註明逆命題不成立並引用 R-57。
- `apps/stock-desk/backend/app/data/service.py`
  - L37-52 定義前綴、`<blank>`、`<none>` 常數，以及 `ServiceScope`、`CurrencyLookup`；
  - L202-221 建構子：`currency_for_market`、`scope` 為 keyword-only 必填、沒有預設值，`scope` 值不合法就 raise；
  - L369-411 記錄函式：空 bars 直接 return；查不到幣別時 `verdict="mismatch"`、`mismatched=len(bars)`；ERROR 或 WARNING 依 `scope` 決定；
  - L630-647 `_try_provider` 的 `except Exception` 只包住 `provider.get_daily_bars`，閘門若放在其後，raise 會正常向外傳出（R-79 (c) 的前提）。
- `apps/stock-desk/backend/app/api/deps.py`
  - L72-80 `_market_currency` 回傳 `MARKET_CURRENCY.get(market)`，會產生 None；
  - L117-168 三個建構點都顯式傳入查表與 `scope`。
- `app/positions/models.py` L67：`MARKET_CURRENCY = {"TW": "TWD", "US": "USD"}`，目前涵蓋 `Market` 的兩個值，所以 R-79 (b) 在正式設定下不會改變行為。
- 測試：
  - `tests/test_f9b0_rejection.py` L70-110：四種違反組合、非 `UNAVAILABLE` 全組合、`rejection=None` 全組合可建構；
  - `tests/test_f9a_service_currency_warning.py` L342-359：查表回 None 的情境矩陣；
  - `tests/test_api_deps.py` L147-153：查表參數化用的是 `sorted(MARKET_CURRENCY)`，**不是 `get_args(Market)`**。這表示「`Market` 擴充了但沒補表」目前沒有測試會轉紅，R-79 (a) 補的就是這個缺口。

**方案比較（偏離 2，F-9b 的處置）**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A：當成 W-c（`unit_mismatch`） | 沿用既有分流 | W-c 字面「來源幣別與市場不符」不實；F-9b2 會寫入 W-c 標記，冷卻期內再顯示 C 版 | 高：等於未經審查地套用字面。否決 |
| B：`UNAVAILABLE`、`rejection=None`（照 M-5 字面） | 不用新增 rejection 值 | 會接 `NO_BARS_REASON`、產生 `price` token（「查無價格資料」），是 F9W-11 否決的語意 | 中：屬於未審過的字面用法。否決 |
| C：新增 rejection 值，另起字面 | 語意精確 | 要新增字面並送審，只為了一個正式設定下不可達的狀態 | 成本與收益不成比例。否決 |
| **D：CI 測試＋建構期 raise＋執行期 raise（採用）** | 不需要任何字面；組態錯誤在 CI 和首次建構時就會暴露；仍然 fail-closed | 若真的發生，使用者看到的是通用錯誤，而不是降級說明；F-9b0 的一個測試在 F-9b 要改寫 | 低：正式設定下不可達，CI 先擋 |

**ADR 修改清單（交 tech-writer；〔TA7〕指本回覆）**

**R-76〔D-7 (2) 不變式〕**

把「**不變式**：`rejection` 不為 None ⇔ 該回覆為 `UNAVAILABLE` 且 `bars=[]`，以 `ProviderResult` 的 model validator 強制，違反即 raise。任何帶 bars 的回覆一律 `rejection=None`，包括：」改為：

> **不變式（單向）**：`rejection` 不為 None ⇒ 該回覆為 `UNAVAILABLE` 且 `bars=[]`，以 `ProviderResult` 的 model validator 強制，違反即 raise。逆命題不成立：一般失敗（各層皆失敗），以及 ADR-0009 D-8 冷卻期無快取時回 `COOLDOWN_NO_CACHE_REASON`（D-2 (5)(a) 第 5 步），同樣是 `UNAVAILABLE`、`bars=[]`，但 `rejection=None`；validator 不得拒絕這種組合，`load_bars` 也靠它進入 D-7 (7) 三分流的 (iii)。依對偶，凡是帶 bars 或狀態不是 `UNAVAILABLE` 的回覆，`rejection` 必為 None。帶 bars 的情形包括：〔TA4 R-48；TA7 R-76 更正 R-48 的「⇔」〕

其後「W-c′ 加上通過閘門的快取而回快取、T-17、……不帶到帶 bars 的回覆上。」原樣保留。

**R-77〔C-34 (a)〕**

「(a) 違反 D-7 (2) 不變式時 `ProviderResult` 建構即 raise；」改為：

> (a) 違反 D-7 (2) 不變式（單向）時 `ProviderResult` 建構即 raise，涵蓋「`UNAVAILABLE` 帶 bars」以及「非 `UNAVAILABLE` 狀態不論有無 bars」；另以測試釘住逆命題不成立：`rejection=None` 時每一種狀態、有無 bars 皆可建構，其中包括 `UNAVAILABLE`、`bars=[]`。〔TA4 R-48；TA7 R-77〕

**R-78〔D-4 末點 M-5；D-5 新增一點〕**

- D-4 末點的「market 查不到預期幣別時 fail-closed（回 `UNAVAILABLE`）。〔TA1 M-5〕」改為：

> market 查不到預期幣別屬組態錯誤，不是資料事件，fail-closed 改在建構期與 CI 處理（D-5、C-35）：F-9b 起，`MarketDataService` 建構時對 `Market` 的每個值呼叫注入的查表，回 None 或空白即 raise；執行期若查表仍回 None（只有查表函式本身會變動結果時才可能發生），在該檢查點 raise，不轉成 `UNAVAILABLE`，不帶任何 `rejection` 或使用者面字面；raise 前不寫快取、不 `record_fetch`。理由：這個情境沒有屬實的已核可字面。W-c 會宣稱來源幣別與市場不符；`NO_BARS_REASON` 加上 `price` token 會宣稱查無資料（F9W-11）。F-9b0 觀察模式下照常記錄，格式為 `expected=<none> verdict=mismatch mismatched=<n>/<n>`，`verdict` 依 D-2 (1)「不符優先於空白」取 `mismatch`；bars 為空時不記。〔TA1 M-5；TA7 R-78 取代 M-5 的「回 `UNAVAILABLE`」；送風控知悉〕

- D-5 末尾新增一點：

> 查表必須涵蓋 `Market` 的每個值：以測試釘住 `set(get_args(Market)) <= set(MARKET_CURRENCY)` 且各值非空白。擴充 `Market` 而沒有補表時，測試轉紅，並適用失效條件 4。〔TA7 R-78〕

**R-79〔實作約束新增 C-35；表頭；PR 表 F-9b 列〕**

- 新增一列：

> | C-35（F-9b；(a) 可提前放入 F-9b0） | (a) 測試 `set(get_args(Market)) <= set(MARKET_CURRENCY)`，且每個值為非空白字串。(b) `MarketDataService` 建構時對 `get_args(Market)` 每個值呼叫注入的查表，回 None 或空白即 raise `ValueError`；「查表回 None」「查表回 `""`」各一測。(c) 執行期查表回 None 時在該檢查點 raise：例外不得被 `_try_provider` 的 provider 例外防護吞掉，不得轉成 `UNAVAILABLE`；用「建構時有值、之後回 None」的查表，在 live 檢查點與 layer 0 各一測，斷言例外向外傳出、快取未寫入、`record_fetch` 未呼叫。(d) F-9b0 的 `test_a_market_without_a_currency_counts_as_mismatch_and_changes_nothing` 在 F-9b 改寫為 (b)(c)，並依 TA5 共同門檻在 PR 說明列出測試名稱。(b) 與 live 檢查點的 (c) 屬 commit 5，layer 0 的 (c) 屬 commit 6。〔TA7 R-79〕 |

- 實作約束小節標題「C-34 為 TA4 R-48 增列」後加「；C-35 為 TA7 R-79 增列」。
- PR 表 F-9b 列「內容」欄的末句（「…不在本 PR 範圍。〔TA6 R-71〕」）之前加：「查表全稱檢查與組態錯誤 raise（C-35；取代 M-5 的『回 `UNAVAILABLE`』）；」。

**R-80〔實作進度補記、檔頭、佐證〕**

- 實作進度補記加一點：

> F-9b0 對「查表查不到該市場幣別」照常記錄 `expected=<none> verdict=mismatch mismatched=<n>/<n>`，bars 為空時不記；不變式依 R-76 只做單向。兩者皆經 TA7 追認。〔TA7 R-76、R-78〕

- 檔頭來源清單加第七次回覆（TA7，檔名由 coordinator 定），優先序改為 TA7 ＞ TA6 ＞ TA5 ＞ TA4 ＞ TA3 ＞ TA2 ＞ TA1。TA4 回報檔 L14、L72 裡的「⇔」是歷史紀錄，**不要改原檔**，以本優先序為準。
- 佐證清單加一列：「TA7 套用：D-7 (2) 不變式 R-76；C-34 (a) R-77；D-4 末點與 D-5 R-78；C-35、PR 表 R-79；補記與檔頭 R-80」。

**對實作的約束（逐條可檢查）**

- F-9b0：偏離 1、2 **都不用改程式**。C-35 (a) 可選擇提前放入 F-9b0，不阻擋合併。
- F-9b：依 C-35 實作。閘門的查表必須放在 `_try_provider` 的 `try` 區塊之外、`cache.put` 之前（D-2 (1)、TA1 M-7）。
- 任何 F-9b 程式都不得為了「查不到幣別」產生 `rejection`，也不得接任何使用者面字面。

### 給其他部門（經 coordinator 轉達）

- **tech-writer**：在 T-10 之前一次套用 R-76～R-80。
- **qa-reviewer**：審 F-9b0 時以 R-76 為準：validator 只做單向是正確的，不要以 ADR 現行的「⇔」字面判 BLOCKING。查不到幣別的記錄格式依 R-78 追認。
- **dev-lead**：F-9b0 維持現狀。F-9b 依 C-35 實作；commit 5 改寫 F-9a／F-9b0 那個「查不到幣別」測試時，PR 說明要列出測試名稱。
- **risk-compliance-officer**：R-78 知悉即可，不需裁示。這項修正移除了一個原本需要使用者面字面的狀態，沒有新增、也沒有改動任何字面。
- **CEO**：T-10 不新增知悉事項。

## 驗證

**讀過的文件**
- `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`：D-1、D-2、D-4、D-5、D-7、C-1～C-9、C-34、檔頭 T-10、各章節索引；
- `/home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024抽驗與待確認項裁決R-47至R-56.md`（R-48 原文 L68-86）；
- `/home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024第三次抽驗與F-9b切分R-57至R-69.md`（全文）；
- `/home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024第四次抽驗R-70至R-75.md`（R-70、R-71），確認上次編號止於 R-75。

**讀過的 worktree 程式**（路徑皆在 `/home/user/AICompany/.claude/worktrees/agent-af8fe673a54e77432/apps/stock-desk/backend/` 之下）
- `app/data/interface.py`、`app/data/service.py`（L20-59、L175-234、L355-424、L604-663）、`app/api/deps.py`（相關段落）、`app/positions/models.py` L67；
- `tests/test_f9b0_rejection.py` L1-115、`tests/test_f9a_service_currency_warning.py` L325-369、`tests/test_api_deps.py` L130-153。

**ADR 字面檢查**：grep 確認 ADR 中「⇔」只出現在 L213（D-7 (2)），「查不到預期幣別」只出現在 L185（D-4 末點）。

**屬推論或未查證**
- 讀到的 worktree 檔案是現況，我沒有用 git 確認它就是 commit dc028dd 的內容。
- 「執行期查表回 None 只有在查表函式本身會變動結果時才可能發生」是依 `MARKET_CURRENCY` 為模組常數推得，要由 C-35 測試實證。
- 沒有跑任何測試，F-9b0 測試是否全綠以 dev-lead／qa-reviewer 的實跑結果為準。

## 下一步

1. **coordinator**：把本回覆存到 `work/reviews/`（TA7），然後把 R-76～R-80 交給 tech-writer。同時通知 qa-reviewer：F-9b0 依 R-76、R-78 審。R-78 轉 risk-compliance-officer 知悉。
2. **tech-writer**：在 CEO 核可 T-10 前，把 R-76～R-80 套用到 `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`。套用後回報，由我抽驗 D-7 (2) 與 D-4 末點的落字。
3. **qa-reviewer**：審 F-9b0（含 Codex 第二意見）。偏離 1、2 不列 BLOCKING。
4. **dev-lead**：F-9b0 不用改。F-9b 依 C-35 實作，可選擇把 C-35 (a) 提前放入 F-9b0。
5. **CEO**：等 R-76～R-80 落字後再核可 T-10，不新增知悉事項。

相關檔案（絕對路徑）：
- /home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md
- /home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024抽驗與待確認項裁決R-47至R-56.md
- /home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024第三次抽驗與F-9b切分R-57至R-69.md
- /home/user/AICompany/.claude/worktrees/agent-af8fe673a54e77432/apps/stock-desk/backend/app/data/interface.py
- /home/user/AICompany/.claude/worktrees/agent-af8fe673a54e77432/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/.claude/worktrees/agent-af8fe673a54e77432/apps/stock-desk/backend/app/api/deps.py
- /home/user/AICompany/.claude/worktrees/agent-af8fe673a54e77432/apps/stock-desk/backend/tests/test_api_deps.py