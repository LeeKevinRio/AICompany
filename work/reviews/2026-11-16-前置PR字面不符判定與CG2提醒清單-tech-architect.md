# 前置 PR 字面不符判定與 CG-2 提醒清單

- 審查者：tech-architect
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
worktree 已確認在該分支上：`store.py:867` 有 `def bootstrap`。四點判定如下。
1. 第 6 點的字面確實有誤。dev-lead 的斷言符合我的原意，但要再收緊一處：store.py 內呼叫 `create_objects` 的函式只能是 `_write`。這條補測試要在前置 PR 合併前完成。更正附記全文在下方，可以逐字落檔。
2. `WRITE_METHODS` 加入 `"bootstrap"` 在我容許的範圍內。理由：這份白名單列舉「可以開寫入交易的方法」，而第 2 點規定 `bootstrap` 要走 `_write`，加這一項是直接結果。它沒有改變 `create_schema`／`register_claim` 的任何行為斷言，同檔其他斷言也不得動。
3. 6 項自定解讀全部接受。第 3、4、5 項各附一條給 CG-2 的約束（見下）。
4. CG-2 PR 的提醒清單在「下一步」。

## 各部門回報（tech-architect）
**自定解讀逐項判定**
- 1 接受：用 `time.monotonic()` 只決定何時放棄，`registered_at` 仍只取自 store 時鐘，符合 S-2。等待期間會持有 IMMEDIATE 鎖最多約 1 秒；這是一次性操作，可以接受。
- 2 接受：第 4 點寫的是「不晚於」，本來就涵蓋同值和時鐘倒退。
- 3 接受：`RuntimeError` 屬於程式錯誤，不算拒絕。CG-2 的 CLI 不得捕捉它，也不得把它歸成結束碼 3。
- 4 接受：store 層不管路徑，這是對的。但 `sqlite3.connect` 對不存在的路徑會建出 0 位元組的檔，回滾後這個檔還在。所以 CLI 必須在建立 `ForecastStore` 之前完成以下檢查，任一不成立就以結束碼 4 拒絕，而且不建立任何檔：
  - (a) `<backend>` 由模組位置導出，不取自工作目錄。
  - (b) `Path.resolve(strict=True)` 成功，結果等於 `<backend>/data/stock-desk.db`，而且是一般檔案。
  - (c) 環境變數與 `apps/stock-desk/.env` 都沒有設 `STOCK_DESK_DB_PATH`。
  - (d) 檢查 `forecast_`、`plan_` 表時只用 `mode=ro` 的 URI 連線（R-4 提早停止）。
  - 測試：路徑不存在時結束碼為 4，且執行後該路徑仍不存在。
- 5 接受：提交後的核對要先做 `ledger_schema_status()`，再查 `provisional_results_seen()`。核對過程中出現任何例外，一律印固定句、以結束碼 5 結束。
- 6 接受：dev-lead 的斷言比補充七字面更嚴。

**附記全文（交 tech-writer 落檔）**

檔頭：
```
- 補充紀錄：2026-11-16 append 補充七附記（第 6 點 `create_objects` 呼叫點的字面更正、既有測試 `WRITE_METHODS` 加列 `bootstrap` 的容許、`bootstrap` 目標路徑檢查歸 CLI；tech-architect 裁示，字面更正與收緊，不放寬補充七其餘各點；CEO 可推翻；來源 `work/reviews/2026-11-16-CG2前置PR交件-dev-lead.md`）。
```
檔尾：
```
---

## 補充七附記：第 6 點字面更正、既有測試白名單與目標路徑檢查（2026-11-16）

- 決策者：tech-architect。來源：`work/reviews/2026-11-16-CG2前置PR交件-dev-lead.md`。
- 性質：更正與收緊，不放寬補充七其餘各點。CEO 可推翻。

1. 第 6 點第一項更正為：`app/` 中呼叫 `create_objects` 的地方恰為兩處，即 store.py 的 `ForecastStore._write` 與 schema.py 的 `create_schema`。原字面與第 1 點衝突，以本附記為準。「沒有任何模組呼叫 `create_schema`」的範圍是 `app/`，測試與 harness 不在此限。
2. 第 1 點與 S-15 的「既有測試不改」，不含 store 寫入方法的列舉白名單（`tests/test_forecast_store.py` 的 `WRITE_METHODS`）。白名單加列 `bootstrap` 是第 2 點的直接結果，予以容許；同檔其他斷言不得改動。
3. `ForecastStore.bootstrap` 不檢查目標檔。補充四第 2 點的目標與環境變數條件，以及 R-3 的「主 DB 存在於預設位置」，由 claims.py 在建立 `ForecastStore` 之前檢查：`<backend>` 由模組位置導出，不取自工作目錄；`Path.resolve(strict=True)` 成功，且等於 `<backend>/data/stock-desk.db`，且為一般檔案；檢查 `forecast_`、`plan_` 表時只用 `mode=ro` 的唯讀 URI。任一不成立就以結束碼 4 拒絕，且不得建立任何檔案。

- **S-15a（逐條可檢查）**
  - 第 1 點：AST 測試，斷言 store.py 內呼叫 `create_objects` 的函式恰為 `{"_write"}`，schema.py 內恰為 `{"create_schema"}`。
  - 第 2 點：`tests/test_forecast_store.py` 的 diff 只有一行。
  - 第 3 點：CG-2 PR 測試，目標不存在時結束碼為 4，且該路徑仍不存在。
```

## 驗證
- 讀過的檔案：
  - 補充七全文（ADR 第 767–840 行）、補充四第 2、4、5 點
  - `store.py` 第 560–979 行
  - `test_forecast_bootstrap.py:551-581`
  - `test_forecast_store.py:1369-1425`
  - RC-163 原文（`work/reviews/2026-11-16-補充六附記與登記條件確認-tech-architect.md:81-83`）
- 目前的不足：`test_s15_only_the_store_calls_create_objects` 只比對到檔案層級（store.py），所以 store.py 內其他方法若直接呼叫 `create_objects`，這個測試抓不到。這就是附記第 1 點要補的測試。
- 我沒有執行測試；完整的程式碼審查由 qa-reviewer 負責。沒有讀 `.env`，也沒有碰任何 `*.db`。

## 下一步
**前置 PR（交 dev-lead）**
- 補上 S-15a 第 1 點的 AST 斷言，之後再交 qa-reviewer。
- tech-writer 把附記落檔進 ADR-0030。

**CG-2 PR 提醒清單（供 coordinator 派工）**
1. 把前置 PR 的斷言翻轉：`app/` 中呼叫 `bootstrap` 的模組恰為 `{"forecast/claims.py"}`。另加斷言「claims.py 呼叫了 `bootstrap`」。claims.py 不得呼叫 `register_claim`、`_write`、`create_objects`、`create_schema`；`bootstrap --production` 只呼叫 `store.bootstrap` 和唯讀查詢。
2. 依附記第 3 點，在建立 store 之前完成路徑、環境變數、存在性和唯讀表檢查。
3. 結束碼：
   - 4：補充四第 2 點的拒絕條件，以及交易內的 `SchemaNotEmptyError`。
   - 3：其他 `ForecastStoreError` 拒絕，包括等時鐘逾時、prereg 核對不符、鍵入值無效。
   - 預期外的例外（含 `RuntimeError`）不捕捉。
   - 每個結束碼各有一個測試；3 和 4 都要斷言沒有寫入。
4. 提交後用唯讀連線核對四項：schema 完整、`forward_claims()` 恰好是回傳的兩個 `claim_id`、`runs()` 為空、兩列值都等於鍵入值。不成立就印固定句、以結束碼 5 結束、不重試，一鍵檔隨之 STOP。
5. `provisional_results_seen` 依補充六附記第 7 點：由 CEO 鍵入 0 或 1，沒有預設值；無效輸入就停止、不寫入；回傳內容加一行 `provisional_results_seen=<0|1>`；0 與 1 各一個成功測試。
6. RC-163 抽取規則以常數寫明，從 `git cat-file blob <git_head>:<凍結包路徑>` 抽出區塊，與 YAML blob 比對 sha256。以下情況判為失敗，並附「規則確實會擋錯」的測試：
   - 標題出現 0 次或超過 1 次；
   - 缺開頭圍欄；
   - 缺結尾圍欄。
7. 第 7 點：PR 附上 `git merge-base --is-ancestor <前置 PR 合併 commit> <git_head>` 的結果。harness 通過時的 `git_head` 必須能到達前置 PR 的合併 commit，並以 CEO 那一次的 `git_head` 重做 (d) 比對。
8. 前置 PR 改過的 docstring，到 CG-2 合併前不得再改。M-1～M-9、R-1～R-8 列在 PR 說明中。CG-2 PR 不得與接線 PR 合併。

相關檔案：
- `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
- `/home/user/AICompany/work/reviews/2026-11-16-CG2前置PR交件-dev-lead.md`
- `/home/user/AICompany/.claude/worktrees/agent-aa23ba638139de497/apps/stock-desk/backend/tests/test_forecast_bootstrap.py`
