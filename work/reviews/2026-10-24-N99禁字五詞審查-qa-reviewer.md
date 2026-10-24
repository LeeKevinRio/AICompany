# N-99 禁字五詞審查

- 審查者：qa-reviewer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## Summary
N-99 的未 staged diff（三檔）符合風控裁示第二節第 3 點。五詞在前端與後端兩處都有，位置在「機率洗白」段尾，新增的交叉斷言會失敗，也不會誤報。我 Grep 確認過，`apps/stock-desk` 內沒有既有文案含這五詞，所以加詞後不會有 UI 或後端字串被掃到。無 BLOCKING_ISSUES。

## 各檔問題
### apps/stock-desk/frontend/app/lib/adviceWording.ts
- 五詞（符合率、吻合率、猜對、正確率、準確度）在 440–444 行，緊接「高機率」之後、`// 即時性` 之前，位置正確。
- 註解全為英文，只引用 `work/reviews/...風控.md` 與 `backend/tests/test_event_study_wording.py::_FRONTEND_TERMS`，兩者都是 repo 內既有路徑。註解沒有把 `shared/forbidden-terms.json` 放進去，並明寫「刻意不放」。這與 CLAUDE.md 的 main/產品線分離無關（`apps/stock-desk` 本身就是產品線）。
- 沒有問題。

### apps/stock-desk/backend/tests/test_event_study_wording.py
- `_FRONTEND_TERMS` 在 55–60 行加入五詞，位置正確。這五詞同時進了既有的兩個 parametrize 掃描（API note、event-study report）。
- `_frontend_forbidden_terms_block()` 以 `index("export const FRONTEND_FORBIDDEN_TERMS")` 起、`"\n];\n"` 迄。我確認 `adviceWording.ts` 全檔只有一個 `^];$`（495 行），而且在 374 行起點之後，所以截取範圍正確。
- 斷言比對的是 `'"{term}",'`，而 TS 註解行內沒有這種帶引號加逗號的字樣，註解不會讓斷言誤過。
- 這個區塊內若漏掉任一詞，斷言就會失敗，不會空轉。`source.index` 找不到時會直接 `ValueError`，不會安靜通過。
- [可維護性][low] 斷言綁定 `"詞",` 雙引號加逗號的寫法。若日後改成單引號、或一行放多個詞，會誤報失敗，不會漏報。dev-lead 回報已揭露，偏嚴方向，可接受，不需改。

### apps/stock-desk/frontend/app/lib/__tests__/adviceWording.test.ts
- 後端鏡像只在 `_FRONTEND_TERMS = (` 到第一個 `"\n)\n"` 之間找，我確認後端該 tuple 結尾在 75 行，範圍正確。檔內其他地方（例如 `_N99_TERMS`）出現這些詞，不會讓斷言誤過。
- `start`、`end` 都有 `expect` 守住，格式變動時會明確失敗。
- 路徑 `new URL("../../../../backend/tests/...", import.meta.url)` 從 `app/lib/__tests__/` 往上四層到 `stock-desk/`，正確；dev-lead 回報 vitest 全綠。
- [可維護性][low] `backendFrontendTermsBlock()` 在 `describe` 本體（收集階段）執行。檔案不存在時整個 describe 在收集階段失敗，錯誤訊息較不直觀，但仍會紅，不影響正確性。
- 註解以中文為主，夾英文說明。CLAUDE.md 要求程式碼註解用英文；這一段是區塊 docstring 的中文引言，其餘為英文。既有檔案本來就是中英混用（例如同檔 wave3 區塊），沿用慣例，不列為問題。

## 加詞後的掃描風險（Grep 確認）
- Grep `符合率|吻合率|猜對|正確率|準確度`（範圍 `apps/stock-desk`，排除 node_modules）：命中只有本次新增的 `adviceWording.ts`（440–444）、`test_event_study_wording.py`（56–60、81）、`adviceWording.test.ts`（131）。既有 UI 文案與後端字串零命中，與 dev-lead 的「既有命中清單為空」一致。
- 子字串風險：我另外 Grep `正確|準確|猜`，既有命中如下，都不含這五詞：
  - 「正確性」（kelly_wording.py、TradingViewChartPanel.tsx、componentWordingScan.test.ts）：「正確性」不含「正確率」。
  - 「不正確」「正確位置」「請確認…是否正確」。
  - 「猜測」「猜幣別」「猜測值」「猜的欄位」：不含「猜對」。
  - 「數字準確」（intradayWording.test.ts:332）：不含「準確度」。
- 前端有 `FRONTEND_FORBIDDEN_TERMS` 全掃描的測試，後端另有多個 test 載入或 import 這份清單。dev-lead 前端跑了完整 vitest（2260 passed），後端只跑了兩個測試檔（153 passed）。後端其他掃描測試（例如 `test_rules_invalidation_wording.py`、各 `test_adr00xx_*`）我無法執行，但上述 Grep 證明後端 source 與 tests 沒有可被這五詞掃中的既有字串，風險極低。`intradayWording.test.ts` 對 `"盤中",` 元素的來源掃描不受這五詞影響。

## 第二意見（Codex）
無法執行。`codex` 在此環境回傳 `/bin/bash: line 1: codex: command not found`，`which codex` 也沒有結果。依規範明寫缺席原因。本次改動純屬禁字清單加詞加存在性斷言，風險低。Codex 缺席不影響本地審查結論，但請 coordinator 知悉這是缺席而非通過。若流程要求必須有 Codex 意見，請在有 codex CLI 的環境補跑。

## 唯讀權限判準常數
未觸及。我跑了兩道檢查（以未 staged 的三檔 diff 為範圍）：`git diff --name-only -- scripts/validate_agents.py` 無輸出；對本批 diff grep `READONLY_AGENTS|READONLY_ALLOWED_BASH` 的 `+/-` 行，也無命中。

## Verdict
PASS（Codex 第二意見缺席，原因見上）
無 BLOCKING_ISSUES
BLOCKING_ISSUES=false

下一步：本批不涉及 UI 畫面，純禁字清單與測試。依風控要求，PR 需附上「既有命中清單：空」，並與已 staged 的 N-82 批次分開 commit。
