# Stock Desk — C1（Phase 8 已裁示未交付項）逐項盤點對帳

- 撰寫者：product-manager
- 撰寫日期：2026-08-23
- 範圍：對照 `work/stock-desk-phase8-需求.md`（Phase 8 PRD，2026-08-02 二次修訂版）逐條 FR，核對 `product/stock-desk` 分支程式碼現況與測試
- 對帳基準：程式現況為準；找不到程式佐證的一律寫「查無，需 dev 協查」，不寫「未做」
- 結論性質：本文件只做事實盤點與處置建議，不改動 `work/機會清單.md`（交協調人統一處理）

---

## 結論先行

**C1 條目所列三項「未交付」宣稱與現況不符，全部已交付且有測試把關**：

1. 回測策略擴充 FR-10（RSI 反轉）/ FR-11（N 日突破）——**已做，有守門**
2. 產業欄位 FR-12（`Position.sector`、CSV 匯入欄、第 2 條上限）——**已做，有守門**（歷經 4 輪風控複審，2026-08-09 全流程收官）
3. 警示規則編輯 `PUT`/`PATCH`——**已做，有守門**

**但 C1 條目本身還包含「PM 對 phase8 PRD（FR-C1~C8 決策中樞等）逐項盤點結案狀態」這項工作，本次逐項盤點後，PRD 其餘 FR 並非全數完成**：

- **已做、有守門**：FR-1、FR-4、FR-5、FR-8、FR-9、FR-10、FR-11、FR-12、FR-C1、FR-C2、FR-C6、FR-C7、FR-C8 —— 共 13 項
- **部分做**：FR-2（成因分類機器可讀化未完成，仍是通用文案）、FR-6（AC-6.1「報酬衰減拆解」區塊缺 inline 摘要句，AC-6.2「情境推估」已有）、FR-7（AC-7.1 字面要求的後端 parametrize 測試查無，風險以其他形式覆蓋）—— 共 3 項
- **未做（前置閘門未解除，非缺陷）**：FR-C3（基本面）、FR-C4（籌碼面）、FR-C5（消息面）—— 因 S-1/S-2/S-3 spike 需要有網環境由 CEO 執行回填，`work/stock-desk-phase8-spike-盤點.md` 第 1.3/2.3/3.3 節「實測結果」欄位至今全空，三個 FR 依 PRD 明文「spike 未完成前不得進入 build」，故合規地停在未做 —— 共 3 項
- **已做（`total_equity_twd` 分母定義事項，FR-3）**：見下方逐項表

**發現的根因**：`work/reviews/c1-phase8-review.md` 顯示 FR-10/11、FR-12、FR-1 這批工作已在 **2026-08-09 當天**歷經多輪 qa/風控審查並「全流程收官」（含 4 輪風控複審 RiskGauge 文案、FX1 修復、四狀態產業文案）。`work/機會清單.md` 的 C1 條目**首版日期同樣是 2026-08-09**，但條目內容描述的是審查/收官**之前**的抽查快照（`strategies.py` 仍僅 `ma_cross`、`Position` 仍無 `sector`、`alerts.py` 仍僅 GET/POST/DELETE），未反映同日稍後完成的收官結果，此後五個工作天（至 2026-08-23）也未回頭校正。這是一次**清單未追上程式現況**的落差，不是工作被漏做。

---

## C1 是否可結案

**建議：C1 條目本身可結案（三項原始宣稱全部已交付、有測試守門），但不可整條刪除——需拆分為「已結案」與「新殘項」兩部分轉列，且必須把「PM 對 phase8 PRD 逐項盤點結案狀態」這項工作的產出（本文件）作為結案佐證一併存查。**

原因：
1. C1 原文宣稱的三項具體缺口（FR-10/11、FR-12、警示編輯）確認已交付，不應繼續掛在 P0 佔用容量。
2. 但 C1 條目的完整敘述還包含「含 PM 對 phase8 PRD（FR-C1~C8 決策中樞等）逐項盤點結案狀態」——這項工作本次已完成（即本文件），其產出揭露了 3 個部分做項與 3 個因前置閘門而未做項，這些不是「C1 的殘留」而是**各自獨立、性質不同的新機會**，不應塞進一個已結案的舊條目底下，應轉列為新條目（見下節）。
3. FR-C3/C4/C5（基本面/籌碼面/消息面）卡在 CEO 尚未執行 spike 腳本這一步，這是**整個核心主軸能否往下走的關鍵前置**，重要性高於「C1 收尾」本身，建議協調人特別留意其優先序是否該提升。

---

## 逐項對帳表

> 圖例：✅已做（有守門＝有測試釘住 or 風控核可）｜⚠️部分做｜⛔未做（含前置閘門未解除）｜❓查無需協查

### 核心主軸 FR-C1～FR-C8

| FR | 狀態 | 程式佐證 | 測試/守門佐證 |
| - | - | - | - |
| FR-C1 決策中樞頁資訊架構 | ✅ 已做 | `frontend/app/position/[symbol]/page.tsx:107-127`（操作摘要獨立查詢、技術分析區塊獨立載入，各自 DataMeta badge） | `frontend/app/lib/__tests__/componentWordingScan.test.ts` 掃描 `page.tsx`／`OperationSummaryPanel.tsx` 等 |
| FR-C2 技術分析區塊 | ✅ 已做 | `frontend/app/position/[symbol]/TechnicalIndicatorsPanel.tsx:11`（docstring 明寫「FR-C2 (Phase 8)：renders every technical/risk indicator `compute_signals()`」） | 同上掃描涵蓋該檔 |
| FR-C3 基本面區塊 | ⛔ 未做（前置閘門未解除） | `apps/stock-desk/backend/app/data/providers/` 僅 `twse.py`/`tpex.py`/`finmind.py`/`alpha_vantage.py`/`yfinance.py`/`fx.py`/`us_symbols.py`，無基本面 adapter；`page.tsx:124` 註解明寫「FR-C3/C4/C5 (fundamentals/chip/news) are not part of this batch — their spikes (S-1/S-2/S-3) have not landed」 | 不適用（未進 build） |
| FR-C4 籌碼面區塊 | ⛔ 未做（前置閘門未解除） | 同上，無籌碼 adapter | 不適用 |
| FR-C5 消息面區塊 | ⛔ 未做（含 AC-C5.2 的「誠實缺席」占位文案也未落地） | 同上；決策中樞頁**沒有**消息面區塊、也沒有「本產品目前不提供消息面資料」的占位句——連 AC-C5.2 允許的「合格不做」占位都未產出 | 不適用 |
| FR-C6 持倉操作建議「當下可執行」化 | ✅ 已做，有守門 | `frontend/app/lib/adviceWording.ts`、`frontend/app/lib/operationSummary.ts`（docstring 明寫 FR-C6/C7） | `frontend/app/lib/__tests__/operationSummary.test.ts`；`componentWordingScan.test.ts` 掃描禁用詞（§1.3 全清單） |
| FR-C7 進場評估（未持有標的） | ✅ 已做，有守門 | `frontend/app/lib/directorySearch.ts:11`（FR-C7(a) 查詢入口）；`adviceWording.ts:51,77`（候選模式標題與常駐證據限制語） | `operationSummary.test.ts:689` `describe("buildOperationSummary — candidate mode (FR-C7)"` |
| FR-C8 資料新鮮度誠實揭露 | ✅ 已做，有守門 | `OperationSummaryPanel.tsx:14,31`（FR-C8(a) 逐區塊新鮮度徽章） | `componentWordingScan.test.ts` 的「即時」裸詞掃描（`findBareRealtimeClaims`） |

**FR-C3/C4/C5 未做的根因**：不是實作缺失，是 PRD 自訂的硬前置閘門（S-1～S-3 spike）至今未解除。`work/stock-desk-phase8-spike-盤點.md` 第 1.3、2.3、3.3 節「實測結果（待 CEO 本機執行腳本後回填）」表格**全部空白**，`scripts/spike_phase8_sources.py` 存在但無證據曾被執行。這代表核心主軸尚有三分之一（基本面/籌碼面/消息面）完全卡在「CEO 需在有網環境跑一次驗證腳本」這一步，超過三週未推進。

### 既有候選 FR-1～FR-9

| FR | 狀態 | 程式佐證 | 測試/守門佐證 |
| - | - | - | - |
| FR-1 警示規則編輯端點與前端表單 | ✅ 已做，有守門 | `backend/app/api/alerts.py:112`（`PUT`）、`:129`（`PATCH`，docstring 明寫 FR-1）；`frontend/app/settings/EditAlertRuleModal.tsx`（PATCH 呼叫，docstring 逐條對應 AC-1.2/1.6） | `backend/tests/test_alerts_api.py:78` `test_put_edits_a_threshold_in_place_keeping_the_rule_id`（AC-1.1）、`:105` `test_patch_toggles_enabled_and_leaves_every_other_field_alone`（AC-1.2）、`:159` 附近 AC-1.3、`:176` AC-1.4、`:185` `test_put_can_switch_the_rule_type_with_matching_params`（AC-1.5） |
| FR-2 `quantity_range` 成因欄位 | ⚠️ 部分做 | `backend/app/advice/limits.py:1281` `suggest_quantity_range` 的 `basis` 是**單一組裝好的完整句子**（自然語言），不是機器可讀的分類碼；`frontend/app/lib/adviceWording.ts:107-114` 註解明寫：「Do NOT rewrite this to name a specific cause until risk-compliance-officer signs off on the per-cause copy (AC-2.2)」——`quantity_range` 缺席時前端仍是同一句通用文案 `QUANTITY_RANGE_ABSENCE_TEXT` | 缺 AC-2.1 要求的「機器可讀成因分類」測試；此缺口已被記錄在 `work/機會清單.md` D2 項第一條（`quantity_range_reason` 成因細分），與本次盤點結論一致，非本次新發現 |
| FR-3 建議卡「總資產」限定語 | ✅ 已做 | `frontend/app/settings/SettingsForm.tsx`、`frontend/app/lib/adviceWording.ts:105`（`CANDIDATE_QUANTITY_BASIS_NOTE` = 「以你目前的總資產（已估值部位市值，不含現金）與上限推導。」，符合 AC-3.1 選項 B 定案文字） | `componentWordingScan.test.ts` 掃描 `SettingsForm.tsx` |
| FR-4 命中規則方向標示 | ✅ 已做，且超出原範圍一併清償 D2 項 | `frontend/app/position/[symbol]/AdviceCardView.tsx:138-169`（`has_conflict` 渲染 + D2 item 3 註解明寫清償了 `work/機會清單.md` D2 的舊列管項） | 同一檔案內附 D2 suggested 裁決引註（`波次1文案裁決.md`） |
| FR-5 回測報告常駐警語 | ✅ 已做 | `frontend/app/backtest/BacktestReportView.tsx:136`：「本回測報告呈現的所有數字皆屬歷史統計描述，不代表未來會重演。」（措辭與 PRD 草稿字面不同，但語意等價，且為風控/creative 定稿後的版本，`componentWordingScan.test.ts:150` White-list 註解可佐證其經過審查流程） | `componentWordingScan.test.ts` 掃描該檔 |
| FR-6 槓桿專章 inline 摘要 | ⚠️ 部分做 | `frontend/app/position/[symbol]/LeverageChapterView.tsx:176-181`「情境推估（erosion）」區塊**有** inline 摘要句（`chapter.erosion?.nature ?? "情境推估，非預測。"`，滿足 AC-6.2）；但「報酬衰減拆解（drag）」區塊（:94-172）**沒有**任何 inline 摘要句指出最關鍵假設（如 PRD 舉例的「費用為線性近似」），只有數字表格 + 收合的 `AssumptionsList`，不滿足 AC-6.1 | 查無對應前端測試檔（`LeverageChapterView.tsx` 無 `__tests__` 對應檔），此區塊目前無守門 |
| FR-7 `signal_condition` banned-word 測試補強 | ⚠️ 部分做（以不同形式落地，字面 AC 未逐字滿足） | 禁用詞防護實際覆蓋面很廣：`backend/tests/test_advice_wording.py`（`FORBIDDEN_TERMS` 掃描規則物件與渲染卡片）、`backend/tests/test_alerts_engine.py:231,319`（警示訊息禁用詞掃描）、`frontend/app/lib/__tests__/componentWordingScan.test.ts` 把 `format.ts`（含 `signalFieldLabel` 欄位標籤）納入掃描範圍 | 但**查無** AC-7.1 字面要求的「加入案例遍歷 `signal_condition` 可用欄位（`KNOWN_FIELDS`/`FIELD_LABELS`）」這種後端 parametrized 測試——`grep KNOWN_FIELDS` 命中 `test_advice_loader.py`/`test_advice_engine.py`，但這兩處測的是「規則檔只能用已知欄位」，不是「欄位標籤本身不含禁用動作動詞」。此為需 dev-lead 確認是否需要補測試，還是既有前端掃描已足夠涵蓋風險的認定問題 |
| FR-8 `RiskGauge` 改由後端回報 | ✅ 已做，有守門 | `frontend/app/components/RiskGauge.tsx:18`（docstring 明寫「FR-8: the book-level view of the same five caps `app.advice.limits`」） | `:56` 註解引註「風控快審 FR-8 八句（2026-08-09，`work/reviews/股數區間文案裁決.md`）」 |
| FR-9 總曝險啟用（自報淨值） | ✅ 已做，有守門 | `backend/app/settings/net_worth.py:1`（docstring「Sanity rules for the account net worth a user reports (FR-9 (c))」）；六問定案見 `work/stock-desk-phase8-風控定調.md` 清單二 | `backend/tests/test_advice_limits.py:388-484`（`test_gross_exposure_*` 系列，涵蓋 passed/violated/not_evaluable/30 天過期/三句必附揭露） |

### CEO 裁示納回項 FR-10～FR-12（C1 條目原始三項宣稱之二）

| FR | 狀態 | 程式佐證 | 測試/守門佐證 |
| - | - | - | - |
| FR-10 回測策略：RSI 反轉 | ✅ 已做，有守門 | `backend/app/backtest/strategies.py:108` `rsi_reversal`（門檻 30/50，docstring 附 Wilder 1978 出處） | `backend/tests/test_backtest_strategies.py`；`work/reviews/c1-phase8-review.md`「通過」段：「FR-10/11：`_replay` 無 look-ahead、無跨折污染；RSI 抽取純搬移有 golden test」 |
| FR-11 回測策略：N 日高低點突破 | ✅ 已做，有守門 | `strategies.py:142` `breakout`（20/10 窗口，docstring 附 Turtle System 1 出處） | 同上 `test_backtest_strategies.py`；同一審查通過段 |
| FR-12 產業欄位 | ✅ 已做，有守門（歷經 4 輪風控複審） | `backend/app/positions/models.py`（`sector` 欄位）、`backend/app/positions/csv_io.py`（CSV `sector` 欄）、`backend/app/advice/limits.py`（`_check_sector_weight` 生效）、`backend/app/advice/book.py`（四狀態文案）；前端 `frontend/app/components/EditPositionModal.tsx:325-361`（產業別下拉，`useSectors` 取值） | `backend/tests/test_positions_api.py:293-350`（`test_sectors_endpoint_lists_the_closed_twse_taxonomy` 等 6 條）、`test_directory_sector_persist.py`（15 條）；`work/reviews/c1-phase8-review.md` 完整審查軌跡：初審 BLOCKING → 風控快審 VETO 句1/句2 → 二輪修正 PASS → qa 終審 PASS → RiskGauge 三輪/四輪風控回審 APPROVE，2026-08-09「C1 批全流程收官」 |
| 警示規則 `PUT`/`PATCH`（C1 條目原文第三項） | ✅ 已做，有守門 | 同 FR-1 | 同 FR-1 |

---

## 已做但無守門（單獨列區）

盤點過程中未發現「程式已做但完全無測試釘住」的既有候選 FR 項（FR-1、FR-4、FR-5、FR-8、FR-9、FR-10、FR-11、FR-12、FR-C1、FR-C2、FR-C6、FR-C7、FR-C8 皆有對應測試或風控核可紀錄）。

**唯一的無守門缺口是 FR-6 的「報酬衰減拆解」區塊**（見上表）：程式碼存在（`LeverageChapterView.tsx:94-172`），但既不滿足 AC-6.1 的 inline 摘要要求，也查無對應測試檔案守門其呈現內容——這不是「已做無守門」而是「做得不完整且無守門」，已歸類為部分做，此處僅重申其守門缺口。

---

## 未做 / 部分做項轉列草案（供協調人貼入 `work/機會清單.md`）

> 以下為建議格式，優先級與規模為 PM 建議值，最終取捨由協調人／CEO 定奪。

| # | 機會 | 為什麼（來源） | 優先級 | 規模 |
| - | --- | --- | - | - |
| C1-a | **C1 結案**：回測策略擴充 FR-10/FR-11、產業欄位 FR-12、警示規則編輯 PUT/PATCH 三項原始宣稱皆已交付且有測試守門，2026-08-09 已歷經 qa/風控多輪審查收官（見 `work/reviews/c1-phase8-review.md`）。清單描述與現況脫節，非工作漏做。 | 本次逐項對帳（`work/stock-desk-C1-phase8交付盤點.md`） | — （建議標記 done） | — |
| C1-b | **FR-C3/C4/C5（基本面/籌碼面/消息面）前置閘門卡關**：`work/stock-desk-phase8-spike-盤點.md` 的 S-1/S-2/S-3 實測結果表格全空，`scripts/spike_phase8_sources.py` 需 CEO 在有網環境執行後回填，超過三週未推進；核心主軸決策中樞頁因此永久缺三分之一內容，FR-C5 甚至連 AC-C5.2 允許的「合格不做」占位句都未落地。 | PRD 明文硬前置閘門（`work/stock-desk-phase8-需求.md` 風險與依賴第 1 點）；不解除則 FR-C3/C4/C5 永遠卡住 | **P0**（若要推進核心主軸剩餘範圍） | 前置動作 S（CEO 執行腳本＋回填）；後續實作視 spike 結論另估 M/L |
| C1-c | **FR-2 `quantity_range` 成因機器可讀分類未完成**：現況是單一組裝好的完整句子，AC-2.1 要求的「機器可讀成因分類」與差異化前端文案未落地；`adviceWording.ts:107-114` 明文標記「未經風控核准前不得改寫」。與 `work/機會清單.md` D2 項第一條為同一缺口，建議合併追蹤而非另開新號。 | Phase 6 舊列管放行條件 (b) 尚未觸發（見 `work/機會清單.md` D2） | P1 | M |
| C1-d | **FR-6 槓桿專章「報酬衰減拆解」區塊缺 inline 摘要**：AC-6.1 要求收合假設清單上方要有一句點出最關鍵假設（如「費用為線性近似」），現況只有情境推估（erosion）區塊做到（AC-6.2），drag 區塊沒有，且該元件查無對應測試檔案守門。 | PRD AC-6.1 逐字要求；`LeverageChapterView.tsx:94-172` 程式現況 | P2 | S |
| C1-e | **FR-7 signal_condition 欄位禁用詞測試字面缺口**：現有防護（`test_advice_wording.py`、`test_alerts_engine.py` 訊息掃描、前端 `componentWordingScan.test.ts` 掃描 `format.ts`）在實務上大機率已覆蓋風險，但查無 AC-7.1 字面要求的「後端 parametrize 遍歷 `signal_condition` 可用欄位（`KNOWN_FIELDS`/`FIELD_LABELS`）」測試。需 dev-lead 確認：是否要補一條字面測試，或現有覆蓋面已足夠而正式認定此 AC 用不同形式滿足。 | PRD AC-7.1 逐字要求 vs 現況覆蓋面差異 | P2 | S |

---

## 附註：C1 條目原文與現況落差的具體對照

C1 條目原文（2026-08-09 首版）：
> 回測策略擴充 FR-10/FR-11（RSI 超賣反彈、N 日新高突破；經抽查 `strategies.py` 仍僅 `ma_cross`）、產業欄位 FR-12（`Position` 仍無 `sector`，第 2 條上限恆 not_evaluable）、警示規則編輯 PUT/PATCH（`alerts.py` 仍僅 GET/POST/DELETE）

現況（本次核實，2026-08-23）：
- `strategies.py:1-201` 三支策略 + `build_strategy`，且有完整出處註解與測試
- `Position.sector` 已存在，`limits.py` 的 `_check_sector_weight` 已生效，四狀態文案歷經 4 輪風控複審
- `alerts.py:112,129` `PUT`/`PATCH` 皆已存在，前端 `EditAlertRuleModal.tsx` 已接線

三項描述與程式現況**完全不符**，且不符的方向一致：都是「清單記錄了審查通過之前的快照」。建議協調人在更新機會清單時，同時檢查該日期前後是否還有其他條目有類似「首版日期與收官日期同一天但描述取自較早快照」的落差。

---

*本文件僅盤點，不改動 `work/機會清單.md`。落檔路徑：`work/stock-desk-C1-phase8交付盤點.md`，僅寫檔未 commit，由協調人統一處理（含 `work/.gitignore` 放行行）。*
