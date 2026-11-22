# RC-556 改字時點裁示與 R0-2 盤點（RC-555 (i)）

- 審查者：tech-architect
- 日期：2026-11-22
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：RC-556 改字時點裁示、R0-2 盤點（RC-555 (i)）

全程唯讀，只用了 Read、Glob、Grep。沒有寫檔，沒有執行 git、uv 或 pytest，沒有讀 `.env*`，沒有碰 `apps/stock-desk/backend/data/`，也沒有看 `.claude/worktrees/`。

**先標 high 項（依 RC-555 (iii)，請 coordinator 今天轉風控）**

R0-2 標為 high、或寫明「查到即升 high」的項目裡，有 4 項的程式已經在 `product/stock-desk`。也就是說已經在 CEO 可能在跑的版本裡，但 `work/` 裡找不到 CEO 知悉過的紀錄：

1. **C-1（high，屬過去曝險）**：決策卡第 4 條用占位匯率 1.0 計算。這個缺陷從 2026-07-26（09a6833）一直存在，到 PR-0（9f5166e）進了 CEO 本機才消失。現行 checkout 已經修好（`engine.py:357` 加了守門，`book.py:358` 有 `MIXED_CURRENCY_NOTE`）。CEO 在缺陷期間有沒有依卡片決策，沒有紀錄。
2. **X-2、X-3、X-8（有條件的 high）**：
   - X-3c（6a83097）已經在 product。依 X-6，本機只要有 1 列以上「幣別與市場不符」就是 high。
   - X-3c 進 CEO 本機之前，如果有這種列，數字會失真約 31 倍，畫面沒有提示。
   - X-3c 進來之後，總資產可能明顯下降（X-8），CEO 事前沒有被告知。
   - 本機有沒有這種列：不知道。X-3a 沒有任何結果回貼紀錄。
3. **X-9（有條件的 high，現在沒人觀測得到）**：X-3b 的 log（`valuation.py:389`）已經在 product，log 一出現就是 high。但沒有人讀 CEO 本機的 log。
4. **X-13、F1b（有條件的 high，現在沒人觀測得到）**：F-1b（7fc90b2）已經落地。F-1b 自己的警告（`valuation.py:589` `unusable fx rate dropped from valuation`）一出現就是 high。log 存在哪裡、誰去查，R0-2 第 274 行列為未落實，之後也沒找到落實紀錄。

另外有兩道閘門已經失效，等級不是 high，但同樣是「已上線、CEO 沒有知悉」：
- **D-1**：PR-1（be64f49）「上線以 CEO 接受 ADR-0023 前提 4 為閘門」。ADR-0023 仍是 proposed。
- **X-14**：PR-RK4c（58359be）「須在發布前簽回」。

---

## 本次結論

1. **第 1 題（RC-556 時點）**
   - 【裁示】排在**正式登記完成（登記紀錄 commit 落檔）之後**，而且**在退役 PR 合併之後**。
   - 跟接線 PR 不規定先後，但不得放進同一個 PR。最好的時點是退役 PR 合併後、接線 PR 最後一次 merge product 之前，這樣接線 PR 只要在原本就必做的那次同步裡一併吸收。
   - 不需要 ADR 補充。
   - 三個檔都不在 `code_digest` 範圍內，所以：
     - 不動 `code_digest`，接線版 `code_digest` 不會因為 RC-556 再變一次；
     - 不動 REAL_PINS 的 `frozen_files`、`definition_*`、`rules`；
     - 不牽動 `kelly_wording.py` 的任何已登記雜湊或定義物件。
   - 會動到的只有 `app/` 的 tree id。CG-2 合併 commit M 之前、以及 M 到登記完成之間，都不得落地。
2. **第 2 題（R0-2 盤點）**：44 條逐條分類，表在下面。
   - 摘要：
     - 「仍有效」13 條，其中 4 條是休眠條款（E-4、E-6 (2)、E-10、E-3 (4)(5)）；
     - 「已被後來的程式取代」14 條；
     - 「內容改變」17 條。
   - D-5、D-6 已經失去「部署前置」的作用。剩下的用途都可以改用別的方式處理，不必請 CEO 執行。
   - R0-2 有沒有送出：`work/` 裡找不到任何送出或回覆紀錄。
3. **有沒有必須由 CEO 決定的事**：本件沒有。新知悉包的內容依 RC-555 (ii) 由 creative-lead 起草、風控逐字審。

---

## 各部門回報（tech-architect）

### 第 1 題：RC-556 改字的時點（書面裁示）

#### 評估摘要

- 採用：**登記完成後、退役 PR 合併後，獨立 PR**。
- 否決：登記前落地、併入接線 PR、併入文件 PR（RC-554）。

#### 事實（逐項回答派工問題）

**`code_digest`：不動。**
- 【事實】`code_digest` 的範圍是 `app/forecast`、`app/outlook`、`app/dirdef`、`app/data/session_calendar.py`。出處：
  - ADR-0030 第 135 行；
  - `app/forecast/canonical.py:77-78` 的 `CODE_DIGEST_PACKAGES = ("forecast", "outlook", "dirdef")`、`CODE_DIGEST_FILES = ("data/session_calendar.py",)`。
- 【事實】RC-556 動到的檔都在範圍外：
  - `app/api/backtest.py`、`app/api/kelly_wording.py`、`app/backtest/event_study.py`；
  - suggested 的 `app/dividends/sync.py`、`app/api/deps.py`；
  - `tests/` 與 golden。
- 【事實】`app/forecast`、`app/outlook`、`app/dirdef` 都沒有 import 這三個模組（Grep 零命中）。
- 【推論】所以 D-5 第 6 點的重算不會被觸發；不論在接線前還是接線後合併，對預測紀錄帳都沒有作用。接線版 `code_digest` 只會因為補充十四再變一次（追蹤清單第 733、751 行已記），不會因為 RC-556 再變。

**`app/` tree id：會變。** 這是唯一受影響的釘點。
- RC-507 (2) 要求 `M:apps/stock-desk/backend/app` 等於 `d631a75a4aba2ace76c44e8647d1bd11180662d5`。RC-556 如果在 CG-2 合併前進了 product，M 的 `app/` tree 就不會等於這個值，只能回頭在 CG-2 分支重釘。這直接違反 RC-511（CG-2 分支只能新增 `work/reviews/` 的 `A`），M-9 也要重開。
- 補充六第 6 點 (d)：從管線驗收的 `git_head` 到 CG-2 合併 head 之間，`app/` 只允許列舉的那幾種差異。`app/api/*` 不在列舉內，進來了驗收就失效，CEO 必須在新 head 重跑。
- 補充七附記三第 1 點的 R-1：預檢與登記時，`HEAD:apps/stock-desk/backend/app` 的 tree id 要等於常數；coordinator 人工核對「合併 commit 與 `git_head` 之間 `app/` 沒有 diff」。M 到登記完成之間進來任何 `app/` 變動，登記一定 STOP。這段期間同時也是 #156 的禁止期間。
- 登記完成之後：RC-507 (2) 只約束 M（我 11-21 的裁示，以及追蹤清單第 733 行），R-1 測試也會隨退役 PR 刪除，所以沒有其他東西釘住 `app/` tree id。另外，coordinator 11-21 已查過 9 支待合併分支，都沒有釘 tree id 的常數（追蹤清單第 735 行）。

**REAL_PINS 與 `frozen_files`：不動。**
- 【事實】`frozen_files` 對應 M-2（事先宣告 v0.32）與 M-3（C-8 紀錄檔）兩份文件；`definition_*` 對應 M-4；`rules` 對應 M-5 的 h3、h5 YAML。出處：ADR-0030 第 514～520 行，以及我 11-21 的 `review_refs` 裁示第 29 行。
- RC-556 一個都沒碰。
- 禁詞比對 `registration_phrase_scan` 只掃規則集與 definition 的字串（`app/forecast/definitions.py:275-297`），不掃 `app/api`。

**`kelly_wording.py`：沒有任何已登記雜湊或定義物件。**
- 【事實】檔內 Grep 不到 `sha256`、`hashlib`、`digest`。`app/kelly/freeze.py` 也不含任何 wording 或雜湊。
- 84 句清冊（`kelly_wording.py:1163-1173` 一帶）是「鍵對常數」的映射。改 B 句只改 `"div-never-synced"` 對應的值，鍵集合和數量都不變，`test_the_batch_is_every_sentence_the_review_has_closed_on` 不需要改。要改的只有 `CONFIRMED_VERBATIM` 的期望值。
- 【事實，依 dev-lead 查證】B 句在讀取時由已存的 `dividend_reason_code` 組出，DB 不存句子本身。【推論】改字後舊列會顯示新字面，不需要資料遷移。Kelly 凍結只凍結寫入，不受影響。
- ADR 方面：`docs/adr/` Grep 不到 A、B、C 三句的字面，也沒有任何 ADR 釘住它們。

#### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (1) CG-2 合併前落地 | 最早消掉畫面上的指令 | 破壞 RC-507 (2)，逼得 CG-2 回頭重釘，違反 RC-511，M-9 重開；管線驗收依補充六 6(d) 失效，CEO 要重跑 | 否決 |
| (2) M 到登記完成之間 | 無 | R-1 必然 STOP，而且落在 #156 期間 | 否決 |
| **(3) 登記完成、退役 PR 合併之後，獨立 PR（採用）** | 對 ADR-0030 零牽動；退役 PR 已記錄的 tree id `185c424b…` 不會因此過時；接線 PR 本來就要 merge product，可以一併吸收 | 畫面上的指令要多留一段時間 | 低：RC-553 已把那條指令列入 RC-476 常設範圍；風控也判定不急 |
| (4) 登記完成後、退役 PR 合併前 | 比 (3) 早一點 | 技術上可行，因為 S-22 是相對 merge-base；但退役 PR 說明裡的新 tree id 要重算，qa 要重核，而退役 PR 在接線的關鍵路徑上 | 不採用：多一輪重工 |
| (5) 併入接線 PR | 少一個 PR | 接線 PR 多出兩個語意（產品文案、golden），W-7、S-20a 的零差異證明要改寫；RC-284 的精神是接線 PR 不夾帶其他變動；兩邊的審查節奏會互相拖住 | 否決 |

#### 決策（不需要 ADR 補充）

- 理由：時點限制全部直接來自既有條文，沒有任何條文的字面或讀法要改。依據是 ADR-0030 補充六第 6 點 (d)、補充七附記三第 1 點、RC-507 (2)、RC-511、#156。RC-556 也不碰 `code_digest` 範圍，沒有 D-5 第 6 點的新情境。
- 改在追蹤清單加一列就足以追蹤（內部文字，不是 CEO 可見字面）。建議寫法：
  - 「RC-556 改字 PR：依 tech-architect 11-22 裁示，登記紀錄 commit 落檔且退役 PR 合併之後才可合併；獨立 PR，不併入接線、README、RC-554 文件 PR；不得落在其他 PR 的最終 head 驗證到合併之間；不動 `code_digest` 範圍。」

#### 對實作的約束（逐條可由 qa-reviewer 檢查）

1. 從 `product/stock-desk` 開獨立分支，自成一個 PR。不得與 RC-554 文件 PR、README PR（RC-459）、接線 PR 同一個 PR。
2. 變動檔限於：
   - `app/api/backtest.py`、`app/api/kelly_wording.py`、`app/backtest/event_study.py`；
   - `tests/test_api_backtest_dividends.py`、`tests/test_api_event_study.py`、`tests/test_kelly_wording.py`；
   - `tests/golden/backtest/` 的 4 份、`tests/golden/event_study/walk.json`；
   - 選做（RC-556 第 7 點，只改英文註解或 docstring）：`app/dividends/sync.py`、`app/api/deps.py`、`tests/conftest.py`。
   - 不得有其他檔，前端零差異。
3. `git diff <merge-base> HEAD -- apps/stock-desk/backend/app/forecast apps/stock-desk/backend/app/outlook apps/stock-desk/backend/app/dirdef apps/stock-desk/backend/app/data/session_calendar.py` 必須為空。PR 說明附上合併前後在同一支 `canonical.code_digest` 算出的值，兩者相等。
4. Golden 的 diff 只能是 A 句 8 處（4 檔各 2 處）與 C 句 1 處，不得有其他行。
5. `kelly_wording.py`：
   - 只改 `KELLY_DIVIDEND_NEVER_SYNCED_FACT` 的值（必要時加第 533～536 行的理由註解）；
   - 清冊鍵集合與數量 84 不變；
   - E3 括號版常數與它的測試零差異。
6. `DIVIDEND_BIAS_SCOPE_NOTE` 零差異，A 句照舊串接它（RC-556 2(a)）。
7. `test_the_sync_command_is_quoted_the_way_it_is_actually_run` 改成反向守門：使用者可見的除權息句裡不含 `uv run`、`python -m`。逐字釘住的兩支測試改釘風控定稿的字面。
8. 合併時點，以下全部成立：
   - (a) 登記紀錄 commit 已經在 `work/`；
   - (b) 退役 PR 已經合併；
   - (c) 不在 #156 期間；
   - (d) 不落在其他 PR「最終 head 已送驗證」到「合併」之間。gap-check 的 F10 與 RC-399 (d)、接線 PR 的最終全套、驗收一鍵檔退役分支的 F10，都是綁 head 的驗證。
9. RC-556 如果先於接線 PR 進 product：接線 PR 的 `code_digest` 照舊在最終 head 重算（追蹤清單第 733 行），預期與 merge RC-556 之前相等。qa 用這一點做一致性核對。
10. ruff、ruff format、mypy、全套 pytest（3.12）綠燈；送 qa-reviewer（有 Codex 就用）；字面送風控逐字審（RC-556 第 2 點）。不改 DB schema 或資料。

---

### 第 2 題：R0-2 盤點（RC-555 (i)，只寫事實）

**分類定義**
- 仍有效：所寫內容對目前 product 仍然成立，仍需要 CEO 知悉或決定。
- 已被取代：後來的程式已經改變行為，條文描述的狀態不再存在，或只剩歷史意義。
- 內容改變：部分成立，前提或範圍變了，要改寫才能再用。

**共同依據**
- 「已在 product」以兩種證據判斷：
  - 任務單的結案紀錄寫「已 push 至 `product/stock-desk`」；
  - 主工作樹 Grep 到對應的字面或程式。dev-lead 記錄主工作樹為 product HEAD `5a66a4c`，我沒有用 git 核對。
- 各項**進 product 的日期一律未查證**，見文末交 devops-sre 的清單。

#### A 組（部署前提）

| 項目 | 分類 | 事實與出處 | 註記 |
|---|---|---|---|
| C-1 | 已被取代（歷史曝險未知） | PR-0 9f5166e 已 push（PR-0 任務單第 401～402 行）；`engine.py:357` 以 `portfolio.close is not None` 守門，`book.py:358` 有 `MIXED_CURRENCY_NOTE` | **high**，見開頭第 1 點 |
| C-2 | 已被取代 | 暫行做法以「PR-0 修好、本機更新」為消除條件（R0-2 第 40 行）；X-7 的建議股數影響由 X-3c 處理（不符列不估值） | |
| C-3 | 仍有效 | 常設前提「只有 TWD 與 USD 兩種計價幣別」，擴充幣別時要重審（R0-2 第 46 行） | 我沒有重新讀碼確認現在仍只有兩種 |
| C-4 | 已被取代 | 這是內部 e2e 紀錄的更正；PR-0 與 X-3c 之後，對 CEO 沒有可行動的意義 | |

#### B 組（X-3 系列）

| 項目 | 分類 | 事實與出處 | 註記 |
|---|---|---|---|
| X-1 | 內容改變 | X-3c 6a83097 已 push（X-3 任務單第 971～972 行），不符列會在畫面上自行揭露：`valuationWording.ts` 有「幣別與市場不符」，`book.py:216` 為 (b)，`book.py:372` 為 (c)。「請改跑 X-3 腳本」受 RC-553 的 P1 約束。ADR-0017 待決點 2 仍未結案（X-3 任務單第 5、52 行） | |
| X-2 | 已被取代（殘留仍有效） | X-3c 之後不符列不估值。RN-16(c) 的殘留 (iii)「加碼建議仍可能出現但不給股數」仍在：ADR-0023 (A) 降級句「無法用風險上限確認加碼」在 `app/` Grep 零命中 | **有條件的 high**，見開頭第 2 點 |
| X-3 | 已被取代 | 同上，X-3c | **有條件的 high**，同上 |
| X-4 | 仍有效 | 畫面字面 (b) 已帶修正路徑；RX-9 PASS（X-3 任務單第 973 行）。RC-552 判定不在文件裡另外禁止 | |
| X-5 | 已被取代 | R0-2 第 125 行自己寫明，X-3c 上線後就不適用 | |
| X-6 | 內容改變 | 分級依 X-3a 結果而定。X3-R2「X-3a 交付後的下一次部署，以腳本已執行並回報為前置」：X-3b、KX-10、X-3c 都已在 product，`work/` 裡沒有任何 `X-3_out` 結果回貼紀錄（Grep 只命中腳本、README 與 R0-2 本身） | **閘門落空** |
| X-7 | 已被取代 | 已併入 C-2；X-3c 之後，不符列不再影響建議股數 | |
| X-8 | 仍有效 | 描述的就是 X-3c 的現行行為，CEO 沒有知悉紀錄 | **有條件的 high**，見開頭第 2 點 |
| X-9 | 內容改變 | X-3b 5124337 已 push（X-3 任務單第 930 行）；`valuation.py:389` 的 log 仍在。「失真會持續到 X-3c 上線」這半句已隨 X-3c 結束 | **有條件的 high**，現在沒人觀測得到 |

#### C 組（匯率來源、X-13、X-14）

| 項目 | 分類 | 事實與出處 | 註記 |
|---|---|---|---|
| X-10 | 內容改變 | PR-RK2 cf9619e（RK-2 任務單第 59 行，`book.py:388` 銜接句）與 PR-RK4c 58359be（RK-4 任務單第 134～143 行，`book.py:1122` `quote_shown`）都已落地，「修正前」一段已不是現況。前提「台銀仍被擋」：2026-09-19 之後沒有查證紀錄；RK4c-R11 的定期查證也沒找到紀錄 | 前提未查證 |
| X-11 | 內容改變（第 4 點與第 4 點之二仍有效） | PR-RK4a a553e6c、PR-RK4b 2fec1ac（RK-4 任務單第 72、86 行，`book.py:406` 歸屬句）。第 4 點的永久殘留需要 CEO 明示接受，尚未取得 | |
| X-12 | 內容改變 | PR-RK5a 910344a、PR-RK5c f3e3508、PR-RK5b 012850b（RK-5 任務單第 45～74 行，`portfolio/summary.py:48` 混源句）；W11-5 沒有接線（`app/` 無 fx 快取，Grep 只有 `book.py:1493` 一句註解）。現況 low | |
| X-13 | 內容改變 | F-1b 7fc90b2（F-1b 任務單第 479 行，`valuation.py:589`），「F-1b 合併前」這一段已不是現況。新的升級觸發是 F-1b 自己的警告；log 保存位置與查看時點未落實 | **有條件的 high**，現在沒人觀測得到 |
| X-14 | 仍有效（簽回時限已落空） | PR-RK4c 已經出貨，條件是「CEO 於發布前簽回 X-14」（RK-4 任務單第 139、143 行），沒有取得；字面 C 也還沒加（R0-2 第 301 行） | 閘門落空 |

#### 補充收錄（F1、F1b）

| 項目 | 分類 | 事實與出處 | 註記 |
|---|---|---|---|
| F1-知悉 1 | 已被取代 | F-1b 7fc90b2 已把非正匯率降為未估值（`price_guard.py:51` `usable_rate`） | |
| F1-知悉 2 | 仍有效 | F-1 f25c90d 已落地（F-1 任務單第 163 行）。之後有沒有改歸因，沒找到紀錄，也沒讀碼核對 | |
| F1-知悉 3 | 仍有效 | F-2 沒有落地：`frontend/app/lib/keyLevels.ts:99-106` 只擋非有限值，不擋收盤價 ≤ 0；追蹤清單 T-3 仍列待辦（第 27 行）。F-1 任務單寫「F-3 查到非零就把 F-2 升級」，F-3 沒有執行過 | 有條件的升級 |
| F1b-知悉 | 內容改變 | 這一條只指向 X-13，狀況同 X-13 | 同 X-13 |

R0-2 第 305 行寫「補充收錄請 coordinator 確認是否併入正式包」，沒找到確認紀錄。

#### D 組（決定項）

| 項目 | 分類 | 事實與出處 | 註記 |
|---|---|---|---|
| D-1 | 仍有效（內容改變） | ADR-0023 仍是 proposed，前提 4「仍待 CEO 表態」（ADR-0023 第 3、23 行）。PR-1 be64f49 已 push（6-a 任務單第 225 行），但 R0-2 第 328 行寫的是「上線仍以你接受前提 4 為閘門」。(A) 沒有落地，殘留 (iii) 仍在；6-b（PR-3）的 W-b1 字面「若計入無法估值的部位」Grep 零命中，推定也沒有落地。D-1b、D-1c 的同 release 包裝前提，已經因為 PR-1 先上線而改變 | 閘門落空，等級 medium（(viii)） |
| D-2 | 內容改變 | 提議仍待 CEO 核可（ADR-0015 第 373、376 行）；提議裡的前置條件 PR-RK2 已經合併；W11-5 沒有接線 | |
| D-3 | 內容改變 | 同 D-2（ADR-0015 第 378、385 行）；PR-RK5a、5b、5c 已經合併；N-2、N-3 仍是 W11-5 的前置 | |
| D-4 | 已被取代 | `data/service.py:1019-1031` 第一次失敗就帶 `RECENT_ATTEMPT_FAILED_REASON`，註解引用風控 F11-W-38；10-15 決策包第 65 行寫「F-6 殘項」已合併。沒找到 CEO 決定立案的紀錄 | |
| D-5 | 內容改變 | 見下方「D-5、D-6 還需不需要」 | |
| D-6 | 內容改變 | 同上 | |
| D-7 | 已被取代 | 排序已經執行：X-3c、RK 系列都已落地（各任務單結案紀錄） | |
| D-8 | 內容改變 | `work/` 找不到 tag 或部署紀錄（Grep `release v0.1`、`git tag -a`、`部署紀錄` 都只命中 10-08 以前的檔，以及 N-190 那份「沒辦法查證部署紀錄」）。`dev-up.bat` 第 109～110 行每次啟動都 `git pull --ff-only`，「部署」已經不是一次獨立的事件 | |

#### E 組（風控書面異議）

| 項目 | 分類 | 事實與出處 |
|---|---|---|
| E-1 | 內容改變 | R0-1 的兩項期限已符合；「F-1 那次部署前書面回覆」已經落空 |
| E-2 | 內容改變 | (1)「沒查就部署」已在事實上發生（X-3b、X-3c 在 product，沒有腳本結果）。(2) KX-10 dd3f9da 與 X-3b 5124337 都在 product。RX-12（release note 與 PR-X3b-2 同次發布）：發布說明草稿之後沒找到送出紀錄 |
| E-3 | 已被取代（(4)、(5) 仍有效，休眠中） | RX-9 PASS、XC-L2-R1 相符（X-3 任務單第 973、1012 行）。(4)、(5) 只在 CEO 要求改字時才會觸發 |
| E-4 | 仍有效（休眠中） | 出貨的是 72 字定稿；只有 CEO 要換回主案時才成立 |
| E-5 | 已被取代 | PR-RK2 已經合併，「W11-5 早於 PR-RK2」已經不可能發生 |
| E-6 | (1) 仍有效；(2) 休眠中；(3) 已不成立 | 出貨的是 41 字 W-RK4-1；收盤價閘門已落地 |
| E-7 | 仍有效 | W11-5 沒有接線，N-2、N-3 仍適用 |
| E-8 | 仍有效 | ADR-0023 仍是 proposed；PR0-F6 的情形不成立 |
| E-9 | 已被取代（推定） | ADR-0022 PR 66a88b3 已 done，W-6u 列在合併前提裡（ADR-0022 第 9 行；產業上限任務單第 282 行）。我沒有讀碼核對 W-6u 字面 |
| E-10 | 仍有效（休眠中） | 只在 CEO 有不同意見時才成立 |
| E-11 | 仍有效 | F-2 沒有落地（同 F1-知悉 3） |
| E-12 | 內容改變 | K-B 路徑實際上成立了（X-3c 已出貨）；發布說明沒找到送出紀錄 |

分類計數（44 條）：仍有效 13、已被取代 14、內容改變 17。
- 仍有效：C-3、X-4、X-8、X-14、F1-2、F1-3、D-1、E-4、E-6、E-7、E-8、E-10、E-11。其中 E-4、E-10 整條休眠，E-3 (4)(5)、E-6 (2) 是部分休眠；E-3 歸在「已被取代」。
- 已被取代：C-1、C-2、C-4、X-2、X-3、X-5、X-7、F1-1、D-4、D-7、E-3、E-5、E-9，以及 C-5（R0-2 已標為被取代，未另計勾選，本計數不含）。
- 已被取代、但殘留仍有效：X-2 的 (iii)、E-3 的 (4)(5)。

#### D-5、D-6 在 X-3c、F-1 落地後還需不需要

**D-5（X-3a）：作為部署前置已經沒有作用。**
- 部署早已發生；X3-R2 落空這件事要照實記錄，不能靠補跑腳本修復。
- X-3c 之後，不符列由產品自己在讀取時判定並揭露，數字已不會失真。
- 剩下的用途有兩個：
  - (a) ADR-0017 待決點 2 的正式結案；
  - (b) 腳本的「無法讀取列」分類。X-3c 有沒有涵蓋無法讀取的列，我沒有讀碼核對。
- 【建議】這兩項不必請 CEO 執行。(a) 可以改以「畫面有沒有出現 (b)」作為等價觀察，經風控同意後結案；(b) 由 dev-lead 讀碼確認 X-3c 對無法讀取列的行為。真的需要本機執行時，照 RC-553 的 P1 另擬新文件。

**D-6（F-3）：作為部署前置也已經沒有作用。** F-1 已經在 product，「F-1 是否擋部署」這個問題已經不存在。
- 剩下的用途是決定 F-2 的優先序（F1-知悉 3）。
- 【建議】直接把 T-3（`computeKeyLevels` 在收盤價 ≤ 0 時回 null）或 F-2 排進開發，這樣不論本機資料如何，這個缺口都會消失，不必請 CEO 跑腳本。
- F-3 不掃匯率，對 X-13 也沒有證據價值（R0-2 第 275 行）。

#### R0-2 當初有沒有送出

- 【事實】Grep `R0-2`、`簽核包`、`知悉包` 遍查 `work/`，命中的只有：
  - 2026-10-08 的起草與審查檔；
  - 追蹤清單第 756、758、759 行（都是 11-22 寫的）；
  - 11-21 風控 RC-407～RC-421 那份第 314 行，提到「2026-10-08 的簽核包寫過…」，只是引用內容，不是送出紀錄；
  - 11-22 的幾份檔。
- 10-15～11-20 的 CEO 決策檔與決策包（`work/dispatch/` 檔名含 CEO 的各份）都沒有引用 R0-2。R0-2 第 449～459 行的簽核欄是空白。
- 結論：`work/` 裡沒有送出紀錄，也沒有回覆紀錄。CEO 是否在對話中收到或回覆過，我無從查證。這和 RC-555 第 1 點的前提一致。

#### 需要 git 才能確定的事（交 devops-sre，我沒有猜）

1. `apps/stock-desk/dev-up.bat` 的 `git pull` 從哪個 commit、哪一天開始，例如 `git log --format='%H %ci' -S'git pull' -- apps/stock-desk/dev-up.bat`。
   - 也請確認 2026-10-08 當時的版本有沒有這一行：`git show <當日 product commit>:apps/stock-desk/dev-up.bat`。
   - 輔助事實：10-08 devops-sre 的核對只寫到 `dev-up.sh` 會 pull（PR-0 任務單第 319 行）；10-26 的產品審視已寫明 `dev-up.bat:75-79` 會 pull；10-03 的手冊叫 CEO 手動 pull（第 107 行）。
2. 下列 commit 各自進入 `product/stock-desk` 的時間：commit 日期與「第一次成為 product first-parent 祖先」的時間分開列。
   - 06ea06b、09a6833、9f5166e（PR-0）、be64f49（PR-1）、171907e（R-2-a）、f25c90d（F-1）、66a88b3（ADR-0022 PR）；
   - 5124337（X-3b）、dd3f9da（KX-10）、cf9619e（PR-RK2）、6a83097（X-3c）；
   - 910344a、f3e3508、012850b（RK5a、5c、5b）；
   - a553e6c、2fec1ac、58359be（RK4a、4b、4c）、72e227e、d57c10b（RK4c-R3）；
   - 7fc90b2（F-1b）；F-6／W-38 對應的 commit；518b1e5（dev-up 起 scheduler）；4b47940（dividend_sync）。
3. PR-2（(A) 降級句）、PR-3（6-b）、F-2、T-3 有沒有 commit 存在於任何分支。我只用字面 Grep 了主工作樹。
4. 主工作樹 HEAD 到底是 `5a66a4c` 還是 `7e54571`（風控已指出有兩種說法），以及主工作樹是否就在 `product/stock-desk`。
5. `git tag -l`，以及有沒有任何 release commit 或部署紀錄（對應 D-8）。
6. E-9：W-6u 字面所在的 commit 是否就是 66a88b3。

CEO 本機實際跑的是哪個 HEAD、啟動過幾次，不是 repo 內的 git 查得到的。要問 CEO 只能用風控定稿的題目（RC-555 第 4 點），不得另外追問。

---

## 驗證

**讀過的檔**
- 風控 RC-548～RC-560 全文；dev-lead 揭露句查證全文。
- 我 11-21 的退役鏈裁示全文；補充十四組版全文。
- 追蹤清單第 1～40、604～607、700～704、725～760 行。
- R0-2 全文，分三段讀：1～234、235～364、365～507 行。
- ADR-0030：第 122、135、180～184 行（Grep），第 500～529、625～669、905～974 行。
- ADR-0022 第 1～15 行；ADR-0023 第 1～25 行，加 Grep；ADR-0015 的 Grep。
- 任務單：
  - RK-4 第 60～143 行；
  - PR-0、X-3、F-1、F-1b、RK-2、RK-5、6-a、產業上限各任務單的結案相關行（Grep）。
- `app/forecast/canonical.py` 第 15、77～78、214～234 行（Grep）；`definitions.py:275-300`；`data/service.py:94-98, 1005-1032`；`kelly_wording.py:1150-1179`；`dev-up.bat` 第 1～25、106～115 行。
- 發布說明草稿第 1～15 行；10-16 暫停點全文。

**Grep 結果**
- 有命中：
  - `app/` 中，X-3c 的 (b)(c)、PR-RK2 銜接句、RK4 歸屬句、`quote_shown`、RK5b 混源句、X-3b log、F-1b log、`usable_rate`、F-6 原因句、PR-0 守門；
  - 前端「幣別與市場不符」。
- 零命中：
  - `app/` 中的 (A) 降級句、W-b1 字面、fx 快取；
  - `kelly_wording.py` 的雜湊字樣；
  - `forecast`、`outlook`、`dirdef` 對三個模組的 import；
  - `work/` 的 X-3a、F-3 結果回貼、tag 或部署紀錄、台銀定期查證（10 月中以後）。

**沒有查證的事**
- 所有 git 事實（見交 devops-sre 的清單），包括主工作樹的分支與 HEAD。
- CG-2 分支上 `cg2_register.py` 的 REAL_PINS 實際內容：主工作樹沒有這個檔，我依 qa、風控、dev-lead 的紀錄判斷。
- 接線分支會不會也改到 `app/api/deps.py` 或 `tests/conftest.py`：接線範圍清單只存在於 worktree，我沒有看。合併時由 dev-lead 用 merge-tree 確認。
- X-3c 對「無法讀取列」的行為。
- W-6u 字面是否已經落地。
- F1-知悉 2 的歸因是否已被改寫。
- 現在是否仍只有 TWD 與 USD 兩種幣別。
- 台銀現在是否仍被擋。
- CEO 本機的版本、log、DB 內容。
- 是否在對話中送出過 R0-2。

---

## 下一步

- **coordinator**
  - 今天把開頭的 high 項轉風控（RC-555 (iii)），由風控決定要不要提前單獨告知。
  - 追蹤清單加入第 1 題的時點列，並把第 2 題的盤點結果記在「R0-2 部署前提失效另案」那一列。
  - 新閘門落空 4 項照實記錄：X3-R2、D-1 的 PR-1 閘門、X-14 發布前簽回、RX-12 發布說明送出紀錄。
- **devops-sre**：補上述 6 項 git 事實，結果書面交 tech-architect 與風控。
- **creative-lead**：等風控看過盤點後，依 RC-555 (ii) 起草新知悉包，只放「仍有效」與「內容改變」中風控認定要送的項目。另依 RC-556 起草 A、B、C 三句。
- **dev-lead**：RC-556 字面定稿後，依第 1 題的約束 1～10 另開任務單，並依約束 8 排合併時點。另外只讀確認 X-3c 對無法讀取列的行為（D-5 剩下的用途）。
- **frontend-engineer 與 coordinator**：把 T-3（`computeKeyLevels` 在收盤價 ≤ 0 時回 null）或 F-2 排進開發，取代 D-6。
- **風控**：判定 high 項要不要提前告知；判定 D-5、D-6 的替代做法（以畫面上的 (b) 作為 ADR-0017 待決點 2 的等價觀察；以 T-3／F-2 取代 F-3）能不能接受。
- **CEO**：本件沒有需要決定或操作的事。

相關路徑：
- /home/user/AICompany/work/reviews/2026-11-22-補普查標註定稿R0-2另案揭露句方向與PSReadLine更正RC548至RC560-風控.md
- /home/user/AICompany/work/reviews/2026-11-22-dividends-sync揭露句查證-dev-lead.md
- /home/user/AICompany/work/dispatch/2026-10-08-CEO知悉簽核包-R0-2.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/work/reviews/2026-11-21-退役鏈同步衝突與claims註解裁示及補充十四-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-21-補充十四-待寫入-coordinator組版.md
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/docs/adr/0023-stock-desk-風險上限分子不完整時的非對稱判定通則.md
- /home/user/AICompany/docs/adr/0022-stock-desk-單一產業佔比上限在同產業或產業未知持股無法估值時的判定.md
- /home/user/AICompany/docs/adr/0015-stock-desk-匯率跨請求快取.md
- /home/user/AICompany/apps/stock-desk/backend/app/forecast/canonical.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/kelly_wording.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/keyLevels.ts
- /home/user/AICompany/apps/stock-desk/dev-up.bat
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md
- /home/user/AICompany/work/dispatch/2026-10-08-任務單-RK-4-匯率已換算卻無來源句的缺漏型揭露.md
- /home/user/AICompany/work/dispatch/2026-10-08-任務單-RK-5-fx_open來源未記錄與總覽匯率貢獻混源.md
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-F-1b-匯率非正值的估值防護.md
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-PR-0-決策卡第4條ATR回填繞過book層撤下.md
