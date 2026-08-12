"""Unit tests for the TWSE sector-taxonomy audit (``app.directory.sector_audit``).

Directly constructs ``SectorProfileEntry`` objects rather than routing
through the adapter/fixture -- the adapter's own parsing (including that
``sector`` is a raw TWSE code, not a name) is covered in
``test_directory_providers.py``; here the goal is pinning the diff logic's
four buckets (matched / official_only / local_only / naming_diffs) plus the
UNKNOWN_CODE finding precisely. Most tests inject a small synthetic
``code_to_name`` map rather than the real
``app.directory.twse_sector_codes.TWSE_SECTOR_CODE_TO_NAME`` table, so they
stay independent of that table's real contents (which has its own coverage
test in ``tests/test_twse_sector_codes.py``).
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


def _entry(symbol: str, name: str, sector_code: str) -> SectorProfileEntry:
    return SectorProfileEntry(
        symbol=symbol, name=name, sector=sector_code, source=SOURCE, as_of=AS_OF
    )


def test_compare_sectors_no_findings_when_official_matches_known_exactly() -> None:
    entries = [_entry("2330", "台積電", "24"), _entry("1101", "台泥", "01")]
    code_to_name = {"24": "半導體業", "01": "水泥工業"}

    report = compare_sectors(
        entries,
        as_of=AS_OF,
        source=SOURCE,
        known=("半導體業", "水泥工業"),
        code_to_name=code_to_name,
    )

    assert report.has_findings is False
    assert report.official_only == ()
    assert report.local_only == ()
    assert report.naming_diffs == ()
    assert report.unknown_codes == ()
    assert report.matched == ("半導體業", "水泥工業")
    assert report.company_count == 2
    assert report.official_sector_codes == ("01", "24")
    # official_sector_names is sorted alphabetically, not by insertion order.
    assert report.official_sector_names == tuple(sorted(("半導體業", "水泥工業")))


def test_compare_sectors_flags_official_only() -> None:
    """A resolved name TWSE's data uses that our closed list never enumerates."""
    entries = [_entry("9188", "測試存託憑證", "91")]
    code_to_name = {"91": "存託憑證"}

    report = compare_sectors(
        entries, as_of=AS_OF, source=SOURCE, known=("半導體業",), code_to_name=code_to_name
    )

    assert report.official_only == ("存託憑證",)
    assert report.local_only == ("半導體業",)
    assert report.naming_diffs == ()
    assert report.matched == ()
    assert report.unknown_codes == ()


def test_compare_sectors_flags_local_only_when_no_company_uses_it() -> None:
    """A local category that this fetch's companies never used."""
    entries = [_entry("2330", "台積電", "24")]
    code_to_name = {"24": "半導體業"}

    report = compare_sectors(
        entries,
        as_of=AS_OF,
        source=SOURCE,
        known=("半導體業", "農業科技業"),
        code_to_name=code_to_name,
    )

    assert report.local_only == ("農業科技業",)
    assert report.official_only == ()
    assert report.matched == ("半導體業",)


def test_compare_sectors_flags_unknown_code_separately_from_official_only() -> None:
    """A code with no entry in the mapping table must not be silently dropped."""
    entries = [
        _entry("2330", "台積電", "24"),
        _entry("9921", "測試未知代碼列", "99"),
    ]
    code_to_name = {"24": "半導體業"}

    report = compare_sectors(
        entries, as_of=AS_OF, source=SOURCE, known=("半導體業",), code_to_name=code_to_name
    )

    assert report.unknown_codes == ("99",)
    assert report.has_findings is True
    # The unknown code contributes no resolved name, so it must not leak
    # into official_only/official_sector_names as if it were a real gap.
    assert report.official_only == ()
    assert "99" not in report.official_sector_names
    assert report.official_sector_codes == ("24", "99")
    assert report.matched == ("半導體業",)


def test_compare_sectors_deduplicates_repeated_unknown_codes() -> None:
    entries = [
        _entry("9921", "測試未知代碼列一", "99"),
        _entry("9922", "測試未知代碼列二", "99"),
    ]

    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=(), code_to_name={})

    assert report.unknown_codes == ("99",)


def test_compare_sectors_separates_whitespace_naming_diffs_from_real_diffs() -> None:
    """Full-width/ASCII whitespace differences must not double-count as real gaps.

    A code resolving to a name with stray whitespace would be a mapping-table
    bug, not a genuine TWSE OpenAPI quirk (unlike when the raw field itself
    used to be a free-text name) -- this test keeps the defensive
    normalization logic covered via an injected ``code_to_name`` map.
    """
    entries = [
        _entry("9921", "測試巨大機械", "05"),  # resolves to a whitespace variant
        _entry("9188", "測試存託憑證", "91"),  # genuinely absent from local list
    ]
    code_to_name = {"05": "電機　機械", "91": "存託憑證"}  # full-width space inside "05"

    report = compare_sectors(
        entries, as_of=AS_OF, source=SOURCE, known=("電機機械",), code_to_name=code_to_name
    )

    assert report.naming_diffs == (NamingDiff(local="電機機械", official="電機　機械"),)
    assert report.local_only == ()  # matched away by the naming diff, not double-counted
    assert report.official_only == ("存託憑證",)  # real gap, unaffected
    assert report.unknown_codes == ()


def test_compare_sectors_deduplicates_repeated_official_sector_names() -> None:
    entries = [
        _entry("2330", "台積電", "24"),
        _entry("2454", "聯發科", "24"),
    ]
    code_to_name = {"24": "半導體業"}

    report = compare_sectors(
        entries, as_of=AS_OF, source=SOURCE, known=("半導體業",), code_to_name=code_to_name
    )

    assert report.official_sector_names == ("半導體業",)
    assert report.company_count == 2


def test_render_terminal_lines_reports_no_findings() -> None:
    entries = [_entry("2330", "台積電", "24")]
    code_to_name = {"24": "半導體業"}
    report = compare_sectors(
        entries, as_of=AS_OF, source=SOURCE, known=("半導體業",), code_to_name=code_to_name
    )

    lines = render_terminal_lines(report)

    assert any("無差異" in line for line in lines)


def test_render_terminal_lines_summarizes_all_buckets_including_unknown_code() -> None:
    entries = [
        _entry("9921", "測試巨大機械", "05"),
        _entry("9188", "測試存託憑證", "91"),
        _entry("9922", "測試未知代碼列", "99"),
    ]
    code_to_name = {"05": "電機　機械", "91": "存託憑證"}
    report = compare_sectors(
        entries,
        as_of=AS_OF,
        source=SOURCE,
        known=("電機機械", "農業科技業"),
        code_to_name=code_to_name,
    )

    lines = render_terminal_lines(report)
    joined = "\n".join(lines)

    assert "UNKNOWN_CODE" in joined
    assert "99" in joined
    assert "官方有、本地清單沒有" in joined
    assert "存託憑證" in joined
    assert "本地清單有、這次官方資料沒有" in joined
    assert "農業科技業" in joined
    assert "名稱用字差異" in joined
    assert "電機機械" in joined
    assert "不自動修改 app/positions/sectors.py" in joined


def test_render_markdown_never_claims_sectors_py_was_changed() -> None:
    entries = [_entry("9188", "測試存託憑證", "91")]
    code_to_name = {"91": "存託憑證"}
    report = compare_sectors(
        entries, as_of=AS_OF, source=SOURCE, known=("半導體業",), code_to_name=code_to_name
    )

    markdown = render_markdown(report)

    assert "不會被本工具自動修改" in markdown
    assert "存託憑證" in markdown
    assert "半導體業" in markdown  # local_only, printed under its own section
    assert "CEO 裁決" in markdown
    assert "產業清單覆核" in markdown


def test_render_markdown_surfaces_unknown_code_prominently() -> None:
    entries = [_entry("9922", "測試未知代碼列", "99")]
    report = compare_sectors(entries, as_of=AS_OF, source=SOURCE, known=(), code_to_name={})

    markdown = render_markdown(report)

    assert "UNKNOWN_CODE" in markdown
    assert "99" in markdown
    assert "twse_sector_codes.py" in markdown
