"""The ``forecast_record:`` log lines (risk-compliance RC-331, RC-333 (a)).

* RC-331: ``recorder.DISK_DIFFERS_WARNING`` is, at run time, the text approved in
  the RC-331～RC-335 record (extracted from the record, never typed here), and
  the superseded wording with its imperative clause is gone from ``app/``.
"""

from __future__ import annotations

from pathlib import Path

from app.forecast import recorder as recorder_module
from tests import approved_copy

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_rc331_the_disk_differs_warning_is_the_approved_text() -> None:
    approved = approved_copy.disk_differs_line()
    assert recorder_module.DISK_DIFFERS_WARNING == approved
    assert approved.startswith("forecast_record: ") and approved.isascii()
    assert "\n" not in approved


def test_rc331_the_superseded_clause_is_gone_from_app() -> None:
    offenders = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if "restart the scheduler process to load them" in path.read_text(encoding="utf-8")
    )
    assert offenders == []
