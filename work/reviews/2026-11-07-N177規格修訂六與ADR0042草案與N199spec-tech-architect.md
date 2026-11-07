# N-177 規格修訂六、ADR-0042 草案（N-198）、N-199 spec

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

### 先回答：風控 N-197 (b) CEO 通知的前提 (1)

**會跑完。** 前端在 `/today` 讀取中重新整理或取消請求，後端那一次同步 `def` 的 `/today` 都會照樣執行到結束。前提 (1) 成立，通知裡「，或在頁面讀取中重新整理」與「，頁面讀取中不要重新整理」兩句都不用刪。

依據如下。程式與套件原始碼都是讀碼判斷，沒有執行。版本取自 `uv.lock`，venv 內 `__version__` 相同：fastapi 0.139.2、starlette 1.3.1、uvicorn 0.51.0、anyio 4.14.2。

1. **端點與依賴都跑在 threadpool，中途停不下來。**
   - `/today` 是 `def today(...)`（`app/api/playbook.py:581-582`）。它的兩個依賴 `get_playbook_service`、`get_cap1_reading` 也都是 `def`。
   - FastAPI 對非 coroutine 端點走 `run_in_threadpool`（`fastapi/routing.py:337-347`）。Starlette 的 `run_in_threadpool` 就是 `anyio.to_thread.run_sync(func)`（`starlette/concurrency.py:32-34`），沒有傳 `abandon_on_cancel`，預設是 False。依 `anyio/to_thread.py:27-46`，host task 被取消時，要等 worker thread 跑完才生效。
   - Python 的 thread 本身也無法從外部中斷。
2. **uvicorn 在 client 斷線時不取消 app。**
   - `connection_lost`（`h11_impl.py:107-130`、`httptools_impl.py:116-126`）只把 `cycle.disconnected` 設為真，並喚醒 `receive`。
   - 之後的 `send` 直接 return（`h11_impl.py:464-465`）。也就是回應被丟掉，但端點照跑。
3. **本 repo 沒有會在斷線時中斷請求的 middleware。**
   - `app/main.py:59-69` 裝了三層，都是純 ASGI：`CorsVisibleServerErrorMiddleware`、`RequireClientHeaderMiddleware`（GET 直接放行）、Starlette 的 `CORSMiddleware`。
   - 三層都沒有讀 `receive` 去等 `http.disconnect`，也沒有用 `BaseHTTPMiddleware`。
   - 我在 venv 內 starlette 的 `routing.py`、`_exception_handler.py`、`applications.py`、`middleware/{cors,errors,exceptions}.py` 與 `fastapi/routing.py` grep `disconnect`、`is_disconnected`、`cancel_scope`，零筆。
4. **前端的取消不會中止 HTTP 請求。**
   - `getPlaybookToday()`（`frontend/app/lib/api.ts:437-439`）沒有接 TanStack 傳入的 `signal`。依 `query-core/src/query.ts:444-457`，signal 沒被讀過，`cancelQueries` 就不會 abort fetch，請求會照樣送完。
   - 重新整理或關分頁時，瀏覽器會中止 fetch，但依第 1、2 點，後端仍然跑完。
   - 重新整理後的新頁面會立刻送出新的 `/today`，**與舊的那次在後端並行**。這正是通知所說的並發。
5. **唯一會讓它中途停止的是行程終止**：關掉後端視窗、`dev-up.bat:150` 的 `uvicorn --reload` 偵測到程式檔變動而重啟，或當機。這屬於 R-6′ 的失敗變體，不是重新整理造成的。

**順帶給風控的一點（不改上面的結論）：** 通知裡並發情況的例子不完整。
- 出清的 `onSettled` 會先 `cancelQueries`、再 `invalidateQueries`（`queries.ts:522-525`）。
- 若當下有 `/today` 在途，舊請求照樣跑完，新請求同時開始（`query.ts:404-419`；`queryClient.ts:317-319`，`cancelRefetch` 預設為 true）。後端就會有兩個 `/today` 並行。
- coordinator 只被授權刪字，要不要補這個例子，由風控決定。

### 本次交付
- **修訂六**：coordinator 已通知，原「修訂五」改稱修訂六，內容不變。
  - 補上 C8 的五項 required，並同時套用到 N197a-C8。
  - 補上 N-197a 的四項 required：
    - T10；
    - 鍵不存在的分支：我**選「視為不變式違反、依 C-11 失敗」**，不新增任何字面；
    - set_at 換算成台北時間，精確到秒，並標示「台北時間」；
    - 在 docstring 寫明 `previous_total_deploy` 的語意。
  - 三項 suggested 全部採用。
  - 我讀過另一位 TA 的修訂五（N-177a 停止點），和本修訂沒有重疊的段落。
- **ADR-0042 草案**（`docs/adr/` 目前最大號是 0041）：每一筆結算列的 claim、動帳與 schedule 標記，都在同一個 `BEGIN IMMEDIATE` 內完成。
  - :382「buy 的 UPDATE 沒有 planned 守衛」**會一併消除**。
  - :314 的 E-2 並發窗口**不會消除**，只是少了一個觸發來源。
  - 先後順序：必須在 N-177a 之後；預設也在 N-177b 之後。
- **N-199 spec**：照風控要求新增兩項唯讀檢查。我另外加了第三項 N199-C「同一批有兩筆以上已判定成交的買進」（[TA 補]，要不要列為 required 待風控決定）。理由是失敗變體發生後，使用者若照第二張指令買進而且結算成功，批次會變成 open，A 與 B 兩項都抓不到。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 區塊一：修訂六（附到規格檔末）

````markdown
## 修訂六（tech-architect，2026-11-07；回應風控 [風控-197]）

- 依據：[風控-197] `work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md`，結論 CONDITIONAL APPROVE。
- 程式依據：主 checkout product/stock-desk，N-190 以 3985f4d fast-forward 之後的 tip。只讀、未執行。行號以這個 checkout 為準、以內容定位；修訂四引用的行號已位移，對照見第 4 節。
- 編號說明：同日 `work/reviews/2026-11-07-N177a停止點裁示-tech-architect.md` 自稱「修訂五」（N-177a 停止點：T18、QB-3、C4、4.2、T21、1.3(4)、T26(iv)）。本修訂與它沒有重疊段落。
- 本修訂只取代或新增下面點名的段落，其餘維持修訂四。
- [TA 補]、[待風控] 的意義同前。

### 0. 風控審查結果的登錄（不改判斷）
- 修訂四索引第 1～10 項符合。5′ 接受，附五項 required，見第 1 節。
- N-197a spec 核可，附四項 required，見第 2 節。
- 三項 suggested 全部採用，見第 3 節。
- R-5′、R-6′ 已由風控定稿，交 tech-writer 逐字落檔，本修訂不轉錄。
- N-197 (b)：
  - F2 拆成 N-198（N-169F2），ADR 草案為 ADR-0042，另行送審；
  - 偵測工具的補充檢查為 N-199，spec 另交。
- CEO 通知前提 (1)：TA 確認成立，見第 5 節。

### 1. C8 的執行與判斷分離
- 取代修訂四 1.2「[TA 補，待風控確認執行方式] 執行與判斷分離」整段。
- N196-C8 的實質要求、`<base>` 定義、PR 說明須列出的項目都不變。
- 本節同時適用 N197a-C8（見 1.8）。

**1.1 名詞**
- `<head>`：qa 審查對象 PR 的 head commit，完整 40 碼。
- `<tip>`：執行者 fetch 之後 `origin/product/stock-desk` 所指的 commit，完整 40 碼。
- `<base>`：`git merge-base <tip> <head>` 的輸出。
- `<M_1>`、`<M_2>`：前置單在 product 上的 merge commit，完整 40 碼。
  - N196-C8：N-177a、N-195。
  - N197a-C8：N-195、N-196。

**1.2 (i) 作者端紀錄（dev-lead，附在 PR 說明）**
- 在 PR 分支的 checkout 上逐條執行，貼出指令原文與完整輸出。每條指令之後都接 `; echo "exit=$?"`：
```bash
git fetch origin; echo "exit=$?"
git rev-parse origin/product/stock-desk; echo "exit=$?"
git rev-parse HEAD; echo "exit=$?"
git merge-base origin/product/stock-desk HEAD; echo "exit=$?"
git merge-base --is-ancestor <M_1> <base>; echo "exit=$?"
git merge-base --is-ancestor <M_2> <base>; echo "exit=$?"
```
- `--is-ancestor` 成功時沒有 stdout，所以 `exit=` 那一行是唯一的證據，一定要有。
- 只寫「通過」或只貼結論，不算數。

**1.3 (ii) 獨立紀錄（coordinator 或 devops-sre，記在 `work/reviews/` 的本案審查紀錄）**
- 在自己的 checkout 上 fetch 之後，自己求出 `<tip>`、`<head>`、`<base>`，不得抄 PR 說明裡的值：
```bash
git fetch origin; echo "exit=$?"
git rev-parse origin/product/stock-desk; echo "exit=$?"
git rev-parse origin/<PR 分支名>; echo "exit=$?"
git merge-base origin/product/stock-desk origin/<PR 分支名>; echo "exit=$?"
git merge-base --is-ancestor <M_1> <base>; echo "exit=$?"
git merge-base --is-ancestor <M_2> <base>; echo "exit=$?"
```
- 紀錄要列出 `<tip>`、`<head>`、`<base>`、`<M_1>`、`<M_2>`，都是完整 40 碼。
- 紀錄要寫明執行者，並聲明執行者：
  - 不是 (i) 的執行者；
  - 不是 `<base>..<head>` 範圍內任何 commit 的作者，也不是其中任何 `Co-Authored-By`。

**1.4 獨立性（風控 required 第 3 項）**
- (ii) 的執行者不得是 (i) 的執行者，也不得是該 PR 的作者或共同作者。
- qa 以 PR 頁面的 commit 清單核對。這一步是讀頁面，不需要 Bash。
- 不符就判 BLOCKING。

**1.5 qa 的判斷（全部都要成立；任一項不成立就判 BLOCKING）**
1. (i)、(ii) 都存在，每條指令都附原文與 `exit=` 行。
2. 兩份紀錄的 `<head>` 相同，`<base>` 也相同。
   - [TA 補] `<tip>` 可以不同。理由：product 只會往前長（禁止 force push），新增的 commit 不在 `<head>` 裡時，`<base>` 不會變。
   - `<base>` 不同，就表示其中一份已經過時，要重做。
3. 兩份紀錄中，兩條 `--is-ancestor` 都是 `exit=0`。
4. 綁定審查對象：qa 執行 `git diff --stat <紀錄中的 head> <qa 實際審查的 commit>`，輸出必須為空。
5. 1.6 的旁證成立。

**1.6 `git diff` 旁證（qa 執行；採用風控 suggested 的精確判準）**
- N196-C8 要跑的兩份 diff：
  - `git diff <M_N-177a> <base> -- apps/stock-desk/backend/app/playbook/store.py`
  - `git diff <M_N-195> <base> -- apps/stock-desk/backend/app/playbook/`
- N197a-C8 要跑的兩份 diff：
  - `git diff <M_N-195> <base> -- apps/stock-desk/backend/app/playbook/`
  - `git diff <M_N-196> <base> -- apps/stock-desk/backend/app/playbook/store.py`
- 判準：下表任一個錨點出現在某一條 `-` 行，而同一份 diff 沒有任何一條 `+` 行含同一個錨點，旁證就不成立。

| 錨點 | 適用 | 比對 diff 行的 regex |
|---|---|---|
| `_settle_batch_line` 的定義 | N196 | `^[-+]\s*def _settle_batch_line\(` |
| `_settle_s2_fill` 的定義 | N196 | `^[-+]\s*def _settle_s2_fill\(` |
| 稽核表 DDL | N196 | `^[-+].*CREATE TABLE IF NOT EXISTS (playbook_fill_moves\|\{FILL_MOVES_TABLE\})` |
| 稽核表名常數 | N196 | `^[-+]FILL_MOVES_TABLE = ` |
| `set_total_deploy` 的定義 | 兩者 | `^[-+]\s*def set_total_deploy\(` |
| `read_rebalance_inputs` 的定義 | N197a | `^[-+]\s*def read_rebalance_inputs\(` |

- [TA 補] DDL 是以 f-string 由常數組成（4.6），CREATE TABLE 那一行可能不含字面表名。所以錨點同時收兩種寫法，並把常數定義行也列為錨點。
- [TA 補] `+` 行的配對只看錨點，不看參數，這是刻意的。後續單合法改簽名時（例如 N-198 讓 `_settle_batch_line` 改為接收 conn），不會被誤判。
- 旁證只是內容層面的獨立檢查，不能取代 (i)、(ii) 的 ancestry 判定。qa 仍然要讀完整份 diff。

**1.7 PR head 變動就重做（風控 required 第 5 項）**
- PR head 只要有任何新 push（包括 C9 的 merge product），以下全部重做，舊紀錄作廢：
  - (i)、(ii)；
  - 1.5 第 4 點；
  - 1.6 的旁證。
- 新紀錄齊備之前，qa 不得給 PASS。

**1.8 不變的部分，以及 N197a-C8**
- QB-N196-2 不變。不擴充 `READONLY_ALLOWED_BASH`，也不提出這方面的 ADR。
- 風控揭露的殘留照登錄：qa 無法親自重現 ancestry；ADR-0007 所說的現況不變。
- **N197a-C8（取代修訂四 3.9 的 C8）**：base 與先後順序，依本節同一種方法驗證；`<M_1>`、`<M_2>` 改為 N-195、N-196 的 merge commit。
- **QB-N197a-2（新增，BLOCKING）**：內容同 QB-N196-2，對象是 N197a-C8。

### 2. N-197a 的 required（[風控-197] 第二節第 3(b) 點）

**2.1 拒絕分支改寫**
- 取代修訂四 3.9 中 service.py `rebalance` 的拒絕分支，拿掉 `or "0"`：
```python
        if not write.written:
            total_deploy, set_at = _superseded_fields(write.found)
            message = wording.REBALANCE_SUPERSEDED.format(
                total_deploy=f"{total_deploy:.2f}",
                set_at=wording.taipei_wall_time(set_at),
            )
            return RebalanceResult(
                executed_at=as_of, status="superseded", total_assets=None,
                previous_total_deploy=total_deploy,
                new_total_deploy=None, deployed_value=None, overshoot=None,
                directives=[], message=message, warnings=[message],
            )
```

**2.2 鍵不存在的分支：視為不變式違反（風控 3(b)2，TA 選第一種）**
- 新增 store.py 的例外型別：
```python
class TotalDeployStampInvariantError(RuntimeError):
    """A refused TOTAL_DEPLOY write found the stamp incomplete or malformed (N197a-C11)."""
```
- 新增 service.py 的模組私有 helper：
```python
def _superseded_fields(found: TotalDeployStamp) -> tuple[Decimal, datetime]:
    """Parse what a refused write found under the lock (N197a-C11).

    Every writer stores the three keys in one transaction (C6), so a refusal that
    finds one absent or malformed means that invariant is broken: raise, never
    substitute 0 and never guess a time zone. Values are not echoed (private).
    """
    if found.total_deploy is None or found.set_at is None or found.source is None:
        raise TotalDeployStampInvariantError("TOTAL_DEPLOY stamp incomplete under the lock")
    try:
        total_deploy = Decimal(found.total_deploy)
        set_at = datetime.fromisoformat(found.set_at)
    except (InvalidOperation, ValueError):
        raise TotalDeployStampInvariantError("TOTAL_DEPLOY stamp malformed under the lock") from None
    if not total_deploy.is_finite() or set_at.tzinfo is None:
        raise TotalDeployStampInvariantError("TOTAL_DEPLOY stamp malformed under the lock")
    return total_deploy, set_at
```
- 為什麼選第一種：
  - 現有寫入者不會刪除這三個鍵。`set_capital` 與 N-195 的 `_total_deploy_state` 都是同時寫三個鍵，而 `_write_state` 只有收到 None 才會刪鍵（store.py:690-700）。所以拒絕路徑上出現缺鍵，只可能是不變式被破壞。
  - 第二種（改用不含金額的字面）要多一句字面，並送風控逐字定稿，會把 C10 的阻擋再往後推；而且那句字面會掩蓋不變式已被破壞這件事。
- 發生時的狀態：
  - store 的交易已經 commit，而且沒有寫入任何東西（`written` 為 False）；
  - 不呼叫 `record_directives`；
  - 例外原樣往外拋，由 `CorsVisibleServerErrorMiddleware` 回 500，並記錄 traceback。這就是依 C-11 失敗、不靜默。
- `from None`：避免 traceback 帶出鍵值。

**2.3 set_at 的時區格式（風控 3(b)3）**
- 新增 wording.py 的函式。字面只放在 wording.py，「台北時間」沿用 `app/advice/limits.py` 的 `DISCLOSURE_TZ_LABEL` 與 `app/api/event_study.py:144` 的既有標示：
```python
_TAIPEI = ZoneInfo("Asia/Taipei")


def taipei_wall_time(moment: datetime) -> str:
    """``moment`` as Asia/Taipei wall time to the second, labelled (N197a-C12)."""
    if moment.tzinfo is None:
        raise ValueError("taipei_wall_time needs an aware datetime")
    return moment.astimezone(_TAIPEI).strftime("%Y-%m-%d %H:%M:%S") + " 台北時間"
```
- 格式是 `YYYY-MM-DD HH:MM:SS 台北時間`：
  - 精確到秒，微秒直接截去，不四捨五入；
  - 台灣沒有日光節約時間，所以不另外標 UTC+8；
  - 用到秒而不是像 event_study 只到分，是因為交錯窗口很短，只到分鐘時，可能和 REBALANCE 本身的執行時刻顯示成同一個值。
- 給 creative-lead 的佔位規則：
  - 佔位只有 `{total_deploy}`（.2f）與 `{set_at}` 兩個；
  - `{set_at}` 的代入值本身已經含「台北時間」，字面不得再加任何時區字樣；
  - 不得新增需要計算的數字。

**2.4 docstring（風控 3(b)4）**
- `RebalanceResult` 的 class docstring 末尾，逐字追加以下段落（程式內的說明用英文）：
```
``previous_total_deploy`` depends on ``status`` (N197a-C13). On ``"ok"`` and
``"insufficient_data"`` it is the TOTAL_DEPLOY this run read in its snapshot,
before it computed anything. On ``"superseded"`` it is the TOTAL_DEPLOY found
under the write lock when this run's write was refused -- the value stored now,
written by another operation after the snapshot -- and not the value that was in
force before this run.
```
- 已知限制：
  - `app/api/playbook.py:185-198` 的 `RebalanceResponse` 依 C1 零 diff，所以 OpenAPI 的欄位上沒有這段說明；
  - 前端沒有使用這個回應（3.6）。
  - 若風控要求在 API 上也加欄位說明，C1 要擴大到 `app/api/playbook.py` 的一個 `Field(description=...)`，請回 TA。

**2.5 約束（追加 C11～C13；C1 取代）**
- **C1（取代）**：diff 範圍。
  - store.py：修訂四列出的項目，加上 `TotalDeployStampInvariantError`。
  - service.py：
    - `rebalance` 中 `set_total_deploy` 那一個呼叫與拒絕分支；
    - 模組私有的 `_superseded_fields`；
    - 必要的 import（`InvalidOperation`、`datetime`、`TotalDeployStamp`、`TotalDeployStampInvariantError`）。
  - models.py：Literal 的加法，加上 2.4 的 docstring 段落。
  - wording.py：`REBALANCE_SUPERSEDED`、`_TAIPEI`、`taipei_wall_time`，以及 `zoneinfo` 的 import。
  - `tests/**`。
  - 以下零 diff：engine.py、`app/api/**`、`app/data/**`、`app/services/**`、frontend。
- **C11**：拒絕分支只能經由 `_superseded_fields` 取值。
  - 三個鍵任一個為 None、金額無法解析或不是有限值、set_at 無法解析或沒有時區，一律 raise `TotalDeployStampInvariantError`。
  - 不得以 0、空字串或任何預設值代入；不得猜測時區。
- **C12**：set_at 只經由 `taipei_wall_time` 呈現；字面內不得出現 ISO 原始字串。
- **C13**：`RebalanceResult` 的 docstring 含 2.4 的段落，逐字一致（空白正規化之後）。

**2.6 測試（追加 T10～T13，全部 BLOCKING）**
- **T10（AST；C6 不變式）**：掃描範圍是 `app/**/*.py`。函式以 `模組:類別.函式` 的限定名記錄；模組層級的程式碼以 `模組:<module>` 記錄。
  - (a) **引用集合**：
    - 列出所有出現 `ast.Name(id="STATE_CASH")` 或 `ast.Attribute(attr="STATE_CASH")` 的函式，以具名常數 `STATE_CASH_REFERENCES` 釘住；
    - PR 要附上對 N-197a base 的實測值；
    - 新增任何一個成員，測試就失敗，回 TA 與風控判定它是不是寫入者。
  - (b) **寫入者集合 W**：滿足下列任一條件的函式。
    - 某個 `ast.Dict` 的鍵是 STATE_CASH（Name 或 Attribute）；
    - 某個 Store 語境的 `ast.Subscript`，slice 是 STATE_CASH；
    - 呼叫 `_write_state(` 或 `_set_state(` 時，values 引數是 Dict 字面，而且鍵含 `ast.Constant("cash")`。
    - 斷言 W 等於具名常數 `STATE_CASH_WRITERS`。baseline 是三部分的聯集，以 PR 實測為準：
      - `{store:PlaybookStore.set_capital}`；
      - 結算私有 helper：N-177a 之後實測，依修訂一 1.3(3) 預期是 `store:_add_cash`；
      - 若 N-197a base 仍定義 `set_cash`，加上 `{store:PlaybookStore.set_cash}`，並另外斷言 `app/` 內沒有 `set_cash(` 呼叫點（與 N177a-T19 同一個條件）。
    - 結算 helper 的呼叫者只能是 `_settle_s2_fill`、`_settle_batch_line`。這一點引用 N177a-T19 的同一個斷言，不另寫一份。
  - (c) **C6 的內容**：W 中結算 helper 與死碼 `set_cash` 以外的成員（現況只有 `set_capital`）：
    - 含 STATE_CASH 鍵的那個 Dict 字面，必須同時含 STATE_TOTAL_DEPLOY、STATE_TOTAL_DEPLOY_SET_AT、STATE_TOTAL_DEPLOY_SOURCE 三個鍵；
    - 而且這個 Dict 是同一個 `_set_state(`／`_write_state(` 呼叫的引數，也就是同一個交易。
  - (d) **原始 SQL**：`app/` 內任何字串常數（包括 f-string 的常數片段），若同時符合 `(?i)\b(insert|replace|update|delete)\b` 與 `\bplaybook_state\b`，只能出現在 `store:_write_state`。
  - (e) **無法靜態判讀的寫入呼叫**：
    - `_write_state(`／`_set_state(` 的 values 引數不是 Dict 字面的呼叫，以 (函式, 計數) 的具名常數釘住，只准調低，比照 N177b-T22 (c′-3)；
    - 現況預期有 `store:PlaybookStore._set_state`；
    - N-195 的 `set_total_deploy` 若以 `_total_deploy_state(...)` 傳入，也列入，並另外斷言 `_total_deploy_state` 不屬於 W。
  - **失敗時的處理**：
    - W 新增成員，或任何集合調高：回 TA 與風控（C6）；
    - W 少了成員：在同一個 commit 更新常數，並在 PR 說明列出，不必回 TA。
- **T11（C11）**：同一個注入點，在窗口內以測試專用的 `_set_state` 製造以下三種情況：
  - (i) 刪除 STATE_TOTAL_DEPLOY；
  - (ii) 把 set_at 寫成 `"not-a-date"`；
  - (iii) 把 set_at 寫成沒有時區的 `"2026-11-07T01:02:03"`。
  - 每一種都斷言：raise `TotalDeployStampInvariantError`；例外訊息不含任何鍵值；DB 中四個鍵與窗口寫入之後的值逐字相同；沒有 REBALANCE 指令列。
- **T12（C12）**：
  - `taipei_wall_time(datetime.fromisoformat("2026-11-07T03:04:05.678901+00:00")) == "2026-11-07 11:04:05 台北時間"`；
  - 跨日：`"2026-11-07T16:30:00+00:00"` 對應 `"2026-11-08 00:30:00 台北時間"`；
  - 傳入沒有時區的 datetime → `ValueError`；
  - T2 的 `message` 中不含 `found.set_at` 的原始字串。
- **T13（C13）**：`inspect.getdoc(RebalanceResult)` 經空白正規化之後，含有 2.4 的段落。

### 3. suggested 的評估（全部採用）

**3.1 旁證判準的精確化（修訂四第 5 項）**：已併入 1.6。

**3.2 (c′-1) 的名稱集合擴大到任何作用域（修訂四第 10 項）**
- 取代修訂四 2.2 (c′-1) 的第一句。新的定義：
- EMERGENCY 名稱集合 = 掃描範圍內，任何作用域（模組、類別、函式、lambda、comprehension）中，以下列任一形式綁定，而且綁定值的 AST 子樹含 `ast.Constant("EMERGENCY")` 的名稱：
  - Assign、AnnAssign、AugAssign、NamedExpr 的 Name 目標，包括 Tuple／List 解包中的每一個 Name；
  - For 與 comprehension 的目標，條件是 iter 含該常數；
  - 函式參數，條件是預設值含該常數；
  - `with ... as` 的目標；
  - Attribute 目標的 attr，例如 `self.x = "EMERGENCY"` 的 `x`。
- 集合由測試計算，不寫死。
- 現況：至少有 `EMERGENCY_RULE_ID`（store.py:313）。`UNKEYED_RULE_IDS`（store.py:267，tuple 內含該常數）也會被收進集合。
- 這是刻意的過度涵蓋：
  - 集合只用來判定 `rule_id=` 的值；
  - 多收進來的名稱若從未出現在 `rule_id=`，不影響計數；
  - 若出現了，計數變大、測試失敗，回 TA 判讀。方向是寧可誤報。
- (c′-1) 的 Constant／Name／Attribute 判定，以及「總數恰好一處」的要求，都不變。

**3.3 3.9 第 6 點的指涉改為更正版（修訂四第 4 項）**
- 修訂四 1.1 的 3.9 第 6 點末句，改為：「修好之前，以風控 2026-11-07 更正版 CEO 通知（取代同日稍早送出的補充句；[風控-197] 第二節第 6 點）揭露。」
- 修訂四 3.9 N-197a「定位」的第 4 個子彈，改為：「在 N-197a 上線之前，第 2 列是殘留，以風控 2026-11-07 更正版 CEO 通知揭露，並登錄 ADR-0041 R-5′（風控定稿，[風控-197] 第二節第 5 點）。」

### 4. 行號對照（修訂四引用 → 現在的 checkout；以內容定位）

| 內容 | 修訂四 | 現在 |
|---|---|---|
| service `rebalance` 起點／`list_batches`／`portfolio_state`／`set_capital` | :1516／:1535／:1538／:1612 | :1809／:1828／:1831／:1908 |
| service `confirm_rules` 起點／其中的 `set_capital` | :1722-1739／:1734 | :1987 起／:2030 |
| service `_settle_pending` 中的 claim 與 G1 分支 | :1339-1356 | :1632-1649 |
| service `evaluate_today` 的 `read_in_flight`／`list_batches`／`roll_peak_closes`／`list_batches`／`portfolio_state` | :1861／:1862／:1898／:1901／:1902 | :2157／:2158／:2196／:2199／:2200 |
| store `claim_directive` | :1453-1460 | :1531-1555 |
| store `set_capital` | :945-967 | :1033-1055 |
| store `EMERGENCY_RULE_ID` | :291 | :313 |
| wording `SETTLEMENT_EXIT_ITEM`／`SETTLEMENT_BATCH_ALREADY_FILLED_NOTE` | :956／:963-969 | :1019／:1026 起 |
| models `RebalanceResult` | — | :511-534 |
| engine `planned_batch_shares` | :176-205 | :186 起 |
| api `today` | :582 | :581-582（未動） |

### 5. CEO 通知前提 (1)：TA 確認成立
- 同步 `/today` 在 threadpool 中執行，不會因為 client 斷線而中斷：
  - FastAPI 走 `run_in_threadpool`，進到 anyio 的 `run_sync`，`abandon_on_cancel=False`；
  - uvicorn 在斷線時只標記 disconnected，不取消 app task；
  - 本 repo 三層 middleware 都是純 ASGI，沒有監聽斷線。
- 前端的 `getPlaybookToday` 不接 `signal`，`cancelQueries` 不會中止 fetch。
- 重新整理之後，新頁面立刻送出新的 `/today`，與舊的那次在後端並行。
- 兩句都保留。完整依據見 TA 回報與 ADR-0042 Context 第 4 點。

### 6. 修改處索引（風控比對用）

| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 1 | C8 執行與判斷分離（1.1～1.7） | 取代修訂四 1.2 對應段：明列指令與 `exit=`；(ii) 獨立計算並列出 40 碼；執行者獨立；以 `git diff --stat` 綁定審查對象；head 變動就重做 | [風控-197] 二-2 required 1～5 |
| 2 | 1.5 第 2 點 `<tip>` 可以不同 | [TA 補] | product 只往前長 |
| 3 | 1.6 旁證錨點 | 採用 suggested，[TA 補] 收 f-string DDL 與常數定義行 | 二-1 第 5 項 suggested |
| 4 | N197a-C8、QB-N197a-2（1.8） | 取代或新增 | 二-2「N197a-C8 一併適用」 |
| 5 | 拒絕分支（2.1）、C11、T11 | 取代：鍵不存在視為不變式違反，不以 0 代入 | 二-3(b)2，TA 選第一種 |
| 6 | `taipei_wall_time`、C12、T12 | 新增：台北時間，精確到秒，附標示 | 二-3(b)3 |
| 7 | docstring 段落、C13、T13 | 新增 | 二-3(b)4 |
| 8 | T10（AST） | 新增：引用、寫入者、C6 內容、原始 SQL、不可判讀呼叫 | 二-3(b)1 |
| 9 | C1 | 取代：納入 2.1～2.4 的程式位置 | 隨 5～7 |
| 10 | (c′-1) 任何作用域，過度涵蓋 | 採用 | 二-1 第 10 項 suggested |
| 11 | 3.9 第 6 點、N-197a 定位：指涉改為更正版 | 採用 | 二-1 第 4 項 suggested |
| 12 | 行號對照（第 4 節） | 登錄 | checkout 已位移 |
| 13 | CEO 通知前提 (1)（第 5 節） | 確認成立 | 二-4(e) 前提 (1) |

（修訂六由 coordinator 2026-11-07 附加；原文見 tech-architect 回報。）
````

#### 區塊二：ADR-0042 草案（交 tech-writer 落檔為 `docs/adr/0042-stock-desk-排程台結算的claim與動帳併入同一寫鎖交易.md`）

````markdown
# ADR-0042：stock-desk 排程台結算的 claim 與動帳併入同一個寫鎖交易（N-198／N-169F2；補充 ADR-0035、ADR-0041，不取代）

- 狀態：proposed
- 日期：2026-11-07
- 決策者：
  - tech-architect：草案；
  - risk-compliance-officer：審查，最遲在 N-196 合入 product 時送達（[風控-197] 第二節第 4 點第 2 項）；
  - CEO：核可，待定。
- 來源簡稱（都在 `work/reviews/` 下）：
  - [TA-177S]：`2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`（修訂一 1.3 的 R-α、修訂四第 4 節、修訂六）；
  - [風控-197]：`2026-11-07-N177修訂四比對與N197裁示-風控.md`；
  - [TA-E2]：`2026-11-04-N182解讀點2與3裁示-tech-architect.md`（E-2）；
  - [風控-1104]：`2026-11-04-ADR0039v2回審與N182字面-風控.md`（第 11 點）。
- 適用範圍：只有 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。
- 程式位置：主 checkout，N-190 以 3985f4d 合入之後的 tip。只讀、未執行，以內容定位。
- 前提：N-177a、N-177b 尚未合入，本 ADR 以兩者已核可的規格為前提（見「先後與相依」）。

## Context（背景）

1. **現況：claim 與動帳分屬不同交易（F2）。**
   - `claim_directive`（store.py:1531-1555）是一句條件 UPDATE，以自己的連線獨立 commit。G1 的條件也在這一句裡（`BATCH_LEFT_PLANNED_SQL`，store.py:279-283）。
   - `_settle_pending`（service.py:1553 起）對每一列依序執行：
     - claim（:1632）；
     - claim 失敗時，另開連線讀 G1 的拒絕原因（:1635）；
     - N2 的鎖外預讀（:1653）；
     - `settle`（:1656）。
   - `settle` 內：
     - N-177a 的 R-α 之後，每一筆動帳各有自己的 `BEGIN IMMEDIATE`（ADR-0041 Decision 5）；
     - missed 計數是單句 UPDATE；
     - `_mark_schedule` 另開連線（store.py:1663-1678）。
   - claim 與動帳之間沒有任何補償機制。
2. **後果（ADR-0041 R-6′，風控定稿）：**
   - (a) **並發**：某一列已 claim、動帳還沒 commit 時，另一個 `/today` 在 service.py:2199 讀到該批仍是 planned，排程日可能對同一批再出一張 R1 買進指令。
   - (b) **失敗**：claim 之後動帳失敗（例如 `database is locked`、行程終止），該批會停在 planned。之後的排程日，不需要並發也會再出 R1；G1 不會擋，畫面也沒有揭露。
3. **追蹤清單 :382：buy 的 UPDATE 沒有 planned 守衛。**
   - 同一批有兩筆待結算的 buy、而兩個結算並發時，兩邊的 claim 都可能在任一邊動帳之前通過 G1（因為批次仍是 planned）。
   - 結果是兩筆都動帳：現金重複扣款，批次欄位被後寫的一筆覆寫。
   - R-α 的 buy 分支以 `UPDATE ... WHERE symbol = ? AND batch_no = ?` 寫入，沒有檢查 status（[TA-177S] 修訂一 1.3(2) 第 3 點）。
4. **並發從哪裡來（讀碼查證，未實跑）：**
   - 後端的同步 `/today` 在 threadpool 中執行，client 斷線不會讓它停下來：
     - FastAPI 0.139.2 對非 coroutine 端點走 `run_in_threadpool`（`fastapi/routing.py:337-347`），也就是 `anyio.to_thread.run_sync`，`abandon_on_cancel=False`；
     - uvicorn 0.51.0 斷線時只標記 `disconnected`（`h11_impl.py:107-130`、`:464-465`）；
     - 本 app 的三層 middleware（main.py:59-69）都是純 ASGI，不監聽斷線。
   - 前端的 `getPlaybookToday()`（api.ts:437-439）不接 TanStack 的 `signal`。所以 `cancelQueries` 不會中止 fetch，HTTP 請求照樣送完（query-core `query.ts:444-457`）。
   - 會造成兩個 `/today` 在後端並行的前端路徑：
     - **兩個分頁或兩個視窗**：各自有一個 QueryClient，彼此不會去重。
     - **讀取中重新整理**：舊請求照樣跑完，新頁面立刻送出新的請求。
     - **出清的 `onSettled`**（queries.ts:522-525）：`cancelQueries` 之後接 `invalidateQueries`，在途的舊請求不會中止。
       - query 已有資料時，`invalidateQueries` 的 `cancelRefetch` 預設為 true（queryClient.ts:317-319），會靜默取消舊的、立刻發出新的（query.ts:411-413）。
       - 首次載入時，`cancelQueries` 先讓 retryer 進入 rejected，接著的 `fetch` 會重新發出請求（query.ts:404-419）。
       - 兩種情況，後端都會並行。
     - **資金確認的 `onSuccess`**（queries.ts:450-452）：機制相同。但這個按鈕只在尚未確認時出現；在途的舊請求若在確認 commit 之前讀到 authorship，就走 unauthored 路徑、不結算（service.py:2150-2152），所以與 F2 幾乎無關。
   - 不會造成並發的路徑：
     - **視窗 focus**：`refetch({ cancelRefetch: false })`（query.ts:333-336），在途時共用同一個 promise；
     - **`retry: 1`**：在前一次失敗回應之後才重送，後端那一次已經結束；
     - **同頁兩處使用 `usePlaybookToday`**（page.tsx:60、PendingExitBlock.tsx:43）：同一個 key、同一個 QueryClient，會去重。
   - `POST /api/playbook/settle` 也經由 `_settle_pending`，與 `/today` 之間同樣會並發。
5. **限制：**
   - 不新增 `DirectiveStatus`；
   - 不做批次層級 claim；
   - G1 的 SQL 零 diff；
   - 不寫 `missed` 以外的新狀態；
   - 帳冊只在 claim 成功之後才動；
   - C-B6 的 buy 行為零改動（ADR-0035 6′、ADR-0041 Decision 4）；
   - engine 零 diff（C-B11）；
   - 持鎖期間不得有網路 I/O；
   - 唯一的寫入同步機制是 SQLite 寫鎖（排除行程內鎖，理由同 ADR-0041 的 R-β）。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|
| P1：**逐列**單一 `BEGIN IMMEDIATE`：claim、G1 原因讀取、動帳、schedule 標記 | 兩種 R-6′ 變體與 :382 都根治；粒度與 R-α 相同；一列失敗只影響那一列；寫鎖只持有到 SQL 結束 | 動到 `_settle_pending` 與 store 的交易邊界；每一次 claim 嘗試多一個短交易 | 低 | **採用** |
| P2：整次結算一個 `BEGIN IMMEDIATE` | 整次結算原子；交易數最少 | 一列失敗，整批都回滾，所有結算停擺；N2 與 W-B3 在鎖外讀，看不到交易內的寫入；持鎖時間隨列數增長 | 中 | 否決 |
| P3：claim 之後動帳失敗就補償（把 settled 改回 0） | 交易邊界不動 | 違反「已 claim 的列不會被 unclaim」（`batch_blocking_claim` 的前提）；行程終止時補償不會執行，失敗變體仍在 | 高 | 否決 |
| P4：新增「claiming」中間狀態 | 失敗可以偵測 | 新增 `DirectiveStatus`，被禁止；要改前端與字面 | 高 | 否決 |
| P5：(b-ii) G0 守衛（`commit_evaluation` 不寫同批的 R1） | 不動結算 | 風控已否決作為過渡方案（[風控-197] 4 第 3 點）；失敗變體會變成該批永久停住 | 中 | 否決 |
| P6：service 層的 `threading.Lock` | 簡單 | 只在單一行程內有效；qa 無法以 SQL trace 檢查 | 中 | 否決 |

## Decision（決策）

1. **新的 store 方法 `claim_and_settle`**：唯一的結算進入點，一列一次呼叫。
```python
class ClaimSettle(NamedTuple):
    """What one claim-and-settle transaction did (ADR-0042)."""

    claimed: bool
    #: G1 refused the claim: the status of the batch that is no longer planned.
    refused_by: BatchStatus | None
    #: N-177b's outcome when claimed; None otherwise.
    settled: SettleOutcome | None


def claim_and_settle(
    self, directive_id: int, outcome: Directive, *, open_price: Decimal
) -> ClaimSettle: ...
```
   - 一個連線、一個 `BEGIN IMMEDIATE`，依序執行：
     - (a) claim 的 UPDATE。SQL 只有一份定義：把 `claim_directive` 現行的 SQL 文字，原樣移到模組常數 `_CLAIM_SQL`，並且仍然是由 `BATCH_LEFT_PLANNED_SQL` 拼接而成。`settled_at` 在鎖內取值。
     - (b) rowcount 為 0：在同一個連線執行 `batch_blocking_claim` 的那句 SELECT（模組常數 `_BLOCKING_CLAIM_SQL`，文字逐字不變），然後 `COMMIT`。這時沒有任何寫入。
     - (c) rowcount 為 1：在同一個連線執行 `settle` 的本體 `_settle_on(conn, outcome, fill_price=open_price, directive_id=directive_id)`：
       - S2 → `_settle_s2_fill(conn, …)`；
       - missed → `_count_missed(conn, …)`；
       - executed 逐批 → `_settle_batch_line(conn, …)`；
       - 最後 `_mark_schedule(conn, outcome)`。
       - 這些 helper 都改為接收 conn，自己不再 BEGIN 或 COMMIT，也不另開連線。
     - (d) `COMMIT`。
   - 例外處理：先 `if conn.in_transaction: ROLLBACK`，再原樣 raise（C-11）。
2. **buy 的 planned 守衛（消除 :382）**
   - 根本上的守衛是 G1：它在同一個寫鎖交易內判定，而 SQLite 同一時間只允許一個寫交易，所以第二筆 buy 的 claim 一定看到已經 open 的批次，被 G1 拒絕。
   - 另加防禦性斷言：`_settle_batch_line` 的 buy 路徑，在鎖內讀到的批次 `status` 必須是 `"planned"`，否則 raise `ClaimInvariantError(RuntimeError)`，整個交易回滾，連 claim 也回滾。
   - 這是 Python 端比對鎖內讀到的值，不是新的 SQL 比較，所以不違反「批次是否 planned 的 SQL 只在 `BATCH_LEFT_PLANNED_SQL`」（ADR-0039 補充 E-3、QB-10）。
3. **`_settle_pending`**
   - 每一列只呼叫一次 `claim_and_settle`，取代現行的 `claim_directive` → `batch_blocking_claim` → `settle` 序列。
   - 依回傳值分流：
     - claimed：進 `settled`；
     - refused_by 不為 None：G1，進 `unsettled`，`refused_by_g1=True`；
     - 兩者皆非：別的請求已處理，`continue`。
   - N2 依 N-177b 改由 `SettleOutcome` 判定（Q-g）。
   - W-B3 的事後讀取（`_batch_of`）不變。
   - **取開盤價的程式段（`series = loaded.get(...)` 到 `if opening is None: ... continue`）零 diff**，維持 ADR-0040 Decision 14 第 3 點的實質要求。
4. **保留的公開方法**
   - `claim_directive`、`batch_blocking_claim`、`settle` 保留，供測試與手動重放使用，改為委派到同一份 SQL 與 `_settle_on`。
   - `settle` 自己包一個 `BEGIN IMMEDIATE`。
   - `app/` 內這三者都不得有呼叫點（N198-C3）。
5. **語意**
   - 循序執行：帳冊各欄（`updated_at`、`settled_at` 除外）、現金、schedule、指令列的 `settled`／`status`／`settled_open_price`，都與 N-198 之前逐值相同。
   - 並發：每一列的 claim、動帳與 schedule 一起 commit。任何讀者都看不到「已 claim 但未動帳」的狀態。兩個結算請求的結果，等於依取得寫鎖順序的某一個循序執行。
   - 失敗：一列在任何一步失敗，那一列的 claim、動帳、schedule 都不會留下；該列維持 `settled=0`／`pending`，下一次結算時重新判定 G1 與開盤價。
6. **約束（qa 逐條檢查，全部 BLOCKING）**
   - **N198-C1**：diff 範圍。
     - store.py 只限：`_CLAIM_SQL`、`_BLOCKING_CLAIM_SQL`、`ClaimSettle`、`ClaimInvariantError`、`claim_and_settle`、`_settle_on`；`_settle_s2_fill`、`_settle_batch_line`、`_count_missed`、`_mark_schedule` 改為接收 conn；`claim_directive`、`batch_blocking_claim`、`settle` 改為委派。
     - service.py 只限 `_settle_pending` 的逐列迴圈。
     - `tests/**`。
     - engine.py、models.py、wording.py、`app/api/**`、`app/data/**`、frontend 零 diff。
   - **N198-C2**：`BATCH_LEFT_PLANNED_SQL`、`_insert_directives` 零 diff；`_CLAIM_SQL`、`_BLOCKING_CLAIM_SQL` 與 N-198 之前的 SQL 文字逐字相同（以測試釘住）。
   - **N198-C3**：`app/` 內 `claim_and_settle(` 恰好一處，就在 `_settle_pending`；`claim_directive(`、`batch_blocking_claim(`、store 的 `.settle(` 呼叫點都是 0（AST 判定）。
   - **N198-C4**：交易內的語句序列，依 Decision 1：
     - 從 `BEGIN IMMEDIATE` 開始；
     - 接 claim UPDATE；
     - 接「G1 原因 SELECT」或「動帳語句加上 schedule UPDATE」；
     - 以 `COMMIT` 結束。
     - 持鎖期間不另開連線，沒有網路，也不呼叫會另開連線的 `self.*`。
   - **N198-C5**：股數與 cash 的寫入者仍然只有 `_settle_s2_fill`、`_settle_batch_line`（經由 `_add_cash`），名稱不變（N177a-T19 照舊通過）；不新增寫入路徑。
   - **N198-C6**：Decision 2 的斷言存在，失敗時整個交易回滾。
   - **N198-C7**：以 merge commit 合入。base 必須含 N-177a 與 N-177b，以修訂六第 1 節的方法驗證（`<M_1>`、`<M_2>` 為 N-177a、N-177b）。合入前 merge 最新 product，之後重跑完整 CI 與 seam golden。
   - **N198-C8**：既有測試的修改只限以下三類，並逐條列在 PR 說明交 qa 判定：
     - (i) N177a-T9、T29「該列維持 `settled=1`／executed（F2 殘留）」的斷言，改為「該列維持 `settled=0`／`pending`，claim 已回滾」；
     - (ii) N177a-T28 與 `test_playbook_same_day_race.py::_writes_inside`、同檔 T14 中以「第一個或唯一一個 `BEGIN IMMEDIATE`」取交易的斷言：`/today` 的 `BEGIN IMMEDIATE` 數，改為 1 加上本次「有開盤價的到期列」數，包括 taken、G1、missed；
     - (iii) 直接呼叫 `claim_directive` 再呼叫 `settle` 的既有測試照舊通過，不得改寫。
7. **測試（全部 BLOCKING；用真實 `PlaybookStore`、檔案型 DB）**
   - **N198-T1（R-6′ 並發變體）**：
     - 設定：B 的 `claim_and_settle` 在 claim UPDATE 之後、動帳之前執行 hook；hook 另開執行緒跑 A 的 `evaluate_today`，最多等 0.5 秒後放行 B，最後 join A。
     - 斷言：A 沒有對 (s, k) 寫入 R1；排程日只對 k+1 出單；任何時刻都讀不到「r 是 `settled=1`，而 k 是 planned」。
     - 效力證明：PR 說明附本機輸出，顯示換回 N-198 之前的序列時本測試失敗。這份對照不 commit。
   - **N198-T2（失敗變體）**：分別對 `_add_cash`、batch UPDATE、`_mark_schedule` 注入例外。
     - 斷言：該列 `settled=0`／`pending`；批次、現金、schedule 都不變；例外原樣拋出；沒有留下未結束的交易。
     - 下一次結算正常完成，而且只動帳一次。
   - **N198-T3（:382）**：同一批有兩筆待結算 buy。A 在 claim 之後執行 hook，另開執行緒跑 B 的 `claim_and_settle`。
     - 斷言：現金只扣一次；批次的值來自 A 那一筆；B 被 G1 拒絕。
     - 效力證明同 T1。
   - **N198-T4**：SQL trace，依 C4；並以 connection factory 計數，確認交易期間沒有開第二個連線。
   - **N198-T5（循序等價）**：固定 seed，至少 300 組，以測試檔內的 N-198 之前參考實作比對，依 Decision 5 的循序條款。
   - **N198-T6**：AST，依 C3。
   - **N198-T7**：Decision 2 的斷言：對已經 open 的批次直接呼叫 buy 路徑，會 raise，而且 claim 也回滾。
   - **N198-T8**：C2 的 SQL 文字逐字比對。
   - **N198-T9**：N-199 偵測工具對 T1～T3 產生的 DB 執行，N199-A、N199-B、N199-C 都是 0 筆。

## Consequences（後果）

- 好處：
  - R-6′ 的兩種變體都消除：
    - 並發時，讀者只看得到 claim 之前或動帳之後的狀態；
    - 失敗時，claim 不會留下。
  - :382 的重複扣款消除（Decision 2）。
  - ADR-0041 Consequences「claim 之後若當機，會留下『executed 但沒有稽核』的列」不再發生；只剩 N-198 之前寫入的列。
  - missed 計數與 schedule 標記，和 claim 一起成為原子操作。
- 壞處與代價：
  - **E-2（追蹤清單 :314）不消除。**
    - E-2 的窗口在本請求的 `read_in_flight`（service.py:2157）與 `commit_evaluation`（:2222）之間：另一個請求的整筆結算在這段時間內 commit。N-198 只改另一個請求內部的交易邊界，不改本請求的讀取時點。
    - N-198 消除的是同批重複 R1 的其中一個來源（R-6′），所以 E-2 的觸發頻率會下降。但跨日重發（ADR-0035 V4）仍會產生同批的第二筆 R1。
    - 殘留仍歸 N-169，修法方向維持風控同意的 (iv)：把 `read_in_flight` 移到 commit 之後（[風控-1104] 第 11 點 (d)）。本 ADR 不處理。
  - `/today` 的 `BEGIN IMMEDIATE` 數，變成 1 加上有開盤價的到期列數。寫鎖競爭的次數增加，但每一次都只持有到 SQL 結束。超過 busy_timeout（5 秒）時，依 C-11 以 `database is locked` 失敗，而且那一列不留任何痕跡。
  - schedule 標記失敗時，現在會連同 claim 與動帳一起回滾。以前是 claim 與動帳留下、schedule 沒標。這是行為變更，方向是保守的：那一列下次重試。
  - 一列 commit 之後，若 `_settle_pending` 的後段失敗（例如字面組裝），帳冊是一致的，但那一次的回應沒有送達；下一次 `/today` 不會再把這些列列為本次結算。這是既有行為，不是本 ADR 新引入的。
  - N-198 部署之前寫入的資料，仍可能帶著 R-6′ 的痕跡，由 N-199 的偵測工具事後檢查。
- 被約束：
  - `app/` 內結算的唯一進入點是 `claim_and_settle`。新增任何會 claim 或會動帳的呼叫點，要回 TA 與風控。
  - ADR-0041「被約束」中「只能放在 `settle` 的私有 helper 內，並在單一 `BEGIN IMMEDIATE` 內讀改寫」，讀為「`settle` 或 `claim_and_settle` 的私有 helper，在呼叫者持有的單一 `BEGIN IMMEDIATE` 內讀改寫」。
  - 日後改動結算的交易邊界，依 ADR-0041 Decision 4，另立 ADR 並送風控。

## 與其他 ADR 的關係
- **ADR-0035**：補充，不取代，原文不改。
  - Decision 6′ 的「G1 判斷與 claim 原子化」維持，G1 的 SQL 零 diff。
  - 6′ 的殘留風險與 Consequences「F2 並發窗口仍在」，由本 ADR 消除。
  - 「不做批次層級 claim」維持：仍是逐列 claim。
- **ADR-0041**：補充，不取代。
  - Decision 4 列出的不變式全部維持：「帳冊只在 claim 成功之後才動」加強為「與 claim 同一交易」。
  - Decision 5 的 R-α 是本 ADR 的前提：本 ADR 把它的交易邊界往外擴到 claim。
  - R-6′ 的「已修正」註記，照風控逐字：「R-6′ 由 N-169F2 修正：claim 與動帳在同一交易內 commit。」N-198 以 merge commit 合入 product 之後才落檔；CEO 內部通知（N-197 (b)）維持到 N-198 **部署**為止。
  - Consequences「claim 與 settle 仍分屬兩個 transaction（F2，歸 N-169）…判定為未動帳（多報方向）」那一點的補註，[待風控] 草稿：「由 ADR-0042（N-198）消除：claim 與動帳同一交易 commit，當機時兩者都不留下；本點只適用於 N-198 之前寫入的列。」
- **ADR-0040**：原文不改。
  - Decision 14 第 1 點：不涉及。
  - 第 2 點：不新增寫入路徑（C5）。
  - 第 3 點「`_settle_pending` 零 diff」：與 ADR-0041 對第 2 點的判定相同，適用對象是 ADR-0040／N-190 的 build；N-177b 也已經改動 `_settle_pending`（ADR-0041 Decision 10）。實質要求「不得改取開盤價的方式」維持，由 Decision 3 的零 diff 段守住，qa 逐 hunk 檢查。
  - 第 4 點：不涉及。
- **N177a-C2**：`claim_directive`、`batch_blocking_claim` 零 diff，是 N-177a PR 的範圍約束，不追溯到後續單。
  - N-198 改的是委派方式，SQL 文字逐字不變（C2）。
  - `BATCH_LEFT_PLANNED_SQL`、`_insert_directives` 仍然零 diff。
- **ADR-0034**：C-B6 的行為不變，由 T5 的差分測試與 N-168 既有測試守住。C-B11 維持（engine 零 diff）。
- **ADR-0039**：群組 B 的讀取時點不變；N-171 區塊不受影響。
- 本 ADR 不取代任何 ADR。

## 先後與相依
1. **N-177a（R-α）必須先合入**，沒有例外。本 ADR 改的是 R-α 各個 helper 的交易歸屬。N-198 的 PR 要在 N-177a 合入 product 之後才開。release 位置照 ADR-0040 Decision 13：N-177a 是 N-190 之後的下一個 release。
2. **N-177b 預設先合入。**
   - 兩者都改 `_settle_pending`，也都動 `settle` 的回傳（`SettleOutcome`）。
   - 若 N-177b 在第三包凍結前趕不上，N-198 可以先合入，但 N-177b 的 Q-g、N177b-C6／C9 要由 TA 出補充，改為從 `claim_and_settle` 的回傳取值，並回風控。
3. **N-195、N-196、N-197a**：沒有邏輯相依（REBALANCE 路徑）；都會動到 store.py，依 C7 merge 最新 product 即可。
4. **N-199**：不相依。偵測工具要在 R2 之前交付；N-198 部署之後，建議再跑一次，確認沒有新的命中。
5. **期限**（[風控-197] 第二節第 4 點第 2 項）：實作最遲與第三包同一個 release；趕不上時，在第三包凍結前回報風控並附理由；要延期，需要 CEO 書面同意。

## 待決
- [待風控] 本 ADR 全文，以及 ADR-0041 那一點補註的草稿。
- [待風控] Context 第 4 點補充的出清 `onSettled` 並發路徑，要不要寫進 N-197 (b) 的 CEO 通知（coordinator 無權增字）。
- CEO：核可。
````

#### 區塊三：N-199 spec（交 data-engineer 實作、qa-reviewer 審查）

````markdown
# N-199 spec：N-177／N-190 偵測回溯工具新增 N-197 (b) 的事後檢查（唯讀）

- 依據：[風控-197] 第二節第 4 點第 4 項；追蹤清單 :403。
- 對象檔案：`apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py`，以及 `tests/test_n177_n190_backtrack_probe.py`。
  - diff 只限這兩個檔；`app/` 零 diff。
- 注意：主 checkout 目前沒有這個檔。TA 讀的是 scratchpad `wt_probe` 的版本（qa 複核 166c58c 的對象）。data-engineer 開工前，請先確認 product 上的版本與它相同；若不同，回 TA。
- 期限：最遲與 R2 同一個 release；工具若不隨 release 發佈，就在 R2 部署之前交付。不擋 N-196、N-197a。

## 1. 沿用的既有約束（不得放寬；既有測試原樣綠燈）
- S1：`mode=ro` 的 URI，加上 `PRAGMA query_only=ON`，timeout 5 秒；檔案不存在時拒絕，不建立。
- S2：只有 SELECT／WITH；全部是模組層級的 `*_SQL` 常數；只用綁定參數。既有的 S2 測試會自動涵蓋新常數。
- S3、S4：只用標準函式庫；不 import `app`；沒有網路。
- S5：DB 的 SHA-256 前後比對，不一致就 exit 3。
- S6、RC-5：拒絕 production DB 路徑，以及 git 工作樹內的 `--out-dir`（exit 4）。
- S7：只寫 `report.md`、`report.json`，以 `"x"` 模式開檔。
- S8、RC-3：只寫事實，不寫建議；DB 的自由文字不進報告；欄位值經 `sanitize`。
- Exit codes 不變：0、2、3、4。**命中不改變 exit code**，命中時仍是 0。
- `SCRIPT_VERSION` 改為 `"2"`；`SCHEMA_VERSION` 維持 1。理由：JSON 只加鍵、舊鍵語意不變，`--previous-json` 只讀 `n177`，所以第一次執行的 v1 報告仍可用於閘門比對。

## 2. 新增的 SQL（模組常數，放在 `M1_ROWS_SQL` 之後）
```python
#: N199-A (N-197 (b) failure variant): an executed buy whose batch never left planned,
#: or was skipped afterwards. The book did not take the fill.
N199_FILL_NOT_BOOKED_SQL = """
SELECT d.id, d.symbol, d.batch_no, d.rule_id, d.shares, d.data_date, d.execution_date,
       d.created_at, d.settled_at, d.settled_open_price, b.status
FROM playbook_directives AS d
JOIN playbook_batches AS b ON b.symbol = d.symbol AND b.batch_no = d.batch_no
WHERE d.action = 'buy' AND d.status = 'executed' AND d.settled = 1
  AND d.batch_no IS NOT NULL AND b.status IN ('planned', 'skipped')
ORDER BY d.symbol, d.batch_no, d.id
"""

#: N199-B (N-197 (b) concurrent variant, and every other source of the same shape):
#: an executed buy plus an unsettled pending buy on one batch that has left planned
#: (the condition of the store's BATCH_LEFT_PLANNED_SQL, G1).
N199_SAME_BATCH_BLOCKED_SQL = """
SELECT e.id, e.symbol, e.batch_no, e.rule_id, e.execution_date, e.settled_at,
       p.id, p.rule_id, p.shares, p.data_date, p.execution_date, p.created_at, b.status
FROM playbook_directives AS e
JOIN playbook_batches AS b ON b.symbol = e.symbol AND b.batch_no = e.batch_no
JOIN playbook_directives AS p
  ON p.symbol = e.symbol AND p.batch_no = e.batch_no AND p.id <> e.id
WHERE e.action = 'buy' AND e.status = 'executed' AND e.settled = 1
  AND e.batch_no IS NOT NULL
  AND p.action = 'buy' AND p.status = 'pending' AND p.settled = 0
  AND b.status <> 'planned'
ORDER BY e.symbol, e.batch_no, e.id, p.id
"""

#: N199-C ([TA 補]): two or more executed buys on one batch -- the later stage of the
#: failure variant (a re-issued R1 filled) and the two-buy race (tracking :382).
N199_MULTI_EXECUTED_BUY_SQL = """
SELECT d.symbol, d.batch_no, COUNT(*), b.status
FROM playbook_directives AS d
LEFT JOIN playbook_batches AS b ON b.symbol = d.symbol AND b.batch_no = d.batch_no
WHERE d.action = 'buy' AND d.status = 'executed' AND d.settled = 1
  AND d.batch_no IS NOT NULL
GROUP BY d.symbol, d.batch_no
HAVING COUNT(*) >= 2
ORDER BY d.symbol, d.batch_no
"""

#: Detail for N199-A and N199-C: every buy line of one batch, oldest first.
N199_BATCH_BUYS_SQL = """
SELECT id, rule_id, status, settled, shares, data_date, execution_date, created_at,
       settled_at, settled_open_price
FROM playbook_directives
WHERE symbol = ? AND batch_no = ? AND action = 'buy'
ORDER BY id
"""
```
- 各條件的說明：
  - N199-A 把 `skipped` 也收進來，這是 [TA 補]：失敗變體發生之後，該批仍是 planned，之後可能被 R3 跳過；這時仍然是「成交沒有記入帳冊」。
  - 已判定成交的 buy、但批次列不存在的情況，屬於既有的 N177-D，不重複列在 N199-A。
  - N199-B 的 `b.status <> 'planned'` 和 store 的 `BATCH_LEFT_PLANNED_SQL` 同義：批次列存在而且已離開 planned。由 T6 的 parity 測試綁住。
- `load()`：
  - 在既有連線上執行這三條 SQL；
  - 對 N199-A、N199-C 命中的每一個 (symbol, batch_no)，各執行一次 `N199_BATCH_BUYS_SQL`；
  - `Snapshot` 加法新增 `n199_fill_not_booked`、`n199_same_batch_blocked`、`n199_multi_executed`、`n199_batch_buys` 四個欄位。
  - 若 `playbook_batches` 不存在：現行的 `load()` 已經會依 :540-542 以 exit 2 結束，不另外處理。

## 3. 輸出欄位
- 新增 `classify_n199(snap)`；`build_result` 加上 `"n199"` 鍵。
- JSON 的形狀（金額沿用既有的字串慣例；`settled` 是整數）：
```json
"n199": {
  "fill_not_booked": [
    {"id": 0, "symbol": "", "batch_no": 0, "rule_id": "", "shares": 0,
     "data_date": "", "execution_date": "", "created_at": "", "settled_at": "",
     "settled_open_price": "", "batch_status": "",
     "other_buys": [{"id": 0, "rule_id": "", "status": "", "settled": 0,
                     "data_date": "", "execution_date": ""}]}
  ],
  "same_batch_blocked": [
    {"symbol": "", "batch_no": 0, "batch_status": "",
     "executed": {"id": 0, "rule_id": "", "execution_date": "", "settled_at": ""},
     "pending": {"id": 0, "rule_id": "", "shares": 0, "data_date": "",
                 "execution_date": "", "created_at": ""},
     "seconds_pending_created_after_executed_settled": 0}
  ],
  "multi_executed_buys": [
    {"symbol": "", "batch_no": 0, "batch_status": null, "count": 0,
     "buys": [{"id": 0, "rule_id": "", "shares": 0, "execution_date": "",
               "created_at": "", "settled_at": "", "settled_open_price": ""}]}
  ]
}
```
- 秒數的算法：
  - `int((_instant(p.created_at) - _instant(e.settled_at)).total_seconds())`，向零截斷；
  - 任一個時間無法解析時為 `null`，markdown 顯示「無法判定」。
- `other_buys`：同一批 id 不等於該列的所有 buy，取自 `N199_BATCH_BUYS_SQL`。
- `ENUM_VALUES` 加法新增 `"batch_status": frozenset({"planned", "open", "closed", "skipped"})`。不在集合內的值，照既有規則顯示「（非預期值）」，並計入 `unexpected_enum_values`。
- markdown：
  - 摘要表追加三列：
    - 「N199-A 已判定成交、批次未記入的買進」
    - 「N199-B 同批已有成交買進，另有 G1 擋下類的待結算買進」
    - 「N199-C 同批兩筆以上已判定成交的買進」
  - 在 N190-D 之後新增三節，每節開頭只放一句條件說明（事實），例如「條件：買進列 settled=1、status=executed，所屬批次仍為 planned 或 skipped。」，接著是表格。
- stdout：在 `gate_affected_symbols=` 之後加三行 ASCII，只有計數：
  - `n199_a_rows=<n>`
  - `n199_b_rows=<n>`
  - `n199_c_rows=<n>`
- `LIMITATIONS` 新增三條：
  - L12：「N199-A、N199-C 無法判定當時現金是否已扣：現金沒有異動歷史；N-177a 之前的逐批買進先寫現金、再寫批次，N-177a 之後兩者在同一交易。」
  - L13：「N199-B 的條件與結算的 G1 擋下類相同，不區分並發、跨日重發（ADR-0035 V4）或 N-172a 之前的重複；DB 不記錄某一列是否曾被嘗試結算，未到預定執行日的列也列入。」
  - L14：「N199-B 的秒數是待結算列 created_at 減已成交列 settled_at（都是 UTC ISO），只是時間差，不表示原因。」
- 三節的文字都不得有結論或建議（S8）。這些是工具的固定文字，不是使用者面向的建議文案；但 qa 的 S8 測試必須涵蓋它們。

## 4. 測試（data-engineer；全部 BLOCKING）
- **N199-T1**：N199-A 命中。
  - 批次 planned、已判定成交的 buy → 列出，欄位逐一斷言；
  - 批次 skipped → 列出，`batch_status` 為 skipped；
  - `other_buys` 列出同一批後續的 R1。
- **N199-T2**：N199-A 不命中。
  - 批次 open 的已成交 buy；
  - planned 批次上的 pending buy；
  - planned 批次上的 missed buy（`settled=1`、`missed`）；
  - 批次列不存在的已成交 buy：只出現在 N177-D。
- **N199-T3**：N199-B 命中。
  - 批次 open，加上同批 pending buy → 列出，秒數正確；
  - 批次 closed → 也列出；
  - 時間無法解析 → 秒數為 null，markdown 顯示「無法判定」。
- **N199-T4**：N199-B 不命中。
  - 批次 planned（只命中 A）；
  - pending buy 在別批；
  - 已成交 buy 加上同批 pending **sell**；
  - pending buy 已經 `settled=1`。
- **N199-T5**：N199-C。
  - 同一批兩筆、三筆已成交 buy → 列出，count 正確；
  - 只有一筆 → 不列；
  - 批次列不存在 → `batch_status` 為 null。
- **N199-T6（S11 parity）**：
  - 固定 seed，至少 200 組隨機 book（批次 status ∈ planned、open、closed、skipped，或批次列不存在；buy 列的 settled、status 隨機）；
  - 斷言：N199-B 的 `pending.id` 集合，等於「`SELECT id FROM playbook_directives WHERE action='buy' AND settled=0 AND status='pending' AND {app.playbook.store.BATCH_LEFT_PLANNED_SQL}`」與「同一批存在已成交 buy」兩者的交集。
- **N199-T7（真實路徑）**：用真實 `PlaybookStore` 建 DB，再複製一份執行工具。
  - (i) 只呼叫 `claim_directive`，不呼叫 `settle` → N199-A 為 1 筆；
  - (ii) 先完整結算 r1，再以 `record_directives` 寫入同批第二張 R1（pending）→ N199-B 為 1 筆；
  - (iii) 在 (i) 之後，同批第二張 R1 以 `claim_directive` 加 `settle` 成交 → N199-C 為 1 筆。
  - 這個測試只依賴 `claim_directive`、`settle`、`record_directives` 三個公開方法（N-198 之後保留），所以 N-198 合入後仍然成立。
- **N199-T8**：S2 涵蓋新常數。
  - `*_SQL` 常數的數量釘為「原數 + 4」；
  - 新常數都以 SELECT 開頭；
  - `N199_BATCH_BUYS_SQL` 只以綁定參數執行。
- **N199-T9**：報告。
  - 摘要三列與三節的標題存在；
  - stdout 三行，ASCII；
  - JSON 有 `n199` 鍵、sorted keys、金額是字串；
  - `schema_version == 1`；
  - 以舊版（v1、沒有 `n199`）的 `report.json` 當 `--previous-json` 時，能被接受，`diff_vs_previous` 不變。
- **N199-T10**：`sanitize`。
  - 非預期的 `rule_id`、`batch_status` 顯示為「（非預期值）」並計數；
  - DB 中的自由文字不會出現在 N199 的任何欄位（`rule_summary` 不讀）。
- **N199-T11**：有命中時：exit 0；DB 的前後雜湊相同；只寫兩個報告檔。
- **N199-T12**：S8，新增的固定文字都不含禁詞；L12～L14 都寫進 markdown。

## 5. 隱私（RC-6）與命中回報
- `report.md`、`report.json` 含標的、股數、價格與時間，屬於持股資料：
  - 不得 commit；
  - 不得貼進 `work/`（那也是 repo）；
  - 不得貼進任何對話紀錄。
- 工具既有的 git 工作樹拒絕檢查（RC-5）照舊。
- 交付之後，CEO 依 [TA-177S] 6.8 的步驟執行：停服務；複製 `.db`，有 `-wal`、`-shm` 時一起複製；對複本執行。
- 寫進 `work/` 的命中回報只能有：
  - 三個計數；
  - 腳本 SHA-256；
  - DB 的前後 SHA-256；
  - 執行時間。
- 逐檔明細由 CEO 在本機讀報告，或由 coordinator 以 repo 以外的方式轉給 CEO。
- 任一計數大於 0：coordinator 通知風控與 CEO。N199-A、N199-C 的列，請 CEO 以券商對帳單核對該批的實際持股。這是事實核對的請求，不是處置建議；處置另行裁示。
- 建議：N-198 部署之後再跑一次。N199-A、N199-C 應該不再有新增的列；N199-B 仍可能因跨日重發（V4）而命中。

## 6. QB（qa-reviewer）
- QB-1：diff 只有兩個檔。
- QB-2：第 1 節的既有約束全部零放寬，既有測試原樣綠燈。
- QB-3：N199-T1～T12 存在且綠燈；T6 的 seed 固定、至少 200 組。
- QB-4：Codex 第二意見。
````

### 審查結論、逐條意見、否決理由（輸出契約）

**評估摘要：**
- **採用：**
  - C8 執行與判斷分離的完整程序；
  - N-197a 的鍵不存在分支「視為不變式違反」；
  - set_at 以台北時間精確到秒呈現；
  - ADR-0042 的 P1 方案（逐列單一寫鎖交易）；
  - N-199 的 A、B 兩項，加上 C 項（[TA 補]）。
- **否決：**
  - 鍵不存在時改用不含金額的字面分支；
  - 整次結算一個交易（P2）；
  - 補償式 unclaim（P3）；
  - 新增 claiming 狀態（P4）；
  - G0 守衛（P5，風控已否決）；
  - 行程內鎖（P6）。

**對實作的約束：** 都寫在各區塊內，逐條可以檢查：
- 修訂六：C1、C11～C13、T10～T13、QB-N197a-2；
- ADR-0042：N198-C1～C8、T1～T9；
- N-199：T1～T12、QB-1～4。

**否決理由：** 本輪沒有否決既有的實作方案。

### 其他部門
本輪沒有參與。

## 三、驗證

**讀過的文件：**
- 風控審查全文：`work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md`。
- 規格檔：
  - 第 84-342 行（N-177a 原規格）；
  - 第 688-944 行（修訂一 R-α）；
  - 第 1936-2323 行（修訂四全文）。
- ADR：
  - ADR-0041 全文；
  - ADR-0040：檔頭、Decision 14、:270-299；
  - ADR-0035 中 F2、6′ 相關各行；
  - ADR-0001 模板。
- 追蹤清單：`work/dispatch/2026-10-17-後續追蹤清單.md` 的 :264、:314、:382、:395-404。
- N-182 的 E-2 原文與風控第 11 點。
- 另一位 TA 的修訂五：只用 grep 讀了章節標題，與本修訂不重疊。

**讀過的程式**（都是只讀，沒有執行）：
- backend：
  - `app/main.py`、`app/api/server_error.py`、`app/api/client_header.py`；
  - `app/api/playbook.py`：端點清單、`today`、`RebalanceResponse`；
  - `service.py`：`_settle_pending`、`settle_on_request`、`evaluate_today` 開頭，以及 rebalance／confirm_rules 的位置；
  - `store.py`：常數區、in-flight、`claim_directive`、`batch_blocking_claim`、`settle`、`_connect`、`save_batch`、`get_batch`、`roll_peak_closes`、`_write_state`、state 讀寫、`set_capital`、`set_cash`、`_mark_schedule`；
  - `models.py` 的 `RebalanceResult`；
  - `wording.py` 的 REBALANCE_* 與結算字面的位置；
  - `pyproject.toml`、`uv.lock` 的版本，`dev-up.bat:150`。
- venv 套件原始碼：
  - `starlette/concurrency.py`；
  - `fastapi/routing.py`（相關段落）；
  - `anyio/to_thread.py`；
  - `uvicorn` 的 h11、httptools 兩個 protocol 實作；
  - 各模組的版本字串。
- frontend：
  - `app/lib/queries.ts`、`app/lib/api.ts`（request 與 `getPlaybookToday`）；
  - `@tanstack/query-core/src/query.ts`、`queryClient.ts` 的相關段落。
- 偵測工具：scratchpad `wt_probe` 版本的常數、SQL、`load`、`build_result`、`sanitize`、`render_markdown` 的頭尾、`main`，以及測試檔的測試名稱清單。

**發現的落差：**
- `n177_n190_backtrack_probe.py` 不在主 checkout，只在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_probe/` 與 `.../wt_n190fix/`。
- 主 checkout 的 reflog 在 3985f4d 之後只有兩個 docs commit，看不到 probe 的合入紀錄。
- 這和「已合入 product」的說法不一致，請 coordinator 確認。spec 已經寫明開工前要先比對。

**未查證：**
- 實際並發頻率；
- 瀏覽器在重新整理時的確切中止行為（不影響結論）；
- 實作中的 N-177a、N-177b 中，helper 的實際名稱（`_add_cash` 等以規格為準，PR 實測）；
- N-195 的 `set_total_deploy` 實際寫法。

我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案，也沒有執行任何指令。

## 四、下一步

1. **coordinator：**
   - 前提 (1) 已確認成立，N-197 (b) 的 CEO 通知可以照原文送出，不需刪字。
   - 出清 `onSettled` 的並發路徑，轉給風控決定要不要補進通知。
   - 把修訂六附到規格檔末。
   - 把 ADR-0042 草案現在就送風控，不必等到 N-196 合入。
   - 確認偵測工具在 product 上的實際狀態。
2. **risk-compliance-officer：**
   - 審修訂六第 1、2 節。重點是 1.5 第 2 點「`<tip>` 可以不同」，以及 2.2 選擇不變式違反的理由。
   - 審 ADR-0042 全文、:114 補註的草稿，以及「E-2 不消除」的判定。
   - 決定 N199-C 要不要列為 required。
3. **creative-lead：** 依 [風控-197] 3(c) 與修訂六 2.3 擬 `REBALANCE_SUPERSEDED`。佔位只有 `{total_deploy}`、`{set_at}`，而且 `{set_at}` 已含「台北時間」。
4. **tech-writer：** ADR-0042 在風控審過之後落檔，狀態維持 proposed；R-6′ 的「已修正」註記，等 N-198 合入之後才落檔。
5. **dev-lead：**
   - N-196、N-197a 的 C8 證據依修訂六第 1 節準備；
   - N-198 等 N-177a（以及預設的 N-177b）合入之後才開工。
6. **data-engineer：** 依 N-199 spec 實作。交付之後，由 CEO 依 6.8 的步驟對 production 複本跑一次；回報進 `work/` 的內容只能有計數。
7. **qa-reviewer：** 修訂六、N-198、N-199 中新增的約束都列為 BLOCKING。

**相關檔案：**
- /home/user/AICompany/work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md
- /home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-07-N177a停止點裁示-tech-architect.md
- /home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md
- /home/user/AICompany/docs/adr/0040-stock-desk-排程台以交易日判定為最新的快取日線視為可用.md
- /home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md
- /home/user/AICompany/apps/stock-desk/backend/app/main.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/api.ts
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_probe/apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_probe/apps/stock-desk/backend/tests/test_n177_n190_backtrack_probe.py
