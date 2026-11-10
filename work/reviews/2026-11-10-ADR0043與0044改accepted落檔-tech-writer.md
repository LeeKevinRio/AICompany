# ADR-0043、0044 改 accepted 與 J-10 檔頭註記落檔

- 審查者：tech-writer
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
五項任務皆已完成，未切分支、未 commit。有一個需要你決定的小衝突：ADR-0044 的 `portfolio_with_stamp` grep 結果是 1，不是 0。原因是你要求我在狀態變更紀錄寫「由 portfolio_with_stamp 改為 portfolio_and_stamp」，這句本身就含舊名。檔內正文已無舊名，剩下的 1 筆就是第 4 行這句。如果腳本要求嚴格為 0，請告訴我改寫該句，例如寫成「由舊暫稱改為 portfolio_and_stamp」。

## 各部門回報（逐檔改動，行號為改後行號）

**ADR-0043**（路徑：`/home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md`）
- 第 3 行：`- 狀態：proposed` 改為 `- 狀態：accepted（CEO #136 於 2026-11-10 核可，核可明示包含 ADR-0034 補充四及 #136 列出的全部 7 項，原文如下：(1)…(7)…）`。7 項照抄 #136 原文，來源是 `work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 第 172 行。
- 新增第 4 行「狀態變更紀錄」：
  - 內容：本 ADR 原以 proposed 落檔；2026-11-10 CEO #136 書面裁示「ADR-0043 與 ADR-0034 補充四改為 accepted；J-10 的檔頭註記生效」，自 2026-11-10 起依 J-9 生效。
  - 另註明既有的核可前敘述依 accepted ADR 只能 append 的規則保留原文不改。
- 原第 4 行起的「日期」等內容順延一行。
- 核可前的敘述（例如第 519 行、第 619 行的 proposed 字樣）完全沒動。
- J-n 與 I-n 條款文字未動。

**ADR-0034**（路徑：`/home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md`）
- 補充四第 7 行及其下的 J-1～J-10 原文未動，狀態行（第 3 行）未動。
- 在 J-10（第 28 行）之後、第 30 行「日期」之前，新增第 29 行，與 J 條款同縮排層級，也就是補充四的末尾：`  - 2026-11-10 CEO #136 核可 ADR-0043，明示包含本補充四；本補充四自當日起為 accepted，依 J-9 生效。`
- 這一行不是 `**J-n**` 或 `**I-n**` 格式，不會被條款比對誤抓。

**ADR-0044**（路徑：`/home/user/AICompany/docs/adr/0044-stock-desk-排程台REBALANCE之後-未結算的R系列買進列如何處置.md`）
- 第 3 行：`- 狀態：proposed` 改為 `- 狀態：accepted（CEO #137 於 2026-11-10 核可，原文：「核可（Recommended）。ADR-0044 改為 accepted，內容依寫法 A、時序選項 1、選擇修正。殘留 R-a～R-g 全部已有裁示。N-210a、N-210b 可以開工」）`。
- 新增第 4 行「狀態變更紀錄」：
  - 內容：原為 proposed，2026-11-10 CEO #137 核可後改為 accepted。
  - 同次修訂：store 方法暫稱由 portfolio_with_stamp 改為 portfolio_and_stamp，語意不變。
  - 補充：這是 dev-lead v3.1 交件要求，也是在 accepted 之前的同一次修訂一起做。
- 原第 89 行（現第 90 行）：`暫稱 \`portfolio_with_stamp()\`` 改為 `暫稱 \`portfolio_and_stamp()\``。「暫稱」兩字保留。
- 原第 362 行（現第 363 行）：`同一次 \`portfolio_with_stamp()\` 呼叫` 改為 `同一次 \`portfolio_and_stamp()\` 呼叫`。

**J-10 檔頭註記**
- J-10 原文：「本判定生效後，由 tech-writer 在 ADR-0035、0041、0042 檔頭各加一行指向 ADR-0043 D3 第 7 點的註記；生效前不加。」
- 它指定了加註位置與指向，但沒有指定註記文字，所以我寫了最短的事實敘述，並引用 J-10 與 CEO #136。
- 註記格式：`- 註記（依 ADR-0034 補充四 J-10，2026-11-10 CEO #136 核可後生效）：ADR-0034 補充四 J-3 對本檔〔對應約束〕作範圍判定，見 ADR-0043 D3 第 7 點；本檔原文不改。`
- 各檔的〔對應約束〕與插入位置如下，三檔皆為單行插入：
  - ADR-0035：附錄 B 的 N172-C3「engine 零 diff」。插在第 4 行，位於狀態行之後、補充一之前。
  - ADR-0041：「限制」與「與其他 ADR 的關係」中的「engine 零 diff（C-B11）」。插在第 4 行，位於狀態行之後、日期之前。
  - ADR-0042：N198-C1「engine.py 零 diff」。插在第 4 行，位於狀態行之後、日期之前。
- 對應約束與 ADR-0034 補充四 J-3 的列舉一致。
- 注意：ADR-0041 的狀態目前仍是 proposed，我沒有動它，因為任務沒有要求。

## 驗證
- `portfolio_with_stamp` 在 ADR-0044：共 1 筆，在第 4 行狀態變更紀錄。正文（第 90、363 行）0 筆，這兩處已是 `portfolio_and_stamp`。
- `portfolio_with_stamp` 在 `docs/adr/*.md` 其他檔：改前只有 ADR-0044 有。
- J-n 與 I-n 條款：我只用 Edit 新增行，沒有改動任何條款行。ADR-0034 的 J-1～J-10 已用 grep 確認仍在，位置為第 9～28 行。
- 未做的驗證：沒有 Bash，無法跑 diff 或你的比對腳本，請 coordinator 自行跑。
- 未讀 `.env`，未碰 `*.db`。

## 下一步
1. 請決定 `portfolio_with_stamp` 的 grep 是否要嚴格為 0，需要的話我改寫 ADR-0044 第 4 行。
2. 請 coordinator 跑條款逐字比對腳本，並 commit。
3. ADR-0041 狀態仍為 proposed，若 CEO 另有核可裁示再處理。
4. 本次沒有 A 類技術宣稱。所有 B 類敘述的來源都是 `work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 的 #136（第 172 行）與 #137（第 173 行）原文，以及 ADR-0043 D3 第 7 點與 ADR-0034 補充四 J-3、J-9、J-10。快照基準是目前 product/stock-desk 工作樹，尚未 commit，行號請以原文定位。

---

## coordinator 註記（2026-11-10）
- 條款逐字比對腳本（ADR-0034 補充四 J/I 對 ADR-0043 D3 第 7 點）：True。
- `portfolio_with_stamp` 只剩 ADR-0044 第 4 行狀態變更紀錄 1 筆，是改名紀錄本身。coordinator 定案（CEO 可推翻）：保留。驗收標準改為「正文 0 筆」，第 90、363 行已是 `portfolio_and_stamp()`。
- ADR-0041 狀態仍為 proposed，本次不處理，列入追蹤清單。
