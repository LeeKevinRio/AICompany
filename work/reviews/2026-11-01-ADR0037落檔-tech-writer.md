# ADR-0037 落檔

- 審查者：tech-writer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

ADR-0037 已落檔，狀態為 `proposed（待 CEO 核可）`。落檔前用 Glob 確認過 `docs/adr/0037-*` 不存在。我沒有改其他檔案，沒有讀 `.env`，也沒有碰 `data/*.db`。

檔案：`/home/user/AICompany/docs/adr/0037-stock-desk-排程台出清流程的狀態擁有層.md`

- 檔頭沿用 0035 的格式：標題、狀態、日期、決策者、來源簡稱、與既有 ADR 的關係、適用範圍、標註。
- 草案主文（Context、Options、Decision、Consequences、待決）照轉錄，沒有補任何技術細節。
- 檔頭下方加了「落檔註記」，記了兩件事：
  - Q15 由風控裁示採方案 D，依據 `work/reviews/2026-11-01-Q14四項Q15與PRDv5確認-風控.md`。
  - 初稿原用 0036 編號，0036 已由 ADR-0035 預留，所以改用 0037。這是 coordinator 定案（2026-11-01，CEO 可推翻）。決策包 `work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 第 116 行有這筆紀錄，我用 Grep 確認過。
- 落檔註記另外說明了三件事：本檔屬 B 類轉錄；文內 `檔案:行號` 未重驗；來源檔的「2. FE-2 寫法比較與建議」與「3. info」兩節未收錄。
- FE-C、FE-T、VETO 三份清單收進附錄 A、B、C。

## 各部門回報

- tech-writer（本人）：只做落檔。
- 其他部門：本次沒有動作。

## 驗證

- 檔名：`0037-stock-desk-排程台出清流程的狀態擁有層.md`，在 `docs/adr/` 下。
- 行數：260 行（Grep 計數）。
- 收錄核對：
  - FE-C1～FE-C23：附錄 A 共 23 條，Grep 計數 23。「改」「新」標記、巢狀條列與條文都照來源，沒有增刪。
  - FE-T1～FE-T14：附錄 B 共 13 個條目，因為來源本來就把 FE-T6 與 FE-T7 合成一條（「FE-T6、FE-T7 不變」）。展開後是 FE-T1～FE-T14 全數涵蓋。順序照來源，FE-T12（qa-e2e）放在 node 環境清單之後。「建議（不阻擋）」一段也收了。
  - VETO-1～VETO-5：附錄 C 共 5 條，Grep 計數 5。
- 限制：核對方式是 Grep 計數加條號列舉，再對照來源讀過的內容。我沒有做逐字 diff 工具比對。
- 佐證（B 類）：全部內容來源是 `work/reviews/2026-11-01-ADR0037D版與FE2評估-tech-architect.md` 第「1. ADR-0037 修訂草案」一節（2026-11-01，tech-architect）。檔頭 Q15 註記來源是風控檔，編號變更來源是決策包第 116 行。
- 沒有 A 類宣稱。草案內的 `mutation.ts:246`、`mutationObserver.ts:164` 等行號是 tech-architect 的快照，我沒有重驗。來源也自述結論皆為讀碼推論，且 tech-architect 沒有 Bash，無法 `git show` 兩個分支。

## 下一步

- coordinator：commit 這個檔案，並同步 ADR 索引（我沒有動索引）。0035 檔尾也註明「ADR-0036 尚未起草」，0036 的實際起草留給日後處理。
- CEO：核可 ADR-0037。
- risk-compliance-officer（來自草案「待決」）：
  - 裁定「送出中離開頁面、之後請求失敗」是否需要揭露。
  - 裁定出清 mutation 的 `networkMode` 是否改為 `'always'`。
  - 知悉 FE-C8 的「對話框開著時延後捲動」。
- frontend-engineer：核可後依 FE-C1～FE-C23 把 `fix/stock-desk-exit-feedback` 從 A 遷到 D。
- tech-architect：落檔註記第 4 點說明行號未重驗。核可前，可以請他抽驗幾條關鍵行號，例如 `mutation.ts:246-251`、`mutationObserver.ts:164`。
