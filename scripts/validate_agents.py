#!/usr/bin/env python3
"""Validate .claude/agents/*.md against the company agent spec.

Checks (see CLAUDE.md / docs/org-chart.md):
- frontmatter parses and required fields are present
- name matches filename and is globally unique
- tools are all in the whitelist
- description starts with a trigger phrase and has a reasonable length
- body contains all required sections
- read-only roles do not have Write/Edit/unscoped Bash
- docs/org-chart.md department table matches agent files exactly

Stdlib only (no PyYAML) so it runs anywhere. Exits non-zero on any error,
printing file, line number, and reason for each failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / ".claude" / "agents"
ORG_CHART = ROOT / "docs" / "org-chart.md"

REQUIRED_FIELDS = ("name", "description", "tools", "model")

BASE_TOOLS = {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}
SCOPED_BASH = {"Bash(codex:*)", "Bash(git diff:*)"}
PREVIEW_TOOLS = {
    "mcp__Claude_Preview__preview_start",
    "mcp__Claude_Preview__preview_stop",
    "mcp__Claude_Preview__preview_list",
    "mcp__Claude_Preview__preview_screenshot",
    "mcp__Claude_Preview__preview_snapshot",
    "mcp__Claude_Preview__preview_click",
    "mcp__Claude_Preview__preview_fill",
    "mcp__Claude_Preview__preview_eval",
    "mcp__Claude_Preview__preview_inspect",
    "mcp__Claude_Preview__preview_console_logs",
    "mcp__Claude_Preview__preview_logs",
    "mcp__Claude_Preview__preview_network",
    "mcp__Claude_Preview__preview_resize",
}
TOOL_WHITELIST = BASE_TOOLS | SCOPED_BASH | PREVIEW_TOOLS

MODEL_WHITELIST = {"opus", "sonnet", "haiku", "inherit"}

# Roles whose judgement must stay independent: no write access, no unscoped Bash.
READONLY_AGENTS = {"qa-reviewer", "qa-e2e", "tech-architect", "risk-compliance-officer"}
READONLY_FORBIDDEN = {"Write", "Edit", "Bash"}

TRIGGER_PHRASES = ("MUST BE USED", "Use PROACTIVELY")
DESCRIPTION_MIN, DESCRIPTION_MAX = 20, 400

REQUIRED_SECTIONS = (
    "角色定位",
    "職責範圍",
    "輸入契約",
    "輸出契約",
    "品質檢查清單",
    "交接對象",
    "紅線",
)

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ORG_TABLE_ROW_RE = re.compile(r"^\|\s*`([a-z0-9-]+)`\s*\|")

errors: list[str] = []


def err(path: Path, line: int, msg: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}:{line}: {msg}")


def parse_frontmatter(path: Path, lines: list[str]) -> tuple[dict[str, str], dict[str, int], int]:
    """Parse simple `key: value` frontmatter. Returns (fields, field_line_numbers, body_start_index)."""
    fields: dict[str, str] = {}
    field_lines: dict[str, int] = {}
    if not lines or lines[0].strip() != "---":
        err(path, 1, "缺少 frontmatter（檔案第一行必須是 ---）")
        return fields, field_lines, 0
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        err(path, 1, "frontmatter 未閉合（找不到第二個 ---）")
        return fields, field_lines, 0
    for i in range(1, end):
        raw = lines[i]
        if not raw.strip():
            continue
        if ":" not in raw:
            err(path, i + 1, f"frontmatter 無法解析（缺少冒號）：{raw.strip()!r}")
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        if key in fields:
            err(path, i + 1, f"frontmatter 欄位重複：{key}")
        fields[key] = value.strip()
        field_lines[key] = i + 1
    return fields, field_lines, end + 1


def check_agent(path: Path, seen_names: dict[str, Path]) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    fields, field_lines, body_start = parse_frontmatter(path, lines)

    for field in REQUIRED_FIELDS:
        if not fields.get(field):
            err(path, 1, f"frontmatter 缺少必填欄位：{field}")

    name = fields.get("name", "")
    if name:
        line = field_lines.get("name", 1)
        if not NAME_RE.match(name):
            err(path, line, f"name 必須是 kebab-case：{name!r}")
        if name != path.stem:
            err(path, line, f"name（{name}）與檔名（{path.stem}）不一致")
        if name in seen_names:
            err(path, line, f"name 重複：{name}（已出現在 {seen_names[name].name}）")
        else:
            seen_names[name] = path

    description = fields.get("description", "")
    if description:
        line = field_lines.get("description", 1)
        if not any(description.startswith(p) for p in TRIGGER_PHRASES):
            err(path, line, f"description 必須以觸發語開頭（{' 或 '.join(TRIGGER_PHRASES)}）")
        if not (DESCRIPTION_MIN <= len(description) <= DESCRIPTION_MAX):
            err(path, line, f"description 長度 {len(description)} 不在 {DESCRIPTION_MIN}–{DESCRIPTION_MAX} 範圍內")

    tools_raw = fields.get("tools", "")
    tools = [t.strip() for t in tools_raw.split(",") if t.strip()] if tools_raw else []
    if tools_raw:
        line = field_lines.get("tools", 1)
        for tool in tools:
            if tool not in TOOL_WHITELIST:
                err(path, line, f"tools 含白名單外的工具：{tool}")
        if path.stem in READONLY_AGENTS:
            forbidden = READONLY_FORBIDDEN & set(tools)
            if forbidden:
                err(path, line, f"唯讀角色不得擁有 {'、'.join(sorted(forbidden))}")

    model = fields.get("model", "")
    if model and model not in MODEL_WHITELIST:
        err(path, field_lines.get("model", 1), f"model 必須是 {sorted(MODEL_WHITELIST)} 之一：{model!r}")

    headings = {}
    for i in range(body_start, len(lines)):
        m = re.match(r"^##\s+(.+?)\s*$", lines[i])
        if m:
            headings[m.group(1)] = i + 1
    for section in REQUIRED_SECTIONS:
        if section not in headings:
            err(path, len(lines), f"body 缺少必要小節：## {section}")


def check_org_chart(agent_names: set[str]) -> None:
    if not ORG_CHART.exists():
        errors.append(f"{ORG_CHART.relative_to(ROOT)}:1: 檔案不存在（org chart 為必要文件）")
        return
    listed: dict[str, int] = {}
    for i, raw in enumerate(ORG_CHART.read_text(encoding="utf-8").splitlines(), start=1):
        m = ORG_TABLE_ROW_RE.match(raw)
        if m:
            name = m.group(1)
            if name in listed:
                err(ORG_CHART, i, f"部門總表重複列出：{name}")
            listed[name] = i
    for name in sorted(agent_names - set(listed)):
        errors.append(f"{ORG_CHART.relative_to(ROOT)}:1: 部門總表缺少 agent：{name}（.claude/agents/{name}.md 存在）")
    for name, line in listed.items():
        if name not in agent_names:
            err(ORG_CHART, line, f"部門總表列出的 {name} 沒有對應的 .claude/agents/{name}.md")


def main() -> int:
    if not AGENTS_DIR.is_dir():
        print(f"{AGENTS_DIR.relative_to(ROOT)}: 目錄不存在", file=sys.stderr)
        return 1
    agent_files = sorted(AGENTS_DIR.glob("*.md"))
    if not agent_files:
        print(f"{AGENTS_DIR.relative_to(ROOT)}: 沒有任何 agent 檔案", file=sys.stderr)
        return 1

    seen_names: dict[str, Path] = {}
    for path in agent_files:
        check_agent(path, seen_names)
    check_org_chart({p.stem for p in agent_files})

    if errors:
        print(f"validate_agents: {len(errors)} 個問題\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print(f"validate_agents: OK（{len(agent_files)} 個 agents 全數通過）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
