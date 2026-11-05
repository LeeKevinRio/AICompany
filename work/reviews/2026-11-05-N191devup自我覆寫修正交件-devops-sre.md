# N-191 dev-up 自我覆寫修正交件

- 審查者：devops-sre
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-191 已修好並 push。分支 `fix/stock-desk-dev-up-selfupdate`，commit `a71b6c12c9a7a0b59fd98e400f43d058d16ae8ea`。尚未 merge 進 product，等審查。
- sh 這邊我用假 git 模擬 pull 改寫自己，確認舊版會出錯、新版能跑完。
- .bat 無法在 Linux 執行，只做了靜態檢查和逐行推演，**還沒有實機驗證**，需要 CEO 在 Windows 跑一次。

## 各部門回報（devops-sre）
工作目錄 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n191`。我沒有讀 `.env`，也沒有碰 `data/*.db`。

**dev-up.bat（`apps/stock-desk/dev-up.bat`）**
- 做法是啟動時複製自己到 `%TEMP%` 再跑副本，這樣 `git pull` 改寫原檔時，正在執行的是副本。
- 在 `setlocal` 和 `title` 之後插入一個守衛區塊：
  1. `if not defined DEVUP_SRC_DIR (` 判斷是不是第一次進入。
  2. `set "DEVUP_SRC_DIR=%~dp0"` 把原目錄（結尾帶 `\`）存起來。
  3. `copy /y "%~f0" "%TEMP%\stock-desk-dev-up.bat"`。複製失敗會印 `[ERROR]`、`pause`、`exit /b 1`。
  4. `call "%TEMP%\stock-desk-dev-up.bat"`，然後 `exit /b !errorlevel!`。
- 副本執行時 `DEVUP_SRC_DIR` 已定義，會跳過守衛。
- 整個 if 區塊在執行前就已整段解析完。所以子程序跑完回來時，母程序不會再讀磁碟上已經被改過的檔案，直接執行記憶體裡的 `exit /b`。這是這個做法成立的關鍵。
- 4 處 `%~dp0` 改成 `%DEVUP_SRC_DIR%`：`BACKEND_DIR`、`FRONTEND_DIR`、`REPO_ROOT`（`%DEVUP_SRC_DIR%..\..`）、`ENV_FILE`。
- 其餘邏輯一行未動：分支檢查、`.env` 載入、等 `/health`、port 與 scheduler 偵測。
- 錯誤訊息裡沒有放 `%TEMP%`，因為路徑若含 `)` 會弄壞括號區塊。
- 檔案仍是純 ASCII，CRLF 共 302 行、`\r` 數 302，`file` 顯示 CRLF。
- 副作用：`%TEMP%\stock-desk-dev-up.bat` 是固定檔名，每次執行會覆蓋。同時開兩份 dev-up 時，後啟動的那份會覆蓋前一份正在跑的副本，可能再出現同樣的錯誤。這個情況很少見，我接受。

**dev-up.sh（`apps/stock-desk/dev-up.sh`）**
- 從 `# ---- 0. optional .env` 到結尾整段包進 `main() { ... }`。
- 檔尾改成 `main "$@"; exit $?`，兩者在同一行。bash 先把整行讀完才執行，所以 main 結束後不會再回頭讀檔案。
- trap、`cleanup`、`probe`、`wait_for` 留在函式外，這些都在 pull 之前就已讀完。
- 用 `git diff -w` 看，實質只多 8 行（註解、函式標頭與結尾），其他只是縮排。

**文件**
- `.claude/skills/local-run/SKILL.md` 新增「自我更新防護(N-191)」一條，並提醒日後改腳本時不要把主流程搬出防護區塊。
- 根目錄 `README.md`（`apps/stock-desk/README.md`）不用改。

## 驗證
- `bash -n dev-up.sh`：通過。
- 簡化腳本模擬「執行中被改寫」：
  - 舊寫法印出 `A: start` 後就中斷，後面都沒執行。
  - 包 `main` 的寫法完整印出 `A: after-pull`、`A: end`，rc=0。
- 用真正的 `dev-up.sh` 搭配假的 git、uv、npm、curl 實測。假 `git pull` 會把檔案改寫成較長的版本，並在檔尾追加指令。
  - 新版：pull 之後照常走完 2/4、3/4、4/4 並印出三行 `[OK]` 狀態；我確認檔案確實被改寫（`SHOULD_NOT` 字串存在於磁碟檔案），但那些追加的行沒有被執行。
  - 還原成舊版 `dev-up.sh` 再跑同樣情境：pull 後出現 `line 89: syntax error near unexpected token 'offline,'`，重現了同類問題。
- .bat 只做了靜態檢查（ASCII、CRLF、`%~dp0` 殘留），沒有 CI 可跑。

**建議 CEO 在 Windows 本機驗證**
1. 先確認本機在 `product/stock-desk` 且沒有未提交的改動。
2. 把本分支的 dev-up.bat 版本放到目標位置。需要測「pull 改寫自己」時，先讓本機落後一個動到 dev-up.bat 的 commit（例如 `git reset --hard HEAD~1`；要在不重要的 clone 上做），再雙擊 `dev-up.bat`。
3. 預期：沒有出現「'TARGET_BRANCH' 不是內部或外部命令」和「Branch switch failed」，流程走完 [1/4]～[4/4]，最後有三行 `[OK]` 並開啟瀏覽器。
4. 確認 `%TEMP%\stock-desk-dev-up.bat` 存在，並檢查 `git status` 顯示 `dev-up.bat` 已是新版。
5. 另外測：從別的目錄用完整路徑執行、路徑含空白時是否正常、`.env` 存在時是否仍印 `[ENV] Loading settings from ...`、跳過 pull 之外的 Y/N 提示是否正常。
6. 注意：如果 `dev-up.bat` 本身有 CRLF 被轉成 LF 的情況，`.gitattributes` 已設定，請確認 checkout 後仍為 CRLF。

## 下一步
- 交 qa-reviewer 審查，重點看 bat 守衛區塊的括號解析和 `exit /b !errorlevel!`。
- 審查通過、CEO 在 Windows 驗證 OK 後，由 coordinator 處理 merge 進 `product/stock-desk`。

**回滾方式**：在產品線上 `git revert a71b6c12`，或直接丟棄這個分支；沒有對外發佈動作，也沒有動 main。
