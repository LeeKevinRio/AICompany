# 財務資料源 spike 依 qa 退修（B-1、NB-1～NB-10）

- 審查者：data-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

B-1 與 NB-1～NB-10 都已處理（其中 NB-6、NB-7、NB-8 也一併做了），已 push 到 `origin feat/stock-desk-fundamentals-spike`，後端 CI 全綠，工作樹已移除。腳本雜湊和 CEO 文件的核對值已重算並同步。

**待你與 qa-reviewer 確認的一個取捨：P-12 的「INCONCLUSIVE」規則。**
- 審查建議的原文是「任何一檔持股沒抓到就判 INCONCLUSIVE」。
- 我實作成：有正向發現，就判 `HOLDS`，並在判定行註明哪幾檔沒檢查。
- 理由：只要有一檔持股確認是外幣或 IFRS，「有這類持股」就已經成立，另一檔沒抓到不會推翻它。
- 其他情形一律不得判 `NOT_HOLD`：
  - 沒有正向發現且有持股沒抓到：判 `INCONCLUSIVE`，並列出沒抓到的代號。
  - 只有每一檔都抓到且都不是，才判 `NOT_HOLD`。
- 若 qa-reviewer 堅持原文字面，改一行即可。

**NB-5 的做法與審查的字面建議不同，請 qa-reviewer 特別看。**
- 審查建議「關閉轉址」。若只是單純關閉，SEC 存取規範頁一旦搬家，P-5 會變 INCONCLUSIVE。
- 我改成：urllib 一律不自動轉址，由 Fetcher 自己跟隨，最多 2 跳。
- 條件與限制：
  - 只跟 https。
  - 只跟同站；`*.sec.gov` 視為同一站。
  - 每一跳都計入請求上限 30，也套用間隔。
  - 換主機時移除 `Authorization`。
- 轉址因此變成可見、可計數的請求。轉址的最壞情形是 26 + 2 = 28，仍在上限內。

**真實資料的限制不變**：判定邏輯都只驗過假回應。真實 SEC 資料下 NB-1（XBRL 之前的年度）是否如預期，要等 CEO 的輸出才知道。

## 各部門回報（data-engineer）

**Commit 清單**（分支共 8 個，新增 2 個）
- `b4d18bc` fix: spike 腳本修正 qa 審查（B-1 P-12 誤判，及 NB-1～NB-7）
- `0d3b0c2` docs: spike 執行指令依 qa 審查更新（P-12 判讀、隱私提醒、轉址、核對值）

兩個 commit 都帶指定的兩行 trailer。先前的 6 個 commit 未改動，沒有 merge product。

**B-1（P-12 三處）**

| 問題 | 修法 |
| --- | --- |
| 基準公司被算進持股判定 | 只判斷 `ev.holdings`；AAPL、AMZN、INTC 不計入，也不再顯示在 P-12 證據行 |
| 持股沒抓到仍可判 `NOT_HOLD` | 沒抓到的持股一律列出代號；沒有正向發現時判 `INCONCLUSIVE`，持股 404、不在對照檔、請求失敗都屬此類 |
| 用整份文件的單位判外幣 | 改看白名單標籤的單位，加上 `ifrs-full` 是否出現；整份文件零星的外幣單位（外幣債券、衍生品名目金額）另列在證據行，標明「不用於判定」 |

新增測試：
- 持股抓取失敗：
  - 單元測試。
  - 完整跑一遍的 e2e，持股 404 與不在對照檔兩種。
- 美國公司帶零星 EUR、JPY 單位：仍判為非外幣。
- 基準公司為外幣時不影響持股判定。
- 以 US-GAAP 但用人民幣申報的公司，會判為外幣。
- 有正向發現時，另一檔沒抓到仍判 HOLDS。

**一併處理**
- NB-1 P-2：第一份原始年報之前的年度不計入比率，但列在證據行（期間數與前幾筆日期）；範圍內缺原始年報的年度也列出。
- NB-2：`verified` 改為「最近還在用，且至少 3 個不同的全年期間」，不再數 fact 筆數。測了「同一年被 9 份申報報過」不算。
- NB-3 P-1 分兩級：
  - 缺 `accn` 或 `filed`：`NOT_HOLD`，字面開頭 `STRUCTURAL:`。
  - 其他欄位缺：`PARTIAL`，並列出是哪些欄位，註明不是結構性問題。
  - 同一份申報有多組 `fy`／`fp`：仍是 `NOT_HOLD`，字面開頭 `CLAIM REFUTED:`，文件註明它不影響 ADR 的 `start`／`end` 期間鍵。
  - 另外修了一個副作用：缺 `fy` 時不再被當成第二個會計年度。
- NB-4：`except` 補上 `http.client.HTTPException`；測了 `IncompleteRead`、`RemoteDisconnected`、`BadStatusLine`。
- NB-6：移除會誤對 CIK 的無點寫法 `BRKB`。
- NB-7：P-5 的「User-Agent 被接受」要有 200 才寫 yes。
- NB-8：原始碼守則新增：
  - 禁止匯入 `subprocess`、`socket`、`ctypes`、`ssl` 等模組。
  - 禁止 `HTTPConnection`、`os.system`、`eval`、`exec` 等危險呼叫。
  - `.open()` 只允許網址 opener。
- 文件：
  - NB-9：改成「以上任何一行」。
  - NB-10：新增持股代號隱私提醒，意思是不想留痕就不要填，代價是 P-12 只能是 `INCONCLUSIVE`。
  - P-1／P-2／P-3／P-12 的判讀說明對齊新行為。
  - 新增轉址計入請求上限的說明。

**重算後的核對值**（已寫入 CEO 文件）
- 最後修改腳本的 commit：`b4d18bc662d7c7687e59d4800e012d11d068265a`
- `script_sha256_lf`：`01556a87935989fffdcf52ff84548a1aa9f7300b7e7dcc78adcda9ec96fad3fd`
- 這個雜湊是在腳本 commit 後用 `sha256sum` 算的，之後腳本沒再改過。
- 文件 `git check-ignore` 仍為 exit 1（不被忽略），不含真實 email。

## 驗證

CI 原文摘錄（工作樹，`Popen(start_new_session=True)` runner，有 `__main__` guard）：
```
##### ruff check: exit 0   All checks passed!
##### ruff format: exit 0  465 files already formatted
##### mypy strict: exit 0  Success: no issues found in 457 source files
##### pytest: exit 0
TOTAL 19716 503 97%
Required test coverage of 90% reached. Total coverage: 97.45%
8995 passed, 2 xfailed, 34 warnings in 847.24s (0:14:07)
```
- 新測試檔 116 項（上一版 93 項）；單獨跑 116 passed。
- 另用 `--cov=scripts` 量，腳本本身約 99%。
- 腳本另跑過 `mypy --strict`，無錯誤。
- 安全不變項仍有測試把關：
  - 只有 GET。
  - 不碰 DB、不寫檔，唯一的檔案讀取是讀自己（算雜湊）。
  - 不 import `app`。
  - 輸出遮蔽測試仍成立：完整跑後輸出不含假金鑰或假 email，且確認它們確實被拿去發請求。
- 請求數：
  - 正常 22。
  - 最壞 26，不含轉址。
  - 上限 30，由程式強制。
  - 腳本檔頭與文件已同步更新。

## 下一步

1. coordinator 送 **qa-reviewer** 重審，並補跑 Codex 第二意見。上次審查環境沒有 `codex`，目前仍是單家審查。
2. 請 qa-reviewer 特別看三處：
   - P-12 我選的「正向發現優先」規則。
   - NB-5 的跟隨轉址設計。
   - P-2 的「第一份原始年報之前不計入」是否足以避免誤判。
3. 重審通過後交 CEO 在本機執行。核對值已更新，CEO 也可用輸出第三行 `script_sha256_lf` 自行比對。
4. CEO 輸出回來後，由 data-engineer 整理 P 項實測結果交 tech-architect 修訂 ADR-0038。
5. 風險提示：持股代號隱私是否需要更強的處理（例如腳本改為只輸出遮蔽後的代號），目前依 qa 建議只加文件提醒。若 CEO 或風控希望更嚴，可再改。
