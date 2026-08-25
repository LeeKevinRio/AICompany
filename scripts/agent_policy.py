"""Single source of truth for which agents are read-only and what Bash they may run.

Two independent consumers read this module and must never define their own copy:

- `scripts/validate_agents.py` — static check: does an agent's `.md` frontmatter
  declare a `tools:` line that stays within policy? (design-time)
- `.claude/hooks/readonly_guard.py` — runtime check: does an actual tool call from
  a read-only agent stay within policy? (execution-time, the real enforcement)

Background: before this file existed, both checks lived only as prose in agent
frontmatter (`tools: Read, Grep, Glob, Bash(codex:*), Bash(git diff:*)`) and as a
comment in the validator. Neither was ever enforced by Claude Code at the command
level — the `tools:` frontmatter field is a coarse, tool-name-only allowlist; listing
`Bash(codex:*)` there only adds the `Bash` tool to the pool, the parenthetical scope
is not parsed. Real command-level enforcement requires a PreToolUse hook, which is
what `.claude/hooks/readonly_guard.py` is. See work/ 或 ADR-0007 Context 段 for the
incident this fixes.

Stdlib only (no third-party deps): both consumers must run without any project
virtualenv activated.
"""

from __future__ import annotations

# Roles whose judgement must stay independent: no write access, and no more Bash
# than explicitly enumerated below. Adding a name here is a privilege *removal*
# decision (make a role read-only); removing a name is a privilege *grant* decision
# (let a role start mutating) — either way, changing this set changes what
# .claude/hooks/readonly_guard.py enforces at runtime, not just what
# scripts/validate_agents.py checks at commit time.
READONLY_AGENTS = frozenset(
    {
        "qa-reviewer",
        "qa-e2e",
        "tech-architect",
        "risk-compliance-officer",
    }
)

# Subset of READONLY_AGENTS whose role genuinely needs some Bash (today: qa-reviewer,
# to run `codex` for the cross-vendor second opinion and `git diff` to read the staged
# diff). Every other member of READONLY_AGENTS has zero Bash in its `tools:` line and
# gets a full Bash deny at runtime too — defence in depth, in case its tool pool is
# ever widened by mistake elsewhere (e.g. a future settings.json edit, a copy-paste
# frontmatter error). Do not add a name here without also adding matching patterns to
# READONLY_ALLOWED_BASH_PATTERNS below, and without security-engineer sign-off.
READONLY_BASH_SCOPED_AGENTS = frozenset({"qa-reviewer"})

# Declarative form, consumed by scripts/validate_agents.py to check the literal
# "Bash(...)" tokens a read-only agent's `tools:` line may contain. This is a
# *design-time* string check only — it does not, by itself, restrict anything at
# runtime. Runtime restriction is READONLY_ALLOWED_BASH_PATTERNS below.
READONLY_ALLOWED_BASH = frozenset({"Bash(codex:*)", "Bash(git diff:*)"})

# Runtime form, consumed by .claude/hooks/readonly_guard.py. Each entry is a regular
# expression matched with re.fullmatch() against one *subcommand* — i.e. the Bash
# command string after it has already been split on shell separators (&&, ||, ;, |,
# |&, &, newline) and stripped of leading/trailing whitespace. Every pattern is
# anchored (fullmatch, not search) and requires a word boundary after the literal
# prefix so "codexx" or "git diffusion" don't match.
#
# Adding an entry here is an explicit privilege decision, not a convenience: it must
# stay non-mutating and enumerable (a fixed, inspectable command surface).
#
# Interpreters, shells, and generic execution-environment wrappers never qualify,
# however narrow the pattern looks: `Bash(node:*)` allows
# `node -e "require('fs').writeFileSync(...)"`, and `Bash(npx playwright:*)` executes
# the project's own config / globalSetup — both are arbitrary code execution, i.e.
# technically identical to unscoped Bash. The same reasoning rules out `timeout`,
# `docker exec`, `devbox run`, `mise exec`, `direnv exec`, and similar wrappers even
# though Claude Code's own permission engine treats some of them as transparent for
# *allow*-rule matching — readonly_guard.py deliberately does NOT replicate that
# wrapper-stripping convenience, because for a hard deny-by-default gate, being
# stricter than necessary is safe and being more lenient than necessary is not. The
# invariant being protected is "a judge must not be able to modify what it judges",
# not "a judge must not run anything".
READONLY_ALLOWED_BASH_PATTERNS = (
    r"codex(?:\s.*)?",
    r"git\s+diff(?:\s.*)?",
)
