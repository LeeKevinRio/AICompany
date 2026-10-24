"""The replay snapshot fetch path for ``^TWII`` (ADR-0005 I-3 解釋性註記; follow-up N-82).

Covers the registered acceptance items (a)-(g) of that note plus the
single-date-derivation guard (``fromtimestamp`` appears once in the yfinance
adapter). Everything is offline: ``httpx.MockTransport`` stands in for Yahoo,
and the only database is a ``tmp_path`` one.

Map of acceptance item -> test:

* (a) call-site closure ........ ``TestAcceptanceACallSiteClosure``
* (b) no cache/service/quota ... ``TestAcceptanceBNoCacheServiceQuota``
* (c) status ................... ``TestAcceptanceCStatus``
* (d) cache + quota spy ........ ``TestAcceptanceDCacheAndQuotaSpy``
* (e) fail-closed .............. ``TestAcceptanceEFailClosed``
* (f) symbols .................. ``TestAcceptanceFSymbols``
* (g) existing paths unchanged . ``TestAcceptanceGExistingPathsUnchanged``
* single date derivation ....... ``TestSingleDateDerivation``
* TA ruling 2026-10-24 (work/reviews/2026-10-24-N82設計裁量點裁定-tech-architect.md):
  point 1 (always one request, padded) ... ``TestSingleRequest``
  point 2 (malformed vs null-gap rows) .. ``TestMalformedRowsFailTheWholeFetch``,
                                          ``TestNullGapRows``
  point 5 (received_at) ................. ``TestReceivedAt``
  L-3 (source is None) .................. ``TestSourceIsNoneWhenNothingWasContacted``
"""

from __future__ import annotations

import ast
import dataclasses
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.data.cache import PriceBarCache
from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, MarketDataProvider, PriceBar, ProviderResult
from app.data.providers import yfinance as yfinance_module
from app.data.providers.yfinance import (
    INDEX_SYMBOL_METADATA,
    RawChartBar,
    RawChartFetch,
    RawChartResponse,
    RawNullGapRow,
    YFinanceAdapter,
)
from app.data.quota import QuotaLedger
from app.services import index as index_module
from app.services.index import (
    MARKET_BENCHMARK,
    IndexProviderBridge,
    IndexSeriesService,
    LoadedBenchmark,
    LoadedIndexBars,
    ReplayIndexNullGapRow,
    ReplayIndexSnapshot,
    fetch_replay_index_snapshot,
    load_index_series,
    load_market_benchmark,
)
from tests.api_helpers import recent_bars, trending_closes

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
YFINANCE_FILE = "app/data/providers/yfinance.py"
INDEX_FILE = "app/services/index.py"
# ``app/forecast/replay_checks.py`` does not exist yet (ADR-0027 D-1 names it as the
# only caller). The allow-lists below are written as {defining file, that path}, so the
# closure test already holds today and keeps holding once the file lands.
REPLAY_CHECKS_FILE = "app/forecast/replay_checks.py"

TWII = "^TWII"
START = date(2024, 1, 1)
END = date(2024, 1, 31)
YAHOO_HOST = "query1.finance.yahoo.com"


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _ts(day: date, hour_utc: int = 1) -> int:
    """Unix seconds of ``day`` at ``hour_utc`` UTC (01:00 UTC == 09:00 in Taipei)."""
    return int(datetime(day.year, day.month, day.day, hour_utc, tzinfo=UTC).timestamp())


def _payload(
    timestamps: list[Any],
    *,
    meta: dict[str, Any] | None = None,
    closes: list[Any] | None = None,
    nulls_at: tuple[int, ...] = (),
    null_cells: dict[int, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    count = len(timestamps)
    base = [17900.5 + i for i in range(count)]
    close_values: list[Any] = list(closes) if closes is not None else [b + 10 for b in base]
    columns: dict[str, list[Any]] = {
        "open": list(base),
        "high": [b + 50 for b in base],
        "low": [b - 50 for b in base],
        "close": close_values,
        "volume": [0] * count,
    }
    for idx in nulls_at:
        columns["open"][idx] = None
        columns["close"][idx] = None
    for idx, names in (null_cells or {}).items():
        for name in names:
            columns[name][idx] = None
    return {
        "chart": {
            "result": [
                {
                    "meta": (
                        meta
                        if meta is not None
                        else {
                            "currency": "TWD",
                            "symbol": TWII,
                            "exchangeTimezoneName": "Asia/Taipei",
                            "gmtoffset": 28800,
                        }
                    ),
                    "timestamp": timestamps,
                    "indicators": {"quote": [columns]},
                }
            ],
            "error": None,
        }
    }


JAN_DAYS = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]


def _jan_payload() -> dict[str, Any]:
    return _payload([_ts(day) for day in JAN_DAYS])


def _jan_stamps() -> list[Any]:
    return [_ts(day) for day in JAN_DAYS]


def _quote_block(payload: dict[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = payload["chart"]["result"][0]["indicators"]["quote"][0]
    return block


ALL_FIELDS = ("open", "high", "low", "close", "volume")


Step = Callable[[httpx.Request], httpx.Response]


class Wire:
    """A scripted Yahoo: one step per request, in order; records every request."""

    def __init__(self, *steps: Step | dict[str, Any]) -> None:
        self._steps = list(steps)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests), len(self._steps)) - 1
        step = self._steps[index]
        if isinstance(step, dict):
            return httpx.Response(200, json=step)
        return step(request)

    def adapter(self) -> YFinanceAdapter:
        client = RateLimitedClient(
            base_url=f"https://{YAHOO_HOST}",
            min_interval_seconds=0.0,
            transport=httpx.MockTransport(self),
            sleep_fn=lambda _seconds: None,
        )
        return YFinanceAdapter(client=client)


def _raise_connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("boom", request=request)


def _fetch(wire: Wire, start: date = START, end: date = END) -> ReplayIndexSnapshot:
    return fetch_replay_index_snapshot(wire.adapter(), index_symbol=TWII, start=start, end=end)


def _assert_failed_closed(snapshot: ReplayIndexSnapshot) -> None:
    assert snapshot.status is DataStatus.UNAVAILABLE
    assert snapshot.responses == ()
    assert snapshot.bar_count == 0
    assert snapshot.reason


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


RECEIVED_AT = datetime(2024, 2, 1, 0, 0, 5, tzinfo=UTC)


def _raw_response(
    seq: int,
    *,
    bars: tuple[RawChartBar, ...] | None = None,
    null_gap_rows: tuple[RawNullGapRow, ...] = (),
) -> RawChartResponse:
    default_bars = (
        RawChartBar(
            raw_timestamp=_ts(JAN_DAYS[0]),
            session_date=JAN_DAYS[0],
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=0,
        ),
    )
    return RawChartResponse(
        response_seq=seq,
        exchange_timezone_name="Asia/Taipei",
        gmtoffset=28800,
        bars=default_bars if bars is None else bars,
        received_at=RECEIVED_AT,
        null_gap_rows=null_gap_rows,
    )


def _good_fetch() -> RawChartFetch:
    second = RawChartBar(
        raw_timestamp=_ts(JAN_DAYS[1]),
        session_date=JAN_DAYS[1],
        open=Decimal("2"),
        high=Decimal("3"),
        low=Decimal("1"),
        close=Decimal("2.5"),
        volume=0,
    )
    base = _raw_response(1)
    return RawChartFetch(
        index_symbol=TWII,
        as_of=datetime(2024, 2, 1, tzinfo=UTC),
        source="yfinance",
        responses=(dataclasses.replace(base, bars=(*base.bars, second)),),
    )


class FakeReplayProvider:
    """A ``ReplayIndexChartProvider`` that records what it was asked for."""

    def __init__(self, fetch: RawChartFetch) -> None:
        self._fetch = fetch
        self.calls: list[tuple[str, date, date]] = []

    def get_index_raw_responses(self, index_symbol: str, start: date, end: date) -> RawChartFetch:
        self.calls.append((index_symbol, start, end))
        return self._fetch


_AS_OF = datetime(2024, 2, 1, tzinfo=UTC)


def _answer(*responses: RawChartResponse, **overrides: Any) -> RawChartFetch:
    fields: dict[str, Any] = {
        "index_symbol": TWII,
        "as_of": _AS_OF,
        "source": "yfinance",
        "responses": responses,
        "reason": None,
    }
    fields.update(overrides)
    return RawChartFetch(**fields)


#: Answers a provider must never get through (the multi-response cases live here since
#: the adapter itself always issues one request, TA ruling point 1).
SERVICE_REJECTED_ANSWERS: dict[str, RawChartFetch] = {
    "provider_reason": _answer(reason="來源回報失敗"),
    "empty_string_reason": _answer(reason=""),
    "no_responses_no_reason": _answer(),
    "wrong_symbol_echoed": _answer(_raw_response(1), index_symbol="^GSPC"),
    "seq_not_starting_at_1": _answer(_raw_response(2)),
    "seq_gap": _answer(_raw_response(1), _raw_response(3)),
    "duplicate_seq": _answer(_raw_response(1), _raw_response(1)),
    "first_response_without_bars": _answer(_raw_response(1, bars=()), _raw_response(2)),
    "second_response_without_bars": _answer(_raw_response(1), _raw_response(2, bars=())),
    "reason_set_but_responses_present": _answer(_raw_response(1), reason="第 2/2 份回應失敗"),
}


# --------------------------------------------------------------------------- #
# Adapter side: raw responses, shared parse
# --------------------------------------------------------------------------- #


class TestAdapterRawResponses:
    def test_returns_meta_originals_and_raw_bars(self) -> None:
        wire = Wire(_jan_payload())
        result = wire.adapter().get_index_raw_responses(TWII, START, END)

        assert result.reason is None
        assert result.index_symbol == TWII
        assert result.source == "yfinance"
        assert result.as_of.tzinfo is not None
        assert len(result.responses) == 1
        response = result.responses[0]
        assert response.response_seq == 1
        assert response.exchange_timezone_name == "Asia/Taipei"
        assert response.gmtoffset == 28800
        assert [bar.session_date for bar in response.bars] == JAN_DAYS
        assert [bar.raw_timestamp for bar in response.bars] == [_ts(day) for day in JAN_DAYS]
        first = response.bars[0]
        assert (first.open, first.high, first.low, first.close, first.volume) == (
            Decimal("17900.5"),
            Decimal("17950.5"),
            Decimal("17850.5"),
            Decimal("17910.5"),
            0,
        )

    def test_meta_values_are_passed_through_unjudged(self) -> None:
        wire = Wire(
            _payload([_ts(JAN_DAYS[0])], meta={"exchangeTimezoneName": "UTC", "gmtoffset": "28800"})
        )
        response = wire.adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert response.exchange_timezone_name == "UTC"
        assert response.gmtoffset == "28800"  # a string stays a string; the gate judges it

    @pytest.mark.parametrize("meta", [{}, {"currency": "TWD"}])
    def test_absent_meta_fields_are_none_not_rejected(self, meta: dict[str, Any]) -> None:
        wire = Wire(_payload([_ts(JAN_DAYS[0])], meta=meta))
        response = wire.adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert response.exchange_timezone_name is None
        assert response.gmtoffset is None
        assert len(response.bars) == 1

    def test_non_dict_meta_is_none_not_rejected(self) -> None:
        payload = _payload([_ts(JAN_DAYS[0])])
        payload["chart"]["result"][0]["meta"] = "garbage"
        response = Wire(payload).adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert response.exchange_timezone_name is None
        assert response.gmtoffset is None

    def test_non_integer_timestamp_is_kept_as_received(self) -> None:
        stamp = _ts(JAN_DAYS[0])
        raw = httpx.Response(
            200,
            content=(
                b'{"chart":{"error":null,"result":[{"meta":{},"timestamp":[%d.5],'
                b'"indicators":{"quote":[{"open":[1],"high":[2],"low":[0.5],"close":[1.5],'
                b'"volume":[3]}]}}]}}' % stamp
            ),
        )
        wire = Wire(lambda _request: raw)
        bar = wire.adapter().get_index_raw_responses(TWII, START, END).responses[0].bars[0]
        # parse_float=Decimal: a fractional timestamp arrives as Decimal, not coerced to int.
        assert isinstance(bar.raw_timestamp, Decimal)
        assert bar.raw_timestamp == Decimal(f"{stamp}.5")
        assert bar.session_date == JAN_DAYS[0]

    def test_taipei_midnight_timestamp_keeps_raw_value_and_current_utc_date(self) -> None:
        # Taipei 2024-01-03 00:00 == 2024-01-02 16:00 UTC. The UTC-date convention (unchanged,
        # out of scope here) labels it Jan 2; the raw timestamp is kept so the replay gate
        # (ADR-0027 gate (5a)/(5b)) can see the discrepancy instead of it being hidden.
        stamp = _ts(date(2024, 1, 2), hour_utc=16)
        bar = (
            Wire(_payload([stamp]))
            .adapter()
            .get_index_raw_responses(TWII, START, END)
            .responses[0]
            .bars[0]
        )
        assert bar.raw_timestamp == stamp
        assert bar.session_date == date(2024, 1, 2)

    def test_null_rows_are_not_bars_and_not_filled(self) -> None:
        payload = _payload([_ts(day) for day in JAN_DAYS], nulls_at=(1,))
        result = Wire(payload).adapter().get_index_raw_responses(TWII, START, END)
        assert [bar.session_date for bar in result.responses[0].bars] == [
            JAN_DAYS[0],
            JAN_DAYS[2],
            JAN_DAYS[3],
        ]
        # ... and they are reported, not silently lost (see TestNullGapRows).
        assert [gap.session_date for gap in result.responses[0].null_gap_rows] == [JAN_DAYS[1]]

    def test_source_order_and_duplicate_dates_are_kept(self) -> None:
        stamps = [_ts(JAN_DAYS[2]), _ts(JAN_DAYS[0]), _ts(JAN_DAYS[0], hour_utc=2)]
        bars = (
            Wire(_payload(stamps))
            .adapter()
            .get_index_raw_responses(TWII, START, END)
            .responses[0]
            .bars
        )
        assert [bar.raw_timestamp for bar in bars] == stamps
        assert [bar.session_date for bar in bars] == [JAN_DAYS[2], JAN_DAYS[0], JAN_DAYS[0]]

    def test_bars_outside_the_requested_range_are_dropped(self) -> None:
        stamps = [_ts(date(2023, 12, 29)), _ts(JAN_DAYS[0]), _ts(date(2024, 2, 1))]
        bars = (
            Wire(_payload(stamps))
            .adapter()
            .get_index_raw_responses(TWII, START, END)
            .responses[0]
            .bars
        )
        assert [bar.session_date for bar in bars] == [JAN_DAYS[0]]

    def test_same_rows_and_dates_as_get_index_daily_bars(self) -> None:
        payload = _payload([_ts(day) for day in JAN_DAYS], nulls_at=(2,))
        daily = Wire(payload).adapter().get_index_daily_bars(TWII, START, END)
        raw = Wire(payload).adapter().get_index_raw_responses(TWII, START, END)
        assert [(b.date, b.open, b.high, b.low, b.close, b.volume) for b in daily.bars] == [
            (b.session_date, b.open, b.high, b.low, b.close, b.volume)
            for b in raw.responses[0].bars
        ]

    def test_request_shape_is_the_index_daily_shape(self) -> None:
        wire = Wire(_jan_payload())
        wire.adapter().get_index_raw_responses(TWII, START, END)
        (request,) = wire.requests
        assert request.url.host == YAHOO_HOST
        assert request.url.path == "/v8/finance/chart/^TWII"
        assert request.url.params["interval"] == "1d"
        # Padded by one day on each side (TA ruling point 1): [start - 1, end + 1].
        assert request.url.params["period1"] == str(_ts(START - timedelta(days=1), hour_utc=0))
        assert request.url.params["period2"] == str(_ts(END, hour_utc=0) + 2 * 86_400)

    @pytest.mark.parametrize("symbol", ["^SOX", "TWII", "^twii", "AAPL", "", "^TWII "])
    def test_symbol_outside_the_metadata_table_makes_no_request(self, symbol: str) -> None:
        wire = Wire(_jan_payload())
        result = wire.adapter().get_index_raw_responses(symbol, START, END)
        assert wire.requests == []
        assert result.responses == ()
        assert result.reason

    def test_inverted_range_makes_no_request(self) -> None:
        wire = Wire(_jan_payload())
        result = wire.adapter().get_index_raw_responses(TWII, END, START)
        assert wire.requests == []
        assert result.responses == ()
        assert result.reason

    def test_every_metadata_symbol_is_accepted_by_the_adapter_method(self) -> None:
        # The adapter takes any INDEX_SYMBOL_METADATA key (same table as the daily path); the
        # one-symbol restriction is the service function's job (acceptance (f)).
        for symbol in INDEX_SYMBOL_METADATA:
            wire = Wire(_jan_payload())
            assert wire.adapter().get_index_raw_responses(symbol, START, END).reason is None

    def test_method_is_not_on_the_provider_abc_or_the_bridge(self) -> None:
        assert not hasattr(MarketDataProvider, "get_index_raw_responses")
        assert not hasattr(IndexProviderBridge, "get_index_raw_responses")
        assert not hasattr(IndexSeriesService, "get_index_raw_responses")


class TestSingleRequest:
    """TA ruling point 1: always one request, padded one day each side, filtered by date."""

    def test_twenty_year_range_is_one_request_with_padded_period(self) -> None:  # (1-a)
        start, end = date(2004, 1, 1), date(2024, 1, 31)
        wire = Wire(_jan_payload())
        result = wire.adapter().get_index_raw_responses(TWII, start, end)
        assert result.reason is None
        assert len(wire.requests) == 1
        params = wire.requests[0].url.params
        assert params["period1"] == str(_ts(start - timedelta(days=1), hour_utc=0))
        assert params["period2"] == str(_ts(end + timedelta(days=2), hour_utc=0))
        assert [r.response_seq for r in result.responses] == [1]

    def test_rows_dated_just_outside_the_range_are_not_bars(self) -> None:  # (1-b)
        before, after = START - timedelta(days=1), END + timedelta(days=1)
        stamps = [_ts(before), _ts(JAN_DAYS[0]), _ts(after)]
        result = Wire(_payload(stamps)).adapter().get_index_raw_responses(TWII, START, END)
        assert [bar.session_date for bar in result.responses[0].bars] == [JAN_DAYS[0]]

    def test_the_get_index_daily_bars_request_window_is_unchanged(self) -> None:
        wire = Wire(_jan_payload())
        wire.adapter().get_index_daily_bars(TWII, START, END)
        params = wire.requests[0].url.params
        assert params["period1"] == str(_ts(START, hour_utc=0))
        assert params["period2"] == str(_ts(END, hour_utc=0) + 86_400)

    def test_multi_window_machinery_is_gone(self) -> None:  # (1-d)
        source = Path(yfinance_module.__file__).read_text(encoding="utf-8")
        assert "RAW_CHART_MAX_WINDOW_DAYS" not in source
        assert "_split_windows" not in source
        assert "window" not in (yfinance_module.__doc__ or "").lower()


class TestSingleDateDerivation:
    def _tree(self) -> ast.Module:
        return ast.parse(Path(yfinance_module.__file__).read_text(encoding="utf-8"))

    def _callers_of(self, name: str) -> set[str]:
        callers: set[str] = set()
        for func in ast.walk(self._tree()):
            if not isinstance(func, ast.FunctionDef):
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == name
                ):
                    callers.add(func.name)
        return callers

    def test_fromtimestamp_appears_exactly_once_in_yfinance_adapter(self) -> None:
        names = {"fromtimestamp", "utcfromtimestamp"}
        hits = [
            node
            for node in ast.walk(self._tree())
            if (isinstance(node, ast.Attribute) and node.attr in names)
            or (isinstance(node, ast.Name) and node.id in names)
        ]
        assert len(hits) == 1

    def test_the_one_derivation_lives_in_derive_session_date(self) -> None:
        owners: list[str] = []
        for func in ast.walk(self._tree()):
            if not isinstance(func, ast.FunctionDef):
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Attribute) and node.attr == "fromtimestamp":
                    owners.append(func.name)
        assert owners == ["_derive_session_date"]

    def test_only_the_row_parser_and_the_raw_classifier_derive_dates(self) -> None:
        assert self._callers_of("_derive_session_date") == {
            "_parse_chart_row",
            "_classify_raw_rows",
        }

    def test_bar_path_and_raw_path_share_the_row_parser(self) -> None:
        # the bar path (via _parse_row) and the raw path (via _classify_raw_rows)
        assert self._callers_of("_parse_chart_row") == {"_parse_row", "_classify_raw_rows"}


# --------------------------------------------------------------------------- #
# TA ruling point 2: malformed rows fail the whole fetch; null gaps are reported
# --------------------------------------------------------------------------- #

MALFORMED_KEYWORD = "無法解析的列"


def _ms_timestamp_payload() -> dict[str, Any]:  # (2-a)
    stamps = _jan_stamps()
    stamps[2] = _ts(JAN_DAYS[2]) * 1000
    return _payload(stamps)


def _shorter_close_payload() -> dict[str, Any]:  # (2-c)
    payload = _jan_payload()
    _quote_block(payload)["close"].pop()
    return payload


def _missing_volume_payload() -> dict[str, Any]:  # (2-d)
    payload = _jan_payload()
    del _quote_block(payload)["volume"]
    return payload


def _bad_close_value_payload() -> dict[str, Any]:  # (2-e)
    return _payload(_jan_stamps(), closes=[1.0, "abc", 3.0, 4.0])


def _null_timestamp_payload() -> dict[str, Any]:  # (2-f)
    stamps = _jan_stamps()
    stamps[1] = None
    return _payload(stamps)


def _bool_timestamp_payload() -> dict[str, Any]:  # (2-g)
    stamps = _jan_stamps()
    stamps[1] = True
    return _payload(stamps)


def _malformed_row_out_of_range_payload() -> dict[str, Any]:  # (2-h)
    stamps = [_ts(START - timedelta(days=1)), *_jan_stamps()]
    return _payload(stamps, closes=["abc", 1.0, 2.0, 3.0, 4.0])


def _all_null_millisecond_payload() -> dict[str, Any]:  # (2-i)
    stamps = [_ts(JAN_DAYS[0]) * 1000, *_jan_stamps()[1:]]
    return _payload(stamps, null_cells={0: ALL_FIELDS})


def _empty_close_array_payload() -> dict[str, Any]:
    payload = _jan_payload()
    _quote_block(payload)["close"] = []
    return payload


def _string_close_array_payload() -> dict[str, Any]:
    payload = _jan_payload()
    _quote_block(payload)["close"] = "abcd"
    return payload


def _bad_volume_value_payload() -> dict[str, Any]:
    payload = _jan_payload()
    _quote_block(payload)["volume"][1] = "x"
    return payload


def _bad_value_beside_a_null_payload() -> dict[str, Any]:
    payload = _payload(_jan_stamps(), null_cells={1: ("close",)})
    _quote_block(payload)["open"][1] = "abc"
    return payload


def _non_numeric_timestamp_payload() -> dict[str, Any]:
    stamps = _jan_stamps()
    stamps[0] = "not-a-number"
    return _payload(stamps)


MALFORMED_PAYLOADS: dict[str, Callable[[], dict[str, Any]]] = {
    "millisecond_timestamp": _ms_timestamp_payload,
    "timestamp_1e30": lambda: _payload([*_jan_stamps()[:2], 10**30, *_jan_stamps()[3:]]),
    "close_shorter_by_one": _shorter_close_payload,
    "volume_key_missing": _missing_volume_payload,
    "close_value_abc": _bad_close_value_payload,
    "timestamp_null": _null_timestamp_payload,
    "timestamp_true": _bool_timestamp_payload,
    "malformed_row_outside_range": _malformed_row_out_of_range_payload,
    "all_null_row_with_millisecond_timestamp": _all_null_millisecond_payload,
    "close_array_empty": _empty_close_array_payload,
    "close_array_not_a_list": _string_close_array_payload,
    "volume_value_x": _bad_volume_value_payload,
    "bad_value_beside_a_null": _bad_value_beside_a_null_payload,
    "timestamp_not_numeric": _non_numeric_timestamp_payload,
}


class TestMalformedRowsFailTheWholeFetch:
    @pytest.mark.parametrize("name", sorted(MALFORMED_PAYLOADS))
    def test_adapter_fails_whole_with_the_same_reason(self, name: str) -> None:  # (2-a)-(2-i)
        result = (
            Wire(MALFORMED_PAYLOADS[name]()).adapter().get_index_raw_responses(TWII, START, END)
        )
        assert result.responses == ()
        assert MALFORMED_KEYWORD in (result.reason or "")

    def test_every_malformed_cell_gives_one_identical_reason(self) -> None:
        reasons = {
            Wire(build()).adapter().get_index_raw_responses(TWII, START, END).reason
            for build in MALFORMED_PAYLOADS.values()
        }
        assert len(reasons) == 1

    @pytest.mark.parametrize("name", sorted(MALFORMED_PAYLOADS))
    def test_service_returns_unavailable_with_zero_bars(self, name: str) -> None:
        snapshot = _fetch(Wire(MALFORMED_PAYLOADS[name]()))
        _assert_failed_closed(snapshot)
        assert MALFORMED_KEYWORD in (snapshot.reason or "")

    def test_good_rows_around_a_malformed_row_are_not_returned(self) -> None:
        result = Wire(_ms_timestamp_payload()).adapter().get_index_raw_responses(TWII, START, END)
        assert result.responses == ()

    def test_get_index_daily_bars_is_unchanged_for_the_same_payloads(self) -> None:  # (2-n)
        def dates(payload: dict[str, Any]) -> list[date]:
            result = Wire(payload).adapter().get_index_daily_bars(TWII, START, END)
            assert result.status is DataStatus.BACKUP
            return [bar.date for bar in result.bars]

        d0, d1, d2, d3 = JAN_DAYS
        # The bar path still skips these rows silently (behaviour deliberately untouched).
        assert dates(_ms_timestamp_payload()) == [d0, d1, d3]
        assert dates(_shorter_close_payload()) == [d0, d1, d2]
        assert dates(_bad_close_value_payload()) == [d0, d2, d3]
        assert dates(_payload(_jan_stamps(), null_cells={1: ALL_FIELDS})) == [d0, d2, d3]


class TestNullGapRows:
    def test_all_null_in_range_row_is_reported_not_a_bar(self) -> None:  # (2-j)
        payload = _payload(_jan_stamps(), null_cells={1: ALL_FIELDS})
        response = Wire(payload).adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert [bar.session_date for bar in response.bars] == [
            JAN_DAYS[0],
            JAN_DAYS[2],
            JAN_DAYS[3],
        ]
        assert response.null_gap_rows == (
            RawNullGapRow(
                raw_timestamp=_ts(JAN_DAYS[1]),
                session_date=JAN_DAYS[1],
                null_fields=("open", "high", "low", "close", "volume"),
            ),
        )

    def test_only_volume_null_lists_only_volume(self) -> None:  # (2-k)
        payload = _payload(_jan_stamps(), null_cells={2: ("volume",)})
        response = Wire(payload).adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert [gap.null_fields for gap in response.null_gap_rows] == [("volume",)]
        assert JAN_DAYS[2] not in [bar.session_date for bar in response.bars]

    def test_null_fields_follow_the_open_high_low_close_volume_order(self) -> None:
        payload = _payload(_jan_stamps(), null_cells={0: ("volume", "close", "open")})
        gap = Wire(payload).adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert gap.null_gap_rows[0].null_fields == ("open", "close", "volume")

    def test_gap_dated_outside_the_range_is_not_reported(self) -> None:  # (2-l)
        before, after = START - timedelta(days=1), END + timedelta(days=1)
        payload = _payload(
            [_ts(before), *_jan_stamps(), _ts(after)],
            null_cells={0: ALL_FIELDS, 5: ("close",)},
        )
        response = Wire(payload).adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert response.null_gap_rows == ()
        assert [bar.session_date for bar in response.bars] == JAN_DAYS

    def test_raw_timestamp_of_a_gap_is_the_original_value(self) -> None:
        stamps = _jan_stamps()
        payload = _payload(stamps, null_cells={1: ALL_FIELDS})
        gap = Wire(payload).adapter().get_index_raw_responses(TWII, START, END).responses[0]
        assert gap.null_gap_rows[0].raw_timestamp == stamps[1]

    def test_gaps_without_any_bar_still_fail(self) -> None:
        payload = _payload([_ts(JAN_DAYS[0])], null_cells={0: ALL_FIELDS})
        result = Wire(payload).adapter().get_index_raw_responses(TWII, START, END)
        assert result.responses == ()
        assert "查無" in (result.reason or "")

    def test_service_hands_gaps_over_as_reported(self) -> None:  # (2-m)
        gap = RawNullGapRow(_ts(JAN_DAYS[1]), JAN_DAYS[1], ("volume",))
        fetch = dataclasses.replace(
            _good_fetch(),
            responses=(_raw_response(1, null_gap_rows=(gap,)),),
        )
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(fetch), index_symbol=TWII, start=START, end=END
        )
        assert snapshot.status is DataStatus.BACKUP
        assert snapshot.responses[0].null_gap_rows == (
            ReplayIndexNullGapRow(_ts(JAN_DAYS[1]), JAN_DAYS[1], ("volume",)),
        )

    def test_service_hands_gaps_over_end_to_end(self) -> None:
        payload = _payload(_jan_stamps(), null_cells={1: ("volume",), 3: ALL_FIELDS})
        snapshot = _fetch(Wire(payload))
        assert snapshot.status is DataStatus.BACKUP
        assert [
            (g.raw_timestamp, g.session_date, g.null_fields)
            for g in snapshot.responses[0].null_gap_rows
        ] == [
            (_ts(JAN_DAYS[1]), JAN_DAYS[1], ("volume",)),
            (_ts(JAN_DAYS[3]), JAN_DAYS[3], ALL_FIELDS),
        ]
        assert snapshot.bar_count == 2


# --------------------------------------------------------------------------- #
# TA ruling point 5: received_at; L-3: source is None when nothing was contacted
# --------------------------------------------------------------------------- #


class TestReceivedAt:
    def test_adapter_stamps_received_at_after_the_request_returned(self) -> None:  # (5-b)
        seen: list[datetime] = []

        def step(request: httpx.Request) -> httpx.Response:
            seen.append(datetime.now(UTC))
            return httpx.Response(200, json=_jan_payload())

        before = datetime.now(UTC)
        result = Wire(step).adapter().get_index_raw_responses(TWII, START, END)
        after = datetime.now(UTC)
        received_at = result.responses[0].received_at
        assert received_at.tzinfo is not None
        assert before <= result.as_of <= seen[0] <= received_at <= after

    def test_service_passes_received_at_through_unchanged(self) -> None:  # (5-b)
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(_good_fetch()), index_symbol=TWII, start=START, end=END
        )
        assert snapshot.responses[0].received_at == RECEIVED_AT
        assert snapshot.as_of == _good_fetch().as_of

    def test_service_with_real_adapter_keeps_as_of_before_received_at(self) -> None:
        before = datetime.now(UTC)
        snapshot = _fetch(Wire(_jan_payload()))
        after = datetime.now(UTC)
        assert before <= snapshot.as_of <= snapshot.responses[0].received_at <= after


class TestSourceIsNoneWhenNothingWasContacted:
    def test_unsupported_symbol_has_no_source(self) -> None:
        provider = FakeReplayProvider(_good_fetch())
        snapshot = fetch_replay_index_snapshot(provider, index_symbol="^GSPC", start=START, end=END)
        assert snapshot.source is None
        assert provider.calls == []

    def test_success_carries_the_provider_source(self) -> None:
        fetch = dataclasses.replace(_good_fetch(), source="some-source")
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(fetch), index_symbol=TWII, start=START, end=END
        )
        assert snapshot.source == "some-source"

    def test_provider_reported_failure_carries_the_provider_source(self) -> None:
        fetch = RawChartFetch(
            index_symbol=TWII,
            as_of=datetime(2024, 2, 1, tzinfo=UTC),
            source="some-source",
            reason="boom",
        )
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(fetch), index_symbol=TWII, start=START, end=END
        )
        _assert_failed_closed(snapshot)
        assert snapshot.source == "some-source"

    def test_real_adapter_failure_and_success_name_yfinance(self) -> None:
        assert _fetch(Wire(_raise_connect_error)).source == "yfinance"
        assert _fetch(Wire(_jan_payload())).source == "yfinance"


# --------------------------------------------------------------------------- #
# Acceptance (a): call-site closure
# --------------------------------------------------------------------------- #


def _identifiers(tree: ast.AST) -> set[str]:
    """Every name-like token in ``tree``: names, attributes, imports, defs, args, strings."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.name.split(".")[-1])
            if node.asname:
                found.add(node.asname)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


def _files_mentioning(names: set[str], root: Path = APP_ROOT) -> dict[str, set[str]]:
    """``name -> {posix path relative to the backend dir}`` for every ``*.py`` under ``root``."""
    where: dict[str, set[str]] = {name: set() for name in names}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root.parent).as_posix()
        identifiers = _identifiers(ast.parse(path.read_text(encoding="utf-8")))
        for name in names & identifiers:
            where[name].add(relative)
    return where


class TestAcceptanceACallSiteClosure:
    def test_replay_fetch_function_name_is_confined(self) -> None:
        where = _files_mentioning({"fetch_replay_index_snapshot"})
        allowed = {INDEX_FILE, REPLAY_CHECKS_FILE}
        found = where["fetch_replay_index_snapshot"]
        assert INDEX_FILE in found  # the scan is not vacuous: the definition is seen
        assert found <= allowed

    def test_adapter_raw_method_name_is_confined(self) -> None:
        where = _files_mentioning({"get_index_raw_responses"})
        found = where["get_index_raw_responses"]
        assert YFINANCE_FILE in found
        assert found <= {YFINANCE_FILE, INDEX_FILE}

    def test_return_type_names_are_confined(self) -> None:
        names = {
            "ReplayIndexSnapshot",
            "ReplayIndexResponse",
            "ReplayIndexBar",
            "ReplayIndexNullGapRow",
        }
        for name, found in _files_mentioning(names).items():
            assert INDEX_FILE in found, name
            assert found <= {INDEX_FILE, REPLAY_CHECKS_FILE}, name

    def test_injected_adapter_protocol_names_are_confined(self) -> None:
        names = {
            "ReplayIndexChartProvider",
            "ReplayChartFetchLike",
            "ReplayChartResponseLike",
            "ReplayChartBarLike",
            "ReplayNullGapRowLike",
        }
        for name, found in _files_mentioning(names).items():
            assert INDEX_FILE in found, name
            assert found <= {INDEX_FILE, REPLAY_CHECKS_FILE}, name

    def test_adapter_side_raw_types_stay_inside_the_adapter_module(self) -> None:
        names = {"RawChartFetch", "RawChartResponse", "RawChartBar", "RawNullGapRow"}
        for name, found in _files_mentioning(names).items():
            assert found == {YFINANCE_FILE}, name

    def test_scanner_sees_aliased_and_attribute_uses(self, tmp_path: Path) -> None:
        pkg = tmp_path / "app"
        pkg.mkdir()
        (pkg / "a.py").write_text(
            "from app.services.index import fetch_replay_index_snapshot as f\n"
        )
        (pkg / "b.py").write_text(
            "from app.services import index as I\nI.fetch_replay_index_snapshot()\n"
        )
        (pkg / "c.py").write_text("getattr(x, 'fetch_replay_index_snapshot')\n")
        (pkg / "d.py").write_text("x = 1\n")
        found = _files_mentioning({"fetch_replay_index_snapshot"}, root=pkg)
        assert found["fetch_replay_index_snapshot"] == {"app/a.py", "app/b.py", "app/c.py"}


# --------------------------------------------------------------------------- #
# Acceptance (b): no cache / service layer / quota
# --------------------------------------------------------------------------- #

REPLAY_FUNCTIONS = ("fetch_replay_index_snapshot", "_replay_unavailable")
FORBIDDEN_IN_BODY = {
    "MarketDataService",
    "IndexSeriesService",
    "IndexProviderBridge",
    "PriceService",
    "PriceBarCache",
    "get_cached_bars",
    "get_daily_bars",
    "record_fetch",
    "record_attempt",
    "QuotaLedger",
    "canonical_us_symbol",
}


def _index_tree() -> ast.Module:
    return ast.parse(Path(index_module.__file__).read_text(encoding="utf-8"))


def _replay_function_nodes() -> list[ast.FunctionDef]:
    return [
        node
        for node in ast.walk(_index_tree())
        if isinstance(node, ast.FunctionDef) and node.name in REPLAY_FUNCTIONS
    ]


class TestAcceptanceBNoCacheServiceQuota:
    def test_replay_function_nodes_are_all_found(self) -> None:
        assert {node.name for node in _replay_function_nodes()} == set(REPLAY_FUNCTIONS)

    def test_no_other_function_in_the_module_is_replay_specific(self) -> None:
        replay_named = {
            node.name
            for node in ast.walk(_index_tree())
            if isinstance(node, ast.FunctionDef) and "replay" in node.name.lower()
        }
        assert replay_named == set(REPLAY_FUNCTIONS)

    def test_function_bodies_reference_none_of_the_forbidden_names(self) -> None:
        for func in _replay_function_nodes():
            used = _identifiers(func) & FORBIDDEN_IN_BODY
            assert not used, (func.name, used)

    def test_module_imports_no_cache_quota_or_provider_module(self) -> None:
        modules: set[str] = set()
        for node in ast.walk(_index_tree()):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                # A relative import (`from ..data import cache`) would dodge the module-name
                # check below, so none is allowed in this module at all.
                assert node.level == 0, f"relative import at line {node.lineno}"
                base = node.module or ""
                modules.add(base)
                modules.update(f"{base}.{alias.name}" for alias in node.names)
        for module in modules:
            for banned in ("app.data.cache", "app.data.quota", "app.data.providers"):
                assert module != banned
                assert not module.startswith(banned + "."), module


# --------------------------------------------------------------------------- #
# Acceptance (c): status
# --------------------------------------------------------------------------- #


class TestAcceptanceCStatus:
    def test_datastatus_members_in_replay_functions_are_only_backup_and_unavailable(self) -> None:
        members: set[str] = set()
        for func in _replay_function_nodes():
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "DataStatus"
                ):
                    members.add(node.attr)
        assert members == {"BACKUP", "UNAVAILABLE"}

    def test_replay_functions_do_not_use_disclosed_status_or_fresh_literals(self) -> None:
        for func in _replay_function_nodes():
            ids = _identifiers(func)
            assert "disclosed_status" not in ids
            assert "FRESH" not in ids
            assert "fresh" not in {i.lower() for i in ids if isinstance(i, str) and i.isalpha()}

    def test_success_with_fake_adapter_is_backup(self) -> None:
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(_good_fetch()), index_symbol=TWII, start=START, end=END
        )
        assert snapshot.status is DataStatus.BACKUP
        assert snapshot.reason is None
        assert snapshot.bar_count == 2

    def test_success_through_real_adapter_is_backup_never_fresh(self) -> None:
        snapshot = _fetch(Wire(_jan_payload()))
        assert snapshot.status is DataStatus.BACKUP
        assert snapshot.status.value != DataStatus.FRESH.value
        assert snapshot.source == "yfinance"
        assert snapshot.index_symbol == TWII
        assert snapshot.bar_count == 4
        assert snapshot.as_of.tzinfo is not None

    def test_failure_is_unavailable(self) -> None:
        _assert_failed_closed(_fetch(Wire(_raise_connect_error)))

    def test_snapshot_carries_raw_values_through(self) -> None:
        snapshot = _fetch(Wire(_jan_payload()))
        (response,) = snapshot.responses
        assert response.response_seq == 1
        assert response.exchange_timezone_name == "Asia/Taipei"
        assert response.gmtoffset == 28800
        assert [bar.raw_timestamp for bar in response.bars] == [_ts(day) for day in JAN_DAYS]
        assert [bar.session_date for bar in response.bars] == JAN_DAYS

    def test_result_type_is_a_dedicated_type_without_meta_or_notes(self) -> None:
        snapshot = _fetch(Wire(_jan_payload()))
        assert not isinstance(snapshot, (ProviderResult, LoadedIndexBars, LoadedBenchmark))
        assert not hasattr(snapshot, "meta")
        assert not hasattr(snapshot, "notes")
        assert {f.name for f in dataclasses.fields(ReplayIndexSnapshot)} == {
            "index_symbol",
            "status",
            "as_of",
            "source",
            "responses",
            "reason",
        }
        assert dataclasses.is_dataclass(snapshot) and snapshot.__dataclass_params__.frozen  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Acceptance (d): cache and quota spy
# --------------------------------------------------------------------------- #


def _public_methods(cls: type) -> list[str]:
    return [
        name
        for name, member in vars(cls).items()
        if not name.startswith("_") and callable(member) and not isinstance(member, property)
    ]


@pytest.fixture
def spied_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Path, dict[str, int]]]:
    """A cache DB and a quota DB pre-seeded for ``^TWII``; every public method is then counted."""
    cache_db, quota_db = tmp_path / "cache.db", tmp_path / "quota.db"
    cache = PriceBarCache(cache_db)
    cached = recent_bars(
        trending_closes(5, start=999.0), symbol=TWII, market="TW", end=date(2024, 1, 31)
    )
    cache.put(cached, source="yfinance")
    cache.record_fetch(
        TWII, "TW", start=START, end=END, fetched_at=datetime(2024, 2, 1, tzinfo=UTC)
    )
    cache.record_attempt(TWII, "TW", at=datetime(2024, 2, 1, tzinfo=UTC))
    ledger = QuotaLedger(quota_db)
    ledger.reserve("alpha_vantage", limit_value=25, now=datetime(2024, 2, 1, tzinfo=UTC))

    calls: dict[str, int] = {}
    for cls in (PriceBarCache, QuotaLedger):
        for name in _public_methods(cls):
            original = getattr(cls, name)

            def make(label: str, fn: Callable[..., Any]) -> Callable[..., Any]:
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    calls[label] = calls.get(label, 0) + 1
                    return fn(*args, **kwargs)

                return wrapper

            monkeypatch.setattr(cls, name, make(f"{cls.__name__}.{name}", original))
    yield cache_db, quota_db, calls


def _row_counts(cache_db: Path, quota_db: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for db, tables in (
        (cache_db, ("price_bars_cache", "price_bars_fetch_log", "price_bars_attempt_log")),
        (quota_db, ("provider_quota_usage",)),
    ):
        with closing(sqlite3.connect(db)) as conn:
            for table in tables:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                counts[table] = int(row[0])
    return counts


class TestAcceptanceDCacheAndQuotaSpy:
    def test_spy_is_wired_and_seed_rows_exist(
        self, spied_stores: tuple[Path, Path, dict[str, int]]
    ) -> None:
        cache_db, quota_db, calls = spied_stores
        before = _row_counts(cache_db, quota_db)
        assert all(count >= 1 for count in before.values()), before
        # The spy really counts: calling a store method is observed.
        PriceBarCache(cache_db).last_attempt_at(TWII, "TW")
        assert calls.get("PriceBarCache.last_attempt_at") == 1

    def test_success_touches_neither_store(
        self, spied_stores: tuple[Path, Path, dict[str, int]]
    ) -> None:
        cache_db, quota_db, calls = spied_stores
        before = _row_counts(cache_db, quota_db)
        snapshot = _fetch(Wire(_jan_payload()))
        assert snapshot.status is DataStatus.BACKUP
        assert calls == {}
        assert _row_counts(cache_db, quota_db) == before
        # What came back is the source's data, not the cached ^TWII rows (close ~999).
        closes = [bar.close for response in snapshot.responses for bar in response.bars]
        assert closes == [Decimal(f"{17910 + i}.5") for i in range(4)]

    def test_failure_touches_neither_store(
        self, spied_stores: tuple[Path, Path, dict[str, int]]
    ) -> None:
        cache_db, quota_db, calls = spied_stores
        before = _row_counts(cache_db, quota_db)
        snapshot = _fetch(Wire(_raise_connect_error))
        _assert_failed_closed(snapshot)
        assert calls == {}
        assert _row_counts(cache_db, quota_db) == before

    def test_quota_env_is_not_consulted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # yfinance has no quota ledger: the fetch works with no quota-related configuration.
        for name in ("ALPHA_VANTAGE_DAILY_LIMIT", "ALPHA_VANTAGE_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        assert _fetch(Wire(_jan_payload())).status is DataStatus.BACKUP


# --------------------------------------------------------------------------- #
# Acceptance (e): fail-closed
# --------------------------------------------------------------------------- #


def _status_step(code: int) -> Step:
    return lambda _request: httpx.Response(code, text="x")


def _body_step(body: bytes) -> Step:
    return lambda _request: httpx.Response(200, content=body)


def _json_step(payload: dict[str, Any]) -> Step:
    return lambda _request: httpx.Response(200, json=payload)


def _failure_cases() -> dict[str, tuple[Step, str]]:
    """``name -> (scripted Yahoo step, keyword the failure reason must contain)``."""
    return {
        "connection_error": (_raise_connect_error, "連線逾時或發生錯誤"),
        "http_500": (_status_step(500), "HTTP 狀態"),
        "http_404": (_status_step(404), "HTTP 狀態"),
        "http_429": (_status_step(429), "HTTP 狀態"),
        "non_json": (_body_step(b"<html>nope</html>"), "回應格式無法解析"),
        "no_chart_block": (_json_step({"nothing": 1}), "缺少預期的 chart 區塊"),
        "chart_not_a_dict": (_json_step({"chart": []}), "缺少預期的 chart 區塊"),
        "chart_error": (
            _json_step(
                {
                    "chart": {
                        "result": None,
                        "error": {
                            "code": "Not Found",
                            "description": "No data found, symbol may be delisted",
                        },
                    }
                }
            ),
            "yfinance 回報錯誤",
        ),
        "no_result_block": (
            _json_step({"chart": {"result": [], "error": None}}),
            "未回傳任何結果區塊",
        ),
        "result_null": (
            _json_step({"chart": {"result": None, "error": None}}),
            "未回傳任何結果區塊",
        ),
        "result_not_a_dict": (
            _json_step({"chart": {"result": ["x"], "error": None}}),
            "結果區塊格式無法解析",
        ),
        "timestamp_missing": (
            _json_step(
                {"chart": {"result": [{"meta": {}, "indicators": {"quote": [{}]}}], "error": None}}
            ),
            "結果區塊格式無法解析",
        ),
        "indicators_missing": (
            _json_step(
                {"chart": {"result": [{"meta": {}, "timestamp": [1704157200]}], "error": None}}
            ),
            "結果區塊格式無法解析",
        ),
        "quote_missing": (
            _json_step(
                {
                    "chart": {
                        "result": [
                            {"meta": {}, "timestamp": [1704157200], "indicators": {"quote": []}}
                        ],
                        "error": None,
                    }
                }
            ),
            "結果區塊格式無法解析",
        ),
        "no_bar_in_range": (_json_step(_payload([_ts(date(2019, 3, 4))])), "查無"),
        "empty_timestamps": (_json_step(_payload([])), "查無"),
        "all_rows_null": (
            _json_step(
                _payload(
                    [_ts(JAN_DAYS[0]), _ts(JAN_DAYS[1])], null_cells={0: ALL_FIELDS, 1: ALL_FIELDS}
                )
            ),
            "查無",
        ),
    }


FAILURE_NAMES = sorted(_failure_cases())


class TestAcceptanceEFailClosed:
    @pytest.mark.parametrize("name", FAILURE_NAMES)
    def test_single_response_failure(self, name: str) -> None:
        step, keyword = _failure_cases()[name]
        wire = Wire(step)
        snapshot = _fetch(wire)
        _assert_failed_closed(snapshot)
        # The failing branch is the intended one, not just any failure.
        assert keyword in (snapshot.reason or "")
        # Transport-level retry belongs to the same request; nothing beyond it is attempted.
        assert 1 <= len(wire.requests) <= 2
        assert {r.url.host for r in wire.requests} == {YAHOO_HOST}
        assert {r.url.path for r in wire.requests} == {"/v8/finance/chart/^TWII"}

    @pytest.mark.parametrize("name", FAILURE_NAMES)
    def test_adapter_reason_matches_for_the_same_cell(self, name: str) -> None:
        step, keyword = _failure_cases()[name]
        result = Wire(step).adapter().get_index_raw_responses(TWII, START, END)
        assert result.responses == ()
        assert keyword in (result.reason or "")

    def test_a_long_range_is_still_one_request_and_fails_as_one(self) -> None:
        wire = Wire(_status_step(404))
        _assert_failed_closed(_fetch(wire, date(2004, 1, 1), END))
        assert len(wire.requests) == 1

    def test_failure_with_cached_twii_rows_still_yields_zero_bars(
        self, spied_stores: tuple[Path, Path, dict[str, int]]
    ) -> None:
        _cache_db, _quota_db, calls = spied_stores
        snapshot = _fetch(Wire(_status_step(500)))
        _assert_failed_closed(snapshot)
        assert calls == {}

    def test_only_the_injected_adapter_is_called(self) -> None:
        provider = FakeReplayProvider(_good_fetch())
        fetch_replay_index_snapshot(provider, index_symbol=TWII, start=START, end=END)
        assert provider.calls == [(TWII, START, END)]

    def test_failure_reason_is_traditional_chinese_and_names_no_fallback(self) -> None:
        reason = _fetch(Wire(_status_step(500))).reason or ""
        assert "重放快照取數失敗" in reason
        assert "不改用快取或其他來源" in reason

    @pytest.mark.parametrize("name", sorted(SERVICE_REJECTED_ANSWERS))
    def test_service_rejects_malformed_provider_answers(self, name: str) -> None:  # (1-c)
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(SERVICE_REJECTED_ANSWERS[name]),
            index_symbol=TWII,
            start=START,
            end=END,
        )
        _assert_failed_closed(snapshot)

    def test_two_good_responses_are_handed_over_in_order(self) -> None:
        fetch = dataclasses.replace(_good_fetch(), responses=(_raw_response(1), _raw_response(2)))
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(fetch), index_symbol=TWII, start=START, end=END
        )
        assert snapshot.status is DataStatus.BACKUP
        assert [r.response_seq for r in snapshot.responses] == [1, 2]
        assert snapshot.bar_count == 2

    def test_a_failing_second_response_costs_the_good_first_one_too(self) -> None:
        fetch = RawChartFetch(
            index_symbol=TWII,
            as_of=datetime(2024, 2, 1, tzinfo=UTC),
            source="yfinance",
            responses=(_raw_response(1),),
            reason="第 2/2 份回應：yfinance 回應非預期的 HTTP 狀態，暫不可用。",
        )
        snapshot = fetch_replay_index_snapshot(
            FakeReplayProvider(fetch), index_symbol=TWII, start=START, end=END
        )
        _assert_failed_closed(snapshot)
        assert "2/2" in (snapshot.reason or "")

    def test_provider_exceptions_are_not_swallowed(self) -> None:
        class Exploding:
            def get_index_raw_responses(
                self, index_symbol: str, start: date, end: date
            ) -> RawChartFetch:
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            fetch_replay_index_snapshot(Exploding(), index_symbol=TWII, start=START, end=END)


# --------------------------------------------------------------------------- #
# Acceptance (f): symbols
# --------------------------------------------------------------------------- #


class TestAcceptanceFSymbols:
    @pytest.mark.parametrize(
        "symbol", ["^GSPC", "^NDX", "^SOX", "TWII", "^twii", "2330", "", "^TWII "]
    )
    def test_other_symbols_are_unavailable_with_zero_transport_calls(self, symbol: str) -> None:
        wire = Wire(_jan_payload())
        snapshot = fetch_replay_index_snapshot(
            wire.adapter(), index_symbol=symbol, start=START, end=END
        )
        _assert_failed_closed(snapshot)
        assert wire.requests == []
        assert "不接受" in (snapshot.reason or "")

    @pytest.mark.parametrize("symbol", ["^GSPC", "^NDX", "^SOX"])
    def test_provider_is_not_called_for_other_symbols(self, symbol: str) -> None:
        provider = FakeReplayProvider(_good_fetch())
        _assert_failed_closed(
            fetch_replay_index_snapshot(provider, index_symbol=symbol, start=START, end=END)
        )
        assert provider.calls == []

    def test_the_only_accepted_symbol_is_the_tw_benchmark(self) -> None:
        assert MARKET_BENCHMARK["TW"].series_symbol == TWII
        wire = Wire(_jan_payload())
        _fetch(wire)
        assert {r.url.path for r in wire.requests} == {"/v8/finance/chart/^TWII"}

    def test_provider_is_always_asked_for_the_benchmark_symbol(self) -> None:
        provider = FakeReplayProvider(_good_fetch())
        fetch_replay_index_snapshot(provider, index_symbol=TWII, start=START, end=END)
        assert [call[0] for call in provider.calls] == [MARKET_BENCHMARK["TW"].series_symbol]


# --------------------------------------------------------------------------- #
# Acceptance (g): existing paths unchanged
# --------------------------------------------------------------------------- #


class TestAcceptanceGExistingPathsUnchanged:
    # The pinned sets below are the fields/methods as of the commit that introduced the
    # replay fetch; they are asserted with set equality, so adding or removing one fails.
    def test_price_bar_fields(self) -> None:
        assert set(PriceBar.model_fields) == {
            "symbol",
            "market",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "currency",
            "as_of",
            "source",
        }

    def test_provider_result_fields(self) -> None:
        assert set(ProviderResult.model_fields) == {
            "bars",
            "status",
            "as_of",
            "source",
            "staleness_minutes",
            "is_within_ttl",
            "reason",
            "complete",
            "rejection",
        }

    def test_market_data_provider_abstract_methods(self) -> None:
        assert set(MarketDataProvider.__abstractmethods__) == {"get_daily_bars"}

    def test_existing_index_entry_points_still_exist(self) -> None:
        for name in (
            "IndexSeriesService",
            "IndexProviderBridge",
            "load_index_series",
            "load_market_benchmark",
            "load_index_bars",
        ):
            assert hasattr(index_module, name)
        assert callable(load_index_series) and callable(load_market_benchmark)

    def test_get_index_daily_bars_is_unchanged_by_the_shared_parse(self) -> None:
        wire = Wire(_jan_payload())
        result = wire.adapter().get_index_daily_bars(TWII, START, END)
        assert result.status is DataStatus.BACKUP
        assert [bar.date for bar in result.bars] == JAN_DAYS
        assert all(bar.market == "TW" and bar.currency == "TWD" for bar in result.bars)
        assert result.bars[0].open == Decimal("17900.5")
