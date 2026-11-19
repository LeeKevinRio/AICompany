# 對沖 PRD 三題回覆交件（^TWII 開盤值、費率、融券資料來源）

- 審查者：data-engineer
- 日期：2026-11-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

三題的報告已寫好，沒有 commit，也沒有改任何程式或 PRD：`/home/user/AICompany/work/research/2026-11-19-對沖PRD三題回覆-data-engineer.md`。我沒有碰 `.env` 的值，也沒有碰 `data/*.db`。

**第 1 題有會影響 CEO 驗收與正式登記的發現。**

1. **PRD 第 147 行的前提不符程式。**
   - `^TWII` 開盤值為 null 時，canonical 不會拒收整份快照，因為 null 到不了 canonical。
   - yfinance adapter 的 cache 路徑只要 open、high、low、close、volume 任一為 None，就整列靜默丟掉，連有效的收盤價也一起丟（`app/data/providers/yfinance.py:301-307`）。
   - 快取表 `price_bars_cache` 的 open 欄是 `NOT NULL`（`app/data/cache.py:43`），所以資料庫裡不會有 null 的開盤值。
   - 被丟的交易日在快照裡直接缺席。`app/outlook` 沒有連續性檢查，也沒有「缺一天」的 missing 代碼，`DropReason` 只有 `not_final`（`app/outlook/inputs.py:62`）。缺口會讓均線與報酬的 lag 悄悄跨過去，不報錯。
   - 風險是「靜默失真」，不是「拒收」。以上為已證實（逐行讀程式）。

2. **開盤值為 0 會通過所有現有防線。**
   - adapter、cache、`canonical_price` 都接受 0（`canonical.py:105-106`）。
   - 唯一會抓它的 `quality._check_ohlc_consistency`，在 `app/` 內沒有呼叫者。
   - 預測核心只讀收盤價，所以目前的記錄不受影響。但第二段用 T+1 開盤進場時，若宣告只定義「缺日」為 `open_unusable`，0 會被當成真實開盤價。

3. **只有開盤值為 NaN 或 Infinity 才會真的讓整次記錄失敗。**
   - 這種情況下該次 run 記為 `outcome="error"`、`error_class="CanonicalFormError"`（`recorder.py:306-322`），可見且 fail-closed。
   - Yahoo 是否真的會回 NaN，我沒有證據，列為推論。

4. **CEO 這次真實資料驗收的行為**（只讀 DB 複本、不連網，`pipeline_acceptance_real.py`）：
   - 開盤為 0：不會停，回貼只有 `bars_sha256=` 與 `acceptance_result=PASS`，任何一行都看不出來。這是已知缺口，不是驗收失敗的原因。
   - 開盤為空字串或不可解析：停在 `STOP: a TWII row of the cache copy cannot be read.`。
   - 開盤為 NaN 或 Infinity：腳本只顯示 `ERROR: unexpected failure; no paste-back file was made. Tell the coordinator.`，不產生 paste-back 檔（`pipeline_acceptance_real.py:342、959-961`）。
   - 缺交易日：腳本只檢查「run_date 之前的交易日數夠不夠」，缺日不會停。

5. **真實資料與測試**：
   - Yahoo 抓不到（`CONNECT tunnel failed, 403`），標為「網路不通，未實測」。
   - 我改用官方 TWSE 的加權指數日線交叉看，34 個月共 685 個交易日，開盤欄沒有空值、非數字或小於等於 0。缺 2024-02 與 2024-09 兩個月，因為被限流。
   - 這是官方指數資料，不是 Yahoo `^TWII` 的資料，不能證明 Yahoo 那欄乾淨。
   - repo 內 `^TWII` 的 fixture 全是合成的，沒有開盤為 null 或 0 的案例，也沒有實錄回應的契約測試。
   - 注意 `app/forecast/inputs.py` 不存在，實際檔案是 `app/outlook/inputs.py`。raw 路徑（會回報 null 缺口）與 `record_forecasts` 在 `app/` 內都還沒有呼叫者，因為尚未接線。

6. **修補建議（登記前可做，不動 `app/`）：**
   - 第二段事先宣告把 `open_unusable` 擴充為「應有交易日但無 bar，或開盤非有限、小於等於 0、不在該列最低與最高之間」。
   - 驗收後做一次唯讀體檢，數 DB 複本裡開盤小於等於 0 與缺日的列數。這項我不能自己做。
   - 用 TWSE 官方開盤欄做對照源。
   - 若要新增腳本，必須等 CEO 這次驗收之後。因為驗收會檢查 git 乾淨且已推到 origin，現在新增檔案會讓驗收停下來。

7. **修補建議（接線之後，動 `app/`，需要 tech-architect 出 ADR）：**
   - 丟列要計數並寫進 `dropped_rows`。
   - 加上連續性檢查與新的 missing 代碼。
   - 加上開盤小於等於 0 與最低到最高範圍的檢查。

**第 2 題**
- repo 現有的手續費 0.1425%、證交稅 0.3%、ETF 0.1% 都是未查證預設值，`verified_on=None`（`app/backtest/costs.py:47-55`）。
- 現行法定費率因官方站（law.moj、mof、fsc、taifex、taiwanindex 等）連不上，**未查證，數字不填**。我只列出該去查的頁面類型，不含任何數字。
- 反向 ETF：TWSE 官方 ETF 清單共 245 檔，臺灣加權相關的反向型有 3 檔，分屬兩種標的指數名稱，分別是「臺灣證券交易所發行量加權股價日報酬反向一倍指數」與「臺指反向一倍指數」。
  - 名稱 1 的結構，以及名稱 2 可能建立在期貨上的推測，都只是由名稱推得（推論）。
  - 指數編製規則、期貨轉倉成本、經理費實值皆未查證。
- RC-170 歷史值來源：
  - TWSE 價格指數 `/rwd/zh/TAIEX/MI_5MINS_HIST`，實測可得起點 1999-01。
  - 報酬指數 `/rwd/zh/TAIEX/MFI94U`，可得起點保守為 2003-01。
  - 格式為每月一份 JSON，日期為民國年，數值為含千分位逗號的字串，沒用金鑰。
  - 報酬指數的編製假設（是否稅前、再投入時點）未查證。
  - 連續請求會被回 307 安全頁，需長間隔限速。

**第 3 題**
- 上櫃（TPEx OpenAPI，免金鑰）：
  - `tpex_margin_sbl`、`tpex_mainboard_margin_balance`：融券與借券賣出餘額、可借券賣出股數。
  - `tpex_margin_trading_lend`：標借費率區間，單位與計算基礎未查證。
  - `tpex_intraday_fee`：當沖券差借券費率。
  - 這些是當日快照，歷史要自己每日蒐集。
- 上市（TWSE）：
  - `MI_MARGN`、`TWT93U`：每日融券餘額。
  - `TWT96U`：當日可借券賣出股數（券源）。
  - `BFI84U`：停券預告。
  - 上市的借券費率沒有找到端點，屬未查證。
- repo 現有 adapter 完全不涵蓋融資融券與借券。

## 2. 各部門回報

- data-engineer（我）：完成三題查證與報告。
- 網路請求：約 100 次唯讀 GET，未帶金鑰。TWSE 對連續請求回 307 安全頁，我已放慢；日後正式 adapter 必須照限速設計。

## 3. 驗證

- 這次沒有跑 repo 測試。程式面結論來自逐行閱讀與 grep，報告內附行號。
- 網路實測的成功與失敗清單，以及開盤值掃描的方法與限制，都在報告第 3 節。

## 4. 下一步

1. coordinator 或 PM：把「PRD 第 147 行前提不實」以待辦形式記錄，不改凍結的 PRD 本文，並把「開盤為 0」列為與 null 並列的情境。
2. quant：依 R1 擴充 `open_unusable` 的定義；RC-170 常數自行鎖定。
3. tech-architect：決定 adapter 的 null 丟列行為算不算「動核心 app/」（`app/data` 不在 code_digest 範圍，但仍在 `app/`），並為接線後的修補出 ADR。
4. CEO：
   - 這次驗收可照常跑。
   - 現行手續費與證交稅、反向指數編製規則、上市借券費率需要在可連外網的環境查證。
   - 若需要，我可再出一份沿用 10-16 那份限速與停手設計的探測指令包，目前沒有建立。
5. 未決缺口：現行手續費與證交稅（含反向 ETF 適用性）、反向指數編製規則與轉倉成本、經理費實值、上市借券費率、Yahoo `^TWII` 開盤欄實況、TWSE 報酬指數編製假設，全部是未查證。
