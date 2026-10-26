# 任務單：FD-4 通知與維運體驗

- 狀態：done（待 CEO 驗收）
- 發起人：總經理（CEO 定調）
- 目前負責：CEO
- 相關文件：`work/flight-deals-FD-4-PRD.md`、`work/flight-deals-PRD.md`（FD-1，FR-C、FR-E）、`work/flight-deals-FD-3-PRD.md`、`work/tasks/FD-1.md`（待辦）、`work/tasks/FD-3.md`、`docs/adr/0002-flight-deals-技術棧與資料源.md`（accepted；D-4、D-5、C-17 為本任務約束；第 350 行「不設登入自動啟動」需增補）

## 目標

四塊，不加其他新功能面：

1. 每日摘要推播：預設每天 08:00（Asia/Taipei，設定頁可改時間、可關閉、預設開啟）推一則 Telegram。每個啟用中監看一行（路線中文＋代碼｜目前最低價與日期組合｜較前一日漲跌，無資料「—」），加資料源狀態、上次掃描時間、過去 24 小時查價失敗次數，結尾固定免責句與「沒有收到價格通知不代表沒有低價」。同日去重；Telegram 未設定走 `suppressed`；無啟用監看仍推短訊；通知紀錄頁顯示類型「每日摘要」。
2. Telegram 設定精靈：`flight-deals telegram-setup`，輪詢 `getUpdates` 最多 60 秒找 chat id，印出可貼上的設定行並詢問是否測試發送；不自動寫 `.env`；token 不出現在任何輸出。
3. Windows 登入自動啟動：`install-autostart.bat`、`uninstall-autostart.bat`（登入自動啟動機制、登入時、目前使用者、隱藏視窗）、README、健康頁顯示「自動啟動：已安裝／未安裝」（偵測不到則不顯示）；仍只綁 127.0.0.1。
4. 列表頁趨勢：監看列表在最低價旁顯示較前一輪掃描的漲跌（箭頭＋金額），無前一輪「—」。

範圍外：Travelpayouts 備援、多使用者、LINE、價格預測、自動購票、行動版 app。

## 驗收條件

完整 Given/When/Then 見 PRD「驗收條件」章節（AC-DG1 至 AC-DG17、AC-SW1 至 AC-SW10、AC-AS1 至 AC-AS10、AC-TR1 至 AC-TR6）。摘要：

- 每日摘要：08:00 推一次且當天不重複；關閉後不推；Telegram 未設定不推且無 failed；無監看推短訊；漲跌計算與「—」；固定結尾與禁用字檢查；失敗重試；補發；通知紀錄可見；長度上限。
- 精靈：找到 chat id 並印出設定行；60 秒逾時行為；多 chat 處理；token 不出現在任何輸出（假 token 測試）；不寫 `.env`；服務執行中仍可用。
- 自動啟動：install 後出現隱藏、登入觸發的工作；重複安裝不重複；uninstall 後健康頁變「未安裝」；偵測不到不顯示；與 dev-up.bat 共存時由單一排程鎖擋第二份。
- 列表趨勢：↓／↑／＝ 與金額；無基準「—」；revision 變動後不跨版本比較。

## tech-architect 評估關卡需回覆

1. 「前一日結束時最低價」與「前一輪掃描結束時最低價」能否由現有觀測資料重建；是否需 migration；彈性窗輪換取樣造成的偏差如何處理（PRD 開放問題 2）。
2. 新增「每日摘要」通知類型的資料模型、dedupe key、`app_setting` 設定項、排程與補發機制（開放問題 3、4）。
3. 訊息超過長度上限的處理（開放問題 5）。
4. `chat_id` 遮蔽祕密規則與精靈輸出的相容性（開放問題 6）。
5. ADR-0002 增補：自動啟動（第 350 行）與 FD-4 新增約束；是否需另開 ADR（開放問題 7）。
6. 評估通過才可推進至 `build`；若認為某需求不可行，須退回 product-manager 並附理由。
7. 另請 devops-sre 就自動啟動的提權、隱藏視窗、網路未就緒與偵測方式給意見（開放問題 8、9）。

## 待回覆的預設值

PRD 開放問題 1（補發）、8（不提權、能偵測才顯示）、9（固定工作名、覆寫）、10（選最新 chat）、11（測試訊息不寫 DB）、12（摘要每監看只列一組最低價）。未覆議則照預設。

## 後續關卡（預期）

- spec → build：tech-architect 評估通過；dev-lead、frontend-engineer、devops-sre 分工。
- review：qa-reviewer（含 Codex）；token 外洩測試與禁用字測試必過。
- risk-gate：risk-compliance-officer 看摘要文案模板（AC-DG17）。
- UI 實機：qa-e2e（或總經理代跑）；登出再登入、真實 Telegram 送達須 CEO 或總經理手動驗收。

## 交接紀錄

- 2026-10-26 product-manager → tech-architect：FD-4 PRD v0.1 與驗收條件已定（依總經理定調），請依上列評估關卡回覆；開放問題 2 至 7 待 tech-architect，8、9 待 devops-sre，10 至 12 待總經理，13 待 risk-compliance-officer，14 待 qa-e2e。
- 2026-10-26 tech-architect → 總經理：評估通過，不另開 ADR；增補小節與 C-32～C-36 落進 ADR-0002。翻案三處：自動啟動改 HKCU Run（不用 schtasks）、列表漲跌用快照對快照、telegram-setup 由 app.py 提供 factory。遷移陷阱：重建 notification 表須 FK off，runner 要擴充並先備份。
- 2026-10-26 總經理：本機實測 `.venv\Scripts\pythonw.exe` 存在；APScheduler 3.11.3 `CronTrigger(timezone=)` 可用。開放問題 1、10～12 照預設（補發、多 chat 列出讓使用者選、精靈測試訊息不進紀錄、每監看一組）。PRD 的「schtasks／登入自動啟動機制」字面改為「登入自動啟動（不需系統管理員權限）」；列表最低價改排除已出發日期（行為變更，PM 知情）。狀態 spec → build。
- 2026-10-26 dev-lead、frontend-engineer → 總經理：交件（migration 0002、快照漲跌、摘要服務與四個排程 job、telegram-setup、autostart、背景模式；381 測試）。總經理裁示 PRD 與 ADR 三處不一致照 ADR：AC-DG11 失敗次數＝24 小時內 failed 的 scan_run 筆數（文案「查價失敗的掃描：N 次」）；AC-DG7／DG8 不做百分比；AC-DG9 用「尚無價格」。總經理修掉 settings.html 的 form feed 字元。
- 2026-10-26 devops-sre → 總經理：交付 `install-autostart.bat`、`uninstall-autostart.bat`（CRLF、純 ASCII、無祕密與 runas，只做 uv／pythonw.exe 前置檢查後呼叫 `uv run --project "%~dp0." flight-deals autostart install|uninstall`、印結束碼、pause）與 README 三小節（登入自動啟動、Telegram 設定精靈、每日摘要）。本機實測（PowerShell，bat 以 `cmd /c ".\x.bat < NUL"` 執行）：
  1. 安裝前 `uv run flight-deals autostart status` → 「登入自動啟動：未安裝」；`reg query ... /v flight-deals` → 查無（rc=1）。
  2. `install-autostart.bat` → 「已安裝登入自動啟動…」Exit code 0；`status` →「已安裝（指向此專案）」；`reg query` 值為 `"D:\AIProject\AICompany-flight-deals\apps\flight-deals\.venv\Scripts\pythonw.exe" -m flight_deals.cli --background`（REG_SZ）。再裝一次 →「設定相同，未變更」，無重複。
  3. 手動執行上述指令（`Start-Process -PassThru -Wait`，工作目錄 C:\Windows\System32 模擬登入）：ExitCode=2；`data\flight-deals.log` 新增一行 ERROR「refusing to start: 此資料庫已有另一個實例在執行排程（pid=35156 …）」；無視窗（無主控台、無 stdout／stderr）；log 內無 token 樣式字串（本機亦未設 token）；port 8795 仍由原服務 PID 35156 監聽，未受影響。
  4. `uninstall-autostart.bat` → 「已移除…」Exit code 0；`status` →「未安裝」；`reg query` 查無（rc=1）；再移除一次 →「尚未安裝…不需要移除」Exit code 0。最終狀態：未安裝。
  5. `dev-up.bat :scan_app` 條件實測：背景實例啟動期間 `Get-CimInstance Win32_Process` 看到兩個程序皆符合 `Name like 'python*'` 且 CommandLine like `*-m flight_deals*`：venv 的 `...\.venv\Scripts\pythonw.exe" -m flight_deals.cli --background`（uv venv 轉發器）與其子程序 `C:\Users\iu\AppData\Local\Programs\Python\Python311\pythonw.exe" -m flight_deals.cli --background`；一般啟動的服務為 `python.exe "...\flight-deals.exe" --port 8795`，符合 `*flight-deals.exe*`。結論：偵測條件涵蓋，dev-up.bat 不需修改。
  已知限制：未真的登出登入（依指示）；「無視窗」只能由 pythonw 無主控台推論，登入時實際行為待 CEO 手動驗收（AC-AS3）；log 以 cmd 預設碼頁讀會亂碼，用 UTF-8 檢視。
- 2026-10-26 risk-compliance-officer → 總經理：每日摘要模板 **APPROVE**、風險閘門不適用；三項 recommended（漲跌但書、過舊標籤帶門檻、列表定義行）由 dev-lead 採納。列表「較前一輪」顏色（跌綠漲紅）目前可接受，若再加強視覺（徽章、動畫、只在下跌時高亮）須重審。
- 2026-10-26 總經理代跑 e2e：重啟服務自動遷移（data/ 出現 flight-deals.pre-v2.db）；列表「較前一輪」欄與定義行；通知紀錄出現「每日摘要」suppressed（啟動補推）；設定頁儲存摘要時間 10:15 成功並還原 08:00；健康頁「自動啟動：未安裝」（form feed 字元由總經理以位元組層級修掉）；telegram-setup 非互動卡住的問題由 dev-lead 第三批修正（387 測試）。
- 2026-10-26 qa-reviewer → 總經理：**PASS**，BLOCKING_ISSUES=false；C-32～C-36 全過；4 medium（背景模式啟動例外未進 log、備份殘檔、next_run_time 測試缺口、ADR／PRD 未 staged）與 4 low 由 dev-lead 第四批修畢（393 測試）、總經理補 staged。Codex 無 high；其指出的「備份被沿用」降為 low（rollback 後 DB 未變）。
- 2026-10-26 總經理：狀態 → done，待 CEO 驗收。人工驗收項：登出再登入的自動啟動（AC-AS3）、真實 Telegram 送達（AC-DG1、AC-SW3）。
