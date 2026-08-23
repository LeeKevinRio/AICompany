---
name: e2e-fallback
description: preview MCP 不可用時的 E2E 實機驗收降級路徑——改用環境預裝的 Playwright + Chromium 代跑實機操作、截圖與 CSS 量測，維持與 qa-e2e 相同的驗收紀律。當 qa-e2e 會話拿不到 `preview_*` 工具（遠端／容器環境未掛載 Claude_Preview MCP）、或任何 UI 驗收需要在無 MCP 環境進行時必用。
---

# e2e-fallback — preview 不可用時的實機驗收降級路徑

> 存在理由：`qa-e2e` 的工具集以 Claude_Preview MCP 為主。**該 MCP 不一定掛載得到**
> （遠端容器環境實測就拿不到），此時 qa-e2e 會話只剩 Read / Grep / Glob，
> 既不能啟動應用也不能截圖，UI 驗收會整條卡死。本 skill 把「降級但仍是實機」的路徑寫死，
> 避免每次 UI 驗收都先撞一次牆、再臨場發明流程。
>
> **降級的是工具，不是紀律**：本文件所有步驟都不放寬 qa-e2e 的驗收標準，
> 尤其是「不得以讀 code 代替實機觀察」。

## 第 0 節・判定：要不要降級（30 秒內決定）

1. qa-e2e 接到任務的第一件事：檢查自己這次會話**實際拿到**的工具清單裡有沒有
   `mcp__Claude_Preview__preview_start`。
2. **有** → 走原本的 preview 流程，本 skill 用不到。
3. **沒有** → 一句話宣告降級（例：「本會話未掛載 Claude_Preview MCP，改走 `e2e-fallback`」），
   接第 1 節，**不要**直接回 `BLOCKING_ISSUES=true` 收工。
   **半殘也算不可用**：`preview_start` 在清單中、但實際呼叫持續失敗或 timeout
   （非操作本身寫錯，而是工具起不來）→ 視同不可用，同樣走降級，並在報告註明實際現象與錯誤訊息。
   不要卡在「工具好像有、又不能用」的中間地帶反覆重試。
4. 只有在第 1 節的代跑也不可行時（見第 7 節），才升級 CEO 由他決定擋件或改期。

## 第 1 節・角色分工：誰跑、誰判

降級路徑需要開 process、跑瀏覽器、寫檔，這些都要 **Bash**；
而 `qa-e2e` 依公司章程「最小權限」是唯讀角色（無 Write / Edit / Bash），
**這條界線不因為降級而放寬**。因此降級時拆成兩個人：

| 角色 | 誰 | 做什麼 | 不做什麼 |
| --- | --- | --- | --- |
| **代跑執行者** | 具 Bash 權限者，預設 `qa-automation` | 依第 2–5 節啟動應用、跑腳本、產出截圖與逐字文字、貼原始輸出 | 不下 PASS / NEEDS_CHANGES 判斷、不挑要不要報的異常 |
| **驗收判讀者** | `qa-e2e` | 讀截圖與逐字輸出、比對預期行為與視覺規範、出具 Verdict | 不改腳本、不改受測應用 |

- 代跑執行者只交**事實**（畫面、逐字文字、量測值、console / network 原始輸出），
  判斷權留給 qa-e2e，獨立性不變。
- qa-e2e 的輸出契約照原格式，另在「驗收摘要」註明 **「以 e2e-fallback 代跑，代跑者：<who>」**，
  讓 CEO 知道證據是怎麼來的。
- 代跑者若發現腳本本身跑不動（選擇器找不到、頁面空白），**如實回報現象**，
  不得改受測應用來遷就腳本。

## 第 2 節・前置探測（先確認環境，再寫腳本）

依序跑，全部有結果才往下：

```bash
# 1) 預裝瀏覽器在哪（常見於 PLAYWRIGHT_BROWSERS_PATH 指到的目錄）
echo "$PLAYWRIGHT_BROWSERS_PATH"
ls -d "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"/*/chrome-linux/chrome

# 2) 有沒有可用的 playwright 套件（優先找全域安裝）
npm root -g
NODE_PATH=$(npm root -g) node -e "console.log(require('playwright/package.json').version)"
```

- 探測全部落空（找不到瀏覽器或找不到 playwright）→ 直接跳第 7 節，不要嘗試安裝。
- 專案自己已經有 `@playwright/test` 依賴時，優先用專案的，仍**沿用預裝瀏覽器**（見第 3 節）。
- **供應鏈信任邊界（硬性）**：探測到的瀏覽器執行檔與 playwright 模組路徑，
  都必須落在環境既定的預裝前綴下（本環境為 `/opt/`，實際前綴以 devops-sre 的環境定義為準）。
  解析結果落在該前綴之外（例如指到某個使用者目錄、專案內 `node_modules`、暫存目錄）
  **一律視同探測失敗**，走第 7 節升級，不得臨場判斷「應該也可以」。

```bash
# 邊界檢查：兩個路徑都要以既定前綴開頭，否則視同探測失敗
case "$(NODE_PATH=$(npm root -g) node -p "require.resolve('playwright')")" in /opt/*) echo OK;; *) echo REJECT;; esac
```

> 這個探測是**給人看的早期訊號**，不是控制本身——它跟 runner 實際載入模組是兩次獨立的解析事件。
> 真正的控制是第 5 節 runner 開頭的 fail-closed 斷言（同一條前綴，不符就 `exit 1`），
> 第 6 節的 `provenance` 查核則是事後稽核。三者是同一條防線的三個時間點，不可互相取代。

## 第 3 節・鐵則：僅允許執行既有套件，任何安裝一律禁止

**採白名單（僅允許項），不採列舉禁止**——列舉法一定漏。

**僅允許**：
- 用 `node <scratchpad 腳本>` 執行**環境既有**的全域 playwright（路徑須通過第 2 節的邊界檢查）。
- 唯讀的探測指令（`ls`、`npm root -g`、`node -p require.resolve(...)`、`curl` 對本機受測服務）。

**其餘一律禁止**，包含但不限於任何形式的套件安裝／更新／下載：
`playwright install`、`playwright install-deps`、`npx <未安裝的套件>`、
`npm install` / `npm i -g` / `pnpm add` / `yarn add`、`pip install` / `uv add`、`apt-get install`、
以及任何直接抓檔的 `curl -O` / `wget`。
**不得為了驗收改動受測專案的依賴宣告**（`package.json` / lockfile / `pyproject.toml` 等）——
驗收不得改變被驗收的那份工作區。

> 出現「必須裝東西才跑得起來」的需求時，這不是可以自己解的障礙：
> 一律視同第 7 節的「降級不可行」，回報並升級 CEO 決定，由具權責者處理環境。

環境變數與啟動方式：

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers   # 換成第 2 節探測到的實際路徑
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1          # defense-in-depth，非充分條件（見下方註）
```

- 註：本流程是直接 `require()` 全域套件並指定 `executablePath`，
  **本來就不會走到自動下載路徑**；`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD` 只是多一層保險，
  不要誤以為有設它就等於「安全、可以隨便下指令」——真正的控制是本節的白名單。
- 瀏覽器一律用 `executablePath` 指到探測結果的絕對路徑，不靠 playwright 自動解析版本。

## 第 4 節・啟動受測應用

1. **啟動方式依專案既有流程**：優先用產品線既有的啟動 skill（例如產品線的 `local-run`）、
   `.claude/launch.json`、或 repo 內既有的 dev 腳本；本文件不定義任何產品的指令。
2. 起完後先用 `curl -sS -o /dev/null -w '%{http_code}' <url>` 確認前後端都活著，再開瀏覽器。
3. **環境限制（硬性）**：本流程**只能對接沙盒 / demo / 本機非正式環境**。
   不得使用真實金鑰或正式環境憑證，不得把受測應用指向正式的帳務、持倉、金流或任何含真人資料的資料源。
   受測應用預設會連正式資料源且**無法切換**時，先回報這個事實，
   由 CEO 決定是否照第 6 節的遮罩規則有限度進行，或直接走第 7 節。
4. **資料**：若環境離線或外部資料源不可用，且專案**已有**離線示範資料的種子流程，就用它，
   並在報告中明確標示「本次畫面資料為合成示範資料」；
   若專案沒有這種流程，**不得為了驗收自行捏造資料塞進系統**，改在報告標示「無資料，該項無法驗收」。
5. 啟動失敗（port 佔用、依賴缺失）先如實記錄原始錯誤訊息，再判斷是環境問題還是產品問題——
   產品問題屬 finding，環境問題屬降級障礙。

## 第 5 節・代跑腳本骨架

腳本寫在 **scratchpad（暫存目錄）**，不得留在 repo 工作區。以下骨架已在遠端容器實測可跑，
依實際驗收流程增刪步驟即可（程式碼與註解一律英文）：

```js
// e2e-fallback runner: drive a preinstalled Chromium without touching the project.
// Bare specifier on purpose: require() ignores NODE_PATH for absolute paths, so a
// hardcoded default would silently pin one machine's layout.
const PW = process.env.PW_MODULE || 'playwright';
const EXEC = process.env.PW_CHROME; // absolute path found in section 2
const OUT = process.env.OUT_DIR;    // scratchpad dir, never inside the repo
const BASE = process.env.BASE_URL;

// --- Fail-closed instrument check. Runs before anything else, on purpose. ---
// Node resolves node_modules by walking up from THE SCRIPT FILE'S OWN PATH, and that
// lookup wins over NODE_PATH. So a scratchpad nested anywhere under the product repo
// lets the code under test supply the instrument that measures it -- `cd` does not
// help, because cwd is not what drives resolution. The measurement is only as
// trustworthy as its instrument, so refuse to run rather than emit pretty evidence.
const TRUSTED_PREFIX = process.env.TRUSTED_PREFIX || '/opt/'; // env fact, owned by devops-sre
const assertTrusted = (label, p) => {
  if (typeof p !== 'string' || !p.startsWith(TRUSTED_PREFIX)) {
    console.error(`e2e-fallback: ABORT -- untrusted ${label}`);
    console.error(`  resolved to: ${p}`);
    console.error(`  expected under: ${TRUSTED_PREFIX}`);
    console.error('  this run produces no valid evidence; escalate per section 7.');
    process.exit(1);
  }
};
// Resolve before require(): requiring a hostile module executes its top-level code,
// so asserting afterwards would already be too late.
const PW_RESOLVED = require.resolve(PW);
assertTrusted('playwright module', PW_RESOLVED);
assertTrusted('chromium executable', EXEC);

const { chromium } = require(PW);

// Instrument provenance, echoed into the evidence packet so the check is auditable
// after the fact too (the section 2 probe is a separate resolution event and proves
// nothing about this run). qa-e2e re-verifies these in section 6.
const provenance = { playwrightModule: PW_RESOLVED, chromiumExecutable: EXEC, trustedPrefix: TRUSTED_PREFIX };

(async () => {
  const browser = await chromium.launch({ executablePath: EXEC });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  // Collect evidence the reviewer cannot get from code reading.
  const consoleErrors = [];
  const failedRequests = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message}`));
  page.on('requestfailed', (r) => failedRequests.push(`${r.url()} ${r.failure()?.errorText}`));
  page.on('response', (r) => { if (r.status() >= 400) failedRequests.push(`${r.status()} ${r.url()}`); });

  await page.goto(BASE, { waitUntil: 'networkidle' });

  // 1. Verbatim on-screen text: quote UI copy literally in the report, but mask
  //    account-specific values (amounts, holdings, identifiers) per section 6.
  const heading = await page.locator('h1').first().textContent();

  // 2. Measured CSS values, the replacement for preview_inspect.
  const style = await page.locator('h1').first().evaluate((el) => {
    const s = getComputedStyle(el);
    return { color: s.color, fontSize: s.fontSize, background: s.backgroundColor };
  });

  // 3. Screenshots: desktop and 375px mobile viewport.
  await page.screenshot({ path: `${OUT}/desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: `${OUT}/mobile-375.png`, fullPage: true });

  console.log(JSON.stringify({ provenance, heading, style, consoleErrors, failedRequests }, null, 2));
  await browser.close();
})();
```

執行（環境變數由第 2 節的探測結果填入）：

```bash
PW_CHROME=<探測到的 chrome 絕對路徑> OUT_DIR=<scratchpad 目錄> BASE_URL=<應用網址> \
  NODE_PATH=$(npm root -g) node <scratchpad>/runner.js
```

- **`cd` 不是防線，別靠它**（本 skill 曾一度這樣寫，是錯的）：
  Node 找 `node_modules` 是從**腳本檔案自身的路徑**逐層往上找，這個查找**優先於 `NODE_PATH`**，
  而**與 cwd 無關**。因此只要 runner 腳本檔**放在受測產品目錄樹底下的 scratchpad**
  （例如 `<product-repo>/scratchpad/runner.js`），先 `cd` 進 scratchpad 再用絕對路徑執行，
  載入到的**仍然是產品樹裡的那份影子套件**——實測重現過。
  真正擋下它的是 **runner 開頭的 fail-closed 前綴斷言**（不符合就 `exit 1`，跑都跑不起來）；
  第 2 節的探測與第 6 節的查核是它的前後兩道稽核，不是替代品。
- 可行的話仍建議把 scratchpad 放在**受測專案樹之外**，但那是衛生習慣，**不是控制**。
- `NODE_PATH` 只對 **bare specifier**（`require('playwright')`）生效；
  一旦把 `PW_MODULE` 設成絕對路徑，`require()` 就直接吃該路徑、完全不查 `NODE_PATH`
  （斷言仍會擋下前綴不符的路徑）。
  要覆寫請確認該絕對路徑通得過第 2 節的前綴檢查。
- 解析失敗（`MODULE_NOT_FOUND`）是**預期行為**，代表這台機器沒有可信的既有 playwright ——
  走第 7 節升級，**不要**用安裝來「修好它」。

對應關係（原 preview 工具 → 降級做法）：

| preview 工具 | 降級做法 |
| --- | --- |
| `preview_start` / `preview_stop` | 第 4 節的專案既有啟動流程 + `browser.launch()` / `browser.close()` |
| `preview_list` | N/A——降級是單一瀏覽器 session，沒有多實例可列 |
| `preview_click` / `preview_fill` | `page.click()` / `page.fill()` |
| `preview_screenshot` | `page.screenshot()`（桌面 + 375px 各一張） |
| `preview_snapshot` | `page.locator(...).ariaSnapshot()` |
| `preview_eval` | `page.evaluate()`——查非 CSS 的頁面狀態（DOM 屬性、`localStorage`、全域變數）時最好用，別忘了它 |
| `preview_inspect` | `page.locator(...).evaluate()` 內 `getComputedStyle()` 取實際值 |
| `preview_console_logs` | `page.on('console' / 'pageerror')` |
| `preview_logs` | 若指的是瀏覽器外部的 log（dev server / 後端輸出）則**無對應**，需視專案啟動方式自行取得，取不到就在報告如實標示 |
| `preview_network` | `page.on('requestfailed' / 'response')` 收 4xx / 5xx |
| `preview_resize` | `page.setViewportSize()` |

## 第 6 節・產出與交件

- 產出物（腳本、截圖、原始輸出）一律放 scratchpad，**不進 repo、不進 commit**。
- 代跑者交件必附：跑的指令、腳本原文、**未經改寫的 stdout**（含 `provenance` 欄位）、截圖路徑。
  「未經改寫」的**唯一例外**是敏感欄位——依下方〈敏感資料處置〉遮罩後才算數，
  遮罩過的 stdout 仍屬「未經改寫」。兩條規則請一起讀完再動手，別只照第一句做。
- **儀器來源查核（qa-e2e 收到證據後的第一件事）**：確認 stdout 的
  `provenance.playwrightModule` 與 `provenance.chromiumExecutable` **兩個路徑都落在既定前綴內**
  （第 2 節）。任一落在前綴之外（尤其是指進受測專案的 `node_modules`）→
  **該批證據作廢**，不得據以判斷，走第 7 節。
  同時確認 stdout **不是**以 `e2e-fallback: ABORT` 開頭——那代表 runner 的斷言已擋下該次執行，
  這種情況沒有證據可判，直接走第 7 節。
  **比對基準一律取自第 2 節的既定前綴（devops-sre 的環境定義），
  不得以 stdout 裡的 `provenance.trustedPrefix` 為準**——拿封包自己宣告的基準去量封包自己的路徑，
  必然自洽通過（極端情況 `TRUSTED_PREFIX=/` 會一路綠燈），查核形同虛設。
  若 `provenance.trustedPrefix` 與既定前綴不一致，代表該次執行**放寬了信任邊界**，
  **證據作廢**，走第 7 節。
  理由：第 2 節的探測與 runner 的 `require()` 是**兩次獨立的解析事件**，探測綠燈不代表這次跑用的是同一份。
  **量測儀器不得由受量測者提供**，這條由裁判查、不由代跑者自證。
  本 skill 開發時實測重現過這個攻擊：受測樹裡一份假 playwright（代理真模組但把量測值悄悄取整），
  第 2 節探測仍綠燈、`NODE_PATH` 也設對了，畫面文字與 console 全部正常，
  真實的 `15.9998px` 被改寫成好看的 `16px`——**唯一露出破綻的欄位就是 `provenance`**。
  現在 runner 開頭的 fail-closed 斷言會讓這種跑法**直接 `exit 1`**；本查核是它的第二道稽核
  （防止有人改了骨架、拿掉斷言、或用舊版腳本），不是唯一防線。
- qa-e2e 依原輸出契約出 Verdict，其中：
  - 「流程逐步結果」每一步要寫**畫面實際字面**（逐字，不要改寫、不要意譯）。
  - 「視覺抽查」寫量測到的實際值 vs 規範值。
  - 任何**沒能實機看到**的項目寫「無法驗收」＋原因，不得用 code 推測補位。

### 敏感資料處置（與逐字要求的界線）

證據會沿著「螢幕 → 逐字證據 → Verdict 報告」往下傳，而 Verdict 依章程會落到 `work/` 或任務單
（**會被 commit、會被長期保留**）。因此「檔案不進 commit」不夠，**內容轉述**也要管：

- **遮罩對象只有敏感數值**：真實金額、持倉數量、帳號 / 卡號、Email、電話、身分識別碼、
  API key 或 token 片段——一律寫成 `***` 或量級描述（例：「六位數新台幣金額」），不得原文抄錄。
- **別漏掉 URL**：`failedRequests` 收的是完整網址，query string 常夾帶 `token` / `session_id` /
  `api_key` / 簽章等參數。貼進報告前逐條掃過，把參數值遮掉（保留參數名與路徑，
  它們才是判斷失敗原因需要的資訊）；`consoleErrors` 內含的網址與 stack trace 同樣要掃。
- **文案字面仍必須逐字**：介面標籤、按鈕文字、狀態提示、錯誤訊息、免責聲明與風險揭露句，
  **一個字都不能改寫或省略**——這是 e2e 驗收的核心價值，遮罩規則對這些內容**不適用**。
  界線一句話記：**「這串字是設計出來給所有使用者看的」→ 逐字；「這串數字屬於某個特定人 / 帳戶」→ 遮罩。**
- **合成示範資料不必遮罩**，但要在報告標示它是合成資料（見第 4 節第 4 點）。
- 遮罩若讓某個驗收點無法判斷（例如就是要驗數字格式），在報告寫明
  「因含敏感數值改以遮罩呈現，該項僅驗格式不驗數值」，不得為了方便就把原值貼上去。
- **截圖只能待在 scratchpad**：不得複製、貼上或附加到任何其他位置——
  包含 repo 工作區、`work/` 任務單附件、PR / issue comment、外部聊天或雲端空間。
  需要讓人看畫面時，給 scratchpad 路徑，不要搬檔案。
- **截圖視同一次性資料**：只是本次驗收的臨時證據，不得長期保留；
  驗收結束（Verdict 交付、爭議釐清完畢）即可刪除，不做歸檔。

### 轉述失真（通則）

> **代跑者的職責是傳輸，不是清理；任何看起來像「壞掉」的輸出，壞掉本身就是資料。**

遮罩是**唯一**獲准的內容變更（且僅限敏感數值）。除此之外，證據一律原樣搬運——
好心的修正會蓋掉事實，而且失真通常剛好發生在最該被看見的地方。同族陷阱：

- **亂碼自行「還原」**：亂碼通常代表回應沒宣告 `charset=utf-8`，
  那就是真實使用者也會看到的缺陷（本 skill 開發時實測重現過），屬 finding。
- **數值四捨五入**：把 `getComputedStyle` 的 `15.9998px` 寫成 `16px`——
  抹掉的正是真實的 sub-pixel bug。量測值有幾位數就寫幾位數。
- **美化或重排 JSON / stack trace**：順序、縮排、被截斷的片段都可能是線索，原樣貼。
- **順手修「顯然是 typo」**：介面上的錯字就是要被回報的缺陷，不是你的筆誤。
- **把英文錯誤訊息翻成中文**：報告正文用繁中，但**錯誤訊息與畫面字面保留原文**，
  需要時另外加註說明，不得以譯文取代原文。

## 第 7 節・降級也不可行時

以下情況才回 `BLOCKING_ISSUES=true` 並升級 CEO，且必須寫清楚卡在哪一步：

- 第 2 節探測不到瀏覽器或 playwright，或解析到的路徑落在既定前綴之外（且不得安裝）。
- 要跑起來就得安裝／更新／下載任何套件（第 3 節白名單以外的指令）——這一律不是自己解的障礙。
- 應用在本環境起不來，且原因為環境限制而非產品缺陷。
- 受測應用只能連正式／含真人資料的資料源且無法切換到沙盒（第 4 節第 3 點），而 CEO 未裁示可有限度進行。
- 驗收目標本身需要真人感官判斷（動效手感、外部帳號登入）而工具無法覆蓋。

## 附錄・已驗證環境（2026-08-23，遠端容器）

> **歸屬**：以下版本號與路徑是**環境事實，維護責任在 devops-sre**——
> 於 2026-08-23 在本環境實測取得，架構面不背書任何特定版本；
> 環境變更（node / playwright / 瀏覽器版本異動）時由 devops-sre 更新本附錄。
> 本 skill 的流程本身不依賴這些值，**新環境一律以第 2 節探測結果為準**。

當時實測可用的具體值，供快速比對：

- `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`，內含 `chromium-1194`、`chromium_headless_shell-1194`。
- 瀏覽器執行檔：`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`。
- 全域 playwright `1.56.1`：`/opt/node22/lib/node_modules/playwright`（`npm root -g` 可得）。
- 以上組合實跑成功：截圖、`textContent` 逐字取字、`getComputedStyle` 量測、console 收集皆正常，
  全程未執行 `playwright install`、未改動受測專案任何檔案。
