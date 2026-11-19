# CG-2 登記 PR：M-9 核對用證據（M-2、M-3、M-6）

- 產出者：coordinator
- 日期：2026-11-17
- PR head：`9d5bbf480948d3a94fcef0966293bbfca7702089`（`feat/nm5-cg2-registration`）
- 說明：以下是指令與原始輸出，供風控核對 M-2、M-3、M-6。M-6 以 PR head 的程式在 Python 3.12 執行 `definitions.registration_phrase_scan`，沒有連任何資料庫。

```
# M-9 evidence at PR head 9d5bbf480948d3a94fcef0966293bbfca7702089
## M-2 prereg
$ git rev-parse 9d5bbf480948d3a94fcef0966293bbfca7702089:"work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md"
d1e4d06a4e1c1a06158ad33a481050fe44bf8ae1
$ git cat-file blob 9d5bbf480948d3a94fcef0966293bbfca7702089:"work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md" | sha256sum
7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e  -
$ git log --format='%H %ad %s' --date=short 9d5bbf480948d3a94fcef0966293bbfca7702089 -- "work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md" | head -3
ed9275321b0be82bce5c8f3f97a2e31bb3abeb34 2026-11-15 docs: 事先宣告 v0.32 套用風控 RC-153～RC-157（補回放寬面揭露與 R-113 第 4 點、狀態行更正）
371329d4c3b4d802ac34d24686e22ca08408d52e 2026-11-15 docs: 事先宣告升為 v0.32（套用凍結包 V32-01～V32-16；待風控單項確認 RC-126 放寬面揭露位置）
949d958db522a5f6c671e234e7472f60a5ebeaaf 2026-10-25 docs: 事先宣告 v0.31 與 ADR-0027 N-17 因子修訂觸發批同批落檔
## M-3 C-8 record
$ git rev-parse 9d5bbf480948d3a94fcef0966293bbfca7702089:"work/dispatch/2026-11-15-C8決策紀錄-F2B.md"
e664f147f2c5339e321ae333b7ce3c7d35ebcda7
$ git cat-file blob 9d5bbf480948d3a94fcef0966293bbfca7702089:"work/dispatch/2026-11-15-C8決策紀錄-F2B.md" | sha256sum
c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f  -
$ git log --format='%H %ad %s' --date=short 9d5bbf480948d3a94fcef0966293bbfca7702089 -- "work/dispatch/2026-11-15-C8決策紀錄-F2B.md" | head -3
7883f12e846d23b86670092dad01e543763bdc4b 2026-11-15 docs: 建立 C-8 決策紀錄檔（F2-B；待風控單項確認）
## eol
$ git -C <worktree at 9d5bbf480948d3a94fcef0966293bbfca7702089> ls-files --eol -- <two docs>
i/lf    w/lf    attr/text eol=lf      	"work/dispatch/2026-11-15-C8\346\261\272\347\255\226\347\264\200\351\214\204-F2B.md"
i/lf    w/lf    attr/text eol=lf      	"work/research/2026-10-15-3\346\227\2455\346\227\245\346\226\271\345\220\221\345\210\244\346\226\267-\344\272\213\345\205\210\345\256\243\345\221\212\350\215\211\346\241\210.md"
## M-6 banned phrase scan (code at 9d5bbf480948d3a94fcef0966293bbfca7702089, Python 3.12, definitions.registration_phrase_scan)
outlook-market-v1.0-h3: hits 0 rules_strings 159 definition_strings 12 phrases 10
    banned phrase scan (NFKC, whitespace and zero-width removed): rules 159 strings, definition 12 strings, 10 phrases, hits 0
outlook-market-v1.0-h5: hits 0 rules_strings 159 definition_strings 12 phrases 10
    banned phrase scan (NFKC, whitespace and zero-width removed): rules 159 strings, definition 12 strings, 10 phrases, hits 0
```
