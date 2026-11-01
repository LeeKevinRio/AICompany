# 出清畫面 PRD v5.4（AC-67 揭露地板、風險 26）

- 審查者：product-manager
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

PRD 已修為 v5.4（狀態 spec），只改了 `/home/user/AICompany/work/prd/2026-10-29-出清後回饋畫面-N164N165.md`。依 tech-architect〈ADR-0037 補充一〉S-1，三項都做完，沒有自擬任何使用者可見字面。

1. **風險 25 收斂，新增 AC-67（阻擋條件）。**
   - 不變式 INV-1：出清 mutation 為 success，就代表該次回應已寫入 store。`onSuccess` 不吞例外，`accept()` 先提交再通知訂閱者。
   - AC-67 四種情境：
     - (a) 正常：對話框關閉，橫幅出現。
     - (b) 寫入同步拋出：顯示 NB-6，對話框不得關閉，送出鎖釋放，面板不含例外內容。`cancelQueries` 與 `invalidateQueries` 各恰好 1 次。
     - (c) 訂閱者拋出：橫幅仍出現，不得顯示 NB-6。
     - (d) mutation reject：顯示 NB-6。
   - 總地板：逐 frame 取樣，任何情況都不存在「2xx 已到、對話框已關、整頁沒有橫幅也沒有失敗面板」。
   - 源碼檢查項：`onSuccess` 不含 try／catch，不得用頁面旗標或比對 `receipt.seq` 決定關閉對話框，失敗面板不呈現例外內容。
   - mapping 表原「待 tech-architect 收斂後補」已改為指向 AC-67。
2. **記錄已知代價（新增風險 26）。**
   - 前端內部錯誤（例如 store 的 reducer bug）也會顯示 NB-6，使用者可能因此重送。
   - 重送時後端回 S1，不會重複產生指令（N-166、ADR-0033）；S1 須維持風控核可版字面。
   - 另記錄一個組合：定義層 `onSettled` 在 success 路徑拋出時，橫幅與 NB-6 會同時存在。兩者皆為真，可接受。
3. **「出清 POST 沒有用戶端逾時」列為範圍外、另案處理。**
   - 已寫入範圍外清單，風險 24 的「附帶」同步指向範圍外。
   - 逾時後走 NB-6，由 tech-architect 評估，不納入本包 FR、AC 與工期。

順帶補強一處：tech-architect 的 FE-C24 把出清 options 的禁用鍵由 `retry`、`scope` 擴大為再加 `retryDelay`、`mutationKey`，我已同步寫入 FR-8a 與 AC-65。

## 各部門回報

本次只有 PM 作業，沒有其他部門參與。PRD「交接」已更新如下。

- **風控：** 知悉 INV-1、失敗面板不呈現例外內容（用戶端例外落入同一支 NB-6，不新增字面）與已知代價。
- **frontend-engineer：** 依補充一的 FE-C4 (a)～(g) 實作，依 FE-T13(c1)～(c5) 改寫並新增測試；FE-C24 已符合，不用改。
- **tech-architect／coordinator／tech-writer：** 補充一全文的存放位置，以及 ADR-0037 檔頭補充行，由 coordinator 與 tech-writer 處理。
- **qa：**
  - qa-reviewer 實查 FE-C4 (b) 的提交順序、FE-C24 的四個禁用鍵、FE-T13(c4) 的矩陣。
  - qa-automation 把 FE-T13 與離線守門測試列常駐。
  - qa-e2e 驗 AC-67 的 (a)(d)。

## 驗證

- 這次只有補強，沒有刪除或降低任何既有驗收條件，已逐項列入變更紀錄 v5.4。
- **請你確認一個程序問題。** tech-architect 提醒：補充一改到 ADR-0037 Decision 2 的「包 try/catch」字樣，屬決策條文，而 ADR-0001 規定生效後不得原地改寫。
  - 他已比照 ADR-0033 先例寫成補充，建議 CEO 知悉；CEO 若要求依 ADR-0001 開新 ADR，他可改寫為 ADR-0038。
  - 這不在 PM 範圍，我只記在風險 25 的程序備註，請 coordinator 轉達 CEO。
- AC-67 的 (b)(c) 需要注入寫入失敗，只能由 node 單元測試驗證，因為本產品前端測試環境沒有 jsdom。qa-e2e 只能驗 (a)(d) 的畫面。
- 判斷的性質：
  - INV-1 的控制流、`accept()` 的內部順序，都是 tech-architect 的讀碼推論，沒有實測；他沒有 Bash，也沒讀到分支上的程式碼。
  - AC-67 就是驗證，FE-T13(c1)～(c5) 的測試要補上。
- 我沒有跑任何程式，沒有讀 `.env`，也沒有碰 `data/*.db`。

## 下一步

1. frontend-engineer 依補充一修改並補測試；qa-reviewer 實查。
2. coordinator 與 tech-writer 處理補充一全文的存放位置與 ADR-0037 檔頭補充行。
3. 請 coordinator 轉達 CEO 知悉補充一，必要時決定是否改開 ADR-0038。
4. 其餘待辦不變：Q13；art-lead A-1 與 r3.2 書面核對；N-171 PRD 帶入 C-3 驗收條件；出清 POST 用戶端逾時另案評估。

檔案：`/home/user/AICompany/work/prd/2026-10-29-出清後回饋畫面-N164N165.md`
