# missing code 白名單裁示

- 審查者：tech-architect
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
1. **採 A**，`MISSING_CODES` 放在 `app/outlook/engine.py`，不放 `missing.py`。
2. **判定為「四類、五個 code」，沒有差異要處理。** §2.5 表第 3 列字面就是「`E-VOL-SHORT` 或 `E-VOL-DEGENERATE`」，兩者同一個順位、同一個 item `sigma_d`，而且互斥：`volatility` 只回傳一個 `missing_code`。補充五 3(c) 說的「四類」指表上四列，白名單是這四列的五個 code。
3. A 讓 `code_digest` 改變，對比較基準、M-2～M-5、CG-2 都沒有影響，前提是 A 在 CG-2 PR 合併前落地。依 CEO #139，這件事本來就是補充五 3(c) 的既有阻擋項，不算插隊。現在做，`code_digest` 沒有任何使用者；拖到接線後才做，正式帳會出現一次 digest 變更，觸發 D-5 第 6 點全量重算。

## 各部門回報
**tech-architect（唯讀，已讀 ADR-0030 補充一～五、凍結包 §2.5、worktree 內 `engine.py`／`volatility.py`／`missing.py`／`baselines.py`／`basket.py`／`store.py`／harness）**

選 A 的理由：
- 「哪些 code 屬於 §2.5」是 engine 的產出語意，應該只定義一次（K-6 精神），而且要放在產出它的模組，也就是 D-1 指定的 `engine.py`。
- B 把這份成員清單放在 `tests/`。它只引用了常數，「誰算在內」仍是第二份定義，等於迴避 qa 的要求。
- A 可以用 AST 鎖住產出端，B 做不到。

放 `engine.py` 而不放 `missing.py` 的理由：
- `missing.py` 是 ADR-0027 D-13 的通用結構，`MissingItem.code` 是 `str`，也承載 §2.5 以外的 code，例如 `basket.py` 的 `E-ADJ-COVERAGE`。
- 放進去會暗示那是封閉清單，誘使日後拿它驗 `MissingItem`，打壞 basket。
- `missing.py` 目前不 import 任何 `app` 模組，放進去就得反向依賴 `volatility`。`engine.py` 已經 import `volatility` 和 `get_args`。

`code_digest` 改變的影響逐項：
- **補充三（修訂版）第 1 點**：基準是同一個 DB 裡較早的 `forecast_run`。正式主 DB 有 0 列（bootstrap 要求），也還沒接線；harness 用暫存 DB，所以沒有比對對象，無影響。若有人重用留著舊 run 的暫存 DB，會觸發重算；語意沒變，重算應逐位相同，這是正常行為。
- **補充四 M-2～M-5／M-8**：釘住的是事先宣告 blob、C-8、definition、規則雜湊，都不是 `code_digest`。A 不動 YAML 和定義物件，無影響。
- **CG-2**：登記不記錄 `code_digest`。R-1 要求從 CG-2 合併 commit 到 HEAD 之間 `app/` 沒有 diff，所以 **A 必須在 CG-2 PR 合併前落地**，依補充四第 6 點的順序本來就會成立。M-1 要求 harness 在 A 之後重跑。

## 驗證（交 qa-reviewer 逐條檢查）
- C1：`MISSING_CODES` 只在 `engine.py` 定義一次，依 §2.5 順序排，值恰好是五個：`(E_BARS_SHORT, E_PRICE_UNUSABLE, *get_args(VolatilityMissingCode), E_PIT_UNVERIFIED)`。它不含 `E-ADJ-COVERAGE`，`app/` 和 `tests/` 都沒有它的字串副本（grep）。
- C2：`engine.py` 第 382、392 行用字串字面 `"E-VOL-SHORT"`、`"E-VOL-DEGENERATE"` 比對。同一個 commit 改成 `volatility.E_VOL_SHORT`／`E_VOL_DEGENERATE`，同一個語意、同一次 digest 變更。另用 AST 確認 `engine.py` 內所有 `_item(` 的第一個參數都是 `MISSING_CODES` 裡的名稱，不是字串字面。
- C3：測試覆蓋三件事：engine 產出的 code 都在集合內；同一筆紀錄不會同時有兩個 `E-VOL-*`；code 依 §2.5 順位不遞減。
- C4：harness 從 `app.outlook.engine` import `MISSING_CODES`。至少一個反例 fixture 會判失敗，例如 insufficient 紀錄帶 `E-ADJ-COVERAGE`（補充五 S-13a）。輸出只有通過／失敗和失敗種類，不含筆數。
- C5：h3、h5 的規則與定義雜湊不變（既有測試）。repo 裡不得有寫死的 `code_digest` 值。我看過的範圍沒有，請 dev-lead 用 grep 確認全部 tests。

本次只讀檔，沒有跑任何測試。

## 下一步
1. dev-lead 在 `nm5-batch5-fix` 依 C1～C4 實作，然後重跑 harness，交 qa（含 Codex）。
2. tech-writer 在 ADR-0030 補充五第 3 點 (c) 後加一行解讀：「四類＝§2.5 四列、五個 code；唯一定義為 `app.outlook.engine.MISSING_CODES`」。
3. 凍結後待辦（不插隊）：`baselines.py:49-50` 另有一份 `E_BARS_SHORT`／`E_PRICE_UNUSABLE`。`engine.py` 會 import `baselines`，要合併得把常數抽到葉模組，屬重構，屆時會再改一次 `code_digest` 並觸發一次設計內的重算。`store.py:143` 的 `"E-VOL-"` 前綴可在同一輪改為由 `VolatilityMissingCode` 導出。
4. 若 CEO 判定 `code_digest` 在接線前的任何變更都要先核可，請升級 CEO。我的判斷是不需要。

相關檔案：
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/work/research/2026-11-14-NM5凍結包-大盤h3h5-quant.md
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/outlook/engine.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/outlook/volatility.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/outlook/missing.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/outlook/baselines.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/tests/forecast_pipeline_harness.py
