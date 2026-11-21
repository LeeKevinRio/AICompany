# 三份舊 CEO 文件標註套用交件（docs/legacy-ceo-docs-notice）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
已完成：從 origin/product/stock-desk 開 `docs/legacy-ceo-docs-notice`，三份舊文件各一個獨立 commit，已 push（`git push -u`）。沒有開 PR、沒有合併，也沒有 amend、rebase 或 force push。三份檔都在 base 上被追蹤，不需搬動。驗證 1～8 點全部符合，沒有任何差異需要處理。

- base SHA：`7b54beb30a32b2fc3b225bd87b5876d556e8c0f6`（`origin/product/stock-desk` 的最新 head，我 fetch 後取得）
- worktree 路徑：`/home/user/AICompany/.claude/worktrees/agent-ad164245da4946303`（停在 head，工作樹乾淨）
- commit，由舊到新：
  1. `904c5c488937d41b502b9e14670480217ca0f91e` docs: 族群動能無資料檢查手冊加註給 CEO 的標註與警示
  2. `d7b17b07569646da9fd4f611e9ebfbbdbd958391` docs: 警示評估載入失敗檢查手冊加註給 CEO 的標註與警示
  3. `dc81ac9519ef34606d71a861d48abd0d69842927` docs: 產品說明加註給 CEO 的標註與警示（head）
- 三個 commit 的結尾都有指定的兩行 trailer。repo 內容沒有寫 model ID。

## 各部門回報（devops-sre）
**做法。** 腳本放在 scratchpad，沒有 commit：
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/apply.py`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/verify.py`

腳本從風控檔「三份文件各處定稿全文」一節擷取 23 個四反引號區塊，區塊數與預期完全相符。套用前先 assert：
- 每個標題原文在該檔恰好出現一次，且標題下一行是空行；
- 讀者行原文恰好出現一次，且在第 5 行；
- 檔案沒有 CR，結尾是 LF。

位置先在未插入的原檔上決定，再由後往前插入，避免行號位移。

**判斷與歧義**
1. G-6、P-3、P-4、P-5 風控另註明的插入位置，與通則「標題下原有空行之後」一致。我另外確認過 G-6 的下一行是 `### A.`、P-3 是 `### 目的`、P-4 是 `### Docker（推薦）`、P-5 是 `**Q: Confidence 是勝率嗎？**`。
2. 風控檔的 G-0、A-0、P-0 區塊，最後一行是區塊內的空行，並沒有歧義。我以此為檔頭的最後一行空行，行數正好是 17、13、10。
3. G-2 與 G-5 的警示全文相同，所以驗證不能用「全文唯一」判斷，我改以「標題位置加 2 行」比對。
4. 標題行號與風控給的行號全部吻合（39、77、81、122、142、225；12、59、85、133、170；247、373、395、437、487）。
5. 風控檔本身在 base 上就已追蹤，在 worktree 內可直接讀到，沒有用到 `/home/user/AICompany/` 那份。
6. 沒有任何縮排或區塊邊界的歧義需要用保守方式處理。

## 驗證（實際輸出）
1. **行數與淨增。** 三檔原本都是 LF 結尾，沒有 BOM、沒有 CR。

   | 檔 | 原 `split('\n')` | 新 `split('\n')` | 淨增 | 結尾 LF | Read 行數換算 |
   |---|---|---|---|---|---|
   | 族群 | 334 | 363 | +29 | 是 | 333→362 |
   | 警示 | 201 | 224 | +23 | 是 | 200→223 |
   | 產品說明 | 540 | 560 | +20 | 是 | 539→559 |

   `git diff --stat` 為族群 31 行（30 增 1 刪）、警示 25 行（24 增 1 刪）、產品說明 20 行（全為增）。刪除的 1 行就是讀者行替換。
2. **逐處與定稿 `==` 比較。** 全部為 True，涵蓋：
   - 族群：G-0、G-R、G-1～G-6；
   - 警示：A-0、A-R、A-1～A-5；
   - 產品說明：P-0、P-1～P-5。

   讀者行新位置：族群第 22 行、警示第 18 行。
3. **插入形式。** 每處都是「前一行空行、前兩行是標題（以 `#` 開頭）、後一行空行」，全部為 True。警示所在行號如下：
   - 族群：58、98、104、147、169、254；
   - 警示：27、76、104、154、193；
   - 產品說明：259、387、411、455、507。
4. **`> **給 CEO：` 開頭的行數。** 族群 7、警示 6、產品說明 6，符合預期。
5. **`這份標註只針對`、`大多只是說明`。** 三檔都是 0 次。
6. **換行與編碼。** CR 0（與原檔一致，皆為 LF），行尾空白 0，UTF-8 可解碼，無 BOM。
7. **`git diff 7b54beb… --stat --name-only`。** 只有那三個檔，其他檔零差異。
8. **base。** 是 `product/stock-desk`。

**repo 內對這三份檔的引用。**
- 測試或腳本（`*.py`、`*.sh`、`*.bat`、`*.yml`、`*.json`、`*.ts`、`*.tsx`、`*.js`、`*.toml`）：搜尋檔名、`L61`、`L303`，零命中，沒有程式讀這三份檔的內容或行號。
- 文件引用，不需改，共 28 個檔、71 處。主要有：
  - `apps/stock-desk/README.md`
  - `docs/adr/0025-stock-desk-產品定位改為提供投資建議.md`
  - `work/stock-desk-新定位-需求總綱與分期-2026-10-15.md` 第 537 行，寫「族群動能無資料檢查手冊 L61、L303」。這份手冊插入後，這兩個行號會位移，風控已說明日後以標題定位。
  - `work/stock-desk-新定位-字面遷移清單-2026-10-16.md`（15 處）
  - 多份 `work/reviews/` 與 `work/dispatch/` 檔，其中風控與 tech-architect 的 2026-11-21 審查件引用最多。

## 下一步
- qa-reviewer（含 Codex）依 RC-474 第 1～8 點核對，並附確認句。
- 風控單項確認需要：head SHA `dc81ac9519ef34606d71a861d48abd0d69842927`、上述工作樹路徑、base 名稱 `product/stock-desk`、三份檔被 `product/stock-desk` 追蹤的確認（本件已做）。
- 本件沒有開 PR。依 RC-475，合併須在接線 PR 之前，且不得在預檢到登記完成之間 push。
  - **未確認：我 push 的時點是否落在「預檢到登記完成」的窗口內。** 我沒有該狀態的資訊，請 coordinator 確認。
  - 若有衝突，需要決定這支分支要不要先撤下。
- 若與 README PR 合成同一支，須依 RC-475 的 (a)～(e)。

沒有查證的事：
- 沒有跑任何 CI，也沒有跑 `validate_agents.py`，因為這次只動 `work/` 底下的文件；
- 沒有查 GitHub 上是否已有人對這支分支開 PR；
- 沒有核對警示手冊維護人，也沒有查 QuickEdit，這兩項屬 tech-architect。
