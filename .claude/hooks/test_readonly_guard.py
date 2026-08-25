#!/usr/bin/env python3
"""Tests for readonly_guard.py.

Run with: python3 .claude/hooks/test_readonly_guard.py -v

Two layers:
- Unit tests import the hook's internal functions directly (fast, precise on the
  splitter/matcher logic).
- Subprocess tests invoke the hook exactly the way Claude Code does: pipe JSON on
  stdin to `python3 readonly_guard.py`, check the real process exit code. These are
  the tests that actually prove the fail-closed and deny-by-default properties,
  because they exercise the real main()/argv/exit-code path, not just a function
  return value.

Stdlib only — this must run without any project virtualenv.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOK_DIR.parent.parent
HOOK_SCRIPT = HOOK_DIR / "readonly_guard.py"

sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from readonly_guard import _bash_command_allowed, _split_subcommands, _Unparseable  # noqa: E402
from agent_policy import READONLY_ALLOWED_BASH_PATTERNS  # noqa: E402


def run_hook(payload, cwd=None) -> subprocess.CompletedProcess:
    """Invoke the real script as a subprocess, exactly like Claude Code would."""
    if isinstance(payload, (dict, list)):
        stdin_bytes = json.dumps(payload).encode()
    else:
        stdin_bytes = payload  # already raw bytes/str, for malformed-input tests
        if isinstance(stdin_bytes, str):
            stdin_bytes = stdin_bytes.encode()
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        timeout=10,
    )


_UNSET = "__unset__"


def call(tool_name, agent_type=_UNSET, command=None, extra_input=None):
    data = {"tool_name": tool_name}
    if agent_type != _UNSET:
        data["agent_type"] = agent_type
    tool_input = dict(extra_input or {})
    if command is not None:
        tool_input["command"] = command
    if tool_input:
        data["tool_input"] = tool_input
    return run_hook(data)


class SplitterUnitTests(unittest.TestCase):
    def test_simple_two_char_operators(self):
        self.assertEqual(
            _split_subcommands("a && b || c |& d"),
            ["a", "b", "c", "d"],
        )

    def test_one_char_operators_and_newline(self):
        self.assertEqual(
            _split_subcommands("a; b | c & d\ne"),
            ["a", "b", "c", "d", "e"],
        )

    def test_semicolon_inside_single_quotes_not_split(self):
        self.assertEqual(
            _split_subcommands("git diff -- 'a;b'"),
            ["git diff -- 'a;b'"],
        )

    def test_semicolon_inside_double_quotes_not_split(self):
        self.assertEqual(
            _split_subcommands('git diff -- "a;b"'),
            ['git diff -- "a;b"'],
        )

    def test_escaped_semicolon_not_split(self):
        # Matches real bash semantics: `\;` outside quotes is a literal semicolon
        # character, not a command separator.
        self.assertEqual(
            _split_subcommands(r"codex --version \; rm -rf /"),
            [r"codex --version \; rm -rf /"],
        )

    def test_unterminated_single_quote_raises(self):
        with self.assertRaises(_Unparseable):
            _split_subcommands("git diff -- 'unterminated")

    def test_unterminated_double_quote_raises(self):
        with self.assertRaises(_Unparseable):
            _split_subcommands('git diff -- "unterminated')


class BashAllowedUnitTests(unittest.TestCase):
    def check(self, command, expect_allowed):
        allowed, reason = _bash_command_allowed(command, READONLY_ALLOWED_BASH_PATTERNS)
        self.assertEqual(allowed, expect_allowed, msg=f"command={command!r} reason={reason!r}")

    # --- happy path -----------------------------------------------------
    def test_bare_codex(self):
        self.check("codex --version", True)

    def test_bare_git_diff(self):
        self.check("git diff HEAD~1..HEAD -- foo.py", True)

    def test_two_allowed_subcommands_chained(self):
        self.check("codex --version && git diff --stat", True)

    def test_semicolon_chained_allowed(self):
        self.check("git diff a b -- x.py; codex --version", True)

    def test_extra_whitespace_tolerated(self):
        self.check("   git diff   --stat   ", True)

    def test_quoted_semicolon_argument_allowed(self):
        # ';' is inside quotes, part of a filename argument, not a real separator.
        self.check("git diff -- 'weird;name.py'", True)

    # --- historical over-broad usage now correctly denied ---------------
    def test_which_codex_denied(self):
        self.check("which codex", False)

    def test_grep_denied(self):
        self.check("grep -n foo bar.py", False)

    def test_sed_inplace_denied(self):
        self.check("sed -i 's/a/b/' file.py", False)

    def test_uv_run_pytest_denied(self):
        self.check("uv run pytest -q", False)

    def test_ls_denied(self):
        self.check("ls -la", False)

    def test_git_status_denied(self):
        self.check("git status", False)

    def test_git_checkout_denied(self):
        self.check("git checkout -- file", False)

    # --- actual historical incident commands (from the real transcripts) -
    def test_incident_sed_injection_denied(self):
        self.check(
            "sed -i '46a import app.kelly.store  # TEMP QA INJECTION' app/advice/limits.py",
            False,
        )

    def test_incident_python_heredoc_rewrite_denied(self):
        self.check(
            'python3 - <<\'EOF\'\np = "app/x.py"\nopen(p, "w").write("evil")\nEOF',
            False,
        )

    # --- bypass attempts required by the task ----------------------------
    def test_chained_malicious_subcommand_denied(self):
        self.check("codex --version; rm -rf /", False)

    def test_command_substitution_dollar_denied(self):
        self.check("codex $(rm -rf /)", False)

    def test_command_substitution_backtick_denied(self):
        self.check("git diff `cat /etc/passwd`", False)

    def test_process_substitution_input_denied(self):
        self.check("git diff <(rm -rf /) <(echo x)", False)

    def test_process_substitution_output_denied(self):
        self.check("codex --version >(rm -rf /)", False)

    def test_output_redirection_denied(self):
        self.check(
            "codex --version > /home/user/AICompany/apps/stock-desk/backend/app/main.py",
            False,
        )

    def test_append_redirection_denied(self):
        self.check("git diff --stat >> /tmp/x", False)

    def test_stderr_redirection_denied(self):
        self.check("codex --version 2> /tmp/x", False)

    def test_heredoc_denied(self):
        self.check("codex --version <<EOF\nx\nEOF", False)

    def test_newline_injection_denied(self):
        self.check("codex --version\nrm -rf /", False)

    def test_timeout_wrapper_not_stripped_denied(self):
        # Deliberately stricter than Claude Code's own allow-rule convenience
        # behaviour: we do not strip `timeout`.
        self.check("timeout 30 codex --version", False)

    def test_npx_wrapper_denied(self):
        self.check("npx codex --version", False)

    def test_docker_exec_wrapper_denied(self):
        self.check("docker exec sandbox codex --version", False)

    def test_devbox_run_wrapper_denied(self):
        self.check("devbox run codex --version", False)

    def test_env_assignment_prefix_denied(self):
        self.check("FOO=bar codex --version", False)

    def test_env_command_prefix_denied(self):
        self.check("env FOO=bar codex --version", False)

    def test_xargs_wrapper_denied(self):
        self.check("xargs codex --version", False)

    def test_word_boundary_codexx_denied(self):
        self.check("codexx --version", False)

    def test_word_boundary_git_diffusion_denied(self):
        self.check("git diffusion --stat", False)

    # --- malformed input --------------------------------------------------
    def test_empty_command_denied(self):
        self.check("", False)

    def test_whitespace_only_command_denied(self):
        self.check("   ", False)

    def test_none_command_denied(self):
        self.check(None, False)

    def test_non_string_command_denied(self):
        self.check(123, False)

    def test_unterminated_quote_denied(self):
        self.check("git diff -- 'unterminated", False)

    def test_trailing_separator_denied(self):
        self.check("codex --version;", False)


class SubprocessBehaviourTests(unittest.TestCase):
    """Exercise the real script via subprocess: exit codes are what Claude Code
    actually checks, so these are the tests that matter most."""

    # --- pass-through: not our concern ------------------------------------
    def test_main_thread_no_agent_type_bash_passes(self):
        result = call("Bash", agent_type="__unset__", command="rm -rf /")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_implementation_role_write_passes(self):
        result = call("Write", agent_type="dev-lead")
        self.assertEqual(result.returncode, 0)

    def test_implementation_role_arbitrary_bash_passes(self):
        result = call("Bash", agent_type="dev-lead", command="git commit -m x && git push")
        self.assertEqual(result.returncode, 0)

    def test_implementation_role_edit_passes(self):
        result = call("Edit", agent_type="qa-automation")
        self.assertEqual(result.returncode, 0)

    # --- Write/Edit denied for all four read-only roles --------------------
    def test_qa_reviewer_write_denied(self):
        result = call("Write", agent_type="qa-reviewer")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"qa-reviewer", result.stderr)

    def test_qa_reviewer_edit_denied(self):
        result = call("Edit", agent_type="qa-reviewer")
        self.assertEqual(result.returncode, 2)

    def test_risk_compliance_write_denied(self):
        result = call("Write", agent_type="risk-compliance-officer")
        self.assertEqual(result.returncode, 2)

    def test_tech_architect_edit_denied(self):
        result = call("Edit", agent_type="tech-architect")
        self.assertEqual(result.returncode, 2)

    def test_qa_e2e_write_denied(self):
        result = call("Write", agent_type="qa-e2e")
        self.assertEqual(result.returncode, 2)

    # --- Bash fully denied for the three non-scoped read-only roles --------
    def test_risk_compliance_bash_codex_still_denied(self):
        # Even the "safe" codex command is denied: this role has zero Bash budget.
        result = call("Bash", agent_type="risk-compliance-officer", command="codex --version")
        self.assertEqual(result.returncode, 2)

    def test_tech_architect_bash_git_diff_still_denied(self):
        result = call("Bash", agent_type="tech-architect", command="git diff HEAD~1")
        self.assertEqual(result.returncode, 2)

    def test_qa_e2e_bash_denied(self):
        result = call("Bash", agent_type="qa-e2e", command="ls")
        self.assertEqual(result.returncode, 2)

    # --- qa-reviewer Bash: allow-list happy path ----------------------------
    def test_qa_reviewer_codex_allowed(self):
        result = call("Bash", agent_type="qa-reviewer", command="codex --version")
        self.assertEqual(result.returncode, 0)

    def test_qa_reviewer_git_diff_allowed(self):
        result = call(
            "Bash", agent_type="qa-reviewer", command="git diff 7c4795a..adb4aab --stat"
        )
        self.assertEqual(result.returncode, 0)

    def test_qa_reviewer_chained_allowed_allowed(self):
        result = call(
            "Bash", agent_type="qa-reviewer", command="codex --version && git diff --stat"
        )
        self.assertEqual(result.returncode, 0)

    # --- qa-reviewer Bash: real historical excess usage now denied ---------
    def test_qa_reviewer_grep_denied(self):
        result = call("Bash", agent_type="qa-reviewer", command="grep -n foo bar.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"qa-reviewer", result.stderr)

    def test_qa_reviewer_sed_injection_denied(self):
        result = call(
            "Bash",
            agent_type="qa-reviewer",
            command="sed -i '46a import app.kelly.store' app/advice/limits.py",
        )
        self.assertEqual(result.returncode, 2)

    def test_qa_reviewer_command_substitution_denied(self):
        result = call("Bash", agent_type="qa-reviewer", command="codex $(rm -rf /)")
        self.assertEqual(result.returncode, 2)

    def test_qa_reviewer_redirection_denied(self):
        result = call(
            "Bash",
            agent_type="qa-reviewer",
            command="codex --version > /home/user/AICompany/x.py",
        )
        self.assertEqual(result.returncode, 2)

    def test_qa_reviewer_missing_command_denied(self):
        result = call("Bash", agent_type="qa-reviewer")  # no tool_input at all
        self.assertEqual(result.returncode, 2)

    # --- fail-closed on malformed hook input --------------------------------
    def test_malformed_json_denied(self):
        result = run_hook("{not valid json")
        self.assertEqual(result.returncode, 2)

    def test_empty_stdin_denied(self):
        result = run_hook(b"")
        self.assertEqual(result.returncode, 2)

    def test_top_level_json_array_denied(self):
        result = run_hook("[]")
        self.assertEqual(result.returncode, 2)

    def test_top_level_json_scalar_denied(self):
        result = run_hook("42")
        self.assertEqual(result.returncode, 2)

    def test_unicode_garbage_denied(self):
        result = run_hook("not even close to json 亂碼 {{{")
        self.assertEqual(result.returncode, 2)

    def test_policy_module_missing_denies_everyone(self):
        """If scripts/agent_policy.py is unreachable, the hook must deny even a
        completely unrelated implementation-role call — never fail open just
        because its own dependency broke."""
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp) / "fake-repo"
            fake_hooks_dir = fake_root / ".claude" / "hooks"
            fake_hooks_dir.mkdir(parents=True)
            # Deliberately do NOT create fake_root / "scripts" / "agent_policy.py".
            shutil.copy(HOOK_SCRIPT, fake_hooks_dir / "readonly_guard.py")

            result = subprocess.run(
                [sys.executable, str(fake_hooks_dir / "readonly_guard.py")],
                input=json.dumps(
                    {"tool_name": "Write", "agent_type": "dev-lead"}
                ).encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"fail-closed", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
