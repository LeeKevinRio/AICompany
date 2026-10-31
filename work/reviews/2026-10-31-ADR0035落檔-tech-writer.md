# ADR-0035 落檔

- 審查者：tech-writer
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

ADR-0035 已落檔，是新增檔案，我沒有改其他任何檔案。
- 路徑：`/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`
- 行數：301 行（Grep 計數）。
- 寫入前我用 Glob 確認過 `docs/adr/0035-*` 不存在，現有只到 0034。
- 格式比照 0034：檔頭、Context、Options、Decision、Consequences、待決、附錄。
- 狀態填 `accepted`，依據寫 CEO #83、#86、#88（2026-10-31）。#84、#85 寫在 Decision 9。
- 標明補充 0033 與 0034、不取代，兩份原文不改。
- #87 只在「與 ADR 的關係」中提到，並連結決策包第 107 行，沒有展開。
- 0033 C-10 第二句寫為 N-166 的範圍約束，與本 ADR 不衝突（Decision 10）。
- `SAME_DAY_EARLIER_ENTRY_NOTE` 與 `SETTLEMENT_BATCH_ALREADY_FILLED_NOTE` 只寫識別名，並註明「逐字由風控定稿，僅放 `wording.py`，風控核可前不得合併」（目前風控審查中）。
- 偵測 SQL 沒有收錄，指向 [TA1] 第二節。

## 各部門回報

- **tech-architect**：草案與追加兩份評估都是 B 類轉錄，沒有補任何草案沒寫的技術細節。
- **CEO**：#83～#88 與 coordinator 定案，逐項對照決策包第 101～108 行轉錄。
- **風控**：兩句新字面尚未定稿，已列為待決與合併門檻。
- **tech-writer 自己**：我沒有讀 code。文內 `檔案:行號` 都是 [TA1]、[TA2] 的快照，檔頭已註明未逐條重驗。

### 對草案的修訂與我做的判斷

1. **Decision 6 的措辭**：草案寫「結算端不改」，與 G1 會改 `claim_directive` 與 `settle_pending` 相衝。我改成「除 6′ 的 G1 外不改」，並註明依據是 [TA2] 對 N172-C8 的修訂。
2. **Decision 編號**：保留草案 1～10，另加 6′（G1）。Decision 5 明定採 S-α，揭露觸發條件是「清單含 R 系列 buy 且 `mode != "normal"`」，不得比對 `FROZEN_NOTE` 字串。另外新增 11（字面規則）、12（排序與拆分）、13（指向附錄）三條，內容都來自任務單與 coordinator 定案。
3. **Decision 8**：改寫為「K3 與 N-176 合併，另立 ADR-0036，K3 不得早於 N-176」。
4. **Decision 9**：依 #84、#85 寫入偵測、R-3 工具、`playbook_adjustments`、D-A′／D-B／D-C／D-D 只揭露、EMERGENCY 舊列不清並由讀取側去重。偵測類別含 [TA2] 新增的 D-G。
5. **0034 Decision 9**：依 [TA1] 轉錄為「本 ADR accepted 時視為滿足」。
6. **Options 區**：納入 (a)～(g) 方案表、S-α～S-δ 表、「後補 bar」封堵情境表、D-A～D-G 與 R-1～R-4 表。

## 驗證

**檔案**：新增 `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`，301 行。

**核對結果（以原文逐條對照）**
- **N172-C1～C11**：11 條全收，在附錄 B。C8 用 [TA2] 修訂版，並註明原版已被取代。
- **N172-T1～T21**：21 條全收，在附錄 C。T1～T16 來自 [TA1]，T17～T21 來自 [TA2]。
- **VETO**：附錄 D 收了 [TA1] 的 6 條、[TA2] 追加的 3 條。
  - [TA1]：(b)、(c)、(d1)、(d2)、R-1／刪列／改 status、`confirm-rules` 充當修復。
  - [TA2]：S-δ、K3 早於 N-176 單獨上線、G1 沿用 `missed`／新增狀態／改 `settle()`。
- **V1～V6、N-174(c)**：收在 Context 表。
- **R-1～R-4**：收在 Options 表。

**我實際讀過或查過的**
- 兩份 TA 評估全文，以及決策包第 94～108 行。
- 0033 附錄 A 與 C-1～C-11，並用 Grep 確認 F2、F4 確實在附錄 D。
- 0034 全文，作為格式範本。
- Glob 確認 `work/repro/test_n172_repro.py`、`test_n174_repro.py`、`test_n176_repro.py` 與兩份 qa 報告存在。

**佐證清單的性質**：本檔全為 B 類轉錄，每項宣稱的來源都在文內標出（[TA1]、[TA2]、[決策包] 第幾行、CEO 編號）。快照是 2026-10-31、工作樹 `product/stock-desk`。我沒有對應的 git commit hash，因為沒有讀 code。抽驗請以內容定位。

**發現的小事**
- [TA1] 原把 qa 草稿測試列在 scratchpad 且未 commit，[TA2] 才列為 `work/repro/`。我採用 `work/repro/` 路徑，這三個檔案確實存在。
- [TA1] 引的 `0033:行號`、`0034:行號` 沒有沿用，一律改引條號。

## 下一步

1. **風控**：給兩句新字面逐字定稿。這兩句都是合併門檻，其中 `SAME_DAY_EARLIER_ENTRY_NOTE` 是 CEO #86 明列的門檻。
2. **coordinator**：
   - commit 這個新檔，並同步 ADR 索引。我沒有查 0035 之前是否有索引檔，0034 落檔時 `docs/adr/` 沒有。
   - 確認暫行緩解的 CEO 裁定結果。[TA1] 草案列為 CEO 事項 9，但決策包 #83～#88 沒有記錄，檔內寫為「待查證：向 coordinator 確認」。
3. **tech-architect**：確認 Decision 6 的措辭，以及我新增的 Decision 11～13 是否符合草案原意。
4. **qa-automation**：重現 V2、V3、V5、週三早上窗口、F8，並在 N-166 合併後重跑 F7。在重現前，這些在檔內都標為讀碼判定。
5. **後續**：
   - dev-lead 依附錄 B、C 實作 N-172a（等 N-166 合併後），偵測腳本可立即開工。
   - ADR-0036（在途單生命週期）尚未起草。
   - 本 ADR 交 tech-architect 確認正確性，再交 CEO 驗收。
