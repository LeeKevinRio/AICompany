"""Cache-busting ``?v=`` on the page script and stylesheet (FD-9 e2e finding)."""

from __future__ import annotations

import re
from pathlib import Path

from flight_deals.web.server import static_version
from tests.conftest import Harness

VERSION = re.compile(r"^[0-9a-f]{12}$")


def test_pages_reference_versioned_assets(harness: Harness) -> None:
    version = static_version()
    assert VERSION.match(version)
    for url in ("/", "/explore/compare", "/settings", "/comparisons/999"):
        text = harness.client.get(url).text
        assert f'src="/static/app.js?v={version}"' in text, url
        assert f'href="/static/app.css?v={version}"' in text, url
    script = harness.client.get(f"/static/app.js?v={version}")
    assert script.status_code == 200 and "initCompareForm" in script.text
    # Same-origin script: the CSP is unchanged.
    assert "script-src 'self'" in script.headers["content-security-policy"]


def test_version_follows_both_files(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text("console.log(1);", encoding="utf-8")
    (tmp_path / "app.css").write_text("body{}", encoding="utf-8")
    first = static_version(tmp_path)
    assert VERSION.match(first) and static_version(tmp_path) == first
    (tmp_path / "app.js").write_text("console.log(2);", encoding="utf-8")
    second = static_version(tmp_path)
    assert second != first
    (tmp_path / "app.css").write_text("body{color:red}", encoding="utf-8")
    assert static_version(tmp_path) not in (first, second)
