# export 修正知悉、警示手冊不維護、§4、QuickEdit 相關字面（RC-495～RC-506）

- 審查者：risk-compliance-officer
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# risk-compliance-officer 判定：export 寫法漏網、警示手冊不維護、§4 與 ADR-0029、QuickEdit（RC-495～RC-506）

- 審查者：risk-compliance-officer，日期 2026-11-21
- 全程唯讀，只用了 Read、Glob、Grep。沒有寫檔，沒有讀任何 `.env*`，沒有碰 `apps/stock-desk/backend/data/`，也沒有執行 git 或 uv。
- 依據：`/home/user/AICompany/work/reviews/2026-11-21-export寫法漏網與警示手冊維護與QuickEdit裁示-tech-architect.md`（全文）。

---

# 第一件：`export` 寫法讓登記預檢漏網（裁示 (甲)，知悉級）

## 本次結論
- **知悉 (甲)。在「CEO 看得到的字面零變動」這個約束下，不需要新的 CEO 字面（RC-495）。**
- **M-2、M-3、M-6 要在新 head 上重新核對，只做輕量核對（RC-496）。**
- **證據句的更正：知悉。RC-418 與 RC-457 第 4 點的理由句要調整，登記紀錄的註記改用新字面（RC-497）。**
- **不告知 CEO（RC-498）。**

## 各部門回報（risk-compliance-officer）

### [RC-495] 不需要新的 CEO 字面（required 條件一項）
- STOP 原文是 `STOP: STOCK_DESK_DB_PATH is set in the .env file of the app.`。正式登記操作說明第 104 行的說明是「`.env` 檔裡有指定資料庫位置的設定。程式只檢查有沒有這個設定名稱，不會讀其他內容。」放寬到 `export` 寫法和不分大小寫之後，這兩句都還是正確的：抓到的仍然是「指定資料庫位置的設定」，也仍然只看鍵名。所以不用改字。
- 修正後，CEO 在預檢遇到這個 STOP 的機會會變大。處理路徑沿用現有的「告訴 coordinator」，再照 RC-417 (d) 辦：不叫 CEO 移除設定，當天轉 tech-architect。
- **條件（required）：**「零變動」要在新 head 上有證據，由 RC-496 第 (e)、(f) 項提供。

### [RC-496] M-9 裡 M-2、M-3、M-6 在新 head 上重新核對（required）
- 理由：我 11-17 的核對寫明的是 head `9d5bbf48`，而 M-9 的對象是 PR head。這次的修改本身碰不到 M-2、M-3、M-6 的內容，所以只核對「內容沒變」，不重做實質審查。
- **coordinator 在新 head 上附原始輸出：**
  - (a) `git diff --name-status 9d5bbf48 <新 head>`：變動檔案要在約束第 1、6、8 點允許的範圍內。
  - (b) `git diff 9d5bbf48 <新 head> --` 加上以下路徑，要沒有任何輸出：事先宣告 v0.32、C-8 紀錄檔、`app/outlook/rules/`、`app/dirdef/`、`app/forecast/definitions.py`、`app/advice/banned_phrases.py`。
  - (c) 兩份文件的 blob id，以及 `git cat-file blob <新 head>:<path> | sha256sum`：要等於 11-17 的值（`7c45b0ba…b406e`、`c942642c…a54f`）。另附兩份文件的 `ls-files --eol`。
  - (d) 在新 head 重跑 `definitions.registration_phrase_scan` 的原始輸出：h3、h5 都要是 `hits 0`，字串數 159／12／10 都不變。
  - (e) `git diff 9d5bbf48 <新 head> -- apps/stock-desk/backend/scripts/cg2_register.py` 的全文：只能動 `ENV_KEY_PATTERN`、`app_tree_id`，以及必要的註解。`REAL_PINS` 的 frozen_files、definition、rules、review_refs 都不變，固定句（`_TELL` 與各 STOP 句）也不變。
  - (f) qa 對 `verify_cg2_instruction.py` 通過、兩支 cg2 `.bat` 與登記操作說明零差異的確認句。
- **我會出一份補充核對報告，11-17 那份保留不動。** 補充報告要在 CG-2 合併 commit 的 `HEAD` 裡，qa 的 M-9 最終紀錄要引用它的路徑。
- `review_refs` 要不要加入補充報告或新的 qa 紀錄，由 tech-architect 裁示，因為這牽涉約束第 8 點「`REAL_PINS` 不得變動」的範圍。我不要求加入；若加入，我也不反對。
- 我核對之後 head 若又改變：重附 (a)(b)(c)(d)(e)，我只核對有差異的地方。

### [RC-497] 證據句更正後的調整（required）
- RC-418 的理由句「登記成功就證明當時沒有設」、RC-457 第 4 點的「登記成功就表示當時沒有設」，一律改讀成「登記當時，程序環境變數沒有設，`.env` 裡也沒有預檢比對得到的寫法」。修正之後也不得用「證明」：盤點表裡還有幾種寫法沒有查證，Windows 實機探測也還沒做。
- 兩條的處置不變。RC-418「不單獨通知」的另外兩個理由仍然成立；RC-457「README PR 在登記之後合併」也不變。
- 我在 RC-418 末段同意的註記字面，由下面這段取代：

項目：登記紀錄的 `env`／`.env` 註記（取代 RC-418 末段同意的字面）
定稿全文：
````
登記成功：登記當時，程序環境變數沒有設定 STOCK_DESK_DB_PATH，app 的 .env 裡也沒有預檢比對得到的 STOCK_DESK_DB_PATH 設定行（補充四第 2 點；比對規則為 CG-2 合併 commit {SHA} 中的 ENV_KEY_PATTERN）。uv 會載入哪些寫法：Linux 上由 dev-lead 以 uv {版本} 實測；Windows 實機探測：{已完成，見 {路徑}／未完成}。本註記不涵蓋登記之後 .env 的變動。
````
- suggested（轉 tech-architect）：要不要把 Windows 實機探測列為登記的前置條件，由 tech-architect 裁示。

### [RC-498] 不告知 CEO（required）
- 理由：
  - CEO 看得到的字面零變動；
  - CEO 還沒有被要求登記，預檢也還沒有通知；
  - 修正與否都不需要 CEO 操作或決定（tech-architect 已書面確認）；
  - 單獨告知等於提示 CEO 去打開 `.env`（RC-418、RC-432 (c)）。
- **禁說（任何對 CEO 的文字）：**
  - `export`、大小寫、regex、漏洞、「預檢有問題」；
  - 叫 CEO 查看或確認 `.env`、環境變數；
  - 「可能需要您決定」（RC-424）；
  - 「安全」「沒有影響」「不用擔心」；
  - 任何登記日期或「很快」。
- CEO 主動問登記的時程時，用下面這句：

項目：CEO 問「什麼時候登記」時的回覆句
定稿全文：
````
正式登記還在準備中；需要您操作時，我會再告訴您要做什麼。
````

- CEO 追問原因，或問「是不是有問題」時，用下面這句：

項目：CEO 追問登記延後的原因時的回覆句
定稿全文：
````
登記之前，團隊在補強一項登記前的自動檢查。這不需要您做任何操作，也不需要您查看任何設定；需要您操作時，我會再告訴您。
````

- 兩句都不得和其他系列（R、S、A、B、RC-471／RC-489）的訊息放在同一則。

---

# 第二件：警示評估載入失敗檢查手冊「不維護」

## 本次結論
**維持現行字面，不補（RC-499）。** 這次合併照常進行，也不另開只改一行的 PR。

## 各部門回報（risk-compliance-officer）

### [RC-499]（required）
- **理由：**
  - A-0 第 6 行寫「供團隊參考；裡面的畫面字面與做法可能已經過時」，在「不維護」之下仍然正確，沒有擔保會更新；
  - 第 7 行禁止照做，第 12 行寫「需要任何一步時由 coordinator 告訴您」，CEO 的行為不依賴「會不會再更新」；
  - 少這一句不構成隱藏風險；
  - 補上要重做 RC-474 確認、換 head、qa 重核。為了一句非必要的資訊付這個代價不值得，也會讓 RC-487 的合併條件重新開啟。
- **連帶規則：**
  - RC-474 對警示手冊的「指定維護人後的例外」**撤銷**，比照族群手冊：這份檔任何一處要改，都先送我。
  - 日後若因為其他原因要改 A-0，**在同一次變更**補上「之後不會再更新」，送我審。
  - 禁說：對 CEO 說這份手冊「會更新」「之後會改正」。
- RC-471、RC-489 的告知字面不受影響。

---

# 第三件：§4 未被 ADR-0029 涵蓋（知悉級，內部紀錄）

### [RC-500]
- **知悉。** A-5 的字面「不是向您提出的問題」「需要您決定的事，由 coordinator 另外問您」仍然成立，不用改。追蹤清單照 tech-architect 的建議記一列。
- **required：**
  - 日後若立案做「警示評估載入失敗」的自動告警，凡是有 CEO 看得到的推播或字面，先送我。
  - 若在 CEO 決定 #43 之前原地修訂 ADR-0029、把這個事件加進列舉，#43 給 CEO 的說明要跟著更新，並送我審，因為 CEO 要決定的內容變了。

---

# 第四件：QuickEdit 與要 CEO 看 scheduler 視窗的文字

## 本次結論
1. **RC-320 第三條門檻撤回。** B 的那一列改字，並在「請不要做的事」新增第 6 點（RC-501）。
2. **S-b 改字；R 系列與 S-a、S-b2 不改（RC-502）。** 截圖本身沒有問題。問題在 S-b 的「照樣告訴我」沒有限定是哪個視窗，CEO 可能會到 scheduler 視窗選取、複製文字。
3. **RC-469 的三份檔頭已經足夠，不改（RC-503）。**
4. **第 206、211 行列入日後改字待辦，低優先（RC-504）。** 事實更正：這兩行指的是 backend 和 frontend 視窗，不是 scheduler 視窗。
5. **scheduler 程序內的修正若讓 CEO 看得到行為改變，要告知 CEO。** 由 creative-lead 起草，我審（RC-505）。
6. **查證之前不單獨通知 CEO。** 查證成立時另有觸發條件（RC-506）。

## 各部門回報（risk-compliance-officer）

### [RC-501] RC-320 第三條門檻與 B 文件（required，B 送出前套用）
- RC-320 第三點撤回。第一、二點和「之後」那一段照舊。
- 撤回的理由：未接線時，不記錄會由狀態報告的前兩條門檻抓到，延遲最多一週，B 第 118 行已經揭露。第三條要 CEO 去看 scheduler 視窗，而查證之前，這正是要避免的事。
- 套用對象是 B 的正本（主工作樹的 `work/dispatch/2026-11-20-預測記錄條件通知-CEO-草稿.md`）。有多份 worktree 副本：coordinator 先確認哪一份是正本，再用 Grep 確認「原」只出現一次。我在主工作樹確認過，兩處各只出現一次（第 147、137 行）。

替換 1（B「您可能會看到什麼」表格）
原：
````
| scheduler 視窗出現以 `forecast_record:` 開頭的英文行（不只一種） | 這些只是執行狀態。有些行的英文可能提到某個操作，也不要自己照做。連續 2 個平日以上都出現 → 告訴 coordinator | 判斷結果；可以據此推論當晚的資料或判斷 |
````
新：
````
| scheduler 視窗出現以 `forecast_record:` 開頭的英文行（不只一種） | 這些只是執行狀態，不需要特地去看，也不需要為此告訴 coordinator；有沒有記錄，以狀態報告為準。有些行的英文可能提到某個操作，也不要自己照做 | 判斷結果；可以據此推論當晚的資料或判斷 |
````

替換 2（B「請不要做的事」，在第 5 點之後新增第 6 點）
原：
````
5. 不要自己輸入其他指令；只執行狀態報告一鍵檔。
````
新：
````
5. 不要自己輸入其他指令；只執行狀態報告一鍵檔。
6. 不要在標題是 `stock-desk scheduler` 的視窗裡用滑鼠點選、拖曳選取或複製文字，也不要在裡面按 Ctrl+F 或 Ctrl+S；不需要去看或捲動它的內容。在這個視窗裡選取文字，有可能讓 scheduler 暫停，背景更新、警示和預測記錄可能因此延後，當晚的預測記錄也可能沒有記下；這一點還沒有在 Windows 上實際測試過。不小心點到、視窗標題出現「選取」或「Select」時，按一次 Esc 鍵，並告訴 coordinator。
````
- 第 135 行「不要因為看到下面的英文行…」不用改。
- 這兩處併入 RC-324 的單項確認，由我逐字比對。
- 禁說：「點了就會停」（沒有查證）、「不會影響」。

### [RC-502] S-b、R 系列的「截圖也可以」（required）

替換（S-b 定稿最後一句；S-b 其餘部分不變）
原：
````
畫面上若看到英文的錯誤行，或有哪裡看起來不對，方便時可以照樣告訴我（截圖也可以）；不需要說明原因。
````
新：
````
畫面上若看到英文的錯誤行，或有哪裡看起來不對，方便時可以截圖告訴我；請不要為此在標題是 `stock-desk scheduler` 的視窗裡點選、選取或複製文字。不需要說明原因。
````
- **R 系列、S-a、S-b2 不改。** 它們要 CEO 回報的行都印在 `dev-up.bat` 主視窗，包括三行、`Done.`、Y/N 提示，以及 `[STOP]`／`[FAILED]`／`[TIMEOUT]`／`Cancelled.`。在主視窗選取文字不影響 scheduler。RC-494 的結論不變。
- coordinator 處理註記：CEO 的回報看起來是從 scheduler 視窗複製來的時候（例如 `forecast_record:` 開頭的行），照實記錄，不追問那個視窗的其他內容，並轉 devops-sre 作為查證的背景資料。
- S-b 若已經用過舊版，不送更正，只照上一條記錄。

### [RC-503] RC-469 三份檔頭：足夠
- 警示手冊的 A-0、A-1 已經禁止在 scheduler 視窗搜尋或判讀 log；族群手冊的檔頭與 G 系列禁止照文件的任何步驟做，涵蓋捲動和 Ctrl+F。
- 檔頭的任務是讓 CEO 不要照手冊做，不負責發布通則。通則放在 B 第 6 點。
- 不改，RC-487 照舊合併。

### [RC-504] `dev-up.bat` 第 206、211 行（待辦，低優先）
- 事實（丙的工作樹）：第 206 行指的是 `'stock-desk backend'` 視窗，第 211 行指的是 `'stock-desk frontend'` 視窗，都不是 scheduler 視窗。第 206 行觸發時，scheduler 還沒有啟動（第 170 行才啟動）。
- 列入待辦的理由不是 QuickEdit：這兩行叫人自己去看錯誤，而且寫「Claude」，和 RC-446 的方向不一致。另外，backend 視窗被選取時，【推論】可能讓 backend 卡住。
- **時點：**丙合併、登記完成、接線合併之後，下一次 `dev-up.bat` 改 `echo` 的 PR 一併處理。不單獨開 PR，不併入丙（RC-493），不在預檢到登記完成之間 push。只能改 `echo`（ADR-0012 補充一 (b)(iii)）。字面先送我，方向比照第 191 行：「Do not try to fix it yourself. Tell the coordinator.」

### [RC-505] scheduler 程序內修正的告知（required，日後）
- **方向 ①**（關掉 QuickEdit，CEO 不能再在 scheduler 視窗選取文字）：CEO 看得到行為改變，**要告知**。
  - 起草：creative-lead，依 tech-architect 或 devops-sre 書面寫出的事實；我審；coordinator 送。
  - 時點：修正合併後，下一次非急迫的訊息，單獨一則。不在預檢到登記完成之間送，不和 R、S 系列放在同一則。
  - 內容要寫：發生了什麼改變、不需要做任何操作。B 第 6 點仍然有效，因為選單的「標記」和 Ctrl+S 仍然會擋住輸出。
- **方向 ②**（`QueueHandler`）：tech-architect 書面寫明 CEO 看不到任何改變的話，不用告知。
- 要放寬或刪除 B 第 6 點，不論哪個方向，或查證結果否定了推論，字面都先送我。在我核准之前，第 6 點照舊。

### [RC-506] 查證之前（required）
- **不單獨通知 CEO。** 推論還沒有查證；CEO 目前也沒有被任何文字引導到 scheduler 視窗。B 送出時，第 6 點就會交代。
- **觸發條件：**devops-sre 的實機結果**證實**推論，而 B 那時還沒有送出時，當天把結果送我。我再決定要不要把第 6 點的內容先單獨送 CEO，因為警示是面向使用者的功能。
- product 上第 191 行的舊字面（叫 CEO 去看 scheduler 視窗）在丙合併後就會消失。在那之前，R 系列已經要求 CEO「不要自己處理，直接告訴我」，不另外處理。

---

## 驗證
- **讀過：**
  - tech-architect 本日報告全文，以及 11-21 心跳裁示第 95～117 行；
  - 我的 11-17 M-9 核對全文、RC-407～RC-421 第 240～359 行、RC-456～RC-468 第 55～104 行、RC-469～RC-486 第 1～240、500～579 行、RC-487～RC-494 全文、RC-313～RC-324 第 60～119 行；
  - B 文件第 95～174 行；
  - 警示手冊與族群手冊檔頭（`agent-ad164245da4946303` 工作樹）；
  - 丙工作樹的 `dev-up.bat` 第 160～215 行；
  - `agent-a16d399220753e66d` 工作樹的 `cg2_register.py` 第 95～234 行；
  - 正式登記操作說明第 104 行。
- **Grep：**
  - B 文件的兩個「原」都只出現一次（主工作樹第 137、147 行）；
  - `截圖也可以`、`scheduler 視窗` 在 reviews 與 dispatch 的命中處；
  - RC-418 的引用處；
  - `claims.py` 的 `_ENV_FILE_KEY`。
- **觀察（沒有審）：**`agent-a16d399220753e66d` 工作樹的 `claims.py` 第 294 行已經是新的 pattern（`(?:export\s+)?`、`re.IGNORECASE`），`cg2_register.py` 第 103 行還是舊的。dev-lead 應該還在進行中。這不是我的審查對象，兩者是否一致由 qa 依約束第 1 點核對。
- **沒有查證：**
  - QuickEdit 的全部行為、Esc 能不能解除選取、主控台標題的實際字樣（「選取」或「Select」）、CEO 用的是哪一種主控台；
  - uv 的 dotenv 規則與 Windows 上的大小寫行為；
  - 新 head 是否存在、CG-2 是否還沒合併；
  - B 正本是哪一份；S-b 有沒有用過；
  - `review_refs` 屬不屬於約束第 8 點的「M-2～M-5 `REAL_PINS`」；
  - 追蹤清單第 692、723 行被省略的內容。

## 下一步
- **coordinator：**
  - 新 head 定案後，依 RC-496 附 (a)～(f) 送我；
  - 登記紀錄改用 RC-497 的註記；
  - 追蹤清單裡引用「登記成功就證明／表示當時沒有設」的列，依 RC-497 改讀；
  - 依 RC-501 套用 B 的兩處、依 RC-502 套用 S-b；
  - 記下 RC-499、RC-500、RC-504～RC-506；RC-487 照舊合併。
- **tech-architect：**裁示 `review_refs` 要不要更新（RC-496）；Windows 探測要不要列為登記前置條件（RC-497，suggested）。
- **devops-sre：**QuickEdit 實機驗證時加測「Esc 能否解除選取」與「標題字樣」，結果書面送 tech-architect 和我（RC-506）。
- **qa-reviewer：**M-9 最終紀錄引用我的補充報告；依 RC-496 (f) 提供確認句。
- **creative-lead：**目前沒有工作；RC-505 方向 ① 落地時起草。
- **CEO：**四件都沒有需要決定或操作的事。

相關路徑：
- /home/user/AICompany/work/reviews/2026-11-21-export寫法漏網與警示手冊維護與QuickEdit裁示-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md
- /home/user/AICompany/work/dispatch/2026-11-20-預測記錄條件通知-CEO-草稿.md
- /home/user/AICompany/work/reviews/2026-11-21-三份舊文件標註定稿與過渡規則延伸與啟動重啟回覆句與env範本問句RC469至RC486-風控.md
- /home/user/AICompany/work/reviews/2026-11-21-重啟請求定稿與手冊0.2及0.3節與attestation告知RC407至RC421-風控.md
- /home/user/AICompany/.claude/worktrees/agent-ad164245da4946303/work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md
- /home/user/AICompany/.claude/worktrees/agent-ae9857ccf30c8de4a/apps/stock-desk/dev-up.bat
- /home/user/AICompany/.claude/worktrees/agent-a16d399220753e66d/apps/stock-desk/backend/scripts/cg2_register.py
- /home/user/AICompany/.claude/worktrees/agent-a16d399220753e66d/apps/stock-desk/backend/app/forecast/claims.py
