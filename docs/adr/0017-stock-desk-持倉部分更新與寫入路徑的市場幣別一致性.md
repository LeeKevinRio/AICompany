# ADR-0017：stock-desk 持倉部分更新與寫入路徑的市場幣別一致性

- 狀態：proposed
- 日期：2026-10-03
- 決策者：tech-architect（草案）；CEO 待核可（見「需要 CEO 決定」）
- 適用範圍：僅 product/stock-desk 產品線
- 與既有 ADR 的關係：不取代、不修訂任何既有 ADR。承接 PRD `work/stock-desk-庫存頁-PRD.md` §4 第 1 點與待裁定 Q1（是否新增 `PATCH /api/positions/{id}`）、Q3（`/positions/import` 轉址作法）。
- 編號說明：0013 缺號，但已被 ADR-0014、ADR-0016 與 `work/` 內的草稿引用（指員工線 `chore/agent-readonly-hook` 的唯讀 hook ADR），依 ADR-0001「編號不重用」不得挪用；0015、0016 已落檔，故本 ADR 使用 0017（來源：tech-architect 2026-10-03 裁定）。落檔時 `docs/adr/` 目錄查無 0017，`grep 0017` 於 repo 內亦無 ADR 引用。
- 來源與版本：本檔為 tech-architect 2026-10-03 裁定（「stock-desk 持倉部分更新與寫入路徑的市場幣別一致性」）的落檔，僅做格式調整，技術內容未增補。
  - Decision 的 D-1～D-4 原為裁定原文逐字轉錄（草案原編號 1～4）；D-5～D-7 為同一裁定另加之條文（D-5 來源：tech-architect B2）。
  - **2026-10-03 覆核裁定**：tech-architect 對落檔者註記 1～9 項逐一裁定，依其逐字指示改動：D-2 末句、D-4 全文與 CSV 補述、D-5 改寫、新增 D-8、C3～C6、新增 C9、T-5、T-14、新增 T-16～T-19、Consequences「代價」、「已接受缺口」與「已知不在本案」各新增一條。上述條文以裁定後版本為準；原 Decision 文字已被取代，不保留舊版。
  - Options 三張表：草案未逐項提供「優點／缺點／風險」，落檔者不補寫，改用「內容」「結論與理由」兩欄，理由只轉錄草案所給者。
  - 測試要求 T-1～T-15 的編號為落檔者依 tech-architect 清單的排列順序標示（store 5 項、API 10 項），草案若另有編號以草案為準；T-16～T-19 的編號由 2026-10-03 覆核裁定指定。
  - 落檔時的快照：分支 `product/stock-desk`，HEAD `7de98a4b8b5a46236b5e42fa5b88f0f1d507d6d0`（tech-writer 於落檔時讀取 `.git/refs/heads/product/stock-desk`）。此為快照，之後 HEAD 可能前進，行號與現況不保證相符。
  - 檔內 Context 對現況的描述，落檔者抽驗了 `store.update` 整列覆寫（`positions/store.py:248-251`）、`fill_sector_if_empty` 的 CAS 條件（`store.py:308-309`）、`_row_to_position` 建構 `Position`（`store.py:341`）、`PositionInput` 欄位預設（`positions/models.py:67,73,74`）、估值依 `{currency}TWD` 取匯率（`portfolio/valuation.py:400-404`，僅讀到 grep 命中行）；其餘由草案所述，未逐項重新驗證。
  - 檔末「落檔者註記」不屬 tech-architect 裁定，是落檔時對照 code 與 PRD 發現、待 tech-architect 確認的事項；確認前不影響上列決策文字。

---

## Context（背景）

- 庫存頁（`work/stock-desk-庫存頁-PRD.md`）要支援行內修正數量、平均成本、備註。
- 既有 `PUT /api/positions/{id}` 是整列覆寫。伺服端會回填 `sector`（`store.fill_sector_if_empty`，CAS 窄寫入）；行內修正若以 PUT 送出過期的整列，會把回填的 `sector` 蓋回 null。`opened_at`、`sector`、`note` 少帶即被靜默清空。
- 市場與幣別目前沒有一致性檢查。TW 搭配 USD 這類組合會讓估值靜默乘上 USDTWD。
- `_row_to_position` 讀 DB 時會建構 `Position`（繼承 `PositionInput`），因此會執行 `PositionInput` 的 validator。跨欄位驗證若放在模型層，既有的舊不一致列會讓 `list_all()` 崩潰。

---

## Options（選項比較）

三個題目各一張表，**粗體**為採用方案。採用：C、`PositionWriteInput`、`next.config` redirects。

**A. 部分更新的 API 形狀**

| 方案 | 內容 | 結論與理由 |
| --- | --- | --- |
| A 沿用 PUT | 行內修正也呼叫整列覆寫的 PUT | 未採用（見 Context：覆寫會蓋回 `sector`、少帶欄位靜默清空） |
| B 讀出合併整列寫回 | 讀出現有列、合併被改欄位、整列寫回（`alerts` 的寫法） | 未採用（見 D-2：不得以「讀出→合併→`store.update` 整列寫回」實作） |
| **C 只寫被改欄位（採用）** | `PATCH` 以單一 `UPDATE` 只寫被送出的欄位與 `updated_at` | 採用（見 D-1、D-2） |

**B. 市場／幣別一致性放在哪裡**

| 方案 | 內容 | 結論與理由 |
| --- | --- | --- |
| `PositionInput` 的 `model_validator` | 驗證放模型層 | 否決：讀取時 `Position` 會重新驗證，既有舊列會讓 `list_all()` 崩潰 |
| DB `CHECK` 約束 | 驗證放資料庫 | 否決：需重建表，且舊資料會使重建失敗 |
| 伺服端由市場推導幣別 | 不接受使用者送幣別，由市場決定 | 另案（本 ADR 不處理） |
| **寫入專用子類 `PositionWriteInput`（採用）** | 子類只在寫入路徑使用，跨欄位檢查只放這裡 | 採用（見 D-4） |

**C. `/positions/import` 舊路由轉址**

| 方案 | 內容 | 結論與理由 |
| --- | --- | --- |
| **`next.config` `redirects()`（採用）** | 設定層轉址，回 307 | 採用（見 D-6） |
| server component `redirect` | 在頁面元件內轉址 | 否決：閃現 |
| client `replace` | 前端導向 | 否決：閃現 |

---

## Decision（決策）

> D-1～D-4 為 tech-architect 裁定原文（D-2 末句與 D-4 依 2026-10-03 覆核裁定改動）。

**D-1**　新增 `PATCH /api/positions/{id}`，body 只接受 `quantity`、`avg_cost`、`note`（`extra="forbid"`）。未送的欄位不變；`quantity`、`avg_cost` 送 `null` 回 422；`note` 送 `null` 或空白則清除。驗證訊息與 `PositionInput` 逐字相同。

**D-2**　PATCH 以單一 `UPDATE` 只寫被送出的欄位與 `updated_at`；不得以「讀出→合併→`store.update` 整列寫回」實作。若日後 PATCH 擴及 `symbol`、`market`、`currency`、`sector`、`instrument_type` 任一欄，須改在 `BEGIN IMMEDIATE` 交易內讀、合併、驗證、只寫被改欄位，並以新 ADR 取代本則。body 未送任何欄位（`{}`）時不執行 `UPDATE`、不推進 `updated_at`，回 200 與現值；id 不存在仍回 404。

**D-3**　行內修正一律走 PATCH；PUT 保留為整筆覆寫，供進階修改彈窗使用。第一階段不做樂觀鎖（409）；日後如需，以被改欄位的舊值比對，不以 `updated_at` 比對。

**D-4**　市場與幣別必須一致：TW→TWD、US→USD，無例外。此檢查只存在於寫入路徑（POST、PUT 的 `PositionWriteInput`，以及 CSV 匯入的逐列檢查），錯誤位置為 `currency` 欄位。CSV 匯入以 `_parse_row` 對 `PositionWriteInput` 的每一條規則逐列先行檢查（同一訊息常數），全數通過後才建構 `PositionWriteInput`；建構不得先於檢查，否則模型層錯誤會成為 `POST /api/positions/import` 的 500。`PositionInput` 與 `Position` 不得再新增任何跨欄位不變式，因為 `Position` 會在讀取時重新驗證；既有的 `_sector_is_tw_only` 維持原位，不在本 ADR 移動（見 Consequences「已知不在本案」）。PATCH 不檢查此規則；既有不一致資料不自動修正，由使用者經 PUT 修正。

> 以下 D-5～D-7 為同一裁定另加之條文。

**D-5**　持倉寫入模型（`PositionInput`、`PositionWriteInput`、`PositionPatch`）所有產生使用者可見訊息的 validator 一律以 `PydanticCustomError` 拋出，使 422 回應的 `msg` 與訊息常數逐字相同、不帶「Value error, 」前綴（來源：tech-architect B2；先例 `app/kelly/models.py`）。

**D-6**　`/positions/import` 轉址一律設在 `next.config.ts` 的 `redirects()`，`permanent: false`（307）。

**D-7**　`DELETE /api/positions/{id}` 維持硬刪除；不得 cascade 刪除 `alert_rules`、`kelly_inputs`、`playbook_*`。

**D-8**　備註的空白語意四門一致：POST、PUT（`PositionWriteInput`）、PATCH（`PositionPatch`）與 CSV 匯入，空白或僅含空白的 `note` 一律存為 NULL。正規化只放寫入模型，不放 `PositionInput`（C3）。既有存為空字串的舊列不遷移；前端將空字串與 null 同樣顯示為「—」。

---

## Consequences（後果）

**好處：**
- `sector` 回填與行內修正的競態在結構上消失：PATCH 不寫 `sector` 欄。
- 估值不再被不一致的市場／幣別組合靜默算錯（寫入路徑擋下新的不一致資料）。

**代價：**
- 寫入有三個模型、四扇門：`PositionInput`（讀取與基底，不放新規則）、`PositionWriteInput`（POST、PUT、CSV 建構）、`PositionPatch`（PATCH），另加 CSV 逐列檢查須與 `PositionWriteInput` 同步（C9）。新增寫入規則時須同時改兩處並補測試，是持續的維護成本。

**已接受缺口：**
- `PositionPatch` 以 `extra="forbid"` 拒絕多餘欄位時，422 的 `msg` 為 pydantic 內建英文「Extra inputs are not permitted」；前端只送三欄，正常操作不會觸發，維持不另做訊息轉換（tech-architect 2026-10-03）。
- 既有不一致列（例如 TW 搭配 USD）仍可被 PATCH。三層保護：讀取不崩（C3、C4）、PUT 會擋（D-4）、合併前以唯讀盤點 SQL 清查（見「需要 CEO 決定」）。
- 兩個分頁同時修改同一欄位，最後寫入者勝（D-3：第一階段不做樂觀鎖）。
- 刪除持倉不 cascade（D-7）：以 (symbol, market) 為鍵的 `alert_rules`、`kelly_inputs` 會保留，警示照常依該代號評估（風險上限每次由現有持倉即時計算，不引用 position id），之後重新新增同代號時凱利輸入自動接上；playbook 不讀持倉，刪除對其無影響。資料表間沒有任何持久化的 position id 引用，因此不存在懸空 id。前端個股頁的 advice／leverage 快取可能短暫顯示舊的「部位 ID」，建議所有持倉 mutation 一併失效 `["advice"]`、`["leverage"]`（非擋件）。

**已知不在本案：**
- 進階修改彈窗走 PUT，仍有過期 `sector` 的競態。
- 彈窗改代號、市場、幣別，會讓凱利輸入（`kelly_inputs`）與警示規則（`alert_rules`）變孤兒。
- playbook 的股數與持倉是兩套資料。
- 既有讀取期 validator 的潛在崩潰：`_sector_is_tw_only`（US 列帶 `sector`）與產業別封閉清單檢查（清單日後刪減某類別時，帶該類別的舊列）都在 `Position` 讀取時執行，資料若經 DB 直接寫入或清單變動，`list_all()` 會拋例外。現行各寫入門都擋得住，屬低機率；將讀取期 validator 移至寫入模型另案處理，屆時須另開 ADR。

---

## 對實作的約束（逐條可檢查）

- **C1**：前端 FR-3（行內修正）只呼叫 PATCH；body 的 key 為 `quantity`、`avg_cost`、`note` 的子集合；行內不得呼叫 `updatePosition`。
- **C2**：store 的 PATCH 實作不得呼叫 `update` 或 `get` 後整列寫回；`SET` 只列被送出的欄位（加 `updated_at`）。
- **C3**：`PositionInput`、`Position` 不得新增任何 validator（含 market／currency 一致性）；新的寫入期規則只能加在 `PositionWriteInput` 或 `PositionPatch`。
- **C4**：`list_all()` 遇 TW＋USD（或 US＋TWD）舊列不拋例外。範圍僅限本 ADR 新增的市場／幣別規則；既有讀取期 validator 的舊資料風險見 Consequences。
- **C5**：`apps/stock-desk/frontend/app/` 的非測試原始碼不得以 `/positions/import` 作為導覽目標（`href`、`router.push`／`replace`、`redirect()`）；唯一例外為 `next.config.ts` 的 `redirects()` 及其測試。另依 PRD R7，`homeReflow.test.ts` 的導覽高亮斷言、`componentWordingScan.test.ts` 的掃描路徑、`positionsTableView.ts` 的註解與 `frontend/README.md` 一律改為 `/positions`。
- **C6**：DELETE 不 cascade（D-7），由 T-18 驗證。
- **C7**：新增的錯誤字面由 creative-lead 確認；前端不自創驗證文案。
- **C8**：行內無法顯示的 `fieldErrors`，退回 `ErrorPanel`。
- **C9**：`csv_io._parse_row` 建構的是 `PositionWriteInput`，且建構語句位於所有 `fail(...)` 檢查與 `if errors: return` 之後；`PositionWriteInput` 每新增一條規則，`_parse_row` 須同步新增對應逐列檢查與測試。

---

## 測試要求

**後端 store（pytest）**
- **T-1**：只改 `quantity`，其他欄位不變。
- **T-2**：競態回歸：`fill_sector_if_empty` 之後做 PATCH，`sector` 保留。
- **T-3**：`note` 三種語意（未送＝不變、`null`＝清除、空白＝清除）。
- **T-4**：id 不存在時回 `None`。
- **T-5**：空 patch（`{}`）回 200 與現值，`updated_at` 不變；空 patch 打不存在的 id 回 404。

**後端 API（pytest）**
- **T-6**：PATCH 成功回 200，且 `GET` 反映新值。
- **T-7**：`quantity=0` 回 422，`loc` 為 `body.quantity`，訊息與 `PositionInput` 逐字相同。
- **T-8**：多餘欄位回 422。
- **T-9**：`quantity`／`avg_cost` 送 `null` 回 422。
- **T-10**：id 不存在回 404。
- **T-11**：既有不一致列（TW＋USD）PATCH 成功，且 `GET` 與 summary 不回 500。
- **T-12**：POST 市場／幣別不一致回 422，`loc` 為 `currency`。
- **T-13**：PUT 市場／幣別不一致回 422。
- **T-14**：CSV 含合法列與市場／幣別不一致列混合時，回 200（非 500），不一致列產生 `RowError(field="currency")`、訊息與 API 逐字相同，合法列照常匯入。
- **T-15**：demo seed 符合市場／幣別規則表（TW→TWD、US→USD）。
- **T-16**：參數化測試逐一觸發 symbol 空白、指數代號、`quantity`、`avg_cost`、`opened_at`、產業別封閉清單、`_sector_is_tw_only`、市場／幣別一致性（POST）與 `PositionPatch` 的 `quantity`／`avg_cost`（含 `null`），斷言 422 的 `msg` 與對應訊息常數**完全相等**，且不以 `Value error` 開頭。
- **T-17**：POST 與 PUT 送 `note: "   "`，回傳與 `GET` 的 `note` 皆為 `null`。
- **T-18**（pytest）：建立持倉，並以各 store 的公開方法為同一 (symbol, market) 建立一筆 `alert_rules` 與一筆 `kelly_inputs`；`DELETE` 該持倉回 204 後，兩者仍存在且內容不變。

**前端（單元測試）**
- **T-19**：載入 `next.config.ts` 並呼叫 `redirects()`，斷言含 `{ source: "/positions/import", destination: "/positions", permanent: false }`；且 `app/positions/import/page.tsx` 不存在。

---

## 需要 CEO 決定

1. 核可本 ADR。
2. 合併前，在實機 DB 跑唯讀盤點 SQL：

   ```sql
   SELECT id, symbol, market, currency FROM positions WHERE (market='TW' AND currency<>'TWD') OR (market='US' AND currency<>'USD');
   ```

   有結果時，用進階修改彈窗（PUT）逐筆修正。

---

## 相關檔案（絕對路徑，草案所列）

後端（`/home/user/AICompany/apps/stock-desk/backend/`）：
- `app/api/positions.py`
- `app/positions/models.py`
- `app/positions/store.py`
- `app/positions/csv_io.py`
- `app/directory/sector_backfill.py`
- `app/directory/sync.py`
- `app/portfolio/valuation.py`
- `app/kelly/models.py`

前端（`/home/user/AICompany/apps/stock-desk/frontend/`）：
- `app/components/EditPositionModal.tsx`
- `app/components/EmptyPositionsState.tsx`
- `app/lib/api.ts`
- `app/lib/queries.ts`
- `next.config.ts`

文件：
- `/home/user/AICompany/work/stock-desk-庫存頁-PRD.md`
- `/home/user/AICompany/work/stock-desk-庫存頁-視覺規範-2026-10-03.md`

落檔者補列（草案未列，因 T-15 提到 demo seed 而補，僅路徑）：
- `/home/user/AICompany/apps/stock-desk/backend/app/demo/seed.py`

---

## 落檔者註記（落檔時發現的出入；9 項皆已由 tech-architect 於 2026-10-03 裁定）

tech-writer 落檔時對照 code 與 PRD，發現下列條文與現況或條文之間有出入，並提交 tech-architect。9 項皆已裁定，裁定結果已併入上方 Decision、Consequences、C、T 各節；本節保留原發現文字作為追溯，各項後方標明裁定落點。原發現的行號為落檔時快照，裁定改動後可能漂移。

1. **【已裁定（2026-10-03）→ D-4、C3、C4、Consequences「已知不在本案」】D-4「不得加入任何跨欄位不變式」與現有程式**：`PositionInput` 目前已有一個跨欄位的 `model_validator`（`_sector_is_tw_only`，非 TW 且帶 `sector` 即拒絕，`positions/models.py:90-94`），`Position` 讀取時同樣會執行。請確認 D-4 的「不得加入」是指「不再新增」，還是要求移除既有者；並確認既有的 US 列帶 `sector` 的舊資料是否也屬 C4 的檢查範圍。
2. **【已裁定（2026-10-03）→ D-8、T-17】D-1「`note` 空白則清除」與現有寫入行為**：`PositionInput.note` 沒有 validator，`str_strip_whitespace=True`（`models.py:57,74`）下空白 `note` 經 POST／PUT 會存成空字串；CSV 路徑則是 `note_raw or None`（`csv_io.py:193-194`）。PATCH 將空白清除為 null，與 PUT 的空白結果不同，請確認是否接受此差異（影響 T-3 的斷言）。
3. **【已裁定（2026-10-03）→ D-2 末句、T-5】空 patch 的行為未在 Decision 定義**：D-2 寫「單一 `UPDATE` 只寫被送出的欄位與 `updated_at`」，T-5 卻要求空 patch 不推進 `updated_at`；Decision 未說明 body 為 `{}` 時回 200（回現況）、422 或其他。
4. **【已裁定（2026-10-03）→ C5】C5 與現況**：`"/positions/import"` 目前出現在 `NavBar.tsx:285`、`EmptyPositionsState.tsx:11`、`frontend/README.md:23`，另有 `positionsTableView.ts:399` 註解與 `homeReflow.test.ts` 多處（測試中是 `isNavItemActive` 的參數，不是 href）。C5 例外只列 `next.config` 與其測試，請確認 `homeReflow.test.ts`、註解、README 是否須一併改（PRD R7 已列測試與 README 須同步）。
5. **【已裁定（2026-10-03）→ D-5、T-16】D-5 與 T 清單**：D-5 沒有對應的測試項。T-7 的「訊息逐字相同」只涵蓋 `quantity`；`avg_cost`、`sector`、`symbol`、`opened_at` 與既有 `_sector_is_tw_only` 的訊息是否也要釘「無 `Value error, ` 前綴」未說明。專案內已有先例：`app/kelly/models.py:118-139` 以 `PydanticCustomError` 處理同一問題。
6. **【已裁定（2026-10-03）→ T-18、T-19、C6】D-6、D-7 與 T 清單**：D-6（307 轉址）與 D-7／C6（DELETE 不 cascade）沒有編號的測試項；C5 只提到「`next.config` 的測試」。請確認是否補 T 項。
7. **【已裁定（2026-10-03）→ D-4 CSV 補述、C9、T-14】D-4 與 CSV 路徑**：CSV 目前在逐列檢查全數通過後才建構 `PositionInput`（`csv_io.py:196-211`），其檔內註解（`csv_io.py:159-163`）說明模型層才擋得住的檢查會變成未捕捉的 `ValidationError`（`POST /api/positions/import` 的 500）。D-4 寫「CSV 匯入的逐列檢查」，請確認 CSV 是否繼續建構 `PositionInput` 還是改用 `PositionWriteInput`（若改用，須確保逐列檢查先於建構，否則會產生 500）。
8. **【已裁定（2026-10-03）→ Consequences「代價」】Consequences「兩個模型兩扇門」**：實作將有 `PositionInput`、`PositionWriteInput` 與 PATCH 的 body 模型三個模型，加上 CSV 逐列檢查，請確認措辭。
9. **【已裁定（2026-10-03）→ Consequences「已接受缺口」】D-7 的連帶後果**：DELETE 不 cascade 意味刪除持倉後 `alert_rules`、`kelly_inputs`、`playbook_*` 仍保留相關列；Consequences 的「孤兒」只列了彈窗改代號／市場／幣別的情形，未列刪除持倉的情形，請確認是否為有意。
