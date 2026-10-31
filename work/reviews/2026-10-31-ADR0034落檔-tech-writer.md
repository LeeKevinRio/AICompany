# ADR-0034 落檔

- 審查者：tech-writer
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

ADR-0034 已落檔，路徑 `/home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md`。

- 動工前 Glob 確認 `docs/adr/0034-*` 不存在，所以沒有停手。
- 格式比照 0033：檔頭、Context、Options、Decision、Consequences、待決、附錄。
- 狀態寫 `accepted`，依據寫 CEO #79、#80（2026-10-31）。
- 與 0033 的關係：
  - 補充 0033，不取代；0033 維持 accepted，原文不改。
  - 取代條件已明寫：若風控要求 message 新增第四支，則另立取代 0033 的 ADR，不修改本 ADR 或 0033。
- Decision 共 11 條，要求的內容都有：
  - B-2a 加 L4。
  - 在 0033 的 C-1 transaction 內擴充鎖內第四項讀取，並對同一批列做 UPDATE。
  - 三支 message 結構不變，只附加句子。
  - B-2b 永久紅線（CEO #80）。
  - 排序：N-166 合併後才合併，走獨立分支（VETO-4）。
  - 另收錄：W 系列識別名表、風控的 message 組合順序、確認面板不動。
- A 案的 C-A／T-A 只在 Options 寫「未採」要點，沒有全文收錄。
- F5（N-172）已列為已知風險與前置條件：定調前 N-168 不開工實作。

## 2. 各部門回報

本次只做落檔轉錄，沒有請其他部門回報。工作涉及的來源與對應部門如下。

- **tech-architect**：Q1～Q5、L1～L4、VETO、C-B、T-B、F5、草案 Context／Consequences。
- **risk-compliance-officer**：方案表態、D1～D7、W 系列識別名、組合順序、逐條意見。
- **product-manager**：方案比較、背景、FR 與 AC。
- **CEO**：決策包第 95、96 行（#79、#80）與第 100 行 coordinator 定案；追蹤清單 N-168 補2、N-172、N-173、N-174。

來源之間有三點需要負責部門確認，我沒有自行裁決：

1. **N-168a 平行開發與前置條件互相矛盾。**
   - TA 建議允許 B-2a 的 schema、settle 複製戳記、`/today` 欄位等部分先平行開發，稱 N-168a。
   - #79 沒有載入這項，追蹤清單 N-168 補2 卻寫「F5 定調前不開工實作」。
   - ADR 記載為「不採認 N-168a 可先行，待 CEO 另行裁示」。請 CEO 確認。
2. **TA 引用的 0033 行號與現檔偏 1 行。**
   - 例：C-1 現在在第 125 行，TA 引為 124。內容無誤。
   - ADR 改引 0033 的條號與附錄名稱，並在檔頭註明。
3. **凍結期延長的估計，PM 與風控不一致。**
   - 風控寫約 1 個交易日，PM 寫一到兩個。
   - ADR 如實並陳，不採信任一數字。

另外，決策包 #79、#80 的裁定欄位標示為「（建議）」。這與 0033 對 #76、#77 的處理相同，我依你的指示視為 CEO 裁定。

## 3. 驗證

**檔名與行數**：`/home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md`，230 行。後來又做了兩處小修，行數不變。這個數字用 Grep 以 `^` 計數，不是 `wc -l`。

**VETO、C-B、T-B 收錄核對**：用 Grep 逐條點名核對，全數收錄。

- VETO-1～VETO-5：5 條，附錄 B。
  - VETO-3 以標題含括號的格式寫成「僅 A 案；A 案未採，記錄備查」，所以沒被我的簡單模式比對到，已人工確認存在。
- C-B1～C-B11：11 條，附錄 C。
- T-B1～T-B16：16 條，附錄 D。

我是逐條轉錄，沒有補技術細節。

**W 系列實際字面沒有進檔**：

- 檔內只有識別名：
  - `EMERGENCY_EXIT_PENDING_ENTRY_NOTE`
  - `EMERGENCY_EXIT_PENDING_ENTRY_PAST_DUE_NOTE`
  - `ENTRY_BEFORE_EXIT_LABEL`
  - `ENTRY_BEFORE_EXIT_NOTE`
  - `SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE`
  - `PENDING_ENTRY_FROZEN_NOTE`
  - `EMERGENCY_EXIT_LABELED_BATCH_NOTE`
- 檔頭與 Decision 5 都註明「逐字以 `work/reviews/2026-10-31-N168方案裁示-風控.md` 為準，僅放 `wording.py`」。
- 我用 Grep 查了風控 W 句的特徵片段，包括「請勿就」「帳冊判定成交」「提交前已產生」「暫停期間記入」「不適用於你」。這些片段在 ADR 內都找不到。
- 有兩處提到「你已買進」「本系統不下單」的字眼。它們是在轉述風控的「字串檢查規則」（W 系列不得含「你已買進」類說法、須含「本系統不下單」），不是 W 句本文。
- 還有一處我原本寫得太接近風控 W 句的意思（「無法替使用者在券商撤單」），已改寫成中性敘述。

**「出清後成交」**：

- 檔內出現 2 次，都是否定語境，沒有任何一處把它當面向使用者的標示。
  - 第 1 次在檔頭「標註約定」：說明它只能當內部識別名。
  - 第 2 次在 Context 第 3 點：已改成「以『出清後』描述…可能是錯的」，不再含「出清後成交」整詞。
  - 若你用 grep 檢查，預期會命中第 1 次。
- 面向使用者的標示語意寫成「出清當時尚未結算、不在該次出清範圍」。

**未改任何其他檔案**：沒有改 0033，沒有改 ADR 索引（`docs/adr/` 下本來就沒有索引檔），沒有讀 `.env`，沒有碰 `data/*.db`，也沒有執行程式。

**佐證清單（B 類）**：

- 本檔是轉錄，所有 `檔案:行號` 都是 TA 或風控撰寫時（2026-10-31）的快照，我沒有逐條重驗。
- 快照基準是分支 `product/stock-desk` 當時的工作樹。我沒有 Bash，無法取得 commit hash，只讀到 `.git/HEAD` 指向該分支。
- 抽驗時請以內容定位，不要依行號。

## 4. 下一步

1. **coordinator**：commit 本檔（Conventional Commits，`docs:` 開頭）。
   - 本任務沒有 Bash，所以沒有 commit。
   - 若要在 0033 加指向 0034 的註記，需另案由 CEO 與 tech-architect 決定。
2. **CEO**：裁示 N-168a 是否可先行平行開發，並確認凍結期延長的估計口徑。
3. **qa-automation 與 tech-architect**：重現並定調 F5（N-172）。這是 N-168 開工的前置條件。
4. **風控**：W 系列合併前仍須逐字核可紀錄（PRD 的 AC-11）。
5. **product-manager**：依 TA 兩處更正與風控 required 項修訂 PRD。
6. **dev-lead**：N-166 合併且 F5 定調後，依附錄 C、D 實作。
7. **tech-architect**：請抽驗本檔後再交 CEO 驗收。
