# ADR-0029 D-10 第 1 點「CEO 清查主機 log 並輪換祕密」閘門判定（回應 RC-610）

- 判定者：security-engineer
- 日期：2026-11-22
- 方法：只用 Read、Grep、非變更性 git（`git log`、`git branch`、`git merge-base --is-ancestor`、`git grep`、`git show`）。未讀任何 `.env*`，未碰 `apps/stock-desk/backend/data/`，未執行 `.bat`，未改檔。報告不含任何 token 或 URL 值。

## 本次結論

1. **R-1 修補已合併進 `product/stock-desk`；告警通道本體沒有。** 閘門的兩個半邊要分開看。
   - R-1 分支三個 commit（`cb4e51a`、`ce56f43`、`91b5429`）都是 `product/stock-desk` 的祖先；合併 commit `3903df1`，committer date 2026-10-26T08:18:47Z。
   - 維運告警本體（`push_channels.py`、`ops_alert/sink.py`、`render.py`、`selftest.py`）不在 `product/stock-desk`；`app/ops_alert/` 目前只有 `__init__.py` 與 `model.py`。所以 D-10 第 2～6 點仍未成立，告警通道 PR 在我與風控判定前不得合併，這點照 RC-610 第 3 點。
2. **「CEO 清查 log」這一半是已落空的閘門，要補進 RC-587 名單。** ADR-0029 起草時（2026-10-18）R-1 尚未合併，閘門要求「R-1 合併且 CEO 完成清查與輪換」；R-1 在 10-26 合併，沒有任何紀錄顯示清查或輪換發生。這是依文件事實的判斷，沒有執行紀錄可證明「沒做」，記為「無完成紀錄」。
3. **建議做法：不清查、直接輪換（輪換只有帳號持有人能做）。** 不要求 CEO 讀 log、不要求回報任何內容。
4. **時點選草案一第 3 點 (c)**：無法事前攔截，改為事後揭露，並由風控判定可否接受、殘留記錄在閘門出處。不選 (a)。
5. **不建議做「只回報筆數」的唯讀工具。** 理由見下。

## 各部門回報（security-engineer）

### 1. 已合併情形的曝險評估

**事實（均附出處）**
- F-1 的成因仍在程式史上：`cb4e51a^` 的 `app/scheduler.py:782` 為 `logging.basicConfig(level=logging.INFO, ...)`；該行自 Phase 1（`dbd8d4f`，2026-07-23）起存在，`cb4e51a`（2026-10-18）才移除。出處：`git show cb4e51a^:...scheduler.py`、`git log -S'basicConfig'`。
- 同一個 `scheduler.py` 在 R-1 之前就會呼叫 `notify_all`（第 95、420～421 行；條件為 `settings.alerts.notify_webhooks` 為真）。`notify.py` 內有 Telegram URL 樣板（含 `{token}`）與 `httpx.Client()` 送出（`notify.py:42、120、144`，在 `product/stock-desk` 上）。`notify.py` 於 `f4f7baa`（2026-07-26，Phase 6）加入。
- httpx 在 INFO 等級記請求 URL，這在 `logging_setup.py` 的模組說明中記載，且是 F-1 的原始發現（ADR-0029 第 31 行）。
- R-1 合併後的程式：`configure_logging()` 將 `httpx`、`httpcore` 壓在 WARNING，另加 `redact_url()` 遮蔽 Telegram token、Discord webhook token、query 的 `token/apikey/api_key`（`logging_setup.py`）。`app/main.py:49`、`app/scheduler.py:786` 皆呼叫它。
- 主機部署手冊把兩個行程的輸出附加寫入 `logs\api.log`、`logs\scheduler.log`（手冊第 140、144 行）；ADR-0029 第 274 行指出容器部署的 Docker json-file 沒有大小上限。附加寫入代表舊內容不會因升級而被覆蓋。

**推論（未驗證）**
- 〔推論〕2026-07-26 至 2026-10-26 之間，只要 scheduler 在已設定 Telegram 或 Discord 的環境中真的送過告警，`logs\scheduler.log`（或容器 log）就可能含完整 URL，也就是含 token。這個條件鏈有三個環節我無法觀測：是否設定了通道、是否啟用 `notify_webhooks`、是否真的送出過。
- 〔推論〕R-1 的程式合併不會修改既有 log 檔；舊檔內容原樣保留。
- 〔推論〕CEO 實際執行的版本，要等他取得並啟動新版才會換成有遮蔽的程式；團隊觀測不到那一刻（RC-605 事實段同一個限制）。所以「10-26 之後新寫入的 log 已遮蔽」只對已更新啟動的行程成立。
- 〔推論〕曝險範圍：log 在 CEO 自己的主機上。只有在該檔被其他人或程序讀得到（備份同步、雲端資料夾、被貼出、被他人共用主機存取）時，token 才算被他人取得。上述各項我都不知道。

**未查證**
- 是否有任何通道實際設定過、`notify_webhooks` 是否為真；舊 log 是否仍存在；log 有無被備份、同步或分享；`product/stock-desk` 內資料源的 URL 是否另帶 query 憑證（R-1 的遮蔽規則涵蓋 `token/apikey/api_key`，但我沒有逐一盤點資料源）；Docker json-file 位置的內容。
- 我沒有檢查 R-1 遮蔽在 uvicorn 自己的 handler（API 行程的 access log）上是否生效；uvicorn access log 記的是進來的請求路徑，不是對外 URL，所以此處原本就不是 F-1 的路徑，但未實測。

**風險分級**：維持 high，不降級。理由：缺乏觀測，條件鏈中的一環成立就會有真實憑證留在檔案裡；但已知的外洩路徑需要其他人讀到該檔，因此不升 critical（critical 是「真實金鑰進 git」，本案不在 git 內，我也沒有在 git 內發現）。

### 2. 做法評估

**(甲) 不清查、直接輪換（優先，不需要 CEO 讀 log）**
- 內容：把 Telegram bot token 撤銷重發、把 Discord webhook 刪除重建。舊值作廢後，殘留在舊 log 的舊值沒有效力，不論 log 內有沒有。
- 優點：與「log 內有沒有」無關，不需要知道答案；不要求 CEO 查看或回報任何內容；不產生新的祕密流動。
- 副作用：
  1. 輪換期間到新值寫入主機設定之間，既有使用者告警的推播會失敗（這是 `notify_all` 的既有失敗路徑，不影響流程但沒有推播）。
  2. 新值必須由 CEO 自己寫入主機的環境設定檔並重啟 scheduler；團隊不得代為處理或要求看值。重啟會讓 scheduler 一併換成含 R-1 的程式（對本案是正向，但屬於一次行為變更）。
  3. Discord 重建 webhook 會改變 URL，若其他地方（其他頻道設定、其他工具）也用同一個 URL，那些地方會一併失效。
  4. 輪換只讓舊憑證作廢，**不會清除舊 log 檔**；舊檔仍含已作廢的字串，可能含的其他內容（價格、持倉、symbol）不因此改變。是否保留或刪除舊 log 是另一個決定，不屬於本閘門。
  5. 若從未設定任何通道，這個動作是白做；但白做的成本很低。
  6. 若資料源 URL 的 query 帶憑證（未查證），這些憑證不在此次輪換內。是否輪換由 devops-sre 對資料源逐一盤點後再提；本判定不要求 CEO 做。
- 殘留：輪換完成的時點是 CEO 的動作，團隊觀測不到，只能靠 CEO 的一句確認（見第 4 點）。

**(乙) 只回報筆數、不顯示內容的唯讀工具**
- 可行：寫一支唯讀腳本，只計算 `logs\*.log` 內符合 token 或 webhook 樣式的行數，輸出整數，不輸出任何內容。
- 不建議，理由：
  1. 計數為 0 也不能推出「不需輪換」：log 可能已輪替、被搬走、在容器 json-file 內，或寫在腳本沒掃到的位置；計數為非 0 才會推出「需要輪換」，但那時的動作還是 (甲)。所以不論結果，動作都是 (甲)，這支工具對決策沒有增量。
  2. 需要新增程式、qa-reviewer 審查，並依 RC-608 第 1 點逐案由風控核可；還要 CEO 執行並回報數字，違反「不把觀測責任移給 CEO」的精神。
  3. 工具本身若寫錯（例如不小心輸出匹配行），會製造新的外洩路徑。
- 若風控或 CEO 仍想要，最低條件：輸出只能是整數與檔案數，程式碼不含任何會印出匹配文字的呼叫，且附測試以假 token fixture 證明輸出不含該字串；執行與讀取都在 CEO 本機，結果不離開本機（RC-610 (a)）。

### 3. 時點選擇：草案一第 3 點 (c)

- 依 RC-608 對 (a)、(c) 的描述：(a)＝先合併唯讀工具、使用者執行並回貼結果；(c)＝寫明無法事前攔截，改成事後揭露。我沒有取得草案一第 3 點 (b) 的原文，不對 (b) 作評論；若 (b) 與以下理由相容，請風控或 tech-architect 對照。
- 選 **(c)**，理由：
  1. R-1 已在 10-26 合併，現在不存在「合併前閘門」可以擋，只剩既有主機上的舊 log，這正是 RC-610 (c) 說的「合併前閘門擋不住既有 log」。
  2. (a) 需要不建議的 (乙)，且把觀測責任轉給 CEO。
  3. 動作 (甲) 不依賴任何團隊可觀測的前置條件，沒有理由等待工具。
- (c) 要附帶的記錄（依 RC-608 第 2 點）：
  - 殘留：舊 log 中是否有真實憑證，無法觀測；CEO 是否完成輪換，只能靠 CEO 的一句確認；R-1 對 CEO 實際行程生效的時點無法觀測。
  - 這不是閘門自動解除。D-10 第 1 點在 CEO 確認輪換前，維持「未成立」。
  - 告警通道 PR 的合併條件維持：D-10 第 1 點成立（含 CEO 確認）、第 2～6 點成立，缺一不合併。

### 4. CEO 要做的事（中性事實，交 creative-lead 起草、風控逐字審）

事實項（不是字面，不得叫 CEO 貼內容）：
1. 以下兩種通道，若曾在這台主機上設定過，各有一個可以讓舊憑證作廢的操作，操作只有帳號持有人能做：
   - Telegram：在 BotFather 撤銷並重新產生該 bot 的 token。
   - Discord：刪除該 webhook 並重新建立。
2. 作廢之後，新值由 CEO 寫入主機自己的環境設定檔，重啟 scheduler 才會生效；在此之前，使用者告警的推播會失敗。
3. 團隊不需要、也不會要求看到舊值、新值、log 內容，也不需要 CEO 回報任何內容。
4. 唯一需要的回覆：一句「已輪換」「沒有設定過」或「暫不輪換」三選一；團隊用這一句更新 D-10 第 1 點的狀態。
5. 沒有設定過任何通道時，這件事沒有可做的動作。
6. 若 CEO 選「暫不輪換」，紀錄寫為「未輪換，暫不處理」；不得寫成「已處理」。D-10 第 1 點維持未成立，告警通道不合併。
7. 舊 log 保留或刪除，與本閘門無關，不在這一題內處理。

字面約束建議（供風控）：不得出現任何 token、URL、`.env` 內容；不得叫 CEO 貼上、截圖或讀出任何內容；不得推論「log 內一定有」；不寫已解除的語氣；不引用 R-1 代號、F-1 代號。

### 補件：回應 coordinator 的查證請求（使用者警示推送的曝險起點）

**事實（git 查證）**
- 使用者警示推送 `app/alerts/notify.py` 最早進入 `product/stock-desk` 的 commit 是 `f4f7baa`（Phase 6，2026-07-26T07:55:23Z）；`f4f7baa` 是現行 `product/stock-desk` 的祖先。
- 同一個 commit 的 `app/scheduler.py` 已 import `notify_all`（第 43 行）、在 `settings.alerts.notify_webhooks` 為真時呼叫（第 150～151 行），且 `main()` 內為 `logging.basicConfig(level=logging.INFO, ...)`（第 249 行）。也就是推送與 INFO 等級在**同一個 commit 就並存**，沒有「先有推送、後來才開 INFO」的時間差。
- `cb4e51a^` 的 `app/main.py` 沒有 logging 設定與 notify 相關行（grep 無命中）；API 行程沒有 `basicConfig`，故此路徑的曝險集中在 scheduler 行程。〔推論〕API 行程若也呼叫推送，其 httpx 不會被提到 INFO；我沒有逐一查 API 路由是否呼叫 `notify`。
- R-1 合併 `3903df1` 為 2026-10-26T08:18:47Z（台灣時間 16:18），與 devops-sre 一致；本體 `cb4e51a` 的 committer date 是 10-18T21:01Z（台灣時間 10-19 05:01），亦即 devops-sre 所說 10-19。

**結論**
- coordinator 的推論成立（以 git 事實為限）：曝險的主要來源是 **2026-07-26 至 2026-10-26 之間、scheduler 行程送使用者警示**，而不是 ADR-0029 的告警通道。ADR-0029 的通道本體沒有合併，不是來源；它只是把「是否清查並輪換」寫成上線前提。
- 〔推論〕曝險時窗：約三個月（07-26 至 10-26，且以 CEO 實際行程更新時點為準，團隊觀測不到）。是否真的寫出，仍取決於三個未觀測條件（通道有無設定、`notify_webhooks` 是否為真、是否送出過）。
- 對 (a)～(d) 與前述判定沒有改變：做法 (甲)、時點 (c)、不做 (乙)。調整兩處：
  1. D-10 第 1 點的「閘門落空」依據改為「R-1 合併前三個月的使用者警示 log」，不再是「告警通道」本身；補進 RC-587 名單時請用此說法。
  2. 輪換對象與 CEO 事實項不變（使用者警示用的就是同一組 Telegram／Discord 設定）。因為使用者警示現在就在用，輪換期間的推播失敗副作用（副作用 1）影響的是**使用者警示**，字面要照實寫，不要寫成只影響維運告警。
- 未查證：API 路由是否呼叫 `notify`；07-26 之後是否曾短暫關閉 INFO（我只比對首尾，未逐 commit 列出）。

## 驗證

**已執行**
- 補件：`git merge-base --is-ancestor f4f7baa product/stock-desk`、`git show f4f7baa:...scheduler.py | grep`、`git log -S'notify_all'`、`git show cb4e51a^:...main.py | grep`。

- `git branch -a --list`；`git merge-base --is-ancestor cb4e51a|ce56f43|91b5429 product/stock-desk`（皆為祖先，`origin/product/stock-desk` 同為 `21edb2a`）。
- `git log product/stock-desk --merges --ancestry-path 91b5429..product/stock-desk`：R-1 合併 `3903df1` 時間 10-26T08:18:47Z。
- `git ls-tree -r --name-only product/stock-desk` 篩選：確認 `app/ops_alert/` 只有 `__init__.py`、`model.py`，無 `push_channels.py`、`sink.py`、`render.py`、`selftest.py`。
- `git show cb4e51a^:...scheduler.py`、`git log -S`、`git grep` 於 `product/stock-desk`：F-1 成因行與 `notify_all` 呼叫點、`logging_setup.py` 遮蔽規則。
- Read：RC-610 所在審查檔全文、ADR-0029 命中行（第 16～19、28～32、245、274 行）。

**未驗證**
- 主機上實際的 log 內容、通道設定狀態、CEO 行程執行的版本；devops-sre 另查的結論若與我的 `git` 結果不一致，以事實為準並告知我。
- 遮蔽規則在 uvicorn handler 上的行為（未實測）。
- 資料源 URL 是否帶 query 憑證（未盤點）。
- 草案一第 3 點 (b) 的原文。
- 我讀的是本機 repo 的 `product/stock-desk` 與 `origin/product/stock-desk`，兩者目前同為 `21edb2a`；沒有 fetch 遠端新狀態。

**Verdict**：NEEDS_CHANGES
BLOCKING_ISSUES=true
（阻擋範圍：告警通道 PR 合併、D-10 第 1 點視為成立。不阻擋其他工作。）

## 下一步

- **風控**：收件；確認 (c) 的選擇與殘留記錄；對第 4 點的事實項與字面約束逐字審；把「CEO 清查 log」補進 RC-587 已落空名單（R-1 合併 10-26、無完成紀錄）。
- **creative-lead**：依第 4 點起草 CEO 可見字面，送風控逐字審；不得要求貼內容。
- **devops-sre**：確認其「已合併」結論與本報告一致；盤點資料源 URL 是否帶 query 憑證；舊 log 的實際位置（含 Docker json-file）只記路徑，不讀內容。
- **tech-architect**：D-10 第 1 點文字依 (c) 與「由 CEO 一句確認」改寫（新 ADR 取代，ADR-0001），告警通道 PR 維持不合併。
- **coordinator**：N 項追蹤加入「D-10 第 1 點：無完成紀錄」；取得 CEO 的一句回覆後通知我與風控。
- **CEO**：待風控審定的字面送達後，三選一回覆；在那之前沒有需要決定的事。
