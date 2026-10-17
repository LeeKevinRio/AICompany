# ADR-0027 依 tech-architect 疑義裁定照改回報（tech-writer）

- 審查者：tech-writer
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- tech-architect 的裁定（`work/reviews/2026-10-17-ADR-0027-r3系列套用疑義裁定-tech-architect.md` 第二節）已逐字改進 `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`。只動這一個檔，沒有 commit。
- 你要求的改動全部完成：第 1、2、3（選配）、4、5、7、8、12、15 項。
- D-9.3／FL-22 的第五個 `status_reason` 值這次沒有改，仍是「四值」，依指示留待另案。
- 裁定中標為回送風控的三處，我照寫：
  - `max(as_of, fetched_at) ≤ now`（第 2 項）；
  - FL-19 (c)②③ 兩個選配子例（第 3 項）；
  - 期間內 FL-52 在 `outlook_block` 的 {`forward_n_below_min`} 格 fail-closed 失敗（第 4 項）。
- 被取代的原文都已逐字進修訂紀錄（見二）。
- 行號是快照，請以原文定位。

## 二、逐條改動

| 裁定項 | 改動位置（現行行號） | 內容 |
|---|---|---|
| 第 1 項 | Consequences，L1141–1148 | 八點整段取代。第 7 點保留 RC′-8 逐字文，方括號指示沒有寫進 ADR。標題改成粗體。第 2、3 點改為「記 `inputs_not_ready`、該日是觀察日才留缺日列」。第 8 點刪掉重複子句。CEO 說明第 4、5 點不動。 |
| 第 2 項 | D-7.3，L365 | 改為 `is_final(TW, T, as_of, fetched_at)` 為真（ADR-0028 CS-17），而且 `max(as_of, fetched_at) ≤ now`。 |
| 第 2 項 | FL-61，約 L1189 起 | (a)～(e) 逐字內文取代。 |
| 第 3 項 | FL-19 (c)② 句尾、(c)③ 句尾（約 L1198–1199） | (c)② 加「`trigger = official_holiday` 但 d 不在 `holiday_table` 涵蓋範圍或不是表列休市日」。(c)③ 加「`verification_ref` 指向的查證紀錄 `session_date ≠ d`」。 |
| 第 4 項 | FL-58 (e1)(e2)，約 L1377 起 | (e1) 拆兩格。第一格 G_eff＝{`forward_n_below_min`, `replay_review_pending`}，選 (c) 並由 `covers` 聯集等於 G_eff 決定片段，不得只選第 4 項。第二格依解除路徑，G_eff＝{`forward_n_below_min`}，選 (c)、第 4 項。(e2) 加註 `replay_review_pending` 已解除。(e3) 不動。 |
| 第 4 項 | A-63 第 11 點登記子點，L796–798 | 登記 LM-12、LM-98。登記 LM-127／LM-126（LM-34、LM-73 已由風控撤回，附 R9-04 路徑）。`outlook_block` 的 LM-12 與 LM-120 優先序待定，FL-52 在該格 fail-closed。 |
| 第 4 項 | FL-52 T-2 子點 | 改為第九批 LM-144：`e_changed_since` 為真或沒有 daily snapshot 時，選 LM-144，不選 LM-129。 |
| 第 4 項 | 待決事項 tech-architect 列 | 加 A-63 第 11 點：`outlook_block` 優先序、selector 簽章、LM-144 slot 登記、驗證徽章遮蔽。 |
| 第 5 項 | D-7.8，約 L401 | 改為「D-7.8 第 8 點全文與 FL-52b (9) 所稱『紀錄清單』…」。 |
| 第 7 項 | 第 9 點第 4 點，約 L684 | 「待 PM 依 Phase 4 版面確認」改為「初版經 PM 確認（`work/reviews/2026-10-17-PLAN_OUTPUT_SURFACES與頁面歸屬-product-manager.md`）」。 |
| 第 8 項 | 第 9 點 2a，約 L676 | 「不在本點清單內」改為「第 1 點所列歸屬（`first_layer` 六項、`symbol_detail`）以外」。 |
| 第 12 項 | A-63 第 12 點 (2)、FL-58 時鐘無關格 | 兩處〔超出字面…〕改成風控 RC″ 回送確認第 7 點、第 4 點核可的引用。〔未查證〕與 `cache.py:109` 保留。 |
| 第 15 項 | FL-52 開頭 | 「測試四點」改為「測試項目」。 |
| 第 15 項 | FL-52 (d) 末句 | 改為「『期間已開始』片段為 LM-106。A-62 R2 第 6 點所列片段全部核可之前，本項仍失敗。」 |
| 第 15 項 | D-7.8 第 2 子點，約 L426 | 改為「本點第 4 點與 A-62 R2 第 6 點所列片段核可之前，FL-52 (d) 失敗」。 |
| 第 15 項 | r2 待決清單，約 L1478–1494 | 行尾加註「〔已決：…〕」八項（A-36 狀態片段 LM-106；A-36 第 4 點；R5-06；其餘 7 個片段；LM-79 worst_case；`exclusion_reasons`；兩個狀態片段；`in_eligible_set`），沒有刪除任何一項。「已結算＋實際結果」那一項沒有片段編號，不加註。 |
| 第 15 項 | quant v0.9 的「B-6、B-7（同 r2）」 | 取代為「指數序列…已決，見 D-9.3（V10-01）；B4『該股所屬族群』…已決，見 D-4 第 7 點（V10-05）」。 |
| 第 15 項 | D-11.4 (f)，約 L817 | 句尾加澄清句（作廢列另依 A-61 用 LM-109，兩者並列）。 |

**修訂紀錄位置**：新段在 L2048 之後（「r3 系列套用疑義裁定」），掛在 A-79、A-75、A-63、A-68、A-66、A-71、A-85／A-30 之下，逐字保留被取代的首次套用版原文。

**修訂紀錄裡的標記**：引用原文的〔超出字面…〕、「測試四點」、「B-6、B-7（同 r2）」、LM-34、LM-73 會留在修訂紀錄，不算本文殘留。

**過程中的小失誤**：第 1 項第 8 點我一度漏掉「已寫入的 snapshot 不改；」，已補回。

## 三、驗證（Grep 自查）

以下數字是 L1536（`## 修訂紀錄`）之前的本文。

| 項目 | 結果 |
|---|---|
| 「〔超出字面」 | 本文 0；只出現在修訂紀錄原文引用（約 L2085–2086） |
| 「測試四點」 | 本文 0；只在修訂紀錄原文引用（約 L2111） |
| 「B-6、B-7（同 r2）」 | 本文 0；只在修訂紀錄原文引用（約 L2116） |
| LM-34、LM-73 | 本文只在 L797，即撤回註記；其餘在修訂紀錄 |
| FL-58 (e1) | 兩格都沒有「G_eff 含兩個值，卻選 (c)、第 4 項」的格；第一格明寫不得只選第 4 項 |
| `max(as_of, fetched_at) ≤ now` | 存在（L365） |
| `min(as_of, fetched_at)` | 只在修訂紀錄原文引用（約 L2070） |

先前那批自查，全檔重跑：

| 項目 | 結果 |
|---|---|
| `x2_post_confirm` | 0 |
| `待風控確認` | 0 |
| 「時間戳 ≥ 該 snapshot 的 `stats_json.e_read_at`」 | 0 |
| 「依 `recorded_at`」 | 0 |
| 「依 `resolved_at`」 | 0 |
| 「`e_read_at` 晚於該事件」 | 0 |
| 「大盤或個股在 `gated` 時照樣附」 | 0 |
| 「LM-38 重送核可之前」 | 0 |
| 「LM-38 要重送」 | 0 |
| 「〔超出底線」 | 0 |
| `post_x2_final_run`、`e_read_event_seq`、`e_read_outcome_seq`、`E_NEUTRAL_EVENTS`、`had_listed_result`、`gate_coverage_gaps`、`GATE_SLOT_SCOPES` | 全部存在（七項合計 15 行） |

## 四、下一步

1. coordinator：做 hunk 對照與機械核對。我這邊沒有 shell 工具，無法跑 `git diff`。
2. 另案送風控：D-9.3／FL-22 第五值的條文，以及 quant 在作廢判定順序中的位置。
3. 待決事項已記：第九批提案 1（`outlook_block` 優先序、selector 簽章、LM-144 slot）落地前，FL-52 在 `outlook_block` 的 {`forward_n_below_min`} 格必然失敗。這是 fail-closed，只擋 D_v，不會讓畫面多顯示內容。
4. 先前回報的第四節疑義，其餘各項已按裁定確認，沒有新的疑義。
