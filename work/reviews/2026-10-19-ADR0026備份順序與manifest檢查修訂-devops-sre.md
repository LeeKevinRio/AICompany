# ADR-0026 備份順序與 manifest 檢查修訂（含依 N20-10 對齊）

- 審查者：devops-sre
- 日期：2026-10-19
- 轉存：coordinator，逐字轉存 subagent 回報，共 2 份，依時間順序

---

## 一、本次結論

已完成 ADR-0026 的修訂，只改文件，沒有 commit 或 push。ADR-0026 狀態是 `proposed`，所以依 ADR-0001 直接在本檔原地修訂，不必開新 ADR。

檔案：/home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md（`git diff`：+76／-3，只有我的改動）。

要求逐項對照：
1. **備份順序**：已加在 D-9 第 2 點之後、同一層。字句照風控第四節 devops-sre 第 1 點逐字。編號用「2-1」，不讓後面各點改號，因為 ADR-0027 已引用 D-9.3、D-9.4。
2. **manifest 三項**：已寫在 2-1 之下，有 (a) 備份完成與開始時刻、(b) 參考 run 與 `recorded_at`、(c) 檢查結果。D-9 第 2 點的 manifest 一句句末接了「另加記 2-1 點所列各項」，原句不變。
   - 參考 run 的取法與 ADR-0027 D-9.2「R 倒退」一致：最後一列 `forecast_settle_eval.market_run_max`，與最近一個已完成更正作業的 `market_scan_to`，取較大值，沒有列的一方不計。
   - `recorded_at` 用原字串相等（SQL `=`），不解析、不比大小。
   - 檢查沒通過的備份組標為不可用於整檔還原，並記 WARNING。
3. **D-9 第 4 點**：已加入風控字句（逐字）、解除路徑只有一條（用通過的組重做，或修訂本點，不新增解除用工具），並寫明規定落地前已存在的備份組怎麼處理。
4. **修訂紀錄**：ADR-0026 原本沒有「修訂紀錄」節，我在檔尾新建。逐項標了方向與 CEO 欄，被取代的原文逐字錄存。五項是收緊、一項是更正指向（不變），CEO 欄全部填「否」。
5. **status**：proposed，已照上述處理。
6. **N-40**：已寫進「未查證事項與作者揭露」，列為待驗證，沒有實測。

## 二、各部門回報（devops-sre）

**我自己起草、風控沒給逐字稿的部分，請風控確認：**
- **舊組處理**：沒有 2-1 的順序時刻、參考 run 與檢查結果的備份組，一律視為「未檢查」，等同沒通過。這包括落地前產生的組，也包括落地後、ADR-0027 N-20 欄位存在之前產生的組。
  - 不推定為通過，不補寫 manifest，不做補檢工具。
  - 舊組依既有保留規則自然過期。
  - 落地當天由操作者依新順序手動做一組新備份，縮短空窗。
  - 災難時若沒有任何通過的組，不得自行改用舊組，升級 CEO 與 devops-sre，決定前不得改動 DB。
  - 這個空窗代價要讓 CEO 知悉。
- **無參考 run**：兩方都沒有列時，記「無參考 run」，(c) 不適用，不算未通過。這與 ADR-0027「沒有參考值就不檢查」同處理，也與 data-engineer 第二節 5 的實作約束 3 一致。
- **fail-closed**：有參考 run，但主 DB 備份沒有存 `recorded_at`，算未通過。
- **欄位名**：`restore_usable` 與 N-20 的 `recorded_at` 欄位名都標暫定，以 ADR-0027 定案為準。

**超出你列的要求、但為了一致性所做的兩處最小改字，原文已逐字錄存：**
- D-9 第 2 點第一子點「在同一時點各做一份」改為「各做一份……先後順序依 2-1」。不改的話，會與 2-1 的「不得並行」互相矛盾。
- 待決事項 devops-sre 一欄的「D-9.4 的四條規則」改指全部規則，並加上 2-1。D-9.4 已經不止四條。
- 如果你不要這兩處，可以回退。回退後矛盾和過期的數字仍在，要另行處理。

## 三、驗證

- 讀過的檔案：
  - ADR-0026 全文；
  - 風控 2026-10-19 裁定全文；
  - data-engineer 2026-10-18 查證全文；
  - ADR-0001；
  - ADR-0027 L1098～1111（D-9.2「R 倒退」）。
- `git diff` 確認 ADR-0026 只有我的改動。
- 沒有跑 `validate_agents.py`，因為只改了 ADR，沒動 agent 或 org-chart。
- 沒讀 `.env`，沒碰 `apps/stock-desk/backend/data/*.db`，沒有 commit 或 push。
- **要注意**：`git status` 顯示 ADR-0027 也有未提交的改動（+23／-12）。那不是我改的，應該是 tech-architect 的 N-20 改寫。同批送風控時，兩份要一起處理。

## 四、下一步

1. coordinator 把 ADR-0026 連同 tech-architect 的 N-20 改寫同批送風控確認。擋點是：身分比對的實作，要等這批確認落檔之後才能開始。
2. 以下幾點供 tech-architect 與風控確認：
   - 2-1 引用的 N-20 欄位（`market_run_max_recorded_at`、`market_scan_to_recorded_at`）名稱，要與 ADR-0027 最終稿一致。
   - **F-8**（備份組連續 3 天沒有成功產出）：「檢查沒通過」是否算沒成功產出，現文沒定義，我沒有擅自加。
   - **新增 IV 條款**：2-1 的檢查目前沒有對應的 IV 條款與 IT 測試（data-engineer 建議的「備份順序顛倒」與「還原後重號」兩格）。建議由 qa-reviewer 與 tech-architect 補，我沒擅自加。
3. 部署手冊 §4 與 §5（R-Q7-6）仍待我更新，這次依指示沒動，§5 仍擋 D_v。
4. N-40 的 WAL 驗證是 suggested。有空檔時我再做，結果回報 data-engineer 與 tech-architect。

---

## 一、本次結論

ADR-0026 D-9 第 2-1 點已對齊 tech-architect 的 N20-10 與 4-C，四件事都完成。只改 ADR-0026，沒有 commit 或 push。

檔案：/home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md（`git diff` 為 +105／-3，含上一輪的改動）。

(1) **身分三欄**：(b)、(c) 改成 `{recorded_at, kind, session_date}`。主 DB 端欄位名用 `market_run_max_identity_json`、`market_scan_to_identity_json`、`market_run_current_identity_json`。比對規則是三欄原字串相等（SQL `=`），`session_date` 兩邊都是 null 時算相等，不解析也不比大小。

(2) **第三個候選**：加了 `forecast_gap_audit` 中 `market_run_current` 最大的一列，同值時取 `audit_id` 最大者。三方取法與 ADR-0027 D-9.2 一致：
- 沒有列的一方不計。
- 取值最大的候選記為參考 run。
- 同值時依 settle_eval → correction_job → gap_audit 取第一個。

(3) **擴為三方**：「兩者相等／兩者取大」改為三方。多個候選指向同一個 run 時，各候選存下的身分都記入 manifest，而且都要通過檢查。

(4) **暫定欄位名**：N-20 的 `recorded_at` 欄位名已換成上述三個 `*_identity_json`。`restore_usable` 是本 ADR 自己的 manifest 欄位，維持暫定。

## 二、各部門回報（devops-sre）

- 「檢查沒通過」的條件隨之改為三項：
  - run 在市場 DB 備份中不存在；
  - 身分三欄有任一欄不相等；
  - 有參考 run，但主 DB 備份沒有存下該候選的身分（無法比對，fail-closed）。
- 修訂紀錄新增第 7 項，內容如下：
  - 標方向為收緊，CEO 欄為否，依據是 N20-10、4-C。
  - 被改掉的本日中間稿（未 commit）逐字錄存。
  - 最後一行說明哪些落字是 devops-sre 起草，請風控與 tech-architect 確認。
  - 上一輪「待風控確認」清單裡的「沒有存 `recorded_at`」已改為「沒有存身分」。

**我對 N20-10 的落字，請風控與 tech-architect 確認：**
- 三方取最大值，且同值時各候選都要通過。
- 取到的最大值為 0 時，視為無參考 run，不算未通過。這與 4-B 的 v_c＝0 規則一致。
- 4-B 的 (b) 規則在 manifest 端的對應做法是「run 存在且三欄相等」，我沒有另外實作 `r_now ≥ v_c` 的判斷，因為備份檢查沒有 r_now。

## 三、驗證

- 讀過的檔案：tech-architect 回覆第二節 4（4-A、4-B 的 N20-1～N20-10、4-C、對實作的約束第 8、10 點）。
- 編輯後用 grep 確認，條文內不再有單一 `recorded_at` 的舊敘述。剩下的 `recorded_at` 只出現在新條文的三欄說明，以及修訂紀錄的逐字引文。
- 目前只改了 ADR-0026，沒有碰其他檔案。
- 沒讀 `.env`，沒碰 `*.db`，沒跑程式或測試，沒有 commit 或 push。
- 先前回報的內容仍有效，只是 2-1 的細節以本次為準。

## 四、下一步

1. 這一版與 ADR-0027 N-20 批同批送風控確認，確認前不 commit。
2. 對齊檢查：tech-architect 的約束第 10 點要求 2-1 先落檔。目前 2-1 已就位，但 ADR-0027 的 `*_identity_json` 欄位名要與本檔逐字一致，落檔時用 grep 核對。
3. 本次沒有新增 IV 條款或測試。manifest 檢查的測試（備份順序顛倒、還原後重號、三欄任一不符）仍建議由 qa-reviewer 與 tech-architect 補。
4. N-40 的 WAL 驗證仍是 suggested，未實測，結果之後回報 data-engineer 與 tech-architect。
