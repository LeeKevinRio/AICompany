"""TWSE / TPEx OpenAPI adapters for the security directory (代號/公司名稱/市場).

## Schema confidence -- read before touching endpoint paths or field names

Neither endpoint below has been called against a live response from this
sandbox: outbound HTTPS to both ``openapi.twse.com.tw`` and
``www.tpex.org.tw`` is blocked by this environment's egress policy (same
finding as ``apps/stock-desk/scripts/verify_market_data.py`` and
``tests/fixtures/README.md`` -- proxy CONNECT returns 403 for every financial
domain probed so far). Per the dispatch order ("查不到就以既有 adapter 內已知
端點推斷並在註解標註待驗"), the paths and field names below are **inferred**
from the existing ``TwseAdapter``/``TpexAdapter`` daily-bar adapters' host
conventions plus publicly documented OpenAPI dataset shapes, not confirmed
against a live payload:

- TWSE: ``GET https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL``
  is TWSE's "每日收盤行情(全部)" dataset -- a same-day snapshot of every
  listed (上市) symbol, English-keyed (``Code``, ``Name``, ...). It is used
  here purely for its ``Code``/``Name`` columns, not the price columns, as a
  practical stand-in for a dedicated "company directory" endpoint (TWSE's
  ``t187ap03_L`` "上市公司基本資料" dataset is the more literal directory
  match but its exact field names are even less certain, so the simpler,
  more commonly referenced ``STOCK_DAY_ALL`` shape was chosen to minimize the
  number of unverified field-name guesses).
- TPEx: ``GET https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes``
  is the OTC (上櫃) counterpart -- TPEx's OpenAPI is Chinese-keyed
  (``代號``, ``名稱``, ...), unlike TWSE's English keys; this asymmetry is a
  known real quirk of the two exchanges' OpenAPI portals, not a mistake here.

**Before the CEO's first real sync run**, if either endpoint 404s or the
response shape does not match what ``_parse_twse_row``/``_parse_tpex_row``
expect, that is expected until data-engineer confirms the exact dataset
against the live Swagger docs at ``openapi.twse.com.tw`` /
``www.tpex.org.tw/openapi`` -- see ``work/stock-desk-phase8-spike-盤點.md``
for the same caveat applied to other OpenAPI datasets in this project. A
schema mismatch must surface as ``ok=False`` with a clear reason (never a
partially-parsed, silently-wrong directory), which is exactly what the
per-row ``UnparseableRowError`` skip below produces.
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
                    f"TWSE OpenAPI 回應非陣列（收到 {type(payload).__name__}），"
                    "schema 與預期不符"
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
                    f"TPEx OpenAPI 回應非陣列（收到 {type(payload).__name__}），"
                    "schema 與預期不符"
                ),
                source=self.source_id,
                as_of=now,
            )

        entries: list[DirectoryEntry] = []
        skipped = 0
        for row in payload:
            try:
                symbol, name = _parse_row(row, symbol_key="代號", name_key="名稱")
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
