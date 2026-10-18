# ADR-0027 疑義裁定語意不變部分套用回報（tech-writer）

- 審查者：tech-writer
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

只改了 `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`，在上一輪的未 commit 修改上繼續。第 1、3 (3a)、4 (4a)、5 項和 coordinator 的 F-8 加註都已逐字套用。第 2 項、R-11 第 5 點、(3b)、(4b) 都沒碰。沒有 commit，沒有動決策包、事先宣告和其他檔，沒有讀 `.env`、`*.db`。

## 二、各部門回報（tech-writer；行號是目前工作樹的行號）

**第 1 項：表數**
- L89：15 張改為 16 張。
- L202 M-11 列：「新增 11 張表（…；剩餘待決項 N-4 加 `forecast_void_late_diag`）」，該列其餘不變。
- L1511 Consequences：16 張表。
- L2021 CEO 待決第 10 點新增。第 9 點（L2020）原文不改。
- 修訂紀錄 L3017：寫在 N-4 段末，「最大代價」、Consequences 和 M-11 列的原文都逐字貼入。M-11 列原文取自改前的 L202 整列，「〔逐字貼入目前 L202 整列〕」佔位已換掉。
- 決策包那部分沒動。

**第 3 項 (3a)**
- L315：欄位清單加 `market_scan_from INTEGER NOT NULL, market_scan_to INTEGER NOT NULL`。
- L316-L320：新增子點（含四個巢狀子點）。
- L2989：「未套用的 suggested」句已改。刪去「；N-4 的…欄位」，原句尾 `FLT。` 之後接上「N-4 的 `market_scan_from`／`market_scan_to` 做成 `forecast_correction_job` 欄位一項，已由 tech-architect 疑義裁定第 3 項採用，見 N-4 段。」
- 修訂紀錄 L3027：在 N-4 段，欄位清單原文逐字保留，L2950 被刪的原句尾也逐字保留。
- (3b) 沒套用，也就沒有 `market_scan_restore_suspected`。

**第 4 項 (4a)**
- A-28 (ii) 在 L1231，已加 `cause ∈ {suspended_f3, db_restored}` 和括號句。
- 修訂紀錄 L3036-L3039：在 N-5 段，被取代原文逐字保留。條目內註明 (4b) 尚未套用、待風控確認。

**第 5 項 FL-64**
- L1663 起，緊接在 FL-23（L1662）之後，下一個條目是 FL-24（L1696）。
- (f) 的「〔第 2 項採甲版時〕三個 scope × `dividend_factor`」括號標記原樣保留。
- 修訂紀錄 L3031：在 N-4 段，註明無被取代原文，並註明該標記待風控確認第 2 項後再定。

**第 5 點 coordinator 裁定（F-8）**
- L599：第 9 項第一行原文不改，句尾加上〔剩餘待決項註…〕，字面與你給的一致。
- 修訂紀錄 L3059-L3060：新增獨立小段「D-8.1 第 9 項（F-8；掛 A-77；方向：不變）」，放在檔尾「起算日」段（L3056）之後。
- 這一條有兩處超出你給的字面，請知悉：
  - 我補了一句註明「§6.2」是指 `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 的 §6.2。依據是 data-engineer 查證檔 L26、L121，我已回頭 Grep 確認。
  - 另一句註明「事先宣告 §9.2」和「風控 v0.13 審查 R-4」是依 coordinator 字面轉錄，我沒有回查。
  - 這兩句如果你不要，可以刪。

## 三、驗證

- 行尾空白：Grep `[ \t]+$` 為 0 筆。
- 新名稱拼寫：`market_scan_from`、`market_scan_to`、`cause`、`suspended_f3`、`db_restored`、FL-64 的拼寫全文一致。
  - `cause ∈ {suspended_f3, db_restored}` 出現在 L773（原有的 N5-2）和 L1231（A-28 (ii)），兩處一致。
  - `market_scan_*` 出現在 L315-L320、L350、L353、L1670、L1684-L1693、L2989、L3027 等處。
- FL 編號：FL-64 只出現一次作為條目（L1663）。FL-20～FL-29、FL-60～FL-63 都沒有重複。
- 表數殘留：「15 張」只剩被取代原文的引用處（L2897、L3018、L3021）。L2850-L2858 一帶的已 commit 被取代原文沒動。
- 未做：沒有跑 `git diff --check` 和 `scripts/validate_agents.py`，我沒有 Bash。

## 四、下一步

1. 風控確認的一包（第 2 項、R-11 第 5 點中斷作業修訂、(3b)、(4b)）回來後，我再套。屆時要回頭處理三處：
   - FL-64 (f) 的〔第 2 項採甲版時〕標記；
   - R-11 第 6 點（L354）；
   - L355 R-11 第 5 點，目前仍是「同一個 `(run_id, recorded_at)` 不得出現在兩個作業的 `triggers_json`」。
2. 目前 FL-64 (e) 第四格（中斷作業之後的下一個作業可以寫入）檢查的是裁定修訂後的規則，但 R-11 第 5 點條文還是舊字面，兩者暫時不一致。這是裁定本身造成的，要等風控確認後才會收斂。
3. 仍須與事先宣告 v0.13 同批，不得單獨 commit。
4. 佐證清單（B 類，來源：tech-architect 疑義裁定檔 2026-10-18 第二節第 1、3(3a)、4(4a)、5 項，以及 coordinator 的 F-8 裁定）：本次所有改動都轉錄自裁定檔的字面，沒有新增 A 類技術宣稱。唯一自行查證的是 F-8 註腳中「§6.2」的對應檔案，依據是 data-engineer 查證檔 L26、L121。快照是工作樹未 commit 狀態，抽驗時請以原文定位，不要只靠行號。
