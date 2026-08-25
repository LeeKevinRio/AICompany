#!/usr/bin/env python3
"""Tests for readonly_guard.py.

Run with: python3 .claude/hooks/test_readonly_guard.py -v

Three layers:
- SplitterUnitTests / BashAllowedUnitTests: import the hook's internal functions
  directly (fast, precise on the splitter/tokenizer/matcher logic).
- PolicyConsistencyTests: check the BASH_RULES <-> downstream-constant invariant
  tech-architect required (V4/B1) — that "declared" and "enforced" can never drift
  apart because they're the same record, not two hand-synced lists.
- SubprocessBehaviourTests: invoke the hook exactly the way Claude Code does: pipe
  JSON on stdin to `python3 readonly_guard.py`, check the real process exit code.
  These are the tests that actually prove the fail-closed and deny-by-default
  properties, because they exercise the real main()/argv/exit-code path.

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
LIB_DIR = REPO_ROOT / ".claude" / "lib"
HOOK_SCRIPT = HOOK_DIR / "readonly_guard.py"

sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(LIB_DIR))

from readonly_guard import _bash_command_allowed, _split_subcommands, _tokenize, _Unparseable  # noqa: E402
from agent_policy import BASH_RULES, READONLY_ALLOWED_BASH  # noqa: E402


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


class TokenizeUnitTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_tokenize("git diff --stat"), ["git", "diff", "--stat"])

    def test_quotes_removed(self):
        self.assertEqual(
            _tokenize('codex exec --sandbox read-only "hello world"'),
            ["codex", "exec", "--sandbox", "read-only", "hello world"],
        )

    def test_unbalanced_quote_raises_valueerror(self):
        with self.assertRaises(ValueError):
            _tokenize("git diff -- 'oops")


class BashAllowedUnitTests(unittest.TestCase):
    def check(self, command, expect_allowed):
        allowed, reason = _bash_command_allowed(command, BASH_RULES)
        self.assertEqual(allowed, expect_allowed, msg=f"command={command!r} reason={reason!r}")

    # --- git diff: happy path (flag allowlist) --------------------------
    def test_bare_git_diff_stat(self):
        self.check("git diff --stat", True)

    def test_git_diff_name_only_with_ref(self):
        self.check("git diff --name-only HEAD~1", True)

    def test_git_diff_unified_context_flag(self):
        self.check("git diff -U200 a..b -- x.py", True)

    def test_git_diff_refs_and_paths_no_dashdash(self):
        self.check("git diff a..b -- x.py y.py", True)

    def test_git_diff_parent_ref_tilde(self):
        self.check("git diff ea2923c~1..6d564cc -- apps/x", True)

    def test_git_diff_two_parent_refs(self):
        self.check("git diff 694b374~1 694b374 --stat", True)

    def test_git_diff_extra_whitespace_tolerated(self):
        self.check("   git diff   --stat   ", True)

    def test_git_diff_quoted_semicolon_path_allowed(self):
        self.check("git diff -- 'weird;name.py'", True)

    def test_git_diff_anything_after_dashdash_allowed_as_pathspec(self):
        # Anything after a literal "--" is a pathspec to git, not re-parsed as a
        # flag — including strings that look like the exact flags we deny before
        # "--". This is standard "end of options" behaviour, not a loophole.
        self.check("git diff -- --output=looks_dangerous_but_is_a_filename", True)

    # --- git diff: CRITICAL-1 (security-engineer) and denylist-shaped flags ----
    def test_output_equals_flag_denied(self):
        self.check("git diff --output=/tmp/victim.py", False)

    def test_output_long_flag_space_form_denied(self):
        self.check("git diff --output /tmp/victim.py", False)

    def test_o_short_flag_denied(self):
        self.check("git diff -o /tmp/victim.py", False)

    def test_capital_o_orderfile_flag_denied(self):
        self.check("git diff -O /tmp/orderfile", False)

    def test_ext_diff_denied(self):
        self.check("git diff --ext-diff", False)

    def test_textconv_denied(self):
        self.check("git diff --textconv", False)

    def test_no_textconv_denied(self):
        self.check("git diff --no-textconv", False)

    def test_unknown_future_flag_denied_by_default(self):
        # Allowlist, not denylist: a flag nobody has named yet still gets denied.
        self.check("git diff --some-flag-nobody-thought-of", False)

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

    def test_bare_codex_version_denied(self):
        # Real historical usage (env probing), no longer allowed: exact-shape
        # matching means only the two sanctioned invocation forms pass.
        self.check("codex --version", False)

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

    # --- codex: happy path (exact shapes) --------------------------------
    def test_codex_review_prompt_shape_allowed(self):
        self.check(
            'codex exec --sandbox read-only "你是資深 code reviewer，請審查 staged diff"',
            True,
        )

    def test_codex_review_uncommitted_shape_allowed(self):
        self.check("codex exec review --uncommitted", True)

    # --- codex: CRITICAL-2 (security-engineer) — sandbox/approval bypass -------
    def test_codex_dangerously_bypass_flag_appended_denied(self):
        self.check(
            'codex exec --sandbox read-only "x" --dangerously-bypass-approvals-and-sandbox',
            False,
        )

    def test_codex_yolo_alias_appended_denied(self):
        self.check('codex exec --sandbox read-only "x" --yolo', False)

    def test_codex_yolo_alias_before_sandbox_denied(self):
        self.check('codex exec --yolo --sandbox read-only "x"', False)

    def test_codex_approve_for_me_denied(self):
        self.check('codex exec --approve-for-me "x"', False)

    def test_codex_not_so_yolo_alias_denied(self):
        self.check('codex exec --not-so-yolo "x"', False)

    def test_codex_sandbox_workspace_write_denied(self):
        self.check('codex exec --sandbox workspace-write "x"', False)

    def test_codex_sandbox_danger_full_access_denied(self):
        self.check('codex exec --sandbox danger-full-access "x"', False)

    def test_codex_output_last_message_short_flag_denied(self):
        # -o writes the agent's last message to an arbitrary file — the codex
        # analogue of git diff's --output bug.
        self.check('codex exec --sandbox read-only -o /tmp/x "prompt"', False)

    def test_codex_output_last_message_long_flag_denied(self):
        self.check(
            'codex exec --sandbox read-only --output-last-message /tmp/x "prompt"', False
        )

    def test_codex_config_override_flag_denied(self):
        self.check('codex exec --sandbox read-only -c sandbox_mode="danger-full-access" "x"', False)

    def test_codex_profile_flag_denied(self):
        self.check('codex exec --sandbox read-only --profile evil "x"', False)

    def test_codex_add_dir_flag_denied(self):
        self.check('codex exec --sandbox read-only --add-dir / "x"', False)

    def test_codex_bypass_hook_trust_denied(self):
        self.check('codex exec review --uncommitted --dangerously-bypass-hook-trust', False)

    def test_codex_review_uncommitted_plus_extra_token_denied(self):
        self.check("codex exec review --uncommitted --json", False)

    def test_codex_missing_sandbox_flag_denied(self):
        self.check('codex exec "just a prompt, no --sandbox at all"', False)

    def test_codex_wrong_subcommand_order_denied(self):
        self.check('codex --sandbox read-only exec "x"', False)

    def test_codex_extra_leading_token_denied(self):
        self.check('sudo codex exec --sandbox read-only "x"', False)

    # --- bypass attempts required by the task ----------------------------
    def test_chained_malicious_subcommand_denied(self):
        self.check('codex exec --sandbox read-only "x"; rm -rf /', False)

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
        self.check('codex exec --sandbox read-only "x"\nrm -rf /', False)

    def test_timeout_wrapper_not_stripped_denied(self):
        # Deliberately stricter than Claude Code's own allow-rule convenience
        # behaviour: we do not strip `timeout`.
        self.check('timeout 30 codex exec --sandbox read-only "x"', False)

    def test_npx_wrapper_denied(self):
        self.check("npx codex --version", False)

    def test_docker_exec_wrapper_denied(self):
        self.check("docker exec sandbox codex --version", False)

    def test_devbox_run_wrapper_denied(self):
        self.check("devbox run codex --version", False)

    def test_env_assignment_prefix_denied(self):
        self.check('FOO=bar codex exec --sandbox read-only "x"', False)

    def test_env_command_prefix_denied(self):
        self.check('env FOO=bar codex exec --sandbox read-only "x"', False)

    def test_xargs_wrapper_denied(self):
        self.check("xargs codex --version", False)

    def test_word_boundary_codexx_denied(self):
        self.check("codexx --version", False)

    def test_word_boundary_git_diffusion_denied(self):
        self.check("git diffusion --stat", False)

    def test_brace_expansion_denied(self):
        self.check("git diff HEAD^{tree}", False)

    def test_paren_denied(self):
        self.check("git diff (--stat)", False)

    def test_bang_denied(self):
        self.check("git diff !$", False)

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
        self.check("git diff --stat;", False)


class PolicyConsistencyTests(unittest.TestCase):
    """tech-architect V4/B1: 'declared without enforced' must be structurally
    impossible, not just conventionally avoided. These tests pin that down."""

    def test_declared_count_matches_rule_count(self):
        # READONLY_ALLOWED_BASH is *derived* from BASH_RULES (tuple(r.declared for
        # r in BASH_RULES)), so this is close to tautological by construction — but
        # it's exactly the invariant a future edit could break by reintroducing a
        # hand-maintained parallel constant, so it's pinned here explicitly.
        self.assertEqual(len(READONLY_ALLOWED_BASH), len(BASH_RULES))

    def test_every_rule_has_a_nonempty_rationale(self):
        for rule in BASH_RULES:
            self.assertTrue(
                rule.rationale and len(rule.rationale.strip()) > 10,
                msg=f"rule {rule.label!r} has no real rationale",
            )

    def test_every_declared_token_has_at_least_one_matching_rule(self):
        # The actual "declared without enforced" check: every distinct token that
        # scripts/validate_agents.py would accept in an agent's `tools:` line must
        # have at least one BASH_RULES entry that can actually match something.
        declared_tokens = set(READONLY_ALLOWED_BASH)
        for token in declared_tokens:
            rules_for_token = [r for r in BASH_RULES if r.declared == token]
            self.assertTrue(
                rules_for_token, msg=f"{token!r} is declared but has zero enforcing rules"
            )

    def test_qa_reviewer_frontmatter_only_declares_known_tokens(self):
        qa_reviewer_md = REPO_ROOT / ".claude" / "agents" / "qa-reviewer.md"
        text = qa_reviewer_md.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("tools:"):
                tools = [t.strip() for t in line.split(":", 1)[1].split(",")]
                for tool in tools:
                    if tool.startswith("Bash("):
                        self.assertIn(
                            tool,
                            READONLY_ALLOWED_BASH,
                            msg=f"qa-reviewer.md declares {tool!r}, not in READONLY_ALLOWED_BASH",
                        )
                break
        else:
            self.fail("qa-reviewer.md has no tools: line")

    def test_word_boundary_variants_rejected_by_every_rule(self):
        # Not a regex-fullmatch check anymore (codex rules are exact-shape, not
        # regex) — but the underlying property tech-architect asked for still
        # holds and is checked directly against each rule's match() function.
        bad_token_sets = [
            ["codexx", "exec", "--sandbox", "read-only", "x"],
            ["git", "diffusion", "--stat"],
        ]
        for tokens in bad_token_sets:
            for rule in BASH_RULES:
                self.assertFalse(
                    rule.match(tokens),
                    msg=f"rule {rule.label!r} incorrectly matched {tokens!r}",
                )


class SubprocessBehaviourTests(unittest.TestCase):
    """Exercise the real script via subprocess: exit codes are what Claude Code
    actually checks, so these are the tests that matter most."""

    # --- pass-through: not our concern ------------------------------------
    def test_main_thread_no_agent_type_bash_passes(self):
        result = call("Bash", agent_type=_UNSET, command="rm -rf /")
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
        # Even a fully-sanctioned codex shape is denied: this role has zero Bash budget.
        result = call(
            "Bash",
            agent_type="risk-compliance-officer",
            command='codex exec --sandbox read-only "x"',
        )
        self.assertEqual(result.returncode, 2)

    def test_tech_architect_bash_git_diff_still_denied(self):
        result = call("Bash", agent_type="tech-architect", command="git diff HEAD~1")
        self.assertEqual(result.returncode, 2)

    def test_qa_e2e_bash_denied(self):
        result = call("Bash", agent_type="qa-e2e", command="ls")
        self.assertEqual(result.returncode, 2)

    # --- qa-reviewer Bash: allow-list happy path ----------------------------
    def test_qa_reviewer_codex_review_prompt_allowed(self):
        result = call(
            "Bash",
            agent_type="qa-reviewer",
            command='codex exec --sandbox read-only "review this diff"',
        )
        self.assertEqual(result.returncode, 0)

    def test_qa_reviewer_codex_review_uncommitted_allowed(self):
        result = call("Bash", agent_type="qa-reviewer", command="codex exec review --uncommitted")
        self.assertEqual(result.returncode, 0)

    def test_qa_reviewer_git_diff_allowed(self):
        result = call(
            "Bash", agent_type="qa-reviewer", command="git diff 7c4795a..adb4aab --stat"
        )
        self.assertEqual(result.returncode, 0)

    def test_qa_reviewer_chained_allowed_allowed(self):
        result = call(
            "Bash",
            agent_type="qa-reviewer",
            command='codex exec review --uncommitted && git diff --stat',
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

    def test_qa_reviewer_git_diff_output_flag_denied(self):
        # security-engineer CRITICAL-1 repro, at the subprocess/exit-code level.
        result = call(
            "Bash",
            agent_type="qa-reviewer",
            command="git diff --output=/home/user/AICompany/apps/stock-desk/backend/app/main.py",
        )
        self.assertEqual(result.returncode, 2)

    def test_qa_reviewer_codex_dangerously_bypass_denied(self):
        # security-engineer CRITICAL-2 repro, at the subprocess/exit-code level.
        result = call(
            "Bash",
            agent_type="qa-reviewer",
            command=(
                'codex exec --sandbox read-only "x" '
                "--dangerously-bypass-approvals-and-sandbox"
            ),
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
        """If .claude/lib/agent_policy.py is unreachable, the hook must deny even
        a completely unrelated implementation-role call — never fail open just
        because its own dependency broke."""
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp) / "fake-repo"
            fake_hooks_dir = fake_root / ".claude" / "hooks"
            fake_hooks_dir.mkdir(parents=True)
            # Deliberately do NOT create fake_root / ".claude" / "lib" / "agent_policy.py".
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
