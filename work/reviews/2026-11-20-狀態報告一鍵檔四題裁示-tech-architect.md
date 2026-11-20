# 狀態報告一鍵檔四題裁示（編碼、唯讀範圍、清理、結束碼）

- 審查者：tech-architect
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

四個待決題與兩件順帶確認，每題各給一個答案：

1. **主控台編碼**：選 (d)。`.bat` 不加 `chcp`，Python 端也不改。另新增一項 S-21a，規定第一次 Windows 實機執行時的確認方式。
2. **checkpoint 改動主 DB 位元組**：可以接受。這和 backend、scheduler 的連線最後關閉時的行為一樣，也不影響 CG-3、帳外缺日比對與 F-8。補充十一第 2 點要補一句照實寫明，這句要送風控確認。CEO 說明要寫「不要和其他 stock-desk 一鍵檔同時執行」。
3. **失敗清理的資料夾**：接受，附一條限制：只刪這次執行建立的東西。
4. **`[MISSING] uv`**：實際上很少發生，但有可能發生，所以檢查要留著。從技術面看，我不反對改字；字面由風控定。
- **全套測試**：同意不另外補跑，附一個條件（見下方第 5 項）。
- **工具結束碼**：要寫進補充十一。`verify` 結束碼 1 時工具回 0 可以，但 (c) 要改回 3：凡是印了 STOP 句就回 3。devops-sre 要改一處。

## 各部門回報（tech-architect）

**1. 主控台編碼：選 (d)**
- 理由：腳本只用 `sys.stdout.write` 寫字串，見 `forecast_status.py` 第 151～154 行。
  - stdout 是真正的 cmd 主控台時，Python 3.6 起改用 WindowsConsoleIO（PEP 528），以 UTF-16 呼叫 `WriteConsoleW`。這和 code page 950 無關，`-X utf8` 也不影響。
  - `-I` 會忽略 `PYTHONLEGACYWINDOWSSTDIO`，環境變數改不回舊模式。
  - `uv run` 讓子行程沿用同一個主控台，所以中文應該正常顯示。
  - 這是依 Python 的文件行為推論，沒有在 Windows 上實測。
- 為什麼不選 (a)：`chcp` 會改到 CEO 這個 cmd 視窗的狀態，不能保證切回；而且依上面的推論，它對結果沒有影響。
- 為什麼不選 (b)：以主控台編碼輸出，反而可能在 950 下遇到無法編碼的字（例如 `n̂`），而且會增加與前例的差異。
- 為什麼不選 (c)：(d) 情形時畫面是唯一的輸出，不能接受亂碼。
- 「畫面與檔案逐字相同」比的是腳本寫出的字串，不是主控台的顯示效果。
- 實機確認：接線前那一次 `verify --all` 是 CEO 第一次執行，就當作實機確認。
  - coordinator 核對 CEO 貼回的畫面與 `status.txt` 是否相同。
  - 畫面若是亂碼，退回 devops-sre，再評估 (a)。
- 說明文件加一句：「畫面上的中文若看起來是亂碼，照樣告訴 coordinator」。這句屬 CEO 面字面，由 creative-lead 起草，**送風控**。

**2. 唯讀的實際範圍：可以接受**
- 和 backend 的行為相同：`_read` 是一般連線加 `query_only`，不是 `mode=ro`（`store.py` 第 183～189、645～652 行）。SQLite 的預設行為是：WAL 模式下最後一個連線關閉時，做 checkpoint 並刪掉 `-wal`、`-shm`。backend 和 scheduler 結束時本來就會這樣，邏輯內容不變。
- 逐項影響：
  - **CG-3 `backup_sha256`**：雜湊算的是備份檔本身，不是之後的主 DB。不受影響。
  - **帳外缺日比對**（`gap_check.py` 第 576～604 行）：
    - 兩支同時跑：狀態報告的連線會產生 `-wal`，或改變 `(st_size, st_mtime_ns)`。缺日比對會因此 STOP（`db_in_use`），在檢查失敗時一律停下，不會產生錯誤的資料。這次 STOP 不算「有結果的執行」，不占補充十第 7 點 (d) 的 3 次額度。
    - 狀態報告先跑：反而清掉殘留的 `-wal`，沒有壞處。
  - **D-8 第 3 點與 F-8**：判定依據是整檔還原、更換、重建這類事件，以及核心表列數減少，不看主 DB 的位元組。checkpoint 不屬於這幾種事件。
- 補充十一第 2 點要改字（替換 E1）。這句改寫的是 RC-294 範圍內的揭露，**送風控**確認。
- CEO 說明要寫：「不要在執行其他 stock-desk 一鍵檔的同時執行這一支」。由 creative-lead 起草，**送風控**。

**3. 失敗清理：接受**
- 限制：只刪這次執行建立的東西。
  - 上層的 `~/stock-desk-status` 原本就存在時一律保留，空的也保留。
  - 不得刪除任何不是這次建立的檔案或資料夾。
- 這是實作細節，不改補充十一；請 qa 核對有對應的測試。

**4. `uv` 不存在的情形**
- 平常能用 `dev-up.bat` 啟動，就表示 `uv` 在 PATH 上，所以很少發生。
- 仍可能發生的情形：換了 Windows 帳號、PATH 被其他安裝程式改掉、`uv` 被移除或升級失敗。
- 所以檢查要保留。
- 帶網址的那行會引導 CEO 自己安裝，和 RC-277 的口徑相反。技術面不反對改成只留 `[MISSING] uv`。
- 字面**送風控**定；若改字，`.bat` 與前例的差異測試要跟著更新。

**5. 全套測試：同意不另外補跑**
- 最後一個 commit 只改一處測試的型別標註，而且這支工具的 92 個測試已在 3.12 與 3.13 重跑通過。
- 條件：合併前在合併結果上跑全套，以那一次為準，qa 在審查報告記下結果。
- 另外，devops-sre 待決第 4 項要在合併前確認：固定句測試要從 `work/reviews/` 讀兩份風控報告，要確認 CI 讀得到。

**6. 工具結束碼：要寫進補充十一**
- 依據：結束碼只依「畫面上有沒有固定的 STOP／ERROR 句」決定。這樣 `[NOTE] The tool ended with code 0` 就不會和 STOP 句同時出現。
- `verify` 結束碼 1 時，依第 4 點屬正常完成，畫面有行動句，回 0 可以。
- devops-sre 要改一處：(c) 由 0 改為 3。
- 這不是新的 CEO 面字面，不必送風控；但 E1 送審時一併告知風控。

## 驗證

- 讀過的檔：
  - 交件報告全文：`/home/user/AICompany/work/reviews/2026-11-20-狀態報告一鍵檔交件-devops-sre.md`
  - 補充十一定稿相關行：`/home/user/AICompany/work/reviews/2026-11-20-補充十一草稿-待風控-coordinator組版.md` 第 39～51、70、79～81 行
  - `forecast_status.py` 第 151～209 行
  - `store.py` 的 `_open_connection` 與 `_read`
  - `gap_check.py` 第 545～604 行
  - ADR-0030 的 CG-3 與 F-8
- 第 1 題沒有在 Windows 實測，是依 PEP 528 推論，所以才規定實機確認。
- 第 2 題「最後一個連線關閉時 checkpoint」採信 devops-sre 的實證，我沒有自己重跑。
- 全程唯讀：沒有讀 `.env`，沒有碰 `.db`。

## 下一步

E1（**送風控**確認）
原：
```
     - WAL 模式下，SQLite 會照常建立或更新 `-wal`、`-shm`，與 backend、scheduler 平時的連線相同。
```
新：
```
     - WAL 模式下，SQLite 會照常建立或更新 `-wal`、`-shm`，與 backend、scheduler 平時的連線相同。本工具若是最後一個關閉的連線，SQLite 會把 `-wal` 的內容 checkpoint 進主 DB 本體並刪除 `-wal`、`-shm`，主 DB 檔的位元組與修改時間因此改變，邏輯內容不變；backend、scheduler 的連線最後關閉時也是如此。這裡的「唯讀」指不經 SQL 寫入任何內容，不指主 DB 檔的位元組不變；不得以主 DB 檔的位元組、雜湊或修改時間判讀帳內內容是否改變。
```

E2（新增一行，插在第 4 點以「   - 結束碼：`status` 回傳 0 才算成功。」開頭那一行之後；不必送風控）
```
   - 工具本身的結束碼：`status.txt` 已存檔而且畫面沒有 STOP 或 ERROR 句時為 0（含 `verify` 結束碼 1）；印了 STOP 句時為 3（含 `status` 成功而 `verify` 結束碼 3、4、已存檔的情形）；印 `ERROR: unexpected failure.` 時為 1；印 `ERROR: interrupted.` 時為 2。記事本開啟失敗不改變結束碼。結束碼只供 `.bat` 顯示，任何程式或流程都不得依它判讀帳內內容。
```

E3（新增一行，插在 S-21a 以「  - e2e 擷取 stdout 與 stderr：」開頭那一行之後；不必送風控）
```
  - AST：畫面輸出只經 `sys.stdout.write` 寫字串，不寫 `sys.stdout.buffer`、不呼叫 `reconfigure`；`.bat` 不含 `chcp`。工具結束碼依第 4 點（測試）。Windows 上第一次實際執行（接線前那一次 `verify --all`）視為主控台中文顯示的實機確認：coordinator 核對貼回的畫面與 `status.txt` 相同；畫面為亂碼時退回 devops-sre。
```

分工：
- **coordinator**：套用 E1～E3；E1 送風控確認。
- **devops-sre**：把 (c) 的結束碼改為 3；補「只刪這次建立的東西」測試與 E3 的 AST 測試。
- **creative-lead**：說明文件加兩句：「亂碼照樣告訴 coordinator」與「不要和其他一鍵檔同時執行」，送風控。
- **風控**：裁示 `[MISSING] uv` 那一行的字面。
