"""Single source of truth for which agents are read-only and what Bash they may run.

Two independent consumers read this module and must never define their own copy:

- `scripts/validate_agents.py` — static check: does an agent's `.md` frontmatter
  declare a `tools:` line that stays within policy? (design-time)
- `.claude/hooks/readonly_guard.py` — runtime check: does an actual tool call from
  a read-only agent stay within policy? (execution-time, the real enforcement)

This module lives under `.claude/lib/`, not `scripts/`, on tech-architect's ruling:
`.claude/` already depends on itself (validate_agents.py is fundamentally a linter
*for* `.claude/`, so that dependency direction pre-exists and is its whole point),
while `.claude/` had zero dependency on `scripts/` before this file existed. Putting
policy here adds a module to an edge that already exists instead of growing a new
one. It also lowers the blast radius of an unrelated refactor: `scripts/` is a
generic-sounding directory that tends to get touched for reasons that have nothing
to do with agent policy (a new build script, a rename to `tools/`, packaging
changes) — and because `.claude/hooks/readonly_guard.py` fails closed (denies
Write/Edit/Bash for *everyone*, not just read-only agents, if this import breaks;
see readonly_guard.py's module docstring), an import path a future refactor doesn't
expect to matter is exactly the kind of thing that causes a company-wide outage
nobody saw coming.

Background: before this file existed, both checks lived only as prose in agent
frontmatter (`tools: Read, Grep, Glob, Bash(codex:*), Bash(git diff:*)`) and as a
comment in the validator. Neither was ever enforced by Claude Code at the command
level — the `tools:` frontmatter field is a coarse, tool-name-only allowlist; listing
`Bash(codex:*)` there only adds the `Bash` tool to the pool, the parenthetical scope
is not parsed. Real command-level enforcement requires a PreToolUse hook. See
ADR-0007 Context for the incident this fixes.

Design note on BASH_RULES (tech-architect V4 / security-engineer CRITICAL-1/2):
the original version of this module had two *parallel* constants — a declared-token
set for the validator and a regex-pattern tuple for the hook — kept in sync only by
convention. Two things forced a redesign:

1. tech-architect (ADR-0007 review) pointed out the parallel-constants shape lets
   "declare a capability without actually enforcing it" be written down without
   anything catching it — the exact failure mode this whole mechanism exists to
   close. A single BASH_RULES tuple, with the validator's token and the hook's
   matcher on the *same record*, makes that failure mode a type error, not a
   discipline problem.
2. security-engineer then found that the regex-pattern approach itself was
   unsound, independent of the sync problem: `git\s+diff(?:\s.*)?` allows
   `git diff --output=<path>` to overwrite an arbitrary file (git's own
   `--output`/`-o` flag, nothing to do with shell redirection, so the `<`/`>`
   blanket deny in readonly_guard.py never sees it) — reproduced against the hook
   itself, `git diff --output=<path>` gets exit 0. And `codex(?:\s.*)?` allows any
   trailing flags after the literal word "codex", including
   `--dangerously-bypass-approvals-and-sandbox` (alias `--yolo`), which per Codex
   CLI's own source (openai/codex, codex-rs/utils/cli/src/shared_options.rs) is
   `global(true)` on the `codex exec` subcommand and unconditionally overrides
   `--sandbox read-only` — confirmed by reading codex-rs/cli/src/main.rs's own
   resolution logic (`sandbox_mode = if dangerously_bypass_approvals_and_sandbox
   { None } else { shared.sandbox_mode }`). A prefix regex can't defend against a
   flag appended after the "safe-looking" part of the command; only fully
   enumerating what's allowed can.

Given that, each BASH_RULES entry now carries a `match(tokens)` callable that
receives the *already shell-tokenized* subcommand (see readonly_guard.py's
`_tokenize`) and decides allow/deny structurally, per-tool:

- git diff: prefix must be literally ["git", "diff"], then every flag token (one
  starting with "-") before a literal "--" must be in an explicit allowlist of
  known-harmless flags; a literal "--" switches to "everything after this is a
  pathspec, not re-parsed as a flag by git" and is unconditionally allowed. This is
  an allowlist, not a denylist of the flags security named
  (-o/--output/-O/--ext-diff/--textconv/--no-textconv/-c): a denylist only stops
  the flags someone thought to name, an allowlist stops everything not named safe.
- codex: exact-shape match against the literal command forms documented as the
  company's actual sanctioned usage in `.claude/commands/review.md` step 2 (the
  custom-prompt headless review) and its 備註 (the `codex exec review --uncommitted`
  alternative). No flag-allowlist model for codex: its surface (config profiles,
  `-c` overrides, `--add-dir`, model overrides, ...) is large, changes with every
  Codex CLI release, and several individual flags widen write/bypass capability in
  ways that are hard to enumerate safely (e.g. `--profile` can layer in an
  arbitrary config.toml). Constraining to the *exact* documented shape sidesteps
  needing to reason about that whole surface: nothing except the two known-good
  forms can ever match, by construction.

Stdlib only (no third-party deps): both consumers must run without any project
virtualenv activated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

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
# ever widened by mistake elsewhere. Do not add a name here without also adding
# matching BASH_RULES entries, and without security-engineer sign-off.
READONLY_BASH_SCOPED_AGENTS = frozenset({"qa-reviewer"})


def _tokens_are(tokens: Sequence[str], *expected: str) -> bool:
    return list(tokens) == list(expected)


_GIT_DIFF_ALLOWED_FLAGS = frozenset(
    {
        "--stat",
        "--name-only",
        "--name-status",
        "--numstat",
        "--shortstat",
        "-p",
        "--patch",
    }
)
_GIT_DIFF_UNIFIED_CONTEXT_RE = re.compile(r"-U\d+")  # e.g. -U0, -U200, -U1000


def _match_git_diff(tokens: Sequence[str]) -> bool:
    """git diff <flags-from-allowlist>* [--] <anything, as pathspecs>*

    Everything before a literal "--" that starts with "-" must be an explicitly
    allowed read-only flag; anything else before "--" (not starting with "-") is a
    ref/range/commit-ish and is always allowed. A literal "--" switches to "rest is
    pathspec" and every remaining token is allowed unconditionally, because git
    itself stops treating tokens after "--" as flags — this is standard "end of
    options" behaviour, not something this matcher has to trust the caller about.
    """
    if len(tokens) < 2 or tokens[0] != "git" or tokens[1] != "diff":
        return False
    seen_dashdash = False
    for tok in tokens[2:]:
        if seen_dashdash:
            continue
        if tok == "--":
            seen_dashdash = True
            continue
        if tok.startswith("-"):
            if tok in _GIT_DIFF_ALLOWED_FLAGS or _GIT_DIFF_UNIFIED_CONTEXT_RE.fullmatch(tok):
                continue
            return False
        # Not a flag: a ref, a commit range (a..b / a...b), or a bare path. None of
        # these can make git *write* anything, unlike -o/--output/-O.
    return True


def _match_codex_review_prompt(tokens: Sequence[str]) -> bool:
    """codex exec --sandbox read-only "<prompt>" — exactly the shape documented in
    .claude/commands/review.md step 2. Exactly 5 tokens, nothing appended or
    inserted: an extra token anywhere (e.g. a trailing
    --dangerously-bypass-approvals-and-sandbox) fails this length/position check
    before it ever gets a chance to matter."""
    return (
        len(tokens) == 5
        and tokens[0] == "codex"
        and tokens[1] == "exec"
        and tokens[2] == "--sandbox"
        and tokens[3] == "read-only"
    )


def _match_codex_review_uncommitted(tokens: Sequence[str]) -> bool:
    """codex exec review --uncommitted — the alternative shape documented in
    .claude/commands/review.md 備註. Exact 4-token match, same reasoning as above."""
    return _tokens_are(tokens, "codex", "exec", "review", "--uncommitted")


@dataclass(frozen=True)
class BashRule:
    # Literal token checked against an agent's `tools:` frontmatter line by
    # scripts/validate_agents.py. Multiple rules may share the same `declared`
    # value (today: the two codex shapes both declare as "Bash(codex:*)", because
    # that's the one token qa-reviewer.md actually writes) — READONLY_ALLOWED_BASH
    # below is a tuple, not a set, precisely so record count stays visible and
    # equal to len(BASH_RULES) even when declared values repeat; see
    # test_readonly_guard.py's consistency tests.
    declared: str
    # Short id for messages/tests.
    label: str
    # Why this exact shape and nothing looser — required, not decorative: a rule
    # with no rationale is a rule nobody had to justify.
    rationale: str
    # Given the already shell-tokenized subcommand (see readonly_guard.py
    # `_tokenize`), return True iff this rule allows it.
    match: Callable[[Sequence[str]], bool]


BASH_RULES: tuple[BashRule, ...] = (
    BashRule(
        declared="Bash(git diff:*)",
        label="git-diff",
        rationale=(
            "qa-reviewer reads the staged/committed diff to review it. Flags that "
            "only change *how much* is shown (--stat, --name-only, -U<n>, ...) are "
            "harmless; git's own -o/--output/-O write an arbitrary file regardless "
            "of whether the diff itself is read-only, so flags are allowlisted, "
            "not denylisted — see module docstring, security-engineer CRITICAL-1."
        ),
        match=_match_git_diff,
    ),
    BashRule(
        declared="Bash(codex:*)",
        label="codex-review-prompt",
        rationale=(
            "Exact shape from .claude/commands/review.md step 2: the company's "
            "actual cross-vendor review invocation. --sandbox read-only is only "
            "meaningful if nothing after it can widen it again, hence exact-length "
            "match — see module docstring, security-engineer CRITICAL-2."
        ),
        match=_match_codex_review_prompt,
    ),
    BashRule(
        declared="Bash(codex:*)",
        label="codex-review-uncommitted",
        rationale=(
            "Exact shape from .claude/commands/review.md 備註 (alternative "
            "invocation using Codex's built-in review subcommand)."
        ),
        match=_match_codex_review_uncommitted,
    ),
)

# Declarative form, consumed by scripts/validate_agents.py to check the literal
# "Bash(...)" tokens a read-only agent's `tools:` line may contain. Derived from
# BASH_RULES, not hand-maintained — this is what makes "add a declared token
# without adding an enforced rule" a change to BASH_RULES (impossible to do
# separately) instead of a second place someone has to remember to update.
READONLY_ALLOWED_BASH: tuple[str, ...] = tuple(rule.declared for rule in BASH_RULES)
