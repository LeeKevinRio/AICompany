# ADR-0028 依風控套用後確認 U-1～U-6 照改回報（tech-writer）

- 審查者：tech-writer
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

U-1～U-6 已逐字套用到 `/home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md`，這是唯一動過的檔案。沒有 commit，沒有改修訂紀錄，L681、L713 兩筆「待風控確認」原文沒有動。你列的 5 項自查全部通過。

行號與你給的一致，我是用原文定位後再核對行號。

我先前回報的 13 項疑義中，風控 U-1～U-6 對應的是第 2、4、8、9 項，這次已解決。其餘各項風控判可，不動。

## 二、逐條改動

| 編號 | 行 | 改前關鍵字 | 改後關鍵字 |
|---|---|---|---|
| U-1 | L458 | 標題「頁尾三組（含 `OperationSummaryFooterGroup`）」，括號只列兩組；不取代的主視圖只列 `KeyLevelsPanel`、`EntryObservationPanel` | 「**頁尾三組**（`KeyLevelsFooterGroup`、`EntryFooterGroup`、`OperationSummaryFooterGroup`）」；不取代清單加 `OperationSummaryPanel` |
| U-2 | L577 | 「只有頁尾三組例外，那兩組斷言揭露在組內」 | 「只有頁尾三組（三個 BlockId 全列）例外，這三組斷言揭露在組內」 |
| U-3 | L221 | 「操作摘要與建議卡（`/api/advice`）；」 | 「…（`/api/advice`），含頁尾「操作摘要」組的資料日期句（`asOfStatement`）；」。L218 的 bars 頁尾兩組未動 |
| U-4 | L329 | 「排除欄位只限上列三個，加上 `last_bar_date_anomaly`，不得再增列（K-20）」 | 「排除欄位只限上列四個，不得再增列（K-20）」 |
| U-5 | L565 | 「…最多一次 evidence 讀取（計數）。」 | 「…（計數）；`/api/advice` 的 evidence 讀取次數依 CS-26 第 1 點 K-31 所選方式計數，選 (b) 時至多兩次。」 |
| U-5 | L417 | 「每個請求的 evidence 讀取超過一次；」 | 「每個請求的 evidence 讀取超過一次（`/api/advice` 依 K-31 除外，見本點第四款）；」 |
| U-6 | L403 | 「欄位為必填，前端型別不得標成 optional。」 | 「上列各欄位都是必填：」加六個欄位名稱，以及「前端型別不得標成 optional」 |

U-6 的六個欄位：
- `/api/bars` 的逐列 `date_anomaly`（值可以是 null，但欄位必須存在）、`date_anomaly_rows`、`anomaly_valid_until`；
- 其他端點的 `date_anomaly_rows`、`anomaly_valid_until`、`last_bar_date_anomaly`。

**一個判讀**：U-5 的 L417 說「句末加」，該條原本以「；」結尾。我把括號加在「；」之前，讓清單標點維持一致。如果風控要的是「；」之後，請指出。

## 三、驗證（Grep 工具）

1. L458 與 L577 各自完整列出 `KeyLevelsFooterGroup`、`EntryFooterGroup`、`OperationSummaryFooterGroup`。L458 的不取代清單含 `OperationSummaryPanel`。✓
2. 「那兩組」＋「上列三個」合併 grep：0 筆。✓
3. L565 含「K-31」與「至多兩次」。L417 含「K-31 除外」。✓
   - 另外 L411 原有的「至多兩次」（K-31 (b) 條文）未動。
4. L403 明列六個欄位名稱，見上。✓
5. 「待風控確認」＝2 筆，就是 L681、L713。✓
6. 本次只改上述 7 行（含 U-5 兩處），其餘行未動。我沒有 git，無法跑 diff 核對。

## 四、下一步

1. coordinator 依風控第四節末的核對清單比對。第 6 項（diff 只含新增或本次新增行的改動）需要有 git 的人跑。
2. 通過後可 commit：Conventional Commits，只 add 這個 ADR 檔。
3. L417 的括號位置若風控有異議，再回報給我調整。

相關檔案：`/home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md`
