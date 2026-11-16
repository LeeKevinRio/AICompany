"""Tests for ``check_pinned_eol`` and the real-git preflight of ``pipeline_acceptance_real.py``.

ADR-0030 supplement 6 point 7 and TA C-8. Every repository here is a throw-away ``git init`` in
``tmp_path``; git's global and system configuration are replaced so the machine's own
``core.autocrlf`` cannot leak in. The ``.gitattributes`` under test is the real file of the
backend folder, copied into the temporary repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.pipeline_real_world import real

BACKEND = Path(__file__).resolve().parents[1]
ATTRIBUTES = BACKEND / ".gitattributes"
LF = b"# lock\nname = 'x'\nversion = '1'\n"
CRLF = LF.replace(b"\n", b"\r\n")
PIN = ("uv.lock",)


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "empty-gitconfig"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def make_repo(
    root: Path, *, attributes: bool, autocrlf: str | None, content: bytes = LF
) -> tuple[Path, Path]:
    """A repository with ``apps/stock-desk/backend/uv.lock`` committed; (repo, backend)."""
    repo = root / "repo"
    backend = repo / "apps" / "stock-desk" / "backend"
    backend.mkdir(parents=True)
    git(repo, "init", "-q")
    if autocrlf is not None:
        git(repo, "config", "core.autocrlf", autocrlf)
    if attributes:
        (backend / ".gitattributes").write_bytes(ATTRIBUTES.read_bytes())
    (backend / "uv.lock").write_bytes(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo, backend


# --- the attribute file itself (TA C-8) ---


def test_the_backend_attribute_file_pins_uv_lock_to_lf() -> None:
    # The uv.lock line stays first and unchanged; CG-2 (M-7, ADR-0030 supplement 7
    # addendum 2 point 5) adds the two rule file lines after it.
    assert ATTRIBUTES.read_bytes() == (
        b"uv.lock text eol=lf\n"
        b"/app/outlook/rules/h3.yaml text eol=lf\n"
        b"/app/outlook/rules/h5.yaml text eol=lf\n"
    )


def test_the_root_attribute_file_is_not_changed_by_this_work() -> None:
    root = BACKEND.parents[2] / ".gitattributes"
    assert root.read_text() == (
        "# Windows batch files must keep CRLF line endings on checkout.\n"
        "*.bat text eol=crlf\n"
        "*.sh text eol=lf\n"
    )


def test_git_ls_files_eol_of_the_real_uv_lock_is_lf_lf() -> None:
    listing = subprocess.run(
        ["git", "ls-files", "--eol", "--", "uv.lock"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert listing.split("\t")[0].split()[:2] == ["i/lf", "w/lf"]
    assert "attr/text eol=lf" in listing


# --- check_pinned_eol in a temporary repository ---


def test_lf_work_tree_is_ok(tmp_path: Path) -> None:
    _repo, backend = make_repo(tmp_path, attributes=True, autocrlf=None)
    assert real.check_pinned_eol(backend, PIN) is True


def test_crlf_work_tree_is_a_stop(tmp_path: Path) -> None:
    _repo, backend = make_repo(tmp_path, attributes=True, autocrlf=None)
    (backend / "uv.lock").write_bytes(CRLF)
    assert real.check_pinned_eol(backend, PIN) is False


def test_check_pinned_eol_changes_nothing(tmp_path: Path) -> None:
    repo, backend = make_repo(tmp_path, attributes=True, autocrlf="true")
    (backend / "uv.lock").write_bytes(CRLF)
    config_before = (repo / ".git" / "config").read_bytes()
    assert real.check_pinned_eol(backend, PIN) is False
    assert (backend / "uv.lock").read_bytes() == CRLF
    assert (repo / ".git" / "config").read_bytes() == config_before
    assert git(repo, "config", "--get", "core.autocrlf").strip() == "true"


def test_a_content_change_with_lf_endings_is_also_a_stop(tmp_path: Path) -> None:
    _repo, backend = make_repo(tmp_path, attributes=True, autocrlf=None)
    (backend / "uv.lock").write_bytes(LF + b"extra = 1\n")
    assert real.check_pinned_eol(backend, PIN) is False


def test_the_second_evidence_alone_also_stops(tmp_path: Path) -> None:
    # Bytes equal the blob, but git reports the work tree as CRLF over an LF index entry.
    _repo, backend = make_repo(tmp_path, attributes=True, autocrlf=None)
    blob = (backend / "uv.lock").read_bytes()

    def fake(cwd: Path, args: Any) -> tuple[int, bytes]:
        if args[0] == "cat-file":
            return 0, blob
        return 0, b"i/lf    w/crlf  attr/text eol=lf\tuv.lock\n"

    assert real.check_pinned_eol(backend, PIN, git=fake) is False
    assert real.check_pinned_eol(backend, PIN) is True


def test_a_missing_file_or_a_git_failure_is_a_stop(tmp_path: Path) -> None:
    _repo, backend = make_repo(tmp_path, attributes=True, autocrlf=None)
    assert real.check_pinned_eol(backend, ("absent.lock",)) is False
    assert real.check_pinned_eol(tmp_path, PIN) is False  # not a repository
    (backend / "uv.lock").unlink()
    assert real.check_pinned_eol(backend, PIN) is False


def test_the_attribute_makes_checkout_head_repair_a_crlf_work_tree(tmp_path: Path) -> None:
    # The coordinator's remedy: git checkout HEAD -- uv.lock turns a CRLF work tree back to LF.
    repo, backend = make_repo(tmp_path, attributes=True, autocrlf=None)
    (backend / "uv.lock").write_bytes(CRLF)
    assert real.check_pinned_eol(backend, PIN) is False
    git(repo, "checkout", "HEAD", "--", "apps/stock-desk/backend/uv.lock")
    assert (backend / "uv.lock").read_bytes() == LF
    assert real.check_pinned_eol(backend, PIN) is True


def test_with_autocrlf_true_the_attribute_keeps_a_fresh_checkout_lf(tmp_path: Path) -> None:
    repo, backend = make_repo(tmp_path, attributes=True, autocrlf="true")
    (backend / "uv.lock").unlink()
    git(repo, "checkout", "HEAD", "--", "apps/stock-desk/backend/uv.lock")
    assert (backend / "uv.lock").read_bytes() == LF
    assert real.check_pinned_eol(backend, PIN) is True
    assert real.core_autocrlf(backend) == "true"


def test_control_without_the_attribute_autocrlf_true_writes_crlf(tmp_path: Path) -> None:
    # Why the attribute is needed: the same checkout without it produces CRLF and is a stop.
    repo, backend = make_repo(tmp_path, attributes=False, autocrlf="true")
    (backend / "uv.lock").unlink()
    git(repo, "checkout", "HEAD", "--", "apps/stock-desk/backend/uv.lock")
    assert (backend / "uv.lock").read_bytes() == CRLF
    assert real.check_pinned_eol(backend, PIN) is False


@pytest.mark.parametrize(
    ("setting", "word"),
    [(None, "unset"), ("false", "false"), ("input", "input"), ("true", "true"), ("yes", "other")],
)
def test_core_autocrlf_is_reported_as_a_closed_word(
    tmp_path: Path, setting: str | None, word: str
) -> None:
    _repo, backend = make_repo(tmp_path, attributes=True, autocrlf=setting)
    assert real.core_autocrlf(backend) == word


# --- the preflight with a real git ---


def _ready(root: Path) -> tuple[Path, Path, Path]:
    repo, backend = make_repo(root, attributes=True, autocrlf=None)
    for name in ("app", "tests", "scripts"):
        (backend / name).mkdir()
        (backend / name / "keep.py").write_text("x = 1\n")
    (backend / "data").mkdir()
    (backend / "data" / "stock-desk.db").write_bytes(b"synthetic")
    (repo / ".gitignore").write_text("data/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "more")
    git(repo, "update-ref", "refs/remotes/origin/product/stock-desk", "HEAD")
    home = root / "home"
    home.mkdir()
    return repo, backend, home


def _preflight(backend: Path, home: Path) -> Any:
    return real.preflight(
        backend_dir=backend,
        work=home / "w",
        env={},
        port_check=lambda: False,
        git=real.run_git,
    )


def test_the_preflight_passes_on_a_clean_published_checkout(tmp_path: Path) -> None:
    repo, backend, home = _ready(tmp_path)
    found = _preflight(backend, home)
    assert found.git_head == git(repo, "rev-parse", "HEAD").strip()
    assert found.autocrlf == "unset"


def test_the_preflight_stops_on_an_uncommitted_change(tmp_path: Path) -> None:
    _repo, backend, home = _ready(tmp_path)
    (backend / "app" / "keep.py").write_text("x = 2\n")
    with pytest.raises(real.RunStop) as stop:
        _preflight(backend, home)
    assert stop.value.kind == "git_dirty"


def test_the_preflight_stops_on_an_untracked_file_in_the_code_folders(tmp_path: Path) -> None:
    _repo, backend, home = _ready(tmp_path)
    (backend / "tests" / "new_test.py").write_text("x = 1\n")
    with pytest.raises(real.RunStop) as stop:
        _preflight(backend, home)
    assert stop.value.kind == "git_dirty"


def test_the_preflight_stops_when_head_is_not_on_the_published_branch(tmp_path: Path) -> None:
    repo, backend, home = _ready(tmp_path)
    (backend / "app" / "keep.py").write_text("x = 2\n")
    git(repo, "commit", "-q", "-am", "local only")
    with pytest.raises(real.RunStop) as stop:
        _preflight(backend, home)
    assert stop.value.kind == "head_unpublished"


def test_the_preflight_stops_on_a_crlf_lockfile(tmp_path: Path) -> None:
    _repo, backend, home = _ready(tmp_path)
    (backend / "uv.lock").write_bytes(CRLF)
    with pytest.raises(real.RunStop) as stop:
        _preflight(backend, home)
    # ``git status`` sees the line-ending change as clean or modified depending on the filters;
    # either way a stop, and it is never fixed by the script.
    assert stop.value.kind in {"git_dirty", "eol_differs"}
    assert (backend / "uv.lock").read_bytes() == CRLF


def test_the_preflight_stops_outside_a_repository(tmp_path: Path) -> None:
    backend = tmp_path / "stock-desk" / "backend"
    (backend / "data").mkdir(parents=True)
    (backend / "data" / "stock-desk.db").write_bytes(b"synthetic")
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(real.RunStop) as stop:
        _preflight(backend, home)
    assert stop.value.kind == "git_unusable"
