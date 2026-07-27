# Codex 接入待辦 — 讓「跨廠商第二意見」真的能跑起來

負責人：devops-sre
最後更新：2026-07-27
狀態：待 CEO 裁示（放行網路政策 + 決定認證路徑）

## 0. 這份文件要解決什麼

CLAUDE.md 第 2 條規定：code review 由 qa-reviewer 加呼叫 OpenAI Codex CLI（`/review`）做第二意見。
實際定義這個流程的檔案是：

- `.claude/commands/review.md` — `/review` command 本體，定義呼叫方式與輸出格式。
- `.claude/skills/code-review-checklist/SKILL.md` — qa-reviewer 的標準審查流程，第 3 步要求執行 `/review`。

> 備註（查證結果）：協調者背景資訊提到的路徑 `.claude/skills/review/SKILL.md` 在 repo 內**不存在**；
> 用 `Glob` 對 `.claude/skills/**/SKILL.md` 掃描後確認實際檔案是上面兩個。本文件以實際存在的檔案為準。

現況：Codex 第二意見在 stock-desk Phase 5、6、7 的所有審查輪次全部缺席，qa-reviewer 每輪都如實註記「無法執行，原因：__」，未當作通過條件（符合 `code-review-checklist` 第 3 步「無法執行時在報告註明原因」的要求，但長期缺席代表少了一道防線，需要修正）。

---

## 1. 現況與阻擋點（2026-07-26 實測，容器內，協調者提供並由我核對邏輯一致）

| 檢查項目 | 結果 | 判讀 |
| --- | --- | --- |
| `which codex` | 找不到 | 系統未預裝 Codex CLI 正式版 |
| `npx --yes @openai/codex` | 可下載並執行，版本 `codex-cli 0.145.0` | CLI 本體可透過 npm registry 取得，**不是**被擋的部分 |
| `codex login status` | `Not logged in` | 缺登入態，不論走哪條認證路徑都要先補 |
| `OPENAI_API_KEY` / `CODEX_*` 環境變數 | 不存在 | 沒有設定 API key 這條路徑的憑證 |
| `curl https://api.openai.com/v1/models` | `CONNECT tunnel failed, response 403`（經 `$HTTPS_PROXY`） | **被 agent proxy 的網路政策擋掉**，不是 DNS 或憑證問題 |
| `curl https://auth.openai.com` | 同上，403 | OAuth 登入所需網域也被擋 |
| `curl https://chatgpt.com` | 同上，403 | ChatGPT 帳號登入所需網域也被擋 |

我在本次任務中額外核對的事實（2026-07-27，唯讀動作，未安裝/未修改任何設定）：

- `which codex` 目前仍找不到；`/root/.codex/` 目錄存在但只有空的 `tmp/arg0/` 子目錄，**沒有 `auth.json` 或任何憑證檔**，與「Not logged in」的結論一致。
- 檢查 npm 全域安裝清單（`npm ls -g`）：沒有 `@openai/codex` 或 `codex` 套件，確認目前是「即用即丟」透過 `npx` 下載執行，並非常駐安裝。
- `.claude/commands/review.md` 內註明「指令語法已對 **codex-cli 0.142.3** 驗證」，與實測下載到的 `0.145.0` 版本不同。這不影響本文件的網路/憑證判讀，但提醒：日後放行後，第一次跑 `/review` 時應留意 `codex exec` 子指令與 `--sandbox read-only` 參數在新版是否仍相容（**待查證**，若不相容需請 dev-lead / qa-automation 更新 `.claude/commands/review.md`，不在本文件處理範圍）。

**結論**：CLI 本體「拿得到」，卡點是兩個獨立問題——(1) 網路政策擋住所有 OpenAI 相關網域的對外連線、(2) 沒有任何形式的認證憑證。兩者都要解才能用。

---

## 2. 兩條認證路徑的比較與取捨

### (a) ChatGPT 帳號登入（可用 CEO 的 Pro 訂閱）

- Codex CLI 官方支援 `codex login` 走瀏覽器 OAuth 流程，登入後可用訂閱額度（非另計 API 費用）。
- **問題**：本環境是無頭（headless）容器，沒有瀏覽器，OAuth 流程通常需要開啟瀏覽器並回呼 `localhost` 某個 port 完成授權。在這種容器裡直接執行 `codex login` **預期會卡住或失敗**（**待查證**——需要放行網路後實際跑一次 `codex login`，觀察它是否有提供「印出 URL、在其他裝置完成授權」的無頭替代流程；目前沒有查到官方文件佐證，不確定 Codex CLI 是否支援 device-code 式的無頭登入）。
- **替代作法（可能可行，但兩點都待查證）**：
  1. CEO 在自己本機（有瀏覽器的環境）用 `codex login` 完成 ChatGPT 帳號登入，取得本機的憑證檔，再把該檔案搬到本容器對應路徑。
     - **憑證實際存放路徑：待查證**。我在本容器內找到的是 `/root/.codex/`（環境變數 `CODEX_HOME` 若設定會覆蓋，預設應為 `~/.codex`），但因為目前未登入，這個目錄裡沒有任何憑證檔可供比對，無法確認登入後會產生的檔名（例如是否為 `auth.json`）與內容格式。要查證需：CEO 在本機登入一次 Codex CLI 後，執行 `find ~/.codex -maxdepth 2` 回報實際檔案清單。
     - 憑證檔是否可攜（搬到別的機器 / 容器後是否仍有效，例如是否綁定裝置指紋或有效期限）：**待查證**，需查 Codex CLI 官方文件或直接測試。
  2. 若憑證不可攜，退回選項 (b)。
- 額外前提：即使搬移憑證可行，仍需要網路政策放行 `api.openai.com`（Codex CLI 執行期會呼叫 API，不是只有登入當下需要網路）。

### (b) `OPENAI_API_KEY` 環境變數

- 最直接：在 `.env`（已被 `.gitignore` 排除）或環境變數設定 `OPENAI_API_KEY`，Codex CLI 會自動讀取。
- **重要提醒（CEO 決策用）**：這與 ChatGPT Pro 訂閱是**分開計費**的兩個東西。ChatGPT Pro 是聊天介面的訂閱方案，**不含** OpenAI API 用量額度；要用 API key 這條路，需要另外在 OpenAI Platform（platform.openai.com）開通 API 帳戶並綁定付費方式，依 token 用量計費。CEO 若只有 ChatGPT Pro、沒有另外開 API 帳戶，這條路目前不可用，需先決定是否要另外付費（依「部署平台需要付費方案 → 列選項與成本升級 CEO」的守則，此事應由我明確告知，實際費率因非本次查證範圍，若要精算需另外查證 OpenAI 官方定價頁）。
- 優點：不受無頭容器限制，設定完就能跑，不涉及瀏覽器 OAuth。

### 建議

若 CEO 已有 OpenAI API 帳戶（獨立於 ChatGPT Pro），走 (b) 最簡單可靠。若沒有且不想另外付費，才值得花時間查證 (a) 的憑證可攜性；但 (a) 目前有兩個未查證的不確定性（無頭登入是否可行、憑證是否可攜），存在「查完才發現不可行」的風險。

---

## 3. 需要 CEO 執行的動作清單

### 3.1 網路政策放行（不論選哪條認證路徑都需要）

請放行以下網域的對外連線（透過 agent proxy）：

- `api.openai.com` — Codex CLI 執行期呼叫的主要 API 網域（已於本次診斷確認會被連線，403 tunnel failed）。
- `auth.openai.com` — OAuth 登入流程用（若選路徑 (a) 或未來需要重新登入）。
- `chatgpt.com` — 診斷時也回報被擋，Codex CLI 是否直接連此網域待查證，但既然已知會被 proxy 擋下且與 OpenAI 帳號體系相關，建議一併放行以免中途卡關。
- **待查證**：Codex CLI 是否還會連線到其他輔助網域（例如遙測、更新檢查、CDN 下載 npm 套件本體用的 `registry.npmjs.org` — 這個從實測結果看目前是通的，因為 `npx --yes @openai/codex` 已能下載成功，故不需額外放行）。若放行上述三個網域後執行仍出現 403，請把錯誤訊息中的目標網域回報給我，我再補查證並更新本清單。

### 3.2 憑證存放（對照 repo 既有慣例）

repo 的 `.gitignore` 已經涵蓋：`.env`、`.env.*`（但保留 `.env.example`）、`*.key`、`*.pem`、`secrets.*`、`credentials.*`，以及專門排除 `.codex/`（註記「Codex CLI 本地設定與快取，可能含 token」，代表這件事在設計 repo 時就已經預期過）。

- 若走路徑 (b)：在容器的 `.env`（repo 根目錄，已被 `.gitignore` 排除）新增一行：
  ```
  OPENAI_API_KEY=<CEO 自行貼上的 key，絕不透過我或任何 agent 輸入>
  ```
  並在 `.env.example` 補一行假值 `OPENAI_API_KEY=sk-xxx-placeholder`（純文件用途，不含真實憑證）。**這兩個檔案的實際編輯本身也算「動設定檔」，不在本次文件任務範圍內，待放行後另開任務執行。**
- 若走路徑 (a)：憑證會落在 `~/.codex/`（依 `.gitignore` 的 `.codex/` 規則，已預先排除在 git 追蹤外，不需額外處理 `.gitignore`）。CEO 手動搬移憑證檔時，請直接用安全通道（例如自己在容器內操作，或透過受信任的檔案傳輸），**不要**把憑證內容貼進聊天訊息或任何會被記錄 / 送給任何 agent 的管道。
- 兩條路徑都一樣：**任何 token / API key 不得由我（devops-sre）或其他 agent 讀取、複製、貼到檔案或訊息中**；這是 CLAUDE.md 第 4 條與我角色卡紅線的雙重要求，CEO 需自行完成憑證設定與貼入這一步。

### 3.3 若選 (a) 路徑，額外需要

1. CEO 在有瀏覽器的本機環境安裝 Codex CLI（`npm install -g @openai/codex` 或依官方文件）並執行 `codex login`，完成 ChatGPT 帳號授權。
2. 回報 `find ~/.codex -maxdepth 2` 的輸出（檔名即可，不要貼檔案內容），讓我確認憑證檔案位置與結構，以更新本文件的「待查證」項目。
3. 確認憑證檔是否含有機器綁定資訊（**待查證**：可能需要查 Codex CLI 原始碼或官方 issue，或直接實測搬移後在容器內跑 `codex login status` 看是否仍顯示已登入）。
4. 若可攜，把該檔案（或整個 `~/.codex/` 目錄）安全搬移到本容器的對應路徑（預設 `~/.codex/`，若容器內有設定 `CODEX_HOME` 環境變數則以該路徑為準——**待查證**：本容器目前未設定 `CODEX_HOME`）。

---

## 4. 放行後的驗證步驟（依序執行，每步附預期輸出）

以下假設網路政策已放行、憑證已設定完成（走 (a) 或 (b) 其中一條）。

1. **確認 CLI 可執行**
   ```bash
   npx --yes @openai/codex --version
   ```
   預期輸出：類似 `codex-cli 0.145.0`（或更新版本號）的版本字串，指令成功結束（exit code 0）。

2. **確認登入 / 認證狀態**
   ```bash
   npx --yes @openai/codex login status
   ```
   - 走路徑 (a)：預期輸出顯示已登入的帳號資訊（非 `Not logged in`）。
   - 走路徑 (b)：**待查證** — 用 API key 時 `login status` 的回報方式可能與 OAuth 登入不同（例如顯示「using API key」或不適用此指令）；需要實測後補上實際文字，不要事先假設。

3. **確認可連線到 API（不涉及送出程式碼，純連線測試）**
   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"
   ```
   - 若走 (b)：預期 HTTP 狀態碼 `200`（key 有效且額度未耗盡）。
   - 若走 (a)：此指令不適用（OAuth 模式不是用這個 header），改用第 2 步的 `login status` 或直接跳到第 4 步做端對端測試。
   - 若仍回 `403` 且訊息含 `CONNECT tunnel failed`：代表網路政策放行未生效或放行網域不完整，回到 3.1 檢查。

4. **端對端測試：對一個小 diff 實跑 `/review`**
   - 找一個小改動製造 staged diff（例如在 `work/` 底下新增一行測試用文字檔，`git add` 但不 commit）。
   - 依 `.claude/commands/review.md` 的步驟，執行：
     ```bash
     git --no-pager diff --staged --stat
     codex exec --sandbox read-only "你是資深 code reviewer...(完整 prompt 見 .claude/commands/review.md)"
     ```
   - 預期輸出：結構化文字，依序包含 `## Summary`、`## 各檔問題`、`## Verdict`（`PASS` 或 `NEEDS_CHANGES`），最後一行為 `BLOCKING_ISSUES=true` 或 `BLOCKING_ISSUES=false`。
   - 若指令噴出「unknown subcommand」或參數錯誤：代表安裝到的版本與 `.claude/commands/review.md` 註明的 `0.142.3` 語法不相容，需要另外請 dev-lead 更新該檔案，不屬於本次網路/憑證問題。
   - 測試完成後，把用於測試的暫存檔從 staged 區移除（`git restore --staged <file>` 並刪除檔案），不要留下測試殘留。

5. **確認 qa-reviewer 流程接得上**
   - 找 qa-reviewer 針對同一個 diff 走一次完整 `code-review-checklist` 流程，確認「第二意見（Codex）」欄位能真的填入第 4 步的輸出，而不是「無法執行」的註記。

---

## 5. 安全守則（對照 CLAUDE.md 第 4 條）

- 祕密只能來自環境變數或 `.env`（`.env` 已被 `.gitignore` 排除，`.env.example` 只放假值）——本文件第 3.2 節已依此設計。
- 新增 / 修改任何設定檔（`.env`、`.env.example`、`.claude/commands/review.md` 等）需交 qa-reviewer 審查後才 commit；本文件本身是純文件任務，不涉及設定變更，故不需經此流程，但後續實際落地憑證設定時要走。
- **額外提醒（CEO 需知情）**：`/review` 的運作方式是把 **staged diff 的實際程式碼內容**傳送給 OpenAI 的 Codex API 處理。這代表只要啟用這條流程，公司的程式碼就會外傳給第三方廠商（OpenAI）。目前 repo 若維持 public 狀態，這件事的邊際風險較低（程式碼本來就公開）；但 CLAUDE.md 提到「repo 若可能設為 public，提交前確認無敏感檔案被追蹤」，隱含反向情境——**若日後 repo 轉為 private 且內含敏感商業邏輯 / 客戶資料 / 未公開演算法，啟用 Codex 第二意見前，需要重新評估「程式碼外傳給 OpenAI」這件事本身是否可接受**，這屬於 risk-compliance-officer / CEO 的決策範圍，不是我能自行拍板的事，僅在此提醒。

---

## 6. 失敗時的降級（若最終無法接入）

現行作法（已在 stock-desk Phase 5、6、7 實際發生）：

- qa-reviewer 獨立完成審查，Codex 第二意見欄位如實註記「無法執行，原因：〔網路政策阻擋 / 無認證憑證〕」。
- 依 `code-review-checklist` 第 3 步的既有規則，這屬於允許的例外處理方式（無法執行時註明原因，不當作通過條件跳過），流程本身沒有違規。

風險：

- 少了跨廠商第二意見這道防線，代表所有 code review 的判斷完全依賴單一廠商（Anthropic / Claude）模型的視角，CLAUDE.md 第 2 條設計這條規則的初衷（抓出 Claude 自己看不到的盲點）沒有被落實。
- 長期缺席若沒有被追蹤與定期覆盤，容易變成「日常慣例」而非「已知缺口」，建議每次 qa-reviewer 報告都持續如實註記，並由 CEO 決定何時要真的排時間解決本文件列出的待辦，而不是無限期擱置。
