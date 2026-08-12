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

## Two-step comparison: code first, then name

CEO's first real run of this tool (2026-08-12, against production TWSE data)
found that ``t187ap03_L``'s ``產業別`` column is a two-digit **code**
(e.g. ``"24"``), not a Chinese name -- the comparison below therefore first
resolves each row's code through ``app.directory.twse_sector_codes`` and
*then* diffs the resolved names against ``TWSE_SECTORS``. A code with no
entry in that mapping table is its own, separate finding (``unknown_codes``,
"UNKNOWN_CODE") rather than being silently skipped or miscompared as if it
were a name -- an incomplete code table is exactly the kind of gap that must
surface, not be papered over.

## Comparison categories

- ``matched``: resolved official names that appear verbatim in
  ``TWSE_SECTORS`` -- the two sides agree.
- ``official_only``: resolved names the fetched official rows use that do
  not appear (verbatim) in ``TWSE_SECTORS``. Either a real gap in our list,
  or a code (like ``91`` 存託憑證) that is not really an "industry" in the
  same sense the rest of the taxonomy is -- this module does not try to tell
  those cases apart (that would be guessing intent), it just lists what the
  official data resolved to.
- ``local_only``: entries in ``TWSE_SECTORS`` that never appeared (after
  code resolution) in the fetched official rows. Could mean the category is
  real but currently has zero listed companies, or that our list contains
  something TWSE does not use -- again, undecided here, deferred to a human.
- ``naming_diffs``: resolved-name/local-name pairs equal after whitespace
  normalization only, not verbatim -- kept as a defensive check (a code
  resolving to a name with stray whitespace would be a mapping-table bug,
  not a real taxonomy difference), reported separately instead of being
  double-counted in both of the above buckets.
- ``unknown_codes``: codes the fetched official rows used that have no entry
  in ``app.directory.twse_sector_codes.TWSE_SECTOR_CODE_TO_NAME`` at all --
  reported separately and prominently, since this means the mapping table
  itself needs a human to confirm and add the missing code, not a taxonomy
  decision about ``TWSE_SECTORS``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.directory.providers import SectorProfileEntry
from app.directory.twse_sector_codes import TWSE_SECTOR_CODE_TO_NAME
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
    official_sector_codes: tuple[str, ...]
    official_sector_names: tuple[str, ...]
    matched: tuple[str, ...]
    local_only: tuple[str, ...]
    official_only: tuple[str, ...]
    naming_diffs: tuple[NamingDiff, ...]
    unknown_codes: tuple[str, ...]

    @property
    def has_findings(self) -> bool:
        return bool(
            self.local_only or self.official_only or self.naming_diffs or self.unknown_codes
        )


def compare_sectors(
    entries: Sequence[SectorProfileEntry],
    *,
    as_of: datetime,
    source: str,
    known: Sequence[str] = TWSE_SECTORS,
    code_to_name: Mapping[str, str] = TWSE_SECTOR_CODE_TO_NAME,
) -> SectorComparisonReport:
    """Resolve the fetched ``entries``' ``sector`` codes and diff against ``known``.

    ``code_to_name`` defaults to the module-level TWSE mapping table but is
    injectable for tests (and for re-running the audit against a corrected
    table without editing this function).
    """
    codes_seen = sorted({entry.sector for entry in entries if entry.sector.strip()})
    unknown_codes = tuple(code for code in codes_seen if code not in code_to_name)
    official_names = sorted({code_to_name[code] for code in codes_seen if code in code_to_name})
    official_set = set(official_names)
    known_set = set(known)

    matched = tuple(sorted(official_set & known_set))

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
        official_sector_codes=tuple(codes_seen),
        official_sector_names=tuple(official_names),
        matched=matched,
        local_only=local_only,
        official_only=official_only,
        naming_diffs=tuple(naming_diffs),
        unknown_codes=unknown_codes,
    )


def render_terminal_lines(report: SectorComparisonReport) -> list[str]:
    """Short, human-readable summary for the CLI's stdout."""
    lines = [
        f"官方公司列數：{report.company_count}；官方產業別代碼數："
        f"{len(report.official_sector_codes)}（可解析為 {len(report.official_sector_names)} "
        f"種名稱）；本地清單（TWSE_SECTORS）產業別數：{report.known_sector_count}；"
        f"雙方一致：{len(report.matched)} 項",
    ]
    if report.unknown_codes:
        lines.append(
            f"[UNKNOWN_CODE] 對照表沒有的官方產業別代碼（{len(report.unknown_codes)} 種，"
            "需人工補到 app/directory/twse_sector_codes.py）：" + "、".join(report.unknown_codes)
        )
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
        "端點與 `公司代號`／`公司名稱`／`產業別` 欄位已由 CEO 2026-08-12 實測確認可連通、"
        "欄位存在；`產業別` 欄回傳的是兩碼代碼，經 `app/directory/twse_sector_codes.py` "
        "轉為中文名稱後才與本地清單比對，該對照表本身仍是依公開資料整理、未經官方代碼表"
        "文件逐項核對，見該檔案 PROVENANCE 說明）",
        f"- 官方資料公司列數：{report.company_count}",
        f"- 官方資料涵蓋產業別代碼數：{len(report.official_sector_codes)}"
        f"（可解析為 {len(report.official_sector_names)} 種名稱）",
        f"- 本地清單（`TWSE_SECTORS`）產業別數：{report.known_sector_count}",
        f"- 雙方一致：{len(report.matched)} 項",
        f"- as_of：{report.as_of.isoformat()}",
        "",
        "## UNKNOWN_CODE -- 代碼不在對照表中（需人工補到 twse_sector_codes.py）",
        "",
    ]
    if report.unknown_codes:
        lines.append(
            "以下代碼出現在這次官方資料的 `產業別` 欄，但 "
            "`app/directory/twse_sector_codes.py` 的 `TWSE_SECTOR_CODE_TO_NAME` 對照表"
            "沒有收錄，代表對照表不完整，需人工查證代碼實際代表的產業後補上"
            "（**絕不可用猜測值填入**）："
        )
        lines.extend(f"- `{code}`" for code in report.unknown_codes)
    else:
        lines.append("（無差異，這次官方資料出現的代碼皆能經對照表解析為名稱）")
    lines += ["", "## 雙方一致", ""]
    if report.matched:
        lines.append(
            f"官方資料（代碼解析後）與 `TWSE_SECTORS` 完全一致的產業別"
            f"（{len(report.matched)} 項）："
        )
        lines.extend(f"- {name}" for name in report.matched)
    else:
        lines.append("（無）")
    lines += ["", "## 官方有、本地清單沒有", ""]
    if report.official_only:
        lines.append(
            "官方資料（代碼解析後）出現、但不在 `TWSE_SECTORS` 中的產業別（可能是本地清單"
            "遺漏，也可能是像代碼 `91`／存託憑證這類非傳統產業分類——本工具不臆測是哪一種，"
            "交 CEO 裁決）："
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
        lines.append("| 本地清單 | 官方資料（代碼解析後） |")
        lines.append("| --- | --- |")
        lines.extend(f"| `{diff.local}` | `{diff.official}` |" for diff in report.naming_diffs)
    else:
        lines.append("（無差異）")
    lines += [
        "",
        "## 下一步",
        "",
        "- 本報告不自動改 `app/positions/sectors.py`；上述差異回報 CEO 轉裁決。",
        "- 若有 UNKNOWN_CODE，優先由 data-engineer 查證代碼實際代表的產業後補進 "
        "`app/directory/twse_sector_codes.py`（含更新該檔案的版本日期），再重跑本工具"
        "確認差異是否縮小。",
        "- 裁決結果需要修改清單時，由 data-engineer 依裁決結果另行提交變更"
        "（含 `sectors.py` 檔頭 PROVENANCE NOTICE 的同步更新）。",
        "",
    ]
    return "\n".join(lines)
