<!-- tech-architect 唯讀回報原文（TA6）；coordinator 轉存，2026-10-12 -->

## 本次結論

**還不能進 CEO 核可，需要先套用 R-70～R-75。** 這 6 項都是字句修正或補定義，不改變任何已核可的決策。套用後不需要再送我抽驗，coordinator 用 grep 逐字核對落字即可進 CEO 核可（T-10）。

- **抽驗結果**：R-57、R-58、R-60、R-68 逐字忠實。R-62 加上 F9W-35 (b)、F9W-36、F9W-37 (a)(b) 也都逐字到位。
- **問題出在 R-68 分期**：分期之後，ADR 有三處還寫成「F-9b」，其實已經移到 F-9b0：
  - 實作進度補記；
  - C-6；
  - PR 表 F-9b 列的「內容」欄。
  
  其中實作進度補記那句是我在 TA5 R-60 寫錯的，不是 tech-writer 誤植。
- **風控附帶提醒**：我的定義是 D-2 (2) 適用指數服務，而且指數路徑不適用 D-2 (4) 的 W-c′ 例外。指數 live 層被拒收時，同一次呼叫不回快取（R-72）。這比另一種做法保守，送風控知悉即可，可以和 CEO 核可並行。
- **coordinator 補列的 CEO 知悉句**：大致正確，但有三點要修（R-73）：
  - 出處標錯；
  - 漏了「孤兒壞列不上畫面、代價是額度不是正確性」這個關鍵；
  - 沒有標明「每次點擊重跑梯子」屬於推論。
  
  另外，「孤兒壞列不上畫面」這個說法在股票路徑還沒有測試釘住，補在 R-75。

## 各部門回報

### tech-architect（TA6；唯讀）

**一、抽驗結果**

| 項目 | ADR 位置 | 結果 |
|---|---|---|
| R-57 | D-2 (5)(a) 第 5 步末句 | 逐字相符 |
| R-58 | D-2 (5)(d)、C-30 | 逐字相符；D-7 (7)「至多出現一次（C-30）」和 C-30 不衝突 |
| R-60 | D-4 (b)、C-17、失效條件 13、實作進度補記、佐證末段 | 逐字相符。但實作進度補記寫「F-9b 起」，和 F-9b0 列「F9W-31 (b) 記錄格式（觀察模式）」矛盾 → R-70 |
| R-68 | F-9b0 列、F-9b 建議 commit、硬性順序 | 逐字相符。但 F-9b「內容」欄（題 2）和 C-6 沒有跟著分期 → R-71、題 2 |
| R-62 加 F9W-35 (b) | D-4 (c) | 兩句補句和「風控已確認（F9W-35）」都在，標註約定也同步了 |
| F9W-35 (a)(c) | C-17、D-4 (b) | 兩個 fixture、四項斷言、四條禁止路徑、不得降噪都到位 |
| F9W-36 | D-4 (a)、C-17 | docstring 引用、逐列參數化、F-9b0 合併前，都到位 |
| F9W-37 (a)(b) | C-34 (b) | 到位。(c) 是給 qa-e2e 的 suggested 項，風控沒有要求寫進 ADR，不列為修正 |

**二、ADR 修改清單（R-70 起；交 tech-writer）**

**R-70〔實作進度補記末點、D-4 (b)〕**
- 實作進度補記「F-9b 起此 WARNING 附加 `verdict`、`scope` 兩欄，指數改記 ERROR（TA5 R-60）。」改為：
  > F-9b0 起此記錄附加 `verdict`、`scope` 兩欄，指數服務納入同一記錄並改記 ERROR（觀察模式，回覆、快取、log 表與來源呼叫不變）；F-9b 起閘門轉為拒收，記錄改為每個拒收的閘門檢查點各記一筆。〔TA5 R-60、R-68；TA6 R-70〕
- D-4 (b)「每個拒收的閘門檢查點各記一筆」之後加：
  > （F-9b0 觀察模式下為每個判定不符的檢查點各記一筆）〔TA6 R-70〕

**R-71〔C-6〕**
- 「在 F-9b 改為 keyword-only 必填的 market→幣別查表函式（D-5、M-6）。三個建構點各自顯式傳入准入規則（指數：只檢查幣別、不檢查形狀）和字面組（指數：無）。不得保留 None 預設值。〔TA4 R-56，給 F-9b 實作〕」改為：
  > 在 F-9b0 改為 keyword-only 必填的 market→幣別查表函式，並顯式注入 `scope`（D-5、M-6；TA5 R-60）。三個建構點各自顯式傳入准入規則（指數：只檢查幣別、不檢查形狀）和字面組（指數：無），屬 F-9b（TA5 第三節 commit 7）。不得保留 None 預設值。〔TA4 R-56；TA5 R-68；TA6 R-71〕

**題 2：PR 表 F-9b 列「內容」欄 → 要改寫，不能只刪（R-71 續）**

`classify_currency` 和 `ProviderResult.rejection` 的欄位與不變式已經移到 F-9b0。但 `rejection` 的產生端和消費端仍在 F-9b，deps 的准入與字面組接線也仍在 F-9b。直接刪會讓 qa-reviewer 漏勾。

做法：把「內容」欄從開頭到「消費端字串表（F9W-10）。」整段換成下面這段，其後「建議分 commit：…」那句不動：

> 服務層幣別閘門 fail-closed（live 層 W-c／W-c′，以 F-9b0 的 `classify_currency` 分流）；兩個入口的准入；`ProviderResult.rejection` 的寫入（產生端）與消費（`load_bars` W-d 三分流、估值器新 token）；F9W-4 (a) 同次回覆不讀快取；W-a、W-b、W-c、W-c′ 常數；快取閘門（含 T-15 四條路徑）；新 token、整書成因組、前端標籤（F9W-11）；方向子句測試（F9W-13）；deps 准入規則與字面組接線（指數只檢查幣別、無字面，F9W-9；幣別查表與 `scope` 已於 F-9b0 接上）；AV 縱深檢查（F9W-7）；消費端字串表（F9W-10）；F9W-31 (b) 記錄由觀察改為隨拒收觸發。`ProviderResult.rejection` 欄位與不變式、`classify_currency` 與等價測試、幣別判準必填化、共用測試 helper 已於 F-9b0 完成，不在本 PR 範圍。〔TA6 R-71〕

**R-72〔D-4 指數段；回應風控附帶提醒〕**

位置是 D-4 指數段「指數服務的快取閘門照常 fail-closed…」那一點之後，新增一點：

> 指數服務的 live 層被幣別閘門拒收時（`classify_currency` 判為 mismatch 或 missing 皆同），同一次呼叫不以快取回價格：降級時不讀快取，直接回 `UNAVAILABLE`、`bars=[]`，`rejection` 依 D-7 (2) 的優先序取 `unit_mismatch` 或 `unit_missing`，reason 只含其他 live 層的既有原因（可為 None），不加任何字面；因指數服務不讀也不寫 D-9 標記，此處置不延續到下一次呼叫（D-2 (3) 不適用）。亦即 D-2 (2) 適用指數服務，且指數路徑不適用 D-2 (4) 的 W-c′ 例外：股票路徑 W-c′ 可回通過閘門的快取，以風控核可的 W-c′ 句揭露為前提（F9W-33、F9W-34），指數路徑沒有字面可揭露。D-4 (b) 的記錄照記（`layer=provider`、`scope=index`）；此情境下 `index.py` 會接既有指數版 `NO_BARS_REASON`，與 F9W-31、F9W-32 的殘留同類，與 D-4 (c)「一律 `bars=[]`」一致，並適用失效條件 13；T-16 起草範圍須一併明列「指數 live 層被閘門拒收」。以測試釘住：假 provider 對 `^GSPC`／US 回 `currency="TWD"`、`currency=""` 各一測，快取放通過閘門、但不新鮮到使 layer 0 回 None 的列 → `bars=[]`、`rejection` 如上、快取列未進回覆、恰一筆 `layer=provider`、`scope=index` 的 ERROR、reason 不含 T-15 與任何股票路徑字面。〔TA6 R-72；回應 F9W-D 附帶提醒；送風控知悉〕

另外兩處連動修改：
- D-4 (d) 句尾加「；T-16 起草範圍另含『指數 live 層被閘門拒收』（TA6 R-72）」。
- 佐證末段「F9W-D 的『附帶提醒』…本檔未收錄，留待 tech-architect 抽驗時補定義。」改為「F9W-D 的『附帶提醒』已由 TA6 R-72 補定義於 D-4 指數段（送風控知悉）。」

方案比較：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **甲：指數 live 拒收一律不回快取（採用）** | 和 F9W-4、F9W-31 (c) 一致；指數路徑沒有字面，不會出現「沒有揭露就回快取」的情形 | 指數 W-c′ 比股票路徑嚴格 | 低。正式設定下不可達，有 R-61 絆線把關 |
| 乙：照股票路徑分流（mismatch 不回、missing 可回快取） | 兩條路徑對稱 | 指數 missing 時回快取價格，reason 沒有任何說明為何 live 被拒，等於靜默降級 | 中 |
| 丙：不適用，照現行回快取 | 不用改 | 違反 D-2 (2) 的本意 | 高，否決 |

**R-73〔「給 CEO 的知悉事項」coordinator 補列句〕**

把「另，孤兒壞列殘留（…）須於 T-10 核可時一併知悉，並把 F-9e 排入可執行的時程。〔TA5 R-63；F9W-35～F9W-37 風控知悉段；coordinator 補列〕」整句換成：

> 另，孤兒壞列殘留（請求區間內的壞列落在來源不回傳的日期時，整段重抓成功也覆寫不到；之後每次點擊 layer 0 都會被擋並重跑梯子，美股每次耗一次 AV 額度，指數路徑只用 yfinance、不耗 AV 額度，直到 F-9e 清理；回覆與 beta 只用本次新抓的列，孤兒壞列不上畫面（F9W-35 (a)、C-32 以測試實證），代價是額度與延遲，不是數字正確性；只在手動改庫或 `MARKET_CURRENCY` 變動後可能出現；「每次點擊重跑梯子」為推論，待 F-9b 測試實證；見壞處 5）須於 T-10 核可時一併知悉，並把 F-9e 排入可執行的時程，不無限期擱置。〔TA5 R-63；F9W-D R-63 知悉段與「下一步」5（風控 suggested）；coordinator 補列〕

修改理由：
- 原出處「F9W-35～F9W-37 風控知悉段」不正確。風控對 R-63 的意見在 F9W-D 的「R-63（知悉）」段，F9W-35～37 是條件，不是知悉段。
- 原句漏了「不上畫面、代價非正確性」，這是風控接受此殘留的理由。
- 原句也漏了推論標註。

**R-74〔檔頭與佐證的 TA6 登錄〕**
- 標註約定：在〔TA5 R-x〕定義之後加「〔TA6 R-x〕＝tech-architect 對本檔的第四次抽驗（R-70～R-75，含風控附帶提醒的指數 D-2 (2) 定義）」。
- 兩處優先序改為：
  - 「TA6 ＞ TA5 ＞ TA4 ＞ TA3 ＞ TA2 ＞ TA1」；
  - 「風控裁定 > TA6 R-70～R-75 > TA5 R-57～R-69 > …」。
- 來源清單：加「第六次回覆（TA6）：（檔名由 coordinator 定；R-70～R-75；讀碼基準 product/stock-desk HEAD `391e8fd`，唯讀、未執行測試）」。
- 佐證表：加一列「TA6 套用」，逐項對應 R-70～R-75 的位置。

**R-75〔C-32 加註；F-9b commit 6〕**

C-32 句尾加：

> 股票路徑另以含孤兒壞列（落在來源不回傳日期）的 fixture 斷言：冷卻期外整段重抓成功時，回覆的日期集合與值逐根等於 provider 回傳，孤兒日期不在回覆中，估值只用回覆列。〔TA6 R-75；比照 F9W-35 (a) fixture (ii)〕

理由：F9W-35 (a) 只要求指數路徑。股票路徑走同一段 `fetch_start == start` 的程式碼，但有 backups，而且有 AV。R-73 給 CEO 的「孤兒壞列不上畫面」必須兩條路徑都有測試支撐。

### 給其他部門（經 coordinator 轉達）
- **tech-writer**：套用 R-70～R-75。
- **risk-compliance-officer**：
  - R-72 送知悉：比股票路徑保守，不新增字面，T-16 範圍加一個情境。若有異議，依優先序回改。
  - R-75 只是補測試，供知悉。
- **dev-lead／qa-reviewer**：
  - F-9b 的 commit 5（live 閘門）加入 R-72 測試；
  - commit 6 加入 R-75 fixture；
  - F-9b0 的審查範圍依 R-70、R-71 確認：指數服務的 ERROR 在 F-9b0 觀察模式就會出現。
- **CEO**：知悉句依 R-73。

## 驗證

- **讀過的檔案**：
  - `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md` 全文（533 行）；
  - TA5、F9W-D 兩份來源全文。
- **讀碼核對**（工作樹）：
  - `/home/user/AICompany/apps/stock-desk/backend/app/data/service.py` L160-369：
    - 全層拒答走 L275-280 的 `_fall_back_to_cache`；
    - 只有 `fetch_start > start` 才讀回快取（L215-239）；
    - 成功時回 `result.bars`；
    - F-9a 的 WARNING 格式在 L352-363。
  - `/home/user/AICompany/apps/stock-desk/backend/app/services/index.py` L240-399：`UNAVAILABLE` 或空 bars 一律接 `NO_BARS_REASON` 加上 provider reason，這是 R-72「與 F9W-31／32 殘留同類」的依據。
- **快照**：`.git/HEAD` 指向 `refs/heads/product/stock-desk`，其值為 `391e8fd3e980a337f6c42771f7bb090fa17adcab`。我讀的是工作樹檔案，沒有權限跑 `git status`，所以無法排除有未 commit 的改動。
- **屬推論、尚未實證**：
  - R-72 測試情境的 layer 序列（只有 `provider`）；
  - R-75 的股票路徑孤兒排除。
  
  兩者都須由對應測試實證。
- **未做的事**：沒有改檔、沒有執行測試、沒有 git 操作、沒有連網，也沒有讀 `.env` 或任何 `*.db`。

## 下一步

1. **coordinator**：把本回覆以 TA6 存到 `work/reviews/`，再把 R-70～R-75 交給 tech-writer。R-72、R-75 轉給風控知悉。
2. **tech-writer**：套用 R-70～R-75，並回報新 commit。
3. **coordinator**：用 grep 核對 R-70～R-75 的關鍵字句都已落字，核對無誤即送 CEO 核可（T-10）。不需要再經我抽驗。風控對 R-72 的知悉可以和 T-10 並行，若有異議，在 F-9b 合併前回改。
4. **dev-lead**：F-9b0 可以照 TA5 第三節開工，R-70、R-71 不影響它的 commit 表。

相關檔案：
- /home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md
- /home/user/AICompany/work/reviews/2026-10-12-tech-architect-ADR-0024第三次抽驗與F-9b切分R-57至R-69.md
- /home/user/AICompany/work/reviews/2026-10-12-F-9-R62確認與R60至R66知悉-F9W-35至F9W-37-風控.md
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/index.py