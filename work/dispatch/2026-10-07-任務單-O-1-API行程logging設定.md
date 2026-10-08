# 任務單 O-1：API 行程 logging 設定（等級與時間前綴；httpx 保持 WARNING）

- 日期：2026-10-07　狀態：**draft**（devops-sre 診斷已落檔，見下；待 CEO 排序）　等級：**medium**（可觀測性，不影響資料正確性；但是 F-1b 升級觸發 1 的前提）
- 來源：qa-e2e 第二十四輪觀察「後端 log 行無 level 前綴」；devops-sre 唯讀診斷（HEAD 470f079）。
- 負責：dev-lead（動 `apps/stock-desk/backend/app/main.py`／新增 `app/logging_setup.py`）；qa-reviewer 審查（**審查項：httpx／httpcore 不得被調到 INFO**，並要求測試 `logging.getLogger("httpx").getEffectiveLevel() >= WARNING`）；devops-sre 驗證實際輸出格式與祕密不入 log；security-engineer 知會（順手關掉 2026-10-06「Telegram token 進 log 未重新確認」）。
- 時序：排在 F-1b 之前或同一 release；**不得擋 F-1 部署**（方案 C 先頂著：發版檢查表 grep 訊息本文，不 grep `WARNING`）。不需 ADR。

## 根因（一句話）
`app.main` 從頭到尾沒設 root logger、uvicorn 啟動無 `--log-config`；`app.*` 的 WARNING 走 Python `logging.lastResort`（stderr、只輸出 `%(message)s`、固定 WARNING 以上），所以**無等級、無時間，INFO 整個被丟掉**。scheduler 行程（`scheduler.py:781-783` 有 `basicConfig`）不受影響。

## 採方案 A（devops-sre 建議）
- 新增冪等 `configure_logging()`：格式 `%(asctime)s %(levelname)s %(name)s: %(message)s`；**root 維持 WARNING**，只把 `app`、`scheduler` 設 INFO；明確把 `httpx`、`httpcore` 設 WARNING（httpx 0.28 `_client.py:1025/1740` 以 INFO 記完整 URL，含 `alpha_vantage.py:283` `apikey=`、`finmind.py` `token=`、`alerts/notify.py:36` Telegram `bot{token}` 路徑——**root=INFO 就是新增洩漏面**）；handler 只在 root 無 handler 時加；呼叫放 FastAPI lifespan（`TestClient` 不用 `with` 不觸發，測試零影響），不放 module import 階段。
- uvicorn 自身 `INFO:     ` 行維持；不改 7 處啟動指令。
- 既有測試全用 `caplog` 看 levelno／message／name，不看 formatter，不受影響。

## 發版檢查表 grep（訊息本文；方案 A 前後皆可用）
| 來源 | 行程 | grep 字串 | 意義 |
|---|---|---|---|
| F-1（`valuation.py:402`） | API | `unusable latest close dropped from valuation:` | 收盤 ≤0／非有限被排除出估值 |
| 警示載入失敗（`engine.py:458`） | API（含「立即檢查」） | `alert evaluation: snapshot load failed` | 某標的快照載入例外、該輪略過 |
| scheduler 摘要（`scheduler.py:415`） | scheduler | `failed_symbols=[1-9]` | 本輪有標的載入失敗 |
| F-1b（R-3） | API | `unusable fx rate dropped from valuation:`（建議；dev-lead 以 pin 測試釘死） | 升級觸發 1 |
API 看 backend 視窗／`docker compose logs backend`／`logs\api.log`；scheduler 看 `docker compose logs scheduler`／`logs\scheduler.log`。`release-flow` SKILL 目前沒有任何 log grep 步驟，待 F-1b 字串定下後由 devops-sre 一併補。

---

# devops-sre 診斷全文（2026-10-07，唯讀；coordinator 原文轉錄）

## 現況診斷（唯讀，未改任何檔；HEAD 470f079，分支 product/stock-desk）

**根因：API 行程（`app.main`）從頭到尾沒有設定 root logger。不是 uvicorn 參數問題。**

1. `apps/stock-desk/backend/app/main.py` 全檔（1-80 行）沒有 `import logging`、沒有 `basicConfig`、沒有 lifespan。`app/` 下也沒有任何 `logging*.py`。
2. uvicorn 啟動全部是預設，沒有 `--log-config`／`--log-level`。以下全是同一種寫法：
   - `apps/stock-desk/README.md:61`、`backend/README.md:21`、`.claude/skills/local-run/SKILL.md:61`、`dev-up.sh:76`、`dev-up.bat:115`：`uvicorn app.main:app --reload --port 8000`
   - `compose.yaml:20`、`backend/Dockerfile:20`：`uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - 主機部署手冊 `docs/族群動能-主機部署手冊.md:139`：同上，輸出導向 `logs\api.log`
3. uvicorn 預設 `LOGGING_CONFIG`（我用 venv 的 uvicorn 0.51.0 實測印出）只設定 `uvicorn`、`uvicorn.error`、`uvicorn.access` 三個 logger，其中 `uvicorn` 與 `uvicorn.access` 為 `propagate: false`。root logger 沒有 handler，也沒有被動到。
4. 所以 `app.*` 的 logger（例如 `app.portfolio.valuation`）沒有自己的 handler，往上傳到 root，root 沒 handler，Python 走 `logging.lastResort`。它是 stderr 上的 `StreamHandler`，level 固定 WARNING，沒有 formatter，只輸出 `%(message)s`。
   - 後果一：WARNING 以上只有訊息本文，沒有等級與時間。`exc_info` 的 traceback 仍會印。
   - 後果二：**INFO 整個被丟掉**（lastResort 只收 WARNING 以上）。這代表 API 行程裡所有 `logger.info` 運維看不到，包含 `app.data.service` 的 INFO。

**證據（第二十四輪 `scratchpad/e2e-24/`）**
- `start-backend.sh` 啟動指令是 `nohup .venv/bin/uvicorn app.main:app --port 8000 > backend-$1.log 2>&1 &`，無任何 log 參數。
- `backend-2.log` 實際輸出：uvicorn 自己的行有 `INFO:     ` 前綴；夾在中間的 `unusable latest close dropped from valuation: symbol=2330 market=TW date=2026-10-02 close=0 source=demo_synthetic` 逐字無前綴，與 qa-e2e 觀察一致。
- 這支 log 內沒有任何 `WARNING` 字樣，所以運維若 grep `WARNING` 會漏。

**既有 WARNING 的對照**
- scheduler 行程：`app/scheduler.py:781-783` 的 `main()` 有 `logging.basicConfig(level=INFO, format="%(asctime)s %(levelname)s %(message)s")`。所以 `python -m app.scheduler`（compose、local-run、手冊皆是此寫法）有 `時間 等級 訊息` 前綴，且 INFO 也看得到。`failed_symbols=` 摘要行（`scheduler.py:413-419`，logger 名 `scheduler`，有失敗時升 WARNING）因此有前綴。
- 同一個 scheduler format 沒有 `%(name)s`，看不出 logger 來源，但目前可接受。
- API 行程的 `engine._load_isolated` WARNING（`app/alerts/engine.py:458`，`alert evaluation: snapshot load failed (market=...`）：**同樣無前綴**。這在 `work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md:54` 已有揭露。`POST /api/alerts/evaluate`（畫面「立即檢查」）走這條路，只有 API log 看得到，沒有摘要行。
- CEO 本機用 `local-run`（`dev-up.sh`／`dev-up.bat` 或手動指令）啟動後端，指令與上面相同，所以**格式與 e2e 相同**：無前綴，且是 `--reload` 模式（reload worker 子行程同樣沒有 root 設定）。
- 測試不受 lastResort 影響：tests 全用 `caplog`，沒有任何 `capsys`／`capfd` 去斷言 log 格式（capsys 僅用在 demo_seed／directory_sync 的 print 輸出）。

## 建議方案

**方案 A（建議）：在 API 入口做一次性、冪等的 logging 設定，不動 uvicorn 啟動指令。**
- 新增一個小函式（例如 `app/logging_setup.py::configure_logging()`），格式與 scheduler 對齊並補上 logger 名：`%(asctime)s %(levelname)s %(name)s: %(message)s`。
- 設定要點，**這段比格式本身重要**：
  1. **不要把 root 設成 INFO。** 所有外呼都用 httpx，而 httpx 0.28 在 `_client.py:1025` 與 `:1740` 會以 INFO 記完整請求 URL。URL 內含祕密：`alpha_vantage.py:283` 的 `apikey=`、`finmind.py` 的 `token=`、`alerts/notify.py:36` 的 Telegram `bot{token}` 路徑。root=INFO 會把這些寫進 log 檔。2026-10-06 全員評價已點名「Telegram token 進 log 未重新確認」，這個修法如果做錯就是新增洩漏面。
  2. 建議：root 維持 WARNING，只把 `app` 與 `scheduler` 這兩個命名空間設為 INFO；並明確把 `httpx`、`httpcore` 設為 WARNING 當雙保險。
  3. handler 只在 root 沒有 handler 時才加（等同 `basicConfig` 語意），避免重複輸出。
  4. 呼叫位置：避免在 `app/main.py` 的 module import 階段直接呼叫，否則每個 import `app.main` 的測試都會往 root 掛 handler。較穩的做法是放進 FastAPI lifespan 啟動階段，或在 module 層做但帶 `PYTEST_CURRENT_TEST` 之類的守門（我偏好 lifespan；若 `TestClient` 不用 `with` 就不會觸發 lifespan，測試零影響）。這由 dev-lead 在 `app/main.py` 落地（我目前不動 `apps/`）。
- uvicorn 自己的 `INFO:     ` 行維持原樣，不用動，也不會重複（`uvicorn` 與 `uvicorn.access` 皆 `propagate: false`，`uvicorn.error` 只上傳到 `uvicorn`，不會到 root）。
- 影響範圍：API 行程的 stdout／stderr 格式；`app.*` 的 INFO 會首度出現（`app.data.service` 等，量級為每請求少量，需實作時確認不暴增）。不影響 API 回應、DB、前端。
- 對既有測試：caplog 斷言看的是 `record.levelno`、`getMessage()`、`record.name`（我抽查 `test_unusable_close_f1.py`、`test_alerts_engine.py`、`test_scheduler*.py`、`test_service.py`、`test_providers_fx.py`），不看 formatter，**不受影響**。需注意 pytest 的 `caplog.at_level` 會暫時改 root level，與上述「root 保持 WARNING、`app`／`scheduler` 設 INFO」不衝突。
- 是否需要 ADR：**不需要**（純運維面設定，不改架構、不改契約）。唯一的界線是第 1 點的祕密不入 log，這是 CLAUDE.md 第 4 節既有規則的落地，不是新決策。建議由 dev-lead 實作、qa-reviewer 審查時把「httpx 不得被調到 INFO」寫成一條審查項，最好加一個測試：設定完成後 `logging.getLogger("httpx").getEffectiveLevel() >= WARNING`。

**方案 B：uvicorn `--log-config` 檔，或 `--log-level` 加環境變數。** 需改 7 處啟動指令（README×2、SKILL、dev-up.sh／bat、compose、Dockerfile、手冊），而且 `uv run uvicorn` 的使用者若忘了參數就退回現況。不建議。

**方案 C：不改 code，只改發版檢查表，改成 grep 訊息本文不 grep `WARNING`。** 零風險，可作為方案 A 落地前的過渡；缺點是 INFO 仍然看不到，且無時間戳，事後無法對時。

## 發版檢查表要加的 grep（字串都是訊息本文，A 方案前後都可用；不依賴 level 前綴）

| 來源 | 行程 | grep 字串 | 代表意義 |
| --- | --- | --- | --- |
| F-1（`valuation.py:402`） | API／backend | `unusable latest close dropped from valuation:` | 有收盤價 ≤0 或非有限值被排除出估值 |
| 警示載入失敗（`engine.py:458`） | API／backend（含「立即檢查」） | `alert evaluation: snapshot load failed` | 某標的快照載入例外，該輪警示略過 |
| scheduler 摘要（`scheduler.py:415`） | scheduler | `failed_symbols=[1-9]` | 本輪有標的載入失敗（0 為正常，需用 `[1-9]` 避免誤中） |
| F-1b（待 dev-lead 定字串） | API／backend | **待定**；任務單 KF-11 只規定「英文、logger `app.portfolio.valuation`、含 `pair=`、`date=`、`rate=`、`source=`」，沒規定固定開頭 | 升級觸發 1 |

給 dev-lead 的 F-1b 要求：開頭字串要是固定、可 grep、且和 F-1 的 `unusable latest close dropped from valuation:` 明確區分的字面，例如 `unusable fx rate dropped from valuation:`，並在任務單／測試中釘死逐字。同時建議 F-1b 測試比照 F-1 用 caplog 斷言整句開頭。

檢查表另需寫明「兩種來源要看兩個地方」：API 的 WARNING 看 backend 視窗或 `docker compose logs backend`／`logs\api.log`；scheduler 看 `docker compose logs scheduler`／`logs\scheduler.log`。可以在 `docs/` 或 `release-flow` 補一行（現行 `.claude/skills/release-flow/SKILL.md` 沒有任何 log grep 步驟）。

## 是否開單

1. **建議開單：「API 行程 logging 設定（等級與時間前綴，httpx 保持 WARNING）」，等級 medium。** 理由：影響的是可觀測性，不影響資料正確性；但它是升級觸發 1 的前提，沒有它 F-1b 的 WARNING 只能靠本文 grep、無時間戳，事後無法對時。執行者 dev-lead（動 `apps/`），qa-reviewer 審查，我負責驗證實際輸出格式與祕密不入 log 的檢查。**時序建議：排在 F-1b 之前或同一個 release，且不得擋 F-1 部署**（方案 C 先頂著）。
2. **發版檢查表加 grep 一步**：由我（devops-sre）處理，屬低等級文件變更，等 F-1b 字串定下後一併補。目前不必為此單獨開單，併入上面那張單即可。
3. 若做 A 方案時要把 httpx URL 洩漏面驗證一遍（含 Telegram 路徑），建議順手把「Telegram token 進 log」這條 2026-10-06 的未確認事項關掉；那是獨立查證，不用另外升級。

## 相關檔案（絕對路徑）
- /home/user/AICompany/apps/stock-desk/backend/app/main.py
- /home/user/AICompany/apps/stock-desk/backend/app/scheduler.py（L413-419 摘要行、L781-783 `basicConfig`）
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py（L402）
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/engine.py（L458）
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/notify.py（L36 Telegram URL 含 token）
- /home/user/AICompany/apps/stock-desk/compose.yaml、/home/user/AICompany/apps/stock-desk/backend/Dockerfile、/home/user/AICompany/apps/stock-desk/dev-up.sh、/home/user/AICompany/.claude/skills/local-run/SKILL.md
- /home/user/AICompany/work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md（L54 已揭露 API 無前綴）
- /home/user/AICompany/work/dispatch/2026-10-07-任務單-F-1b-匯率非正值的估值防護.md（KF-11）

---

## 風控裁定（2026-10-08，X-3c 第二段附帶；coordinator 轉錄）
- **接受，列 low；不屬 X3-F8 的觸發情形。**
- 理由：reason 裡的 `FX_APPLIED_NOTE` 在此情境到不了使用者面前——price 規則有守門（`engine.py:482-485`）、signal 規則有守門（`:503-507`）、risk-limit 規則不讀 reason（`:338`）；fired 訊息附的來源句修飾的是估值器已用匯率換算過的第 1、2、3 條數字，確有套用匯率，與一致帳本現況相同。
- **重審觸發**：若估值器與 snapshot 的 `fx_provider` 可能使用不同來源或日期，視為 X3-F8 情形。
- suggested **XS-2**：在 T10-3 或 X-3c 測試追加斷言「所有 outcome 的 reason 都不含 `FX_APPLIED_NOTE` 前綴」，釘住引擎三道守門防退化。
- 審查紀錄：`work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md` 第二段。
