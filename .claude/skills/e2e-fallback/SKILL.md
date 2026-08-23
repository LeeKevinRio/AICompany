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

## 第 3 節・鐵則：不得下載、不得動專案依賴

- **絕不執行 `playwright install` / `playwright install-deps`**：
  離線或受限網路環境會卡住或失敗，而且環境已預裝瀏覽器，裝了只是重複下載。
- **絕不為了驗收在受測專案安裝新依賴**（不改 `package.json` / lockfile / `pyproject.toml`）。
  驗收不得改變被驗收的那份工作區。
- 以下兩個環境變數要在跑腳本時帶上，避免 playwright 自己去抓瀏覽器：

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers   # 換成第 2 節探測到的實際路徑
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
```

- 瀏覽器一律用 `executablePath` 指到探測結果的絕對路徑，不靠 playwright 自動解析版本。

## 第 4 節・啟動受測應用

1. **啟動方式依專案既有流程**：優先用產品線既有的啟動 skill（例如產品線的 `local-run`）、
   `.claude/launch.json`、或 repo 內既有的 dev 腳本；本文件不定義任何產品的指令。
2. 起完後先用 `curl -sS -o /dev/null -w '%{http_code}' <url>` 確認前後端都活著，再開瀏覽器。
3. **資料**：若環境離線或外部資料源不可用，且專案**已有**離線示範資料的種子流程，就用它，
   並在報告中明確標示「本次畫面資料為合成示範資料」；
   若專案沒有這種流程，**不得為了驗收自行捏造資料塞進系統**，改在報告標示「無資料，該項無法驗收」。
4. 啟動失敗（port 佔用、依賴缺失）先如實記錄原始錯誤訊息，再判斷是環境問題還是產品問題——
   產品問題屬 finding，環境問題屬降級障礙。

## 第 5 節・代跑腳本骨架

腳本寫在 **scratchpad（暫存目錄）**，不得留在 repo 工作區。以下骨架已在遠端容器實測可跑，
依實際驗收流程增刪步驟即可（程式碼與註解一律英文）：

```js
// e2e-fallback runner: drive a preinstalled Chromium without touching the project.
const PW = process.env.PW_MODULE || '/opt/node22/lib/node_modules/playwright';
const { chromium } = require(PW);

const EXEC = process.env.PW_CHROME; // absolute path found in section 2
const OUT = process.env.OUT_DIR;    // scratchpad dir, never inside the repo
const BASE = process.env.BASE_URL;

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

  // 1. Verbatim on-screen text: quote this literally in the report.
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

  console.log(JSON.stringify({ heading, style, consoleErrors, failedRequests }, null, 2));
  await browser.close();
})();
```

執行（環境變數由第 2 節的探測結果填入）：

```bash
PW_CHROME=<探測到的 chrome 絕對路徑> OUT_DIR=<scratchpad 目錄> BASE_URL=<應用網址> \
  NODE_PATH=$(npm root -g) node <scratchpad>/runner.js
```

對應關係（原 preview 工具 → 降級做法）：

| preview 工具 | 降級做法 |
| --- | --- |
| `preview_start` / `preview_stop` | 第 4 節的專案既有啟動流程 + `browser.launch()` |
| `preview_click` / `preview_fill` | `page.click()` / `page.fill()` |
| `preview_screenshot` | `page.screenshot()`（桌面 + 375px 各一張） |
| `preview_inspect` | `getComputedStyle()` 取實際值 |
| `preview_console_logs` | `page.on('console' / 'pageerror')` |
| `preview_network` | `page.on('requestfailed' / 'response')` 收 4xx / 5xx |
| `preview_resize` | `page.setViewportSize()` |

## 第 6 節・產出與交件

- 產出物（腳本、截圖、原始輸出）一律放 scratchpad，**不進 repo、不進 commit**。
- 代跑者交件必附：跑的指令、腳本原文、**未經改寫的 stdout**、截圖路徑。
- qa-e2e 依原輸出契約出 Verdict，其中：
  - 「流程逐步結果」每一步要寫**畫面實際字面**（逐字，不要改寫、不要意譯）。
  - 「視覺抽查」寫量測到的實際值 vs 規範值。
  - 任何**沒能實機看到**的項目寫「無法驗收」＋原因，不得用 code 推測補位。

## 第 7 節・降級也不可行時

以下情況才回 `BLOCKING_ISSUES=true` 並升級 CEO，且必須寫清楚卡在哪一步：

- 第 2 節探測不到瀏覽器或 playwright（且不得安裝）。
- 應用在本環境起不來，且原因為環境限制而非產品缺陷。
- 驗收目標本身需要真人感官判斷（動效手感、外部帳號登入）而工具無法覆蓋。

## 附錄・已驗證環境（2026-08-23，遠端容器）

當時實測可用的具體值，供快速比對；**新環境仍以第 2 節探測結果為準**：

- `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`，內含 `chromium-1194`、`chromium_headless_shell-1194`。
- 瀏覽器執行檔：`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`。
- 全域 playwright `1.56.1`：`/opt/node22/lib/node_modules/playwright`（`npm root -g` 可得）。
- 以上組合實跑成功：截圖、`textContent` 逐字取字、`getComputedStyle` 量測、console 收集皆正常，
  全程未執行 `playwright install`、未改動受測專案任何檔案。
