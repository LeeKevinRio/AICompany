# 補充六附記與登記條件確認

- 審查者：tech-architect
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. 「補充六附記」全文在下方，可以逐字落檔。它做了四件事：
   - 收緊第 1 點 (b)，落實 RC-158a/b/c；
   - 落實 RC-160c 與 RC-162；
   - 採用 RC-163；
   - 依 RC-165 解除第 8 點的限制，改成第 6 點列出的四項執行前提。
2. 區塊五最後一句：**可以用**。前提是 CG-2 PR 遵守附記第 7 點 (a)～(e)。CG-2 若想加入任何會因 `provisional_results_seen = 1` 而拒絕登記的條件，要先修 ADR，刪掉這一句，再重送風控。

## 各部門回報

### tech-architect

**第 2 題的核對結果（現行程式，product 分支）**
- `claims.py:190-195`：參數限定 `choices=("0","1")`。`:308` 只做轉 bool，`register()` 沒有任何依這個值拒絕的分支。
- `store.py:758-759`：只檢查型別是 bool。`schema.py:195` 的 CHECK 是 `IN (0, 1)`。
- `tests/test_forecast_claims_cli.py:137`：用 `"1"` 登記，結果是 `EXIT_OK`，而且會寫進資料列。
- 在 `app/` 內 grep：recorder、report、scoring 都沒有讀這個欄位，所以 CG-2 的閘門不受影響。
- 補充四第 2 點的五個 bootstrap 條件，以及 R-1～R-8，都沒有對這個值設條件。R-8 只規定由 CEO 鍵入。

結論：現行規則不會擋住登記。

要注意一個細節：「日後報告照實揭露」目前還只是 D-1 第 2 點的義務，`report` CLI 現在不會印出這個值。不過值會永久存在登記表，補充一的 trigger 也禁止改寫，所以這句話不算不實。

**附記草稿中的判定**
- **RC-163 採用。** 它把第 6 點 (d) 從「檔案可以變」收緊成「位元組必須等於事先 commit 的內容」，沒有放寬任何東西。
- **RC-162 的殘餘問題。** 不是 Python 印出的文字不在機械保證範圍內，例如主控台回顯的 `^C`，或 `.cmd`、`.bat` 啟動時 cmd 自己印的中斷提示。這類文字不含資料。但區塊一寫的是「畫面上只會出現」，所以這點要請風控判斷是否需要補註。依 RC-164，我不改那段字句。

### 補充六附記全文

**檔頭**：插在第 11 行（補充六那一行）之後。

```markdown
- 補充紀錄：2026-11-16 append 補充六附記（風控 RC-158～RC-165 與 CEO #150 的落實：第 1 點 (b) 的檔案操作限制與適用範圍、複本刪除失敗即停止、失敗種類格式、畫面白名單的機械保證、規則檔位元組綁定、`provisional_results_seen` 在 CG-2 的處理；解除第 8 點限制；tech-architect 裁示，收緊不放寬，不改使用者面字面、規則檔、定義物件與已登記雜湊；來源 `work/reviews/2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md`、`work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` #150）。
```

**檔尾**：接在補充六章節最後一行之後。

```markdown
---

## 補充六附記：風控 Q-1、Q-2 確認條件的落實與第 8 點限制的解除（2026-11-16）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md`（APPROVE 附條件，RC-158～RC-165）；CEO #150（2026-11-16：「算，照這樣做」）。另讀 product 分支 `app/forecast/claims.py`、`store.py`、`schema.py`、`tests/test_forecast_claims_cli.py`。
- 性質：收緊補充六第 1、4、6 點，不放寬；解除第 8 點。不改本文與補充六原文，不改使用者面字面、規則檔、定義物件與已登記雜湊。兩者衝突時以本附記為準。

1. **第 1 點 (b) 的檔案操作（RC-158a）**
   - (a) 主 DB 的 `stock-desk.db` 與它的 `-wal`、`-shm` 只能以 `"rb"` 開啟，不得用其他任何模式開啟，也不得刪除、更名、取代、改時間戳、改權限、截斷或加鎖。這個限制同時適用於 `pathlib.Path` 的等價方法。
   - (b) S-13b 第 1 點的 e2e 監聽測試，擴充到下列呼叫：`open`／`io.open` 的模式、`os.open` 的旗標、`os.remove`、`os.unlink`、`os.rename`、`os.replace`、`os.utime`、`os.chmod`、`os.truncate`、`shutil.move`、`shutil.copy*` 的目的地、`msvcrt.locking`。判定方式是目標以 `samefile` 對三檔中任一檔成立就算命中。測試斷言三檔只出現 `"rb"` 開啟，沒有其他任何命中。
2. **適用範圍（RC-158b）**：第 1 點 (b) 的讀法只適用 D-7 真實資料那一次的 `scripts/pipeline_acceptance_real.py`。其他 tests、scripts 與 `app/` 都不得援引它讀取主 DB。既有探針的依據不受影響，但也不得改以 (b) 為依據。qa 審查清單加一行逐條核對。
3. **複本刪除失敗（RC-158c）**：第一次呼叫 `run_acceptance` 之前，複本任一檔刪不掉時，就印出固定的 ASCII STOP 句並以非零結束碼結束，不呼叫 harness。中文說明逐字採用風控定稿，放在說明文件的 STOP 對照表。測試方式：注入刪除失敗，斷言 harness 沒有被呼叫，而且輸出只有該 STOP 句。
4. **失敗種類（RC-160c）**：`failure_kinds` 維持去重、排序、不帶次數。測試涵蓋兩種情形：同一種失敗出現多次時只列一次；失敗發生的順序不同時，輸出相同。改成依出現順序或帶次數，都要重送風控並修本 ADR。
5. **畫面白名單的機械保證（RC-162）**
   - (a) 包裝程式第一個敘述就要做兩件事：把 `sys.excepthook`、`threading.excepthook`、`sys.unraisablehook` 都換成固定句；執行 `warnings.simplefilter("ignore")`。`app` 與 harness 一律在這之後才 import。
   - (b) 最外層攔截 `BaseException`（含 `KeyboardInterrupt`），只印固定句；`finally` 照常清除暫存，然後以非零結束碼結束，不繼續執行。
   - (c) 本點只適用這個包裝程式。補充四第 1 點 (b) 與補充五第 2 點規定 recorder 不捕捉 `BaseException`，兩者不衝突。
   - (d) e2e 測試擷取整段 stdout 與 stderr，斷言每一行都 fullmatch 白名單或固定的 STOP、ERROR 句。涵蓋的情境包括：正常結束、harness 拋出例外、執行緒例外、警告、注入 `KeyboardInterrupt`（取數中、harness 中、清理中）。
   - (e) 不在保證範圍內：不是 Python 行程寫出的文字，例如主控台回顯與殼層提示，以及直譯器層級的致命錯誤。
6. **第 8 點限制的解除（RC-165）**
   - 依據：風控對 Q-1、Q-2 判定 APPROVE 附條件，沒有 VETO；CEO #150 選第一項，所以 Q-2 不轉為 VETO。第 8 點與補充六檔頭的「待風控確認，確認前不得在 CEO 本機執行」，自本附記起解除。
   - 一鍵檔在 CEO 本機執行前，以下四項都要成立：
     - 一鍵檔 PR 已落實本附記第 1、3、4、5 點的測試；
     - qa PASS（含 Codex），CI 綠燈；
     - 說明文件逐字採用風控定稿（RC-164）；
     - coordinator 確認以上三項。
   - RC-159 至此履行完畢。RC-160a/b、RC-161a/b、RC-164 繼續有效。
7. **CG-2 的 `provisional_results_seen`（風控區塊五末句的使用條件）**
   - (a) `bootstrap --production` 與登記一鍵檔都接受 0 與 1。在其他條件成立時，兩個值都照常寫入並以 0 結束。補充四第 2 點與 R-1～R-8 不得新增任何依這個值拒絕的條件。
   - (b) 值在登記當下由 CEO 鍵盤鍵入。不得有預設值，不得寫死，不得取自檔案或環境變數，也不得設計只接受 0 的確認迴圈。輸入不是 `0` 或 `1` 時就停止，不寫入，不轉換。
   - (c) 兩列都寫入鍵入的值。提交後的唯讀核對，要加上「兩列的值都等於鍵入值」。回傳內容加一行 `provisional_results_seen=<0|1>`，供 RC-161a 的紀錄使用。
   - (d) 0 與 1 各有一個測試，都要登記成功、恰好 2 列、值相符；另加一個無效輸入的測試，斷言不寫入。
   - (e) 若要對 1 設任何阻擋，要先修本 ADR，由 coordinator 刪掉說明文件區塊五的末句，並重送風控。
8. **規則檔位元組（RC-163，採用）**：補充六第 6 點 (d) 的 `h3.yaml`、`h5.yaml`，只能是凍結包 §4.1、§4.2 在 `git_head` 已 commit 的逐字位元組。
   - CG-2 PR 的 M-5 測試，從 `git cat-file blob <git_head>:<凍結包路徑>` 抽出兩個區塊，與 YAML 的 blob 比對 sha256。抽取規則以常數寫明。
   - 凍結包本身從 `git_head` 起要零差異。

- **S-13c（逐條可檢查）**：第 1、3、4、5 點各款，各有上述對應的測試；第 2 點列進 qa 審查清單；第 7 點 (d) 與第 8 點列在 CG-2 PR 說明中，並附上測試名稱。
```

## 驗證

- **讀過的文件**：
  - 風控 Q1Q2 確認全文；
  - 我上一次的 T1～T7 裁示；
  - ADR-0030 的補充四、補充五（含附記）、補充六全文與檔頭；
  - 決策包 #149、#150。
- **讀過的程式**：
  - `claims.py` 全文；
  - `store.py:710-820`；
  - `test_forecast_claims_cli.py:125-210`；
  - 在 `app/` 內 grep `provisional`。
- **沒有做的事**：沒有執行任何程式，沒有讀 `.env`，沒有碰 `*.db`，也沒有修改任何檔案。
- **還沒實證的部分**：
  - 第 1 點 (b) 的監聽是否涵蓋完整；
  - 第 5 點在 Windows 上實際的輸出；
  - 第 7 點目前還只是約束，`bootstrap` 尚未實作。

  依 #139，這些由 devops-sre 與 dev-lead 用測試實證，再由 qa 判讀。

## 下一步

1. **tech-writer**：把附記逐字落檔，commit 用 `docs:`。
2. **coordinator**：
   - 把第 5 點 (e) 轉給風控，請它判斷區塊一要不要補註；
   - 區塊五末句維持原樣，不要刪；
   - 第 6 點的四項前提都成立之後，才通知 CEO 執行時機。
3. **devops-sre、dev-lead**：在一鍵檔 PR 落實第 1、3、4、5 點；CG-2 PR 落實第 7、8 點。
4. **qa-reviewer**：依 S-13c 核對，並在清單加入第 2 點那一行。

相關檔案：
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/work/reviews/2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md
- /home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md
- /home/user/AICompany/apps/stock-desk/backend/app/forecast/claims.py
- /home/user/AICompany/apps/stock-desk/backend/app/forecast/store.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_claims_cli.py
