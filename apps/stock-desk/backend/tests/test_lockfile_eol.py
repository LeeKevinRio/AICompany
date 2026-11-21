"""Line-ending tests for ``uv.lock``: the backend attribute file keeps it LF on every checkout.

ADR-0030 supplement 6 point 7 (the root fix for the lockfile line endings) and supplement 12
point 1 (these tests were moved here when the real-data pipeline acceptance tool was retired).
The LF pin keeps ``lockfile_sha256`` in ``runtime_json`` stable; that property outlives the tool.

Every repository here is a throw-away ``git init`` in ``tmp_path``; git's global and system
configuration are replaced so the machine's own ``core.autocrlf`` cannot leak in. The
``.gitattributes`` under test is the real file of the backend folder, copied into the temporary
repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ATTRIBUTES = BACKEND / ".gitattributes"
LF = b"# lock\nname = 'x'\nversion = '1'\n"
CRLF = LF.replace(b"\n", b"\r\n")


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


def test_with_autocrlf_true_the_attribute_keeps_a_fresh_checkout_lf(tmp_path: Path) -> None:
    repo, backend = make_repo(tmp_path, attributes=True, autocrlf="true")
    (backend / "uv.lock").unlink()
    git(repo, "checkout", "HEAD", "--", "apps/stock-desk/backend/uv.lock")
    assert (backend / "uv.lock").read_bytes() == LF


def test_control_without_the_attribute_autocrlf_true_writes_crlf(tmp_path: Path) -> None:
    # Why the attribute is needed: the same checkout without it produces CRLF and is a stop.
    repo, backend = make_repo(tmp_path, attributes=False, autocrlf="true")
    (backend / "uv.lock").unlink()
    git(repo, "checkout", "HEAD", "--", "apps/stock-desk/backend/uv.lock")
    assert (backend / "uv.lock").read_bytes() == CRLF
