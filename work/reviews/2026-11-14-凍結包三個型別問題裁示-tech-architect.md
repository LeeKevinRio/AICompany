# 凍結包三個型別問題裁示（invalidation、aggregation、sigma_d）

- 審查者：tech-architect
- 日期：2026-11-14
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

quant 留給我的三題裁示如下：
1. **`invalidation`：要收緊**，但做法和 quant 提的不同。改成和 `condition` 同一型別的條件樹（`OutlookCondition`），不另寫一套字串文法和解析器。**這會改到規則位元組，也就是 `rules_sha256`／`rules_logic_sha256`；name、explanation、counterargument 這些自然語言字面完全不變。** 風控那邊要知悉。
2. **`aggregation` 兩個值都用 `float`**，和現有的 `weight`、`value` 同一套數值慣例；engine 一律轉成 `Fraction` 比較。quant 的 YAML（`theta: 2`、`min_completeness: 1.0`）不用改，也不動規則字面。
3. **證據不足時 `band_def.sigma_d` 照記**：記 `volatility.sigma_d` 的回傳值，不可用時就是 null，不補值、不另外計算。這和 `band.py`、schema 的 CHECK 都一致，只需在 store 的寫入驗證補一條規則。不動規則字面。

## 各部門回報（tech-architect）

**Q1 `invalidation`（凍結包 2.7）**
- **裁示**：
  - `OutlookRule.invalidation` 的型別從 `str` 改成 `OutlookCondition`。quant 的 DNF 改寫成 `any: [ {all: [...]}, ... ]`，例如 `trend_up` 就寫成三個比較的 `any`。
  - 載入守門加兩條：
    - (a) 欄位都在 `OUTLOOK_RULE_FIELDS` 內，這一條沿用既有的 `condition_fields`；
    - (b) `condition_fields(invalidation)` 的集合，要等於 `condition_fields(condition)` 的集合。
  - 「恰好等於條件的否定」不在載入時判定，改由性質測試證明。
- **理由**：
  - 另寫字串文法，等於在 `app/` 裡出現第二套運算式語言，驗證層日後也要再寫一個求值器，違反 K-6「單一定義」。
  - 改用條件樹，就能沿用既有的 `holds`、欄位守門與禁詞掃描。
  - 拿掉這個欄位、改由程式自動導出否定，則違反 ADR-0025 D-2.3「每條規則宣告 `invalidation`」，所以不採用。
  - 核心期間不對它求值，quant 的這個定位不變。
- **qa 怎麼檢查**：
  - 型別：`invalidation` 不是條件樹（例如寫成字串）時，載入要被拒絕。
  - (a)、(b) 兩條守門各要有反例測試。
  - 四份 YAML 都要通過真值表性質測試：在含邊界值的網格上，`holds(invalidation) == not holds(condition)`。
  - `app/` 裡沒有第二個運算式解析器（grep `split(" or ")` 這類寫法）。

**Q2 `aggregation` 型別**
- **裁示**：
  - `theta: float = Field(gt=0, allow_inf_nan=False)`；
  - `min_completeness: float = Field(gt=0, le=1, allow_inf_nan=False)`；
  - 拒收 bool；
  - engine 用 `Fraction(theta)` 和 `Fraction(evaluable, total) < Fraction(min_completeness)` 判定。
- **理由**：
  - `canonical_sha256` 以最短往返 repr 寫出 float，是決定性的。YAML 寫 `2` 或 `2.0`，都會正規化成同一個邏輯雜湊。
  - `Fraction(float)` 是精確轉換。
  - Decimal：YAML 沒有原生的 Decimal，必須加引號；dump 出的字串也會讓 `"1"` 與 `"1.0"` 得到不同的雜湊。
  - Fraction：需要自訂序列化，等於多一套數值慣例。
  - int：表達不了比例（`min_completeness`），也和小數權重不相容。
- **qa 怎麼檢查**：
  - `theta: 2` 和 `theta: 2.0` 的 `rules_logic_sha256` 相同；`theta: 3` 的不同。
  - true、0、負值、`.nan`、`.inf`、`min_completeness: 1.01` 都要被拒絕。
  - engine 不在 float 上直接比較 W 與 θ（AST 或 grep 確認，用的是 `Fraction`）。

**Q3 證據不足時的 `sigma_d`（凍結包 2.5）**
- **裁示**：
  - `band_def.sigma_d` 記 `volatility.sigma_d` 的回傳值（可用就是數值，`E-VOL-SHORT` 或 `E-VOL-DEGENERATE` 時是 null）；`valid_returns`、`K_h`、`EPS` 照記。
  - `up_pct`、`down_pct` 一律是 null，這是 schema 既有的 CHECK。
  - store 對 `insufficient` 紀錄補一條寫入驗證：`sigma_d` 非 null 時，`band.labeled_snapshot_violations` 必須為空。
  - `sigma_d` 為 null ⇔ `missing_json` 含 `E-VOL-*`。
- **理由**：
  - ADR-0030 D-3 第 6 點只要求 up、down 為 null，沒有要求清掉 σ。
  - B1 與 `z_past_*` 的分母用的是同一個值（凍結包 2.4）。照記才能讓 D-5 第 3 點逐位重算時，涵蓋到 `band_def`。
  - 判定沿用 `band.py` 這個唯一的定義，不新增函式。
- **qa 怎麼檢查**：由 dev-lead 用 `tmp_path` 測試實證四種情況：
  - (i) `insufficient`（`E-BARS-SHORT`），且 σ 可用：寫入成功，`sigma_d` 是數值；
  - (ii) FX-F2，σ 退化：`sigma_d` 是 null，寫入成功；
  - (iii) `insufficient`，但 `sigma_d` 低於 floor：被拒絕；
  - (iv) `insufficient`，`sigma_d` 是 null，但 `missing` 不含 `E-VOL-*`：被拒絕。
  - 另外，(i) 重算後 `band_def` 要逐位相同。

## 驗證

- 讀過的檔案：
  - 凍結包 `/home/user/AICompany/work/research/2026-11-14-NM5凍結包-大盤h3h5-quant.md`（2.4～2.9、4.1）
  - `/home/user/AICompany/apps/stock-desk/backend/app/forecast/band.py`
  - `/home/user/AICompany/apps/stock-desk/backend/app/dirdef/hashing.py`
  - `/home/user/AICompany/apps/stock-desk/backend/app/dirdef/rules.py`
  - worktree 中的 `schema.py`
- 沒有執行任何程式。以下三點**未實證**：
  - pydantic 的 lax float 在 YAML 寫 `2` 時，是否確實轉成 2.0、雜湊是否與寫 `2.0` 相同；
  - lax float 是否接受 bool；
  - store 目前對 `insufficient` 紀錄實際做了哪些 band 檢查。
- 三題都不需要修訂 ADR，也不需要 CEO。

## 下一步

1. quant：把四份 YAML 的 `invalidation` 改寫成條件樹，重跑 6,561 組網格的核對，更新凍結包 2.7 與 v0.32 差異清單。
2. 風控：知悉 `invalidation` 的位元組會改變，自然語言字面不受影響。
3. dev-lead：實作 Q1 的兩條載入守門、Q2 的型別、Q3 的 store 驗證規則，交 Q1～Q3 的測試實證，再送 qa-reviewer。

（上一份 G1／SP-1 裁示與 ADR-0030 補充一全文已交付，本題沒有改動那些內容。）
