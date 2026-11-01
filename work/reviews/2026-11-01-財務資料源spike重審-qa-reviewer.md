# 財務資料源 spike 重審（PASS）

- 審查者：qa-reviewer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS　BLOCKING_ISSUES=false**

上次的阻擋點 B-1（P-12 三處誤判）已修好，NB-1～NB-10 也都有處理。審查範圍是增量 `git diff fbe49d1 origin/feat/stock-desk-fundamentals-spike`，共 3 個檔案：腳本、測試、CEO 文件。上一輪審過的 `.env.example` 在這次增量沒有變動。

`git diff 51cf647^..origin/...` 這個範圍不適合，會夾進一大批無關的 `work/` 檔案（27 個檔案），所以我改用上一輪審過的最後一個 commit（`fbe49d1`）當基準。

三個請你裁定的問題，我的回答如下。

1. **P-12 採「正向發現優先」。**
   - `HOLDS` 的語意是「您的持股裡有這類公司」，是存在性的宣稱。只要有一檔確認是外幣或 IFRS，這個宣稱就成立，另一檔沒抓到推翻不了它。
   - 我上次寫的「任何一檔沒抓到就判 `INCONCLUSIVE`」，真正要防的是「沒抓到卻判 `NOT_HOLD`」。現在的規則已防住，並且在判定行與證據行註明沒檢查的代號。
   - 規則是三段，沒有漏洞：有正向發現判 `HOLDS`；全部抓到且都不是才判 `NOT_HOLD`；其餘判 `INCONCLUSIVE`。
   - 我不要求改回字面版本。
2. **NB-5 的改法比我建議的更好，接受。**
   - 這個設計比單純關閉轉址好，因為單純關閉會讓 SEC 頁面一搬家，P-5 就變 `INCONCLUSIVE`。
   - 實作是 `_NoRedirect` 讓 urllib 回傳 3xx，由 Fetcher 自己跟隨。
   - 條件逐項核對過：最多 2 跳；只走 https；只限同站（同主機，或兩邊都屬 `sec.gov`）。
   - 每一跳都走 `_once`，所以都經過 `Budget.take()` 和間隔等待。
   - 換主機時會移除 `Authorization`。
   - 輸出的轉址紀錄只印主機和路徑，不印查詢字串，所以不會洩漏 token。
   - 304 不在轉址狀態碼內，條件式請求不受影響。
   - 測試涵蓋：逐跳計數、跳數上限、降級到 http 或跨站不跟、移除授權標頭、上限內擋下、被轉址的存取規範頁仍被讀到。
3. **P-2 的新做法足以避免誤判。**
   - 邏輯是「每個標籤各自找出最早的原始申報年度，更早的年度只列不計」。
   - 這正好解掉我先前指出的 XBRL 之前年度（例如 AAPL 的 FY2007、FY2008）把比率壓到 88% 的問題。標籤中途換新，其更早年度也同樣被排除。
   - 排除的期間數和前 6 筆日期，以及範圍內缺原始年報的年度（數量和前 4 筆）都印在證據行，人工看得出有沒有被濫用。
   - 範圍內缺原始年報的年度仍會拉低比率，測試 `drop_original=2022` 驗證會判 `PARTIAL`。

核對值也一致，見驗證段。

## 各部門回報

### qa-reviewer 增量審查（三個檔案逐檔看過）

**`fundamentals_spike.py`**

- **P-12（`eval_p12`）**
  - 只判 `ev.holdings`，AAPL、AMZN、INTC 不再計入。
  - 外幣判斷改看白名單標籤的單位加 `ifrs-full`，整份文件的零星外幣單位另列、標明不用於判定。
  - 沒抓到的持股一律列出代號。
  - 補了五個新測試：只判持股、IFRS 與人民幣、美國公司帶 EUR／JPY、持股沒抓到、正向發現優先。
  - 另外有兩個端對端測試，涵蓋持股 404 和不在對照檔。
- **P-1**
  - 結構性缺漏只剩 `accn`、`filed`，輸出以 `STRUCTURAL:` 開頭。
  - 其他欄位缺漏降為 `PARTIAL`。
  - 多組 `fy`／`fp` 仍是 `NOT_HOLD`，輸出以 `CLAIM REFUTED:` 開頭，文件註明不影響 ADR 以 `start`／`end` 當期間鍵。
  - 缺 `fy` 不再被當成第二個會計年度，副作用也修了。
- **P-3**：`verified` 改數不同的全年期間（`VERIFIED_MIN_YEARS=3`），測試證明同一年被 9 份申報報過不算。
- **P-5**：「User-Agent 被接受」改成要有 200 才寫 yes。
- **傳輸層**：補了 `http.client.HTTPException`，測了 `IncompleteRead`、`RemoteDisconnected`、`BadStatusLine`。
- **代號正規化**：移除無點寫法 `BRKB`。
- **安全不變項**：沒有退步。
  - 仍是 GET 且沒有 `data=`，不碰 DB，不寫檔。
  - 新增的 `http.client` 只拿來取例外型別，沒有開連線。
  - 輸出仍經 `Redactor`。
  - 新增的 `location` 標頭只用於跟隨，不會被印出。

**`test_fundamentals_spike.py`**

- 測試數：增量 +21 個 `def test_`，加上 `parametrize` 多出的 2 項，90 → 111 → 116，與交件的 116 項吻合。
- 原始碼守則加固，涵蓋 NB-8：
  - 禁止匯入 `subprocess`、`socket`、`ctypes`、`ssl` 等。
  - 禁止 `HTTPConnection`、`system`、`popen`、`eval`、`exec`、`compile`、`__import__`。
  - `.open()` 只允許 `_OPENER`。
  - 另一個測試鎖住 urllib 不得自動轉址，原始碼不得出現 `urllib.request.urlopen(`。

**`work/research/財務資料源spike-執行指令-2026-11-01.md`**

- 已新增：轉址說明、P-1／P-2／P-3／P-12 判讀、NB-9 措辭、NB-10 隱私提醒。
- 隱私提醒寫明持股代號會進對話、可能被 commit、repo 可能公開，不想留痕就不要填，代價只有 P-12 是 `INCONCLUSIVE`。這個內容足夠。

### 新的 NB（均不擋件）

- **NB-11　CEO 文件第 283 行附近【可維護性／low】**
  - 單元測試段落仍寫「較早的比較期缺原始申報會判 P-2 部分成立」。
  - 依現在的行為，早於第一份原始年報的年度會被排除，該情境改判 `HOLDS`；只有「範圍內缺原始年報」才是 `PARTIAL`。
  - 建議改成「範圍內缺原始申報會判 P-2 部分成立」。
- **NB-12　CEO 文件請求數說明、`fundamentals_spike.py` 檔頭【可維護性／low】**
  - 文件寫「最壞情形（26 次再加兩次轉址）也低於上限」，但每個請求都可能各自轉址，不只兩次。
  - 實際上由 30 的上限強制保證，不會超過，只是說法不精確。
  - 建議改成「轉址會額外耗用上限內的請求；超過 30 就停」。
- **NB-13　`fundamentals_spike.py` P-2 證據行【可維護性／low】**
  - 排除清單用 `sorted(set(...))[:6]`，只會顯示最早的 6 筆。
  - 若最近才有排除年度，不容易看到，但已印出總期間數，影響很小。

### 章程檢查

- 範圍：只動腳本、測試、CEO 文件，三個檔案都在 `apps/stock-desk/` 與 `work/research/` 內。
- 祕密掃描：增量內容只出現測試用假值，沒有真實祕密。
- trailer：我只被允許用 `git diff`，無法讀 commit message，只能採信 data-engineer 回報（兩個新 commit `b4d18bc`、`0d3b0c2` 都帶指定的兩行 trailer）。合併前請另行核對。

## 驗證

- **核對值與分支一致。**
  - CEO 文件預期 commit：`b4d18bc662d7c7687e59d4800e012d11d068265a`。
  - `git diff b4d18bc… origin/feat/…` 只有 CEO 文件 1 個檔案有差異，所以腳本在該 commit 之後沒有再被改過。
  - `git diff b4d18bc^ b4d18bc` 顯示該 commit 修改了腳本與測試，確定它是「最後修改腳本」的 commit。
  - 文件第 120 行與附錄 bash 版（第 302 行附近）的 commit 值一致。
- **雜湊未能獨立核對。**
  - `script_sha256_lf` 預期值 `01556a87935989fffdcf52ff84548a1aa9f7300b7e7dcc78adcda9ec96fad3fd`，我的 Bash 範圍只有 `git diff`，無法重算。
  - 這個雜湊由 data-engineer 在腳本 commit 後用 `sha256sum` 算出，腳本之後也沒有再改。
  - CEO 端輸出第三行會自動比對，可作為把關。
- **Codex 第二意見：未取得。** `codex --version` 回 `command not found`（exit 127）。**單家審查，Codex 待環境可用時補跑。**
- **測試未獨立執行。** 測試通過與否（pytest 8995 passed、ruff 與 mypy 全綠、單獨跑 116 passed）採信交件說明。
- **Bash 使用紀錄。**
  - 用過：`git diff`（`--stat`、各路徑、各範圍）、`codex --version`。
  - 我又嘗試 `git diff fbe49d1 origin/... -- apps/stock-desk/.env.example`，被權限系統拒絕。這次不再繞過，因為增量 `--stat` 顯示 `.env.example` 沒有在這次異動。
  - 沒有用到白名單以外的 Bash 指令。
- **唯讀權限判準常數**：未觸及。這次增量只有 3 個檔案，沒有 `scripts/validate_agents.py`；增量內容也沒有出現 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH`。這兩道檢查我都以檢視 `--stat` 與逐檔 diff 完成，沒有使用 pipe。

## 下一步

1. 可交 CEO 在有網路的 Windows 機器執行，步驟照 `work/research/財務資料源spike-執行指令-2026-11-01.md`。
2. NB-11、NB-12、NB-13 不擋件。若 data-engineer 之後還有改動，可順手處理。若修改了腳本，核對值與 commit 要重算。
3. 合併前請另行核對兩個新 commit 的 trailer，並在 Codex 可用時補跑第二意見。
4. CEO 輸出回來後，由 data-engineer 整理 P 項實測結果交 tech-architect 修訂 ADR-0038。真實資料下 P-2 的排除年度是否如預期、P-12 的結果，都要看實測。
5. 這是純邏輯與文件類，不涉及 UI，不需要 qa-e2e。

## Verdict
PASS
BLOCKING_ISSUES=false

審查範圍的檔案：
- /home/user/AICompany/apps/stock-desk/backend/scripts/fundamentals_spike.py（分支 `origin/feat/stock-desk-fundamentals-spike`）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_fundamentals_spike.py（同上）
- /home/user/AICompany/work/research/財務資料源spike-執行指令-2026-11-01.md（同上）
- /home/user/AICompany/work/reviews/2026-11-01-財務資料源spike退修-data-engineer.md
