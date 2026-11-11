# 凍結前三題收尾裁示（v3.2 待 TA 結案）

- 審查者：tech-architect
- 日期：2026-11-11
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
三題都已收尾，只有裁示，不改規格本體：第 1 題確認 dev-lead 的讀法，第 2 題確認推得的指令並補一句定義，第 3 題確認不必改。沒有發現插隊類問題。

## 各部門回報（tech-architect）

**1. B-5 禁止條款的範圍：確認 dev-lead 的讀法**
- **裁示**：範圍是整個 `app/api/playbook.py`，包含 confirm-rules 的拒絕對映和 `/today`。只看名單端點的函式不夠。
- **理由**：§0 規定名單端點就寫在這個模組，以檔案為範圍才能用 grep 檢查，不必判斷「哪些函式算名單端點」。這樣也比較嚴，不會跟 ADR-0043 D7 (a′) 衝突。
- **qa 怎麼檢查**：對 `apps/stock-desk/backend/app/api/playbook.py` grep `HTTPException`，以別名 import 的也算在內。每一處都必須帶 `detail=`，值是物件，不能是 `None`。只要一處不符就判 BLOCKING。

**2. N210b-M 中 N-209 那一條指令：確認 dev-lead 的寫法**
- **裁示**：用 `git merge-base --is-ancestor <M_209> <N-210b 的 base> 2>&1; echo "exit=$?"`，必須是 `exit=0`。`<M_209>` 就是 §9.3 錨點登錄由 coordinator 記下的那個完整 40 碼 merge commit。如果 N-209 回退後重新合入，就改用新的 merge commit。
- **理由**：這條是把我 RC-103 確認檔「對實作的約束」第 3 點「base 也必須含 N-209」寫成可執行的指令，形式跟 `<M_198>` 那條和 M1 一致。加上 `2>&1` 只是為了把輸出完整附上，語意不變。
- **qa 怎麼檢查**：N-210b 的 PR 說明裡要有兩條原樣輸出（`<M_198>`、`<M_209>`），兩條都是 `exit=0`，而且 `<M_209>` 和錨點登錄逐字相同。qa 只判讀，不自己執行。

**3. N-212 中 payload 為 SQL NULL 的情形：確認不必改**
- **裁示**：p1、p2、p3 都不必改。
- **理由**：`NULL <> 'object'` 的結果是 NULL，所以這一支不成立，會落到下一支的「套預設值」，推論正確。不過 `app/playbook/store.py:105` 在唯一的 `CREATE TABLE` 裡把 `payload` 定為 `TEXT NOT NULL`，所以 payload 不可能是 SQL NULL。
- **qa 怎麼檢查**：在 `app/` 下 grep `playbook_rule_params`，確認建表只有 `store.py:103-109` 這一處、`payload` 仍是 `TEXT NOT NULL`，而且沒有任何 `ALTER` 或第二份建表語句。

## 驗證
- 讀過：凍結令、v3.2 交件第四節、v3.2 規格 :809-810 與 :916-929、RC-103 確認檔 :100 與 :134 與 :150、N-212 修正回報、`app/api/playbook.py`（目前沒有任何 `HTTPException`）、`app/playbook/store.py:103-109`。
- 唯讀，沒有執行任何指令。第 3 題的 SQL NULL 行為是讀碼推論，**未實證**；但因為有 NOT NULL 約束，不需要另外補實證。
- 沒有讀 `.env`，沒有碰 `data/*.db`。

## 下一步
1. **coordinator**：把本裁示存成單頁裁示檔，在 v3.2 的「待 TA（v3.2）」記為結案，不改規格本體。
2. **qa-reviewer**：依上面三條「qa 怎麼檢查」核對。
3. **devops-sre**：N-210b 合併前執行 N210b-M 的兩條指令。

相關檔案：
- /home/user/AICompany/work/dispatch/2026-11-11-N207規格凍結與測試實證令-coordinator.md
- /home/user/AICompany/work/reviews/2026-11-10-N207實作規格v3.2-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-10-RC103確認與ADR0044註記-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-10-N212修正-data-engineer.md
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
