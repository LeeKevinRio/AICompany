# R14～R16 改寫（配合 product 線不用 GitHub PR 的流程事實）

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：R14～R16 改寫（配合「product 線不用 GitHub PR」的流程事實）

## 一、本次結論

- **我採 (a)：證據改用現行流程裡實際存在的 git 紀錄，不採 (b)（日後一律走 GitHub PR）。**
- **(a) 不需要 CEO 決定。** 誰做什麼、做的先後都沒有改，改的只有三件事：
  - 舉證改用哪些資料；
  - coordinator 合入指令的參數，由分支名改成 40 碼；
  - 交件紀錄要多寫哪些內容。
- **(b) 是流程改變，要 CEO 決定。** 本案不建議採用，理由見方案比較。
- **R14（C9 (b)）：以內容雜湊確立先後，不再依賴 PR 建立時間。**
  - 審查紀錄所在的 commit 記為 `<R>`。三份紀錄（補充、送審紀錄、審查紀錄）都要在 `<R>` 的 tree 裡，且 blob 雜湊和讀取當下的 remote 版本相同。
  - `<R>` 要在 `refs/remotes/origin/product/stock-desk` 上可達，並以 `git ls-remote` 對照伺服器端的值。
  - `<R>` 必須是交件紀錄首版 commit `<D>` 的祖先，也必須是受審對象 `<head>` 的祖先。commit SHA 由內容和 parent 決定，所以 `<head>` 不可能在 `<R>` 之前產生。qa 審的就是 `<head>`，因此 qa 的審查必然晚於這份審查紀錄。
  - 「PR 說明的編輯歷史」改為：交件紀錄路徑在 product 上的 git 歷史。
  - 獨立性改為引用 R16 的版本。
- **R13（γ）已依流程事實改寫：** 沒有 PR 物件可讀，改由 (ii) 的執行者以 `git ls-remote origin refs/heads/<分支名>` 直接向 origin 讀。上一輪已確認的寫法因此重新標為［待風控確認］。
- **R15（合入綁定）：**
  - 合入者 merge 時直接寫 `<head>` 的 40 碼，第二個 parent 就由指令決定。現行流程是本機 merge，不經過 GitHub 合入 API，所以不需要查 API 的參數。
  - **核對要在 push 之前做一次，push 之後再做一次。** 理由是 CEO 以 dev-up 拉 product 就等於部署，push 之後才核對，發現時可能已經部署。
  - 不相等時，分「push 之前」與「push 之後」兩種處理；push 之後發現才算事件。
  - 退路要以 devops-sre 的書面查證為前提，並揭露殘留。
  - 合入者的角色、指令原文與輸出，都記入同一份審查紀錄。
- **R16：獨立性改以角色判定。** 舉證有兩個來源：coordinator 的派工紀錄，以及提交角色自己的交件紀錄。以 git 作者和 `Co-Authored-By` 判定的寫法全部刪除，殘留已揭露。
- **要先揭露的四件事：**
  1. **N-199 偵測工具的合入和你提供的事實不一致。** 追蹤清單 :407 記載：完整 CI 跑在 119988f；重新 merge 後推上 product 的是 f589be8，兩者只比對了 `apps/`、`scripts/`、`.claude/`、`.github/` 四個目錄。這和「對該 merge commit 跑完整 CI」不同。我不追溯判定，只在 R15 (2) 訂了往後的規則［待風控確認］，要不要回頭看由風控決定。
  2. **推上 product 就可能等於部署**（追蹤清單 :409，coordinator 定案）。所以 R15 把主要閘門放在 push 之前。
  3. **product 禁止 force push 只有規範依據**（`.claude/agents/devops-sre.md:54`、`.claude/commands/sync-main.md:29`；CLAUDE.md §3 只明寫 main）。伺服器端有沒有強制，我沒有查證，要 devops-sre 書面查證，結果列為殘留。
  4. **這個 checkout 的 `docs/adr/` 下沒有 0042**（Glob 只找到 0040、0041）。tech-writer 可能還沒落檔，或在別的 worktree 落檔。下面的段落都以區塊 D 的落檔版為準。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 評估摘要
- **採用：**
  - (a) 以 git 紀錄舉證；
  - R14 用「`<R>` 是 `<D>` 與 `<head>` 的祖先」確立先後；
  - (γ) 改用 `git ls-remote`；
  - 以 40 碼 merge，並在 push 前、push 後各核對一次；
  - 獨立性以角色判定，兩個來源互核。
- **否決：**
  - (b) 本案改走 GitHub PR；
  - 只用「`<R>` 是 `<D>` 的祖先」單獨舉證：`<D>` 何時 commit 由 coordinator 決定，舉證力比原設計弱；
  - 要求 N-198 每個 commit 都以 `<R>` 為祖先：會把限制從「延後送審」擴大成「延後開工」；
  - 改為每個角色設定不同的 git 身分：身分一樣是自己設定的，舉證力沒有增加。

#### 方案比較

| 議題 | 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| 流程 | (a) 改用現行流程的 git 紀錄 | 不改流程，不會拖到 N-198 的第三包期限；commit 由內容決定，可篡改的空間比伺服器時間更小 | 「送審」的時點由 coordinator 記錄，git 證明不了 | 低（已揭露） | **採用** |
| | (b) 日後一律走 GitHub PR | 有伺服器記錄的建立時間與編輯歷史 | 屬流程改變，要 CEO 決定；devops-sre 要另外建置 branch protection 和執行者的讀取方式；qa 仍然讀不到 GitHub，一樣要轉錄；N-198 會多一個前置條件 | 中（時程） | 否決（本案） |
| R14 的錨點 | A1：`<R>` 是 `<D>`（交件紀錄首版）的祖先 | 對應「PR 建立」 | `<D>` 何時 commit 由 coordinator 控制 | 中 | 只作為 (2) 的對應，不單獨使用 |
| | A2：`<base>..<head>` 範圍內每個 commit 都以 `<R>` 為祖先 | 最強 | 等於延後開工，超出 R10「只延後送審」的本意 | 中（時程） | 否決 |
| | A3：`<R>` 是 `<head>` 的祖先 | 無法偽造；`<head>` 就是 qa 審的 commit，正好對應「審查紀錄早於受審對象」；和 C7「合入前 merge 最新 product」同方向 | 允許 `<R>` 之前的舊 head 送審過；但依 1.7，那些審查已經作廢 | 低 | **採用，和 A1 併用** |
| (γ) | `git ls-remote` 直接讀伺服器端的 ref | 不依賴本機的 remote-tracking ref；唯讀；不新增唯讀角色的 Bash | 和 (β) 是同一個執行者 | 低 | **採用** |
| | 刪除 (γ)，只留三個值 | 簡單 | 少了一個不依賴本機狀態的來源 | 中 | 否決 |
| 獨立性 | 以角色判定：派工紀錄加上交件紀錄 | 判定得出來 | 靠自述與轉存 | 中（已揭露） | **採用** |
| | git 作者或 `Co-Authored-By` | — | 所有 agent 都是同一個身分，判定不出來 | 高 | 刪除 |

#### 區塊 E：ADR-0042 修改段落

**E-1　新增：檔頭「程式位置」那一點之後新增一點**（配合流程事實；［待風控確認］）

````markdown
- 流程名詞：product 線目前不使用 GitHub PR。本 ADR 中的「PR」「PR 說明」「PR 開出／建立」「PR 分支」「PR head」，依 [TA-177S] 修訂八第 0 節的對照表讀。
````

**E-2　取代：N198-C9 的 (b) 全部，包括「［待風控確認］執行方式（TA 補）」整項；(c) 不變**（R14）

````markdown
       - (b) 補充送達風控，以及風控對補充的審查紀錄，都必須早於 N-198 送審，不得事後補。「送審」依 [TA-177S] 修訂八第 0 節，指該版交件紀錄首次出現在 `origin/product/stock-desk` 上。舉證方式如下，全部都要成立（[風控-ADR42 回審] R10；[風控-ADR42 回審二] R14）：
         - (1) 風控對該補充的審查紀錄，在 N-198 送審之前已經存在於 `work/reviews/`，而且在 (ii) 讀取當下，在 `refs/remotes/origin/product/stock-desk` 上可達。也就是說，(c) 的「審查紀錄存在」提前到送審之前。（「已 push」依 [風控-ADR42 回審二] 第二節第 2 點 (3) 降為「讀取當下可達」。）
         - (2) N-198 的交件紀錄在**首版**就要列出三個路徑：補充、coordinator 的送審紀錄、風控的審查紀錄；另外要列出 (6) 的 `<R>`，寫完整 40 碼。qa 依交件紀錄路徑在 `origin/product/stock-desk` 上的 git 歷史判定：這些引用若是首版之後才補上的，就判 BLOCKING。
         - (3) 送審紀錄要記到分鐘，並註明時區（Asia/Taipei）。
         - (4) 先後無法確立，就判 BLOCKING。例如：只有日期、時區不明、紀錄缺漏，或任一條指令沒有原文、沒有完整輸出、沒有 `exit=` 行。
         - (5) 風控在 risk-gate 核對 (1)～(3) 與 (6) 的紀錄。
         - (6) 以內容雜湊確立先後。現行流程沒有 PR，所以不以 PR 建立時間為錨點。
           - 名詞：
             - `<R>`：風控審查紀錄所在的 commit，完整 40 碼，由交件紀錄首版列出。
             - `<D>`：交件紀錄路徑首次出現在 `origin/product/stock-desk` 的那個 commit，完整 40 碼。
             - `<head>`：同 [TA-177S] 修訂六 1.1。
           - (6a) 證明 `<R>` 的 tree 含有三份紀錄：
             - 原樣貼出 `<R>` 的 tree 中，(2) 列出的三個路徑各自的項目，包括 blob 雜湊。
             - 任一路徑不在 `<R>` 的 tree 中，就判 BLOCKING。
           - (6b) 證明紀錄沒有事後改寫：
             - 同一份紀錄再貼出這三個路徑在 (ii) 讀取當下、`refs/remotes/origin/product/stock-desk` 版本的 blob 雜湊。
             - 任一路徑的兩個雜湊不同，就判 BLOCKING：這表示該紀錄在 `<R>` 之後被改寫過。
             - 因此這三份紀錄在 `<R>` 之後都不得再修改，coordinator 的補記也一樣，要補記就另開檔案。
             - coordinator 的送審紀錄必須是本次送審專用的獨立檔案，不得是會持續更新的檔案（例如追蹤清單）。
           - (6c) 證明 `<R>` 在 product 上可達：
             - `git merge-base --is-ancestor <R> refs/remotes/origin/product/stock-desk`，結果必須是 `exit=0`。
             - 另外貼出 `git ls-remote origin refs/heads/product/stock-desk` 的輸出。它的值必須等於讀取當下本機 `refs/remotes/origin/product/stock-desk` 的值；不等就重做 (6c)。
             - 只接受 `product/stock-desk`。審查紀錄在產品線上；`main` 依 CLAUDE.md §1 不放產品內容，不適用。
           - (6d) 證明 `<R>` 早於送審，也早於受審對象：
             - `git merge-base --is-ancestor <R> <D>`，結果必須是 `exit=0`；
             - `git merge-base --is-ancestor <R> <head>`，結果必須是 `exit=0`。
             - 理由：commit SHA 由內容與 parent 決定，以 `<R>` 為祖先的 commit，不可能在 `<R>` 之前算出來。qa 審的就是 `<head>`（[TA-177S] 修訂八第 1 節，四個值相等），所以 qa 的審查必然晚於這份審查紀錄。
             - 第二條實際上要求：N-198 分支在送審之前，已經 merge 過含有 `<R>` 的 product。這和 C7「合入前 merge 最新 product」同方向，不會延後開工。
           - (6e) 交件紀錄的歷史：
             - 貼出交件紀錄路徑在 `origin/product/stock-desk` 上的完整 commit 歷史，每一筆都寫完整 40 碼，並貼出首版之後每一筆對該檔的 diff。歷史只有一筆，就表示「沒有任何編輯」。
             - 依 [TA-177S] 修訂六 1.7 重新送審時，每一版新的交件紀錄都各自適用 (2) 與 (6d)。
           - 時間的交叉核對：
             - 送審紀錄所載的送達時間（到分鐘，Asia/Taipei），必須早於 coordinator 派工紀錄所載「N-198 送 qa 審查」的時間所在的那一分鐘。落在同一分鐘或更晚，依 (4) 判 BLOCKING。
             - 這兩個時間都由 coordinator 記錄，只用來抓出錯誤，不是先後的主要證據；主要證據是 (6d)。
           - 執行與判斷分離（ADR-0007）：
             - qa-reviewer 的工具是 Read、Grep、Glob、`codex`、`git diff`，不為此新增工具。
             - (6a)～(6e) 由 [TA-177S] 修訂六 1.3 (ii) 的執行者執行。指令原文與完整輸出原樣記入 `work/reviews/` 的本案審查紀錄，每條都附 `exit=` 行，並記錄讀取時間（到分鐘，Asia/Taipei）。
             - 只用唯讀的 git 查詢，實際指令由 devops-sre 指定；本 ADR 只訂要證明的事。
             - 獨立性依 [TA-177S] 修訂八第 2 節，以角色判定。
             - qa 與風控讀這份紀錄判定。
           - 殘留：
             - 證明不了 push 的時點，只證明 `<R>` 早於 `<D>` 與 `<head>`，而且讀取當下在 product 上可達。這一項 [風控-ADR42 回審二] 第二節第 2 點 (3) 已接受。
             - `<D>` 何時 push、qa 何時被派工，都由 coordinator 記錄，git 證明不了。(6d) 的第二條不受影響。
             - `product/stock-desk` 禁止 force push 是公司規範；伺服器端有沒有強制，待 devops-sre 書面查證。沒有強制時，(6c) 只證明讀取當下可達。
             - qa 無法親自重現，與 [TA-177S] 修訂六 1.8 的殘留相同。
````

**E-3　取代：「先後與相依」第 2 點的第 2 小點（A-8 版本）**（隨 R14）

````markdown
     - 這份補充必須在 **N-198 送審之前**送到風控。風控對它的審查紀錄，也要在送審之前已經存在，並在 `origin/product/stock-desk` 上可達，不得事後補。「送審」的定義與舉證都依 N198-C9 (b)。這只會延後送審的時間：N-198 分支要先 merge 含有該審查紀錄的 product。不會延後合入（[風控-ADR42 回審] 第二節第 1 點）。
````

#### 區塊 F：修訂八修改段落（附到規格檔末的版本）

**F-0　取代：修訂八檔頭的三行**

````markdown
## 修訂八（tech-architect，2026-11-07；回應 [風控-ADR42 回審] R13、S7，以及 [風控-ADR42 回審二] R15、R16）

- 依據：[風控-ADR42 回審] `work/reviews/2026-11-07-ADR0042修正版與N199第5節回審-風控.md`；[風控-ADR42 回審二] `work/reviews/2026-11-07-ADR0042修正版二與修訂八回審-風控.md`。
- 本修訂只取代下面點名的段落，其餘維持修訂六、修訂七。取代範圍：
  - 修訂七第 2 節全文；
  - 修訂七第 4 節第 3 點的首行；
  - 修訂六 1.3 末段的執行者聲明；
  - 修訂六 1.4 全文。
- 第 0 節，以及第 1 節中標「配合流程事實」的部分：風控確認 R13 之後，我依 coordinator 提供的流程事實改寫。［待風控確認］
````

**F-1　新增：修訂八第 0 節**（配合流程事實；［待風控確認］）

````markdown
### 0. 流程名詞的對照（配合流程事實）
- 事實（coordinator 提供）：product 線目前不使用 GitHub PR。一張單的合入流程是：
  1. dev-lead 把分支 push 到 origin；
  2. qa-reviewer 讀 `git diff` 審查；
  3. coordinator 在本機或 scratchpad worktree 以 `git merge --no-ff -F <訊息檔>` 產生 merge commit，對它跑完整 CI，全綠後以 fast-forward push 到 `origin/product/stock-desk`。
- 本規格（修訂一起）與 ADR-0042 中的下列詞，依此表讀：

| 原詞 | 現行流程的對應 |
|---|---|
| PR | 一次送審：dev-lead 推到 origin 的分支，加上該次的交件紀錄 |
| PR 分支名、`<PR 分支名>` | 交件紀錄所寫的分支名（`refs/heads/` 之後的部分），下文寫作 `<分支名>` |
| PR 說明 | dev-lead 的交件紀錄（`work/reviews/` 下，coordinator 逐字轉存）。修訂六 1.2 的 (i)、N198-C8 的修改清單、N198-T1 的效力證明都附在這裡 |
| PR 建立、PR 開出 | 送審：該版交件紀錄首次出現在 `origin/product/stock-desk` 的 commit（`<D>`） |
| PR 說明的編輯歷史 | 交件紀錄路徑在 `origin/product/stock-desk` 上的 git 歷史 |
| PR 的 head | 該版交件紀錄所寫的 head（完整 40 碼）；由第 1 節第 6 點和 `<head>` 核對 |
| PR 的 base 分支 | 固定是 `product/stock-desk` |
| 合入 PR | 依第 1 節「合入綁定」產生 merge commit，並以 fast-forward push |
| PR 作者、共同作者 | 在 `<base>..<head>` 範圍內下 git commit 的角色，依第 2 節判定 |

- 交件紀錄：
  - 每一版都要寫：分支名、head 的完整 40 碼、本角色在 `<base>..<head>` 範圍內下的每個 commit（完整 40 碼）。
  - 送 qa 審查之前，先 push 到 `origin/product/stock-desk`。coordinator 在派工紀錄中記錄送 qa 審查的時間（到分鐘，Asia/Taipei）。
  - 首版之後不修改，要補充就另開檔案；head 變動而重新送審時，另開一版新的交件紀錄。
- 日後若改用 GitHub PR，屬流程改變，要 CEO 決定；屆時本表作廢，由 TA 另出修訂。
````

**F-2　取代：修訂八第 1 節，從開頭到「理由（照舊）」為止**（四值相等的規則不變；(γ) 配合流程事實改寫，取代 R13 版本；［待風控確認］）

````markdown
### 1. head SHA 的對照與合入綁定（取代修訂七第 2 節全文）
- 修訂六 1.5 新增第 6 點（全部都要成立；不成立就判 BLOCKING）：
  - 6. 以下四個值都是完整 40 碼，而且必須完全相同；交件紀錄所寫的 head 也必須等於它們。任何兩者不同，就判 BLOCKING：
    - (α) (i) 紀錄中的 `<head>`（`git rev-parse HEAD`）；
    - (β) (ii) 紀錄中的 `<head>`（在 (ii) 的 `git fetch` 之後，`git rev-parse origin/<分支名>`）；
    - (γ) ［配合流程事實改寫］origin 伺服器端的分支 ref：由 (ii) 的執行者以 `git ls-remote` 直接向 origin 讀出 `refs/heads/<分支名>` 的值；
    - (δ) qa 實際審查的 commit：qa 審查這一單時，所下 `git diff` 指令的 head 端一律寫完整 40 碼，不得寫分支名或 `HEAD`，並在審查報告中列出這個值。
- **(γ) 的取得（配合流程事實，取代上一版「PR 物件的 head SHA」）：**
  - 原因：沒有 PR 物件。現行流程中，伺服器端唯一記錄「送審分支當下 tip」的，是 origin 上的 `refs/heads/<分支名>`。
  - 和 (β) 的差別：`git ls-remote` 直接向 origin 讀，不經過本機的 remote-tracking ref；(β) 則依賴本機 fetch 的結果。
  - 候選指令如下，由 devops-sre 查證定稿：
    ```bash
    git ls-remote origin refs/heads/<branch> refs/heads/product/stock-desk; echo "exit=$?"
    ```
  - 原樣貼出：指令原文、完整輸出、`exit=` 行、讀取時間（到分鐘，Asia/Taipei）。
  - 附加核對（取代「head／base 分支名」）：
    - 輸出中屬於送審分支的列恰好一列，ref 名正好是 `refs/heads/<分支名>`，而且 `<分支名>` 等於交件紀錄所寫的分支名。不符就判 BLOCKING：讀到的是另一個分支。
    - `refs/heads/product/stock-desk` 的值，必須等於 (ii) 的 `<tip>`。不等，表示 fetch 與讀取之間 product 有新的 push，(ii) 重做。
  - 時點：(γ) 在 (ii) 的 `git fetch` 之後讀。(γ) 和 (β) 不同，通常表示兩次讀取之間分支有新的 push，依 1.7 全部重做。
- 不新增 Bash：(γ) 由 (ii) 的執行者取得，qa 只讀紀錄；(δ) 是 qa 自己所下 `git diff` 的參數。`READONLY_ALLOWED_BASH` 不變。
- 殘留：(γ) 和 (ii) 一樣經過執行者轉錄，qa 無法親自重現，與修訂六 1.8 登錄的殘留相同。
- 理由（照舊）：1.5 第 4 點的 `git diff --stat` 輸出為空，只代表兩者的 tree 相同，不代表是同一個 commit。同一個 tree 的另一個 commit（例如 rebase 之後的、或空 commit），祖先關係可能不同，(i)、(ii) 的 ancestry 判定就不適用於它。
````

**F-3　取代：修訂八第 1 節「［待風控確認］合入綁定 `<head>`（TA 補）」整項**（R15；配合流程事實）

````markdown
- **合入綁定 `<head>`（[風控-ADR42 回審二] R15）：**
  - (1) 綁定方式：
    - 合入者 merge 時，對象直接寫 `<head>` 的完整 40 碼。不得寫分支名、`origin/<分支名>`、`FETCH_HEAD`，或任何會隨 push 變動的名稱。
    - merge 前 checkout 的必須是 `<tip_m>`：合入者在 merge 之前 fetch 得到的 `refs/remotes/origin/product/stock-desk`，完整 40 碼。
    - 這樣 merge commit `<M>` 的第二個 parent 由指令決定，不受「qa 給 PASS 之後分支又有 push」影響。
    - 現行流程是本機 merge，不經過 GitHub 合入 API，所以上一版「API 的 head 綁定參數」作廢，不需要查證。
  - (2) push 之前的核對（主要閘門）：
    - 理由：CEO 以 dev-up 拉 product 就等於部署（追蹤清單 N-195 審查那一列），push 之後才核對，發現時可能已經部署。
    - 由合入者在 `<M>` 上核對，以下全部成立才可以 push：
      - `<M>` 恰好有兩個 parent；
      - 第一個 parent 等於 `<tip_m>`；
      - 第二個 parent 等於 `<head>`。
    - 完整 CI 的對象就是 `<M>`。若 push 被拒而重新 merge，得到 `<M′>`：對 `<M′>` 重新核對上面三項，並重跑完整 CI。
      - ［TA 補，待風控確認］例外：devops-sre 書面列出完整 CI 會讀取的路徑，而 `<M>` 與 `<M′>` 在這些路徑上的 tree 雜湊逐一相同時，可以沿用 `<M>` 的 CI 結果。兩組 tree 雜湊都要原樣記錄。只比對其中幾個目錄的 `git diff`，不符合這個例外。
    - push 只能是 fast-forward：不得帶 `--force` 或 `--force-with-lease`，refspec 也不得加 `+`。被拒時依上一點重做，不得改用強制推送。
  - (3) push 之後的核對（[風控-ADR42 回審二] R15 (a)；兩條路徑都要做）：
    - 由 (ii) 的執行者 fetch 之後，以唯讀的 git 查詢記錄下面兩項：
      - `refs/remotes/origin/product/stock-desk`，以及 `git ls-remote origin refs/heads/product/stock-desk` 的值：必須等於 `<M>`。若期間又有新的 push，改為記錄新值，並記錄 `git merge-base --is-ancestor <M> refs/remotes/origin/product/stock-desk`，結果必須是 `exit=0`。
      - `<M>` 的完整 40 碼及其第二個 parent：第二個 parent 必須等於 `<head>`。
    - C7、N196-C8、N197a-C8 都要求以 merge commit 合入，所以第二個 parent 一定查得到。查不到（例如被 fast-forward 合入），也依 (4) 視為事件。
  - (4) 不相等時：
    - **在 push 之前發現：** 不得 push。丟棄 `<M>`，記錄下來，依 (1) 重做。這不算事件，但要記入同一份審查紀錄。
    - **在 push 之後發現（屬事件）：** 已經合入了未經審查的內容。
      - coordinator 立即回報風控與 CEO，並請 CEO 在處理完成之前不要 pull product、不要執行 dev-up。CEO 若已經拉取，要讓他知道本機正在執行未經審查的版本。
      - 不得 force push，不得 reset product。
      - 處理方式（TA 訂）：
        - (i) 第二個 parent 以 `<head>` 為祖先，也就是 qa 給 PASS 之後分支上的新 commit 被一起合入：預設補審。
          - qa 審 `git diff <head> <M 的第二個 parent>` 的全部內容，加上 Codex 第二意見；風控在 risk-gate 核對。兩者都通過才結案。
          - 補審判 BLOCKING 時，改走 (ii)。
        - (ii) 其他情形（例如合入的是另一個分支或改寫過的歷史），或補審不通過：
          - 以 `git revert -m 1 <M>` 產生新的 commit，依 (2) 跑完整 CI，再以 fast-forward push。
          - 之後要合入正確的 `<head>` 時，修訂六 1.2～1.7 與本節全部重做。
          - 若被 revert 的內容與要重新合入的分支有共同的 commit，git 不會再次帶入它們。遇到這種情形先回 TA，依當時的拓撲裁示，不得自行處理。
      - 處理完成之前不部署；ADR-0041:114 的補註與 R-6′ 的已修正註記也不落檔。
  - (5) 退路（[風控-ADR42 回審二] R15 (b)）：
    - 前提：devops-sre 書面查證「無法以 40 碼指定 merge 對象」，查證紀錄放在 `work/`，寫明原因。沒有這份紀錄，不得走退路。
    - 做法：merge 之前，由 (ii) 的執行者再讀一次 (γ)，必須等於 `<head>`，不等就不得 merge。merge 之後仍要做 (2) 和 (3)。
    - 殘留揭露：讀取 (γ) 與 merge 之間仍有窗口，分支可能在這段時間被 push。
      - 現行流程是本機 merge，(2) 的 push 前核對會在 push 之前擋下這種情況。
      - 日後若改在無法於 push 之前核對的環境合入（例如伺服器端合入），這個窗口只能靠 (3) 事後補抓，而那時可能已經部署。
  - (6) 紀錄（[風控-ADR42 回審二] R15 (c)）：
    - 合入者只能是 (ii) 的執行者，或者會把下面各項記入同一份審查紀錄的角色。無法留下紀錄的角色不得合入。
    - 合入者不是 (ii) 的執行者時，(3) 仍由 (ii) 的執行者做。
    - `work/reviews/` 的本案審查紀錄要記下：
      - 合入者的角色；
      - merge 所在的位置（本機 checkout 或 scratchpad worktree 的路徑）；
      - `<tip_m>`、`<head>`、`<M>`，都是完整 40 碼；
      - merge、核對、CI、push 的每一條指令原文與完整輸出，每條附 `exit=` 行；
      - merge 訊息檔的內容；
      - 時間（到分鐘，Asia/Taipei）。
    - 實際指令由 devops-sre 指定，只用於非唯讀的執行者。
  - 理由：第 6 點只保證 qa 給 PASS 的那一刻 tip 等於 `<head>`。以 40 碼 merge，加上 push 前的核對，才能保證合入的就是 qa 審過的 commit。
````

（第 1 節其餘兩行不變：「修訂六 1.7 的重做清單，加上 1.5 第 6 點（包括 (γ)）」、「適用於 N196-C8、N197a-C8，以及 ADR-0042 的 N198-C7」。）

**F-4　取代：修訂八第 2 節全文**（R16）

````markdown
### 2. 執行者的獨立性（取代修訂六 1.3 末段的執行者聲明，以及 1.4 全文；[風控-ADR42 回審二] R16）
- 以「角色」判定：
  - 角色指 `.claude/agents/` 定義的 agent 名稱（例如 dev-lead、devops-sre），以及 coordinator。同一角色的不同次派工，都視為同一角色。
  - 不以 git 的 author、committer 或 `Co-Authored-By` 判定。理由：本 checkout 的 reflog 身分一律是 `Claude <noreply@anthropic.com>`，各 agent 的 `Co-Authored-By` 也都是同一個模型標記，git metadata 分不出角色。
- 修訂六 1.3 末段的聲明，改為：
  - (ii) 紀錄寫明執行者的角色，並聲明：本角色不是 (i) 的執行角色，也不是 `<base>..<head>` 範圍內任何 commit 的提交角色。
- 修訂六 1.4 改為：
  - (1) 角色舉證：coordinator 在 `work/` 下的派工紀錄要逐一列出以下各項，(ii) 紀錄要寫明這份派工紀錄的路徑：
    - `<base>..<head>` 範圍內的每個 commit（完整 40 碼）是在哪個角色的派工下 commit 的，並註明出處，也就是該角色交件紀錄的路徑；
    - (i) 的執行角色；
    - (ii) 的執行角色；
    - 合入者的角色（第 1 節「合入綁定」(6)）。
  - (2) 第二來源：每個 commit 的 40 碼，都必須出現在派工紀錄所註明的那份交件紀錄中（第 0 節：交件紀錄要列出本角色下的每個 commit）。
  - (3) commit 清單互核，作用是綁定內容：(i)、(ii) 兩份紀錄都原樣貼出 `<base>..<head>` 範圍內每個 commit 的完整 40 碼。只用唯讀的 git 查詢，實際指令由 devops-sre 指定。不貼作者，也不貼 `Co-Authored-By`。
  - (4) qa 讀紀錄判定，以下任一項成立就判 BLOCKING：
    - (i)、(ii) 兩份清單不一致，或者和派工紀錄列出的 commit 集合不一致；
    - 有 commit 在派工紀錄中沒有提交角色，或者在註明的交件紀錄中找不到；
    - (ii) 的執行角色等於 (i) 的執行角色，或者是任何一個 commit 的提交角色；
    - 派工紀錄缺漏，或 (ii) 紀錄沒有寫角色、沒有聲明。
  - 本修訂之前已經做成的 (ii) 紀錄，要補上角色聲明與派工紀錄才可以判定；不補就判 BLOCKING。
- 殘留（揭露）：
  - git metadata 證明不了角色。獨立性只靠三份資料：coordinator 的派工紀錄、提交角色的交件紀錄、(ii) 執行者的自我聲明。
  - 這三份都由 coordinator 轉存。coordinator 自己擔任 (ii) 的執行者時，派工紀錄中關於 (ii) 的那一列，是 coordinator 對自己的陳述。
  - 建議（不擋）：由 devops-sre 擔任 (ii) 的執行者，讓派工者和查核者分開。
- 適用於 N196-C8、N197a-C8，以及 ADR-0042 的 N198-C7。
````

**F-5　取代：修訂八第 4 節的索引**

````markdown
| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 0 | 本修訂第 0 節（新增） | 流程名詞對照；交件紀錄的應記事項 | 配合流程事實 |
| 1 | 修訂七第 2 節 → 本修訂第 1 節 | 四值相等；(γ) 由「PR 物件的 head SHA」改為 `git ls-remote` | R13；配合流程事實改寫 |
| 2 | 本修訂第 1 節「合入綁定」 | 以 40 碼 merge；push 前、push 後各核對一次；事件處理；退路；紀錄 | R15 |
| 3 | 修訂六 1.3 的聲明與 1.4 → 本修訂第 2 節 | 以角色判定，兩個來源互核；清單只留 SHA | R16 |
| 4 | 修訂七第 4 節第 3 點 → 本修訂第 3 節 | 編號改為 N-200；先行條件與 qa 檢查 | S7（不變） |
````

#### 本輪修改處索引

| # | 位置 | 取代哪一段 | 性質 | 依據 |
|---|---|---|---|---|
| E-1 | ADR-0042 檔頭「程式位置」之後 | 新增 | 流程名詞指向修訂八第 0 節 | 配合流程事實，［待風控確認］ |
| E-2 | ADR-0042 N198-C9 (b) | (b) 全部，包括［待風控確認］執行方式；(c) 不變 | 錨點由 PR 建立改為送審 `<D>`；新增 (6a)～(6e)；(1) 依風控降為「讀取當下可達」；時間核對的錨點改用派工紀錄 | R14 |
| E-3 | ADR-0042「先後與相依」第 2 點第 2 小點 | A-8 的版本 | 「PR 開出」改為「送審」 | 隨 R14 |
| F-0 | 修訂八檔頭 | 檔頭三行 | 依據加入回審二；取代範圍加入修訂六 1.3 的聲明與 1.4 | R15、R16 |
| F-1 | 修訂八第 0 節 | 新增 | 名詞對照表 | 配合流程事實，［待風控確認］ |
| F-2 | 修訂八第 1 節 (γ) | R13 版 | 由 PR 物件改為 `git ls-remote` | 配合流程事實改寫 R13，［待風控確認］ |
| F-3 | 修訂八第 1 節「合入綁定」 | 上一版［待風控確認］整項 | 見 R15 | R15；(2) 的 CI 沿用例外是［TA 補，待風控確認］ |
| F-4 | 修訂八第 2 節 | 全文 | 以角色判定 | R16 |
| F-5 | 修訂八第 4 節 | 索引 | 更新 | — |

#### 對實作的約束（逐條可由 qa 檢查）
- N198-C9 (b)：
  - (6a)～(6e) 的每條指令都有原文、完整輸出與 `exit=`；
  - 三個路徑都在 `<R>` 的 tree 中，兩組 blob 雜湊逐一相同；
  - `<R>` 是 `refs/remotes/origin/product/stock-desk` 的祖先，也是 `<D>` 和 `<head>` 的祖先；
  - 交件紀錄首版已經列出三個路徑與 `<R>`。
- 修訂六 1.5 第 6 點：(α)～(δ) 與交件紀錄的 head 都相等；`ls-remote` 讀到的 ref 名與分支名相符。
- 合入：
  - merge 的對象是 40 碼；
  - push 前的三項核對都有紀錄；
  - CI 的對象是推上去的 `<M>`；
  - push 時沒有 force 參數；
  - push 後的核對由 (ii) 的執行者記錄；
  - 合入者的角色、指令原文、輸出、訊息檔都在同一份審查紀錄中。
- 獨立性：
  - 派工紀錄逐一列出每個 commit 的提交角色，以及 (i)、(ii)、合入者的角色；
  - 每個 commit 都能在交件紀錄中找到；
  - (ii) 的角色不在其中；
  - 判定不引用 git 作者或 `Co-Authored-By`。

### 其他部門
本輪沒有參與。

## 三、驗證

**讀過的文件：**
- `/home/user/AICompany/work/reviews/2026-11-07-ADR0042修正版二與修訂八回審-風控.md`，全文。
- `/home/user/AICompany/work/reviews/2026-11-07-ADR0042修正版二與修訂八-tech-architect.md`，全文（區塊 A～D、修訂八）。
- `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`：:2335-2443（修訂六 1.1～1.8）、:2657-2715（修訂七）。
- `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` :395-414：
  - :397，3985f4d；
  - :407，CI 跑在 119988f、推上去的是 f589be8，只比對四個目錄；
  - :409，CEO 拉 product 就等於部署。
- `/home/user/AICompany/work/reviews/2026-11-07-N195交件-dev-lead.md` :1-30：交件紀錄目前的格式，head 寫 40 碼，commit 只寫短碼。
- `/home/user/AICompany/.git/HEAD`：主 checkout 在 `product/stock-desk`。
- 以 grep 查 force push 規範：CLAUDE.md:46 只明寫 main；`.claude/agents/devops-sre.md:54`；`.claude/commands/sync-main.md:29`。
- 以 Glob 查 `docs/adr/004*`：只有 0040、0041。

**未查證：**
- `product/stock-desk` 在伺服器端是否禁止 force push（交 devops-sre）。
- 所有候選指令的實際寫法，以及執行者能否經由 proxy 執行 `git ls-remote`（交 devops-sre）。
- 交件紀錄目前是否一律在送 qa 之前就推上 product（實務現況我沒有查）。
- f589be8 與 119988f 在其他路徑（例如 `docs/`）上的差異是否影響 CI，例如 `validate_agents.py` 會核對 org-chart 是否同步。

我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案，也沒有執行任何 Bash 指令，只用了 Read、Grep、Glob。

## 四、下一步

1. **coordinator：**
   - 把本回報逐字轉存到 `work/reviews/`，送風控確認 E-1～E-3 與 F-0～F-5；
   - 自行決定要不要把「CLAUDE.md §3 寫『每個 PR』，但 product 線實際不用 PR」的字面落差交 CEO，日後以 `chore/agent-*` 釐清。這一項不擋本案。
2. **risk-compliance-officer：**
   - 判定 R14～R16；
   - 另外確認三項：
     - F-1 名詞對照表，以及 F-2 (γ) 改用 `ls-remote`，也就是 R13 的改寫；
     - F-3 (2) 的 CI 沿用例外；
     - 要不要回頭檢視 f589be8 的 CI 對象落差。
3. **tech-writer：** 風控確認之後：
   - 以 E-2 取代 ADR-0042 的 N198-C9 (b)，C9 (b) 的標記隨之移除；
   - 依 E-1 新增流程名詞那一點，依 E-3 取代先後與相依第 2 點第 2 小點；
   - 「待決」第 1 點，在所有標記處理完之後刪除。
4. **devops-sre：** 以下都只給非唯讀的執行者使用，`READONLY_ALLOWED_BASH` 不變。
   - 書面查證 `product/stock-desk` 在伺服器端是否禁止 force push；
   - 指定以下唯讀查詢：
     - 某個 commit 的 tree 中某路徑的項目與 blob 雜湊；
     - `ls-remote`；
     - 某路徑的歷史，以及首版之後的 diff；
     - merge commit 的 parent 數與各個 parent；
     - `<base>..<head>` 的 SHA 清單；
   - 指定以 40 碼 merge、只允許 fast-forward push 的指令；
   - 若要採用 F-3 (2) 的例外，書面列出完整 CI 會讀取的路徑。
5. **qa-reviewer：**
   - R14～R16 列為 BLOCKING；
   - 風控確認之前，N-198 先合入的路線仍依 C9 (b) (4) 判 BLOCKING。
6. **dev-lead：** 往後的交件紀錄要寫分支名、head 40 碼，以及本角色下每個 commit 的完整 40 碼。
7. **CEO：**
   - (a) 不需要你決定；
   - 若要改成一律走 GitHub PR，屬流程改變，要另立 ADR，由你核可。我不建議在 N-198 期限之前這樣做；
   - ADR-0042 的核可，等風控確認 R14 之後再送。

**相關檔案：**
- /home/user/AICompany/work/reviews/2026-11-07-ADR0042修正版二與修訂八回審-風控.md
- /home/user/AICompany/work/reviews/2026-11-07-ADR0042修正版二與修訂八-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/work/reviews/2026-11-07-N195交件-dev-lead.md
- /home/user/AICompany/.claude/agents/devops-sre.md
- /home/user/AICompany/.claude/commands/sync-main.md
