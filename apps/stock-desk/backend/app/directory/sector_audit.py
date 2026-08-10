"""TWSE sector-taxonomy audit -- diffs the official ``t187ap03_L`` 產業別
column against ``app.positions.sectors.TWSE_SECTORS``, the code's
core-approved closed list (see that module's PROVENANCE NOTICE).

## What this does and does not do

This module backs ``python -m app.directory.sync --verify-sectors``. It
produces a *diff report* for CEO / data-engineer to read and decide on. It
never writes to ``app/positions/sectors.py`` -- that file is a core-approved
list (FR-12), and only a human decision may change it. Silently "fixing" the
list from a single scrape would just replace one unverified guess with
another; the point of the audit is to surface the diff, not resolve it.

## Comparison categories

- ``official_only``: sector names the fetched official rows use that do not
  appear (verbatim) in ``TWSE_SECTORS``. Either a real gap in our list, or
  one of the two umbrella categories (電子工業 / 化學生技醫療) ``sectors.py``
  already documents as deliberately excluded -- this module does not try to
  tell those two cases apart (that would be guessing intent), it just lists
  what the official data used.
- ``local_only``: entries in ``TWSE_SECTORS`` that never appeared in the
  fetched official rows. Could mean the category is real but currently has
  zero listed companies, or that our list contains something TWSE does not
  use -- again, undecided here, deferred to a human.
- ``naming_diffs``: pairs equal after whitespace normalization only, not
  verbatim -- almost always a stray space/full-width space in the source
  data rather than a real taxonomy difference, so reported separately
  instead of being double-counted in both of the above buckets.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.directory.providers import SectorProfileEntry
from app.positions.sectors import TWSE_SECTORS

_WHITESPACE_RE = re.compile(r"[\s　]+")


def _normalize(name: str) -> str:
    """Collapse ASCII/full-width whitespace for comparison purposes only.

    Deliberately does not touch punctuation or characters -- anything beyond
    whitespace normalization would be guessing at an intended equivalence
    between two different strings, which is exactly the kind of silent "fix"
    this audit exists to avoid.
    """
    return _WHITESPACE_RE.sub("", name)


@dataclass(frozen=True)
class NamingDiff:
    """A (local, official) pair that match after whitespace normalization only."""

    local: str
    official: str


@dataclass(frozen=True)
class SectorComparisonReport:
    """Diff between ``TWSE_SECTORS`` (core-approved) and one fetch's official rows."""

    as_of: datetime
    source: str
    company_count: int
    known_sector_count: int
    official_sector_names: tuple[str, ...]
    local_only: tuple[str, ...]
    official_only: tuple[str, ...]
    naming_diffs: tuple[NamingDiff, ...]

    @property
    def has_findings(self) -> bool:
        return bool(self.local_only or self.official_only or self.naming_diffs)


def compare_sectors(
    entries: Sequence[SectorProfileEntry],
    *,
    as_of: datetime,
    source: str,
    known: Sequence[str] = TWSE_SECTORS,
) -> SectorComparisonReport:
    """Diff the fetched ``entries``' ``sector`` column against ``known`` (TWSE_SECTORS)."""
    official_names = sorted({entry.sector for entry in entries if entry.sector.strip()})
    official_set = set(official_names)
    known_set = set(known)

    raw_local_only = sorted(known_set - official_set)
    raw_official_only = sorted(official_set - known_set)

    naming_diffs: list[NamingDiff] = []
    matched_official: set[str] = set()
    for local_name in raw_local_only:
        for official_name in raw_official_only:
            if official_name in matched_official:
                continue
            if _normalize(local_name) == _normalize(official_name):
                naming_diffs.append(NamingDiff(local=local_name, official=official_name))
                matched_official.add(official_name)
                break

    matched_local = {diff.local for diff in naming_diffs}
    local_only = tuple(name for name in raw_local_only if name not in matched_local)
    official_only = tuple(name for name in raw_official_only if name not in matched_official)

    return SectorComparisonReport(
        as_of=as_of,
        source=source,
        company_count=len(entries),
        known_sector_count=len(known_set),
        official_sector_names=tuple(official_names),
        local_only=local_only,
        official_only=official_only,
        naming_diffs=tuple(naming_diffs),
    )


def render_terminal_lines(report: SectorComparisonReport) -> list[str]:
    """Short, human-readable summary for the CLI's stdout."""
    lines = [
        f"官方公司列數：{report.company_count}；官方產業別數：{len(report.official_sector_names)}；"
        f"本地清單（TWSE_SECTORS）產業別數：{report.known_sector_count}",
    ]
    if not report.has_findings:
        lines.append("比對結果：無差異。")
        return lines
    if report.official_only:
        lines.append(
            f"官方有、本地清單沒有（{len(report.official_only)} 項）："
            + "、".join(report.official_only)
        )
    if report.local_only:
        lines.append(
            f"本地清單有、這次官方資料沒有（{len(report.local_only)} 項）："
            + "、".join(report.local_only)
        )
    if report.naming_diffs:
        pairs = "；".join(f"{diff.local} vs {diff.official}" for diff in report.naming_diffs)
        lines.append(f"名稱用字差異（{len(report.naming_diffs)} 組，去空白後相同）：{pairs}")
    lines.append("不自動修改 app/positions/sectors.py；完整差異已寫入草稿報告，回報 CEO 轉裁決。")
    return lines


def render_markdown(report: SectorComparisonReport) -> str:
    """Render ``report`` as the ``work/research/產業清單覆核-<日期>.md`` draft."""
    lines = [
        f"# 產業清單覆核 -- {report.as_of.date().isoformat()}",
        "",
        "> 本檔案為 `python -m app.directory.sync --verify-sectors` 自動產生的**比對草稿**，"
        "非核可清單；`app/positions/sectors.py` 的清單**不會被本工具自動修改**，"
        "任何差異須經 CEO 裁決後才能改動該清單。",
        "",
        f"- 官方來源：`{report.source}`（TWSE OpenAPI `t187ap03_L` 上市公司基本資料，"
        "端點路徑與欄位名稱依官方文件推斷、未經即時回應驗證，"
        "見 `app/directory/providers.py` 檔頭「Sector-profile endpoint」一節）",
        f"- 官方資料公司列數：{report.company_count}",
        f"- 官方資料涵蓋產業別數：{len(report.official_sector_names)}",
        f"- 本地清單（`TWSE_SECTORS`）產業別數：{report.known_sector_count}",
        f"- as_of：{report.as_of.isoformat()}",
        "",
        "## 官方有、本地清單沒有",
        "",
    ]
    if report.official_only:
        lines.append(
            "官方資料出現、但不在 `TWSE_SECTORS` 中的產業別（可能是本地清單遺漏，"
            "也可能是 `電子工業`／`化學生技醫療` 這類本地清單已記載為刻意排除的上層彙總分類"
            "——本工具不臆測是哪一種，交 CEO 裁決）："
        )
        lines.extend(f"- {name}" for name in report.official_only)
    else:
        lines.append("（無差異）")
    lines += ["", "## 本地清單有、官方資料沒有", ""]
    if report.local_only:
        lines.append(
            "`TWSE_SECTORS` 中出現、但這次抓到的官方資料列裡沒有任何公司使用的產業別"
            "（可能是該分類目前無掛牌公司，也可能是本地清單本身有誤"
            "——本工具不臆測，交 CEO 裁決）："
        )
        lines.extend(f"- {name}" for name in report.local_only)
    else:
        lines.append("（無差異）")
    lines += ["", "## 名稱用字差異（去除空白後相同，字面不同）", ""]
    if report.naming_diffs:
        lines.append("| 本地清單 | 官方資料 |")
        lines.append("| --- | --- |")
        lines.extend(f"| `{diff.local}` | `{diff.official}` |" for diff in report.naming_diffs)
    else:
        lines.append("（無差異）")
    lines += [
        "",
        "## 下一步",
        "",
        "- 本報告不自動改 `app/positions/sectors.py`；上述差異回報 CEO 轉裁決。",
        "- 裁決結果需要修改清單時，由 data-engineer 依裁決結果另行提交變更"
        "（含 `sectors.py` 檔頭 PROVENANCE NOTICE 的同步更新）。",
        "",
    ]
    return "\n".join(lines)
