# ADR-0027 checkpoint 批落檔

- 審查者：tech-writer
- 日期：2026-10-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

ADR-0027 的 checkpoint 批已全部落進 `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`，只改這一個檔，沒有碰 git、`.env`、`*.db`。T-1～T-6、2-A～2-E、N39-1～N39-3、2-G 錄存 (i)(ii) 都已套用，2-H 與 2-F 不落檔。

有兩處和你給的機械核對不一致，請裁示，詳見第四段：
- `snapshot_skipped` 實際是 1 處，不是 0。
- 2-B 第三處被取代原文沒有重錄進修訂紀錄。

## 二、各部門回報（落點，行號為落檔後的值，僅供參考）

### T-1～T-6
- **T-1**：D-11 第 2 點 2-A「沒有期限的待重算項不讓閘門等待」第一子點（L1330）。落字為「其 `pending_json` 中屬於該 claim 的 E、而且 `reason = write_validation_failed` 的項」。
- **T-2**：同一小節第三子點。首尾為「`unbounded_pending` 中有 T ≤ T\*_j 的紀錄時，該 checkpoint 列的…」到「…`unbounded_pending` 照列全部這類紀錄，不分 T。」
- **T-3**：`prefix_change_kinds` 的條件改為「`unbounded_pending`：`unbounded_pending` 中有 T ≤ T\*_j 的紀錄；」。
- **T-4**：§4.2 資料來源「每列附」改為「`unbounded_pending`（逐項標明 T 是否 ≤ `prefix_last_session`）」。
- **T-5**：「終局」子點改為「…依 D-9 第 1、3 點與事先宣告 §6.3 v0.22 註（V22-07）寫入 outcome 列之後即為終局。」
- **T-6**：D-11.4 第 12 點 (ii) 子點（L1913 一帶）。在「不得因為 `cause` 只記一個值而只計一邊。」之後，接「（N-23 Q3）§4.2「延後判定的檢查點」列（事先宣告 §4.5「檢查點的判定樣本、時點與 seed」第 2、4 點，v0.22）同樣依 `checkpoint_timing`（`delayed`、`prefix_changed`、`n_at_eval`、`gate_delay_observed_sessions`）判定，不依 `cause`；…」到「`positive_suppressed_during_f3` 不因 `checkpoint_delayed` 而設定。」

### 2-A～2-G
- **2-A**：D-11 第 2 點，插在 `UNIQUE(claim_id, computed_for_session, eval_kind)` 與 `bootstrap_seeds_json` 兩行之間（L1326 起）。
  - 首尾為「（N-23 Q3；風控 R-Q3-3）另加 `UNIQUE(claim_id, checkpoint_n)…`」到「…本點不改檢查點的值、退出期限與 5% 門檻。」
  - 【α】標記已刪，句子保留。
  - `delay_kinds` 那條寫成「`unbounded_pending` 依上文。」，刪標記後補了一個空格。
  - 其餘照 TA 字面。
- **2-B**：三處皆已改。
  - D-11 第 2 點 N-5 甲案子項（L1405）：首尾為「…`cause ∈ {suspended_f3, db_restored, checkpoint_delayed}`（`checkpoint_delayed` 依本點 N-23 Q3）。」
  - 第 12 點 (ii) 的 `suppressed_positive`（L1912）：首尾為「…`db_restored` 依 D-11 第 2 點 N-5 甲案；`checkpoint_delayed` 依 D-11 第 2 點 N-23 Q3）；」
  - 第 12 點 (ii) 首句（L1913）：首尾為「多個原因同時成立時，依 `suspended_f3` → `db_restored` → `checkpoint_delayed` 取第一個（…與第 12 點的優先序一致）。」，照風控 2026-10-19 原字。
  - L3930 的 N-5 修訂紀錄引文沒有動。
- **2-C**：對實作的約束 FL-71 (i)（L2552 一帶）。
  - 首尾為「（N-23 Q3；事先宣告 v0.22 LG-33）checkpoint 列：(1) 同一份資料…」到「…(15) 單一對象與多對象各一組。」，接在「該 T 的 daily 與 checkpoint 列全部不寫。」之後、「Q3 部分 claim」之前。
  - 只有 (13) 換成風控版，(1)～(12)、(14)、(15) 照 TA。
  - 格式處理：FL-71 (i) 原本是單一長列，(1)～(15) 順接在原句後，沒有另起列，字句未增減。
- **2-D**：D-11 第 2 點 seed 的兩處（L1388、L1390）。
  - L1388 首尾為「`eval_key` 前瞻用該列的 `n`，寫成 `n{n}`（十進位、不補零，例如 `n30`；…）」到「…〔N-23 Q3 取代（事先宣告 v0.22 V22-03）：原寫「…」〕」。
  - L1390 首尾為「**`eval_kind` 刻意不放進導出式**：同一 n 的 daily 列與 checkpoint 列用同一組 seed，…」到「…〔N-23 Q3 取代（V22-03）：原寫「…」〕」。
- **2-E**：Consequences，接在「（剩餘待決項，N-5 甲案）**甲案的殘餘**」之後、同一層（L2222、L2223）。
  - 第一點是風控第四節 tech-writer 第 3 點全文，括號插在「【推論，未量測】」之後、「。兩者都在」之前。首尾為「（N-23 Q3；事先宣告 v0.22 第 2、4 點）**延後判定的殘餘**：…」到「…最終責任由 CEO 負〕」。
  - 第二點首尾為「（N-23 Q3；N-38 G-1；事先宣告 v0.22 V22-06）**沒有期限的待重算項（補法 α）的另一面**：…」到「…〔風控 2026-10-19 checkpoint 批確認：知悉級，最終責任由 CEO 負〕」。
- **2-G**：修訂紀錄檔尾新開一段，標題為「N-23 checkpoint 批（乙案；D-11 第 2、3 點、D-11.4 第 2b 點與第 12 點 (ii)、Consequences、FL-71 (i)、FL-54 (e)；方向：補定義（兩面））」，起於 L4638 一帶。
  - 逐項記方向、CEO、風控出處。
  - 錄存 (i)：觸發範圍限「該 claim 的 E 內、T ≤ T\*_j」，TA 原稿的「非空」從未寫入。
  - 錄存 (ii)：整批方向寫「補定義（兩面）」。放寬面原文逐字取自風控乙案裁定第二節 B 的 Q-a、Q-c、Q-d，並附 α 另一面原文。風控出處指向 `work/reviews/2026-10-19-checkpoint批與v0.22逐字確認-風控.md`。
  - 2-B 兩處被取代原文已逐字錄存。2-D 寫「已逐字錄存於正文〔取代〕，本段不重錄」。
  - 另註明 TA 2026-10-18 原稿從未寫入、不落檔。
  - 「本批沒有落檔」列出 2-F、2-H、G-2 ADR 側落字、有標籤預測 `threshold_snapshot` 缺項規則，來源是風控第四節。

### N39
- **N39-1**：D-11.4 第 2b 點（L1510）。首尾為「（N-23 Q3；風控 2026-10-19 N-39）D-4 的區間、n、期間，與同一回應中的…」到「…不得改寫成 `checkpoint_n`。」首段接在原句句末，五個子點為其下一層。
- **N39-2**：D-11 第 3 點（L1416）。首尾為「（N-23 Q3；N-39）同一 claim、同一 T 有 checkpoint 列時，…」到「…（事先宣告 §4.5「檢查點的判定樣本、時點與 seed」第 6 點，v0.22，V22-08；與 §4.5 狀態表「…」一致）」。句末括號已換成風控字句。
- **N39-3**：FL-54 (e)（L2766）。首尾為「（N-39）同一 T 有 checkpoint 列（n＝30、升級）與 daily 列（n＝35）→ …」到「…讀 checkpoint 列的地方是 0 處（AST）。」，接在「（`outlook_view` 只讀一次 snapshot 列）；」之後。

## 三、驗證（grep 實際計數）

| 項目 | 實際 |
|---|---|
| `snapshot_skipped` | **1**（L2552，見第四段第 1 項） |
| `【α】` | 0 |
| `` `unbounded_pending` 非空 `` | 0 |
| `UNIQUE(claim_id, checkpoint_n)` | 正文 1（L1326）；修訂紀錄 0 |
| `cause ∈ {suspended_f3, db_restored}` | 只剩修訂紀錄的 2 處引文（L4662、L4664），正文 0 |
| seed 脈絡的「ISO 日期」 | 只剩 L1388 的〔取代〕引文；全檔另有 L275（市場資料欄位，無關）與 L1350（2-A 的 `phase0_grid_sha256` 格式，TA 字面） |
| 「同一個檢查點兩個原因同時成立時」 | 1 處，L3930（原約 L3865 的 N-5 引文） |
| 「屬於該 claim 的 E、而且 `reason = write_validation_failed`」 | 1（L1330） |
| 「其中有 T ≤ T\*_j 者時，改使該檢查點的正面結果不認列」 | 1，在 Consequences（L2222） |
| 風控「第四節 tech-writer 第 3 點」原文 | 逐字存在於 L2222，含新插入括號 |
| 「沒有期限的待重算項（補法 α）的另一面」 | 存在於 L2223 |

## 四、下一步（偏離與需要你裁示處）

1. **`snapshot_skipped` 是 1 處，不是 0。**
   - 來源是 2-C 第 (14) 格末句「`app/` 與事先宣告內沒有 `snapshot_skipped`（grep）」。
   - 風控說 2-C「照 TA，只有第 (13) 格換字」，所以我照原字落檔，沒有自行刪句。
   - TA 的 2-A 錄存本意是讓這個字串在 ADR 內為 0，與自己的 (14) 矛盾。
   - 請 coordinator 或 TA 裁定：改寫 (14) 末句，或放寬機械核對。
   - 我沒有在修訂紀錄裡寫這個識別字。
2. **2-B 第三處被取代原文（第 12 點 (ii) 首句）沒有重錄進修訂紀錄。**
   - 重錄會讓「同一個檢查點兩個原因同時成立時」變成 2 處，違反你的核對（只剩 L3930 一處）。
   - 該句與 N-5 修訂段所引同一子項的首句逐字相同，已存在於 L3930。
   - 修訂紀錄裡改為指向該處，原文沒有無痕刪除。
   - 若你要求逐字重錄，核對數字就要改成 2。
3. 修訂紀錄裡 2-E 第一點的插入括號寫「字句見該點正文」，沒有重錄，避免重複出現。
4. 修訂紀錄「本批沒有落檔」與 N-38 一句，是我依風控檔第一節與第四節 coordinator 段整理的 B 類敘述。字句如需調整請告知。
5. 範圍外但值得注意，未改動：`FL-47`（L2581）仍寫「每個值等於導出式的結果（即 LG-20）」。`eval_key` 改為 `n{n}` 後，它的測試語意是否需要同步，請 TA 確認。

佐證清單：本批全為 B 類（轉錄），來源為上述三份 `work/reviews/2026-10-19-*.md`，落檔後以字串定位；行號會漂移。我沒有跑 git，工作樹快照無 commit，抽驗時請以原文字串定位。
