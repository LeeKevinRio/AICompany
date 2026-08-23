# Skills — 技能包放這裡

這個資料夾放公司可掛載的 **skills**（技能包）。Skill 是一組封裝好的指示與工具，讓 agent
在特定任務上有更穩定、可重複的工作流程（例如 TDD、debug、git 操作、文件處理）。

## 怎麼用
- 把 skill 放進 `.claude/skills/<skill-name>/`，Claude Code 會自動偵測。
- 同一份 skill 可在 **Claude Code 與 Codex 共用**（兩邊都讀同樣的 skill 定義），維持跨廠商一致的工作流程。

## 已引入的外部 skills(2026-08-23)

| Skill | 來源 | 形式 |
| --- | --- | --- |
| **animate** / **review-animations** / **animation-vocabulary** | [`emilkowalski/skills`](https://github.com/emilkowalski/skills)(pin `d23d7f8`,MIT) | 繁中改作,LICENSE 隨附,文首掛風控地板優先註記 |
| **ui-delivery-checklist** | 概念參考 [`Nutlope/hallmark`](https://github.com/Nutlope/hallmark)(pin `13ac0ec`,MIT) | 自寫(取可機械判定閘門子集,非改作) |

引入評估與雙審紀錄見產品線 `work/研究-外部設計skill庫評估.md` 與 `work/reviews/2026-08-23-員工線-動效skill批次-*.md`。

## 建議之後掛上的開源 skills

| Skill | 來源 | 用途 |
| --- | --- | --- |
| **superpowers** | [`obra/superpowers`](https://github.com/obra/superpowers) | TDD、debug、git 等開發核心工作流程 |
| **anthropics/skills** | [`anthropics/skills`](https://github.com/anthropics/skills) | 官方 skills，含文件處理（docx / pdf / pptx / xlsx 等） |
| **openai/skills** | [`openai/skills`](https://github.com/openai/skills) | 給 Codex 用的 skills（搭配跨廠商 review 流程） |

> 註：上述為建議清單，尚未實際安裝。掛載方式與授權請依各 repo 的說明為準。

## TODO（由 CEO 決定）
- [ ] 選定要掛的 skills 並 clone / 安裝到本資料夾。
- [ ] 確認哪些 skill 給 dev-lead、哪些給 qa-reviewer（Codex）。
- [ ] 視需要調整 skill 的觸發描述，讓自動派工更準。
