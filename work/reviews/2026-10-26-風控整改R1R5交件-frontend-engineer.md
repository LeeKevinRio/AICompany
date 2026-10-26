# 風控整改 R-1～R-5 修正交件

- 審查者：frontend-engineer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
風控 R-1 到 R-5 已依裁定落地，已 push 到 `origin/fix/stock-desk-risk-remediation`。HEAD 為 4c9e1fe357180f5a9b397e8cdad7fffc65a2b238。
- 前後端完整 CI 全綠。
- R-4 用本批新產出的截圖重做實機逐字確認，全部符合。
- 這一輪新增 3 個 commit，都在 48c5209 之上：
  - 9a33b6b：`docs: 刪除 README 已不實的舊免責句`（R-2，單獨一個 commit）
  - b723971：2-R 只在續抱參考時顯示（R-1）
  - 4c9e1fe：4-附 以全形括號分隔（R-3）
- R-5：除這三項外，沒有改任何其他字面。C-1 守門清單未動。`test_advice_engine.py` 未動，後端程式碼自 48c5209 起零變更。

## 各部門回報（frontend-engineer）
路徑前綴：F = `apps/stock-desk/frontend/app/`。

- R-1（b723971）
  - `F lib/limitNotices.ts`：`NOTICE_ACTIONS` 改為只含 `["hold"]`。旁邊註解改為「風控 2026-10-26 裁定修訂 C-6；失效條件 T1、T9」，並附一句英文說明原因。`buildLimitsDoNotChangeActionNotice` 字面不改。
  - `F lib/__tests__/limitNotices.test.ts`：
    - **行為變更（風控修訂 C-6）**：2-R 動作矩陣中，reduce、take_profit、stop_loss 由 `shown: true` 改為 `shown: false`。
    - **行為新增**：00631L 型 fixture（reduce，加第 1、4 條違反）的 `buildLimitNotices` 回傳 `actionNotice` 為 null，2-M 標題「已違反 2 條上限：」與兩行、2-O「另有 1 條上限無法評估，不代表已通過；見下方建議卡。」照常。
    - **行為新增**：渲染層同款 fixture，沒有「不代表你的部位在上限內」，2-M、2-O、3-S 都在。
    - 既有的 2330 順序測試（被擋句、2-R、2-O）維持通過。
- R-2（9a33b6b）：根目錄 `README.md` 只改第 32、33 行。第 32 行句末「；」改「。」，第 33 行整行刪除。改後出貨面（README 與 `F` 程式碼，不含測試）對「研究與教育用途」「非投資建議」只剩 `KeyLevelsPanel.tsx:48,303` 兩行註解，不渲染。
- R-3（4c9e1fe）
  - `F position/[symbol]/OperationSummaryPanel.tsx:303-306`：渲染處改為 `<span className="text-neutral-400">{`（${DRAWDOWN_UNADJUSTED_NOTICE}）`}</span>`。括號與文字在同一個 span、同一個文字節點，並移除 `ml-2`。`DRAWDOWN_UNADJUSTED_NOTICE` 常數不改。
  - `F lib/__tests__/riskRemediationItem4.test.ts`：**行為新增**，兩條逐字斷言，`drawdown_protection`（兩成）與 `deep_drawdown_stop`（三成）各一條。
    - 斷言依據行 innerText 為「依據：目前回撤深於兩成（以未還原價計算，回撤可能含除權息缺口）」，三成同理。
    - 另斷言括號與文字在同一個 span 內，且規則名稱後緊接 `<span class="text-neutral-400">（`。
    - 規則名稱取自 `rules/default.yaml:157,169`。

## 驗證（原文）
輸出檔在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/`。

前端
- `npm run typecheck`：`tsc --noEmit`，`TYPECHECK_EXIT=0`（`fe_typecheck2.txt`）
- `npx vitest run`：`Test Files  86 passed (86)`，`Tests  2413 passed (2413)`，`VITEST_EXIT=0`（`fe_vitest2.txt`；上一輪是 2409，新增 4 條）
- `npm run build`：`BUILD_EXIT=0`（`fe_build2.txt`）

後端（程式碼無變更，仍照要求完整重跑）
- `uv run ruff check .`：`All checks passed!`，`EXIT=0`
- `uv run ruff format --check .`：`437 files already formatted`，`EXIT=0`
- `uv run mypy app tests`：`Success: no issues found in 432 source files`，`EXIT=0`
- `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：
  ```
  TOTAL                                       19119    500    97%
  Required test coverage of 90% reached. Total coverage: 97.38%
  ========== 8089 passed, 2 xfailed, 18 warnings in 1631.16s (0:27:11) ==========
  PYTEST_EXIT=0
  ```
  輸出檔：`be2_ruff.txt`、`be2_fmt.txt`、`be2_mypy.txt`、`be2_pytest.txt`。

## R-4 實機逐字確認（只用本批新截圖）
- 做法同上一輪的 e2e-fallback：offline 合成示範資料（`demo_synthetic`）、DB 為 `remed/demo.db`、後端 8200、前端 3200。為了讓前端指向 8200，我另外用 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8200` 重新 build 了一次，供截圖用。
- 儀器來源（`provenance`）：
  - playwright：`/opt/node-tools/node_modules/playwright/index.js`
  - chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`
  - 前綴 `/opt/`，與既定前綴一致。
- 後端 CORS 白名單寫死 `http://localhost:3000`，而本次被指定用 3200，所以仍用 Chromium 的 `--disable-web-security` 啟動參數解除瀏覽器端 CORS 檢查，沒有改應用。
- 啟動的行程已用 PID 停掉；停後 8200、3200 皆無回應。
- 本批新截圖前綴為 `r2-`，目錄 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/remed/`（共 8 張）：
  - `r2-2330-desktop.png`、`r2-2330-desktop-expanded.png`、`r2-2330-mobile-375.png`
  - `r2-00631L-desktop.png`、`r2-00631L-desktop-expanded.png`、`r2-00631L-mobile-375.png`
  - `r2-backtest-result-desktop.png`、`r2-backtest-result-mobile-375.png`
  - 同目錄前綴不是 `r2-` 的圖都是舊圖，不是本批產出，請勿使用。
  - 腳本 `.../scratchpad/runner2.js`，原始輸出 `.../scratchpad/runner2_out.txt`。
- 逐字結果：
  - 00631L 決策卡
    - 沒有 2-R：「不代表你的部位在上限內」不出現。
    - 2-M：「已違反 2 條上限：」「第 1 條・單一標的佔比 23.28%（上限 15.00%）」「第 4 條・單筆最大可承受虧損 1.33%（上限 1.00%）」。
    - 2-O：「另有 2 條上限無法評估，不代表已通過；見下方建議卡。」
    - 3-S 全文都在。
  - 00631L 操作摘要「依據」行，原文為「依據：目前回撤深於兩成（以未還原價計算，回撤可能含除權息缺口）」。
  - 2330 決策卡：2-R「「續抱參考」不代表你的部位在上限內；目前超過上限只會把加碼參考改為續抱參考，不會改成減碼參考。」仍在。順序為：已違反 2 條上限、兩句「加碼建議被第 N 條上限…擋下。」、2-R、2-O「另有 2 條上限無法評估…」、3-S。
  - 回測框：「先看以下假設：前兩項可能讓結果偏樂觀」及兩點，與上一輪相同。
  - 375px 兩頁 `scrollWidth` 都等於 `innerWidth`（375），無橫向溢出；console 錯誤 `[]`，失敗請求 `[]`。
- 我只看了 `r2-00631L-desktop.png` 一張圖，版面無異常，依據行括號顯示正常；其餘以逐字文字確認。

## 仍待處理
- C-9 仍缺 dev-lead 的書面確認（我提供的程式與測試證據不能代替）。
- 5-K 未做，等 CEO 對「停用會拿掉 10% 封頂」裁定後另開 PR。
- 風控裁定文件提到的 `work/reviews/2026-10-26-風控整改收尾交件-frontend-engineer.md` 是 coordinator 轉存的上一輪報告，我沒有寫任何 `work/` 檔案。
- qa 審查結果出來後如有要修的地方，請再轉給我。

HEAD：4c9e1fe357180f5a9b397e8cdad7fffc65a2b238（`fix/stock-desk-risk-remediation`，已 push，工作區乾淨）。
這條分支完整 commit 序列：7252b4a、89fae00、1af1fac、cf4b490、4fcc83a、48c5209、9a33b6b、b723971、4c9e1fe。
