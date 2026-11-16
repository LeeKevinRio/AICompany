# copy_check 值域裁示

- 審查者：tech-architect
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
1. **`absent_both` 算通過值。** 補充六第 6 點 (a) 這樣讀：三行 `copy_check` 依固定順序對應 `.db`、`-wal`、`-shm`。第 1 行必須是 `SAME`，第 2、3 行各為 `SAME` 或 `absent_both`。
   - 原設計表（`work/reviews/2026-11-15-真實資料管線驗收一鍵檔設計-devops-sre.md` 第 131 行）就寫「三檔各一行，同 r2」，而 r2 本來就有 `absent_both`。所以「三行 `copy_check=SAME`」是我起草時寫得太窄，不是有意要求三檔都存在。
   - 這不算放寬：任何位元組或存在與否的差異，照樣 STOP（`copy_changed`）。
2. **兩邊值域一致，新檔更窄。** r2 的 `compare_copy` 有四個值：`SAME`、`absent_both`、`PRESENCE_DIFFERS`、`DIFFERENT`。新檔的 `copy_db_files`（第 505–526 行）只印 `SAME` 和 `absent_both`，其餘兩種情況改成 STOP，不印。白名單在第 383 行，樣式為 `copy_check=(SAME|absent_both)`。
   - 「兩邊都不存在」的定義一樣。唯一的形式差異：r2 每行帶檔名（`<name>: <verdict>`），新檔不帶，靠 `DB_FILES` 的固定順序認是哪一檔。
3. **需要寫附記三。** ADR 字面與實作衝突，依章程以 ADR 為準，不補的話 CG-2 會誤判。全文附在下面。
4. **另外兩條自定解讀都可以接受。**
   - 第 3 條：可接受。通過要靠回貼證據（第 6 點 (a)），沒有回貼檔就是沒通過，不會誤判；這也和 RC-166「沒有產生回貼檔」一致，還少一個落檔面。
   - 第 5 條：可接受。`p0`、`p1` 刪不掉，照補充六第 3 點處理：不影響通過，但 CG-2 前要重跑取得 `cleanup=ok`，而且不得開啟該資料夾。殘留 `copy` 刪不掉就 STOP，比 RC-158c 更嚴，屬收緊。

## 各部門回報
- **tech-architect**：我讀了交件報告、ADR-0030 補充六／附記／附記二、`pipeline_acceptance_real.py` 第 270–284、383、490–526 行、`r2_first_run.py` 第 219–233 行，以及 CEO 說明第 78 行。說明文件只寫 `copy_check=`，沒寫值，不用改。
- **附記三全文**（交 tech-writer 或 coordinator 逐字落檔）。
  - 檔頭插在第 13 行之後：
```
- 補充紀錄：2026-11-16 append 補充六附記三（第 6 點 (a)「三行 `copy_check=SAME`」的讀法：`-wal`、`-shm` 在主 DB 與複本都不存在時印 `absent_both`，也算通過；tech-architect 裁示，更正起草時寫得太窄的字面，判定強度不變，不改使用者面字面、規則檔、定義物件與已登記雜湊，不改 `app/`，CEO 可推翻；來源 `work/reviews/2026-11-16-一鍵檔外層流程交件-devops-sre.md` 自定解讀第 1 點）。
```
  - 檔尾新增一章：
```
---

## 補充六附記三：`copy_check` 的值域與第 6 點 (a) 的讀法（2026-11-16）

- 決策者：tech-architect。來源：`work/reviews/2026-11-16-一鍵檔外層流程交件-devops-sre.md`（自定解讀第 1、3、5 點）；另讀 `scripts/pipeline_acceptance_real.py` 的 `copy_db_files` 與白名單、`scripts/r2_first_run.py` 的 `compare_copy`、`work/reviews/2026-11-15-真實資料管線驗收一鍵檔設計-devops-sre.md`（「三檔各一行，同 r2」）。
- 性質：更正補充六第 4 點 (a) 與第 6 點 (a) 起草時寫得太窄的字面，判定強度不變。與補充六、附記、附記二衝突時，以本附記為準。

1. **值域**：`copy_check` 恰好三行，依序對應 `stock-desk.db`、`-wal`、`-shm`。每行的值只能是 `SAME`（兩邊都存在，且複製前、複本、複製後三個 sha256 相同）或 `absent_both`（主 DB 與複本兩邊都不存在）。存在與否不一致或位元組不同時，一律 STOP（`copy_changed`），不印成 `copy_check` 行。這是 r2 `compare_copy` 值域的子集。
2. **第 6 點 (a) 的讀法**：「三行 `copy_check=SAME`」讀為：恰好三行，依上述順序；第 1 行必須是 `copy_check=SAME`；第 2、3 行各為 `copy_check=SAME` 或 `copy_check=absent_both`。主 DB 乾淨關閉時，回貼是一行 `SAME` 加兩行 `absent_both`，也算通過。
3. **另兩項確認**：STOP 與 ERROR 時不產生回貼檔，視為「沒有通過證據」。上次殘留的 `p0`、`p1` 刪不掉時回貼 `cleanup=FAILED`，依補充六第 3 點處理。上次殘留的 `copy` 刪不掉時，依附記第 3 點 STOP。
4. **CEO 可推翻**，推翻時改採：主 DB 必須三檔都存在，否則新增 STOP 種類，並重送風控修訂 STOP 對照表。

- **S-13e（逐條可檢查）**：白名單的 `copy_check` 樣式只接受 `SAME|absent_both`（測試）；主 DB 只有 `.db` 時，三行依序為 `SAME`、`absent_both`、`absent_both`（測試）；`-wal`、`-shm` 都存在時三行都是 `SAME`（測試）；主 DB 缺 `.db` 時，在 `copy_check` 之前就 STOP（`test_stop_no_db`）；qa 依第 2 點判讀 CG-2 前的回貼。
```

## 驗證
- 全程唯讀。沒讀 `.env`，沒碰任何 `*.db`，沒跑任何程式。
- 結論來自直接讀程式碼和 grep，沒有實際執行測試。
- S-13e 中「兩檔都存在」與「只有 `.db`」的對應測試，我沒逐一找到測試名稱。交件報告的合成回貼呈現了只有 `.db` 的結果，但測試要由 qa 確認，沒有就請 devops-sre 補上。

## 下一步
1. tech-writer 或 coordinator 把上面兩段逐字落檔到 `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`。
2. qa-reviewer 審這個 PR 時，加核 S-13e，並依附記三第 2 點判讀 CG-2 前的回貼。
3. 我判斷不用重送風控：使用者面字面、輸出可見範圍、對主 DB 的限制都沒變。若 coordinator 認為要送，我不反對。
