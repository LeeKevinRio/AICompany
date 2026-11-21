# 下游分支同步 CG-2 新 head 交件

- 審查者：dev-lead
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

四支分支只同步了兩支，另外兩支因衝突停下，等 tech-architect 裁示。

- **已同步並推送**（`--no-ff` merge，fast-forward push，沒有 rebase、amend 或 force push）：
  - `feat/nm5-wiring`：`2a48af3e0890433531cd51e1a76af1baa69b4248` → **`526201cad04aafa446f38d763b9aabde5411d8d8`**
  - `test/f2-short-window-carryover`：`7f2f8cd30e442e6299b4ce93f8ce0ebdd3c6d9ff` → **`05534b6f92dc82ac36494bac6ea12dbc79400273`**
  - 推送後用 `git ls-remote` 確認遠端就是這兩個值。
- **停下、沒有推送**（遠端維持原值）：
  - `chore/nm5-cg2-oneclick-retire` 仍是 `c559b4afacf8ee6336dd8ffa2a9737a3d4e31749`。
  - `chore/pipeline-acceptance-retire` 仍是 `d01e068e973cdbbb17a06122a8654fb660e5f6d2`。
  - 兩支都在 merge `cc9e302` 時出現 modify/delete 衝突，衝突檔包含 `scripts/cg2_register.py` 和三支 cg2 測試，屬於派工所說「不得自行解決」的範圍。
- **接線版新 `code_digest`**：`32725eb871c9bd5ae12126d5c3f6f506316684b04070664fa9644b2958d7b3c6`。分支 3 和分支 4 的新 head 算出相同的值。舊值 `731e09f4…0c2b` 自此作廢。
- **另有一個問題要 tech-architect 一併裁示**：上游新加進 `app/forecast/claims.py:293` 的註解寫著 `scripts/cg2_register.py`。退役分支的守門測試 `test_no_tracked_file_refers_to_a_retired_file` 會掃到這行。所以就算衝突照退役分支的意思處理（保留刪除），合併後這條守門測試預期還是會紅（靜態推論，沒有實跑）。

## 各部門回報

**dev-lead**

1. **前置確認**
   - 四支的實際 head 與派工預期逐一相同。
   - 四支都含舊 head `9d5bbf48`（`merge-base --is-ancestor` 為 yes）。
   - 分支 2 疊在 1 上、分支 4 疊在 3 上，都確認過。
   - `9d5bbf48..cc9e302` 共 6 個檔，+94／−8。

2. **分支 1 和 2 的衝突（停下，交 tech-architect）**
   - 分支 1 的 `72e0ed0` 刪了 CG-2 一鍵檔與專屬測試，上游 `cc9e302` 又修改了其中 4 個檔，因此出現 modify/delete 衝突：
     - `apps/stock-desk/backend/scripts/cg2_register.py`：上游有三段 hunk：
       - `ENV_KEY_PATTERN` 改為 `^\s*(?:export\s+)?STOCK_DESK_DB_PATH\s*=` 加 `re.IGNORECASE`
       - `app_tree_id` 由 `9c157d86…` 改為 `d631a75a4aba2ace76c44e8647d1bd11180662d5`
       - `review_refs` 加兩條 11-21 紀錄
     - `tests/test_cg2_register_addendum3.py:101`：tree id 期望值改成 `d631a75a…`。
     - `tests/test_cg2_register_flow.py`：+47 行，是 export／大小寫的正反例，以及 `test_r3_the_key_pattern_is_the_one_of_the_claims_module`（兩處 pattern 的相等斷言）。
     - `tests/test_cg2_register_values.py`：`review_refs` 期望值加兩條。
   - 另外兩個檔沒有衝突，可以自動合併：`app/forecast/claims.py` 和 `tests/test_forecast_claims_bootstrap.py`。
   - 分支 2 用 `git merge-tree --write-tree` 試算過，衝突與分支 1 完全相同（同樣 4 個檔，都是 modify/delete）。
   - 兩支都已 `git merge --abort`，工作樹乾淨，沒有留下 merge commit。

3. **給 tech-architect 的連帶事實**
   - 退役分支的守門 regex 是 `cg2_register(?!s)|cg2-register|cg2-preflight|verify_cg2_instruction`，掃的是 `apps/stock-desk` 底下 git 追蹤的所有檔，只排除守門測試自己。
   - 上游 `claims.py:293` 新增了這行註解：`#: flags equal ``ENV_KEY_PATTERN`` of ``scripts/cg2_register.py`` (a test keeps them equal).`
   - 我在 `cc9e302` 的 `app/` 用同一個 regex 做 `git grep -P`，只命中這一行；在 `9d5bbf48` 上沒有命中。
   - 因此不論衝突怎麼解，退役分支合併後都會有兩件事：
     - 守門測試預期失敗。
     - 那段註解所說的「相等斷言」連同 `test_cg2_register_flow.py` 一起被刪掉，註解本身也就過時了。
   - 如果改 `claims.py` 的註解，`app/` tree id 和 `code_digest` 都會再變（`code_digest` 涵蓋 `app/forecast`，只把行尾正規化，註解有變就會改值）。如果改守門測試，就是退役範圍的事。兩條路都需要裁示。
   - 同樣的問題也會出現在接線分支日後與退役分支在 product 上會合的時候。

4. **失效的常數與引用清單**
   - **程式與測試**（在分支 3／4 新 head 上 `git grep`）：
     - 釘 tree id 的只有 `scripts/cg2_register.py:176` 和 `tests/test_cg2_register_addendum3.py:101`。兩處的值都是 `d631a75a4aba2ace76c44e8647d1bd11180662d5`，隨上游一起進來，與 CG-2 一致。
     - 但接線分支本身的 `app/` tree id 是 `4dc141b2fbe709e23ea1e5046a8b6867457b7b13`（合併前是 `db8c60f40dcadc6abffc287af5ad4834f60f61e6`），本來就不等於這個 pin，所以 R-1 測試照舊會紅，見「驗證」。
     - 程式與測試裡沒有任何地方釘 `731e09f4…`、`9c157d86…`、`3f7366ad…` 或 `fc94ada3…`。
     - 退役鏈末端 `d01e068` 的 `apps/` 也沒有釘任何 tree id 或 digest。
   - **文件引用中因這次同步而失效的**（我沒改，交 tech-architect／coordinator）：
     - `work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md:155`：「接線版 `code_digest`（第五輪起）：`731e09f425317a468dac98b099985766b451d5a987b03db45fbb1868bb610c2b`」，已失效，新值是 `32725eb8…b3c6`。
   - **歷史紀錄**：下列文件提到 `9c157d86…`，它們描述的是當時的狀態，我沒有改，是否要加註由 coordinator 決定：
     - `work/reviews/2026-11-20-登記一鍵檔退役PR預先實作交件-dev-lead.md:12,92`
     - `work/reviews/2026-11-20-R2測試偶發失敗修正合併紀錄-devops-sre.md:41,80`（寫著「合併後 tree id 預期是 `9c157d86…`」，這個預期已被 `d631a75a…` 取代）
     - `work/reviews/2026-11-19-缺日靜默丟列與登記先後裁示-tech-architect.md:34`
     - `work/reviews/2026-11-19-接線PR預先實作交件-dev-lead.md:79`
     - 11-17 的多份 CG-2 紀錄
     - 追蹤清單中有 7 處

5. **我做了判斷的地方**
   - 退役鏈停下後，我仍然繼續處理接線鏈（3、4）。理由是兩條鏈互不相依，接線鏈合併沒有衝突，派工的「有衝突就停」我理解為停在發生衝突的那條鏈。如果你的原意是四支全停，要退回只能用新的 revert commit 或由你決定，因為我不 force push。
   - 我沒有在本地建立與遠端同名的分支。分別用 `wip/sync-oneclick-retire`、`wip/sync-nm5-wiring`、`wip/sync-f2-carryover` 合併，再用 `<sha>:refs/heads/<同名>` 推送。本地這三支沒有刪，工作樹目前停在 `wip/sync-oneclick-retire`（`c559b4af`），狀態乾淨。
   - pytest 我多加了 `-p no:cacheprovider`，避免在 repo 裡寫 `.pytest_cache`。這是與 CI 指令唯一的差異。
   - 揭露一件事：我曾想在分支 1 上做一次不 commit 的試解（`git rm` 那 4 個檔），用來實跑守門測試，但這個動作被權限系統拒絕。之後立即 `merge --abort`，沒有任何 commit 或推送。守門測試會失敗這一點，因此只是靜態推論。

## 驗證

**分支 3 `feat/nm5-wiring`**
- head：`2a48af3e0890433531cd51e1a76af1baa69b4248` → `526201cad04aafa446f38d763b9aabde5411d8d8`
- parents：`2a48af3e…`、`cc9e3023…`
- commit 訊息與派工指定的一字不差，含兩行 trailer。
- `git diff 2a48af3 526201c --stat`：6 個檔，+94／−8，與 `9d5bbf48..cc9e302` 相同：
  - `claims.py` 5
  - `cg2_register.py` 11
  - `test_cg2_register_addendum3.py` 2
  - `test_cg2_register_flow.py` 47
  - `test_cg2_register_values.py` 2
  - `test_forecast_claims_bootstrap.py` 35
- 檢查結果：
  - `uv sync --frozen` OK
  - `ruff check .`：All checks passed
  - `ruff format --check .`：568 files already formatted
  - `mypy app tests`：no issues in 554 source files
- 子集 `pytest tests/test_cg2_*.py tests/test_forecast_*.py`：**2 failed、2804 passed**（子集不設覆蓋率門檻）。失敗的兩支與分支 4 相同，見下。

**分支 4 `test/f2-short-window-carryover`**
- head：`7f2f8cd30e442e6299b4ce93f8ce0ebdd3c6d9ff` → `05534b6f92dc82ac36494bac6ea12dbc79400273`
- parents：`7f2f8cd3…`、`526201ca…`
- `git diff 7f2f8cd 05534b6 --stat`：同樣是上面那 6 個檔，+94／−8。
- 檢查結果：
  - `ruff check .`：All checks passed
  - `ruff format --check .`：569 files already formatted
  - `mypy app tests`：no issues in 555 source files
- 全套 `pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：**2 failed、13491 passed、2 xfailed**，覆蓋率 **97.83%**（門檻已達），耗時 42 分 35 秒。
- 兩支失敗：
  1. `test_cg2_register_values.py::test_the_review_refs_all_exist_at_head`：缺 2 份 11-21 紀錄（`…M9補充核對M2M3M6-風控.md`、`…M9補充最終審查-qa.md`）。這是**預期的失敗**（原設計）。11-17 的兩份因為接線分支先前 merge 過 product，已經存在，所以只缺 2 份，不是 4 份。
  2. `test_cg2_register_values.py::test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout`：`4dc141b2…` ≠ `d631a75a…`。這是**接線分支既有的失敗**：接線改了 `app/`，tree id 本來就不等於 CG-2 的 pin。11-19 接線預先實作交件（同檔第 78 行）已記載這支「正是派工預告的那一支」，這次只是比對對象從 `9c157d86…` 換成 `d631a75a…`。我沒有 skip 或 xfail，也沒有改 pin。
- 全套輸出存在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/pytest-b4.log`；分支 3 子集的輸出在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/pytest-b3.log`。

**`code_digest`**
- 做法：用 `git archive <commit> apps/stock-desk/backend/app` 解到 scratchpad 的乾淨樹，再用 backend venv 的 python（加 `-I -B`）呼叫 `app.forecast.canonical.code_digest(app_root)`。腳本在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/sync-scripts/digest.py`。
- 結果：
  - 舊接線 `2a48af3`：`731e09f425317a468dac98b099985766b451d5a987b03db45fbb1868bb610c2b`，與紀錄相符，方法對得上。
  - CG-2 `cc9e302`：`fc94ada3612688221b816d02118fb0f35f5c649dda45bfbff03dc7bde5981538`，與我上一份交件相符。
  - **新接線 `526201c`：`32725eb871c9bd5ae12126d5c3f6f506316684b04070664fa9644b2958d7b3c6`**
  - **新分支 4 `05534b6`：`32725eb871c9bd5ae12126d5c3f6f506316684b04070664fa9644b2958d7b3c6`**，與分支 3 相同，因為分支 4 只多一支測試檔。

**分支 1 和 2**：沒有產生合併結果，所以沒有可跑的測試。

**沒有查證的事**
- 環境差異：venv 由 uv 選了 Python **3.13**，CI 用的是 3.12，我沒有另跑 3.12。
- 退役分支合併後守門測試會紅，只是靜態推論（regex 對 `claims.py:293` 會命中），沒有實跑。
- 沒有對新的接線 head 跑 `verify_cg2_instruction.py`。
- `.github/workflows` 的 compose 與 frontend 兩個 job 沒有跑，這次也沒有改到它們的路徑。

**守則**
- 測試只用 pytest 的 `tmp_path`。
- 沒有碰 `data/`，沒有讀任何 `.env*`，沒有執行 `.bat`。
- 沒有碰 `product/stock-desk`，沒有開 PR。
- repo 內容沒有寫入 model ID。

## 下一步

1. **tech-architect 裁示退役鏈（分支 1、2）**：
   - (a) 4 個 modify/delete 衝突怎麼解。照退役原意是保留刪除，但上游對 `cg2_register.py` 和三支測試的修正就會隨之消失。
   - (b) `claims.py:293` 註解提到 `scripts/cg2_register.py`，會觸發退役守門測試。要改註解，還是調整守門測試的範圍？改註解會讓 `app/` tree id 和 `code_digest` 再變一次，還會牽動 CG-2 已完成的 M-9。
   - 裁示後由我依指示重做這兩支的 merge 與驗證。
2. **coordinator**：
   - 在追蹤清單作廢 `731e09f4…0c2b`，記下新值 `32725eb8…b3c6`（分支 3、4 相同）。
   - 記下分支 3／4 的新 head 與新的 `app/` tree id `4dc141b2…7b13`。
   - 決定 `work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md:155` 由誰更新。
   - F10 紀錄的分支 head 要重做。
3. **確認一件事**：如果接線鏈不應該在退役鏈停下時單獨推送，請告訴我。我不會 force push，退回需要另外決定做法。
4. 這次只有 merge commit、沒有新的程式碼，是否要送 qa-reviewer 審查，請你決定。
