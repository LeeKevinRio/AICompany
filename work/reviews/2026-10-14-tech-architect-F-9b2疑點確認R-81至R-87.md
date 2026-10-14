# F-9b2 實作疑點確認（TA8 R-81～R-87）— tech-architect

> 轉存：coordinator，2026-10-14，子 agent 回報逐字轉存。coordinator 註：R-82 殘留情境與 R-87（2e）已分別由風控 F9W-57、F9W-54 裁示接受（`work/reviews/2026-10-14-F-9b2-字面落地與2e交互-F9W-53至F9W-57-風控.md`），不另送風控。

---

## 本次結論

tech-architect（唯讀）對 F-9b2 六個疑點的確認：**沒有 BLOCKING。** 六點都同意實作者的做法，其中第 1 點附一項非阻擋的補強建議。本輪編號 **R-81～R-87**（我先查過，ADR-0024 與 `work/` 內最大號是 TA7 的 R-80，R-81 起沒有被用過），以下稱 TA8。

| 疑點 | 結論 |
|---|---|
| 1 `rejection_marker` | 同意保留獨立的 keyword-only 必填布林，不改成綁 `wording is not None`；建議補一條建構期不變式（R-81） |
| 2 合併讀回被擋不寫標記 | 同意，符合 D-9 與 F9W-20 的意旨（R-82） |
| 3 W-c′＋通過閘門的快取仍寫 `unit_missing` | 同意，符合 D-9、D-7 (2)、F9W-24（R-83） |
| 4 先讀快取並判定閘門，再走標記步驟 | 同意，維持現行順序，不調整（R-84） |
| 5 ADR-0019 T-5 由後合者處理 | 同意，與 ADR-0024 文字一致；另給 ADR-0019 實作者一條約束（R-85） |
| 6 ADR 補註 | 有 R-86、R-87 兩項，外加 R-81～R-85 的對應補註（合併後由 tech-writer 落檔） |

## 各部門回報

### tech-architect

#### 1. `rejection_marker`（R-81）：同意方案 A，附補強

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A：獨立必填布林（現況，採用）** | 字面上符合 TA5 R-59「由建構點顯式設定」；deps 三處用字面常數寫明，AST 測試已釘住；「跨呼叫記憶」與「使用者面字面」維持兩個獨立開關 | 多一個必填參數；現況下「股票＋有字面＋False」可以建構，而這個組合違反 D-2 (3)、F9W-4 (b) | 低：production 只有 deps 一處建構，AST 已釘成 True／True／False |
| B：綁在 `wording is not None` | 不必多一個參數 | 把兩件風控分開裁定的事綁在一起：F-9c role 2 合併前，T-16 指數字面必須先核可；指數一旦拿到字面，B 會自動開啟指數的標記讀寫。但指數是否適用 D-2 (3) 是 F9W-38 (a) 指定另回風控重審的事項，不能隨字面一起生效 | 中：日後會靜默改變指數的跨呼叫行為 |
| C：由 `scope` 推得 | 不必多一個參數 | 讓 `scope` 再多帶一種行為語意；F9W-38 (a) 重審若改變結論，得改 `scope` 的語意 | 低～中 |

決定採 A。否決 B 的關鍵理由就是上表 B 列那一點。

補強（非 BLOCKING，建議在本 PR 補上；不補的話，要在 PR 說明記為「已知可以建構出來的違規組合」）：

- 建構子加上 `if rejection_marker != (scope == "equity"): raise ValueError(...)`。
- 保留現有「True 必須有 wording」的檢查。
- 補一則測試：「`scope="equity"`、有 wording、`rejection_marker=False` → raise」。

理由：D-2 (3) 對股票路徑沒有可關閉的版本。這一條讓唯一的違規組合在建構期就被擋下。F9W-38 (a) 若日後要讓指數讀標記，改這一行就是明確的、需要 ADR 的動作。

#### 2. 「沒有任何一層取得可用資料」的解讀（R-82）：同意

- 定義：「取得可用資料」指本次有某個 live rung 的結果通過了 live 幣別閘門，也就是它已經 `cache.put`，並在迴圈內 `record_attempt` 清掉標記。之後回覆能不能組成（合併讀回被擋，或讀回為 None）不影響這個判斷。
- 依據是字面要屬實：
  - T-14 與 C′ 的後半句都是「最近一次向來源取得的日線…整段不採用」。
  - F9W-20 把「沒有任何一層取得可用資料」列為 C′ 的適用前提。
  - 該 rung 的列已被採用並寫進快取，這時寫標記會讓下一次點擊的 T-14／C′ 不屬實。
- 不寫標記時，下一次點擊的走向（皆不需新字面，也不會在被擋的快取旁出價格）：
  - 讀回被擋：快取有壞列，冷卻期內落在第 4 步回 T-15，冷卻期外走第 4 步整段重抓。
- 殘留（記錄即可，不改）：
  - 情境：先有 rung 取得資料、讀回為 None，之後有備援 rung 回 W-c。
  - 結果：下一次點擊冷卻期內可能經 R-8，以 `RECENT_ATTEMPT_FAILED_REASON` 回通過閘門的快取。
  - 可達條件：`cache.get` 只有在範圍內完全沒有列（或全部是壞列）時才回 None，而剛 `put` 完的尾段列不會不見，所以只有另一程序刪列或列損毀的競態才會發生。
  - 為何可接受：被服務的列由主來源背書過單位。若改成寫標記，T-14 的「本機尚無此標的可採用的日線資料」反而不屬實。
- `test_a_refused_read_back_after_a_usable_rung_writes_no_marker` 與 M18 已釘住這個行為。

#### 3. W-c′＋通過閘門的快取仍寫 `unit_missing`（R-83）：同意

- 快取不算梯子的「層」。D-7 (2) 已明寫「各層的拒收類別只用於 D-9 標記的寫入判斷，不帶到帶 bars 的回覆上」，等於預設了這個情境要寫標記。
- F9W-24（T-17）的情境「有效 W-c′ 標記＋可採用的快取」只能由這一步產生。不寫的話，T-17 會變成不可達的死規則。
- 對下一次點擊的效果：
  - 快取可採用時，第 5 步的分支與沒有標記時完全相同（同一個 `last_attempt_at`）。
  - 只有請求範圍內沒有快取列時，答案從 `COOLDOWN_NO_CACHE_REASON` 變成 C′。C′ 的「本機尚無…可採用」以本次請求範圍判定，與第 3 步既有的語意相同，屬實。

#### 4. 先讀快取並判定閘門，再走標記步驟（R-84）：同意維持，不調整

- D-2 (5)(a) 本身就寫「在讀出整段快取後、所有分支之前檢查一次…再依下列順序判定」，第 3 步也需要「可採用的快取」這個結果。
- D-4 (b)（F9W-31 (b)）要求每個拒收的檢查點各記一筆，不論最終回覆是什麼。這筆 `scope=equity` 的 WARNING 屬實（快取確實有壞列），也正好是 F-9e 要清理的目標，有維運價值。
- 次數有上限：每次點擊一筆，只在 W-c 冷卻期內；冷卻期外第 2 步本來就會走梯子。
- 替代做法是「先讀標記，命中第 1、2 步就不讀快取」。它不會改變第 4、5 步，但會改寫 ADR 已定的「一次讀、一次判定」，也會讓記錄依標記而有無，只換來少一筆 WARNING。**不採。**
- C-33 的「快取沒有被讀取」只約束同一次呼叫中 live W-c 之後的降級路徑，與這裡無關。

#### 5. ADR-0019 T-5（R-85）：確認一致

- ADR-0024「PR 拆分與順序」寫「先後皆可，後合者負責 rebase 並重跑 T-5」。F-9b2 先合，ADR-0019 就是後合者，由它寫 T-5、在 F-9b2 之上跑。
- T-5 的情境是上次提問成功，此時 `attempted <= last_fetched_at`，標記依有效條件必然無效，F-9b2 不會改變 T-5 的結果。
- 給 ADR-0019 實作者的約束：
  - F-9b2 把 `attempted > last_fetched_at` 的比對放在 `cache.py` 的 `last_attempt`（SQL join）與 `_valid_marker`，這是 ADR-0024「關聯」所說「ADR-0019 K-3 允許的 R-8／D-8 用途」。
  - K-3 的 grep 檢查須把這兩處列為允許位置。
  - 這兩處不得改用 `tail_fetched_at`：標記要比的是「最後一次完整成功」。

#### 6. ADR 補註（R-86、R-87）

**R-86（事實更新，不改決策）**
- **T-14 已採用**，兩市場全面使用；C 版沒有任何產生端會發出。待決事項 T-14 列、D-2 (5)(a) 第 1 步、D-9 冷卻字面、C-13 (6)、PR 表 F-9b2 列都要對應註記。
- **F9W-49**（ADR 目前完全沒提）：
  - (a)(b)(d) 由 F-9b2 第 1、3 步關閉；其中 (d) 有快取時的 RECENT 由第 1 步取代為 T-14。
  - (c) 是 F9W-24 的最終行為。
  - 壞處 3 的「A 版暫行」在 F-9b2 合併後結束。
  - F-9c 硬性前提 2 改標「已滿足」，但 role 2 的條件照舊。

**R-87（送風控知悉）**
- 第 2 步「冷卻期外、梯子全部靜默失敗、快取通過閘門」時，`_fall_back_to_cache` 的「現行規則」在 F11-W-38 之後會帶 `RECENT_ATTEMPT_FAILED_REASON`。TA5 R-64 寫成、風控知悉時，這裡的 reason 是 None。
- 判斷：不是新字串組合，句意屬實（本次梯子剛失敗），也比沒有標記時更保守（會先問來源）。ADR 決策不改，只在 D-2 (5)(a) 第 2 步句尾補註「現行規則含 F11-W-38」。
- 釘住的測試是 `test_step2_then_a_silent_ladder_falls_back_under_the_usual_rules`。

**R-81～R-85 對應的 ADR 補註**

| 位置 | 補註內容 |
|---|---|
| C-6 與 D-4 指數段 | 加上「`rejection_marker` 由三個建構點顯式設定（股票 True、指數 False），AST 測試釘住；建構期拒絕與 `scope` 不一致的值」（R-81） |
| D-9「設定」 | 補「取得可用資料」的定義，與上述讀回 None 的殘留（R-82） |
| D-9「設定」 | 補「快取不算梯子的層；W-c′＋通過閘門的快取仍寫 `unit_missing`」（R-83） |
| D-4 (b) | 補「第 1 步加上快取被擋時，每次點擊仍留一筆 `layer0_cache` WARNING，屬預期」（R-84） |
| 「關聯」ADR-0019 條 | 補 K-3 允許位置（R-85） |
| 檔頭優先序 | 加入「TA8 R-81～R-87」，位於 TA7 之前；風控裁定仍優先於全部 tech-architect 項 |

### 對實作的約束（給 dev-lead；逐條可由 qa-reviewer 檢查）

1. 建議補建構期不變式 `rejection_marker == (scope == "equity")` 與對應的 raise 測試（R-81）。
2. 第 4、5 步的程式與既有測試零改動。合併前重跑 F-9b 的 `test_f9b_cache_currency_gate.py` 與 `test_f9b_live_currency_gate.py` 全綠。
3. 以下測試不得放寬：
   - `test_the_cache_gate_is_judged_before_the_marker_steps`：layer 序列恰為 `["layer0_cache"]`（R-84）。
   - `test_a_refused_read_back_after_a_usable_rung_writes_no_marker`（R-82）。
   - `test_a_w_c_prime_beside_a_passing_cache_still_leaves_its_marker`（R-83）。
4. 股票建構點維持 `cache_first=True`（`test_cache_first_is_on_for_every_ladder` 已釘住）。這是冷卻期內標記守門生效的前提：關掉 layer 0，第 1～3 步就不會執行。
5. PR 說明 (i) 第 1～4 點改寫成引用 R-81～R-84；(g) 2e 引用 R-87。

## 驗證

- 讀過的檔案：
  - worktree `/home/user/AICompany/.claude/worktrees/agent-a23c8918520245bb9` 內的 `apps/stock-desk/backend/app/data/service.py`（建構子、`get_daily_bars`、`get_cached_bars`、`_marker_to_write`、`_try_session_fresh_cache`、`_marker_step`、`_layer_zero_answer`、`_fall_back_to_cache`）、`app/data/cache.py`（遷移、`_valid_marker`、`record_attempt`、`last_attempt`、`get`）、`app/api/deps.py` 三個建構點、`tests/market_service_helpers.py`、`tests/test_f9b2_marker_guard.py`（測試清單與建構、寫入相關段落）、`work/stock-desk-F-9b2-PR說明-2026-10-14.md`。
  - `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md` 全文；ADR-0019 的 K-x 與 T-5。
  - 風控裁定 F9W-20～F9W-24（字面原文）、F9W-49；TA5 R-59、R-64、R-67。
- 自我揭露：
  - 全程唯讀：未改檔，未執行 git、pytest 或任何指令，未讀 `*.db` 或 `.env`。
  - 沒有確認 worktree HEAD 是否等於 a2f8b2a。PR 說明列的最後一個程式 commit 是 2102506，我推測 a2f8b2a 是 PR 說明的 commit，但未查證。
  - mutation M1～M21 與各 commit 的 pytest 數字是 PR 說明所載，我沒有重跑。
  - R-82 殘留的「只有競態才可達」是我依 `cache.get` 只在範圍內無列或全部壞列時回 None 推得，沒有測試實證。
  - `test_f9b2_attempt_log_marker.py` 只看了測試名稱，沒有逐則讀斷言。

## 下一步

1. **dev-lead**：決定是否在本 PR 補 R-81 的不變式；改寫 PR 說明 (i)，送 qa-reviewer＋Codex。
2. **coordinator**：把本回覆存成 `work/reviews/2026-10-14-tech-architect-F-9b2疑點確認R-81至R-87.md`；R-82、R-87 轉風控，**只需知悉**（R-82 會讓競態情境由 C′ 改回 T-15，R-87 是 F11-W-38 改變了 R-64 知悉時的前提）；字面的逐字審照 PR 表走。
3. **tech-writer**：F-9b2 合併後，依 R-81～R-87 在 ADR-0024「合併後更新」節追加補註，並更新檔頭優先序；不改決策本文。
4. **ADR-0019 實作者**（日後）：依 R-85 處理 K-3 的允許位置，並在 F-9b2 之上寫、跑 T-5。
