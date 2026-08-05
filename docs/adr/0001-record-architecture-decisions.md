# ADR-0001：以 ADR 記錄架構決策

- 狀態：accepted
- 日期：2026-07-23
- 決策者：tech-architect（草案）、CEO（核可）

## Context（背景）

架構決策（技術選型、模組邊界、資料源取捨）如果只存在對話紀錄裡，之後沒人追得回「當初為什麼這樣做」。公司需要輕量、進 git、可追溯的決策紀錄格式。

## Decision（決策）

採用 Architecture Decision Records（ADR）：

- 每個架構級決策一份檔案，放在 `docs/adr/`，檔名 `NNNN-<kebab-case-標題>.md`，編號從 0001 遞增、不重用。
- 由 `tech-architect` 產出草案（唯讀職能），由 `tech-writer` 或實作者落檔。
- 狀態欄只能是：`proposed`（提案中）、`accepted`（生效）、`deprecated`（過時）、`superseded by ADR-NNNN`（被取代）。
- 決策生效後不得原地改寫內容；要改就開新 ADR 取代舊的，舊的標 `superseded`。

## ADR 模板

```markdown
# ADR-NNNN：<標題>

- 狀態：proposed | accepted | deprecated | superseded by ADR-NNNN
- 日期：YYYY-MM-DD
- 決策者：<誰提案、誰核可>

## Context（背景）
（要解決什麼問題、有哪些限制）

## Options（選項比較）
| 方案 | 優點 | 缺點 | 風險 |

## Decision（決策）
（選了什麼、為什麼）

## Consequences（後果）
（好處、代價、被此決策約束的事，包括壞處都要寫）
```

## Consequences（後果）

- 好處：決策可追溯、可被反駁；新成員能快速理解系統為什麼長這樣。
- 代價：每個架構決策多一道落檔工序。
- 約束：實作與既有 `accepted` 的 ADR 衝突時，以 ADR 為準；認為 ADR 錯了就提新 ADR，不得默默繞過。
