# 前端減字三項 risk-gate 與 CEO 題改字（RC-740～RC-746）

- 審查者：risk-compliance-officer
- 日期：2026-11-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**一、前端減字三項 risk-gate：APPROVE_WITH_NOTES（RC-740～RC-742）。**
- RC-718 的五項 risk-gate 核對項全部符合。
- 實作者的偏離可以接受。測試只對去註解後的程式碼斷言「不含 `app/advice/limits.py`」，這個做法符合我要防的事：使用者在畫面上看到程式路徑。
- 這次核准只對 head `3ea244bd991c30ba085546219603d5210cb19ef5` 有效。合併前還要先滿足 RC-742 的條件，其中第 1 項是附記四要 commit 進 product，工作樹裡寫好還不算落檔。

**二、RC-725 CEO 題：要改字（RC-743）。** 下面附逐字定稿（RC-744），取代 RC-725 的全部字面。
- TA 指出的兩點都成立。
- 選項寫「修好」，CEO 會讀成第二項的數字會變對、第三項會完整還原，等於高估了選項 2、3 能換到的東西。這屬於隱藏不確定性，不能放行。
- 送出前還差一個條件：TA 要書面確認新加的「處理程度」那一段事實無誤（RC-746）。其餘前置條件，依我能看到的證據都已成立。

## 各部門回報（risk-compliance-officer）

編號：我用 Grep 查了 `work/`、`docs/`，RC-74x 都沒有人用過，這次用 RC-740～RC-746。另一位同仁如果同時也在用 74x，請 coordinator 轉存時再比對一次。

### 審查結論
APPROVE_WITH_NOTES（第一件）。第二件是改字定稿，不適用這個欄位。

### 逐條意見

**[RC-740] RC-718 risk-gate 核對項，逐項結果**

1. **head 的三句和定稿逐字相同：符合。**
   - `SettingsForm.tsx:465`：`除 ATR 停損倍數外，每一項數字都是分數（例如 0.15 = 15%）。`
   - `BacktestReportView.tsx:340`：`Buy &amp; Hold 為同期間、未計交易成本的被動持有基準。`
   - `BacktestReportView.tsx:646`：第三句寫在同一個 JSX 行。
   - 行號和 RC-712 寫的不同，是因為上方多了註解，位置本身沒有搬動。
   - e2e 實際抓到的 innerText，在 375 和 1280 兩種寬度下都和定稿相同。

2. **diff 裡沒有其他使用者看得到的字面變動：符合。**
   - 我沒有 git，這項是用 qa 回報的 numstat 加上逐段讀碼核對的。
   - 各檔增刪行數，和我讀到的改動段落完全對得上：
     - SettingsForm：-1／+3
     - BacktestReportView：-3／+6
     - PendingAlertsPanel：-2／+5
     - boundary test：-3／+1
     - 新測試：+97
     - 合計 +112／-9，和回報的 stat 一致。
   - 新增的行只有註解、import 和那三句。

3. **`frontend/app`（排除 `__tests__`）已經沒有 `app/advice/limits.py` 的畫面字面，也沒有「見後端」「verified_on 為」：符合。**
   - 剩下的 `limits.py` 都在註解裡：SettingsForm 第 28、32、47、100、113 行，`types.ts`、`adviceWording.ts:45`、`cap1SunsetWording.ts:22`，以及幾處 `book_limits.py`。
   - 「見後端」只出現在測試檔裡。「verified_on 為」是 0 筆。

4. **`PendingAlertsPanel.tsx` 沒有過濾 entries 的寫法：符合。**
   - 我讀了全檔（62 行），沒有 filter、slice 或 sort。
   - 另外核對了 `engine.py:233-238`、`:281-287`、`:349-352` 的 11 個 observed 鍵。只有 `close` 在 `SIGNAL_FIELD_OPTIONS` 裡有標籤；`UNEVALUABLE_ALERT_FIELDS` 只有 beta 和 position 三個欄位。所以正式畫面上只有 `close` 會換成中文，其餘鍵照原名顯示，`bar_as_of` 和 `signals_as_of` 都保留。

5. **後端 `UNVERIFIED_RATES_NOTE` 原封不動：符合。**
   - worktree 和主工作樹的 `api/backtest.py:89-92` 逐字相同。
   - backend 零差異這一點，依賴 qa 跑的 `--stat`。

**[RC-741] 偏離判定：可以接受**

- RC-717 第 1 項要防的是畫面上露出程式路徑和不實的對應說法。RC-718 的 risk-gate 項原本就寫「畫面字面」。第 1 項寫成「原始碼不含」，是我寫得太寬，以 RC-718 的寫法為準。
- 那 5 行是早就存在的開發者註解，不會渲染到畫面，也不在這批的範圍內。不要求清掉。
- 這樣做仍然防得住真正的回退：句子在 JSX 文字裡，如果有人把路徑改回畫面上，去註解後的程式碼就會含這個路徑，測試會變紅。
- 「第一句剛好出現 1 次」仍是對原始碼全文斷言。
- suggested：在測試裡用一行註解寫明去註解 regex 的限制（同 qa 的 low），不擋件。

**[RC-742] 合併條件（required，加在 RC-718 的 1～5 項之上）**

1. **附記四要 commit 進 product，才算 RC-722 的「落檔」。**
   - 追蹤清單:817 寫的是 coordinator 用 `git diff --numstat` 核對了 72/0，看起來還是沒 commit 的改動。主工作樹的 ADR-0030 第 21、979 行確實已經有附記四。
   - 你這次說「tech-writer 正在落檔」，和追蹤清單:817 寫的「已落檔」不一致。請以 commit SHA 為準，寫進追蹤清單。
   - qa 依 TA 的三點做落檔核對，是 suggested，排在合併前做；不是這次合併的前置。
2. 合併當下由 coordinator 書面確認 #156 期間還沒開始。
3. 分支的 base 是 `fa9dd420`，product 現在已經前進到 `1563b91f`。合併時如果四個字面檔有衝突，依 RC-718 第 4 點不在這次核准範圍內。
4. 在 M 上跑 frontend 全套 CI 對等。typecheck、vitest、build 目前只有實作者跑過，qa 沒有重跑。
5. RC-633 的 C-0 連動比照 `fde59c2` 處理，由 coordinator 確認。
6. head 一旦改變（rebase、amend 或任何新 commit），這次核准就失效，要重送我。
- 備註：合併後，這個 commit 在 RC-721 歸類 A。diff 裡沒有 `.py`，Q-3 不受影響。

**第一件的 notes（不擋件）**
- 375 寬時說明句斷在「0.15 =」後面。另案 A 會改這個例子，到時一併看。
- e2e 情形 (b) 的 fixture 用 `"rsi14.last"` 當鍵，和正式資料的形狀（`field`／`value`／`op`／`compared_to`）不同。畫面上的「14 日 RSI 最新值」是 fixture 造成的，正式事件不會出現。`signals_as_of` 可見這個結論不受影響，而且單元測試第 6 項用的是正式形狀。
- RC-716 觀察 4（「最新收盤價」可能被讀成現價）仍然存在，交給另案 C 處理。

**[RC-743] RC-725 要改字，理由**
1. **「修好」高估效果。**
   - 第二項在登記前能做的只是偵測到跳空就不照算，而且只適用台股，也可能誤判。要根本解決得先接上另一個資料來源，這個來源還沒查證。
   - 第三項只能改正標示。來源沒有歷史資料，缺的補不回來（我讀過 `sync.py:12-24`）。
   - 讓 CEO 以為選項 2、3 會讓數字變對，是隱藏不確定性。
2. **第三項的觸發條件寫得比程式寬。**
   - 實際條件是：回測期間內 `(first_bar, last_bar]` 有一筆可用的事件被套用（`adjust.py:214`、`:248`、`:279`）。
   - 資料缺口也少寫一種：兩次同步之間錯過的事件也不會補上（`sync.py:19-23`）。
   - 含配股的事件整筆拒用，這點寫的和程式一致（`models.py:171-176`）。
3. 範圍不變，仍是四項，和 TA 的確認一致。

**[RC-744] 逐字定稿（取代 RC-725 全部字面）**

格式照 RC-725：一題四選項，依下列固定順序排列；不加粗，不標「建議」或「推薦」。

項目：header
````
高優先問題排程
````

項目：問題
````
團隊盤點出四項會讓畫面上的提示或數字不可靠的問題，都要改後端程式才能處理：一、首頁的警示狀態列，在這一輪檢查其實沒有完成時，仍可能顯示「目前沒有待處理警示」；二、股票分割、減資這類事件沒有處理，價格的跳空會被當成真實漲跌，算進回撤、停損提示、關鍵價位與技術指標；三、回測期間內只要有一筆除權息事件被拿來調整價格，就標示「已還原除權息」，但除權息資料只從開始同步那天起才有，兩次同步之間錯過的事件也不會補上，含配股的事件也沒有算進去；四、已估值部分的總曝險已經達到或超過上限、又有持倉無法估值時，總曝險上限目前不會擋下加碼。改後端程式能做到的處理分別是：第一項改成照實顯示這一輪檢查沒有完成；第二項改成偵測到這類跳空時不照算，這個偵測只適用台股，也可能誤判而多不算一些沒有問題的資料，要根本解決得先接上另一個資料來源，這個來源還沒查證；第三項改成照實寫出除權息資料涵蓋的期間，缺的資料補不回來，涵蓋不到的期間仍然沒有還原；第四項改成在上述情形擋下加碼。下面各選項說的「處理」，都只做到這個程度。另有幾項要先訂規格才能動手，不在這次的選擇裡，團隊另外處理。這四項目前排在正式登記之後才處理。要提前到登記之前，只能趁登記用的程式還沒合併時做；這會讓正式登記延後，預測紀錄也就晚一點開始累積（預測紀錄要在正式登記之後才開始記，是日後衡量判斷準不準的依據）。不論您選哪一項，團隊目前的安排都是先做只改畫面的調整，減少畫面上的誤導；這些調整只涵蓋部分畫面，推播通知與排程台不在其中。請問這四項要怎麼排？
````

項目：選項 1
````
標題：維持原本順序
說明：四項都等正式登記和後續收尾完成之後才處理，這段期間有多長，現在估不出來；在那之前，問題照舊留在推播通知、回測與排程台，畫面上只有上面說的部分調整。正式登記的時程不因這個選擇改變，團隊也不必重做已完成的登記前核對。這個選擇本身不需要您另外做什麼。
````

項目：選項 2
````
標題：登記前先處理第一項
說明：只把第一項（首頁警示狀態列）提前到登記之前處理，其餘三項同「維持原本順序」。正式登記與預測紀錄開始累積會延後，團隊推估一到數週，這個數字沒有可靠的估算基礎；團隊也要把已完成的登記前核對重做一輪。選這項的話，請先不要執行真實資料管線驗收（雙擊 pipeline-acceptance.bat 的那一次），等團隊通知再執行；如果您已經執行過，處理完之後要再執行一次。
````

項目：選項 3
````
標題：登記前處理完四項
說明：四項都提前到登記之前處理。正式登記與預測紀錄開始累積延後得比「登記前先處理第一項」更多，團隊推估數週，這個數字沒有可靠的估算基礎；四項之中只要有一項沒趕上同一輪，登記前核對就要再重做一輪，時間再拉長。驗收的安排和「登記前先處理第一項」相同。第四項會改變系統何時擋下加碼，合併前團隊會先通知您，等您回覆收到才合併；這則通知不論什麼時候處理都要送，選這項只是提前。
````

項目：選項 4
````
標題：先不決定
說明：目前照「維持原本順序」進行，這個選擇本身不需要您另外做什麼。登記用的程式一合併（最早在驗收結果核對完成之後），這四項就只能排在登記之後處理，另外兩個提前的選項也就不能再選。
````

改字重點：
- 「修／修好／修完」全部改成「處理」，並在題目裡寫明處理能做到的程度。
- 前端折衷改叫「調整」，和後端的「處理」分開，避免同一個詞指兩件事。
- header 改成「高優先問題排程」，避開「修正」。
- 選項 3 的「加碼建議的行為」改成「系統何時擋下加碼」，和題目第四項的說法一致，也不再用「建議」這個詞。

**[RC-745] 自我檢查**
- **禁用詞，0 筆。** 比對了以下清單：
  - `shared/forbidden-terms.json` 的 guarantee 和 price_target；
  - `FRONTEND_FORBIDDEN_TERMS`（`adviceWording.ts:385-494`）裡的祈使、急迫、確定性、機率、即時性、行銷語氣等各類；
  - RC-726 的共通禁說：很快、盡快、選 X 比較好、RC 代號、附記四；
  - RC-723 的「同一版程式」「完全相同的程式」。
  - 全文沒有「建議」「推薦」「正確」「最新」「成功」「即時」。
- **日期：0 個。** 「一到數週」「數週」只是推估的長短，沒有寫成承諾。
- **沒有叫 CEO 看檔。** 沒有要 CEO 看 log、DB、檔案、設定或畫面。`pipeline-acceptance.bat` 只是用來指認是哪一次操作，沿用 RC-725 原文。
- **header 7 字**，在 12 字以內。
- **標題詞數**：
  - 維持／原本／順序：3 個；
  - 登記前／先／處理／第一項：4 個；
  - 登記前／處理完／四項：3 個；
  - 先／不／決定：3 個。
- **四選項對稱**：每個選項都寫到「什麼時候處理」「登記時程」「團隊要不要重做」「CEO 要做什麼」。選項 4 也沿用選項 1 的內容。
- **含「先不決定」。** 格式照 RC-725：不加粗，不標建議或推薦，順序固定。
- **代價**：題目比原稿長，大約多了一段。這是為了不高估效果，我判斷值得。

**[RC-746] RC-724 送出前置條件**
1. **RC-728 已確認：成立。** TA 檔第 15-18、33-48 行。
2. **M 未合併：依現有證據成立，但我沒有用 git 查證。**
   - 追蹤清單沒有 CG-2 合併的紀錄。:804、:817 顯示 CEO 還沒貼回驗收結果；依 RC-727 的順序，M 一定在貼回之後。
   - 主工作樹的 `backend/scripts`、`tests`、`app` 下 Glob 不到 cg2 相關檔，這只能當作輔助。
   - 送出當下由 coordinator 用 git 確認。
3. **#156 未開始：依追蹤清單成立。** :804 寫明 CEO 還沒貼回、登記預檢還沒通知，之後沒有相反的紀錄。
4. **結構性選項未採用：成立。** 在 `work/` Grep 只命中 3 個檔，都是提案或「送風控」的紀錄，沒有採用的紀錄。
5. **新增 required：TA 要書面確認 RC-744 題目中「改後端程式能做到的處理分別是：」那一段的事實。**
   - 尤其是第一項的顯示，以及第二項的「只適用台股」「可能誤判而多不算」「來源還沒查證」。
   - TA 只核對事實，不改字。有不符就退回我改。
   - 第三項的事實我已經自己讀碼核對過。
- 其餘 RC-724 規則照舊：單獨一則，只問這一題，不和 RC-471、RC-489、RC-618 或驗收追問放在一起，不催答。

### 否決理由
無（沒有否決）。

## 驗證

**讀過的檔案與行號**
- `/home/user/AICompany/work/reviews/` 底下：
  - `2026-11-25-前端減字三項逐字審RC712至RC718-風控.md` 1-169（全文）
  - `2026-11-25-前端減字三項實作交件-frontend-engineer.md` 1-80
  - `2026-11-25-前端減字三項審查-qa-reviewer.md` 1-189
  - `2026-11-25-前端減字三項實機證據-qa-automation.md` 1-125
  - `2026-11-25-前端減字三項實機判讀-qa-e2e.md` 1-88
  - `2026-11-25-RC728確認與補充六附記四定稿-tech-architect.md` 1-218
  - `2026-11-25-補充六附記四讀法與高優先修正排程CEO題RC720至RC729-風控.md` 1-260
  - `2026-11-25-預測正確性風險盤點-quant.md` 15-59
- worktree `/home/user/AICompany/.claude/worktrees/agent-a3b8c88b329ce0ede/apps/stock-desk/` 底下：
  - `frontend/app/backtest/__tests__/frontendTrimThreeLiterals.test.ts` 1-98
  - `frontend/app/settings/SettingsForm.tsx` 20-159、450-479
  - `frontend/app/components/PendingAlertsPanel.tsx` 1-62
  - `frontend/app/backtest/BacktestReportView.tsx` 325-349、625-654
  - `frontend/app/backtest/__tests__/backtestFrontendBoundary.test.ts` 95-169
  - `frontend/app/lib/format.ts` 479-500
  - `backend/app/api/backtest.py` 80-99
- 主工作樹：
  - `apps/stock-desk/frontend/app/backtest/__tests__/backtestFrontendBoundary.test.ts` 95-169
  - `apps/stock-desk/backend/app/api/backtest.py` 80-99、110-134
  - `apps/stock-desk/backend/app/dividends/adjust.py` 180-289
  - `apps/stock-desk/backend/app/dividends/sync.py` 1-30
  - `apps/stock-desk/backend/app/dividends/models.py` 160-181
  - `apps/stock-desk/backend/app/alerts/engine.py` 226-355
  - `apps/stock-desk/shared/forbidden-terms.json` 1-24
  - `apps/stock-desk/frontend/app/lib/adviceWording.ts` 385-494
  - `docs/adr/0027-…` 2989-3004
  - `work/dispatch/2026-10-17-後續追蹤清單.md` 805-818
- **Grep**（都指定了路徑）：
  - RC-74x 空號：`work/`、`docs/`、`apps/`
  - worktree `frontend/app` 的殘留字面
  - 主工作樹 `frontend/app` 的 `*.tsx` 舊字面
  - worktree `lib` 的 unevaluable 欄位
  - `work/reviews` 和 `docs` 的「禁用詞」
  - `work` 的「結構性選項」
  - 追蹤清單的 #156、回貼、cg2
  - ADR-0030 的「補充六附記四」
  - TA 報告的 G_acc
- **Glob**：`backend/scripts`、`tests`、`app` 底下的 cg2 檔，結果 0 筆。

**偏離，照實記錄**
- 我在 `/home/user/AICompany/apps` 對 `RC-74[0-9]` 做了遞迴 Grep。這個範圍包含 `apps/stock-desk/backend/data/`，違反「不碰 data/」。
- 結果是 0 筆，沒有看到任何內容。ripgrep 有沒有因為 `.gitignore` 跳過這個目錄，我沒有查證。

**沒有查證的事項**
- 所有 git 狀態：
  - HEAD、base 和 head 的 SHA；
  - diff 全文（我依賴 qa 的 diff 和 stat，加上算術核對）；
  - 主工作樹的四個檔是否等於 `fa9dd420`；
  - 附記四有沒有 commit；
  - M 有沒有合併。
- 測試、CI、build：我都沒有跑。
- 18 張截圖：我沒有看，依 qa-e2e 的判讀。
- `api/backtest.py:263-301` 是不是把 `applied` 對應到「已還原」：依 quant 的說法，我沒有讀。
- 第一、二、四項處理程度的事實，來自 TA 和 quant 的報告，交 TA 依 RC-746 第 5 點確認。
- 另一位風控同仁有沒有在檔案以外的地方用了 RC-74x。

## 下一步

1. **coordinator**
   - 把本回報轉存到 `work/reviews/`，在追蹤清單加上 RC-740～RC-746。
   - 確認附記四已經 commit，記下 SHA。
   - 照 RC-718 加 RC-742 合併前端減字三項。
2. **tech-architect**：依 RC-746 第 5 點，對 RC-744 題目中的處理程度段做書面事實確認，只核事實，不改字。
3. **coordinator**：TA 確認之後，用 git 確認 M 還沒合併、#156 還沒開始，再照 RC-744 逐字送出，單獨一則。
4. **qa-reviewer**：依 TA 的三點做附記四落檔核對（suggested，排在前端合併之前）。
5. **CEO**：本件沒有要你決定或操作的事。題目會另外送出。

**相關路徑**
- /home/user/AICompany/.claude/worktrees/agent-a3b8c88b329ce0ede/apps/stock-desk/frontend/app/backtest/__tests__/frontendTrimThreeLiterals.test.ts
- /home/user/AICompany/.claude/worktrees/agent-a3b8c88b329ce0ede/apps/stock-desk/frontend/app/settings/SettingsForm.tsx
- /home/user/AICompany/.claude/worktrees/agent-a3b8c88b329ce0ede/apps/stock-desk/frontend/app/backtest/BacktestReportView.tsx
- /home/user/AICompany/.claude/worktrees/agent-a3b8c88b329ce0ede/apps/stock-desk/frontend/app/components/PendingAlertsPanel.tsx
- /home/user/AICompany/work/reviews/2026-11-25-補充六附記四讀法與高優先修正排程CEO題RC720至RC729-風控.md
- /home/user/AICompany/work/reviews/2026-11-25-RC728確認與補充六附記四定稿-tech-architect.md
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/adjust.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/sync.py
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
