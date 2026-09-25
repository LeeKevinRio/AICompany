"""The approval and registration CLI (ADR-0012 C-31, T-19; D-6).

``approve`` refuses when any of ``--operator`` / ``--reviewer`` /
``--review-doc`` is missing, when the operator is not ``ceo`` / ``dev-lead``,
when ``quarterly_qa`` is not run by ``dev-lead``, when the review document is
missing, outside the repository, or does not name the ``run_id`` and the
``method_version`` -- and writes nothing then. On success the row carries the
document's repository path and git blob hash.

``register-version`` stamps the frozen commit of a clean tree, and only for a
known version named in a written record.
"""

from __future__ import annotations

import subprocess
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.store import SectorApprovalStore, SectorMethodRegistry, SectorStatsRepository
from app.services import sector_board
from app.services.sector_board import ApprovalRefused, approve, git_blob_hash, register_version
from tests.sector_board_helpers import stats_record

NOW = datetime(2029, 3, 13, 9, tzinfo=UTC)
RUN = "sector-rel-v1.0-L5-H5:2029-03-12:20290312T140000000000"


class _AllKnown:
    def existing_run_ids(self, run_ids: Collection[str]) -> frozenset[str]:
        return frozenset(run_ids)


@dataclass
class Desk:
    repo: Path
    stats: SectorStatsRepository
    approvals: SectorApprovalStore
    doc: Path


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    repo = tmp_path / "repo"
    (repo / "work" / "reviews").mkdir(parents=True)
    db = tmp_path / "main.db"
    stats = SectorStatsRepository(_AllKnown(), db)
    stats.save(stats_record(RUN, ("1", "2")))
    doc = repo / "work" / "reviews" / "risk-approve.md"
    doc.write_text(
        f"# 風控書面 APPROVE\n\nrun_id: {RUN}\nmethod_version: {V1.method_version}\n",
        encoding="utf-8",
    )
    return Desk(repo=repo, stats=stats, approvals=SectorApprovalStore(db), doc=doc)


def _approve(desk: Desk, **overrides: object) -> object:
    options: dict[str, object] = {
        "kind": "first_transition_risk",
        "run_id": RUN,
        "operator": "ceo",
        "reviewer": "risk-compliance-officer",
        "review_doc": desk.doc,
        "stats": desk.stats,
        "approvals": desk.approvals,
        "repo_root": desk.repo,
        "clock": lambda: NOW,
    }
    options.update(overrides)
    return approve(**options)  # type: ignore[arg-type]


def _nothing_written(desk: Desk) -> bool:
    return desk.approvals.list_for(V1.method_version) == ()


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


def test_a_complete_approval_records_the_document(desk: Desk) -> None:
    record = _approve(desk)
    stored = desk.approvals.list_for(V1.method_version)
    assert stored == (record,)
    (row,) = stored
    assert row.review_doc_path == "work/reviews/risk-approve.md"
    expected = subprocess.run(
        ["git", "hash-object", str(desk.doc)], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert row.review_doc_blob_hash == expected == git_blob_hash(desk.doc.read_bytes())
    assert (row.kind, row.operator, row.reviewer, row.approved_at) == (
        "first_transition_risk",
        "ceo",
        "risk-compliance-officer",
        NOW,
    )


def test_quarterly_qa_is_dev_lead_only(desk: Desk) -> None:
    with pytest.raises(ApprovalRefused):
        _approve(desk, kind="quarterly_qa", operator="ceo", reviewer="qa-reviewer")
    assert _nothing_written(desk)
    _approve(desk, kind="quarterly_qa", operator="dev-lead", reviewer="qa-reviewer")
    assert [row.kind for row in desk.approvals.list_for(V1.method_version)] == ["quarterly_qa"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"operator": "qa-reviewer"},
        {"operator": "risk-compliance-officer"},
        {"operator": ""},
        {"reviewer": "   "},
        {"kind": "self_approval"},
        {"run_id": "no-such-run"},
    ],
)
def test_bad_arguments_are_refused(desk: Desk, overrides: dict[str, object]) -> None:
    with pytest.raises(ApprovalRefused):
        _approve(desk, **overrides)
    assert _nothing_written(desk)


def test_the_review_document_must_exist_inside_the_repo(desk: Desk, tmp_path: Path) -> None:
    with pytest.raises(ApprovalRefused, match="不存在"):
        _approve(desk, review_doc=desk.repo / "work" / "reviews" / "missing.md")
    outside = tmp_path / "outside.md"
    outside.write_text(desk.doc.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ApprovalRefused, match="repo 內"):
        _approve(desk, review_doc=outside)
    assert _nothing_written(desk)


@pytest.mark.parametrize("dropped", [RUN, V1.method_version])
def test_the_review_document_must_name_the_run_and_the_version(desk: Desk, dropped: str) -> None:
    desk.doc.write_text(desk.doc.read_text(encoding="utf-8").replace(dropped, "…"), "utf-8")
    with pytest.raises(ApprovalRefused, match="未提及"):
        _approve(desk)
    assert _nothing_written(desk)


@pytest.mark.parametrize("missing", ["--operator", "--reviewer", "--review-doc"])
def test_the_cli_requires_every_credential_flag(missing: str) -> None:
    argv = [
        "approve",
        "--kind",
        "first_transition_risk",
        "--run-id",
        RUN,
        "--operator",
        "ceo",
        "--reviewer",
        "risk-compliance-officer",
        "--review-doc",
        "work/reviews/risk-approve.md",
    ]
    position = argv.index(missing)
    del argv[position : position + 2]
    with pytest.raises(SystemExit) as exited:
        sector_board.main(argv)
    assert exited.value.code == 2


def test_the_cli_rejects_a_read_only_role_as_operator() -> None:
    with pytest.raises(SystemExit) as exited:
        sector_board.main(
            [
                "approve",
                "--kind",
                "quarterly_qa",
                "--run-id",
                RUN,
                "--operator",
                "qa-reviewer",
                "--reviewer",
                "qa-reviewer",
                "--review-doc",
                "x.md",
            ]
        )
    assert exited.value.code == 2


# ---------------------------------------------------------------------------
# register-version
# ---------------------------------------------------------------------------


@dataclass
class _Git:
    head_value: str | None = "f00dfeed"
    clean_value: bool | None = True

    def head(self) -> str | None:
        return self.head_value

    def is_clean(self) -> bool | None:
        return self.clean_value


def _register(desk: Desk, tmp_path: Path, **overrides: object) -> str:
    options: dict[str, object] = {
        "method_version": V1.method_version,
        "operator": "dev-lead",
        "review_doc": desk.doc,
        "registry": SectorMethodRegistry(tmp_path / "main.db"),
        "git": _Git(),
        "repo_root": desk.repo,
        "clock": lambda: NOW,
    }
    options.update(overrides)
    return register_version(**options)  # type: ignore[arg-type]


def test_register_version_stamps_the_clean_commit(desk: Desk, tmp_path: Path) -> None:
    assert _register(desk, tmp_path) == "f00dfeed"
    row = SectorMethodRegistry(tmp_path / "main.db").get(V1.method_version)
    assert row is not None
    assert (row.frozen_commit, row.registered_at, row.counts_toward_m) == ("f00dfeed", NOW, False)
    with pytest.raises(ApprovalRefused, match="已登記"):
        _register(desk, tmp_path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"git": _Git(clean_value=False)},
        {"git": _Git(head_value=None)},
        {"method_version": "sector-rel-v9.9-L5-H5"},
        {"operator": "risk-compliance-officer"},
    ],
)
def test_register_version_refusals(
    desk: Desk, tmp_path: Path, overrides: dict[str, object]
) -> None:
    with pytest.raises(ApprovalRefused):
        _register(desk, tmp_path, **overrides)
    assert SectorMethodRegistry(tmp_path / "main.db").get(V1.method_version) is None


def test_register_version_needs_a_record_naming_the_version(desk: Desk, tmp_path: Path) -> None:
    desk.doc.write_text("# 沒有版本字串\n", encoding="utf-8")
    with pytest.raises(ApprovalRefused, match="未提及"):
        _register(desk, tmp_path)
