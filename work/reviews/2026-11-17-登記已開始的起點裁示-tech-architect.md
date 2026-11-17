# 「登記已開始」的起點裁示與補充七附記三之一

- 審查者：tech-architect
- 日期：2026-11-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
1. 採用 coordinator 的改法。「`start()` 呼叫期間」一律算作登記已開始：結束碼 5，留下 `UNCONFIRMED` 回貼。只有 `start()` 拋出 `OSError`、可以確定子行程沒有建立時，才算沒有開始：STOP `claims_not_started`，結束碼 3。
2. 這和附記三第 3 點的字面「`Popen` 啟動成功後才進入」不同，改法較保守，所以要追加一段附記，全文附在最後，可直接 append。
3. CEO 看得到的字面不必改。RC-207 第七節的適用範圍已經涵蓋「登記程式啟動之後發生錯誤、被中斷」，`INTERRUPTED_LATE` 那一句也已經寫「可能已寫入」。這次只是讓中斷落在那一邊，沒有新增任何句子。

## 各部門回報（tech-architect）
- 讀法與依據：附記三第 3 點的用意，是「確定沒有啟動時，不要說可能已寫入」。換句話說，畫面說「沒有寫入」的前提必須是「確定沒有子行程」。在 `start()` 執行期間被中斷，無法排除子行程已經建立，而現行程式（約第 1221～1225 行）會在這個窄窗說「沒有登記」。這是不安全方向的錯誤，跟 RC-191「無法確認就不能說好壞」相衝突。
- 要改的程式：
  - 呼叫 `start()` 之前先設 `late=True`；`except OSError` 時改回 `False`。
  - 已經取得 `Popen` 物件時就 kill 子行程。SQLite 交易是原子的，kill 不會讓資料庫進入半寫入狀態。
- 要改的測試：`test_p6_an_interrupt_while_starting_is_exit_2_with_no_paste_back` 與 `test_p3_an_error_that_is_not_oserror_while_starting_is_still_before_the_registration`，預期改為結束碼 5，並留下 `UNCONFIRMED` 回貼。另加一個測試：在 `start()` 回傳之後、下一行之前注入中斷，預期也是 5。

## 驗證
我讀過 head `7b3fef0f` 的 `cg2_register.py` 第 1195～1244 行，確認現行程式在 `start()` 回傳之後才設 `late`。qa 報告全文沒有讀，以 coordinator 的摘要為準。

## 下一步
devops-sre 改程式與測試，qa 單項複審。coordinator append 下面這段附記；不必送風控，因為沒有改任何 CEO 可見字面。

---附記全文（逐字 append）---

## 補充七附記三之一：「登記已開始」的起點（2026-11-17）

- 決策者：tech-architect。來源：`work/reviews/2026-11-17-CG2登記一鍵檔修正複審-qa.md`（low：`start()` 期間中斷）；另讀 `7b3fef0f` 的 `scripts/cg2_register.py`。
- 性質：更正附記三第 3 點與 S-15c 第 6 點的字面，方向比原字面保守（不確定時判為已開始）。不改 CEO 可見字面、規則檔、定義物件與已登記雜湊，不改 `app/`。CEO 可推翻。

1. 「登記已開始」的狀態，自呼叫啟動子行程的函式之前起算。只有該函式拋出 `OSError`，也就是能確定子行程沒有建立時，才判為未開始：STOP，結束碼 3。這段期間的其他任何例外或中斷，都判為已開始：結束碼 5，寫入 `register_result=UNCONFIRMED` 回貼；已經取得子行程時，就終止它。
2. S-15c 第 6 點的「啟動子行程前」，讀為「呼叫啟動函式之前」。

- **S-15d（逐條可檢查）**：啟動函式執行中注入中斷、注入非 `OSError` 的例外、注入回傳後的中斷，三種情況都得到結束碼 5 與 `UNCONFIRMED` 回貼；拋 `OSError` 時得到結束碼 3，而且不留回貼（測試）。
