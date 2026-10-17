# Phase 1 探測指令 §6 補查項回報 — data-engineer

> 轉存：coordinator，2026-10-17，子 agent 回報逐字轉存。

---

## 本次結論

已在 `/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 新增「§6 補查項（2026-10-17）」。只新增、未改既有文字：diff 為 +993／-0，原 891 行逐行比對一致。沒有連網，沒有讀 `.env`，沒有碰 `*.db`，沒有改程式，也還沒 commit。

**§6 的重要發現**（均為讀碼，沒有實測）：
1. **A-16 條件（觀察日只來自最終日線）以目前程式無法確認成立。**
   - `PriceBarCache.market_trading_days` 是 `SELECT DISTINCT trade_date`（`cache.py:459-503`）。任何來源、任何一個序列有該日的列就算交易日，沒有「最終」的概念，也沒有最少檔數。
   - `^TWII`（market 為 TW）走同一張表（`api/deps.py:170-178`、`services/index.py:303`）。若 Yahoo 盤中回傳當日進行中的 bar，該日盤中就會被算成交易日。
   - 這個口徑不排除 `demo_synthetic`，而姊妹方法 `market_has_session` 有排除（`cache.py:358-378`），兩者口徑不一致。
   - 寫入快取前只過**幣別**閘門（`service.py:334-353`）。`check_price_bars`（未來日期、OHLC、重複列）在 `app/` 內沒有任何呼叫者，只有測試用。所以「通過品質檢查」現況只等於通過幣別檢查。
   - `ObservedSessionCalendar` 尚未實作（`app/data/` 沒有 `session_calendar.py`、`close_state.py`、`market_hours.py`），所以輸入口徑還能選。
   - 市場 DB 的 `bars` ok run 比快取更接近「最終」：覆蓋率要 ≥ 0.98，並經 FinMind 自證。但排程啟動時會立刻跑一次（`scheduler.py:660-672`），我沒看到時段防護。
   - 我只列事實與選項，輸入口徑歸 tech-architect 決定。
2. **目前沒有任何轉接器防「當日未定案 bar」。**
   - TWSE、TPEx、FinMind 只過濾日期窗，並丟掉 `--` 無成交列。yfinance 的 bar 日期取 UTC 日期。
   - `as_of` 是抓取時鐘，不是來源資料時間。
   - 寫入是 upsert，但 `judge()` 在 15:00 後見到最新日的 bar 就不再重抓。暫定值因此可能留到下一個交易日。
3. **B-2：個股 claim 範圍大概已把槓桿／反向 ETF、國外成分 ETF 排除在外。**
   - 依據是 ADR-0027 D-4，加上 listing 來自 per-company 的 `t187ap03_L`。
   - 但持倉資料鏈的准入規則只擋「數字加 K」，`L`、`R`、`B`、`U` 結尾的代號會放行（`admission.py`）。
   - 「`t187ap03_L` 沒有 ETF 列」只有程式註解，沒有實測紀錄，§6 用一次請求驗證。
   - 「新上市前 5 日」「減資恢復首日」是否真的不設限，**我沒有任何官方出處**，全部列為待人工查證。
4. **V6-11 族群 σ_d：阻礙在除權息，不在日線。**
   - 日線有暖身回補：FinMind 逐檔至少 80 日，D0 前執行，D0 後 CLI 拒絕執行（`pit_snapshot.py`），夠 61 個收盤。
   - 除權息來自每日 `TWT48U_ALL`（只列未來日期）累積，沒有歷史回補。
   - 因此 D0 的 60 日窗內，除權息涵蓋起點很可能晚於窗起點，族群會輸出 `E-ADJ-COVERAGE`（fail-closed）。這是推論，要看 CEO 本機 DB 與常駐時點才能定論。
   - 另兩個風險：暖身價是原始價還是還原價仍未知；B1／B4 在 D0 之後最初 h 日需要 D0 之前的 listing 快照。
   - 暖身約需一千多次 FinMind 請求，額度未知。若不足，依章程升級 CEO。
5. **時程提醒：** 今天 2026-10-17 是週六。6.3 最早的交易日是 2026-10-19（週一），以官方休市表為準。

## 各部門回報

**data-engineer：新增小節與逐項分類。** 新增 §6.0 總覽與前置、6.1～6.6、6.7 總回貼清單、6.8 人工判讀總表。helper 沿用 `probe_lib.sh`（限速、`.STOP`、不轉址），另寫 `probe_lib_s6.sh`（`s6_snap`、`s6_extract`、`s6_compare`）。輸出放 `$PROBE_DIR/s6/`。每項都有回貼範本 S6-1～S6-6。

| 項 | 讀碼結論 | 推論 | 需 CEO 代跑 | 仍須人工判讀 |
|---|---|---|---|---|
| 6.1 VS-6／VS-2／VS-3 | `quote_params.py` 的 09:00 與 `freshness.py` 的 15:00 都不是官方出處；`market_hours.py` 不存在 | 無 | 約 2 次請求：swagger 文字搜尋（不連網）加 TWSE 首頁連結探測 | **數值只接受官方原文加網址加讀到日期**。附逐字抄錄表與三個語意問題（08:30 起算什麼動作、13:25 集合競價與 13:30 的關係、有無調整條款） |
| 6.2 週六補行 | `calendar.py` 觀察範圍內有 bar 即算交易日；`freshness.py` 只認週一至週五，會低報過舊 | 若有補行，隔天觀察到 bar 才修正（同 ADR-0028 D-6 第 4 點） | 三證據：A 休市表逐列檢視（重用 §1.3 檔案）、B FinMind 交易日曆 2020 起 1 次請求、C 本機 DB 週末 bar（唯讀複本） | 官方網頁註記原文；歷史觀察不能寫成「不會有」 |
| 6.3 當日暫定 bar（Q-B7、F-2、F-3） | 見上方發現 2 | 暫定值可能留存；兩來源回傳同一暫定值時，市場 DB 自證會通過；Yahoo 盤中通常含進行中 bar（無本 repo 實測） | **必須交易日分時段**：最低 `t1030`、`t1335`、`t2130` 三輪，選跑 `t1320`、`t1505`、`t0830n`；每輪約 6 次請求，加 `all` 為 8 次，涵蓋 TWSE、TPEx、FinMind、Yahoo（`^TWII` 加探索性 `2330.TW`）和兩個整市場檔；`s6_compare` 自動比對；附判讀矩陣 | 單日不能當規則；結算日、颱風日、FinMind 更新時程無法由單日推定 |
| 6.4 觀察日來源 | 見上方發現 1，附 7 項事實表加行號 | 市場 DB ok run 較接近最終；若沿用快取至少要排除指數與 demo、要求最少檔數、以 `fetched_at ≥ VS-4` 判最終 | 唯讀複本診斷 A～D：低支持度日期、盤中抓取未被覆蓋的列、快取與市場 DB 日期差異、ok run 的擷取時段 | 輸入口徑與是否接上 `check_price_bars` 歸 tech-architect |
| 6.5 無漲跌幅商品（B-2） | 見上方發現 3 | ETF 排除的前提是 `E-SCOPE-TYPE` 以 listing 且 `common_stock` 判斷；新上市靠 σ60 與上市滿 60 日擋；減資恢復首日不被擋，但屬公司行動 | 約 4 次請求：`t187ap03_L`、swagger 漲跌停關鍵字、猜測的 `TWT84U`（404 可接受），以及代號格式與 ETF 存在性分析 | **規定原文**（表列 8 種情形）必須人讀；LM-63 二選一歸風控與 quant |
| 6.6 族群 σ_d（V6-11） | 見上方發現 4 | 阻礙在除權息（結構性），暖身價是否還原待 §3.3 結果 | 唯讀複本診斷 A～E（D0、窗內有效報酬分布、除權息涵蓋起點對窗起點、暖身進度）加 `fm_quota` | 還原口徑、覆蓋門檻是否可行、是否另建回補來源（會牴觸 PIT 紀律，屬新資料源決策）歸 quant 與 tech-architect |

## 驗證

- 把 §6 的 21 個程式碼區塊逐一用 `bash -n` 檢查，全部通過；內嵌 python 全部 `compile` 通過。
- 另外用**合成資料**（不連網）實際執行了這些腳本：`s6_extract`（TWSE、TPEx、FinMind、Yahoo、整市場、壞檔、無檔）、`s6_compare`（含 sha256 差異旗標）、6.2 的休市表分析、6.2 C、6.4.3 的 A～D、6.5 E、6.6.3 的 A～E。輸出符合預期；過程中修正了 `s6_compare` 的方向性訊息，並補上整市場檔的 sha 差異旗標。
- **沒有任何真實端點被驗證**：全部端點、資料集名稱與欄位都是候選。`TWT84U`、FinMind 交易日曆資料集名稱是印象，已在文中標註。
- 指令中沒有 token。FinMind 只經既有 `fm` helper 讀 `$FINMIND_API_TOKEN`。DB 腳本以 `mode=ro` 開啟複本並設 `PRAGMA query_only=ON`。

## 下一步

1. **CEO：** 2026-10-19（週一，需先確認開市）跑 6.3 的三輪。6.1、6.2、6.5、6.6 任何時間都能跑。DB 診斷要先依「DB 唯讀守則」複製兩個 DB。
2. **tech-architect：**
   - 決定 `ObservedSessionCalendar` 的輸入口徑（快取加過濾，或市場 DB ok run），以及是否接上 `check_price_bars`。
   - 看 6.6.2：D0 的族群 σ_d 可能因除權息涵蓋而 fail-closed，這會影響族群預測最早何時能開始累積。
3. **風控與 quant：** 等 6.5 的規定原文與 `t187ap03_L` 結果，再決定 B-2 的二選一。目前請維持 A-16 的暫時對應（LM-71＋LM-26），直到 6.3 與 6.4 的診斷有結果。
4. **qa-reviewer：** 回貼後我會填 ADR-0028 的 `verified_on` 與出處、套用 6.3 判讀矩陣，再交審查。回貼前這份只是探測指令包，不算 done。

相關檔案：
- `/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`（新增 §6，第 892 行起）
