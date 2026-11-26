# 另案 A SettingsForm 非註解改動確認（RC-796 第 7 項）

- 審查者：qa-reviewer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
確認成立。commit 1 在 `SettingsForm.tsx` 的非註解改動只有兩處（`description` 那一行、`<p>` 說明句那一行）。這兩處的新字面和 RC-730 定稿逐字相同。歸類加總是 +8／-3，和 numstat 8／3 一致。

## 各部門回報（歸類）
| 行 | 類別 | + | - |
|---|---|---|---|
| 第 95 行附近，`description` 的舊句（0.15／15%）與新句（0.01／1%） | 非註解 | 1 | 1 |
| 第 98 行前新增的 3 行 `//`（RC-730／RC-731／RC-738、wording、example…verbatim） | 註解 | 3 | 0 |
| 第 462 行附近，JSX 註解舊行（`not a fraction… removed. */}`，含收尾） | 註解 | 0 | 1 |
| 第 462 行附近，JSX 註解新增 3 行（改寫後的 `not a fraction… removed.`、`RC-730…same example`、`as the max_position… above). */}` 收尾行） | 註解 | 3 | 0 |
| `<p>` 內的說明句（0.15 = 15% 換成 0.01 = 1%） | 非註解 | 1 | 1 |
| 合計 | 註解 +6／-1，非註解 +2／-2 | 8 | 3 |

- 其餘 hunk 上下文都是未改動行。
- 淨增 +5，和兩個 hunk 的行數變化（+3、+2）相符。

## 驗證（逐字比對）
比對對象是 RC-730 定稿檔第 25 行和第 30 行。
- `<p>` 句新字面：`除 ATR 停損倍數外，每一項數字都是分數（例如 0.01 = 1%）。`，與第 25 行相同。
- `description` 新字面：`此標的市值占總資產(已估值部位市值,不含現金)的上限（比例，例如 0.01 代表 1%）。`，與第 30 行相同。
- 半形括號、半形逗號、全形括號、全形逗號，以及「=」兩邊的半形空格都一致。
- 和舊句相比，只有數字不同。
- 這是我目視比對，沒有用機械比對。

## 下一步
可交 risk-gate。我只做了這份書面確認，沒有做完整 code review。

## 跑過的指令
- Bash：只跑了 `git diff bd840afd 587767d8296757e605fdaaa89b55c0b3d15f5420 -- apps/stock-desk/frontend/app/settings/SettingsForm.tsx`
- 另外用 Grep 和 Read 唯讀查看 RC-730 定稿檔（`/home/user/AICompany/work/reviews/2026-11-25-另案A例子與另案C警示標籤逐字審RC730至RC739-風控.md`）。這兩個動作不是 Bash，所以任務說明裡「其他一律不跑」若連唯讀工具也算，這點要請你知悉。
- Codex 依 CEO 決策 #58 不可用，未執行。
