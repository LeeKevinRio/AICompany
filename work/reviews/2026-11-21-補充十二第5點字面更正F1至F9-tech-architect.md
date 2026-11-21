# 補充十二第 5 點與 S-21 的字面更正（替換 F1～F9）

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- 第 5 點 (a) 第二項確實與事實不符，要更正。基準檔「存進 git 的 blob」等於 G_acc 上 `.bat` 的 blob（LF），CRLF 只在測試的記憶體裡還原。技術意旨不變（替換 F1）。
- 第 5 點 (b) 的 `-text` 要補一句作用說明（F3）。
- 三個分支各自帶入位元組相同的兩個檔，**這個做法符合規格意旨**。產品線最終只有一條路徑、一份內容。git 對相同內容的新增不會判為衝突；內容不同就會衝突，這本身也是一道防線。不過第 1 點 (e)、第 5 點 (b) 與 S-21 第 1、5 點的字面要跟著改：如果先合併的一鍵檔分支已經把兩檔帶進產品線，退役 PR 的「檔案清單恰好」就會不成立（F4、F6、F7、F8）。
- merge-base 的 blob id **不寫死**進 ADR，記在 PR 說明（F2）。理由是 G_acc 還沒取得。這一條的用意是「實際比對兩個 blob id」，先寫死預期值就把比對變成背書。萬一真的不同，條文會變成自相矛盾。
- S-21 第 5 點「sha256 等於 G_acc 那個 blob 的 sha256」在技術上仍然正確：`git cat-file blob` 輸出的是 LF 位元組，算出來是 `07265206…`。但它容易被誤讀成 CRLF checkout 的雜湊，所以要釐清（F5、F8）。
- 風控：F1、F2、F3、F5 是「字面對齊事實」的更正。F4、F6、F7、F8 改了可檢查的條件（檔案清單改成有條件、新增三分支核對）。我建議全部連同檔頭補述（F9）一次送風控單項過目，其中 F4、F6、F7、F8 請風控實質看。

## 二、各部門回報（tech-architect）

### 替換字面

替換 F1（第 5 點 (a) 第二項）
原：
```
     - 這份基準檔的位元組等於 `git cat-file blob <G_acc>:apps/stock-desk/pipeline-acceptance.bat`，CRLF 也一起保留。
```
新：
```
     - 這份基準檔存進 git 的 blob 等於 `<G_acc>:apps/stock-desk/pipeline-acceptance.bat` 的 blob（blob id 相同）。該 blob 是 LF；CRLF 只由 repo 根目錄 `.gitattributes` 的 `*.bat text eol=crlf` 在 checkout 時產生。基準檔不得寫入 CRLF；比對時，測試先斷言檔內沒有 `\r`，再在記憶體中把 `\n` 換成 `\r\n` 後切行，得到與 CRLF checkout 相同的行序列。
```

替換 F2（第 5 點 (a) 第三項；不寫死 blob id）
原：
```
     - 它同時必須等於本退役 PR 的 merge-base 上同一路徑的 blob。兩者不同就停止，升級 tech-architect。
```
新：
```
     - 該 blob id 同時必須等於本退役 PR 的 merge-base 上 `apps/stock-desk/pipeline-acceptance.bat` 的 blob id。兩者不同就停止，升級 tech-architect。具體 blob id 不寫進本 ADR，記在 PR 說明（(b)）。
```

替換 F3（第 5 點 (b)，`-text` 的作用）
原：
```
     - 同一資料夾放一個 `.gitattributes`，把該檔設為 `-text`。不得改 `backend/.gitattributes`（第 1 點 (b) 的測試釘住了它的內容），也不得改 repo 根目錄的 `.gitattributes`（main 維持零產品耦合）。
```
新：
```
     - 同一資料夾放一個 `.gitattributes`，把該檔設為 `-text`。作用是 add 與 checkout 都不做換行轉換（`core.autocrlf=true` 也一樣），使工作樹位元組等於 LF 的 blob；不得改設為 `text` 或 `eol=crlf`。不得改 `backend/.gitattributes`（第 1 點 (b) 的測試釘住了它的內容），也不得改 repo 根目錄的 `.gitattributes`（main 維持零產品耦合）。
```

替換 F4（第 5 點 (b)，三個分支各自帶入）
原：`     - 全產品線只有一份。兩支分支引用同一個路徑；qa 核對兩支分支內的位元組相同。`
新：
```
     - 全產品線只有一份，路徑固定為 `backend/tests/fixtures/pipeline_acceptance_bat_frozen.txt`，`.gitattributes` 放在同一資料夾。兩支一鍵檔分支與本退役 PR 各自帶入這兩檔，位元組相同；git 合併時視為相同的新增，不論合併先後，產品線上只有一份。三個分支上這兩檔的 blob id 必須各自相同；任一分支不同就停止，升級 tech-architect，不得以合併時解衝突的方式處理。
```

替換 F5（第 5 點 (b)，sha256 的計算對象）
原：
```
     - PR 說明寫明 G_acc、blob id 與 sha256；引用它的測試以常數釘住 sha256。
```
新：
```
     - PR 說明寫明 G_acc、blob id 與 sha256（對存進 git 的 LF 位元組計算，不是 CRLF checkout 的雜湊）；引用它的測試以常數釘住同一個 sha256。
```

替換 F6（第 1 點 (e)）
原：
```
     - 以獨立 PR 一次完成 (a)～(c) 與第 5 點的凍結基準檔。不得以 skip、xfail 或只刪部分測試代替。
```
新：
```
     - 以獨立 PR 一次完成 (a)～(c) 與第 5 點的凍結基準檔（merge-base 上還沒有這兩檔時由本 PR 帶入；已由先合併的一鍵檔分支帶入時，本 PR 對這兩檔零差異）。不得以 skip、xfail 或只刪部分測試代替。
```

替換 F7（S-21 第 1 點）
原：
```
    - 退役 PR 的檔案清單恰好是 (a)～(c) 加第 5 點的基準檔與它的 `.gitattributes`；
```
新：
```
    - 退役 PR 的檔案清單恰好是 (a)～(c) 加第 5 點的基準檔與它的 `.gitattributes`；merge-base 上已有這兩檔時，清單恰好是 (a)～(c)，這兩檔零差異；
```

替換 F8（S-21 第 5 點第一項，補三分支核對）
原：
```
    - 基準檔的 sha256 等於 G_acc 那個 blob 的 sha256，也等於 merge-base 那個 blob 的 sha256；
```
新：
```
    - 基準檔的 sha256（對 LF 位元組計算，即 `git cat-file blob` 輸出的位元組）等於 G_acc 那個 blob 的 sha256，也等於 merge-base 那個 blob 的 sha256；不是 CRLF checkout 的 sha256；
    - 兩支一鍵檔分支與本退役 PR 分支上，基準檔與它的 `.gitattributes` 的 blob id 各自相同，基準檔的 blob id 等於 G_acc 上 `apps/stock-desk/pipeline-acceptance.bat` 的 blob id（coordinator 以 `git rev-parse <commit>:<路徑>` 記錄；qa 以 `git diff <甲>:<路徑> <乙>:<路徑>` 輸出為空核對）；
```
（新字面是兩行。若組版腳本只接受單行，請把第二行拆成獨立的「插入於 F8 之後」處理；兩行的縮排都是 4 個空格。）

替換 F9（檔頭補充紀錄行，只換一個子字串）
原：`經風控審查（RC-344～RC-356，附條件接受，替換 B1～B5 已併入）；`
新：`經風控審查（RC-344～RC-356，附條件接受，替換 B1～B5 已併入）；第 1 點 (e)、第 5 點 (a)(b) 與 S-21 第 1、5 點依 git 查證更正字面（基準檔存進 git 的是 LF blob，CRLF 只在測試的記憶體中還原；兩支一鍵檔分支與退役 PR 各自帶入位元組相同的兩檔），不改技術意旨，經風控單項過目；`

### 裁示要點

- 第 1 項：見 F1。
- 第 2 項：要補，見 F3。不補的話，「blob 是 LF」與「`-text`」放在一起，讀者會誤以為 `-text` 是為了保留 CRLF。
- 第 3 項：做法符合規格，見 F4、F6、F7、F8。
  - qa 是唯讀角色，只能下 `git diff`，不能跑 `git rev-parse`。所以 F8 把工作拆開：coordinator 記錄 blob id，qa 以 blob 對 blob 的 `git diff` 為空來核對。
  - 測試註解寫的來源 commit 是 `d6816eb9`，不是 G_acc。條文要求的是 blob 相等，不是 commit 相等，所以這不構成違規。G_acc 到手後，coordinator 照既定待辦核對 blob id 即可。
- 第 4 項：不寫死，見 F2。
- 第 5 項：
  - S-21 第 5 點仍然正確，只做釐清（F8）。
  - 3(a) 末項「blob id、sha256」與 F5 的定義一致，不必改。
  - 6(a)、4(d) 不受 LF／CRLF 影響，不必改。
- 第 6 項：
  - F1、F2、F3、F5 只讓字面與事實相符，不改技術意旨。
  - F4、F6、F7、F8 讓 S-21 的可檢查條件變成有條件成立，並新增三分支核對，屬於 B1～B5 以外的偏差。依風控先前的表態，應重審。
  - 我建議 F1～F9 連同檔頭先前那一句尚待過目的補述，一次送風控單項過目，並請風控實質看 F4、F6、F7、F8。
  - 這幾項都沒有 CEO 看得到的字面。

## 三、驗證

- 已讀：
  - 補充十二組版檔全文（162 行）、qa 複審、devops-sre 交件。
  - 根目錄與 `backend/` 的 `.gitattributes`。
  - 試合併工作樹的 `tests/fixtures/.gitattributes`：只有一行 `pipeline_acceptance_bat_frozen.txt -text`。
  - `test_forecast_status_flow.py` 的第 57～65 行註解與常數、`_precedent_lines()`（斷言沒有 `\r`，再把 `\n` 換成 `\r\n`）、sha256 測試與 `check-attr` 測試。
- 唯一性：F1～F8 的原句我逐字從現行檔複製，在檔內各出現一次（分別在第 128、129、132、133、134、66、149、159 行）。F9 的子字串只出現在第 11 行；第 7 行的寫法是「附條件核可」，不會誤中。
- 沒有查證：
  - blob id `5b0b271e…`、`445bacf6…`，sha256 `07265206…`，三個分支 head，`8b22c114..tip` 的 log 為空：這些都轉述自 coordinator 與 devops-sre。我是唯讀角色，沒跑 git。
  - `test_gap_check_flow.py` 的註解我沒有讀。
  - 退役分支 `chore/pipeline-acceptance-retire` 的實際內容我沒有讀。
- 沒讀 `.env`，也沒碰 `backend/data/`。

## 四、下一步

1. coordinator 把 F1～F9 送風控單項過目，請風控實質看 F4、F6、F7、F8。
2. 過目後，coordinator 以腳本逐字套用替換，再更新檔頭狀態行。
3. G_acc 到手後，coordinator 記錄三個分支與 G_acc 的 blob id；qa 依 F8 以 `git diff` 核對。
4. qa 的 N1（在已合併 product 的狀態下跑全套）照舊是合併前必辦。

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二-待寫入-coordinator組版.md`
- `/home/user/AICompany/work/reviews/2026-11-21-兩支一鍵檔改凍結基準複審-qa.md`
- `/home/user/AICompany/work/reviews/2026-11-21-兩支一鍵檔差異測試改凍結基準交件-devops-sre.md`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/trial2/status/apps/stock-desk/backend/tests/fixtures/.gitattributes`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/trial2/status/apps/stock-desk/backend/tests/test_forecast_status_flow.py`
