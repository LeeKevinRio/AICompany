# D-10 心跳責任確認書交件與 dev-up.bat／build attestation 查證

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. 第一件已完成。我只新增了一個檔：`/home/user/AICompany/work/reviews/2026-11-21-D-10心跳責任確認-devops-sre.md`。沒有改任何程式、`.bat`、測試或 CI，也沒有 commit 或 push。
   - 檔案已照補充十三第 7 點 (b) 分成五節，另加「沒有查證的事」一節。
   - 檔內沒有對 CEO 說的話的字面，沒有模型名稱，沒有祕密。
2. 第二件查完了，結論在下面。一句話：`dev-up.bat` 路徑下，族群動能的判定在程式上一定是 NE-7（fail-closed）。這個結果是設計預期，但文件與啟動流程之間的落差沒有任何文件記載為「已知且接受」。這件事與預測紀錄帳完全無關。

## 各部門回報

### devops-sre：第一件，確認書的要點

- **第 1 節**：接下責任，並把限制照實寫出。這不是自動偵測。除了補充十三第 1 點 (c) 的各項，我另外查到三項限制：
  - 被跳過的執行有四種 refusal、指數重抓失敗、bar 早於執行開始，都只在 scheduler 視窗留一行 WARNING，不留 `forecast_run`。
  - `dev-up.bat` 開的視窗沒有檔案 log（`logging_setup.py` 只有 `StreamHandler`），視窗一關就沒了。
  - `report status` 不印 `error_class`，所以貼回分不出 `gate_closed` 與 `error` 各自的細分原因。
- **第 2 節 (二)**：每一種結論代號的原因分類，並標明貼回能區分到什麼程度。
  - 漏記 A～F（主機沒開、視窗被關、當晚被跳過、跑的是接線前舊程式、執行卡住、排程時刻不重放）在貼回上完全相同，區分不了。
  - 帶 outcome 的（`inputs_not_ready`、`gate_closed`、`error`）可以區分。
  - 另有一個發現：`STOCK_DESK_DB_PATH` 存在於環境時，狀態報告會 STOP，scheduler 的 `forecast_record` 也會每次拒絕，所以記錄本身也停了。這一種我同日轉 tech-architect。
- **第 2 節 (三)**：各通知的處置步驟。第 0 步是核對 coordinator 存檔的貼回原文與比對紀錄。我只讀 `work/reviews/` 的存檔，不碰 CEO 機器、不讀主 DB。
- **第 2 節 (四)，RC-361 (b)**：需要 CEO 回答「那幾晚有沒有開著」的五個條件，每項都是「是」才需要。不需要問的情形也逐項列出。
  - 條件摘要：
    - 比對列得出具體的漏記交易日；
    - 該區間貼回沒有執行列可說明；
    - CEO 尚未說明；
    - 同一事件還沒問過；
    - 答案會改變我的處置。
  - 三種答案各自的處置：
    - 「沒開著」：不開技術調查。
    - 「有開著」：開缺陷調查並通知 tech-architect。這個答案不排除舊程式在跑。
    - 「不確定」：記為原因未明；連續兩次才轉 tech-architect。
- **第 2 節 (五)**：重啟的處置。
  - 多數情形不需要重啟。
  - 可能需要重啟的是：舊程式還在跑、執行卡住、CEO 的 checkout 未更新。
  - 目前沒有風控定稿的字面可以請 CEO 重啟。既有的 H、L、U 系列都含「請 CEO 不要自己重新啟動」的意旨，需要時要另送風控定稿。
- **第 2 節 (六)(七)**：轉 tech-architect 的九種情形，處置紀錄的位置與回覆時限。
  - 處置紀錄放 `work/reviews/<日期>-心跳處置-devops-sre.md`。
  - 當天回覆，書面紀錄最遲第 2 個平日完成。
- **第 3、4、5 節**：知悉第 5 點的不做事項。知悉第 6 點的設計義務與兩條讀取路徑的後果（含 RC-368），現在不設計。內容日後要改須經 tech-architect。

### devops-sre：第二件，`dev-up.bat` 與 build attestation（只查不改）

**1. 誰讀 attestation、缺少時的行為**
- 讀取與檢查在 `apps/stock-desk/backend/app/services/sector_attestation.py`。
  - `read_attestation`（194～207 行）在檔案不存在或格式壞掉時回 `None`。
  - `verify`（234～261 行）遇到 `None` 就把 `attestation_missing` 放進 `problems`。
  - 不拋錯，也沒有 fallback。
- scheduler 判定時在 `app/services/sector_board.py` 481～513 行：
  - 呼叫 `self.attestation()`。
  - 寫入 `selfcheck_passed = check.ok`，也就是 false。
  - 另在 notes 加 `attestation:attestation_missing`。
- API 這邊在 `app/services/sector_runtime.py` 的 `runtime_from_check`（42～52 行）：`check.ok` 為 false 時，`ci_passed_commit` 是 `None`。
- `app/sectors/gate.py` 457～466 行：只要已有統計列，`selfcheck_passed` 為 false 或 `ci_passed_commit` 為 `None`，就加入 `lookahead_tests_failed`（NE-7）。
- `scripts/attest_sector_gate.py` 的作用：
  - 條件：只在工作樹乾淨時執行，跑 `pytest -m sector_ne7`。
  - 全綠才寫 `backend/app/_build/ci_attestation.json`（含 `ci_passed_commit`、`suite_hash`、`passed_at`）；沒全綠就刪舊檔。
  - 該檔已列入 `backend/.gitignore`（14 行）。
  - `backend/app/_build/` 目前確實不存在（Glob 無結果）。

**2. 以 `dev-up.bat` 啟動時，CEO 看到什麼**
- `dev-up.bat` 全檔沒有 attestation 步驟（已讀全文）。所以 `attestation_missing` 恆成立，NE-7 在程式上恆成立。
- 另外 `dev-up.bat` 每次都 `git pull`。即使曾手動跑過 attestation，新 commit 也會是 `commit_mismatch`，除非每次重跑。
- 畫面上的樣子：
  - 不是每個人都會看到 NE-7 的字樣。優先序是 `NE_ORDER`（`gate.py` 57～66 行），前端只顯示優先序最前的那一個原因。
  - 只要 NE-1（`pit_history_missing`）、NE-2（`accumulating`）、NE-3 等較前面的原因還成立，卡片顯示的就是它們的句子，NE-7 被蓋住。
  - NE-7 只在前面的原因都消失後，才以這句顯示：「歷史統計未通過資料偏誤檢查，本排行僅描述近 5 日的相對強弱。」（`frontend/app/lib/sectorMomentumWording.ts` 446～449 行；API 為 `GET /api/sectors/momentum` 的 `not_evaluated_reason = lookahead_tests_failed`）
  - 近 5 日排行本身照常顯示，只是不列示歷史比例。
- scheduler 視窗的 `sector board refresh: ... notes=...` 那一行會帶 `attestation:...`，但只有在判定真的跑到那一步（新的 5 日樣本完成）才出現。

**3. 設計如此，還是落差**
- 「缺 attestation 時判 NE-7、fail-closed」本身是設計，且有明文：ADR-0012 的 C-36、T-22、C-52（71 行與 857～862 行）。
- 「CEO 用 `dev-up.bat` 就會恆為 NE-7」沒有任何文件記載為已知且接受，所以屬於文件與啟動流程的落差。依據：
  - ADR-0012 C-52（CEO 2026-09-25 裁定採主機 git checkout 直接執行）要求「已在該 checkout 跑過 `attest_sector_gate.py`」。
  - 第 1150 行把部署手冊與重跑 attestation 交給 devops-sre。
  - 手冊（`族群動能-主機部署手冊.md` 120～132、208～212 行）要求這一步。
  - `dev-up.bat`、`local-run`、README 都沒有這一步。
  - `work/dispatch/2026-10-17-後續追蹤清單.md` 第 678 行把它列為「待 devops-sre 另查」。
  - `work/reviews/2026-11-21-dev-up提示改字分支交件-devops-sre.md` 158～166 行是另一個會話的同一觀察。
- grep `work/reviews/` 的 RC-382～RC-400 兩份風控判定，沒有 attest／NE-7 的處理。
- 沒有找到任何一份 ADR 或審查紀錄寫「`dev-up` 路徑下判定為 fail-closed 且 CEO 知悉」。
- 補充一點：ADR-0012 的 K3 把「NE-7 恆成立」寫成「只當 K1 落地前的 fail-closed 現況」。

**4. 與預測紀錄帳的關係：沒有**
- `app/forecast/` 全目錄 grep `attest|NE-7|_build` 無任何命中。
- `code_digest` 只涵蓋 `forecast`、`outlook`、`dirdef` 三個套件的 `*.py`，加 `data/session_calendar.py`（`canonical.py` 77～78、214～231 行）。
  - `sector_attestation.py` 不在範圍內。
  - `ci_attestation.json` 不是 `.py`，也不在範圍內。
- `runtime_json` 只含 Python 版本與建置、平台字串，加 `uv.lock` 的 sha256（`recorder.py` 182～191 行），不含 attestation。
- 所以補產 attestation 本身不會改變 `code_digest` 或 `runtime_json`。

**5. 建議（只建議，不動手）**
- 需要處理，但不急，也不是接線的前置。
- 建議由 tech-architect 先裁示，三選一：
  - (a) 在 `dev-up.bat` 加一步 attestation。這要改 `.bat`，經 qa-reviewer，也要看風控對畫面字句的意見。
  - (b) 在文件明寫「`dev-up.bat` 路徑下族群歷史統計恆為 NE-7，屬預期」，並更新手冊。
  - (c) 另立 ADR 修訂，放寬或改變 C-52 的部署約束。放寬 C-36 是 ADR 明文禁止的，因此只能走這條。
- 之後由 devops-sre 落地，並在乾淨環境驗證。
- 目前 NE-1 與 NE-2 先成立，NE-7 看不出差異。ADR 也預期 N 達 150 之前看不出影響。
- 不影響正式登記，也不影響接線 PR，也不影響預測記錄。
- 我沒有 Windows 環境，不確定 `dev-up.bat` 加這一步後（`attest` 要求 `git status --porcelain` 為空，連未追蹤檔都算）是否會因 CEO 本機的未追蹤檔而拒絕。

## 驗證

- 第一件：檔案已寫入，用 Grep 確認沒有模型名稱、token、password 等字樣。我沒有執行任何 `.bat`、測試或 CI。
- 第二件：以上行號皆由 Read／Grep 直接取得，全程唯讀。
- 讀過補充十三、風控 RC-357～RC-381 全文，ADR-0030 指定行段，接線版 `scheduler.py` 全文，`recorder.py` 與 `report.py` 的相關段落，`dev-up.bat` 全文，以及 `forecast_status.py` 的 STOP／ERROR 條件。
- 沒有讀 `.env`，沒有碰 `apps/stock-desk/backend/data/`。

## 下一步

1. coordinator 把確認書送 qa-reviewer 審查後 commit。commit 必須早於接線 PR 的合併 commit（補充十三第 7 點 (c)）。
2. 第 2 節 (七) 的回覆時限數字與 (四) 的「連續兩次原因未明才轉 tech-architect」是我自訂的，請 tech-architect 審查時確認或調整。
3. 重啟請求目前沒有風控定稿字面（見 (五) 第 3 點）。coordinator 要追蹤，必要時先送風控。
4. attestation 落差請 coordinator 轉 tech-architect 裁示（建議三選一，見上），並更新後續追蹤清單第 678 行的待查項。

## 我沒有查證的事

1. 沒有 Windows 環境。`taskkill`、視窗關閉時有沒有留下 end 列、`platform.platform()` 在 Windows 更新後會不會變，都是推論，沒有實證。
2. 資料來源呼叫有沒有逾時（執行卡住這個原因是否真的會發生）：未讀。
3. APScheduler 在 process 不在時漏掉的排程是否一律不重放：只依程式參數推論。
4. `forecast_status.py` 只讀了 STOP／ERROR 的條件；接線版 `report.py` 與日後合併版是否相同：未比對。
5. CEO 機器上的 HEAD、scheduler 狀態、`.env`：完全看不到。CEO 實際用 `dev-up.bat` 還是手冊流程：未查證。
6. 前端是否在別處（例如詳細展開）把次要的 NE 原因也列出來：我只確認了主視圖以單一主要原因顯示。
7. 第二件的畫面字樣，沒有實機看過 UI。
