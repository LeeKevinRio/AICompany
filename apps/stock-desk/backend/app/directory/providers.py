"""TWSE / TPEx OpenAPI adapters for the security directory (代號/公司名稱/市場).

## Schema confidence -- read before touching endpoint paths or field names

- TWSE: ``GET https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL``
  is TWSE's "每日收盤行情(全部)" dataset -- a same-day snapshot of every
  listed (上市) symbol, English-keyed (``Code``, ``Name``, ...). It is used
  here purely for its ``Code``/``Name`` columns, not the price columns, as a
  practical stand-in for a dedicated "company directory" endpoint. CEO's
  real sync run (2026-08-12) confirmed this endpoint/field pair works
  end-to-end (1379 上市 rows parsed, ``PASS``).
- TPEx: ``GET https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes``
  is the OTC (上櫃) counterpart. **CONFIRMED reachable and the row shape
  below is verified against a live payload** -- CEO's first real sync run
  (2026-08-12) hit this endpoint and captured actual response rows (10,400
  上櫃 rows returned; the endpoint path was already correct, only the field
  names guessed before this run were wrong). The confirmed field names are
  **English-keyed**, not Chinese as previously assumed -- e.g. a sample row:

  .. code-block:: json

      {
        "Date": "1150812",
        "SecuritiesCompanyCode": "006201",
        "CompanyName": "元大富櫃50",
        "Close": "45.21",
        "LatesAskPrice": "45.23"
      }

  Only ``SecuritiesCompanyCode``/``CompanyName`` are consumed below (the
  directory only needs 代號/名稱); price/volume columns such as ``Close``
  or ``TradingShares`` are captured in the fixture for provenance but never
  parsed here. Note ``LatesAskPrice`` is TPEx's own spelling (missing a
  "t") -- copied verbatim (sic), not "corrected", since inventing a
  different key would silently stop matching the real payload. ``Date`` is
  an ROC-calendar string with **no separators** (``"1150812"`` = 民國115年
  08月12日 = 2026-08-12), a different shape from the ``"113/01/02"``
  slash-separated ROC dates ``app.data.providers._util.parse_roc_date``
  already handles elsewhere in this codebase -- it is deliberately left
  unparsed here because the directory sync only needs symbol/name, not a
  trade date; a future consumer that does need it must write a dedicated
  parser for this no-separator shape rather than misusing
  ``parse_roc_date``.

A schema mismatch (missing field, non-array payload, etc.) must still
surface as ``ok=False`` with a clear reason (never a partially-parsed,
silently-wrong directory), which is exactly what the per-row
``UnparseableRowError`` skip below produces.

## Coverage scope: ETF / bond ETF rows are not filtered out

Both the TWSE ``STOCK_DAY_ALL`` fixture and TPEx's mainboard quotes include
ETFs (e.g. TWSE's ``0050``) and, on the TPEx side, bond ETFs whose codes
contain a trailing letter (e.g. ``00679B``). Neither adapter applies any
symbol-shape or instrument-type filter -- ``_parse_row`` only requires a
non-blank string for both the symbol and name columns. This mirrors the
existing ``TwseDirectoryAdapter`` behaviour (which already keeps ``0050``)
rather than inventing a new filtering rule for TPEx alone: the directory's
job is "does this 代號 resolve to a 名稱", not "is this a common stock".

## Sector-profile endpoint (``TwseSectorProfileAdapter``) -- CONFIRMED reachable
## and field names confirmed; one field's *value shape* corrected 2026-08-12

Used only by the ``--verify-sectors`` audit (``app.directory.sector_audit``),
never by the symbol/name sync above. ``GET
https://openapi.twse.com.tw/v1/opendata/t187ap03_L`` is TWSE's "上市公司基本
資料" (listed-company basic profile) dataset -- a more literal directory
match than ``STOCK_DAY_ALL`` for company data; it is picked up here
specifically because it is the dataset publicly documented to carry a
per-company ``產業別`` (industry category) column, which ``STOCK_DAY_ALL``
does not.

CEO's first real run of ``--verify-sectors`` against production TWSE data
(2026-08-12) confirmed the endpoint path and the ``公司代號``/``公司名稱``/
``產業別`` field names are correct as written below (1095 rows fetched
successfully). That same run also corrected an assumption this docstring
used to make: ``產業別`` returns a **two-digit TWSE industry-category code**
(e.g. ``"24"``), not the Chinese industry name. ``app.directory.sector_audit``
resolves the code through ``app.directory.twse_sector_codes`` before
comparing it against ``app.positions.sectors.TWSE_SECTORS`` -- see that
module's docstring for the code-to-name mapping's own provenance (compiled
from public knowledge of TWSE's code table, not yet verified against a live
code-table document). A schema mismatch (missing field, non-string value,
etc.) must still surface as ``ok=False`` here, never a silently-empty or
partially-parsed sector list; an *unrecognized code* is a separate concern
handled one layer up, in ``compare_sectors``' ``UNKNOWN_CODE`` bucket.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from app.data.http import RateLimitedClient
from app.data.providers._util import UnparseableRowError
from app.directory.models import DirectoryEntry

logger = logging.getLogger(__name__)

TWSE_OPENAPI_BASE_URL = "https://openapi.twse.com.tw"
TWSE_STOCK_LIST_PATH = "/v1/exchangeReport/STOCK_DAY_ALL"

TPEX_OPENAPI_BASE_URL = "https://www.tpex.org.tw"
TPEX_STOCK_LIST_PATH = "/openapi/v1/tpex_mainboard_daily_close_quotes"

#: See "Sector-profile endpoint" section in the module docstring -- CEO's
#: 2026-08-12 real run confirmed this path and its field names.
TWSE_COMPANY_PROFILE_PATH = "/v1/opendata/t187ap03_L"


@dataclass(frozen=True)
class DirectoryFetchResult:
    """One source's outcome: either a batch of entries, or an honest failure reason.

    Mirrors ``app.data.interface.ProviderResult``'s discipline of never
    raising for expected failure modes (network errors, bad credentials n/a
    here, unexpected response shape) -- callers get ``ok=False`` and a
    Traditional Chinese ``reason`` instead of an exception, so one source
    failing never takes down the other (AC-2's "不因單一來源失敗而整批放棄").
    """

    entries: tuple[DirectoryEntry, ...]
    ok: bool
    reason: str | None
    source: str
    as_of: datetime


@dataclass(frozen=True)
class SectorProfileEntry:
    """One listed company's ``代號 -> 名稱 -> 產業別`` row from ``t187ap03_L``.

    ``sector`` holds the raw two-digit TWSE industry-category **code** TWSE
    actually returns (confirmed by CEO's 2026-08-12 real run -- see this
    module's "Sector-profile endpoint" docstring section), not a Chinese
    name. Resolving the code to a name is ``app.directory.sector_audit``'s
    job (via ``app.directory.twse_sector_codes``), not this adapter's --
    this dataclass stays a faithful, unmodified record of what TWSE sent.

    Deliberately a plain dataclass, not a ``pydantic`` model like
    ``DirectoryEntry``: this data is never persisted to the store, only fed
    into ``app.directory.sector_audit.compare_sectors`` for a one-off
    comparison against ``app.positions.sectors.TWSE_SECTORS``, so it does not
    need the validated-input-boundary discipline the persisted directory
    rows do. Still carries ``source``/``as_of`` per the provenance rule.
    """

    symbol: str
    name: str
    sector: str
    source: str
    as_of: datetime


@dataclass(frozen=True)
class SectorProfileFetchResult:
    """Outcome of fetching the TWSE company-profile dataset for the sector audit.

    Mirrors ``DirectoryFetchResult``'s discipline: never raise for an
    expected failure mode, report ``ok=False`` with a Traditional Chinese
    ``reason`` instead.
    """

    entries: tuple[SectorProfileEntry, ...]
    ok: bool
    reason: str | None
    source: str
    as_of: datetime


def _parse_row(row: Any, *, symbol_key: str, name_key: str) -> tuple[str, str]:
    if not isinstance(row, dict):
        raise UnparseableRowError(f"row is not an object: {row!r}")
    symbol = row.get(symbol_key)
    name = row.get(name_key)
    if not isinstance(symbol, str) or not symbol.strip():
        raise UnparseableRowError(f"missing/blank {symbol_key!r} in row: {row!r}")
    if not isinstance(name, str) or not name.strip():
        raise UnparseableRowError(f"missing/blank {name_key!r} in row: {row!r}")
    return symbol.strip(), name.strip()


class TwseDirectoryAdapter:
    """Fetches the TWSE-listed (上市) symbol/name list."""

    source_id: ClassVar[str] = "twse_openapi"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self) -> DirectoryFetchResult:
        now = datetime.now(UTC)
        try:
            response = self._client.get(TWSE_STOCK_LIST_PATH)
        except httpx.TransportError as exc:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=(
                    f"連線失敗（{exc.__class__.__name__}）：{exc}。"
                    "本雲端開發環境對財經網域的 egress 已知被封鎖，"
                    "請在有網路的機器（如 CEO 本機）重跑本工具。"
                ),
                source=self.source_id,
                as_of=now,
            )
        if response.status_code != httpx.codes.OK:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=f"TWSE OpenAPI 回傳 HTTP {response.status_code}，非預期狀態碼",
                source=self.source_id,
                as_of=now,
            )
        try:
            payload = response.json()
        except ValueError:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason="TWSE OpenAPI 回應非 JSON，可能是端點路徑或格式已變更",
                source=self.source_id,
                as_of=now,
            )
        if not isinstance(payload, list):
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=(
                    f"TWSE OpenAPI 回應非陣列（收到 {type(payload).__name__}），schema 與預期不符"
                ),
                source=self.source_id,
                as_of=now,
            )

        entries: list[DirectoryEntry] = []
        skipped = 0
        for row in payload:
            try:
                symbol, name = _parse_row(row, symbol_key="Code", name_key="Name")
            except UnparseableRowError as exc:
                logger.debug("skipping unparseable TWSE directory row: %s", exc)
                skipped += 1
                continue
            entries.append(
                DirectoryEntry(
                    symbol=symbol, name=name, market="TW", source=self.source_id, as_of=now
                )
            )

        if not entries:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=f"TWSE OpenAPI 回應中沒有任何可解析的列（略過 {skipped} 列）",
                source=self.source_id,
                as_of=now,
            )
        return DirectoryFetchResult(
            entries=tuple(entries), ok=True, reason=None, source=self.source_id, as_of=now
        )


class TpexDirectoryAdapter:
    """Fetches the TPEx-listed (上櫃) symbol/name list."""

    source_id: ClassVar[str] = "tpex_openapi"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=TPEX_OPENAPI_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self) -> DirectoryFetchResult:
        now = datetime.now(UTC)
        try:
            response = self._client.get(TPEX_STOCK_LIST_PATH)
        except httpx.TransportError as exc:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=(
                    f"連線失敗（{exc.__class__.__name__}）：{exc}。"
                    "本雲端開發環境對財經網域的 egress 已知被封鎖，"
                    "請在有網路的機器（如 CEO 本機）重跑本工具。"
                ),
                source=self.source_id,
                as_of=now,
            )
        if response.status_code != httpx.codes.OK:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=f"TPEx OpenAPI 回傳 HTTP {response.status_code}，非預期狀態碼",
                source=self.source_id,
                as_of=now,
            )
        try:
            payload = response.json()
        except ValueError:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason="TPEx OpenAPI 回應非 JSON，可能是端點路徑或格式已變更",
                source=self.source_id,
                as_of=now,
            )
        if not isinstance(payload, list):
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=(
                    f"TPEx OpenAPI 回應非陣列（收到 {type(payload).__name__}），schema 與預期不符"
                ),
                source=self.source_id,
                as_of=now,
            )

        entries: list[DirectoryEntry] = []
        skipped = 0
        for row in payload:
            try:
                symbol, name = _parse_row(
                    row, symbol_key="SecuritiesCompanyCode", name_key="CompanyName"
                )
            except UnparseableRowError as exc:
                logger.debug("skipping unparseable TPEx directory row: %s", exc)
                skipped += 1
                continue
            entries.append(
                DirectoryEntry(
                    symbol=symbol, name=name, market="TW", source=self.source_id, as_of=now
                )
            )

        if not entries:
            return DirectoryFetchResult(
                entries=(),
                ok=False,
                reason=f"TPEx OpenAPI 回應中沒有任何可解析的列（略過 {skipped} 列）",
                source=self.source_id,
                as_of=now,
            )
        return DirectoryFetchResult(
            entries=tuple(entries), ok=True, reason=None, source=self.source_id, as_of=now
        )


def _parse_sector_row(row: Any) -> tuple[str, str, str]:
    if not isinstance(row, dict):
        raise UnparseableRowError(f"row is not an object: {row!r}")
    symbol = row.get("公司代號")
    name = row.get("公司名稱")
    sector = row.get("產業別")
    if not isinstance(symbol, str) or not symbol.strip():
        raise UnparseableRowError(f"missing/blank 公司代號 in row: {row!r}")
    if not isinstance(name, str) or not name.strip():
        raise UnparseableRowError(f"missing/blank 公司名稱 in row: {row!r}")
    if not isinstance(sector, str) or not sector.strip():
        raise UnparseableRowError(f"missing/blank 產業別 in row: {row!r}")
    return symbol.strip(), name.strip(), sector.strip()


class TwseSectorProfileAdapter:
    """Fetches TWSE's per-company ``產業別`` from the ``t187ap03_L`` dataset.

    Only used by the ``--verify-sectors`` audit -- see the module docstring's
    "Sector-profile endpoint" section for the same unverified-schema caveat
    the symbol/name adapters above carry.
    """

    source_id: ClassVar[str] = "twse_openapi_t187ap03_L"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self) -> SectorProfileFetchResult:
        now = datetime.now(UTC)
        try:
            response = self._client.get(TWSE_COMPANY_PROFILE_PATH)
        except httpx.TransportError as exc:
            return SectorProfileFetchResult(
                entries=(),
                ok=False,
                reason=(
                    f"連線失敗（{exc.__class__.__name__}）：{exc}。"
                    "本雲端開發環境對財經網域的 egress 已知被封鎖，"
                    "請在有網路的機器（如 CEO 本機）重跑本工具。"
                ),
                source=self.source_id,
                as_of=now,
            )
        if response.status_code != httpx.codes.OK:
            return SectorProfileFetchResult(
                entries=(),
                ok=False,
                reason=f"TWSE OpenAPI 回傳 HTTP {response.status_code}，非預期狀態碼",
                source=self.source_id,
                as_of=now,
            )
        try:
            payload = response.json()
        except ValueError:
            return SectorProfileFetchResult(
                entries=(),
                ok=False,
                reason="TWSE OpenAPI 回應非 JSON，可能是端點路徑或格式已變更",
                source=self.source_id,
                as_of=now,
            )
        if not isinstance(payload, list):
            return SectorProfileFetchResult(
                entries=(),
                ok=False,
                reason=(
                    f"TWSE OpenAPI 回應非陣列（收到 {type(payload).__name__}），schema 與預期不符"
                ),
                source=self.source_id,
                as_of=now,
            )

        entries: list[SectorProfileEntry] = []
        skipped = 0
        for row in payload:
            try:
                symbol, name, sector = _parse_sector_row(row)
            except UnparseableRowError as exc:
                logger.debug("skipping unparseable TWSE sector-profile row: %s", exc)
                skipped += 1
                continue
            entries.append(
                SectorProfileEntry(
                    symbol=symbol, name=name, sector=sector, source=self.source_id, as_of=now
                )
            )

        if not entries:
            return SectorProfileFetchResult(
                entries=(),
                ok=False,
                reason=f"TWSE OpenAPI 回應中沒有任何可解析的列（略過 {skipped} 列）",
                source=self.source_id,
                as_of=now,
            )
        return SectorProfileFetchResult(
            entries=tuple(entries), ok=True, reason=None, source=self.source_id, as_of=now
        )
