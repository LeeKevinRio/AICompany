# ADR-0033 落檔

- 審查者：tech-writer
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

ADR-0033 已落檔，狀態 `accepted`，依據 CEO #76（方案 (d)）和 #77（凍結日取 max），皆為 2026-10-29。

- 落檔前用 Glob 確認 `docs/adr/0033-*` 不存在。我另外在 `docs/` 內 grep `0033`，也沒有結果。
- 格式比照 0032 和 0031：標題、狀態、日期、決策者、來源簡稱、與既有 ADR 的關係、標註約定，接著是 Context、Options、Decision、Consequences、待決，最後是附錄 A～E。
- #77 的 max 規則寫在 Decision 3。
- Consequences 寫明「會延長凍結期（CEO #77），須揭露，揭露字面由風控定稿」。同一天純重複呼叫的 max 值相同，不延長，這點也有寫。
- 字面規則寫在檔頭和 Decision 8：
  - `EMERGENCY_EXIT_ALREADY_PENDING` 與延長揭露句的實際文字都沒有寫進 ADR。
  - 只寫「新字面僅放 `wording.py`，風控核可前不得合併」。
  - 是否掛 `EXIT_ATTRIBUTION`，以及揭露放哪些位置，都寫「依風控裁定」。
- 草案裡寫「待 CEO 決策」的地方都改成已決：
  - Options 多了一張凍結日表：max 為採用，「純重複時不延長」為未採，理由是 `exit_confirm` 要跟著改。
  - 附錄 B 的 F-T3 補註「凍結日被延長為新算值」。
  - 「待決」一節標明 CEO 已裁，風控仍未經手。
- 檔頭「標註約定」寫明本檔是草案轉錄，屬 B 類，行號是 2026-10-29 的快照。
- 我沒有改任何其他檔案，也沒有動 accepted 的 ADR。我沒有讀 `.env`，沒有碰 `data/*.db`。

## 2. 各部門回報

- **tech-writer（本人）**：只新增 ADR-0033 一個檔案。
- **tech-architect**：草案是唯一的技術內容來源。
- **risk-compliance-officer**：尚未經手。要定稿的有三項，ADR 的「待決」一節都列了：
  1. `EMERGENCY_EXIT_ALREADY_PENDING` 字面。
  2. 該句是否掛 `EXIT_ATTRIBUTION`。
  3. 延長凍結的揭露字面與放置位置。
- **CEO**：#76、#77 已裁。我在 `work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 第 92、93 行看到裁定原文，與任務單一致。
- **其他待辦（已寫進 ADR 待決）**：
  - dev-lead：依附錄 A、B 實作。
  - product-manager：依附錄 C 撰寫 NB-6。
  - frontend-engineer：建議把 `invalidateQueries` 改到 `onSettled`。

## 3. 驗證

- 檔案：`/home/user/AICompany/docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md`，239 行（以 Grep 計數）。其後我只改了其中一句措辭，行數不變。
- 收錄情況：
  - **C-1～C-11**：全部收錄，在附錄 A，逐條轉錄。
  - **T-1～T-6**：全部收錄，在附錄 B。
  - **F-T1～F-T6**：全部收錄，在附錄 B。API 測試（連 POST 兩次、不得出現 409）也一併收錄。
  - 另外收錄：Q1 現況判定（Context）、Q2 方案比較（Options）、Q5 的 500 狀態表（附錄 C）、F1～F4 範圍外發現（附錄 D）、相關檔案（附錄 E）。
- **字面檢查**：
  - 我確認過兩句新字面的實際文字沒有進檔，只出現識別字（`EMERGENCY_EXIT_ALREADY_PENDING`、`EXIT_ATTRIBUTION`）。
  - 自檢時發現草案有一句描述性的「已有待執行出清」，很接近字面，所以我改成只寫 `ALREADY_PENDING 那一支`。
  - 文中引用的 `EMERGENCY_EXIT_RESULT`、現行歸屬句「本次操作中提交」和「已產生 N 批」，都是既有字面。
- **佐證清單（B 類）**：
  - 全部技術敘述的來源是 [TA]（`work/reviews/2026-10-29-N166出清重複呼叫防護評估-tech-architect.md`，2026-10-29 版）。
  - 決策依據是 [決策包] 第 92、93 行（#76、#77）。
  - 行號是草案的快照，抽驗時請以內容定位。
  - 我沒有補任何草案沒寫的技術細節。
- **A 類抽驗**：
  - 我對照 code 抽驗了兩處：`apps/stock-desk/backend/app/playbook/service.py` 的 `emergency_exit`，和 `apps/stock-desk/backend/app/playbook/store.py` 的 `freeze_emergency`。我沒有確認 commit，所以這是工作樹當下的快照。
  - 抽驗的是這些敘述：
    - `freeze_until` 由 `calendar.shift(as_of, params.emergency_freeze_trading_days)` 算出；
    - 批次只篩 `status`／`remaining_shares`；
    - 先 `apply_effects` 再 `record_directives`；
    - `freeze_emergency` 是直接覆寫。
  - 結果：這些敘述與草案一致。
  - 草案其餘行號沒有逐條重驗，ADR 檔頭已如實註明。
  - 沒有發現草案與 code 矛盾，所以沒有要回報給負責部門的不一致。

## 4. 下一步

1. **risk-compliance-officer**：審兩句新字面和歸屬語掛不掛，並定稿延長凍結的揭露字面與放置位置。這是擋合併項。
2. **coordinator**：
   - 處理 commit。依附註，commit message 結尾要加 Co-Authored-By 與 Claude-Session。
   - 本任務沒有 Bash，也沒有 commit。若有 ADR 索引需要同步，也由 coordinator 處理。
   - 建議 commit 訊息：`docs: 新增 ADR-0033 EMERGENCY_EXIT 重複呼叫的覆蓋判定式冪等`。
3. **tech-architect**：確認落檔內容與草案轉錄無誤（來源部門確認），再交 CEO 驗收。
4. **dev-lead**：依附錄 A、B 開工。風控字面核可前不得合併。
5. **product-manager**：依附錄 C 寫 NB-6。
6. 附錄 D 的 F1～F4 另開追蹤項。
