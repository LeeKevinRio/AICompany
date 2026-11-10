# N-207 台股代號形狀規則交件

- 審查者：data-engineer
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論
- 交付檔：`/home/user/AICompany/work/reviews/2026-11-10-N207台股代號形狀規則-data-engineer.md`。沒有改 code。
- 正向規則（用 fullmatch，不 strip、不轉大寫、不剝後綴）：
  `[1-9][0-9]{3}[A-JL-Z]?|00[0-9]{2,4}[A-JL-Z]?|91[0-9]{4}`
  - 涵蓋普通股、特別股、ETF（含 L、R、U、B、A 後綴）、DR。
  - 排除 `.TW`、空字串、空白、全形、小寫、K 後綴（外幣單位，沿用現行黑名單）、權證形、位數不對。
- **外部來源查證全部是「未查證」。** 本環境連 TWSE、TPEx 失敗（proxy 回 403 或 000），所以規則形狀來自記憶和 repo 內既有代號，不是交易所文件。規則只能標 `verified=False`。我另外列了待補查清單（第 6 節）。
- AC-04 的「非數字代號」確認和合法代號衝突，會誤拒 `00631L`、`00679B`、`2882A`。我建議改成「不符台股代號形狀」，並新增 AC-04b：合法的帶字母代號不得因形狀被拒。
- 已知殘留：`0000` 這類形狀合法但不存在的代號會通過形狀檢查，要靠 FR-5 的取日線檢查和 AC-05 擋下。

## 二、各部門回報
- **data-engineer**：
  - 排程台日線走 `app/api/deps.py:125-127`，順序是 TwseAdapter、TpexAdapter、FinMindAdapter。
  - 三者都用裸代號：`stockNo=`（twse.py:100）、`code=`（tpex.py:221）、`data_id=`（finmind.py:113）。三者都不處理 `.TW`。
  - 規則放行的代號能否查到日線**未驗證**。只有普通股 2330 在 2026-08-16 由 CEO 實測過；帶字母代號、6 位數字、DR 只有 fixture 測試。
  - 正規化：本規則不做（FR-5 要求不自動正規化）。日後若要做，只能放在 API 邊界的 validator，在形狀規則之前，不放 adapter，也不放 `admit_symbol`。`leverage/detect.py:50-51` 剝後綴的做法不得沿用。
  - 規則放名單模組，不放資料層。
  - 現有前後端的 `SYMBOL_PATTERN` 不要沿用於 N-207。
- **product-manager（待辦）**：
  - 改寫 AC-04，新增 AC-04b。
  - 裁示外幣單位 K（`00625K`）收不收。
  - FR-5 括號內的「由 data-engineer 查證」改引用本檔。
- **dev-lead（待辦）**：
  - 實作第 4 節的契約測試：正例 20 個、反例 28 個，另加 5 項行為測試。
  - 其中一項行為測試是輸入 `2330.TW` 時，不得有任何請求以 `2330` 送出。
- **risk-compliance-officer（待辦）**：審形狀拒絕訊息的字面。
- **devops-sre／CEO（待辦）**：開通 egress，或在本機補查。

## 三、驗證
- 用 `python3 -I` 對 regex 做 fullmatch：
  - 18 個正例斷言全過。
  - 25 個反例全部回傳 False，包含全形、`"2330\n"`、`2330k`、`030001`。
  - 發現 `0000` 會通過，已列為殘留。
- 外部查證 0 項完成：`curl` 取 isin.twse.com.tw、www.twse.com.tw、www.tpex.org.tw 皆失敗。
- 這份驗證只證明 regex 在列出的案例上的行為，不證明交易所編碼規則，也不證明資料源收這些代號。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有改 code。測試腳本放在 scratchpad，沒有進 repo。

## 四、下一步
1. PM 依第 3 節改 AC-04、新增 AC-04b，並裁示 K。
2. 有網路的人依第 6 節補查，包含用 `scripts/verify_market_data.py` 實測 `00631L`、`00679B`、`2882A` 和一檔 DR。結果回寫後再更新規則的 `verified_on`。
3. dev-lead 實作並加測試，交 qa-reviewer 審查（含 Codex 第二意見）。
4. 補查前，N-207 不得宣稱代號規則「已驗證」。
