# ADR-0028 r3″ 更正 A-87～A-95（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0028 r3″ 更正（tech-architect，唯讀）

## 一、結論

- tech-writer 回報的 10 項都有回覆：確認不改 3 項，給出可直接套用文字的更正 A-87～A-95 共 9 條（A 編號接在 ADR-0027 r3 的 A-86 之後；我 grep 過全 repo，A-87 以後沒有被用過）。
- **方向**：收緊 2 條（A-87 CS-12 接合句、A-91 D-5 (a) 納入 CST-9），不變 6 條，中性 1 條（修訂紀錄），**沒有放寬**。依 CS-21 通則不必送風控，交 coordinator 機械核對即可。
- **LM-70 屬實性不受影響。** R2″ 狀態欄只改括號內的說明，條件、`state`、D-5 的對應（`date_anomaly` → LM-70）都沒動。official basis 下仍保留「官方日曆與資料衝突」這幾個字，原有的字面對應不變。風控 (c) 的推論依據是條件，不是括號說明，所以結論照樣成立（詳見 A-89）。
- tech-writer 的判斷有兩處我追加處理：
  - D-9 標題的「附件 B'-3」也屬於本文的外部參照，併入 A-92 自足化。
  - D-5 (b) 的「§6.4 唯讀複本診斷 A～D」「§6.4 的試算」「§6.3 判讀矩陣 F-7 那一欄」，在探測指令檔裡實際分別是 §6.4.3、§6.4.4、§6.3.3a。data-engineer 沒有在矩陣加欄，而是另立補充表。A-92 改成精確的子節號。

## 二、逐項回覆與條文

套用基準：commit 1d69acd 的 `/home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md`。下文行號只是輔助，以條號定位為準。

### 二-1　無法套用第 1 項：CS-12 接合句 → **A-87（收緊）**

定位：§對實作的約束 CS-12 → 「LM-24 只在…時渲染」的第一個巢狀子項（A-84 那句之前那一行）。

- CS-12 標題括號改為：`（r1 改，A-17；r2 改，A-39；r3″ 改，A-87）`
- 第一個巢狀子項**整句取代**為：
  > - LM-24 在 `basis=observed`、`sub_reason=after_close_pending` 時渲染，要等翻轉 PR 合併後才生效。合併前，D-9 要已經實作合併，而且 CST-5～CST-9 綠燈（D-5「observed 兩列的說明」第二點 (a)）；data-engineer 的確認回報要經過風控單項確認，並由 qa 審查。翻轉 PR 的完整合併條件以 D-5 該點 (a)～(c) 為準。
- A-84 那句（不設執行期旗標）不動，仍是下一個子項。
- 理由：
  - 依 A-85 原則，本文不引用「A-48 (a)」這類提案編號，改寫本 ADR 的條號。
  - 「以 D-5 該點為準」可以避免 CS-12 比 D-5 寬（例如 (b) 的回報最低內容）。
  - 風控 r3 確認第二-6 已認定「A-39 的 CS-12 加引用 A-48 (a)」是收緊。

### 二-2　位置裁量 3 項

| # | 項目 | 回覆 |
|---|---|---|
| 1 | r3 修訂行放在 r2 行之後 | **確認**。「在 r1 修訂下一行」是我提案時的疏漏，依時序應在 r2 之後。r3″ 行（A-95）接在 r3 行之後。 |
| 2 | ADR-0019 兩點並存 | **需更正 → A-88（合併）** |
| 3 | R2″、R3 列的 r3 標註 | **確認**。R2、R2′、R2″ 三列這次另加 r3″ 標註（見 A-89、A-90）。 |

**A-88（不變）ADR-0019 兩點合併**

方案比較：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 保留兩點 | 不動 | 同一份 ADR 有兩點，讀者不知道以哪點為準 | 「D-4、D-5」指哪份 ADR 有歧義 |
| 刪除 L14 | 簡潔 | 「不讀 `tail_fetched_at`」這條約束會消失 | 遺失 ADR-0019 K-3 的對應 |
| **合併（採用）** | 只留一點，約束完整 | 要在修訂紀錄保留 L14 原文 | 低 |

條文：
- 刪除「與既有 ADR 的關係」中的這一點（原 L14）：`  - **ADR-0019**：與 D-4、D-5 的單一取得時間基準一致，不讀 `tail_fetched_at`。`
- 原 L21 的 ADR-0019 點**整點取代**為：
  > - **ADR-0019**（r3、r3′；r3″ 合併，A-88）：`acquired_at` 依 ADR-0019 D-4、D-5 的單一取得時間基準。本 ADR 的模組不讀 `tail_fetched_at` 欄（ADR-0019 K-3 的用途限制）；走快取路徑時，`acquired_at` 的值等於它，是經由 ADR-0019 D-5 的序列取得時間間接取得（見 Context「觀察日曆現況」）。D-9 讀列層的 `as_of` 與 `fetched_at`，R3 另外讀當日 bar 的 `PriceBar.as_of`。這些時間都只用來判斷「是否定案」，一律取較早者（CS-17）。它們不是序列的取得時間，不取代 `acquired_at`（ADR-0019 D-5），也不得顯示（K-13）。K-9 不受影響。

讀法說明：
- 原 L14 的「D-4、D-5」我讀作 ADR-0019 的 D-4、D-5。「單一取得時間基準」就是 ADR-0019 標題，本 ADR 的 D-5 是字面對應，和取得時間無關。
- 「不讀 `tail_fetched_at`」的約束原樣保留，並補上它依據的 K-3（ADR-0019 L156-159：`tail_fetched_at` 只出現在 `judge`、S3-1 閘門、`_cached_result`），沒有放寬。
- 附帶觀察（不更正）：ADR-0016、ADR-0009 也各出現兩次（L12／L15 與 L20）。但 L20 是三份 ADR 共用一個主題的聯合陳述，主題不同，不合併。

### 二-3　套用後疑點 6 項

**(1) R2″ 狀態欄 → A-89（不變）**

需要改。R2″ 現在涵蓋任何 basis，「官方日曆與資料衝突」只在 official 時成立。非 official 時（推論：D 是 build 窗口的 end，若 D 是 absent，max(confirmed) < D，所以 D ∉ R），只會是 weekday_assumed 的週末，和風控 (c) 的推論一致。

- D-4 表 R2″ 列**整列取代**為：
  > | **R2″（新增；r3 改，A-47；r3″ 改狀態欄，A-89）** | D 不是交易日（任何 basis），而且 `price_date == D` | `date_anomaly`（D 依日曆不是交易日，卻有 D 日期的列；basis＝official 時即官方日曆與資料衝突。`sub_reason` 見表後） | price_date |

**LM-70 字面對應的影響評估**（依你的要求標出）：
- **條件欄**：一字不動。風控 (c) 所推的落入情形（R2″ 非 official 只會是週末 D 出現 D 日期的列），所依據的就是條件欄。
- **狀態與對應**：`state` 仍是 `date_anomaly`，D-5 對應仍是 LM-70。sub_reason 只用於 log 與 CS-11 窮舉，不進字面（L146）。
- **括號說明**：不是字面。LM-70「{MM/DD} 價格｜資料日期異常，日期無法確認」本身不宣稱原因。
- **official 的情形**：「官方日曆與資料衝突」原字保留。

結論：字面對應沒有變動，風控「R2″／R2‴ 對 LM-70 屬實」的結論照樣成立，不必回送風控。唯一的字面差異是括號說明從單一原因改成依 basis 敘述，這是讓說明符合 A-47 已經核可的條件，不是新的主張。

**(2) sub_reason 列舉 → A-90（不變，補定義）**

五個 sub_reason 的列舉順序就是 R2／R2′／R2″(official)／R2″(其他)／R2‴，r3 只漏寫了前兩列的對應。

- D-4 表 R2 列**整列取代**為：
  > | R2（r3″ 補 sub_reason，A-90） | `price_date > D` | `date_anomaly`，`sub_reason = future_date`，記 WARNING | price_date |
- D-4 表 R2′ 列**整列取代**為：
  > | **R2′（新增；r3″ 補 sub_reason，A-90）** | 交易日、開盤前，而且 `price_date == D` | `date_anomaly`，`sub_reason = before_open`（開盤前不可能有當日 bar） | price_date |
- 表後第一句（原「（r3，A-47）R2″ 的狀態仍是 `date_anomaly`，`sub_reason` 依 basis 分成 `official_conflict` 與 `not_a_session`。」）**整句取代**為：
  > （r3，A-47；r3″ 補對應，A-90）R2″ 的狀態仍是 `date_anomaly`；basis＝official 時 `sub_reason = official_conflict`，其他 basis（observed、weekday_assumed）時為 `not_a_session`。
- 列舉句（`date_anomaly` 的 `sub_reason`（…）只用於 log…）不動。
- LM-70：R2、R2′ 自 r1 起就對應 LM-70，補 sub_reason 不改對應。CS-11 窮舉的組合變多，但都對應 LM-70。

**(3) D-5 第二點 (a) 未含 CST-9 → A-91（收緊）**

- D-5「observed 兩列的說明」第二點 (a) **整句取代**為：
  > - (a) D-9 已經實作合併，CST-5～CST-9 綠燈；
- D-5 該說明區的標題括號改為：`（r2，A-38；r3 改，A-48；r3″ 改，A-91、A-92）`
- 理由：「D-9 已經實作合併」包含 D-9 第 8 點（R3 同口徑），它的測試是 CST-9。只列到 CST-8，條件本身前後不一致。這是收緊，不必送風控。
- qa-reviewer 審翻轉 PR 時，核對範圍由風控寫的「CST-5～8」擴為 CST-5～CST-9。

**(4) 外部參照自足化 → A-92（不變，比照 ADR-0027 A-85：只動參照，不動實質）**

我已用 Grep 核對探測指令檔：§6.3.3a 是 F-7 補充欄（L1460）；§6.4.3 是本機 DB 診斷，有 A～D（L1601-1661）；§6.4.4 是新口徑試算（L1691）。

D-5「observed 兩列的說明」第二點 (b)，各子項依序替換片段：
1. 「Phase 1 探測 §6.3 至少三輪的結果」→「Phase 1 探測指令（`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`，下稱「探測指令」）§6.3 至少三輪的結果」
2. 「§6.4 唯讀複本診斷 A～D 的數字」→「探測指令 §6.4.3 唯讀複本診斷 A～D 的數字」
3. (i)「§6.4 的試算必須用」→「探測指令 §6.4.4 的新口徑試算必須用」
4. (ii)「（§6.4 唯讀複本涵蓋的全部日期）」→「（探測指令 §6.4 所用唯讀複本涵蓋的全部日期）」
5. (iii)「§6.3 判讀矩陣 F-7 那一欄的結果」→「探測指令 §6.3.3a（判讀矩陣的 F-7 補充欄）的結果」

其他位置：
- **F-7**：「§6.3 發現某個所用來源」→「探測指令（`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`）§6.3 發現某個所用來源」；條號括號改為 `（r3；r3″ 補參照，A-92）`。
- **D-9 標題**：`### D-9 觀察交易日集合的輸入（r3，附件 B'-3）` → `### D-9 觀察交易日集合的輸入（r3）`
- **待決事項 data-engineer**：「R4c 翻轉前的確認回報內容（依 A-48）」→「R4c 翻轉前的確認回報內容（依 D-5「observed 兩列的說明」第二點 (b)）」
- **確認不改**：
  - 檔頭 r3 修訂行的「附件 B'-3」是出處紀錄，不是本文的規範性參照，加上修訂紀錄 L518 的註記已經自足。
  - tech-writer 在 r3 區塊加的「第五節第 1 點指提案檔」註記保留，因為引用的原文仍含這個編號。
  - 「第五節第 1 點」本文出現的那一處，由 A-93 整句取代後消失。

**(5) 風控待決項過時 → A-93（不變，狀態更新）**

- 待決事項「風控」下的「新增（r3，A-52）：r3 設計的單項確認（見第五節第 1 點）；R2″ 改寫、R2‴ 對應 LM-70 是否屬實。」**整句取代**為：
  > - 已裁示（r3，A-52；r3″ 更新，A-93）：r3 設計的單項確認為 APPROVE WITH CONDITIONS，沒有 VETO（`work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md`）。R2″ 改寫、R2‴ 都對應 LM-70，風控認定屬實，不必另外起草。required R-1～R-3 已由 r3′ 寫入（SE-2 與 CST-5 的 R-1 fixture、CS-21 通則、D-5「observed 兩列的說明」第二點 (b) (i)～(iii)）。R-4 屬於 ADR-0027，不在本 ADR。
- 其餘風控項不動，含仍待辦的「新增（r2，A-40）：data-engineer 觀察日確認回報的單項確認」與「新狀態的字面」。
- 附帶（不改 ADR）：
  - 風控提到 LM-70 的但書「只在異常時仍顯示價格才成立」仍待 tech-architect 與 PM 定。
  - tech-architect 這一側，D-5 `date_anomaly` 列與 D-4 補充（r1 A-19）已經寫明「價格照常顯示、不改估值與總額」，所以成立。剩 PM 側要表態，請 coordinator 轉給 product-manager。

**(6) (f)(g) 孤兒標號 → A-94（不變）**

待決事項 data-engineer 下「新增（r3′，A-52′）：」的兩個子項，**整組取代**為（拿掉標號）：
>     - 確認所有寫入 `price_bars_cache` 的轉接器，`PriceBar.as_of` 都不晚於第一個請求送出的時間；
>     - D-5「observed 兩列的說明」第二點 (b) (i)～(iii) 的回報內容。

ADR 內沒有任何條文引用「(f)」「(g)」，拿掉標號不會斷引用。舊標號的對照記在修訂紀錄。

### 二-4　檔頭與修訂紀錄 → A-95（中性）

**檔頭**：在「r3 修訂」行之後加一行：
> - r3″ 更正：2026-10-17，依 tech-architect r3″ 更正 A-87～A-95（r3 套用後的接合、參照與編修；A-87、A-91 為收緊，其餘方向不變）

**修訂紀錄**：在 A-84 條目之後加 `---` 與以下區塊。`〈轉存路徑〉` 由 coordinator 轉存本回報後填入；引用區塊請 tech-writer 以 1d69acd 的原文逐字貼上，下列文字是我讀到的 1d69acd 原文。

> r3″（2026-10-17）依 tech-architect「ADR-0028 r3″ 更正」A-87～A-95 套用（〈轉存路徑〉）。只更正 r3 套用後的接合、參照與編修：A-87、A-91 為收緊，其餘方向不變，沒有放寬，依 CS-21 通則不必送風控。檔頭狀態維持 proposed。
> 被改寫或取代的原文逐字保留於下；引用區塊內的文字即 r3″ 之前（commit 1d69acd）的原文。

**A-87（CS-12）**
- r3″：observed 子項原文——
  > - LM-24 在 `basis=observed`、`sub_reason=after_close_pending` 時渲染，要等翻轉 PR 合併後才生效。合併前，data-engineer 的確認回報要經過風控單項確認，並由 qa 審查。

  改為見 §對實作的約束 CS-12（補 D-9 前提，對應 r3 提案第四節第 1 點）。

**A-88（與既有 ADR 的關係：ADR-0019）**
- r3″：刪除的原點——
  > - **ADR-0019**：與 D-4、D-5 的單一取得時間基準一致，不讀 `tail_fetched_at`。

  併入 r3′ 的 ADR-0019 點，該點原文——
  > - **ADR-0019**：D-9 讀列層的 `as_of` 與 `fetched_at`，R3 另外讀當日 bar 的 `PriceBar.as_of`。這些時間都只用來判斷「是否定案」，一律取較早者（CS-17）。它們不是序列的取得時間，不取代 `acquired_at`（ADR-0019 D-5），也不得顯示（K-13）。K-9 不受影響。

  改為見檔頭。「D-4、D-5」讀作 ADR-0019 的條號；「不讀 `tail_fetched_at`」保留，補依據 K-3。

**A-89、A-90（D-4 R2、R2′、R2″ 與表後第一句）**
- r3″：三列原文——
  > | R2 | `price_date > D` | `date_anomaly`，記 WARNING | price_date |
  > | **R2′（新增）** | 交易日、開盤前，而且 `price_date == D` | `date_anomaly`（開盤前不可能有當日 bar） | price_date |
  > | **R2″（新增；r3 改，A-47）** | D 不是交易日（任何 basis），而且 `price_date == D` | `date_anomaly`（官方日曆與資料衝突） | price_date |

  表後第一句原文——
  > （r3，A-47）R2″ 的狀態仍是 `date_anomaly`，`sub_reason` 依 basis 分成 `official_conflict` 與 `not_a_session`。

  改為見 §D-4。條件欄與 LM-70 對應不變。

**A-91（D-5 第二點 (a)）**
- r3″：原文——
  > - (a) D-9 已經實作合併，CST-5～CST-8 綠燈；

  改為見 §D-5（納入 CST-9）。

**A-92（外部參照自足化，比照 ADR-0027 A-85）**
- r3″：替換的片段原文——
  - D-5 第二點 (b)：「Phase 1 探測 §6.3 至少三輪的結果」「§6.4 唯讀複本診斷 A～D 的數字」「(i) §6.4 的試算必須用」「（§6.4 唯讀複本涵蓋的全部日期）」「(iii) §6.3 判讀矩陣 F-7 那一欄的結果」；
  - F-7：「§6.3 發現某個所用來源」；
  - D-9 標題：「（r3，附件 B'-3）」；
  - 待決事項 data-engineer：「（依 A-48）」。

  改為見各處。§6.x 指 `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 的章節；F-7 補充欄實際是 §6.3.3a。

**A-93（待決事項 風控）**
- r3″：原文——
  > - 新增（r3，A-52）：r3 設計的單項確認（見第五節第 1 點）；R2″ 改寫、R2‴ 對應 LM-70 是否屬實。

  改為見 §待決事項 風控（已裁示：APPROVE WITH CONDITIONS）。

**A-94（待決事項 data-engineer 標號）**
- r3″：原文——
  >     - (f) 確認所有寫入 `price_bars_cache` 的轉接器，`PriceBar.as_of` 都不晚於第一個請求送出的時間；
  >     - (g) A-48 (b) (i)～(iii) 的回報內容。

  改為見 §待決事項 data-engineer。(f)(g) 原本接續提案第五節第 2 點的 (a)～(e)，ADR 內沒有對應，所以拿掉標號。

**A-95（檔頭、修訂紀錄）**
- r3″：檔頭新增「r3″ 更正」一行，本區塊為新增，無被取代原文。

## 三、方向統計

| 方向 | 數量 | 條目 |
|---|---|---|
| 收緊 | 2 | A-87（CS-12 補 D-9 前提與 CST-5～9）、A-91（D-5 (a) 納入 CST-9） |
| 不變 | 6 | A-88（ADR-0019 合併）、A-89（R2″ 狀態欄）、A-90（R2／R2′ sub_reason 與 R2″ 對應）、A-92（外部參照自足化）、A-93（風控待決狀態更新）、A-94（拿掉 (f)(g) 標號） |
| 中性（紀錄） | 1 | A-95 |
| 放寬 | 0 | — |
| 確認不改 | 3 | r3 修訂行位置、R2″／R3 標註、r3 區塊「提案編號」註記（加上檔頭 r3 行的「附件 B'-3」維持出處紀錄） |

**送審路徑**：沒有放寬，不必送風控。LM-70 對應不變（理由見 A-89），也不必回送風控。交 tech-writer 套用後，由 coordinator 用 diff 機械核對，確認以下三點：
1. R2″ 條件欄一字未動；
2. D-5 的 `date_anomaly` → LM-70 一列未動；
3. CS-12 的 A-84 子項仍在。

**驗證範圍**
- 讀過：
  - ADR-0028 全文（1d69acd 工作樹）；
  - tech-writer 回報全文；
  - 風控 r3 單項確認全文；
  - r3 提案 L140-269；
  - r3′ 提案（grep）；
  - ADR-0027 r3 提案的 A-85 與第六節；
  - ADR-0019 D-4、D-5、K-3（L100-109、L152-159）；
  - 探測指令檔的章節結構（grep 標題與 §6.4.3／§6.4.4 的診斷段標）；
  - data-engineer §6.9 回報 L1-25；
  - 字面清單的 LM-70（L2365、L2389）。
- 沒有修改任何檔案，沒有讀 `.env` 或 `*.db`，也沒有重新核對 code。
- 一處推論：「非 official 的 R2″ 只會是週末」，這是我依 D-9 第 5、6 點推得，和風控 (c) 一致，所以沒有寫進條文。

**下一步**
1. coordinator 把本回報轉存到 `work/reviews/`，再把路徑填入 A-95 區塊的〈轉存路徑〉。
2. tech-writer 依二-1～二-4 套用，只動 ADR-0028。
3. coordinator 用 diff 機械核對。
4. product-manager 確認 LM-70 但書的 PM 側（A-93 附帶項）。

**相關檔案**
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028套用r3與r3prime-tech-writer回報.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028修訂提案r3觀察日來源-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028修訂提案r3prime補正-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md
- /home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md
- /home/user/AICompany/docs/adr/0019-stock-desk-日線-coverage-判定與取得時間單一基準.md
