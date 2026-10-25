# ADR-0027 第一批補遺審查

- 審查者：qa-reviewer
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS，`BLOCKING_ISSUES=false`。** ADR-0027 第一批補遺的四個 hunk 字句忠實於核可來源，我沒有發現遺漏、多寫或與現行 ADR 矛盾之處。N115-10a 的錨點落點可讀，只有一個 low 級的指代歧義。

Codex 第二意見未執行（環境不可用）。`codex --version` 回傳 `codex: command not found`（exit 127）。依 CEO #53 合併前補跑。

## 各部門回報

### qa-reviewer 審查（`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`，只有這一個檔，4 個 hunk）

**忠實度**
- **N115-10a（L240）**：與 TA「決策」N115-10a 的 new 逐字相同。
- **N115-10b（L352）**：與 TA 的 new 逐字相同。
- **N115-11（L2382～L2384）**：兩處取代和新增的 L2384 與 TA 稿逐字相同。新增行的縮排與同層項目一致。
- **修訂紀錄（L5589～L5609）**：與風控「整段定稿」逐字相同，用的是風控定稿，不是 TA 舊稿。`---` 沒有重複，補遺接在第一批「待決事項」之後。
- **被取代原文**：N115-11 的兩條舊句已只剩補遺段引文（L5601、L5602）。coordinator 預產檢查「刪除檢查 removed_fragments_missing 0」成立。
- **多寫與遺漏**：除 coordinator 檢查已列的兩處「- 」接縫外，沒有來源以外的字句，也沒有漏落的項目。10-gram 未覆蓋的 L2382、L2383 兩行，其新字逐字在 TA 稿內。

**內部一致性與外部矛盾**
- **「後三項」指代**：D-13 不變式清單現有四項。「後三項」指 `source_status`／`source`、`attempted_at`、`latest_available`，「第一項」指 `label`／`missing`，指代正確。FL-39（L3070）確為 `MissingItem` 的 model validator 條目，引用正確。
- **`extra="forbid"` 與程式碼區塊**：「每個欄位都沒有預設值」與 L2366～2376 的區塊相符，沒有任何 `= None`。
- **「上一段」與引文**：補遺說的「上一段『N-113、N-115、N-117 批』」與 L5533 標題一致。引用的 N115-6 照實並陳（L5581）句子逐字存在。補遺說「不涵蓋非有限的數值」，與 L5581 的範圍相符。
- **N115-4 照實並陳**：L5580 講的是例外類別名稱規則有兩份，與「違規值列舉只留一份」是不同的東西，不矛盾。
- **FL-78 (n)（L2977）**：「`band.py` 不 import `scoring.py`、`app/outlook/volatility.py`」與 10a 新增的例外不衝突。
- **N113-2 接續**：10a 的「上述 import 範圍的唯一例外」接在 N113-2 新字之後，語意通順。
- **計數**：tech-writer 與 coordinator 的 `N-115` 24→32 一致。補遺段首與來源行用到「N-115」，風控已預告，TA 的「修訂紀錄不增加」不再成立，tech-writer 已據實重算。

**問題（皆不擋）**
1. **[可維護性][low]**（L240）：N115-10a 接在 `band.py` 格中段。後面緊接「`store.py` 的寫入驗證、… 只經這兩個函式判定缺項」。新插入的例外句剛好列出兩個名稱（`ThresholdViolation`、`THRESHOLD_VIOLATION_ORDER`），「這兩個函式」的就近指代變得含糊。
   - 緩解因素：該格開頭已點名 `threshold_inputs` 與 `labeled_snapshot_violations`，且新句的兩個名稱是類別與常數，不是函式。依 TA 與風控的核可，此處照字面可讀、不用改。
   - 建議：日後有機會動這一格時，把「這兩個函式」寫成帶名稱的形式。在那之前不要為此重開核可流程。
2. **[可維護性][low]**（L238、L2977）：ADR 內其他兩處沒有同步提到新的唯一定義處。
   - D-1 `errors.py` 列（L238）沒有列出 `ThresholdViolation`、`THRESHOLD_VIOLATION_ORDER` 定義在這裡。
   - FL-72 (n)（L2977）沒有釘「列舉單一定義在 `errors.py`、`band.py` 的 `app.*` import 恰為那一行」。TA 的 C1～C3 只約束程式與測試。
   - 這兩處都不在核可來源內，不是本批錯誤。建議交 tech-architect 評估是否列後續追蹤，不阻擋本批。
3. **[Edge case][low]**（L352，風控已列 suggested）：「各違規值依括號內的條件各自判定」嚴格說只對 `sigma_d_below_floor`、`valid_returns_below_min` 成立。`sigma_d_not_positive_finite` 的條件寫在前面的「缺項」段。風控已核可不改字，只提醒 C7 測試加一格：`sigma_d_missing` 成立時不再記另外兩個 `sigma_d` 違規值。

## 驗證

**唯讀權限判準常數：未觸及。**
- diff 範圍只有 `docs/adr/` 下的單一 md 檔，不含 `scripts/validate_agents.py`。
- 我讀過 diff 全文，沒有任何以 `+` 或 `-` 開頭、含 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的行。
- 沒有 shadow 定義，也沒有常數值改動。
- 本次依指示只准 `git diff` 與 `codex --version`，所以沒有逐字執行 `--name-only | grep -x` 與 `grep -E` 兩道管線，改以讀 diff 全文判定。

**實際執行過的 Bash 指令（逐字）**
1. `cd /home/user/AICompany && git diff -- docs/adr/`
2. `codex --version`（exit 127，`codex: command not found`）

其餘都是 Read、Grep：
- 讀了 coordinator 預產檢查、TA 裁定、風控確認、tech-writer 交件，以及 ADR 的 L2355～2395、L2976～2978、L5534～5589。
- Grep 了 `band.py`、`FL-39`、`標準庫`、`非數值不會被當成完整`、`class MissingItem` 和補遺標題。
- 沒有讀 `.env`，沒有碰 `*.db`，沒有改任何檔案。

**沒做的事**
- 沒審程式（B1 在重建中）。
- 沒有自行重算 `N-115` 的 32 次。我信 coordinator 與 tech-writer 兩邊一致的數字，只交叉驗證了 L5591 標題含兩處。

## 下一步

1. **coordinator**：合併前補跑 Codex 並補入本報告（CEO #53）。依風控交接更新追蹤清單 N-123 的時限欄。補遺須在第一批 commit 之後單獨 commit。
2. **tech-architect（可選，不擋）**：評估問題 2 要不要列後續追蹤，就是 `errors.py` 列補列與 FL-72 (n) 加格。
3. **dev-lead（B1 重建）**：C7 測試加一格，確認 `sigma_d_missing` 成立時不再記另外兩個 `sigma_d` 違規值。
4. **tech-architect**：起草 N-123，quant 同步 V22-07，送風控。在這之前，補遺段的閘門有效（`scoring.py`、`settlement.py`、`correction.py` 與重放執行函式中經 `threshold_inputs()` 判定缺項的路徑不實作）。

## Verdict
PASS
BLOCKING_ISSUES=false
