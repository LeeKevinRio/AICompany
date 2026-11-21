# D-10 心跳責任確認書補正交件（tech-architect 修改清單 R1～R8）

- 撰寫者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

tech-architect 的 R1～R8 加上 G 的補充事實都已補進同一個檔 `/home/user/AICompany/work/reviews/2026-11-21-D-10心跳責任確認-devops-sre.md`，只改這一個檔，沒有 commit，沒有讀 `.env`（含 `.env.example`），沒有碰 `backend/data/`，沒有執行 `.bat`。
- 我對照了 `dev-up.bat`，事實與 tech-architect 的說法一致，沒有與它不符之處，所以沒有項目需要保留原文或標待複核。
- 有兩處是我自己多寫的，請 coordinator 核對 diff 時留意：
  - D 的來路多寫了「`[FAILED] Scheduler is still running`」與「port 在回答 Y 後仍被占用」，兩者都在 `ensure_scheduler_free` 或 `ensure_port_free` 內以 `exit /b 1` 結束，舊 scheduler 留著。
  - (五) 第 2 點註明：B 屬重啟有效，但不在風控 R2 訊息列的三種情形（舊 scheduler 還在跑、執行卡住、checkout 未更新）之內，所以不自行擴大使用。這一點建議請風控確認 B 要不要納入。

## 各部門回報（逐項改在哪一節）

**檔頭與依據**
- 保留 M1～M8 的修訂紀錄，新增一行：2026-11-21 經 tech-architect 複核（出處為複核報告檔名），其 R1～R8 已補。
- 該行並註明：文內 R1、R2 指 tech-architect 的修改清單，風控的兩則重啟請求稱「風控的 R1 訊息」「風控的 R2 訊息」，兩者不同。
- 依據清單新增風控 RC-407～RC-414 與 tech-architect 複核報告兩項。

**R1（第 2 節（五）第 4 點）**
- 改寫為引用風控報告與 RC-412 的條件，不抄訊息字面。
- 風控的 R2 訊息須由我在當天書面回覆寫明「需要 CEO 重新執行 `dev-up.bat`」，並標出是舊 scheduler 還在跑、執行卡住、checkout 未更新的哪一種。
- 不得用於 `gate_closed` 與 `STOCK_DESK_DB_PATH` refusal，也不得用於原因未明而只是想試試看。
- 同一事件至多一次；送過之後下一份有效貼回仍相同就轉 tech-architect。
- 不得與 L、H、U 系列同一則；決定送風控的 R2 訊息時，不送 L1。
- 另註明「避開時段」那一句尚待 tech-architect 書面確認（RC-414）。
- 其他情形照補充十三第 4 點 (f)。

**R2（第 2 節（六）第 7 項）**
- 拆成 (a)「有開著」的缺陷調查，與 (b)「原因未明、依 (四) 須轉送」。
- (b) 款含連續兩次原因未明、「漏記（尚未開始記錄）」、同一次已達 5 個以上平日。

**R3（「中斷後沒有後續執行」一段）**
- 原因補上持續多晚的 C1、之後卡在 `begin_run` 之前的執行，以及卡在 `begin_run` 之後的執行與 C2。
- 另加三句：D 不適用；C2 表示那筆沒有 end 列的執行之後環境或主 DB 有變動，疑似主 DB 被移動、替換或 schema 不見時依 (六) 第 4 項當天轉 tech-architect；同一份貼回若另依補充十三第 2 點 (b) 列出日期，L2 照漏記的條件判斷。

**R4（第 2 節（二）的 B 列與 D 列，以及（五）第 2 點）**
- 對照 `dev-up.bat` 行號：
  - 屬 D（在 123 行 `call :ensure_scheduler_free` 之前結束）：缺工具 51～53，不是 git repo 61～65，tracked 變更 70～73，切換分支 79～88，`git pull` 失敗 110～113，port 提示回答 N 或遇到 PID 4 在 119～122 與 252～260，Y 之後 port 仍被占用 265～267。
  - `ensure_scheduler_free`（283～302）內回答 N 或停不掉，也屬 D。
  - 屬 B（舊 scheduler 已停、新的沒啟動）：`uv sync` 130～135，`npm install` 139～144，backend 健康檢查逾時 159／200～203。
- 這份行號讀的是 product 現行版。

**R5**
- tech-architect 指的第 253 行附近已被 R1 的重寫取代，現在已無「請 CEO 不要自己重新啟動任何程式」的引號字面，改為不加引號的描述（既有訊息含有要求 CEO 不要自己重新啟動程式的意旨）。

**R6（第 2 節（三）(c) 第 5 步）**
- 「只有改變開關機習慣才能根本改善」改為只適用主機沒開（A）。
- 睡眠（G）另有處理空間，但屬 ADR-0030 補充九第 7 點 (d) 的事項，由 tech-architect 另案處理，不屬我部門自行處理的範圍。
- 發現一律依 (六) 第 8 項轉 tech-architect，只陳述事實，不提建議。

**R7（第 2 節（四）的例外 (2)）**
- 註明「5 個以上平日」以 coordinator 比對紀錄為準，我不自己相加（RC-364 (b)(c)）。

**R8（第 2 節（二）「中斷的執行」）**
- 補「CEO 執行報告的當下剛好有一次執行正在進行」。
- 「睡眠」改標「推論」，註明睡眠只讓程序暫停，本身不一定使那一次沒有 end 列。

**G 的補充事實（第 2 節（二）表後）**
- 照 tech-architect 裁示寫入以下幾點：
  - 不設 `misfire_grace_time` 是補充九第 7 點 (d) 明文決定的。
  - 喚醒不是啟動，不會觸發補跑。
  - 同時跨過 22:10 與 23:10 時那一晚沒有任何執行。
  - 由 tech-architect 另案以 ADR-0030 補充處理，不是接線前置，依補充十三第 4 點 (g) 不得由心跳升級觸發。

## 驗證

- 讀過：tech-architect 複核報告第一件全文、風控報告 RC-407～RC-414、`apps/stock-desk/dev-up.bat` 28～302 行。
- 檢查過檔頭 1～9 行，修訂紀錄兩行並存，格式正確。
- 全文仍無對 CEO 說的字面、模型名稱與祕密。
- 第 6 節「沒有查證的事」新增三項：
  - 3c：風控的 R1、R2 訊息字面未抄，「避開時段」尚待 tech-architect 確認。
  - 3d：`.env.example` 是否含 `STOCK_DESK_DB_PATH` 列為「未查證（權限不允許讀取）」。
  - 3e：`dev-up.bat` 行號只讀 product 現行版，未與接線版與改字分支逐行比對。

## 下一步

1. coordinator 逐項核對 diff，確認後 commit。commit 須早於接線 PR 的合併 commit（補充十三第 7 點 (c)）。
2. 請風控確認 B（`dev-up.bat` 在停舊 scheduler 之後失敗）要不要納入風控 R2 訊息的情形。
3. tech-architect 書面確認兩則請求裡的「避開時段」那一句。
