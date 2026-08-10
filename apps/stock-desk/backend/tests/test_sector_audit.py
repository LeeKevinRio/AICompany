"""Unit tests for the TWSE sector-taxonomy audit (``app.directory.sector_audit``).

Directly constructs ``SectorProfileEntry`` objects rather than routing
through the adapter/fixture -- the adapter's own parsing is covered in
``test_directory_providers.py``; here the goal is pinning the diff logic's
three buckets precisely.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.directory.providers import SectorProfileEntry
from app.directory.sector_audit import (
    NamingDiff,
    compare_sectors,
    render_markdown,
    render_terminal_lines,
)

AS_OF = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
SOURCE = "twse_openapi_t187ap03_L"


def _entry(symbol: str, name: str, sector: str) -> SectorProfileEntry:
    return SectorProfileEntry(symbol=symbol, name=name, sector=sector, source=SOURCE, as_of=AS_OF)


def test_compare_sectors_no_findings_when_official_matches_known_exactly() -> None:
    entries = [_entry("2330", "台積電", "半導體業"), _entry("1101", "台泥", "水泥工業")]

    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("半導體業", "水泥工業"))

    assert report.has_findings is False
    assert report.official_only == ()
    assert report.local_only == ()
    assert report.naming_diffs == ()
    assert report.company_count == 2
    assert report.official_sector_names == ("半導體業", "水泥工業")


def test_compare_sectors_flags_official_only() -> None:
    """A sector TWSE's data uses that our closed list never enumerates."""
    entries = [_entry("8888", "測試電子控股", "電子工業")]

    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("半導體業",))

    assert report.official_only == ("電子工業",)
    assert report.local_only == ("半導體業",)
    assert report.naming_diffs == ()


def test_compare_sectors_flags_local_only_when_no_company_uses_it() -> None:
    """A local category that this fetch's companies never used."""
    entries = [_entry("2330", "台積電", "半導體業")]

    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("半導體業", "農業科技業"))

    assert report.local_only == ("農業科技業",)
    assert report.official_only == ()


def test_compare_sectors_separates_whitespace_naming_diffs_from_real_diffs() -> None:
    """Full-width/ASCII whitespace differences must not double-count as real gaps."""
    entries = [
        _entry("9921", "測試巨大機械", "電機　機械"),  # full-width space inside
        _entry("8888", "測試電子控股", "電子工業"),  # genuinely absent from local list
    ]

    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("電機機械",))

    assert report.naming_diffs == (NamingDiff(local="電機機械", official="電機　機械"),)
    assert report.local_only == ()  # matched away by the naming diff, not double-counted
    assert report.official_only == ("電子工業",)  # real gap, unaffected


def test_compare_sectors_deduplicates_repeated_official_sector_names() -> None:
    entries = [
        _entry("2330", "台積電", "半導體業"),
        _entry("2454", "聯發科", "半導體業"),
    ]

    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("半導體業",))

    assert report.official_sector_names == ("半導體業",)
    assert report.company_count == 2


def test_render_terminal_lines_reports_no_findings() -> None:
    entries = [_entry("2330", "台積電", "半導體業")]
    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("半導體業",))

    lines = render_terminal_lines(report)

    assert any("無差異" in line for line in lines)


def test_render_terminal_lines_summarizes_all_three_buckets() -> None:
    entries = [
        _entry("9921", "測試巨大機械", "電機　機械"),
        _entry("8888", "測試電子控股", "電子工業"),
    ]
    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("電機機械", "農業科技業"))

    lines = render_terminal_lines(report)
    joined = "\n".join(lines)

    assert "官方有、本地清單沒有" in joined
    assert "電子工業" in joined
    assert "本地清單有、這次官方資料沒有" in joined
    assert "農業科技業" in joined
    assert "名稱用字差異" in joined
    assert "電機機械" in joined
    assert "不自動修改 app/positions/sectors.py" in joined


def test_render_markdown_never_claims_sectors_py_was_changed() -> None:
    entries = [_entry("8888", "測試電子控股", "電子工業")]
    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=("半導體業",))

    markdown = render_markdown(report)

    assert "不會被本工具自動修改" in markdown
    assert "電子工業" in markdown
    assert "半導體業" in markdown  # local_only, printed under the second section
    assert "CEO 裁決" in markdown
    assert "產業清單覆核" in markdown
