#!/usr/bin/env python3
"""PreToolUse hook: real runtime enforcement of the read-only agent boundary.

Registered in .claude/settings.json under hooks.PreToolUse with
matcher "Write|Edit|Bash". Fires for every Write/Edit/Bash call from any agent
(main thread or subagent) and decides, per call, whether to hard-block it.

Why this exists
----------------
Before this hook, "read-only" was enforced only by:
  1. Prose in each agent's frontmatter red-line section ("絕不改 code" etc.) — this
     is a *suggestion to the model*, not a control. Claude Code's own docs are
     explicit: "Permission rules are enforced by Claude Code, not by the model.
     Instructions in your prompt or CLAUDE.md ... don't change what Claude Code
     allows."
  2. A `tools:` frontmatter line like `Bash(codex:*), Bash(git diff:*)` — this looks
     like a command-level scope, but Claude Code's `tools:` field is a coarse,
     tool-name-only allowlist. Listing `Bash(codex:*)` only adds the `Bash` *tool* to
     the agent's pool; the parenthetical scope is not parsed or enforced there.
     Confirmed against Claude Code's own docs, which say fine-grained command
     restriction needs a PreToolUse hook, precisely because the `tools:` field can't
     do it.
  3. `.claude/settings.json` permissions.allow — but a bare `"Bash"` entry (added to
     let implementation roles skip approval prompts) matches every Bash call, making
     any narrower `Bash(codex:*)` entry in the same allow list redundant.

The net effect, confirmed against real session transcripts: qa-reviewer (declared
read-only, `tools: ... Bash(codex:*), Bash(git diff:*)`) ran hundreds of unrelated
Bash commands across many sessions, including three that directly rewrote real
source/test files via `sed -i` / `python3 <<EOF ... write file ... EOF`, ran tests
against the mutated version, then reverted with `git checkout --`. Nothing in the
system stopped it; it stopped itself. See ADR-0007 Context for the incident record.

This hook is the actual control. It is deny-by-default for read-only agents and
fail-closed on any internal error (see `main()`).

Design decisions, stated so a future reader doesn't have to reverse-engineer them:

- We do NOT rely on the hook `if` matcher for filtering. Claude Code's own docs
  call the `if` filter "best-effort" and say to fail open when a command can't be
  parsed, then explicitly say: "use the permission system rather than a hook [`if`
  filter] to enforce a hard allow or deny." So all logic lives in this script's own
  body, invoked unconditionally for every Write/Edit/Bash call (matcher only, no
  `if`), and this script itself must never fail open.

- We do NOT replicate Claude Code's own Bash-matching convenience behaviour (wrapper
  stripping for `timeout`/`nice`/`nohup`/etc., env-assignment stripping, `xargs`
  stripping). That behaviour exists to make *allow* rules more convenient for a
  human interactively approving things. For a hard deny-by-default gate, more
  leniency is strictly worse: it only ever *widens* what a subcommand can match.
  Not stripping means some legitimate uses (e.g. `timeout 30 codex --version`) get
  denied — an acceptable false positive. Silently allowing `docker exec x codex` or
  `npx codex` past a naive prefix check would not be acceptable.

- We do NOT attempt to parse `$(...)`, backticks, process substitution, or output
  redirection safely. Any occurrence of `$`, `` ` ``, `<`, or `>` anywhere in the raw
  command (including inside quotes) is a blanket deny for read-only agents. codex and
  git diff usage never legitimately needs any of these; the blanket rule trades a few
  false positives (e.g. a path containing `<` or `>`, vanishingly rare) for closing
  an entire class of injection / exfiltration / silent-overwrite vectors (command
  substitution hiding a second command, process substitution, and output redirection
  overwriting an arbitrary file regardless of whether the "outer" command like
  `git diff` succeeds).

- Fail-closed: the whole decision path (stdin read, JSON parse, policy import,
  command splitting, pattern matching) runs inside one try/except in `main()`. Any
  exception denies the current tool call via exit code 2, which Claude Code's docs
  say blocks unconditionally — "even a JSON permissionDecision of allow can't
  override it" — regardless of what exit code Python would otherwise have produced.
  We deliberately never let an unhandled exception reach the interpreter's default
  handler, because that would exit 1, and Claude Code's docs say only exit 2 is
  guaranteed to block; other codes may not.

Known residual risk (documented honestly, not claimed away):
- This is a hand-written parser, not Claude Code's own (undisclosed, presumably more
  battle-tested) Bash-matching engine. It has not been fuzzed. It is deliberately
  strict/over-broad on denial to bias failures toward "blocks something legitimate"
  rather than "allows something dangerous", but a sufficiently creative shell
  construct this script's author didn't think of could still slip through the
  subcommand-splitting logic (see `_split_subcommands`) even though the blanket
  dangerous-character deny should catch most realistic shell-level bypass attempts.
- An earlier version of this hook matched each subcommand with a loose regex
  (`git\s+diff(?:\s.*)?`, `codex(?:\s.*)?`). security-engineer found and reproduced
  two CRITICAL bypasses against it: `git diff --output=<path>` overwrites an
  arbitrary file (git's own `-o`/`--output` flag — nothing to do with shell
  redirection, so the dangerous-character check never saw it), and any flag
  appended after "codex" — most importantly
  `--dangerously-bypass-approvals-and-sandbox` (alias `--yolo`), confirmed against
  Codex CLI's own source to unconditionally override `--sandbox read-only` — would
  also pass. Both are now closed by moving to the structural, per-tool matchers in
  `.claude/lib/agent_policy.py` (`BASH_RULES`): an explicit flag-allowlist for
  `git diff`, and exact-shape matching for `codex`. Residual risk from *this*
  design: the git-diff flag allowlist is only as complete as the code review that
  approved it (a `git diff` flag this reviewer didn't think of, that turns out to
  also be able to write, would need to be caught the same way `--output` was —
  by someone specifically looking for it); the codex exact-shape matcher is safer
  by construction (nothing except the two named forms can match at all) but is
  only correct insofar as this hook's author read Codex CLI's actual source
  correctly and Codex CLI doesn't change that behaviour in a future release.
- The currently declared whitelist (`codex`, `git diff`, and only the specific
  forms enumerated in `.claude/lib/agent_policy.py`) is much narrower than
  qa-reviewer's actual historical workflow (grep, sed -n, pytest, mypy, ruff, uv
  run, ls, cat, wc, find, git status/log/show, plain `codex --version`, ...).
  Enforcing it as-is will likely block read-only agents' normal work until
  CEO/tech-architect decide whether to broaden `BASH_RULES`. That is a policy
  decision this hook does not make on its own.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

# Characters that, anywhere in a raw Bash command string (quoted or not), cause an
# immediate deny for read-only agents. See module docstring for why these cover
# command substitution ($(...), `...`), process substitution (<(...), >(...)),
# output/error redirection (>, >>, &>, 2>), heredocs (<<EOF), and input redirection
# (<) in one pass, without needing to correctly parse shell quoting for them.
# {}!() added on security-engineer's non-blocking suggestion: no proven bypass found
# through any of them (security-engineer tried brace/paren mid-command syntax-error
# cases and `!` under non-interactive `bash -c`, which has histexpand off), and
# real qa-reviewer usage never needs them, so this gate's "block more than strictly
# necessary" default applies cleanly.
#
# `~` was in that suggested set too but is NOT included here: it is not "cost free"
# — real historical qa-reviewer usage relies on it constantly for parent-commit
# refs (`ea2923c~1`, `694b374~1`, ...), confirmed against the incident transcripts,
# and blanket-denying it would break the git-diff allowlist's actual purpose rather
# than just being conservative. `~` alone (not part of `~(`, `~/`, or similar) has
# no known shell-expansion risk in a non-interactive, non-login `bash -c` context
# used the way Claude Code invokes commands (tilde expansion only applies at the
# start of a word, which `_match_git_diff`'s per-token allowlist already
# constrains), so leaving it out is a deliberate, evidence-based exception, not an
# oversight.
_DANGEROUS_CHARS = ("$", "`", "<", ">", "{", "}", "!", "(", ")")

# Two-character shell operators, checked before the one-character ones so "&&" isn't
# mis-split as two "&" separators (which would also be wrong, since a lone "&"
# backgrounds a job — still a valid separator, just not the same one).
_TWO_CHAR_OPERATORS = ("&&", "||", "|&")
_ONE_CHAR_OPERATORS = (";", "|", "&", "\n")


class _Unparseable(Exception):
    """Raised when a command can't be split with confidence; always denies."""


def _split_subcommands(command: str) -> list[str]:
    """Split a shell command into subcommands on &&, ||, ;, |, |&, &, and newline.

    Quote-aware: does not split on a separator that appears inside a '...' or "..."
    span, and does not split on an escaped character. Raises _Unparseable if a quote
    is left open at the end of the string (a sign of truncation or deliberate
    obfuscation) rather than guessing.
    """
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(command)
    in_single = False
    in_double = False

    while i < n:
        ch = command[i]

        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            if ch == "\\" and i + 1 < n:
                buf.append(ch)
                buf.append(command[i + 1])
                i += 2
                continue
            buf.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue

        # Not inside any quote.
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue

        two = command[i : i + 2]
        if two in _TWO_CHAR_OPERATORS:
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in _ONE_CHAR_OPERATORS:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    if in_single or in_double:
        raise _Unparseable("unterminated quote")

    parts.append("".join(buf))
    return [p.strip() for p in parts]


def _contains_dangerous_construct(command: str) -> bool:
    return any(tok in command for tok in _DANGEROUS_CHARS)


def _tokenize(subcommand: str) -> list[str]:
    """Split one subcommand into shell words (argv-style), quotes removed.

    Delegates to shlex in POSIX mode rather than hand-rolling a second parser: we
    already used a hand-written quote-aware scanner for _split_subcommands (which
    has to recognise shell *operators*, something shlex doesn't do), but plain
    word-splitting with quote removal is exactly what shlex is for, and using the
    standard library here instead of more bespoke logic means one less parser
    security-engineer (or anyone else) has to independently verify against real
    bash semantics. Raises ValueError on unbalanced quotes, same as
    _split_subcommands' _Unparseable — the caller treats both as "deny".
    """
    return shlex.split(subcommand, posix=True)


def _bash_command_allowed(command: object, rules: "tuple") -> tuple[bool, str]:
    """Return (allowed, reason). reason is only meaningful when allowed is False.

    `rules` is agent_policy.BASH_RULES (or the subset applicable to the calling
    agent — today all of READONLY_BASH_SCOPED_AGENTS share the same rule set, but
    the parameter stays generic rather than hardcoding that).
    """
    if not isinstance(command, str) or not command.strip():
        return False, "指令為空或非字串"

    if _contains_dangerous_construct(command):
        return False, (
            "指令含 $ ` < > { } ~ ! ( ) 其中之一"
            "（命令替換/程序替換/重導向/heredoc/其他 shell 特殊語法一律阻擋）"
        )

    try:
        subcommands = _split_subcommands(command)
    except _Unparseable as exc:
        return False, f"指令無法安全拆解子命令（{exc}）"

    if not subcommands:
        return False, "拆解後沒有子命令"

    for sub in subcommands:
        if not sub:
            return False, "存在空的子命令（例如多餘的分隔符）"
        try:
            tokens = _tokenize(sub)
        except ValueError as exc:
            return False, f"子命令無法安全拆解為 shell words（{exc}）：{sub!r}"
        if not tokens:
            return False, f"子命令拆解後沒有任何 token：{sub!r}"
        if not any(rule.match(tokens) for rule in rules):
            return False, f"子命令不在任何白名單規則內：{sub!r}"

    return True, ""


def _decide(data: dict) -> int:
    """Return the process exit code: 2 to deny/block, 0 to allow/not-intervene."""
    # Import here (not at module top level) so any failure — missing file, syntax
    # error, whatever — is caught by the single try/except in main() and denies,
    # instead of crashing the interpreter before main() even starts (which would
    # exit 1, not the guaranteed-blocking exit 2).
    # .claude/lib, not scripts/ — see agent_policy.py's module docstring for why
    # (tech-architect ruling, ADR-0007 review).
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
    from agent_policy import (
        BASH_RULES,
        READONLY_AGENTS,
        READONLY_BASH_SCOPED_AGENTS,
    )

    tool_name = data.get("tool_name")
    agent_type = data.get("agent_type")
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    if agent_type not in READONLY_AGENTS:
        # Main thread, or an implementation role. Not our concern — CEO's
        # zero-prompt policy for implementation roles stays untouched.
        return 0

    if tool_name in ("Write", "Edit"):
        print(
            f"readonly_guard: 阻擋 — {agent_type} 是唯讀角色，不得使用 {tool_name}。",
            file=sys.stderr,
        )
        return 2

    if tool_name == "Bash":
        if agent_type not in READONLY_BASH_SCOPED_AGENTS:
            print(
                f"readonly_guard: 阻擋 — {agent_type} 是唯讀角色且未被授予任何 Bash "
                "白名單（見 .claude/lib/agent_policy.py READONLY_BASH_SCOPED_AGENTS），"
                "一律阻擋 Bash。",
                file=sys.stderr,
            )
            return 2

        command = tool_input.get("command")
        allowed, reason = _bash_command_allowed(command, BASH_RULES)
        if not allowed:
            print(
                f"readonly_guard: 阻擋 — {agent_type} 的 Bash 指令不在白名單內。"
                f"原因：{reason}。指令：{command!r}",
                file=sys.stderr,
            )
            return 2
        return 0

    # Matcher is "Write|Edit|Bash"; anything else reaching here is unexpected, but
    # for a read-only agent, unrecognised is denied too (fail-closed), not allowed.
    print(
        f"readonly_guard: 阻擋 — {agent_type} 是唯讀角色，未知工具 {tool_name!r} "
        "一律阻擋（fail-closed）。",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("hook 輸入的最外層不是 JSON object")
        return _decide(data)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — deliberate catch-all, see module docstring
        print(
            f"readonly_guard: fail-closed 阻擋（腳本內部錯誤，非業務判斷）：{exc!r}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
