# 補充十二 F 系列套用紀錄（風控 RC-405 第 1、2 項）

- 記錄者：coordinator
- 日期：2026-11-21
- 套用腳本：scratchpad 的 `apply_f_series.py`（從 tech-architect 兩份報告與風控 RC-401～RC-403 逐字擷取，沒有手打字面）
- 對象：`work/reviews/2026-11-21-補充十二-待寫入-coordinator組版.md`

## 每一句原文在套用前的出現次數

```
F1：原句在套用前出現 1 次（第 128 行）
F2：原句在套用前出現 1 次（第 129 行）
F3：原句在套用前出現 1 次（第 132 行）
F4：原句在套用前出現 1 次（第 133 行）
F5：原句在套用前出現 1 次（第 134 行）
F6：原句在套用前出現 1 次（第 66 行）
F7：原句在套用前出現 1 次（第 149 行）
F8（三行版，第三行依 RC-402）：原句在套用前出現 1 次（第 159 行）
F10：「插入於」那一行在 F1～F8 套用後出現 1 次（第 134 行）
F9：原子字串在套用前出現 1 次
```

## 套用前後的完整 diff（`diff 套用前 套用後`）

移除 11 行、新增 19 行：F1～F7 各 1 行換 1 行；F8 1 行換 3 行；F10 新增 6 行；檔頭補充紀錄行（F9）1 行換 1 行；另有組版檔自己的兩行說明（「套用」「狀態」，不寫入 ADR）各 1 行換 1 行。

````
6,7c6,7
< - 套用：`work/reviews/2026-11-21-補充十二與退役連帶條件判定RC344至RC356-風控.md` 的替換 B1～B5（腳本逐字替換，每句原文各出現一次）
< - 狀態：**風控 RC-344～RC-356 附條件核可，B1～B5 已套用。tech-architect 已確認 B1～B5 未改動技術意旨，並依其意見在檔頭補充紀錄行補一句（`work/reviews/2026-11-21-補充十二替換確認與r2-probe雜湊查證-tech-architect.md`）。定稿，待寫入 ADR；寫入時點依第 3 點。檔頭補的那一句尚待風控單項過目。**
---
> - 套用：`work/reviews/2026-11-21-補充十二與退役連帶條件判定RC344至RC356-風控.md` 的替換 B1～B5（腳本逐字替換，每句原文各出現一次）；`work/reviews/2026-11-21-補充十二第5點字面更正F1至F9-tech-architect.md` 的 F1～F7、`work/reviews/2026-11-21-補充十二F10與F8最終字面-tech-architect.md` 的 F8（三行版）與 F10、`work/reviews/2026-11-21-補充十二F10與F8確認RC401至RC406-風控.md` 的 RC-401、RC-402 補字與 F9 新字面（腳本逐字套用）
> - 狀態：**定稿，待寫入 ADR。** 風控 RC-344～RC-356（B1～B5）與 RC-395～RC-406（F 系列）附條件核可，替換皆已以腳本套用；tech-architect 已確認 B1～B5 未改技術意旨。檔頭補的「經風控審查（RC-344～RC-356…）」一句已由風控過目（RC-404 結案）。寫入時點依第 3 點 (a)。本組版檔的檔頭說明各行不寫入 ADR。
11c11
< - 補充紀錄：2026-11-21 append 補充十二（D-7 真實資料管線驗收一鍵檔的退役：範圍、S-13b～S-13e 的存續期間、時點與順序、稽核與取回條件、兩支新一鍵檔的凍結差異基準、對既定補充的讀法註記；tech-architect 裁示；第 2 點窄幅寬於 S-13b～S-13e 字面，已標明；其餘為收緊或釐清；不改本文、補充六及其附記、補充八～十一的字面，不改事先宣告 v0.32、規則檔、定義物件、已登記雜湊與 `code_digest` 涵蓋的原始檔，不改 `app/`；CEO 可見部分由風控定稿；經風控審查（RC-344～RC-356，附條件接受，替換 B1～B5 已併入）；coordinator 定案，CEO 可推翻；來源 `work/reviews/2026-11-21-驗收一鍵檔登記後去留與修法裁示-tech-architect.md`、`work/reviews/2026-11-21-三支舊一鍵檔缺工具提示定稿RC336至RC343-風控.md`）
---
> - 補充紀錄：2026-11-21 append 補充十二（D-7 真實資料管線驗收一鍵檔的退役：範圍、S-13b～S-13e 的存續期間、時點與順序、稽核與取回條件、兩支新一鍵檔的凍結差異基準、對既定補充的讀法註記；tech-architect 裁示；第 2 點窄幅寬於 S-13b～S-13e 字面，已標明；其餘為收緊或釐清；不改本文、補充六及其附記、補充八～十一的字面，不改事先宣告 v0.32、規則檔、定義物件、已登記雜湊與 `code_digest` 涵蓋的原始檔，不改 `app/`；CEO 可見部分由風控定稿；經風控審查（RC-344～RC-356，附條件接受，替換 B1～B5 已併入）；第 1 點 (e)、第 5 點 (a)(b) 與 S-21 第 1、5 點依 git 查證更正（基準檔存進 git 的是 LF blob，CRLF 只在測試的記憶體中還原；兩支一鍵檔分支與退役 PR 各自帶入位元組相同的兩檔）：第 5 點 (a) 與換行屬性、sha256 計算對象的說明為字面對齊事實，不改技術意旨；帶入方式與 S-21 第 1 點的檔案清單改為依合併先後有條件成立，並新增三分支 blob id 核對，以及帶入基準檔的分支合併前與 G_acc 的 blob id 核對，屬收緊；經風控審查（RC-395～RC-406，附條件接受，替換 F1～F8 與 F10 已併入）；coordinator 定案，CEO 可推翻；來源 `work/reviews/2026-11-21-驗收一鍵檔登記後去留與修法裁示-tech-architect.md`、`work/reviews/2026-11-21-三支舊一鍵檔缺工具提示定稿RC336至RC343-風控.md`）
66c66
<      - 以獨立 PR 一次完成 (a)～(c) 與第 5 點的凍結基準檔。不得以 skip、xfail 或只刪部分測試代替。
---
>      - 以獨立 PR 一次完成 (a)～(c) 與第 5 點的凍結基準檔（merge-base 上還沒有這兩檔時由本 PR 帶入；已由先合併的一鍵檔分支帶入時，本 PR 對這兩檔零差異）。不得以 skip、xfail 或只刪部分測試代替。
128,129c128,129
<      - 這份基準檔的位元組等於 `git cat-file blob <G_acc>:apps/stock-desk/pipeline-acceptance.bat`，CRLF 也一起保留。
<      - 它同時必須等於本退役 PR 的 merge-base 上同一路徑的 blob。兩者不同就停止，升級 tech-architect。
---
>      - 這份基準檔存進 git 的 blob 等於 `<G_acc>:apps/stock-desk/pipeline-acceptance.bat` 的 blob（blob id 相同）。該 blob 是 LF；CRLF 只由 repo 根目錄 `.gitattributes` 的 `*.bat text eol=crlf` 在 checkout 時產生。基準檔不得寫入 CRLF；比對時，測試先斷言檔內沒有 `\r`，再在記憶體中把 `\n` 換成 `\r\n` 後切行，得到與 CRLF checkout 相同的行序列。
>      - 該 blob id 同時必須等於本退役 PR 的 merge-base 上 `apps/stock-desk/pipeline-acceptance.bat` 的 blob id。兩者不同就停止，升級 tech-architect。具體 blob id 不寫進本 ADR，記在 PR 說明（(b)）。
132,134c132,140
<      - 同一資料夾放一個 `.gitattributes`，把該檔設為 `-text`。不得改 `backend/.gitattributes`（第 1 點 (b) 的測試釘住了它的內容），也不得改 repo 根目錄的 `.gitattributes`（main 維持零產品耦合）。
<      - 全產品線只有一份。兩支分支引用同一個路徑；qa 核對兩支分支內的位元組相同。
<      - PR 說明寫明 G_acc、blob id 與 sha256；引用它的測試以常數釘住 sha256。
---
>      - 同一資料夾放一個 `.gitattributes`，把該檔設為 `-text`。作用是 add 與 checkout 都不做換行轉換（`core.autocrlf=true` 也一樣），使工作樹位元組等於 LF 的 blob；不得改設為 `text` 或 `eol=crlf`。不得改 `backend/.gitattributes`（第 1 點 (b) 的測試釘住了它的內容），也不得改 repo 根目錄的 `.gitattributes`（main 維持零產品耦合）。
>      - 全產品線只有一份，路徑固定為 `backend/tests/fixtures/pipeline_acceptance_bat_frozen.txt`，`.gitattributes` 放在同一資料夾。兩支一鍵檔分支與本退役 PR 各自帶入這兩檔，位元組相同；git 合併時視為相同的新增，不論合併先後，產品線上只有一份。三個分支上這兩檔的 blob id 必須各自相同；任一分支不同就停止，升級 tech-architect，不得以合併時解衝突的方式處理。
>      - PR 說明寫明 G_acc、blob id 與 sha256（對存進 git 的 LF 位元組計算，不是 CRLF checkout 的雜湊）；引用它的測試以常數釘住同一個 sha256。
>      - 合併前的 blob 核對（兩支一鍵檔分支與本退役 PR 一體適用，不論合併先後）：
>        - G_acc 還沒取得之前，帶有基準檔與它的 `.gitattributes` 的分支，一律不得合併到 `product/stock-desk`。
>        - 這類分支合併之前，coordinator 以 `git rev-parse <commit>:<路徑>` 在 `work/` 記錄三個 blob id：該分支 head 上的基準檔、該分支 head 上的 `.gitattributes`，以及 `<G_acc>:apps/stock-desk/pipeline-acceptance.bat`；紀錄同時寫明該分支 head 與 G_acc 的 commit id（40 碼）。分支 head 之後再變動，就重新記錄，並由 qa 重新核對。
>        - qa 以 `git diff <G_acc>:apps/stock-desk/pipeline-acceptance.bat <分支 head>:apps/stock-desk/backend/tests/fixtures/pipeline_acceptance_bat_frozen.txt` 的輸出為空來核對。
>        - 不同就停止，不得合併，升級 tech-architect。
>        - G_acc 依第 4 點 (a) 改指之後一次「harness 通過」的 `git_head` 時（第 3 點 (e) 的重跑），先前的紀錄失效。尚未合併的分支，依新的 G_acc 重做；已合併的，由 coordinator 以 product 的 HEAD 代替分支 head，重做一次記錄與核對。不同就停止，升級 tech-architect。第 5 點 (c) 的「之後不得更新」不因此放寬，要修正須先修訂本 ADR。
149c155
<     - 退役 PR 的檔案清單恰好是 (a)～(c) 加第 5 點的基準檔與它的 `.gitattributes`；
---
>     - 退役 PR 的檔案清單恰好是 (a)～(c) 加第 5 點的基準檔與它的 `.gitattributes`；merge-base 上已有這兩檔時，清單恰好是 (a)～(c)，這兩檔零差異；
159c165,167
<     - 基準檔的 sha256 等於 G_acc 那個 blob 的 sha256，也等於 merge-base 那個 blob 的 sha256；
---
>     - 基準檔的 sha256（對 LF 位元組計算，即 `git cat-file blob` 輸出的位元組）等於 G_acc 那個 blob 的 sha256，也等於 merge-base 那個 blob 的 sha256；不是 CRLF checkout 的 sha256；
>     - 兩支一鍵檔分支與本退役 PR 分支上，基準檔與它的 `.gitattributes` 的 blob id 各自相同（qa 以 `git diff <甲>:<路徑> <乙>:<路徑>` 輸出為空核對）；
>     - 每一支帶有這兩檔的分支，`work/` 裡都有第 5 點 (b) 合併前 blob 核對的紀錄（分支 head 與 G_acc 的 commit id、三個 blob id 與 qa 的 `git diff` 結果）；紀錄中的分支 head 等於該分支合併時的 head，合併前那一筆紀錄所在的 commit 早於該分支的合併 commit；紀錄所用的 G_acc 不是第 4 點 (a) 現行的 G_acc 時，另有依第 5 點 (b) 末款重做的紀錄；
````
