# 出清畫面 PRD v5.1（Q15、FR-13g、Q12、風險 17）

- 審查者：product-manager
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

PRD 已修為 v5.1，只改了 `/home/user/AICompany/work/prd/2026-10-29-出清後回饋畫面-N164N165.md`。依 tech-architect 的 Q14 評估，四項都做完了，沒有自擬任何使用者可見字面。frontend-engineer 已開工並知道這些是暫定，PRD 內已逐項標「暫定，待風控」。

1. **新增 Q15：** 「離開 `/playbook` 再回來」是否視同重新整理。
   - 暫定答案為視同、回執結束（方案 A），待風控確認。
   - FR-4 已加註。新增 AC-64（暫定）：離開再回來後橫幅不存在，且回執未寫入 sessionStorage、localStorage、IndexedDB、cookie、URL 或 `history.state`（tech-architect VETO-3）。
   - 若不視同，改採 Providers 範圍的獨立 store（方案 D），須重審 FR-12b、FR-3。
2. **新增 FR-13g、AC-62、AC-63**，承接 FE-C20 的焦點交接。
   - 三項必須同時成立：對話框沒開；舊觸發鈕在卸載時持有焦點；commit 後焦點已落到 `<body>`。
   - 成立時把焦點移到新觸發鈕，並使用 `preventScroll`。缺一項就不交接，除此之外不得新增任何焦點移動。
   - AC-62：驗成立情境。
   - AC-63：驗三種不成立情境，焦點在別處、對話框開著、舊鈕沒持有焦點。
   - FR-13f「不新增新的焦點行為」的限定，以 FR-13g 為唯一例外。
   - AC-62 納入 tech-architect 建議的情境「關閉後 `/today` 才恢復」。
3. **關閉 Q12：** 用 tech-architect 報告第 2、4 點回答，已收進 FR-14c、FR-14e、AC-52、風險 17 與 18。
   - `dataUpdatedAt` 可作 R-4 依據，有三個前提，評估時機有四類。
   - 比對寫在 layout effect，並在 effect 執行當下讀送出鎖，可保證送出中不會觸發 R-5。
4. **更新風險 17：**
   - `invalidateQueries` 只有 query 已有 data 時才取消飛行中的請求；首次載入中沒有 data 時不取消。
   - 這更正了風控與 PM 原先的讀碼推論。
   - 缺口已用 FE-C13 補上：`onSettled` 先 `cancelQueries` 再 invalidate，兩者都不 await。
   - AC-55 的說明同步更正，並補一條「cancel 過程中維持 pending、送出結束不等 `/today`」。

額外補的內容，請確認是否合適：
- **新增 Q16。**
  - 內容：tech-architect 明列需風控確認的兩項，逐句相同時更新 `heldAt`；送出前檢查到 R-4 時，把這次送出點擊轉為退回第 2 步、不送出。
  - 理由：我不能把它們當作已定案寫進 Q12 關閉的結論。
  - 暫定採其做法，已寫入 FR-14c、AC-52。
- Q14 標為「已評估（暫定）」。
  - 採頁面層 reducer。
  - VETO-1～3 的產品面約束收進 FR-12(d)。
  - FE-C1～C20 與 FE-T1～T12 引用其報告，PRD 不重複寫。

## 各部門回報

本次只有 PM 作業，沒有其他部門參與。PRD「交接」已更新如下。

- **風控：** 請確認 Q15、Q16 兩項、FR-13g 知悉，並知悉 invalidate 的更正。Q13 仍待你答覆。
- **tech-architect：** Q12 已答，Q14 已評估。請確認 AC-62、AC-63 與你的 FE-C20 三項條件一致。ADR-0036 草案交 tech-writer 落檔，待 CEO 核可。
- **qa-e2e：** 執行 FE-T12。V-12、V-38(c) 增加情境「關閉後 `/today` 才恢復」。
- **qa-automation：** FE-T6（函式庫契約測試）列入常駐，作為套件升級時的守門測試。

## 驗證

- 用 Grep 檢查過 Q12 的殘留敘述。現行條文都已更新為已關閉，殘留的「開放」字樣只在 v4、v5 的變更紀錄裡，屬歷史。
- 這次只有收緊或補強，沒有放寬任何驗收條件，已逐項寫入變更紀錄 v5.1。
- tech-architect 的內容全是讀碼推論，沒有實測，包括 `cancelQueries` 的行為與 React commit 順序。FR-13g 無法在 node 環境驗證，必須由 qa-e2e 實機實測；不成立時只是退回現狀，不會更糟。
- **有一處衝突我沒有自行決定：** tech-architect 建議焦點交接在三家瀏覽器實測，但 PRD 範圍外寫明「不做 Safari、Firefox 驗收」。
  - 我維持以 headless Chromium 驗收。
  - 已記為風險 23 與 AC-62 備註。
  - 若要擴大驗證範圍，請 coordinator 另行指示，並同步修改範圍外條款。
- 我沒有跑任何程式，沒有讀 `.env`，也沒有碰 `data/*.db`。

## 下一步

1. **請 coordinator 把 v5.1 送風控確認。** 我無法自行派工送審。請對照變更紀錄 v5.1、開放問題 Q15 與 Q16、以及 AC-62～AC-64。
2. 風控答覆 Q15、Q16、Q13。
   - 若 Q15 裁定不視同重新整理，PM 改 FR-4、AC-64，並重審 FR-12b；tech-architect 改評估方案 D。
   - 若 Q16 任一項被否決，改 FR-14c 與 AC-52。
3. coordinator 決定驗證瀏覽器範圍：維持 Chromium，或擴大。
4. ADR-0036 待 CEO 核可。

檔案：`/home/user/AICompany/work/prd/2026-10-29-出清後回饋畫面-N164N165.md`
