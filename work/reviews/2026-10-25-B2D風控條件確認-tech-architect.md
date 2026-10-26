# ADR-0027 B2D 批風控附條件 R-1～R-7 確認

- 審查者：tech-architect
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 B2D 批風控附條件（R-1～R-7、S-3）確認

- 審查者：tech-architect
- 日期：2026-10-25

## 本次結論

R-1～R-7 我全部接受，沒有否決任何一項。其中 R-1、R-2、R-3、R-5、R-6、R-7 改寫後接受，R-4 照原文接受。改寫只是讓字面在架構上可以落地、可以檢查，沒有任何一項比風控原案寬。S-3 我也同意，但把主詞從「系統」縮成「recorder」，因為 ADR 的事實依據只涵蓋 recorder。

修訂紀錄的處理：**併入現有的 L5791～5822 同一段，不另開新段。** 理由有三：
- R-1～R-7 是這一批的核可條件，L5822 本來就把風控確認寫成落檔後的閘門。
- R-2、R-4 改的是本批自己新增、還沒 commit 的字面。另開一段的話，會變成記錄一段從沒 commit 過的原文被取代。
- 段內已規定「本段與正文各項同一個 commit」。

改寫的重點有六個：
1. **R-1**：在 FL-56 補「之後版本的值不小於凍結值」的測試格，這樣「比照 FL-31」才真的有東西可以檢查。另外寫明下限是在 `app/dirdef/` 內寫死的字面值，不 import `app.sectors`（FL-78 (a)）。
2. **R-2**：
   - L260 是表格列，`|S_T|` 必須寫成 `\|S_T\|`，否則表格會壞。
   - old 要連「；兩者都是…」一起換掉。插入長句之後「兩者」離它指的對象太遠，會指涉不清。
   - FL-56 加一個 AST 絆線：不得對 `BASKET_MIN_MEMBER_WEIGHT` 做減法。
3. **R-3**：位置從 L2448 移到 L2451。L2451 是「由 qa 核對」那一點，和 R-3 的內容一致。另外「必須經 `f2_variant` 表達」放寬成「經 `f2_variant` 或其他 dirdef 常數表達」：`f2_variant` 只有兩個值，更嚴的 C-8 調整可能要用別的常數。這和 FL-37、照實並陳 B2D-1 的後半句一致。
4. **R-5**：照風控原句寫，會出現死路：只改 `name` 時，舊 claim 會被 D-10 第 2 點的寫入檢查拒絕，又不能登記新 claim。所以我把結論明寫成「不得單獨改名」，這比原案更嚴。
5. **R-6**：「依據」改成可以檢查的形式，也就是要附讀取點清單。
6. **R-7**：
   - 照風控要求，改 L5795、L5803、L5818 三處。
   - 加改 L5798：那裡的「已登記版本的任何欄位不得原地修改」和 R-4 指出的誇大說法相同，不改的話修訂紀錄會和正文不一致。
   - 加補 L5800、L5805 的「無被取代原文」說明，以及 L5822 的閘門。

## 各部門回報

### tech-architect

#### A. 逐項裁定

| 項 | 裁定 | 架構面理由 |
|---|---|---|
| R-1 | **改寫後接受** | 型別約束 `Field(ge=0.9, le=1)` 可以做到，寫法和 `CoverageRules.__post_init__` 的 `floor <= value <= 1.0` 同型。和 FL-31 一致：FL-31 是越小越嚴，這裡是越大越嚴，兩者都是「只能收緊」。改寫三點：(1) FL-56 補「已登記各版不小於凍結值」的測試格，否則「比照 FL-31（測試釘住）」沒有東西可查；(2) 寫明下限在 `app/dirdef/` 內寫死、不 import `app.sectors`，否則實作可能為了「比照」去 import `CoverageRules`，違反 FL-78 (a)；(3) FL-56 的通過值寫 `1.0`，不寫 `1`。理由是模型是 `strict=True`，用 float 字面值可以避開 int 轉 float 的爭議，現有測試 `test_dirdef_definition.py:325` 也用 `1.0`。 |
| R-2 | **改寫後接受** | 判定改成直接比較保留權重，和現行實作 `basket.py:97-99`（`_weight_below`）一致。浮點論證成立：兩個整數相除，經 IEEE 正確捨入，若精確值等於十進位常數，結果就等於該常數的字面值。改寫：(1) 表格列內的 `|S_T|` 要跳脫；(2) old 要涵蓋「；兩者都是沒有預設值的關鍵字參數。」，新字改用具名寫法；(3) FL-56 加 AST 絆線，`app/` 內不得以 `BASKET_MIN_MEMBER_WEIGHT` 屬性為運算元做減法。這是為了還沒實作的結算端。用別名可以繞過，那部分由 code review 把關，字面上也照實寫了。 |
| R-3 | **改寫後接受** | 內容講的是 qa 核對與 CI，放在 L2451（「由 qa 核對」）比放在 L2448（欄位定義）連貫。「必須經 `f2_variant` 表達」改成「經 `f2_variant` 或其他 dirdef 常數表達」：`f2_variant` 是 `Literal["F2-A","F2-B"]`，往更嚴方向的 C-8 調整未必能用這兩個值表達。這和 FL-37「以常數登記在 dirdef 內」、照實並陳 B2D-1「要生效就必須另以常數表達」一致。D-12 共同部分 (vii) 的引用正確（L2344）。 |
| R-4 | **接受** | 事實正確：D-10 第 3 點的欄位清單（L1624）沒有 `definition_sha256`。同時改物件與登記雜湊時，執行期查不到。照實並陳我加了兩處：(1) 補〔事實〕出處；(2) 「該版已有 claim 時」的限定，因為 claim 還沒登記之前，D-10 第 2 點的寫入檢查沒有比對對象。S-1 我承接成追蹤項。 |
| R-5 | **改寫後接受** | 照原句寫會有死路：`name` 在 logic 雜湊範圍內時，只改 `name` 會讓 logic 雜湊不同，D-10 第 2 點的寫入檢查拒絕沿用舊 claim；R-5 又禁止登記新 claim。所以把結論明寫為「不得單獨改名」，這比原案嚴。qa 可以在 PR 中逐條檢查。 |
| R-6 | **改寫後接受** | 指涉改成可定位的寫法：「本點 `rules_logic_sha256` 一句的…」與「本句的…」，不用行號。「依據」具體化成 `app/` 內的讀取點清單，讀取點只限雜湊、登記、禁詞掃描與文字呈現，qa 可以用 grep 或 AST 核對。 |
| R-7 | **改寫後接受** | 三處照辦。另外加改 L5798（和 R-4 同一個誇大說法）、L5800 與 L5805 之後補「無被取代原文」說明、L5822 的閘門補上附條件的處理方式。 |
| S-3 | **改寫後同意** | L2445「不讀決策檔」與 L2450「不讀 `docs/`、`work/`」只約束 recorder，所以主詞改成 recorder，標〔事實〕。「系統」整體不讀決策檔，ADR 沒有字面依據，不能標為事實。 |
| S-1 | 接受，列追蹤 | tech-architect 負責，評估在 claim 登記或每筆紀錄存入 `definition_sha256`。 |
| S-2 | 知悉，轉 quant | 這是事先宣告既有的問題，不在本批改字範圍。 |

#### B. 方案比較（R-5 有兩種寫法，所以這裡列出）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 甲：照風控原句 | 字少 | 「只改 `name`」的後果沒寫清楚，日後可能有人讀成可以沿用舊 claim | 中（寫入檢查會拒絕，但會在執行期才爆） |
| **乙：明寫「不得單獨改名」（採用）** | 和 D-10 第 2 點一致，qa 可以直接檢查 | 改名只能等 quant 凍結時把 `name` 列為字面鍵，或隨實質變更一起改 | 低 |
| 丙：現在就把 `name` 移出雜湊 | 沒有死路 | 搶了 quant 凍結時的決定權（T-2） | 越權，否決 |

#### C. 交 tech-writer 的字面清單

**套用順序與共同規則**
- 先改正文（1～7），再改修訂紀錄段（8～15），修訂紀錄最後改。
- 下列每個 old 和錨點，我都用 Grep `-o` 在現行檔確認過恰好出現 1 次，而且都沒有落在修訂紀錄段引用的被取代原文裡。
- 各 old 和錨點彼此不重疊。第 8 項的 old 包含風控 R-7 原本指定的短字串「風控：B2D-1 輕量確認，其餘知悉」，兩者合成一次替換。
- 新增的標記「風控條件」目前在檔內出現 0 次。
- 第 1、2、3、11 項是表格列或含跳脫字元的字面，`\|` 必須逐字照抄。

**1. R-1　L260（D-1 `basket.py` 列）　接字**
- 錨點：`「不是新值」）；`
- 接在錨點之後：
```text
（B2D-3，風控條件）`BASKET_MIN_MEMBER_WEIGHT` 的型別範圍是 [0.90, 1]，下限比照 `CoverageRules.sector_coverage_threshold` 的「只能收緊」下限，在 `app/dirdef/` 內以字面值寫出、不 import `app.sectors`（FL-78 (a)）；之後版本的值只能大於或等於凍結值（比照 FL-31，測試釘住）；放寬下限須修訂本列，並經風控與 CEO 明確同意；
```

**2. R-2　L260（同列）　old→new**
- old：`10% 是 1 減該值；兩者都是沒有預設值的關鍵字參數。`
- new：
```text
（B2D-3，風控條件）「被排除的權重 > 10%」一律以等價的「保留成員的權重（保留成員數 ÷ \|S_T\|）< `BASKET_MIN_MEMBER_WEIGHT`」判定，以浮點除法的商直接與該常數比較，不先算 1 減該值（`1 - 0.9` 的浮點值小於 0.1，會把恰好 10% 的排除誤判為超過）；事先宣告 §1.2 籃子結算的「≤ 10%」同此，保留權重 ≥ 該值即通過；`coverage_unknown`、`definition` 都是沒有預設值的關鍵字參數。
```

**3. R-2　L3306（FL-56 末條）　old→new**
- old：`` 10%／11%／20% 的格以 `BASKET_MIN_MEMBER_WEIGHT = 0.9` 的 fixture 定義物件驅動； ``
- new：
```text
以 `BASKET_MIN_MEMBER_WEIGHT = 0.9` 的 fixture 定義物件驅動：10% 的格（10 檔排除 1 檔）→ 不輸出 `E-ADJ-COVERAGE`，11%、20% 的格 → 輸出（B2D-3，風控條件）；`app/` 內沒有以 `BASKET_MIN_MEMBER_WEIGHT` 屬性為運算元的減法（AST 絆線；經別名的繞法由 code review 把關）；
```

**4. R-1　L3306（同條）　接字**
- 錨點：`` `coverage_unknown` 含非成員 → `ValueError`； ``
- 接在錨點之後：
```text
（B2D-3，風控條件）`BASKET_MIN_MEMBER_WEIGHT` 為 0.8999 → 型別驗證拒絕，為 0.90 與 1.0 → 通過；依版本號（MAJOR、MINOR 以數值）排序，已登記各版的 `BASKET_MIN_MEMBER_WEIGHT` 都大於或等於凍結值（第一個登記版本的值），登記表為空時照跑；
```

**5. R-5　L1618（D-10 第 1 點 `rules_logic_sha256`）句末接字**
- 錨點：`是否列為字面鍵由 quant 凍結時依前句決定。`
- 接在錨點之後：
```text
（B2D-1，風控條件）`name` 列在範圍內期間，只改 `name` 的變更會使 `rules_logic_sha256` 不同，所以不能沿用原 claim（第 2 點的寫入檢查拒絕）；在 D-12 共同部分 (iv) 的實質性審查中，這種變更一律視為字面變更，不得據以登記新 claim。兩者合起來，`name` 列在範圍內期間，已登記規則集的 `name` 不得單獨修改。
```

**6. R-4　L1619（D-10 第 1 點 `definition_logic_sha256`）　old→new**
- old：`所以已登記版本的任何欄位（含文字與出處欄位）都不能原地修改，`
- new：
```text
所以已登記版本只改物件、不改登記雜湊的原地修改，執行期一律拒絕；已登記版本的物件與兩個雜湊一律不得修改，
```

**7. R-6　L1619（同點）句末接字**
- 錨點：`` 兩個雜湊函式與排除欄位的集合，在 `app/` 內都只在 `app/dirdef/` 定義一次。 ``
- 接在錨點之後：
```text
（B2D-1，風控條件）本點 `rules_logic_sha256` 一句的「quant 凍結時列出的其他字面鍵」，與本句的「凍結時 quant 另列的文字欄位」，每一項都要附上「不被任何標籤、基準或判定讀取」的依據（含該欄位在 `app/` 內的讀取點清單，讀取點只限雜湊、登記、禁詞掃描與文字呈現），送風控確認後才可列入排除範圍。
```

**8. R-3　L2451（D-14 G-2 機器部分「由 qa 核對」一點）句末接字**
- 錨點：`` 這份紀錄是不是 CEO 本人的決定、內容與 `f2_variant` 是否一致，由 qa 核對。 ``
- 接在錨點之後：
```text
（B2D-1，風控條件）每一個新登記的定義版本（含只改 C-8 出處欄位的 MINOR 版），qa 在該 PR 同樣依本點核對決策紀錄是 CEO 本人的決定、內容與 `f2_variant` 一致，下一點的 CI 檢查同樣適用；C-8 選擇的任何改變都必須經 `f2_variant` 或其他 dirdef 常數表達，並受 D-12 共同部分 (vii) 約束，只換決策紀錄而 `f2_variant` 與其他 dirdef 常數不變，不得用來改變 C-8 的選擇。
```

**修訂紀錄段（L5791～5822，併入同一段）**

**9. R-7　L5795　old→new**
- old：`` 風控：B2D-1 輕量確認，其餘知悉 `work/reviews/2026-10-25-B2D批輕量確認-風控.md`。 ``
- new：
```text
風控：B2D-1 輕量確認（附條件）、B2D-3 附條件，其餘知悉 `work/reviews/2026-10-25-B2D批輕量確認-風控.md`；必要修改 R-1～R-7 依 tech-architect 2026-10-25 確認的字面補入（coordinator 轉存 `〔轉存檔名〕`），建議 S-3 一併採用（主詞限於 recorder）。
```

**10. R-7 連帶（R-3、R-4、R-5、R-6）　L5798　old→new**
- old：`` 收緊（新增 `definition_sha256`，已登記版本的任何欄位不得原地修改） ``
- new：
```text
收緊（新增 `definition_sha256`，只改物件、不改登記雜湊的原地修改執行期拒絕，同時改登記雜湊者見照實並陳；風控條件：新登記的每一版逐版核對 G-2〔R-3〕、`name` 列在範圍內期間不得單獨修改〔R-5〕、排除欄位須附依據並送風控〔R-6〕）
```

**11. L5800　句末接字（交代被取代原文）**
- 錨點：`` 其餘（D-10 第 1 點兩句、`definitions.py` 列、D-14 G-2、FL-26）都是句末接字，無被取代原文。 ``
- 接在錨點之後：
```text
風控條件 R-3（D-14 G-2「由 qa 核對」一點）、R-5、R-6（D-10 第 1 點兩句句末）是接字；R-4 改寫的是本段同批新增、尚未 commit 的 D-10 第 1 點字面，無被取代原文。
```

**12. R-7　L5803（B2D-3 方向）　接字**
- 錨點：`` 收緊（門檻隨 `definition_version` 固定、入 logic 雜湊） ``
- 接在錨點之後，原文接著的「。CEO：否。」保留：
```text
；下限比照 `CoverageRules`（[0.90, 1]，之後只能收緊；R-1）；補定義（R-2：「被排除的權重 > 10%」改以保留權重直接與常數比較，判定結果不變，只消除浮點邊界的字面歧義）
```

**13. L5805 之後另起一行（B2D-3 被取代原文的說明）**
- 錨點行：`` > `basket_log_returns(members, series, window)` ``（L5805，整行）
- 在這一行之下插入新行，縮排 4 個半形空白，和 L5800 同型：
```text
    R-1（D-1 `basket.py` 列、FL-56）是接字；R-2 改寫的是本段同批新增、尚未 commit 的字面，無被取代原文。
```

**14. S-3　L5817　old→new**
- old：`系統不會執行〔推論〕，要生效就必須另以常數表達。`
- new：
```text
recorder 不會執行〔事實：D-14「recorder 執行期強制」一點的「不讀決策檔」、G-2 機器部分的「recorder 執行時不讀 `docs/`、`work/`」〕，要生效就必須另以常數表達。
```

**15. R-4　照實並陳新增一點**
- 位置：第 14 項改完的那一行（L5817，行尾是「要生效就必須另以常數表達。」，全檔唯一）之下，插入新行：
```text
  - B2D-1（執行期限制）：`definition_sha256` 只存在程式內的登記表，不存入 `forecast_claim_registry`〔事實：D-10 第 3 點的欄位清單〕；同時改定義物件與登記雜湊的原地修改，執行期查不到，只能由 qa 的 PR 審查與 git 歷史發現；logic 範圍內的改動，在該版已有 claim 時，仍會被 D-10 第 2 點的寫入檢查擋下。改成執行期也查得出來（claim 登記或每筆紀錄存入 `definition_sha256`），列為後續追蹤，由 tech-architect 評估。
```

**16. R-7　L5818　句末接字**
- 錨點：`族群方法日後改版時，已登記的 dirdef 不跟著改，要改就另發 dirdef 版本。`
- 接在錨點之後：
```text
型別下限 0.90 也是另寫的一份（`app/dirdef/` 內的字面值，不 import `CoverageRules`）。
```

**17. L5822　閘門句末接字**
- 錨點：`` B2D-1 風控確認不成立時，回 tech-architect 重議（完整雜湊 `definition_sha256` 保留）。 ``
- 接在錨點之後：
```text
風控 2026-10-25 對 B2D-1、B2D-3 核可附條件：R-1～R-7 補入本段與正文後，回送風控，只核對 R-1～R-7 的字面；R-1、R-2 的程式與測試由 dev-lead 在同一份 staged diff 補上，未補完不 commit。
```

#### D. 對實作的約束（給 dev-lead；qa 逐條檢查）

- **C-5′**：`definition.py:109` 改成 `Annotated[float, Field(ge=0.9, le=1)]`，下限寫成字面值，不 import `app.sectors`。這一條取代我上一份 C-5 的 `(0, 1]`。
- **C-9**：`test_dirdef_definition.py` 的拒絕表（L187～189 一帶）加 `0.8999`；通過格加 `0.90` 和 `1.0`；保留 `nan` 的拒絕格。
- **C-10**：補 FL-56 的兩格：「已登記各版不小於凍結值」（登記表為空時照跑），和「不得對 `BASKET_MIN_MEMBER_WEIGHT` 屬性做減法」的 AST 絆線。10 檔排除 1 檔的格，現有的 `test_outlook_basket.py:270` 已經涵蓋。
- **C-7′（docstring）**：
  - `basket.py:15-16` 的「exceeds ``1 - BASKET_MIN_MEMBER_WEIGHT`` (10%)」改成 retained weight below the threshold 的寫法，和 R-2 一致。
  - `definition.py:35-36` 的「no field ... can be edited in place without the registration check failing」改成只涵蓋「物件改了、登記雜湊沒改」的情形，和 R-4 一致。
- **不得動**：`CoverageRules`；`basket_hold_ratio`；兩張登記表維持空的。

## 驗證

- 讀過的檔案與範圍：
  - 風控回報全文、我的原裁定全文；
  - ADR-0027 L260、L1614～1627、L2333～2345、L2443～2456、L3100～3111、L3306、L5780～5822；
  - `app/dirdef/definition.py` 全文、`app/outlook/basket.py` L1～35 與 L60～169、`app/sectors/definition.py` L80～112；
  - 用 Grep 看了 `test_outlook_basket.py` 與 `test_dirdef_definition.py` 的相關格。
- C 節 17 項的 old 和錨點，全部用 Grep `-o` 確認在現行檔恰好出現 1 次，而且都不在修訂紀錄段的引文行內。新標記「風控條件」、`0.8999`、「`BASKET_MIN_MEMBER_WEIGHT` 的型別範圍」目前都是 0 次。落檔後的計數我沒有預先算好，請 tech-writer 用 Grep `-o` 回報。
- 有一個前提我無法驗證：第 11、13 項的「尚未 commit」，是依 L5822 的閘門字面推定的。我沒有執行 git，請 tech-writer 落檔前用 `git diff` 確認本批的 ADR 改動確實還在工作區、沒有 commit；如果已經 commit，這兩項要改成引用被取代原文。
- 我沒有寫入任何檔案，沒有執行 Bash 或測試，沒有讀 `.env` 或 `*.db`。

## 下一步

1. **coordinator**：轉存本回報（建議檔名 `work/reviews/2026-10-25-B2D風控條件確認-tech-architect.md`），把檔名填進第 9 項的〔轉存檔名〕。S-1（tech-architect）、S-2（quant）登記為追蹤項。
2. **tech-writer**：依 C 節 1～17 的順序落檔，正文和修訂紀錄放同一個 commit，回報 Grep 計數。
3. **dev-lead**：在同一份 staged diff 上做 C-5′、C-9、C-10、C-7′。
4. **風控**：只做 R-1～R-7 的單項確認。我改寫過的地方是 R-1 的兩處補字、R-2 的跳脫與 AST 格、R-3 的位置與「或其他 dirdef 常數」、R-5 的「不得單獨修改」、R-6 的讀取點清單、R-7 的連帶修改，都比原案嚴或相同；請一併確認。
5. **qa-reviewer**：依 D 節和 C 節逐條審查，補跑 Codex。風控單項確認成立之前不 commit。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/reviews/2026-10-25-B2D批輕量確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-25-B2自決事項裁定-tech-architect.md
- /home/user/AICompany/apps/stock-desk/backend/app/dirdef/definition.py
- /home/user/AICompany/apps/stock-desk/backend/app/outlook/basket.py
- /home/user/AICompany/apps/stock-desk/backend/app/sectors/definition.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_dirdef_definition.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_outlook_basket.py
