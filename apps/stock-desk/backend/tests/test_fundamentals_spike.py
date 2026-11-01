"""Tests for ``scripts/fundamentals_spike.py``.

Every HTTP response here is synthetic and served by a fake transport: no test
touches the network, a database, or a real credential. The source-guard tests
at the bottom pin the spike's read-only promises (no SQLite, no ``app`` import,
no file writes, GET only).
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import date
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND / "scripts" / "fundamentals_spike.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fundamentals_spike", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


spike = _load()

TODAY = date(2026, 11, 1)
FAKE_UA = "Test Person test.person@example.com"
FAKE_TOKEN = "fm-token-ABCDEF123456"
FAKE_KEY = "AVKEY9876543210"
FULL_ENV = {
    "SEC_USER_AGENT": FAKE_UA,
    "FINMIND_API_TOKEN": FAKE_TOKEN,
    "ALPHA_VANTAGE_API_KEY": FAKE_KEY,
}


# ------------------------------------------------------------------ fixtures


def _entry(
    end: str,
    val: float,
    *,
    fp: str = "FY",
    form: str = "10-K",
    filed: str = "2025-11-01",
    start: str | None = None,
    fy: int = 2025,
    frame: str | None = None,
    accn: str | None = "0000000000-25-000001",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "end": end,
        "val": val,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }
    if accn is None:
        del row["accn"]
    if start is not None:
        row["start"] = start
    if frame is not None:
        row["frame"] = frame
    return row


def history_rows(
    first: int = 2019,
    last: int = 2025,
    *,
    legacy_comparative: bool = False,
    restate: bool = True,
    frame_everywhere: bool = False,
) -> list[dict[str, Any]]:
    """Annual facts as EDGAR lists them: each 10-K repeats the prior year as a comparative.

    Every 10-K has its own accession number and a single fiscal year; only the filing's own
    year carries a frame, as in the real data.
    """
    rows: list[dict[str, Any]] = []
    for year in range(first, last + 1):
        accn = f"0000320193-{year % 100:02d}-000106"
        periods = [year]
        if year > first or legacy_comparative:
            periods.append(year - 1)
        for period in periods:
            value = float(period * 10)
            if restate and period == 2022 and year == 2023:
                value += 1.0
            rows.append(
                _entry(
                    f"{period}-09-28",
                    value,
                    start=f"{period - 1}-09-29",
                    fy=year,
                    fp="FY",
                    filed=f"{year}-11-01",
                    accn=accn,
                    frame=f"CY{period - 1}" if period == year or frame_everywhere else None,
                )
            )
        rows.append(
            _entry(
                f"{year}-03-30",
                float(year),
                fp="Q2",
                form="10-Q",
                start=f"{year - 1}-09-29",
                fy=year,
                filed=f"{year}-05-01",
                accn=f"0000320193-{year % 100:02d}-000050",
            )
        )
    return rows


def _tag(unit: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"label": "x", "description": "y", "units": {unit: rows}}


def _flow_rows() -> list[dict[str, Any]]:
    return [
        _entry("2025-03-29", 10.0, fp="Q2", form="10-Q", start="2024-09-29", filed="2025-05-01"),
        _entry("2025-09-27", 40.0, fp="FY", start="2024-09-29", frame="CY2025"),
        _entry("2025-06-28", 25.0, fp="Q3", form="10-Q", start="2024-09-29", filed="2025-08-01"),
        _entry("2024-09-28", 38.0, fp="FY", start="2023-10-01", fy=2024, filed="2024-11-01"),
    ]


def companyfacts(
    tags: dict[tuple[str, str], list[dict[str, Any]]], unit: str = "USD"
) -> dict[str, Any]:
    facts: dict[str, dict[str, Any]] = {}
    for (namespace, tag), rows in tags.items():
        facts.setdefault(namespace, {})[tag] = _tag(unit, rows)
    return {"cik": 320193, "entityName": "Synthetic Corp", "facts": facts}


FULL_TAGS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsOfDividends",
    "ShareBasedCompensation",
    "Revenues",
    "NetIncomeLoss",
    "EarningsPerShareDiluted",
)


def full_facts(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A company that uses the primary tag for every whitelist item."""
    flow = history_rows() if rows is None else rows
    return companyfacts(
        {
            **{("us-gaap", tag): flow for tag in FULL_TAGS},
            ("dei", "EntityCommonStockSharesOutstanding"): [
                _entry("2025-10-17", 14776353000, fp="FY", form="10-K")
            ],
        }
    )


def alt_capex_facts() -> dict[str, Any]:
    """Uses the alternate CapEx tag and has no buyback, dividend or SBC tags."""
    flow = history_rows()
    return companyfacts(
        {
            ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"): flow,
            ("us-gaap", "PaymentsToAcquireProductiveAssets"): flow,
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"): flow,
            ("us-gaap", "NetIncomeLoss"): flow,
            ("us-gaap", "EarningsPerShareDiluted"): flow,
        }
    )


def foreign_facts() -> dict[str, Any]:
    """An IFRS filer reporting in TWD: nothing under us-gaap."""
    rows = history_rows()
    facts = {
        "ifrs-full": {
            "CashFlowsFromUsedInOperatingActivities": _tag("TWD", rows),
            "BasicEarningsLossPerShare": _tag("TWD/shares", rows),
        },
        "dei": {"EntityCommonStockSharesOutstanding": _tag("shares", rows[:1])},
    }
    return {"cik": 1046179, "entityName": "Foreign Co", "facts": facts}


def submissions_doc(
    *,
    sic: str = "3571",
    entity_type: str = "operating",
    category: str = "Large accelerated filer",
    fiscal_year_end: str = "0928",
    columns: tuple[str, ...] = (
        "accessionNumber",
        "filingDate",
        "acceptanceDateTime",
        "form",
        "reportDate",
    ),
) -> dict[str, Any]:
    recent: dict[str, list[str]] = {
        "accessionNumber": ["0000320193-25-000106", "0000320193-25-000073", "0000320193-25-000070"],
        "filingDate": ["2025-11-01", "2025-08-01", "2025-09-15"],
        "acceptanceDateTime": [
            "2025-11-01T06:01:36.000Z",
            "2025-08-01T06:01:36.000Z",
            "2025-09-15T06:01:36.000Z",
        ],
        "form": ["10-K", "10-Q", "8-K"],
        "reportDate": ["2025-09-28", "2025-06-28", ""],
    }
    return {
        "name": "Synthetic Corp",
        "sic": sic,
        "sicDescription": "Electronic Computers" if sic else "",
        "entityType": entity_type,
        "category": category,
        "fiscalYearEnd": fiscal_year_end,
        "exchanges": ["Nasdaq"],
        "filings": {"recent": {k: v for k, v in recent.items() if k in columns}},
    }


FAIR_ACCESS_HTML = (
    "<html><head><style>p{}</style></head><body><p>Current guidelines limit users to a maximum "
    "of 10 requests per second. Declare your User-Agent in the request header with a contact "
    "address.</p><p>Unrelated sentence.</p></body></html>"
)

TICKER_MAP = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1018724, "ticker": "AMZN", "title": "Amazon"},
    "2": {"cik_str": 50863, "ticker": "INTC", "title": "Intel"},
    "3": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire"},
    "4": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet"},
    "5": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet"},
    "6": {"cik_str": 884394, "ticker": "SPY", "title": "SPDR S&P 500 ETF Trust"},
    "7": {"cik_str": 1174610, "ticker": "TQQQ", "title": "ProShares Trust II"},
    "8": {"cik_str": 1046179, "ticker": "TSM", "title": "Taiwan Semiconductor"},
    "9": {"cik_str": 1045810, "ticker": "NVDA", "title": "Nvidia"},
    "10": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla"},
    "11": {"cik_str": 1577552, "ticker": "BABA", "title": "Alibaba"},
}

SWAGGER_V2 = {
    "swagger": "2.0",
    "paths": {
        "/opendata/t187ap07_L_ci": {
            "get": {
                "summary": "上市公司資產負債表-一般業",
                "responses": {
                    "200": {"schema": {"type": "array", "items": {"$ref": "#/definitions/Bs"}}}
                },
            }
        },
        "/opendata/t187ap06_L_ci": {
            "get": {
                "summary": "上市公司綜合損益表-一般業",
                "responses": {
                    "200": {"schema": {"type": "array", "items": {"$ref": "#/definitions/Is"}}}
                },
            }
        },
        "/opendata/t187ap05_L": {
            "get": {
                "summary": "上市公司資產負債表-金融業",
                "responses": {
                    "200": {"schema": {"type": "array", "items": {"$ref": "#/definitions/Is"}}}
                },
            }
        },
        "/exchangeReport/STOCK_DAY_ALL": {
            "get": {"summary": "每日收盤行情", "responses": {"200": {"schema": {}}}}
        },
    },
    "definitions": {
        "Bs": {"type": "object", "properties": {"公司代號": {}, "庫藏股票": {}, "資產總額": {}}},
        "Is": {"type": "object", "properties": {"公司代號": {}, "營業收入": {}}},
    },
}

SWAGGER_V3 = {
    "openapi": "3.0.1",
    "paths": {
        "/mopsfin_t187ap_cashflow": {
            "get": {
                "summary": "Cash Flow Statement 現金流量表",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Cf"},
                                }
                            }
                        }
                    }
                },
            }
        },
        "/tpex_treasury": {
            "get": {
                "description": "上櫃公司庫藏股買回",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"properties": {"SecuritiesCompanyCode": {}}},
                                }
                            }
                        }
                    }
                },
            }
        },
    },
    "components": {"schemas": {"Cf": {"properties": {"Code": {}, "OperatingCashFlow": {}}}}},
}

FINMIND_ENUM_SOURCE = (
    "class Dataset(str, Enum):\n"
    '    TaiwanStockBalanceSheet = "TaiwanStockBalanceSheet"\n'
    '    TaiwanStockCashFlowsStatement = "TaiwanStockCashFlowsStatement"\n'
    "    TaiwanStockInstitutionalInvestorsBuySell = (\n"
    '        "TaiwanStockInstitutionalInvestorsBuySell"\n'
    "    )\n"
    '    USStockPrice = "USStockPrice"\n'
)

FINMIND_ROWS = [
    {
        "date": f"2025-{m}",
        "stock_id": "2330",
        "type": t,
        "value": v,
        "origin_name": o,
    }
    for m, v in (("03-31", 1.0), ("06-30", 2.0), ("09-30", 3.0))
    for t, o in (
        ("CashFlowsFromOperatingActivities", "營業活動之淨現金流入"),
        ("PropertyAndPlantAndEquipment", "取得不動產、廠房及設備"),
        ("Depreciation", "折舊費用"),
    )
]

AV_DAILY = {
    "Meta Data": {"2. Symbol": "AAPL", "3. Last Refreshed": "2026-10-30"},
    "Time Series (Daily)": {
        "2026-10-30": {"1. open": "1", "4. close": "2", "5. volume": "3"},
        "2026-10-29": {"1. open": "1", "4. close": "2", "5. volume": "3"},
        "2026-10-28": {"1. open": "1", "4. close": "2", "5. volume": "3"},
    },
}


class FakeNet:
    """Routes URLs to canned responses and records every call."""

    def __init__(self, overrides: Mapping[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.overrides = dict(overrides or {})

    @staticmethod
    def _json(obj: object, status: int = 200, headers: Mapping[str, str] | None = None) -> Any:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return spike.HttpResult(status, body, None, headers or {}, len(body) // 6)

    def __call__(self, url: str, headers: Mapping[str, str]) -> Any:
        self.calls.append((url, dict(headers)))
        for prefix, result in self.overrides.items():
            if url.startswith(prefix):
                return result
        if url == spike.SEC_TICKER_URL:
            return self._json(TICKER_MAP)
        if url.startswith("https://data.sec.gov/submissions/CIK0000884394"):
            return self._json(
                submissions_doc(sic="", entity_type="other", category="", fiscal_year_end="1231")
            )
        if url.startswith("https://data.sec.gov/submissions/"):
            if "If-None-Match" in headers:
                return spike.HttpResult(304, b"")
            return self._json(
                submissions_doc(),
                headers={"etag": '"abc123"', "last-modified": "Sat, 01 Nov 2025 06:00:00 GMT"},
            )
        if url == spike.SEC_DOCS_URL:
            return spike.HttpResult(200, FAIR_ACCESS_HTML.encode("utf-8"))
        if url.startswith("https://data.sec.gov/api/xbrl/companyfacts/CIK0000884394"):
            return spike.HttpResult(404, b"<Error>NoSuchKey</Error>")
        if url.startswith(
            (
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0001046179",
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0001577552",
            )
        ):
            return self._json(foreign_facts())
        if url.startswith("https://data.sec.gov/api/xbrl/companyfacts/CIK0000050863"):
            return self._json(alt_capex_facts())
        if url.startswith("https://data.sec.gov/api/xbrl/companyfacts/"):
            return self._json(full_facts())
        if url == spike.TWSE_SWAGGER_URL:
            return self._json(SWAGGER_V2)
        if url == spike.TPEX_SWAGGER_URL:
            return self._json(SWAGGER_V3)
        if url.startswith(spike.TWSE_BASE_URL + "/opendata/"):
            return self._json([{"公司代號": "2330", "庫藏股票": "0", "資產總額": "123"}])
        if url.startswith(spike.TPEX_BASE_URL + "/"):
            return self._json([{"Code": "6488", "OperatingCashFlow": "9"}])
        if url == spike.FINMIND_ENUM_URL:
            return spike.HttpResult(200, FINMIND_ENUM_SOURCE.encode("utf-8"))
        if url.startswith(spike.FINMIND_USER_INFO_URL):
            return self._json({"user_count": 12, "api_request_limit": 600, "email": "x@y.com"})
        if url.startswith(spike.FINMIND_DATA_URL):
            return self._json({"msg": "success", "status": 200, "data": FINMIND_ROWS})
        if url.startswith(spike.ALPHA_URL):
            return self._json(AV_DAILY)
        return spike.HttpResult(404, b"not found")


def run_main(
    net: Callable[[str, Mapping[str, str]], Any],
    env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    lines: list[str] = []
    code = spike.main(
        [],
        env=FULL_ENV if env is None else env,
        transport=net,
        sleep=lambda _seconds: None,
        emit=lines.append,
        today=TODAY,
    )
    return code, "\n".join(lines)


# ------------------------------------------------------------------ redaction


def test_redactor_masks_secret_values_and_encoded_forms() -> None:
    redact = spike.Redactor(["abc def ghi!", "plain-secret-1"])
    text = "a abc def ghi! b abc%20def%20ghi%21 c abc+def+ghi%21 d plain-secret-1"
    out = redact(text)
    assert "ghi" not in out and "plain-secret-1" not in out
    assert out.count(spike.MASK) == 4


def test_redactor_masks_emails_and_credential_fragments() -> None:
    redact = spike.Redactor([])
    out = redact(
        "ua Jane Doe jane.doe+x@mail.example.org "
        "url ?token=SECRET1&apikey=SECRET2&key=SECRET3 "
        'hdr Authorization: Bearer SECRET4 json "token": "SECRET5"'
    )
    for leaked in ("jane.doe", "SECRET1", "SECRET2", "SECRET3", "SECRET4", "SECRET5"):
        assert leaked not in out
    assert "token=***&apikey=***&key=***" in out
    assert "dXNlcjpwYXNz" not in redact("Authorization: Basic dXNlcjpwYXNz")


def test_redactor_ignores_empty_and_tiny_secrets() -> None:
    redact = spike.Redactor(["", "  ", "ab"])
    assert redact("ab cd") == "ab cd"


def test_redactor_masks_longest_secret_first() -> None:
    redact = spike.Redactor(["secret", "secret-longer-value"])
    assert "longer" not in redact("x secret-longer-value y")


# ------------------------------------------------------------------ http layer


def test_budget_refuses_request_beyond_cap() -> None:
    budget = spike.Budget(2)
    budget.take()
    budget.take()
    with pytest.raises(spike.BudgetExceededError):
        budget.take()
    assert budget.used == 2


def test_fetcher_spaces_sec_requests_and_other_hosts_differently() -> None:
    now = [100.0]
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    fetcher = spike.Fetcher(
        transport=lambda url, headers: spike.HttpResult(200, b"{}"),
        budget=spike.Budget(10),
        sleep=fake_sleep,
        clock=lambda: now[0],
    )
    fetcher.get("https://www.sec.gov/a")
    fetcher.get("https://data.sec.gov/b")  # same SEC bucket
    assert slept == [pytest.approx(spike.SEC_MIN_GAP_SECONDS)]
    slept.clear()
    fetcher.get("https://openapi.twse.com.tw/a")
    fetcher.get("https://openapi.twse.com.tw/b")
    assert slept == [pytest.approx(spike.DEFAULT_MIN_GAP_SECONDS)]
    slept.clear()
    fetcher.get("https://www.alphavantage.co/a")  # first call for that host
    assert slept == []


def test_fetcher_counts_requests_even_when_transport_fails() -> None:
    budget = spike.Budget(5)
    fetcher = spike.Fetcher(
        transport=lambda url, headers: spike.HttpResult(None, b"", "URLError: down"),
        budget=budget,
        sleep=lambda _s: None,
    )
    assert fetcher.get("https://example.test/").status is None
    assert budget.used == 1


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200, encoding: str = "") -> None:
        self._body = body
        self.status = status
        self.headers = {"Content-Encoding": encoding}

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]


def test_urllib_transport_decodes_gzip_and_sends_get(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        seen.append(request)
        assert timeout == spike.REQUEST_TIMEOUT_SECONDS
        return _FakeResponse(gzip.compress(b'{"ok": 1}'), encoding="gzip")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = spike.urllib_transport("https://example.test/x", {"User-Agent": "ua"})
    assert (result.status, result.body) == (200, b'{"ok": 1}')
    assert seen[0].get_method() == "GET" and seen[0].data is None


def test_urllib_transport_reports_http_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        headers = Message()
        headers["Content-Encoding"] = ""
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", headers, io.BytesIO(b"denied")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = spike.urllib_transport("https://example.test/x", {})
    assert result.status == 403 and result.body == b"denied"


def test_urllib_transport_turns_network_errors_into_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("tunnel failed")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = spike.urllib_transport("https://example.test/x", {})
    assert result.status is None and "tunnel failed" in (result.error or "")


def test_urllib_transport_discards_oversize_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spike, "MAX_BODY_BYTES", 4)
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout: _FakeResponse(b"123456789")
    )
    result = spike.urllib_transport("https://example.test/x", {})
    assert result.status == 200 and result.body == b"" and "larger" in (result.error or "")


def test_gzip_decode_falls_back_to_raw_on_bad_data() -> None:
    assert spike._decode_body(b"not gzip", "gzip") == b"not gzip"
    assert spike._decode_body(b"abc", "") == b"abc"


# ------------------------------------------------------------------ SEC parsing


def test_parse_ticker_map_handles_both_layouts() -> None:
    assert spike.parse_ticker_map(TICKER_MAP)["AAPL"] == 320193
    exchange = {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[320193, "A", "aapl", "N"]],
    }
    assert spike.parse_ticker_map(exchange) == {"AAPL": 320193}
    assert spike.parse_ticker_map(["junk"]) == {}
    assert spike.parse_ticker_map({"fields": ["x"], "data": [[1]]}) == {}
    assert spike.parse_ticker_map({"0": {"cik_str": "bad", "ticker": "X"}}) == {}


def test_analyze_companyfacts_finds_primary_tags_and_samples() -> None:
    report = spike.analyze_companyfacts(full_facts(), TODAY)
    assert report is not None
    assert {c: r.verdict for c, r in report.concepts.items()} == {
        "OCF": "EXISTS",
        "CapEx": "EXISTS",
        "Buyback": "EXISTS",
        "Dividends": "EXISTS",
        "SBC": "EXISTS",
        "Revenue": "EXISTS",
        "NetIncome": "EXISTS",
        "DilutedEPS": "EXISTS",
        "Shares": "EXISTS",
    }
    ocf = report.concepts["OCF"].found[0]
    assert ocf.units == {"USD": len(history_rows())}
    assert ocf.latest_fy is not None and ocf.latest_fy["end"] == "2025-09-28"
    assert ocf.latest_interim is not None and ocf.latest_interim["fp"] == "Q2"
    assert ocf.bad_dates == {"end": 0, "start": 0, "filed": 0}
    assert ocf.durations["~12m"] == 13 and ocf.durations["~6m"] == 7
    assert not ocf.stale and ocf.verified
    assert "us-gaap:PaymentsOfDividendsCommonStock" in report.concepts["Dividends"].missing


def test_analyze_companyfacts_reports_missing_and_alternate_tags() -> None:
    report = spike.analyze_companyfacts(alt_capex_facts(), TODAY)
    assert report is not None
    capex = report.concepts["CapEx"]
    assert [s.tag for s in capex.found] == ["PaymentsToAcquireProductiveAssets"]
    assert report.concepts["Buyback"].verdict == "MISSING"
    assert report.concepts["Shares"].found == []


def test_analyze_companyfacts_flags_bad_dates_stale_and_instant_rows() -> None:
    rows = [
        _entry("2020-12-31", 1.0, filed="20210201"),
        {"end": "31/12/2020", "val": 2.0, "fp": "FY", "form": "10-K", "filed": "2021-02-01"},
        _entry("2020-12-31", 3.0, start="bad-date"),
        _entry("2020-12-31", 4.0, start="2020-01-01"),
    ]
    report = spike.analyze_companyfacts(
        companyfacts({("us-gaap", "ShareBasedCompensation"): rows}), TODAY
    )
    assert report is not None
    summary = report.concepts["SBC"].found[0]
    assert summary.bad_dates == {"end": 1, "start": 1, "filed": 1}
    assert summary.stale
    assert summary.durations["instant-or-bad"] == 3


def test_analyze_companyfacts_rejects_unexpected_layout() -> None:
    assert spike.analyze_companyfacts([], TODAY) is None
    assert spike.analyze_companyfacts({"facts": "x"}, TODAY) is None
    report = spike.analyze_companyfacts(
        {"facts": {"us-gaap": {"ShareBasedCompensation": 5}}}, TODAY
    )
    assert report is not None and report.concepts["SBC"].verdict == "MISSING"


def test_summarize_tag_tolerates_malformed_units() -> None:
    summary = spike.summarize_tag(
        "us-gaap", "X", {"units": {"USD": "oops", "shares": [1, {}]}}, TODAY
    )
    assert summary.entries == 1 and summary.latest_end is None and summary.sample_unit == "shares"
    empty = spike.summarize_tag("us-gaap", "X", {}, TODAY)
    assert empty.entries == 0 and empty.sample_unit is None


# ------------------------------------------------------------------ OpenAPI parsing


def test_parse_openapi_resolves_v2_definitions_and_v3_components() -> None:
    v2 = {d.path: d for d in spike.parse_openapi(SWAGGER_V2)}
    assert v2["/opendata/t187ap07_L_ci"].fields == ("公司代號", "庫藏股票", "資產總額")
    assert v2["/exchangeReport/STOCK_DAY_ALL"].fields == ()
    v3 = {d.path: d for d in spike.parse_openapi(SWAGGER_V3)}
    assert v3["/mopsfin_t187ap_cashflow"].fields == ("Code", "OperatingCashFlow")
    assert v3["/tpex_treasury"].summary.startswith("上櫃公司庫藏股")
    assert v3["/tpex_treasury"].fields == ("SecuritiesCompanyCode",)


def test_parse_openapi_handles_garbage() -> None:
    assert spike.parse_openapi([]) == []
    assert spike.parse_openapi({"paths": {"/x": "not a dict", "/y": {"post": {}}}}) == []
    assert spike._resolve_ref({}, "http://elsewhere") is None
    assert spike._resolve_ref({"a": 1}, "#/a/b") is None
    assert spike._schema_fields({}, {"$ref": "#/missing"}) == []


def test_classify_and_field_hits_separate_dataset_from_column_level() -> None:
    datasets = spike.parse_openapi(SWAGGER_V2)
    hits = spike.classify(datasets)
    assert hits["cashflow"] == [] and hits["treasury"] == []
    assert [d.path for d in hits["statement"]] == [
        "/opendata/t187ap07_L_ci",
        "/opendata/t187ap06_L_ci",
        "/opendata/t187ap05_L",
    ]
    column_hits = spike.field_hits(datasets, "treasury")
    assert [(d.path, m) for d, m in column_hits] == [("/opendata/t187ap07_L_ci", ["庫藏股票"])]
    v3_hits = spike.classify(spike.parse_openapi(SWAGGER_V3))
    assert len(v3_hits["cashflow"]) == 1 and len(v3_hits["treasury"]) == 1


def test_pick_samples_prefers_cashflow_and_treasury_then_dedupes_and_limits() -> None:
    v3 = spike.parse_openapi(SWAGGER_V3)
    assert [d.path for d in spike.pick_samples(v3, 5)] == [
        "/mopsfin_t187ap_cashflow",
        "/tpex_treasury",
    ]
    assert len(spike.pick_samples(v3, 1)) == 1
    v2 = spike.parse_openapi(SWAGGER_V2)
    assert [d.path for d in spike.pick_samples(v2, 3)] == [
        "/opendata/t187ap07_L_ci",
        "/opendata/t187ap06_L_ci",
        "/opendata/t187ap05_L",
    ]


# ------------------------------------------------------------------ FinMind parsing


def test_parse_enum_names_reads_single_and_wrapped_assignments() -> None:
    names = spike.parse_enum_names(FINMIND_ENUM_SOURCE)
    assert "TaiwanStockCashFlowsStatement" in names
    assert "TaiwanStockInstitutionalInvestorsBuySell" in names
    assert "USStockPrice" in names


def test_analyze_finmind_rows_matches_keywords_in_type_and_chinese_name() -> None:
    out = spike.analyze_finmind_rows(FINMIND_ROWS)
    assert out["dates"] == ["2025-03-31", "2025-06-30", "2025-09-30"]
    assert set(out["matched"]) == {
        "CashFlowsFromOperatingActivities",
        "PropertyAndPlantAndEquipment",
    }
    assert len(out["types"]) == 3


# ------------------------------------------------------------------ end to end


def test_full_run_with_all_credentials_prints_verdicts_and_leaks_nothing() -> None:
    net = FakeNet()
    code, out = run_main(net)
    assert code == 0
    for secret in (FAKE_UA, "test.person", "example.com", FAKE_TOKEN, FAKE_KEY, "x@y.com"):
        assert secret not in out, secret
    # The secrets were genuinely used on the wire: masking is the only thing hiding them.
    assert any(FAKE_TOKEN in url for url, _ in net.calls)
    assert any(FAKE_KEY in url for url, _ in net.calls)
    assert any(h.get("User-Agent") == FAKE_UA for _, h in net.calls)
    assert any(h.get("Authorization") == f"Bearer {FAKE_TOKEN}" for _, h in net.calls)

    assert len(net.calls) == 22
    assert "requests used: 22 / 30" in out
    assert "[EXISTS] SEC/ticker-map" in out
    assert "[EXISTS] SEC/AAPL/CapEx" in out
    assert "[EXISTS] SEC/INTC/CapEx -- primary missing, alternate(s): " in out
    assert "PaymentsToAcquireProductiveAssets" in out
    assert "[MISSING] SEC/INTC/Buyback" in out
    assert "[EXISTS] SEC/AAPL/date-format" in out
    assert "[MISSING] TWSE/cash flow statement" in out
    assert "no dataset-level match; 1 dataset(s) only carry it as a column" in out
    assert "[EXISTS] TPEx/cash flow statement" in out
    assert "[EXISTS] TPEx/treasury stock" in out
    assert "[MISSING] FinMind/treasury dataset name" in out
    assert "[EXISTS] FinMind/quota" in out
    assert "quota fields: {'user_count': 12, 'api_request_limit': 600}" in out
    assert "[EXISTS] FinMind/cash-flow TWSE 2330" in out
    assert "[EXISTS] FinMind/cash-flow TPEx 6488" in out
    assert "[EXISTS] AlphaVantage/daily" in out
    assert "newest 2026-10-30 (2 days before today)" in out
    assert "apikey=***" in out and "token=" not in out.replace("token=***", "")


def test_request_plan_in_header_matches_what_a_normal_run_sends() -> None:
    doc = spike.__doc__ or ""
    assert re.search(r"Normal run\s+22\b", doc)
    assert f"cap {spike.REQUEST_CAP}" in doc and spike.REQUEST_CAP == 30
    assert 22 + spike.MAX_HOLDINGS + 1 <= spike.REQUEST_CAP  # worst case: holdings and map fallback


def test_run_without_credentials_skips_credentialed_checks_and_sends_no_sec_or_av() -> None:
    net = FakeNet()
    code, out = run_main(net, env={})
    assert code == 0
    urls = [u for u, _ in net.calls]
    assert not any("sec.gov" in u or "alphavantage" in u for u in urls)
    assert not any("user_info" in u for u in urls)
    assert "[SKIPPED] SEC/all" in out
    assert "[SKIPPED] AlphaVantage/daily" in out
    assert "[SKIPPED] FinMind/quota" in out
    assert "FINMIND_API_TOKEN is NOT set" in out
    assert "env SEC_USER_AGENT is NOT set" in out
    assert all("token=" not in u for u in urls)  # no token appended when none is configured


def test_sec_user_agent_without_email_is_refused_before_any_request() -> None:
    net = FakeNet()
    _, out = run_main(net, env={"SEC_USER_AGENT": "no-contact-info"})
    assert not any("sec.gov" in u for u, _ in net.calls)
    assert "[SKIPPED] SEC/all" in out


def test_ticker_map_falls_back_then_uses_builtin_ciks() -> None:
    down = spike.HttpResult(403, b"denied")
    net = FakeNet({"https://www.sec.gov/files/": down})
    _, out = run_main(net, env={"SEC_USER_AGENT": FAKE_UA})
    sec_urls = [u for u, _ in net.calls if "sec.gov" in u]
    assert sec_urls[:2] == [spike.SEC_TICKER_URL, spike.SEC_TICKER_FALLBACK_URL]
    assert any("CIK0000320193" in u for u in sec_urls)
    assert "built-in CIKs (NOT verified by this run)" in out
    assert "[ERROR] SEC/ticker-map https://www.sec.gov/files/company_tickers.json" in out
    assert FAKE_UA not in out


def test_unknown_ticker_in_map_is_reported_missing() -> None:
    only_aapl = {"0": TICKER_MAP["0"]}
    net = FakeNet({spike.SEC_TICKER_URL: spike.HttpResult(200, json.dumps(only_aapl).encode())})
    _, out = run_main(net, env={"SEC_USER_AGENT": FAKE_UA})
    assert "[MISSING] SEC/AMZN/companyfacts -- ticker not in ticker map" in out


def test_every_source_down_reports_errors_without_crashing() -> None:
    def dead(url: str, headers: Mapping[str, str]) -> Any:
        return spike.HttpResult(None, b"", f"URLError: tunnel failed for {url}")

    code, out = run_main(dead)
    assert code == 0
    assert "[ERROR] TWSE/swagger" in out and "[ERROR] TPEx/swagger" in out
    assert "[ERROR] AlphaVantage/daily" in out
    assert "[ERROR] FinMind/dataset enum" in out
    assert "[ERROR] FinMind/quota" in out
    assert FAKE_KEY not in out and FAKE_TOKEN not in out
    # one failed request is not retried
    assert "requests used: " in out


def test_http_error_statuses_and_bad_json_are_reported_per_check() -> None:
    net = FakeNet(
        {
            "https://data.sec.gov/": spike.HttpResult(429, b"slow down"),
            spike.TWSE_SWAGGER_URL: spike.HttpResult(200, b"<html>not json</html>"),
            spike.FINMIND_DATA_URL: spike.HttpResult(
                200, json.dumps({"msg": "Requests reach the limit", "status": 402}).encode()
            ),
            spike.ALPHA_URL: spike.HttpResult(200, b"{broken"),
            spike.FINMIND_USER_INFO_URL: spike.HttpResult(401, b"{}"),
        }
    )
    _, out = run_main(net)
    assert "[ERROR] SEC/AAPL/companyfacts -- HTTP 429" in out
    assert "[ERROR] TWSE/swagger" in out
    assert "JSON parse failed" in out
    assert "[ERROR] FinMind/cash-flow TWSE 2330" in out
    assert "[ERROR] AlphaVantage/daily" in out
    assert "[ERROR] FinMind/quota" in out


def test_alpha_vantage_vendor_messages_are_reported_and_key_echo_is_masked() -> None:
    message = f"Thank you! Your API key is {FAKE_KEY} and you hit the limit. apikey={FAKE_KEY}"
    net = FakeNet({spike.ALPHA_URL: spike.HttpResult(200, json.dumps({"Note": message}).encode())})
    _, out = run_main(net)
    assert "Note: Thank you!" in out
    assert "[ERROR] AlphaVantage/daily -- vendor returned 'Note'" in out
    assert FAKE_KEY not in out


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"Error Message": "bad symbol"}, "vendor returned 'Error Message'"),
        ({"Information": "premium only"}, "vendor returned 'Information'"),
        ({"surprise": 1}, "no 'Time Series (Daily)'"),
        ([1, 2], "HTTP 200"),
    ],
)
def test_alpha_vantage_other_failure_shapes(payload: object, expected: str) -> None:
    net = FakeNet({spike.ALPHA_URL: spike.HttpResult(200, json.dumps(payload).encode())})
    _, out = run_main(net)
    assert "[ERROR] AlphaVantage/daily" in out and expected in out


def test_finmind_empty_rows_and_unexpected_json_shapes() -> None:
    empty = FakeNet(
        {
            spike.FINMIND_DATA_URL: spike.HttpResult(
                200, b'{"msg": "success", "status": 200, "data": []}'
            )
        }
    )
    _, out = run_main(empty)
    assert "[MISSING] FinMind/cash-flow TWSE 2330 -- no usable rows" in out
    bad = FakeNet({spike.FINMIND_DATA_URL: spike.HttpResult(200, b"[1]")})
    _, out = run_main(bad)
    assert "[ERROR] FinMind/cash-flow TWSE 2330" in out
    no_enum = FakeNet({spike.FINMIND_ENUM_URL: spike.HttpResult(404, b"")})
    _, out = run_main(no_enum)
    assert "[ERROR] FinMind/dataset enum" in out
    user_info_bad = FakeNet({spike.FINMIND_USER_INFO_URL: spike.HttpResult(200, b"[]")})
    _, out = run_main(user_info_bad)
    assert "[ERROR] FinMind/quota" in out


def test_finmind_treasury_dataset_in_enum_is_reported() -> None:
    source = FINMIND_ENUM_SOURCE + '    TaiwanStockTreasuryShares = "TaiwanStockTreasuryShares"\n'
    net = FakeNet({spike.FINMIND_ENUM_URL: spike.HttpResult(200, source.encode())})
    _, out = run_main(net)
    assert "[EXISTS] FinMind/treasury dataset name -- ['TaiwanStockTreasuryShares']" in out


def test_openapi_sample_failures_and_unusable_documents() -> None:
    net = FakeNet(
        {
            spike.TWSE_BASE_URL + "/opendata/t187ap07_L_ci": spike.HttpResult(500, b"boom"),
            spike.TWSE_BASE_URL + "/opendata/t187ap06_L_ci": spike.HttpResult(200, b"{}"),
            spike.TPEX_SWAGGER_URL: spike.HttpResult(200, b'{"paths": {}}'),
        }
    )
    _, out = run_main(net)
    assert "[ERROR] TWSE/sample /opendata/t187ap07_L_ci" in out
    assert "[ERROR] TWSE/sample /opendata/t187ap06_L_ci" in out
    assert "[ERROR] TPEx/swagger" in out


def test_openapi_empty_sample_is_reported_missing() -> None:
    net = FakeNet({spike.TWSE_BASE_URL + "/opendata/": spike.HttpResult(200, b"[]")})
    _, out = run_main(net)
    assert "[MISSING] TWSE/sample /opendata/t187ap07_L_ci -- 0 rows" in out


def test_sec_non_json_and_wrong_layout_are_errors() -> None:
    net = FakeNet(
        {
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193": spike.HttpResult(
                200, b"[]"
            ),
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0001018724": spike.HttpResult(
                200, b"nope"
            ),
        }
    )
    _, out = run_main(net, env={"SEC_USER_AGENT": FAKE_UA})
    assert "[ERROR] SEC/AAPL/companyfacts -- unexpected JSON layout" in out
    assert "[ERROR] SEC/AMZN/companyfacts" in out


def test_request_cap_stops_the_run_and_later_sections_still_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spike, "REQUEST_CAP", 3)
    net = FakeNet()
    _, out = run_main(net)
    assert len(net.calls) == 3
    assert "request cap 3 reached" in out
    assert "requests used: 3 / 3" in out


def test_unexpected_exception_in_one_section_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(ctx: Any) -> None:
        raise RuntimeError(f"explode {FAKE_KEY}")

    monkeypatch.setattr(spike, "SECTIONS", (("SEC", boom), ("AlphaVantage", spike.run_alpha)))
    _, out = run_main(FakeNet())
    assert "[ERROR] SEC/unexpected -- RuntimeError: explode ***" in out
    assert "[EXISTS] AlphaVantage/daily" in out
    assert FAKE_KEY not in out


def test_default_sink_prints_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    code = spike.main(
        [], env={}, transport=lambda u, h: spike.HttpResult(404, b""), sleep=lambda _s: None
    )
    captured = capsys.readouterr().out
    assert code == 0 and "Fundamentals data source spike" in captured
    assert "script_sha256_lf: " in captured and "(unavailable)" not in captured


def test_script_digest_is_stable_across_line_endings() -> None:
    lf = SCRIPT_PATH.read_bytes().replace(b"\r\n", b"\n")
    assert spike.script_digest() == hashlib.sha256(lf).hexdigest()


# ------------------------------------------------------------------ ADR-0038 P items


def _evidence(**reports_by_label: dict[str, Any]) -> Any:
    """Evidence holding analysed companyfacts for the given labels (no network involved)."""
    ev = spike.SecEvidence(attempted=True)
    for label, doc in reports_by_label.items():
        report = spike.analyze_companyfacts(doc, TODAY)
        assert report is not None
        ev.reports[label] = report
    return ev


def _submissions(**overrides: Any) -> Any:
    return spike.analyze_submissions(submissions_doc(**overrides), 200)


def test_p1_partial_when_keys_are_complete_but_frame_is_sparse() -> None:
    result = spike.eval_p1(_evidence(AAPL=full_facts(), AMZN=full_facts()))
    assert result.verdict == "PARTIAL"
    assert "frame on" in result.detail and "cannot be a key" in result.detail
    joined = "\n".join(result.lines)
    assert "accn 322/322 (100.0%)" in joined and "start present on period (flow) facts: " in joined
    assert "fy/fp are filing attributes, not period attributes: yes" in joined


def test_p1_holds_only_if_every_fact_has_a_frame() -> None:
    rows = history_rows(frame_everywhere=True)
    rows = [row for row in rows if row["form"] == "10-K"]
    facts = companyfacts({("us-gaap", "NetCashProvidedByUsedInOperatingActivities"): rows})
    assert spike.eval_p1(_evidence(AAPL=facts)).verdict == "HOLDS"


def test_p1_not_hold_when_accn_is_missing_on_some_fact() -> None:
    rows = history_rows()
    rows[3] = _entry("2022-09-28", 1.0, start="2021-09-29", accn=None)
    result = spike.eval_p1(_evidence(AAPL=full_facts(rows)))
    assert result.verdict == "NOT_HOLD" and "accn" in result.detail


def test_p1_not_hold_when_start_is_missing_on_a_flow_fact() -> None:
    rows = history_rows()
    del rows[0]["start"]
    result = spike.eval_p1(_evidence(AAPL=full_facts(rows)))
    assert result.verdict == "NOT_HOLD" and "start" in result.detail


def test_p1_not_hold_when_one_filing_carries_two_fiscal_years() -> None:
    rows = history_rows()
    assert rows[2]["accn"] == rows[3]["accn"]
    rows[3] = {**rows[3], "fy": 1999}
    result = spike.eval_p1(_evidence(AAPL=full_facts(rows)))
    assert result.verdict == "NOT_HOLD" and "not filing-level" in result.detail


def test_p1_inconclusive_without_us_gaap_facts() -> None:
    assert spike.eval_p1(spike.SecEvidence(attempted=True)).verdict == "INCONCLUSIVE"
    assert spike.eval_p1(_evidence(TSM=foreign_facts())).verdict == "INCONCLUSIVE"


def test_p2_holds_when_original_filings_and_comparatives_are_kept() -> None:
    result = spike.eval_p2(_evidence(AAPL=full_facts()), TODAY)
    assert result.verdict == "HOLDS"
    assert "restated period(s) seen" in result.detail
    assert any("value changed across filings" in line for line in result.lines)


def test_p2_partial_when_earliest_comparatives_lack_their_original_filing() -> None:
    rows = history_rows(legacy_comparative=True)
    result = spike.eval_p2(_evidence(AAPL=full_facts(rows)), TODAY)
    assert result.verdict == "PARTIAL"


def test_p2_not_hold_when_each_period_appears_in_one_filing_only() -> None:
    rows = [
        _entry(f"{y}-09-28", float(y), start=f"{y - 1}-09-29", fy=y + 3, filed=f"{y + 3}-01-01")
        for y in range(2016, 2024)
    ]
    result = spike.eval_p2(_evidence(AAPL=full_facts(rows)), TODAY)
    assert result.verdict == "NOT_HOLD"


def test_p2_inconclusive_without_closed_full_years() -> None:
    rows = [_entry("2026-03-28", 1.0, fp="Q2", form="10-Q", start="2025-09-28")]
    assert spike.eval_p2(_evidence(AAPL=full_facts(rows)), TODAY).verdict == "INCONCLUSIVE"
    assert spike.eval_p2(spike.SecEvidence(attempted=True), TODAY).verdict == "INCONCLUSIVE"


def test_p3_holds_partial_and_not_hold_by_coverage() -> None:
    both = _evidence(AAPL=full_facts(), AMZN=full_facts())
    held = spike.eval_p3(both)
    assert held.verdict == "HOLDS"
    assert any(line.startswith("operating_cash_flow: 2/2") for line in held.lines)

    mixed = _evidence(AAPL=full_facts(), INTC=alt_capex_facts())
    partial = spike.eval_p3(mixed)
    assert partial.verdict == "PARTIAL"
    assert "share_repurchase_paid" in partial.detail
    assert any("INTC/capital_expenditure" in line for line in partial.lines)
    assert any("PaymentsToAcquireProductiveAssets [alternate]" in line for line in partial.lines)

    nobody = _evidence(INTC=alt_capex_facts(), AAPL=alt_capex_facts())
    assert spike.eval_p3(nobody).verdict == "NOT_HOLD"
    assert spike.eval_p3(spike.SecEvidence(attempted=True)).verdict == "INCONCLUSIVE"


def test_p3_stale_or_short_series_is_not_verified() -> None:
    old = [
        _entry(f"{y}-09-28", 1.0, start=f"{y - 1}-09-29", fy=y, filed=f"{y}-11-01")
        for y in (2017, 2018, 2019)
    ]
    result = spike.eval_p3(_evidence(AAPL=full_facts(old)))
    assert result.verdict == "NOT_HOLD" and "present but not verified" in "\n".join(result.lines)


def _map_evidence(mapping: dict[str, int], *, network: bool = True) -> Any:
    ev = spike.SecEvidence(attempted=True, map_from_network=network, ticker_map=mapping)
    ev.map_url = spike.SEC_TICKER_URL
    ev.etf_cik_source = "ticker map"
    ev.etf_facts_status = 404
    return ev


def test_p4_class_share_spelling_decides_between_holds_and_partial() -> None:
    base = {"AAPL": 320193, "SPY": 884394, "TQQQ": 1174610, "GOOG": 1, "GOOGL": 1}
    assert spike.eval_p4(_map_evidence({**base, "BRK.B": 1067983})).verdict == "HOLDS"
    partial = spike.eval_p4(_map_evidence({**base, "BRK-B": 1067983}))
    assert partial.verdict == "PARTIAL" and "'BRK-B'" in partial.detail
    assert any("tickers sharing this cik: 2" in line for line in partial.lines if "GOOG" in line)
    missing = spike.eval_p4(_map_evidence(base))
    assert missing.verdict == "NOT_HOLD"
    assert spike.eval_p4(_map_evidence({"BRK.B": 1})).verdict == "NOT_HOLD"


def test_p4_inconclusive_without_a_fetched_map() -> None:
    assert spike.eval_p4(_map_evidence({"AAPL": 1}, network=False)).verdict == "INCONCLUSIVE"
    assert spike.eval_p4(spike.SecEvidence()).verdict == "INCONCLUSIVE"


def test_p5_holds_when_limit_documented_and_no_throttling() -> None:
    ev = spike.SecEvidence(attempted=True, docs_limit=10, sec_statuses=[200, 200, 404])
    ev.docs_snippets = ["Current guidelines limit users to a maximum of 10 requests per second."]
    result = spike.eval_p5(ev)
    assert result.verdict == "HOLDS" and "10 requests/second" in result.detail
    assert "{'200': 2, '404': 1}" in result.lines[0]


def test_p5_not_hold_on_403_or_429_and_inconclusive_without_documented_limit() -> None:
    throttled = spike.SecEvidence(attempted=True, docs_limit=10, sec_statuses=[200, 429])
    assert spike.eval_p5(throttled).verdict == "NOT_HOLD"
    quiet = spike.SecEvidence(attempted=True, docs_limit=None, sec_statuses=[200])
    assert spike.eval_p5(quiet).verdict == "INCONCLUSIVE"
    assert spike.eval_p5(spike.SecEvidence()).verdict == "INCONCLUSIVE"


def _filing_list_evidence(**changes: Any) -> Any:
    ev = _evidence(AAPL=full_facts())
    ev.submissions["AAPL"] = _submissions(**changes.pop("submission", {}))
    ev.conditional_status = changes.get("conditional_status", 304)
    ev.conditional_note = "validators sent"
    return ev


def test_p6_holds_with_columns_and_304() -> None:
    result = spike.eval_p6(_filing_list_evidence())
    assert result.verdict == "HOLDS"
    assert any("companyfacts behind by: 0 day(s)" in line for line in result.lines)


def test_p6_partial_when_conditional_requests_are_ignored() -> None:
    result = spike.eval_p6(_filing_list_evidence(conditional_status=200))
    assert result.verdict == "PARTIAL" and "NOT honoured" in result.detail


def test_p6_not_hold_without_acceptance_timestamp_and_inconclusive_without_data() -> None:
    columns = ("accessionNumber", "filingDate", "form")
    result = spike.eval_p6(_filing_list_evidence(submission={"columns": columns}))
    assert result.verdict == "NOT_HOLD"
    assert spike.eval_p6(spike.SecEvidence(attempted=True)).verdict == "INCONCLUSIVE"


def test_p7_measures_sizes_and_is_inconclusive_without_responses() -> None:
    ev = spike.SecEvidence(attempted=True)
    ev.facts_fetch["AAPL"] = spike.FactsFetch(200, 4_200_000, 800_000, None)
    ev.facts_fetch["AMZN"] = spike.FactsFetch(200, 3_000_000, None, None)
    ev.facts_fetch["INTC"] = spike.FactsFetch(404, 0, None, None)
    result = spike.eval_p7(ev)
    assert result.verdict == "MEASURED"
    assert (
        "largest decoded 4.20 MB" in result.detail and "largest compressed 0.80 MB" in result.detail
    )
    assert any("AMZN: decoded 3.00 MB, on the wire (gzip) unknown" in line for line in result.lines)
    assert not any("INTC" in line for line in result.lines)
    assert spike.eval_p7(spike.SecEvidence()).verdict == "INCONCLUSIVE"


def test_p8_holds_when_company_and_etf_differ() -> None:
    ev = spike.SecEvidence(attempted=True)
    ev.submissions["AAPL"] = _submissions()
    ev.submissions["SPY"] = _submissions(sic="", entity_type="other", category="")
    assert spike.eval_p8(ev).verdict == "HOLDS"


def test_p8_partial_not_hold_and_inconclusive() -> None:
    same = spike.SecEvidence(attempted=True)
    same.submissions["AAPL"] = _submissions()
    same.submissions["SPY"] = _submissions()
    assert spike.eval_p8(same).verdict == "PARTIAL"
    bare = spike.SecEvidence(attempted=True)
    bare.submissions["AAPL"] = _submissions(sic="", entity_type="")
    assert spike.eval_p8(bare).verdict == "NOT_HOLD"
    no_etf = spike.SecEvidence(attempted=True)
    no_etf.submissions["AAPL"] = _submissions()
    assert spike.eval_p8(no_etf).verdict == "INCONCLUSIVE"
    assert spike.eval_p8(spike.SecEvidence()).verdict == "INCONCLUSIVE"


def test_p9_holds_partial_not_hold_and_inconclusive() -> None:
    ev = _evidence(AAPL=full_facts())
    ev.submissions["AAPL"] = _submissions()
    assert spike.eval_p9(ev).verdict == "HOLDS"
    ev.submissions["AAPL"] = _submissions(fiscal_year_end="1231")
    assert spike.eval_p9(ev).verdict == "PARTIAL"
    ev.submissions["AAPL"] = _submissions(fiscal_year_end="")
    assert spike.eval_p9(ev).verdict == "NOT_HOLD"
    lone = spike.SecEvidence(attempted=True)
    lone.submissions["AAPL"] = _submissions()
    assert spike.eval_p9(lone).verdict == "PARTIAL"
    assert spike.eval_p9(spike.SecEvidence()).verdict == "INCONCLUSIVE"


def test_p12_judges_holdings_when_given_and_otherwise_stays_inconclusive() -> None:
    ev = _evidence(AAPL=full_facts(), TSM=foreign_facts(), BABA=foreign_facts(), NVDA=full_facts())
    ev.holdings = ["NVDA", "BABA"]
    holds = spike.eval_p12(ev)
    assert holds.verdict == "HOLDS" and "['BABA']" in holds.detail
    assert any(
        "BABA: ifrs-full=yes; non-USD units=['TWD', 'TWD/shares']" in line for line in holds.lines
    )

    ev.holdings = ["NVDA"]
    ev.reports.pop("BABA")
    assert spike.eval_p12(ev).verdict == "NOT_HOLD"

    ev.holdings = []
    sample_only = spike.eval_p12(ev)
    assert (
        sample_only.verdict == "INCONCLUSIVE"
        and "TSM proves such filers exist" in sample_only.detail
    )
    assert spike.eval_p12(spike.SecEvidence(attempted=True)).verdict == "INCONCLUSIVE"


def test_foreign_currency_units_ignores_usd_and_non_currency_units() -> None:
    units = {"USD": 5, "USD/shares": 2, "shares": 3, "pure": 1, "TWD": 4, "EUR/shares": 1, "CNY": 1}
    assert spike.foreign_currency_units(units) == ["CNY", "EUR/shares", "TWD"]


def test_parse_holdings_filters_caps_and_deduplicates() -> None:
    accepted, ignored = spike.parse_holdings("nvda, tsla ;AAPL TSM $$$ nvda baba GOOG, MSFT")
    assert accepted == ["NVDA", "TSLA", "BABA"]
    assert ignored == ["AAPL", "TSM", "$$$", "nvda", "GOOG", "MSFT"]
    assert spike.parse_holdings("") == ([], [])


def test_lookup_ticker_tries_class_share_spellings() -> None:
    assert spike.ticker_variants("brk.b") == ["BRK.B", "BRK-B", "BRKB"]
    assert spike.lookup_ticker({"BRK-B": 7}, "BRK.B") == (7, "BRK-B")
    assert spike.lookup_ticker({"BRK.B": 7}, "BRK.B") == (7, "BRK.B")
    assert spike.lookup_ticker({}, "BRK.B") == (None, None)


def test_extract_doc_facts_reads_limit_and_user_agent_sentences() -> None:
    limit, snippets = spike.extract_doc_facts(FAIR_ACCESS_HTML)
    assert limit == 10
    assert any("10 requests per second" in s for s in snippets)
    assert any("Declare your User-Agent" in s for s in snippets)
    assert not any("Unrelated" in s or "p{}" in s for s in snippets)
    assert spike.extract_doc_facts("<p>nothing useful</p>") == (None, [])


def test_analyze_submissions_reads_metadata_columns_and_latest_periodic_filing() -> None:
    info = _submissions()
    assert (info.sic, info.entity_type, info.fiscal_year_end) == ("3571", "operating", "0928")
    assert all(info.recent_fields.values()) or info.recent_fields["reportDate"]
    assert info.filing_date_format_ok and info.acceptance_format_ok
    assert info.latest_periodic == {
        "form": "10-K",
        "filingDate": "2025-11-01",
        "acceptanceDateTime": "2025-11-01T06:01:36.000Z",
        "accessionNumber": "0000320193-25-000106",
    }
    assert not spike.analyze_submissions([], 200).ok
    bare = spike.analyze_submissions({"name": "x", "filings": {}}, 200)
    assert bare.ok and bare.recent_fields == {} and bare.latest_periodic is None
    odd = submissions_doc()
    odd["filings"]["recent"]["filingDate"] = ["01/11/2025", "2025-08-01", "2025-09-15"]
    assert spike.analyze_submissions(odd, 200).filing_date_format_ok is False


def test_keep_headers_keeps_validators_and_rate_limits_but_never_cookies_or_auth() -> None:
    kept = spike.keep_headers(
        [
            ("ETag", '"x"'),
            ("Last-Modified", "Sat"),
            ("X-RateLimit-Remaining", "9"),
            ("Set-Cookie", "session=SECRET"),
            ("Authorization", "Bearer SECRET"),
            ("Retry-After", "5"),
        ]
    )
    assert kept == {
        "etag": '"x"',
        "last-modified": "Sat",
        "x-ratelimit-remaining": "9",
        "retry-after": "5",
    }


def test_urllib_transport_records_headers_and_wire_size(monkeypatch: pytest.MonkeyPatch) -> None:
    packed = gzip.compress(b'{"ok": 1}')

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        response = _FakeResponse(packed, encoding="gzip")
        response.headers["ETag"] = '"abc"'
        response.headers["Set-Cookie"] = "SECRET"
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = spike.urllib_transport("https://example.test/x", {})
    assert result.wire_size == len(packed) and result.body == b'{"ok": 1}'
    assert result.headers == {"etag": '"abc"', "content-encoding": "gzip"}


def test_urllib_transport_surfaces_304_with_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        headers = Message()
        headers["ETag"] = '"abc"'
        raise urllib.error.HTTPError(
            request.full_url, 304, "Not Modified", headers, io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = spike.urllib_transport("https://example.test/x", {"If-None-Match": '"abc"'})
    assert result.status == 304 and result.body == b"" and result.headers["etag"] == '"abc"'


def test_full_run_judges_every_p_item_from_the_same_responses() -> None:
    net = FakeNet()
    _, out = run_main(net)
    assert "== 5. ADR-0038 P items" in out
    for pid in ("P-1", "P-2", "P-3", "P-4", "P-5", "P-6", "P-7", "P-8", "P-9", "P-12"):
        assert f"{pid}:" in out, pid
    for line in (
        "[PARTIAL] ADR-0038/P-1",
        "[HOLDS] ADR-0038/P-2",
        "[PARTIAL] ADR-0038/P-3",
        "[PARTIAL] ADR-0038/P-4 -- class share only found as 'BRK-B'",
        "[HOLDS] ADR-0038/P-5",
        "[HOLDS] ADR-0038/P-6 -- filing list has all columns and honours conditional",
        "[MEASURED] ADR-0038/P-7",
        "[HOLDS] ADR-0038/P-8",
        "[HOLDS] ADR-0038/P-9",
        "[INCONCLUSIVE] ADR-0038/P-12 -- TSM proves such filers exist",
    ):
        assert line in out, line
    assert "SPIKE_US_HOLDINGS is NOT set" in out
    # The conditional repeat really carried the validators the first answer offered.
    sub_calls = [(u, h) for u, h in net.calls if "/submissions/CIK0000320193" in u]
    assert len(sub_calls) == 2
    assert sub_calls[1][1]["If-None-Match"] == '"abc123"'
    assert "If-Modified-Since" in sub_calls[1][1]
    assert "If-None-Match" not in sub_calls[0][1]
    assert out.count("verdict counts:") == 1


def test_run_with_holdings_adds_one_request_each_and_judges_p12() -> None:
    env = {**FULL_ENV, "SPIKE_US_HOLDINGS": "nvda, baba, bad!!, tsla, msft, tsm"}
    net = FakeNet()
    _, out = run_main(net, env=env)
    assert len(net.calls) == 22 + 3
    assert "requests used: 25 / 30" in out
    assert "ignored ['bad!!', 'msft', 'tsm']" in out or "ignored ['bad!!', 'tsm', 'msft']" in out
    assert (
        "[HOLDS] ADR-0038/P-12 -- non-USD or IFRS filers among checked companies: ['BABA']" in out
    )
    assert "SPIKE_US_HOLDINGS is set" in out


def test_run_with_holdings_missing_from_ticker_map_reports_it() -> None:
    net = FakeNet()
    _, out = run_main(net, env={**FULL_ENV, "SPIKE_US_HOLDINGS": "ZZZZ"})
    assert "[MISSING] SEC/holding ZZZZ/companyfacts -- ticker not in ticker map" in out
    assert len(net.calls) == 22


def test_first_answer_without_validators_skips_the_conditional_request() -> None:
    bare = spike.HttpResult(200, json.dumps(submissions_doc()).encode("utf-8"))
    net = FakeNet({"https://data.sec.gov/submissions/CIK0000320193": bare})
    _, out = run_main(net)
    assert len(net.calls) == 21
    assert "conditional request skipped" in out
    assert "[PARTIAL] ADR-0038/P-6" in out and "status None" in out


def test_server_ignoring_validators_marks_p6_partial() -> None:
    seen: list[dict[str, str]] = []
    ok = FakeNet()

    def transport(url: str, headers: Mapping[str, str]) -> Any:
        if "/submissions/CIK0000320193" in url:
            seen.append(dict(headers))
            return spike.HttpResult(
                200, json.dumps(submissions_doc()).encode("utf-8"), None, {"etag": '"e"'}
            )
        return ok(url, headers)

    _, out = run_main(transport)
    assert len(seen) == 2 and seen[1]["If-None-Match"] == '"e"'
    assert "[MISSING] SEC/conditional-request" in out
    assert "conditional requests NOT honoured (status 200)" in out


def test_throttling_by_sec_turns_p5_into_not_hold() -> None:
    net = FakeNet(
        {"https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193": spike.HttpResult(429, b"")}
    )
    _, out = run_main(net)
    assert "[NOT_HOLD] ADR-0038/P-5" in out


def test_without_sec_the_p_items_are_skipped_not_guessed() -> None:
    _, out = run_main(FakeNet(), env={})
    assert "[SKIPPED] ADR-0038/P-items -- SEC section skipped" in out
    assert "ADR-0038/P-1" not in out.split("== Summary ==")[1]


# ------------------------------------------------------------------ CLI entry point


def test_cli_help_runs_through_main_guard_in_a_new_session() -> None:
    """``--help`` exits before any request, so this launch never touches the network."""
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env={"PATH": "", "PYTHONIOENCODING": "utf-8"},
    )
    try:
        stdout, stderr = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        proc.kill()
        proc.communicate()
        raise
    assert proc.returncode == 0, stderr
    assert "usage:" in stdout and "Read-only financial data source spike" in stdout


def test_script_has_main_guard_that_exits_with_main_status() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    guards = [
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    ]
    assert len(guards) == 1
    assert "SystemExit" in ast.unparse(guards[0])


# ------------------------------------------------------------------ source code guards

SOURCE = SCRIPT_PATH.read_text(encoding="utf-8")
SOURCE_TREE = ast.parse(SOURCE)

#: Attribute / call names that write, create, move or delete files.
FILE_WRITE_NAMES = {
    "write",
    "writelines",
    "write_text",
    "write_bytes",
    "mkdir",
    "makedirs",
    "touch",
    "unlink",
    "remove",
    "rmdir",
    "rmtree",
    "rename",
    "copy",
    "copyfile",
    "copy2",
    "move",
    "symlink",
    "truncate",
    "NamedTemporaryFile",
    "mkstemp",
    "mkdtemp",
    "TemporaryDirectory",
    "FileHandler",
    "dump",
}


def _imported_roots() -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(SOURCE_TREE):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            assert node.module is not None
            roots.add(node.module.split(".")[0])
    return roots


def test_source_has_no_database_access() -> None:
    assert "sqlite3" not in SOURCE.lower()
    assert not re.search(r"\b(psycopg|sqlalchemy|duckdb|aiosqlite)\b", SOURCE, flags=re.IGNORECASE)
    assert "dbm" not in _imported_roots() and "shelve" not in _imported_roots()


def test_source_never_imports_app_and_uses_only_the_standard_library() -> None:
    roots = _imported_roots()
    assert "app" not in roots
    assert roots <= set(sys.stdlib_module_names) | {"__future__"}


def test_source_writes_no_files() -> None:
    for node in ast.walk(SOURCE_TREE):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            assert name != "open", "file open"
            assert name not in FILE_WRITE_NAMES, name
    imported = _imported_roots()
    assert not imported & {"shutil", "tempfile", "logging", "csv", "pickle", "zipfile", "tarfile"}


def test_source_only_reads_its_own_file_and_nothing_else_from_disk() -> None:
    reads = [
        ast.unparse(node)
        for node in ast.walk(SOURCE_TREE)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"read_bytes", "read_text"}
    ]
    assert reads == ["Path(__file__).read_bytes()"]


def test_source_sends_get_requests_only() -> None:
    methods = [
        kw.value.value
        for node in ast.walk(SOURCE_TREE)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "method" and isinstance(kw.value, ast.Constant)
    ]
    assert methods == ["GET"]
    for node in ast.walk(SOURCE_TREE):
        if isinstance(node, ast.Call):
            assert not any(kw.arg == "data" for kw in node.keywords)
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", SOURCE)


def test_source_holds_no_credentials_or_contact_details() -> None:
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", SOURCE), "email-like text in source"
    assert not re.search(r"(?i)(apikey|api_key|token)\s*=\s*[\"'][^\"']{6,}[\"']", SOURCE)
    # Credentials come only from the environment, by variable name.
    for name in ("SEC_USER_AGENT", "FINMIND_API_TOKEN", "ALPHA_VANTAGE_API_KEY"):
        assert f'"{name}"' in SOURCE
