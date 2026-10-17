# ADR-0027 依風控回送四項確認照改回報（tech-writer）

- 審查者：tech-writer
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

風控回送四項確認（`work/reviews/2026-10-17-ADR-0027-疑義裁定回送四項確認-風控.md`，commit 807be08）的 Q-1、Q-2、Q-3、回送第 3 項條件句，以及 coordinator 定案採用的 suggested 三項，已逐字改進 `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`。只動這一個檔，沒有 commit。`max(as_of, fetched_at) ≤ now` 保留。被取代的原文都已進修訂紀錄。行號是快照，請以原文定位。

## 二、逐條改動

| 項目 | 位置（現行行號） | 內容 |
|---|---|---|
| Q-1 | D-9.3，L535–536 | 加 `index_bar_confirmed_erroneous` 全文，用風控版本，取代 TA 版本（含等待值 5 個觀察交易日、`diag_last_close`、只適用 `scope_kind = market`、結算後確認走 §6.4 supersede＋A-65 翻案伴隨句）。子行加「第五值在作廢判定順序中的位置交 quant 在事先宣告登記（v0.12，凍結前）」。 |
| Q-1 | FL-22，L1226 起 | 「四值」改「五值」，加三格：market 結算前確認且等待期滿取不到→寫入此值；market 結算後確認→supersede 列為此值，`had_listed_result` 為真；非 market scope 寫入→拒絕。 |
| Q-2 | FL-52 (d) 末句，L1311 | 改為泛指版：「本 ADR 任何一處規定『核可之前 FL-52 (d) 失敗』的片段（含 A-62 R2 第 6 點、A-63 單列狀態片段、A-65 (h)、D-7.8 第 4 點），全部核可之前，本項仍失敗。」 |
| Q-3 | 待決事項 tech-architect 列 | 加一條：平日、非休市日、既不在 D-8.1 (i) 也不在 (ii) 的日期，不是觀察日也無缺日列；偵測與 §4.2 揭露方式由 TA 提案、送風控，D_v 前核可。 |
| Q-3 | CEO 說明第 4、5 點（約 L1156–1157） | 第 4 點改為「那一天只要仍算觀察日，就會照實記成缺日，不會補造；如果那一天連大盤的定案資料也沒有，就不算觀察日，也不會出現在缺日紀錄裡，這類日子怎麼揭露會在開始記錄前定好」。第 5 點改為「重抓失敗的日子，只要仍算觀察日，就照實記成缺日」。 |
| 回送第 3 項 | A-63 第 11 點，L801 | 在 `outlook_block`／LM-12／LM-120 fail-closed 句之後加：「這一格的失敗不得以 skip、xfail、placeholder 或暫定字面讓測試通過（比照 D-7.8 第 2 點）。第九批提案 1 的 commit 之前，不得合併任何實作 `outlook_block` gate 片段選用的程式。」 |
| suggested 1 | FL-19 (c)②③ | 兩個子例本文本來就是必要子例，沒有「選配」字樣。修訂紀錄裡原寫「選配」的說明已改成「必要子例（coordinator 定案採用，CEO 可推翻）」。 |
| suggested 2 | r2 待決清單「已結算＋實際結果」項 | 行尾加「〔已決：LM-131（第八批）〕」。 |
| suggested 3 | A-68 第 4 點，約 L684 | 改為「初版經 PM 建議（`work/reviews/2026-10-17-PLAN_OUTPUT_SURFACES與頁面歸屬-product-manager.md`）並經風控顯示面確認（V10-12），之後要改須送審並升 `policy_version`」。 |

**修訂紀錄**
- 新增一段「風控疑義裁定回送確認」，在 L2118 附近。標註風控 807be08，涵蓋本批新增、尚未 commit 的行。
- 逐字保留的原文：FL-22「四值」行、FL-52 (d) 首次套用版末句、CEO 第 4、5 點被改的句子、L684 首次套用版。
- 修訂紀錄檔頭那句「第五值這次不改」已更新為指向這一段。
- 修訂紀錄中 TA 版 D-9.3 條文沒有舊檔原文可保留（D-9.3 第五值為新增）。

## 三、驗證（Grep 自查）

| 項目 | 結果 |
|---|---|
| FL-22 有「五值」 | 是（L1226） |
| FL-22 沒有「四值」 | 全檔「四值」只出現在修訂紀錄（約 L2129）的原文引用 |
| D-9.3 有 `index_bar_confirmed_erroneous` | 是（L535） |
| 「min(as_of, fetched_at) ≤ now」在本文 | 0；只出現在修訂紀錄原文引用（約 L2078） |
| `max(as_of, fetched_at) ≤ now` | 存在（L365） |
| 「不得以 skip」 | 存在（L801，並見修訂紀錄） |
| FL-52 (d) 含「本 ADR 任何一處」 | 是（L1311） |

前兩輪自查（本文 L1544 `## 修訂紀錄` 之前）仍通過：
- `x2_post_confirm`、`待風控確認`、「時間戳 ≥ 該 snapshot 的 `stats_json.e_read_at`」、「依 `recorded_at`」、「依 `resolved_at`」、「`e_read_at` 晚於該事件」、「大盤或個股在 `gated` 時照樣附」、「LM-38 重送核可之前」、「LM-38 要重送」、「〔超出底線」：合計 0。
- 「〔超出字面」、「測試四點」、「B-6、B-7（同 r2）」：本文 0，只在修訂紀錄原文引用（約 L2093–2094、L2119、L2124）。
- LM-34、LM-73：本文只在 L799（撤回註記），其餘在修訂紀錄。
- `post_x2_final_run`、`e_read_event_seq`、`e_read_outcome_seq`、`E_NEUTRAL_EVENTS`、`had_listed_result`、`gate_coverage_gaps`、`GATE_SLOT_SCOPES`：全部存在（七項合計 16 行）。

## 四、下一步

1. coordinator：依風控第四節增補後的清單核對（第 10c、10d 點）。我沒有 shell 工具，無法跑 `git diff`。
2. quant：v0.12（凍結前）登記第五值在作廢判定順序中的位置。
3. TA：Q-3 的偵測與揭露提案（D_v 前送風控）。風控 suggested 另請 TA 確認 `final_after` 的呼叫位置符合 CS-17：A-77 (i) 與 RC″-5 的 `set_i_check` 要改由 `session_calendar.py` 提供。我這次沒有動這兩處，因為風控未要求逐字改寫。
4. 風控 suggested「`now` 寫明是 store 時鐘且可注入」、「族群 `replay_review_approved` 只能出現在測試 fixture」我也沒有寫入，因為不在 coordinator 指定採用的三項內。
5. L1479 引用「D-4 第 7 點」已確認存在（D-4 第 7 點，族群成員輸入）。
