# ADR-0035 補充四釐清三（結算自身讀取不屬 R-4）

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**這兩處都不算 R-4 所說的「在途讀取點」，判定成立，不用改程式。** 但 R-4 原文沒有寫出「結算自身的讀取」是例外，qa 依 QB-7 grep `pending_directives(` 時會一再遇到同樣的疑問，所以補一行「釐清三」，把例外和它的界線寫死。

這兩處是：
- **A**：`_settle_pending` 開頭的 `self._store.pending_directives(on_or_before=as_of)`，在 product 是 `service.py:675`，N-182 分支是 `:747`。
- **B**：`_with_stale_exit_notes` 內的 `self._store.pending_directives()`，在 product 是 `:840`，N-182 分支是 `:915`。

## 二、各部門回報

### tech-architect（本人，唯讀）

**理由**

1. **R-4 管什麼。** R-4 要保護的是「`/today` 回應裡的在途清單，以及這些清單的排除條件，都出自同一個快照」。範圍包括：N-171 的群組 A／B、N-168 的 W-B1 類與 G1 擋下類、W-B6、W-B6b，以及 ENTRY／A 的排除。A、B 兩處的結果都不流進這些清單，只流進 `SettlementResult`，也就是回應裡的 `settlement.*`。
2. **A 是結算要處理的候選列。** 它決定這次要 claim、要載入 K 線的是哪些列，是會導致寫入的讀取。它不能改由 `read_in_flight` 提供，原因有兩個：
   - 補充四 S-2.3(c) 規定 `read_in_flight` 在結算**之後**執行，而結算一開始就需要這份資料；
   - `POST /settle` 這條路徑根本不呼叫 `read_in_flight`。
3. **B 是 N-166 的結算揭露。** 它只決定 N1／N1b 句中「同一批次是否還有更晚的出清列」。
   - 它在結算迴圈之後讀，看到的是 claim 之後的狀態，和隨後 `read_in_flight` 看到的狀態相同。所以在單一請求內，它不會和群組 A 互相矛盾。
   - 唯一的落差來自並發：在 B 和 `read_in_flight` 之間，另一個出清新寫入了一列。這和釐清一 E-2 是同一類並發殘留，歸 F2／N-169。
4. **不是 N-182 新增的。** 兩處都早於切面（dev-lead 已比對過，和 `31753cb` 完全相同），也是 `POST /settle` 的共用路徑。若把它們併入 `read_in_flight`，反而會改到固定項，觸發 R-3。

**要防的風險**
- 有人把 B 讀到的 outstanding 出清列直接拿去組群組 A；
- 有人以「結算內部」為名，在結算裡新增在途清單用的讀取。

釐清三就是為了把這兩條路堵住。

**釐清三（一行，直接附在釐清二末尾）**

```
## 釐清三（tech-architect 2026-11-04，回應 `work/reviews/2026-11-04-N182補件交件-dev-lead.md` 第四段第 3 點）：`_settle_pending` 開頭的 `pending_directives(on_or_before=as_of)` 與 `_with_stale_exit_notes` 內的 `pending_directives()` 屬於結算自身的讀取，不是 R-4 的在途讀取點；條件是這類讀取只出現在 `_settle_pending` 及其呼叫的 helper 內，結果只進 `SettlementResult`，不得被 N-171、N-168、N-182 的任何在途清單、W-B6／W-B6b、ENTRY／A 的排除所引用；在結算內為在途清單新增讀取，仍屬 R-4；qa-reviewer 依 QB-7 grep 時，以這兩處為僅有的白名單，第三處即 BLOCKING。
```

### 其他部門
本次未參與。

## 三、驗證
- 讀了 product 工作樹 `service.py` 的 `:640-699`（`_settle_pending` 開頭）和 `:780-859`（`_with_stale_exit_notes`），並 grep 全檔的 `pending_directives(`：product 上只有這兩處。
- N-182 分支上的行號 `:747`、`:915`，是 dev-lead 交件裡寫的。我沒有讀到 N-182 分支的程式，「兩處與 `31753cb` 完全相同」也是依他的交件。
- 沒有執行任何程式，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 四、下一步
1. **coordinator**：把釐清三附到 `/home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md` 檔末、釐清二之後。ADR-0035 的檔頭註記建議改成「另見補充四釐清一至三」。
2. **qa-reviewer**：QB-7 的 grep 以這兩處為白名單。N-182 重審時，請確認 merge 後的 head 上仍然只有這兩處。
3. **dev-lead**：自查第 4 點的口徑確認成立，不需要動作。
4. **待辦結清**：我在上一份回報第四段第 6 點列的待辦，到這裡已經答覆完畢。
