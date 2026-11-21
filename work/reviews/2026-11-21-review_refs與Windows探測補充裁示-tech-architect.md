# RC-496 review_refs 與 RC-497 Windows 探測補充裁示

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 補充裁示：RC-496 `review_refs` 與 RC-497 Windows 探測（2026-11-21）

這次是在原報告送出之後，回 coordinator 轉來的兩題。全程唯讀：只用 Read 和 Grep，沒有寫檔，沒有讀 `.env*`。

## 本次結論

- **RC-496**：【裁示】`review_refs` **要加**兩條路徑：風控的補充核對報告，以及新的 qa M-9 最終紀錄。
  - 加在原有 5 條之後；原 5 條的內容和順序都不變。
  - `review_refs` 不在我約束第 8 點的範圍內。
  - 時點：兩條路徑要在新 head 送最終 qa **之前**就寫成常數；兩份紀錄本身，等 qa 審完之後再 commit。順序不是「等風控報告存檔之後才加」。
- **RC-497**：【裁示】Windows 實機探測**不列為**正式登記的前置條件。
  - 登記紀錄照 RC-497 的字面寫「Windows 實機探測：未完成」。
  - 有兩個條件，見下方。
- 兩題都不需要 CEO 決定。

## 各部門回報（tech-architect）

### 第 1 題：`review_refs`（RC-496）

**範圍界定**
- 【事實】我約束第 8 點寫的是「M-2～M-5 的 `REAL_PINS` 不得變動」。對應到 `Pins` 的欄位，是 `frozen_files`（M-2、M-3）、`definition_*`（M-4）、`rules`（M-5）。
- 【事實】`review_refs`（`cg2_register.py` 第 195～201 行）是另一個欄位，依據是補充七附記三第 4 點。所以它不在第 8 點的字面範圍內。
- 【事實】RC-496 (e) 把 `review_refs` 也列進「不變」，那是風控自己加的範圍。風控已寫明「若加入，我也不反對」。

**為什麼要加**
- 【事實】附記三第 4 點（ADR-0030 第 940～944 行）規定，`review_refs` 要列「M-9 的風控核對與 qa 最終審查」。
- 【事實】`review_refs` 會隨登記永久寫進登記表。
- 【推論】這次登記的是新 head，M-9 的核對對象也是新 head。只列 11-17 那兩份（對象是 `9d5bbf48`），帳內引用的 M-9 核對就和實際登記的 commit 對不上。
- 11-17 那兩份保留：新 head 的內容和 `9d5bbf48` 相同，是靠它們加上補充核對一起證明的。

**dev-lead 的做法（逐條可查）**
1. coordinator 先定下兩個檔名。檔名必須是 repo 根目錄起算的相對路徑，不得含空白（第 4 點）。例如：
   - `work/reviews/2026-11-2x-CG2登記PR-M9補充核對M2M3M6-風控.md`
   - `work/reviews/2026-11-2x-CG2登記PR-M9補充最終審查-qa.md`
2. dev-lead 在 (甲) 的分支上另開一個 commit（不和 regex 修正混在同一個 commit），做兩件事：
   - 把這兩條路徑依「風控、qa」的順序，加在 `REAL_PINS.review_refs` 的最後；
   - 同步更新 `tests/test_cg2_register_values.py` 第 134～147 行的期望值。
   - 原 5 條逐字不變，順序也不變。
3. 以下照原本的設計處理，不得 skip、xfail 或弱化：
   - `test_the_review_refs_all_exist_at_head`（第 150 行起），在兩份紀錄 commit 之前會失敗；
   - 執行期的 `check_review_refs` 會 STOP `review_refs_missing`。
4. 最終 qa 審的 head 要包含這個 commit。兩份紀錄由 coordinator 在 qa 之後 commit（都在 `work/`，屬補充六第 6 點 (d) 允許的差異；R-1 不涵蓋這兩條路徑）。CG-2 PR 合併時，兩份紀錄都要已經在 HEAD 裡。
5. 兩份紀錄 commit 之後，CG-2 head 又會前進。【建議】風控照 RC-496 末段辦：只核對有差異的地方。這時的差異只有 `work/reviews/` 下新增的兩個檔。
6. `tests/test_cg2_registration_values.py` 不受影響（Grep 確認裡面沒有 `review_refs`），維持零差異。

**要風控改讀的地方**
- RC-496 (e) 的「review_refs 不變」，改讀成「review_refs 只在最後加上第 1 點的兩條，原 5 條逐字、依原順序不變」。
- 風控補充報告的檔名要和第 1 點的常數逐字相同。

### 第 2 題：Windows 實機探測要不要列為登記前置（RC-497）

**裁示：不列為前置。理由如下。**
1. 【推論】`.env` 的解析在 uv 內部，邏輯應該和平台無關。平台會造成差異的地方，主要是鍵名大小寫，而 (甲) 已經規定 regex 不分大小寫。所以 Windows 實機探測主要是補強證據，修正本身不靠它。
2. 【事實】目前沒有 Windows 測試機，也沒有執行者和時程。列為前置等於讓登記無限期延後，前瞻紀錄的起點也跟著延後。
3. 【推論】假設真的有 Windows 才會載入、而 regex 抓不到的寫法，而且 CEO 的 `.env` 剛好用了它，後果是 scheduler 跳過、不記錄，不會寫錯資料庫，狀態報告或心跳可以發現。延後登記的代價，比這個殘餘風險大。

**條件（逐條可查）**
- (a) Linux 探測照我約束第 9 點，仍然是 CG-2 合併的前置。另外加一項：探測用的寫法要各有 CRLF 換行的版本，因為 Windows 上的 `.env` 多半是 CRLF。結果要逐項成立「有載入就一定比對到」。
- (b) Windows 實機探測留在 devops-sre 的驗證清單上，有測試機時和 QuickEdit 一起做。如果發現漏網的寫法：
  - 當天書面送 tech-architect 和風控；
  - 登記紀錄不得改寫，另外 append 一則更正；
  - 怎麼處理由 tech-architect 裁示；
  - 不得叫 CEO 去查看 `.env`（RC-432 (c)、RC-417 (d)）。

## 驗證

- 讀過：
  - `cg2_register.py` 第 142～202、721～729、1065～1068、1118～1121 行；
  - `tests/test_cg2_register_values.py`、`tests/test_cg2_register_addendum3.py` 的 `review_refs` 段落（Grep）；
  - ADR-0030 補充七附記三第 4 點（第 940～944 行）；
  - 風控 RC-495～RC-498 段落。
- 沒有查證：
  - dev-lead 進行中的 (甲) 分支內容；
  - 風控補充報告和新 qa 紀錄的實際檔名；
  - uv 在 Windows 上的實際行為。

## 下一步

- **要送風控的**：第 1 題 RC-496 (e) 的改讀，以及補充報告檔名要和常數一致；第 2 題「不列前置」的裁示和條件 (a)、(b)。
- **dev-lead**：照第 1 題第 2～3 點，另開一個 commit。交件時附 (甲) 的探測證據，CRLF 版本也要涵蓋。
- **coordinator**：先定兩個檔名再交給 dev-lead；qa 審完之後 commit 這兩份紀錄；登記紀錄用 RC-497 的字面，填「未完成」。
- **devops-sre**：Windows 實機探測維持在驗證清單上，沒有時限。
- **有沒有必須由 CEO 決定的事**：沒有。
