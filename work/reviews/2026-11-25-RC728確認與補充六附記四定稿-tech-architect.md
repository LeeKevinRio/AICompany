# RC-728 確認與補充六附記四定稿

- 審查者：tech-architect
- 日期：2026-11-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：回覆 RC-728，並定稿「補充六附記四」全文

全程唯讀，只用了 Read、Glob、Grep，搜尋都列了明確路徑。沒有讀 `.env*`，沒有碰 `apps/stock-desk/backend/data/`，沒有看 `.claude/worktrees/`，也沒有寫檔。

## 本次結論

1. **RC-728：選項 3 的範圍就是 RC-725 題目裡的四項，沒有 H3、H4、RC-695 後端或 L4。**
   - 我報告裡的「五項」數的是 PR，共五支：α1、α2、PR-3、H1 偵測、H2。其中 α1 和 α2 同屬第一項「首頁警示狀態列」。所以按問題算是四項。
   - 選項 2 那一欄寫「其餘四項」是我數錯了，應該是「其餘三項」，也就是 PR-3、H1 偵測、H2。
   - 題目的四項範圍不必改。
2. **題目描述有兩處和事實不一致，請風控判斷要不要改字（字面待風控定稿）。**
   - 第二項與第三項：選項 2、3 寫「修好」，但登記前能合併的只是「偵測後不照算」與「改正標示」，不是根本修正。題目自己也寫了「要改後端程式才能根本修正」，兩處說法要對齊。
   - 第三項：觸發「已還原」的條件寫得比程式寬，資料缺口也少寫了一種。
   - 其餘描述都和事實一致。
3. **補充六附記四的全文已定稿，附在第二節，可以逐字落檔。**
   - Decision 照錄 RC-720 的適用範圍，以及 RC-721 的記號與 Q-1～Q-8，沒有增刪任何條件。
   - 過渡規則照錄 RC-722。
   - 放置位置有兩處：
     - 檔頭補充紀錄行：插在 ADR-0030 第 20 行之後。
     - 正文：附加在第 976 行之後，也就是現在的檔尾。
   - 這兩處都只新增，不改動任何既有的字。

## 各部門回報（tech-architect）

### 一、RC-728 書面確認

**範圍確認**

| RC-725 題目項 | 對應的 PR | 我報告的出處 |
|---|---|---|
| 一、首頁警示狀態列 | α1（RC-653 快照分段）＋α2（RC-652 主體＋RC-654） | `/home/user/AICompany/work/reviews/2026-11-25-high修正提前代價與前端折衷與ADR時點評估-tech-architect.md:77` |
| 二、公司行動跳空 | H1 偵測 | 同上:77 |
| 三、回測「已還原除權息」過度宣稱 | H2 | 同上:77 |
| 四、總曝險上限在有持倉無法估值時不擋加碼 | PR-3（6-b） | 同上:77 |

- 不在範圍內的項目：H3、H4、M4、RC-695 後端、M1～M6、L1～L8、α3、(A)、(B)、PR-2。這些都是題目裡「另有幾項要先訂規格才能動手」那一類。
- 所以 RC-725 的題目與選項 3 不必因範圍而改。
- 我報告的更正（內部文字，交 coordinator 加註，原文不改）：
  - 第 226、228、231、232 行的「五項」，讀作「五支 PR（四個問題）」；
  - 第 231 行選項 2 欄的「其餘四項」，更正為「其餘三項（PR-3、H1 偵測、H2）」。

**逐項核對 RC-725 問題文字**

1. **第一項（首頁警示狀態列）：一致。**
   - 字面「目前沒有待處理警示」與 `apps/stock-desk/frontend/app/lib/oneLinerWording.ts:75` 相符。
   - RC-650 的觸發是帳本讀取失敗（`work/reviews/2026-11-22-警示失敗升高與狀態列與查詢時間RC650至RC656-風控.md:21`、`:48`）。題目改寫成「這一輪檢查其實沒有完成時」，和 RC-652-1「不分成因」的範圍一致。
   - 補一個事實，不必改字：α2 修好之後，畫面會顯示「檢查未完成」，不代表檢查會因此完成。
2. **第二項（公司行動跳空）：問題描述一致，「修好」不一致。**
   - 「沒有處理」與 quant H1 一致（`work/reviews/2026-11-25-預測正確性風險盤點-quant.md:22-24`）。
   - 「算進回撤、停損提示、關鍵價位與技術指標」與 quant:29 一致。quant 那裡把影響標為推論。
   - **不一致處：** 登記前能合併的是「H1 偵測」。偵測到跳空時，該視窗拒算或明示排除，不照算（quant:33-34；我的報告:77「H1 偵測」）。根本修正要等 data-engineer 接上公司行動來源（quant:33），而這個來源還沒查證。
   - 因此選項 2、3 的「修好」用在第二項，會讀成「數字變正確」，實際上只是「不再照算」。另外偵測只適用台股，而且可能誤判成多拒算（我的報告第 2 點 H1 段）。
3. **第三項（「已還原除權息」）：大致一致，有兩處要精確。**
   - 「含配股的事件也沒有算進去」一致：`apps/stock-desk/backend/app/dividends/models.py:171-176`，含配股的事件整筆拒用；`apps/stock-desk/backend/app/api/backtest.py:121-123` 卻寫「報酬已含現金股利與配股」。
   - **不精確處 (a)：** 觸發「已還原」的條件，不是「只要有一筆除權息資料」，而是回測區間內至少有一筆事件被實際套用（`apps/stock-desk/backend/app/dividends/adjust.py:279` `applied=True`；quant:42）。區間外的事件，或被拒用的事件，都不會觸發。
   - **不精確處 (b)：** 資料缺口不只「開始同步那天之前」，兩次同步之間錯過的日期也不會補（`apps/stock-desk/backend/app/dividends/sync.py:19-23`）。
   - **不一致處：** H2 的修正是改成 `partially_adjusted` 並寫出覆蓋起訖（quant:53）。也就是改正標示，不是讓回測變成完整還原。來源本身沒有歷史可以回補（`sync.py:12-17`），所以這一項不可能「修」到完整還原。選項 2、3 的「修好」用在第三項，會讀成「回測會完整還原」。
4. **第四項（總曝險上限不擋加碼）：一致。**
   - 與 RC-673 第 2 點的逐字事實一致（`work/reviews/2026-11-22-PR2PR3脫離閘門與草案與N209N207通知RC670至RC681-風控.md:116`）。
   - 也與 6-b 任務單一致：只有 violated 會擋加碼（`work/dispatch/2026-10-07-任務單-6-b-總曝險上限帳本不完整但已超標時不擋加碼.md:5`）；路線是 A/N ≥ 上限時判 violated（同檔:13、:19）。
   - 「合併前先通知、回覆收到才合併」與 RC-673:110 一致。
   - 補一個事實，不必改字：修正之後，守門順序仍是「無淨值 → 淨值過期 → …」（6-b 任務單:43）。所以自報淨值沒填或過期時，照樣不會擋下。

**建議（交風控決定，字面待風控定稿）**
- 範圍不變，不需要重送範圍。
- 第二、三項的「修好」，可以改成能涵蓋「偵測後不照算」「改正標示」的說法，並和問題文字裡的「根本修正」對齊。
- 第三項的觸發條件與資料缺口，看要不要照上面 (a)(b) 寫精確。
- 依 RC-724，改字之後題目要重送風控。

### 二、補充六附記四全文（交 tech-writer 逐字落檔）

**放置位置**
- (1) 檔頭補充紀錄行：插在 `docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md` 第 20 行之後、第 21 行（`- 日期：2026-10-26`）之前。這是第 4～20 行各補充一路沿用的位置。
- (2) 正文：附加在第 976 行（補充七附記三之一的 S-15d）之後，中間空一行。
- 兩處都只新增行，不動任何既有的字。
- 補充八～十四之後再 append 時，排在本附記之後。它們彼此 8～14 的順序不受影響。

**(1) 檔頭補充紀錄行（全文，一行）**

```
- 補充紀錄：2026-11-25 append 補充六附記四（第 6 點 (d) 允許差異的讀法：前端原始碼與只由 main 帶進來的非文件檔，在 RC-721 Q-1～Q-8 的條件下列為允許差異；窄幅寬於字面；經風控審查（RC-720～RC-723）；tech-architect 起草，風控判定採 r2'；不改使用者面字面、規則檔、定義物件與已登記雜湊，不改 `app/`；CEO 可推翻；來源 `work/reviews/2026-11-25-high修正提前代價與前端折衷與ADR時點評估-tech-architect.md`、`work/reviews/2026-11-25-補充六附記四讀法與高優先修正排程CEO題RC720至RC729-風控.md`）。
```

**(2) 正文（全文）**

````
## 補充六附記四：第 6 點 (d) 對前端原始碼與 main 同步檔的讀法（2026-11-25）

- 決策者：tech-architect 起草；risk-compliance-officer 判定（RC-720～RC-723）。來源：`work/reviews/2026-11-25-high修正提前代價與前端折衷與ADR時點評估-tech-architect.md`（新發現 A）、`work/reviews/2026-11-25-補充六附記四讀法與高優先修正排程CEO題RC720至RC729-風控.md`（RC-720～RC-723）。
- 性質：窄幅寬於字面。經風控審查（RC-720～RC-723）。CEO 可推翻。只釐清補充六第 6 點 (d) 的允許差異範圍；不改本文、補充六與各附記的原文，不改使用者面字面、規則檔、定義物件與已登記雜湊，不改 `app/`。與補充六第 6 點 (d) 衝突時，以本附記為準。

### Context

1. 補充六第 6 點 (d) 第四款只允許「`app/` 以外的登記一鍵檔、文件與測試」，並規定「其餘任何差異都使通過失效，須在新 head 重跑」。前端原始碼（`apps/stock-desk/frontend/`），以及 product `merge origin/main` 時帶進來的非文件檔（例如 `scripts/validate_agents.py`），依字面都不在允許清單內。
2. 現況：前端合併 `6cd7d25`（T-3，2026-11-22）與 `fde59c2`（2026-11-25）已在 product；product 尚未 `merge origin/main`（含 `e1349aa`）。CEO 已於 2026-11-16 被請求執行真實資料管線驗收一次，尚未回貼，所以 `git_head` 未知。
3. 執行期事實（RC-720）：一鍵檔啟動 Python 時，先 `cd /d "%BACKEND_DIR%"`，再 `uv run --no-sync python -I`（`pipeline-acceptance.bat:23`、`:29`）；包裝只把 backend 資料夾插入 `sys.path`（`pipeline_acceptance_real.py:64-66`）。所以 `.ts`、`.tsx`、根目錄的 `scripts/*.py` 都進不了這次執行的 import 圖。
4. 選項：
   - r1（照字面）：上述差異使通過失效。不採：6(d) 要保證的是「通過 harness 的程式」就是「登記的程式」，照字面讓這些差異使通過失效，會增加 CEO 的負擔，卻換不到任何保證。
   - r2（tech-architect 原提案：backend 零差異、不在 backend 底下就放行、以 `git diff --name-only` 證明不可達）。不照原樣採：「backend 零差異」做不到，因為 CG-2 合併本來就會改 backend；「不在 backend 底下就放行」範圍太寬，會放進可能改變換行判定或 uv／Python 行為的檔，以及 `apps/stock-desk/` 底下的 `.bat`；`--name-only` 只能列出改了哪些檔，不能證明這些檔不可達。
   - **r2'（風控判定，採用）**：見 Decision。

### Decision

採 r2'。

**適用範圍（RC-720）**：溯及 `git_head` 之後的所有差異，含 `6cd7d25`、`fde59c2`，以及之後的 `merge origin/main`（含 `e1349aa`）。

**核對條件（RC-721，照錄）**

記號：
- G：回貼的 `git_head`；
- M：CG-2 PR 合併時的 head（也就是 6(d) 的終點）；
- D：`git diff --name-status --no-renames G M` 的全部列。

1. **Q-1** `git merge-base --is-ancestor G M` 的結束碼是 0。
2. **Q-2** D 的每一列都要恰好歸入下列一類。任何一列歸不進去，通過就失效：
   - 類 0：6(d) 原本列的四款，以及補充七附記二第 5 點的三個 `.gitattributes`。照原本的核對方式做，含 AST 比對，也含第四款末句五檔零差異。
   - 類 A：路徑以 `apps/stock-desk/frontend/` 開頭。
   - 類 B：路徑不以 `apps/` 開頭，也不以 `work/` 開頭；而且 `git log --format=%H G..M -- <path>` 列出的每個 commit，都滿足 `git merge-base --is-ancestor <commit> origin/main`。只要有 product 上的 merge commit 出現在清單裡（例如處理過衝突），這一列就不屬於類 B。
3. **Q-3** 檔名排除。符合下列任一的列，不得歸入類 A 或類 B：
   - 檔名（路徑最後一段）是 `.gitattributes`、`pyproject.toml`、`uv.toml`、`uv.lock`、`.python-version`、`sitecustomize.py`、`usercustomize.py` 之一；
   - 檔名以 `.pth` 結尾，或以 `.env` 開頭；
   - 類 A 另外不得以 `.py` 結尾。
4. **Q-4** 路徑以 `apps/stock-desk/` 開頭、但不在 `backend/` 或 `frontend/` 底下的列，只能屬於類 0（登記一鍵檔、文件）。
   - `.bat` 只限兩支 cg2 `.bat`；
   - `pipeline-acceptance.bat`、`dev-up.bat` 有任何差異，通過就失效。`dev-up.bat` 不在這次放寬的範圍內，要放寬請另外送我。
5. **Q-5** 執行期不可達。qa 在 G 上確認：
   - `pipeline-acceptance.bat` 先 `cd /d "%BACKEND_DIR%"`，再用 `uv run --no-sync python -I` 啟動；
   - 包裝唯一的 `sys.path` 動作，是插入 `parents[1]`，也就是 backend 資料夾；
   - 包裝、`.bat` 與 harness 三檔中，Grep `frontend` 都是 0 筆，而且沒有 `parents[2]` 以上的寫法。
   - 這幾檔依 6(d) 必須零差異，所以在 G 上確認，就等於在 M 上確認。
   - suggested：加一支測試，在合成資料上跑完包裝後，斷言 `sys.modules` 裡每個 `__file__` 都落在 backend、`sys.prefix` 或 `sys.base_prefix` 之下。
6. **Q-6** 證據：
   - CG-2 PR 說明（S-13b 第 6 點）要附：D 全文、每一列的歸類與依據（類 B 附每個 commit 的 `is-ancestor` 結果）、Q-3 掃描結果、Q-5 的確認句。
   - 這份放寬的證據要由**非實作者**產出（devops-sre 或 coordinator），由 qa 判讀。這是 required。
7. **Q-7** 任何一條不成立，通過就失效，CEO 要在新 head 重跑。
   - 不得以「這個差異無關」口頭豁免。要豁免，另立補充送我。
   - 重跑通知的字面先送我。
8. **Q-8** 這個讀法不改變下列事項：R-1、RC-507 (1)～(6)、#156 期間禁止合併、6(a)～(c)，以及 `code_digest`、`lockfile_sha256`、harness 雜湊、script 雜湊的核對。

（Q-4、Q-7 中的「我」指 risk-compliance-officer，照錄 RC-721 原文。）

### 過渡規則（RC-722，照錄）

- 落檔之前照 r1 處理。暫緩前端合併與 `merge origin/main` 的決定，等落檔之後才解除。
- coordinator 的「CEO 回貼時先核對 `git_head` 是否含 `6cd7d25`」，改成「跑 RC-721 全套」。

### Consequences

- 好處：前端原始碼與只由 main 帶進來的非文件檔，在 Q-1～Q-8 成立時，不再單獨使「harness 通過」失效；CEO 不會因這類差異被要求重跑。
- 壞處與殘留：
  - 每次判讀回貼都要多跑一套 Q-1～Q-8，而且證據要由非實作者產出、qa 判讀。
  - `dev-up.bat`、`pipeline-acceptance.bat`、任何 `.gitattributes`、uv 與 Python 設定檔，以及 product 上處理過衝突的 merge commit，照樣會使通過失效。
  - Q-3 的排除清單依知識判斷，偏保守（uv 會不會往上層資料夾找設定檔，風控未查證，見 RC-720 驗證段）。
- CEO 告知與禁說依 RC-723，不在本附記重述。
- 回滾：開新附記取代本附記，原文保留。
````

**落檔核對（qa 可逐條檢查）**
1. 第 1～976 行與落檔前逐位元組相同。新增的只有第 20 行之後的一行，以及第 976 行之後的正文。
2. Q-1～Q-8 與 RC-721（風控檔第 45～74 行）逐字相同。適用範圍與 RC-720 第 41 行逐字相同。過渡規則與 RC-722 第 79～80 行逐字相同。
3. 檔頭紀錄行與「性質」行都含三句標示：「窄幅寬於字面」「經風控審查（RC-720～RC-723）」「CEO 可推翻」。

## 驗證

**讀過**
- 風控 RC-720～RC-729 全文（260 行）。
- 我的 11-25 報告第 70～81 行，以及 Grep 命中的第 226、228、231、232 行。
- ADR-0030 第 18～23、974～977 行，以及全檔 `## ` 標題與補充紀錄行的 Grep。
- `dividends/adjust.py:265-284`、`dividends/models.py:160-181`、`dividends/sync.py:1-25`。
- 6-b 任務單的 Grep 命中行。
- RC-673 第 108～120 行；RC-650 檔的 Grep 命中行。
- 追蹤清單第 588、643 行，用來確認補充八～十四尚未寫入。

**Grep 結果**
- `oneLinerWording.ts:75` 的狀態 B 字面。
- `backtest.py:121-123` 的「已還原」句。

**沒有查證**
- 所有 git 狀態：`fde59c2` 的內容、`e1349aa` 的檔案清單、CEO 的 `git_head`。
- ADR-0030 在 product HEAD 上的實際行數。我依主工作樹的檔案判斷，落檔當下由 tech-writer 再確認第 20、976 行的內容與上面所述相同；不同就停下回報。
- 補充八～十四會不會在其他分支先改到 ADR-0030 的檔尾。

## 下一步

- **risk-compliance-officer**：
  - 收 RC-728 的確認：範圍是四項，不變；
  - 判斷第一節第 2、3 項的「修好」與觸發條件要不要改字。改字的話，依 RC-724 重新定稿；不改字，就照原稿。
- **coordinator**：
  - 風控回覆之後，再依 RC-724 的前置條件送出題目；
  - 在我 11-25 報告旁加註「五項」「其餘四項」的更正（原文不改）；
  - 附記四落檔之前，前端合併與 main 同步照舊暫緩。
- **tech-writer**：依第二節的位置逐字落檔；落檔後交 qa 依「落檔核對」三點核對。
- **qa-reviewer**：核對落檔；CG-2 PR 時照 Q-1～Q-8 逐條核對。
- **CEO**：本件沒有需要決定或操作的事。題目依 RC-725、RC-724 另行送出。

**相關路徑**
- /home/user/AICompany/work/reviews/2026-11-25-補充六附記四讀法與高優先修正排程CEO題RC720至RC729-風控.md
- /home/user/AICompany/work/reviews/2026-11-25-high修正提前代價與前端折衷與ADR時點評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-25-預測正確性風險盤點-quant.md
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/work/reviews/2026-11-22-PR2PR3脫離閘門與草案與N209N207通知RC670至RC681-風控.md
- /home/user/AICompany/work/reviews/2026-11-22-警示失敗升高與狀態列與查詢時間RC650至RC656-風控.md
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-6-b-總曝險上限帳本不完整但已超標時不擋加碼.md
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/adjust.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/sync.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/backtest.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/oneLinerWording.ts
