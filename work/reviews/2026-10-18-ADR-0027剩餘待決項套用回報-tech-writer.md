# ADR-0027 剩餘待決項套用回報（tech-writer）

- 審查者：tech-writer
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- 已把風控審查、TA 補充、TA 提案三份來源套進 ADR-0027，只動 `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`。沒有 commit，沒有碰 v0.13，沒有讀 `.env` 或 `*.db`，狀態維持 proposed。
- 風控逐字字句 R-3′、R-6′、R-7、R-8、R-9、R-10、R-11、R-15 全部照寫，沒有改寫。R-11 採甲法，乙法未寫。
- 套用順序是從檔尾往前，用字串定位，行號沒有位移的問題。
- 修訂紀錄末尾新增段「剩餘待決項（N-3～N-12、起算日）」，段首已寫明：
  - 來源與優先序；
  - 與事先宣告 v0.13 同批（任何一份不得單獨 commit）；
  - 累計方向統計維持 18／2／9／1／3；
  - 不新增 A 號。
- 被取代的原文逐字移入該段：L398、L487 兩處被取代片段、FL-19 (h5)(h6)、N-4 原建議條文、N-12 原「部分窗口」後兩子點（被 R-7 取代）。
- 沒有 Bash，所以我沒跑 git。HEAD 是否為 d7601f7、是否只有這一個檔案有變動，我沒驗證。可以間接佐證的是，TA 與風控引用的 L398、L487、L575、L617、L1049、L1835、L1879、L1880 在改動前都對得上原文。
- 有 13 項疑義待你定奪，見第四節。其中第 1、2 項（表數過期、R-11 引用 ADR-0016 D-5.2）是文件內容的實質問題，建議先看。

## 二、套用清單（來源 → 位置；行號為目前工作樹，未 commit）

| 來源 | 位置 |
|---|---|
| 自行加（先例：第九、十批） | 檔頭 L20 新增一行，指向新修訂段 |
| TA 補充 N-12 | D-3 `forecast_outcome` L293-307：`void_reasons_json`，接在「狀態」之後 |
| 風控 R-11 第 4 子點 | D-3 `forecast_outcome` L308：`settle_source_run_max`（與 L347 觸發第 4 點同文） |
| 風控 R-8 | D-3 L316（原 L299）句尾指向 |
| TA N-4 表 | D-3 L319-342：`forecast_void_late_diag`，接在 job／job_end 群組之後 |
| 風控 R-11（甲法，九點逐字） | D-3 L343-352：「晚到資料的觸發」 |
| TA N-3 | D-7.3 L444-：`candidate_t_x2` 處理句，接在 A-75 (iii)(iv) 句之後 |
| TA N-9 | D-7.3 K-10：第一子點改寫（L466），新增 meta 一點（L469） |
| TA N-3 | D-8.1 第 5 項 payload（`origin` 加 `candidate_t_x2`；`independent_source_absent` 句改寫） |
| TA N-3 | D-8.1 第 12 項 (h5) 句尾 L649、待決事項 L2038 加〔已決〕 |
| TA 補充 N-12 | D-9.3 L691：原 L617 加〔已決〕 |
| TA 補充 N-12 | D-9.3 L692-703：判定順序、判定時點、部分窗口 |
| 風控 R-6′ | D-9.3 L693：加 tuple，並註明 FL-22 另加一格 |
| 風控 R-3′ | D-9.3「判定時點」第二子點句尾（約 L698） |
| 風控 R-7 | D-9.3「部分窗口」後兩子點（約 L700-702） |
| TA N5-1、N5-2 甲案 | D-11.2 L756-：整檔還原不另設撤銷、前提被破壞時撤銷、檢查點不得重抽 |
| 風控 R-9 | N5-2 §4.2 揭露句 |
| 風控 R-10 | N5-2「比照 A-28 (iii)」之後（LM-74 句） |
| TA N-6 | A-63 第 11 項 `n_disclosure_masked`（原 L844）之後 L947-：`mask_episodes` |
| 風控 R-8 | D-11.4 11(h) R10-3（約 L1167）：指向註記放在「在 §4.2 揭露。」之後，行末加〔已決〕 |
| TA N5-3 | D-14 L1453：D_v「不會移動」之後 |
| TA 起算日、風控 R-15 | D-14 L1455-：`claim_dv` 三條綁定；N-15 註記在第二條句尾 |
| 風控 R-10 | Consequences L1534：「甲案的殘餘」，句尾加風控裁定註 |
| TA N-12 | FL-22（L1646 起）：表格驅動格，另一格為 R-6′ |
| TA N-12 | FL-50（L1660）：加一格並註明 V10-08 定案後補一格 |
| TA N-3、N-9 | FL-19 (h5)(h6)＋一格（約 L1611-1613）、(i)＋四格（約 L1622） |
| TA N-5、起算日 | FL-48（L1683）加格 |
| TA N-6 | FL-52 遮蔽 FL（L1800）加格 |
| TA N-5 | FL-58 RC‴-1 之後（L1911）加格 |
| TA N-4 | FL-59（L1934）加四格 |
| TA N-3 | 待決事項 L2038：(h5) 〔已決〕 |
| TA N-4 | 待決事項 L2039：診斷標籤〔已決〕 |
| 風控 R-3′、R-4 | 待決事項 L2040：O-1 一列，(a)～(c) 與風控 R-4 逐字相同（Grep 已核對） |
| TA 補充 N-12 | 待決事項 quant 段（原 L1835）加〔已決〕，原句不改 |
| 全部 | 修訂紀錄末段（約 L2940-2999） |

## 三、驗證

已做的自查（Grep 與 Read）：
- **判定順序**：D-9.3 L692 的箭號順序與 L693 的 `VOID_REASON_ORDER` tuple 逐字一致，且與風控 R-6、R-6′ 的順序相同。
- **O-1 定案前不得凍結**：D-9.3（約 L698）與待決事項（L2040）都有。(a)～(c) 與風控 R-4 逐字相同。
- **R-8 指向**：L316（原 L299）與 L1167（原 L1049）都有「〔N-4：操作定義…〕」。
- **風控第 3 點所列名稱**：除 `official_holiday_table_meta` 在 ADR 內寫法同風控外，其餘名稱都存在且拼寫一致。名稱為 `void_reasons_json`、`VOID_REASON_ORDER`、`void_reasons(`、`candidate_t_x2`、`forecast_void_late_diag`、`VOID_LATE_DATA_KINDS`、`void_late_data_count`、`settle_source_run_max`、`scan_late_market_bars`、`ok_bars_runs_between`、`market_scan_from`／`market_scan_to`、`mask_episodes`、`restore_checkpoint_bound`、`claim_dv`、`db_restored`。
- **computed_at**：全文 5 處，都不是 `forecast_outcome` 的欄位。L320 是 `forecast_void_late_diag` 自己的欄位（TA 原文），其餘是 `forecast_validation_snapshot`。
- **settle_source_run_max**：已在 D-3 `forecast_outcome`（L308），且觸發第 4 點（L347）同文。
- **ADR-0016 引用**：只核對了 ADR-0016 檔存在與 D-5.2 內容，結果見疑義 2。
- **沒做的事**：沒有跑 git、沒有跑測試。這次只改 ADR，沒有動 agent 檔，所以沒跑 `validate_agents.py`。

## 四、疑義（我沒有自行決定）

1. **表數過期**：新增 `forecast_void_late_diag` 後，D-3 的表由 15 張變 16 張。下列敘述若照字面算會過期，兩份來源都沒提這件事，我沒改：
   - 評估摘要 L88「15 張」；
   - M-11 列「新增 10 張表」；
   - Consequences「15 張表」；
   - CEO 待決第 9 點「由 8 張改為 10 張」。

   讀法：(甲) 這些數字要同批改成 16／11；(乙) `forecast_void_late_diag` 另有不計入的理由。請 TA 定奪。
2. **R-11 第 6 點引用「ADR-0016 D-5.2」**：我讀了 ADR-0016 L116，D-5.2 的標題是「資料來源：主 DB 同步紀錄」，講覆蓋判定，沒有「因子修訂」觸發的字樣（Grep 該 ADR 無「因子修訂」）。我逐字保留，請 TA 或 data-engineer 確認引用處是否正確。
3. **`market_scan_from`／`market_scan_to` 存放處**：R-11 第 2、5 點用到這兩個欄位，但 D-3 `forecast_correction_job` 的欄位清單沒有它們。風控 suggested 做成 job 欄位，我沒套用。可能的讀法：
   - (甲) 加到 `forecast_correction_job` 欄位；
   - (乙) 放 `triggers_json`（風控不建議）；
   - (丙) 放 job_end。

   目前 ADR 內這兩個名稱沒有定義處。
4. **插入位置**：以下兩處來源只說「之後」，沒給精確位置，請確認：
   - `forecast_void_late_diag` 我放在 job／job_end 整個群組（含 `rejected_count` 與落實 §6.4 兩點）之後，沒有切開 L299 與 L300。
   - 「晚到資料的觸發」我放在 D-3，緊接 diag 表。R-8 指向文寫「見 D-3 …與『晚到資料的觸發』」，與此相容。備選位置是 D-9.5「更正」之下。
5. **R-15 的「D-14 起算日條文句尾」**：我放在第二條（綁定值的那一條）句尾。備選是第一條句尾，或整個起算日區塊之後。另外，「值的綁定已由 tech-architect、quant 確認」一句，quant 的具名確認要在 v0.13 才存在。兩份同批 commit 前須核對 v0.13 已有，否則這句不屬實。
6. **R-8 在 L1049 的位置**：被引句「補到資料的筆數記在…」在行中，我把註記放在「在 §4.2 揭露。」之後（行中），〔已決〕放行末。備選是整行末。
7. **`suppressed_positive.cause`**：N5-2 說 `suppressed_positive` 加必填欄位 `cause ∈ {suspended_f3, db_restored}`。但 A-28 (ii)（約 L1180）仍寫 `suppressed_positive = {checkpoint_n, kind}`，我沒改。讀法：(甲) N5-2 自成修訂；(乙) A-28 (ii) 也要補 `cause`，那會動到既有原文，需要來源授權。
8. **改動到 TA 或風控字面的 6 處**：風控逐字字句沒有任何改寫，下列都是 TA 條文或我補的小幅改動，請確認可接受：
   - L487 payload：TA 的替換文字沒有 Q3-7 括號註。我保留該括號註，並讓它緊接在 `candidate_t_x2` 括號之後（兩個括號並列）。被取代的「（見第 12 項）」隨整句被取代而移除，原文在修訂紀錄。
   - FL-19 (h6)：TA 的敘述是描述性文字。我寫成「direct 與 verified 各一格：verified 格斷言沒有 `origin = candidate_t`；direct 格斷言兩個 origin（`candidate_t`、`candidate_t_x2`）各一筆」。括號內的兩個名稱是我依 N-3 補的。
   - FL-19 新增格：N-3 的「加一格」我標「（N-3）」，沒有編 (h7)。
   - FL-22：D-9.3 內已有「FL-22 另加一格」（R-6′）。我另在 FL-22 加一條「（風控 R-6′）…等於 D-9.3 宣告的 tuple」重述，方便逐條檢查；不要可刪。
   - FL-59 第 1、4 格：TA 原文的「本表」，我換成 `forecast_void_late_diag`，因 FL 區沒有前文可指。
   - 檔頭 L20 新增一行：來源沒明講，沿用第九、十批先例。不要可刪。
9. **FL 沒有覆蓋 R-11 的觸發本身**：TA 的 FL-59 四格只涵蓋 diag 表。R-11 九點的掃描範圍 W、配對、還原保護、「未涵蓋，不計」都沒有 FL 格。來源沒給，我沒補。
10. **F-8 狀態不一致**：ADR D-8.1 第 9 項（約 L594）仍寫「待 data-engineer 查證」。風控 R-4 的新狀態是「repo 內無法查證，需 CEO 代跑 §6.2」。風控的 ADR 清單沒點名這處，我沒改。
11. **待決事項與知悉項沒補**：
    - 待決事項只加了 O-1；N-14 只出現在 D-9.3，沒有獨立列。
    - R-10「最終責任由 CEO 負」只寫在 Consequences，沒有加到 CEO 待決或知悉項。
    - N-5、N-6 要 quant 在 v0.13 登記，ADR 待決事項 quant 段也沒新增列。
12. **suggested 項目未套用**：風控與 TA 標為 suggested 的項目，已列在修訂紀錄段首，這裡不重複。
13. **跨文件依賴**：D-9.3 的 O-1 但書引用事先宣告 §9.2「仍開著的凍結前事項」O-1 的 (a)～(c)。這要靠 quant 的 v0.13 有同文（R-4）。coordinator 機械核對時請連同比對。
