# D-10 心跳責任確認書修訂交件（M1～M8）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

D-10 心跳責任確認書已就地修訂，M1～M8 全部落實。對照程式後，tech-architect 的事實都成立，沒有需要標「待 tech-architect 複核」的項目。只改了一個檔：`/home/user/AICompany/work/reviews/2026-11-21-D-10心跳責任確認-devops-sre.md`。我沒有 commit，也沒有讀 `.env`、碰 `backend/data/`、執行 `.bat`。檔頭已加修訂紀錄，並註明待 tech-architect 複核後才 commit。

## 各部門回報

**M1：`STOCK_DESK_DB_PATH`。**
- 改在第 2 節（二）「無法比對」，新增三種情形的表：(i) Windows 使用者或系統環境變數，(ii) 只在 `.env`，(iii) 只在某個 PowerShell 視窗暫設。
- 「同一個條件也會」改為「多半也會」。(ii) 寫成貼回上只表現為持續的「漏記」或「漏記（尚未開始記錄）」。
- 內部禁止事項（記錄期間不得指示 CEO 設定這個變數，要改須經 tech-architect）寫在同一處。
- 第 2 節（三）(a)-4 與（六）第 5 項擴大為「判斷可能是 refusal 的任何情形」。
- 對照程式：
  - `dev-up.bat` 92～101 行，`.env` 存在時設 `UV_ENV_FILE`。
  - `forecast-status.bat` 第 11 行清空 `UV_ENV_FILE`。
  - `forecast_status.py` 224 行只看程序環境。
  - `scheduler.py` 664、699 行附近的 refusal。
  - `claims.py` 305～306、404～406 行同時拒絕 `env_db_path` 與 `env_file_db_path`。

**M2：漏記原因表（第 2 節（二））。**
- C 拆成 C1（單次型）與 C2（持續型）。
- D 補上 `git pull` 失敗或 tracked 變更在停舊程序前就停止，以及對停舊 scheduler 的提示回答 N。
- E 限定為 `begin_run` 之前；之後的另一半移到「中斷後沒有後續執行」。
- 新增 G：主機睡眠或休眠，標「推論，未查證」。
- 第 1 節第 4 點同步改寫。
- RC-361 (b) 那節（四）的「有開著」處置，已註明這個回答排除不了 D、G 與持續型 C（C2）。
- 對照程式：`scheduler.py` 784～809 行、`dev-up.bat` 的 `goto fail` 與 `ensure_scheduler_free`（283～300 行）。

**M3：中斷的執行。**
- 已加「`end_run` 本身失敗也不留 end 列」。
- 已加「`begin_run` 之前的例外不留列」，含 `get_index_resolver()` 與卡在強制重抓。
- 對照 `recorder.py` 363～392 行：`end_run` 寫在 except 區塊內，確實接不住自己的失敗。
- `scheduler.py` 788 行的 `get_index_resolver()` 確實在 try 之外。

**M4：F-2 與整數差。**
- 第 2 節（二）F-2 與（三）(c) 第 2 步：刪掉「以 a 或 b 為主」，只轉引 coordinator 比對紀錄對 a、b 各自「增加／相同」的結論。
- 第 2 節（七）改為「不得寫入任何整數差，含轉引自比對紀錄者」。

**M5：「不確定」規則（第 2 節（四））。**
- 「連續」定義為下一份有效貼回又出現列得出交易日且仍無法區分的漏記，不論日期是否相同。
- 例外第一次就轉 tech-architect：「漏記（尚未開始記錄）」，以及同一次已觸發補充十三第 6 點 (a) 第二項（5 個以上平日）。
- 第 2 節（六）第 7 項同步。

**M6：時限（第 2 節（七））。**
- 已加一條：「是否需要 L2」與「是否需要重啟」寫在當天的書面回覆。
- 轉 tech-architect 的同日轉送附分類即可，完整紀錄可後補。

**M7：重啟（第 2 節（五））。**
- 重寫為四點：
  - 技術上需要重新執行 `dev-up.bat` 的情形：D 的三種來路、E、checkout 未更新。
  - 重啟無效的情形：`gate_closed`、refusal。
  - `STOCK_DESK_DB_PATH` 的 refusal 不是重啟能解決的；拿掉變數若讓 backend 改用另一顆主 DB，屬資料位置的決定，須經 tech-architect 與風控、必要時由 CEO 決定。
  - 「目前沒有風控定稿字面」改寫為：coordinator 已請風控在接線 PR 合併前預先定稿一則請求，定稿後引用；定稿前照補充十三第 4 點 (f) 辦。
- 全文沒有自擬對 CEO 的句子。

**M8：無法比對（第 2 節（二）與（三）(a)-4）。**
- 缺「最近一次…」那一行，改寫為「接線前版 `report` 或貼回不完整，區分不了」。
- 已加「第二段的 `STOP_VERIFY` 出現在第一段之後，仍是有效貼回，不屬無法比對」。

## 與 tech-architect 說法不符之處

沒有。自行補充的兩處請複核：
- 「中斷後沒有後續執行」的原因欄，我多加了 C2 與 G。理由是 C2 的持續型 refusal 發生時，最後一筆沒有 end 列的執行也會一直是最近一次。
- 第 2 節（六）第 7 項，我把 M5 的例外情形一併列入「開著卻沒有記錄」的轉送。

## 驗證：APScheduler 與 misfire 查證結果

- **鎖定版本**：`apps/stock-desk/backend/uv.lock` 48～49 行，APScheduler 3.11.3。
- **misfire 預設**：本機 venv 裝的同為 3.11.3，`apscheduler/schedulers/base.py` 911 行的預設是 `job_defaults.get("misfire_grace_time", 1)`，也就是 1 秒。`scheduler.py` 839 行用 `BlockingScheduler(timezone="UTC")`，沒有傳 `job_defaults`，`forecast_record` 也沒設 `misfire_grace_time`。
- 這只是讀原始碼，沒有實測。原因 G 仍標「推論，未查證」，睡眠喚醒後的實際行為未驗證。
- 我另外啟動過一個 `pip download` 的背景指令，只是順手核對版本，結果沒有採用。

## 沒有查證的事（已寫入確認書第 6 節）

1. uv 的 `UV_ENV_FILE`／`--env-file` 對空值 `STOCK_DESK_DB_PATH=` 會不會被當成「有設」。`.env` 是否確實把該變數帶進 scheduler 程序環境，也只是讀 `dev-up.bat` 的推論。
2. 接線版 `dev-up.bat` 與 product 現行版是否相同。我讀的是 `apps/stock-desk/dev-up.bat`。
3. 風控預先定稿的重啟請求，我手上沒有字面，所以全文不引用。
4. 睡眠或休眠跨過排程時刻的實際行為（原因 G）。
5. 第 6 節原有各項仍然沒有查證。
