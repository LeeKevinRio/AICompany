"""``GET /api/sectors/momentum`` (ADR-0012 D-10; T-2, T-14, T-20, T-23, T-24, T-26, T-27, T-28).

Two layers:

* end to end through the real app, on a real market DB (written through the
  store's own API) and a real main DB: zero HTTP and the SQL budget (T-2),
  the OpenAPI field-name scan and the ``DataMeta`` mapping;
* :func:`app.api.sectors.build_sector_momentum` on hand-built boards, for the
  state matrix: gate-controlled fields (C-23, C-41), the five whole-card
  reasons and their verbatim sentences (C-42..C-45), thresholds straight off
  the definition (C-33), the ex-date tag (C-38), ``held`` (C-34).
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import sectors as api
from app.api import sectors_wording as wording
from app.api.common import DataMeta
from app.api.deps import get_index_resolver, get_market_resolver
from app.main import app
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import CoverageRules, SectorMomentumDefinition
from app.sectors.gate import UNVERIFIED_RUNTIME, SectorGateRuntime
from app.sectors.models import ApprovalRecord
from app.sectors.store import (
    CardRead,
    StoredBoard,
)
from app.services.market import trading_days_behind_market
from tests.published_helpers import published
from tests.sector_board_helpers import (
    card_client,
    excluded_sector,
    live_card,
    make_board,
    ok_map,
    ranked_sector,
    stats_record,
    verified_runtime,
    weekdays_between,
)

AS_OF = date(2029, 3, 12)
D0 = date(2026, 1, 5)
NOW = datetime(2029, 3, 12, 12, 0, tzinfo=UTC)  # 20:00 Taipei on AS_OF
CALENDAR = weekdays_between(D0, AS_OF)
A_CLASS = frozenset(
    {
        "beat_count_net",
        "beat_count_gross",
        "sample_count",
        "effective_sample_count",
        "base_rate_net",
        "base_rate_gross",
        "ci_low_net",
        "ci_high_net",
        "bootstrap_low_net",
        "bootstrap_high_net",
        "delta_real",
        "delta_shuffle",
        "m_at_evaluation",
    }
)
B_AND_C_CLASS = frozenset(
    {
        "gate_status",
        "not_evaluated_reason",
        "not_evaluated_reasons",
        "pit_gaps",
        "accumulation",
        "fee_verified_on",
        "coverage",
        "min_constituents",
        "sector_coverage_threshold",
        "overall_coverage_threshold",
        "computable_ratio",
        "computable_ratio_min",
        "computable_ratio_pct_display",
        "completeness_pct_display",
        "market_expected_count",
        "market_missing_count",
        "market_ex_date_excluded_count",
        "market_corporate_action_excluded_count",
        "market_ex_date_excluded_ratio",
        "ex_date_tag_ratio_min",
        "ex_date_tag",
        "excluded_reason_counts",
        "insufficient_reason",
        "data_source",
        "data",
        "sectors",
        "excluded_sectors",
    }
)
FORBIDDEN_FIELD_WORDS = (
    "volume",
    "hit_rate",
    "win_rate",
    "score",
    "rating",
    "confidence",
    "action",
)


def _stats(**overrides: object) -> Any:
    return stats_record("stats-1", **overrides)


def _approval(kind: str = "first_transition_risk", run_id: str = "stats-1") -> ApprovalRecord:
    return ApprovalRecord(
        kind=kind,  # type: ignore[arg-type]
        run_id=run_id,
        method_version=V1.method_version,
        operator="ceo" if kind == "first_transition_risk" else "dev-lead",
        reviewer="risk-compliance-officer",
        review_doc_path="work/reviews/x.md",
        review_doc_blob_hash="0" * 40,
        approved_at=NOW,
    )


def _board(**overrides: object) -> StoredBoard:
    options: dict[str, object] = {
        "data_as_of": AS_OF,
        "ranked": [ranked_sector(1, "24", sector_return=0.03), ranked_sector(2, "28")],
        "excluded": [excluded_sector("20", "unranked_category")],
    }
    options.update(overrides)
    return make_board(**options)  # type: ignore[arg-type]


def _build(
    board: StoredBoard | None,
    *,
    stats: tuple[Any, ...] = (),
    approvals: tuple[ApprovalRecord, ...] = (),
    d0: date | None = D0,
    runtime: SectorGateRuntime | None = None,
    held: frozenset[str] | None = frozenset(),
    definition: SectorMomentumDefinition = V1,
    rejected: str | None = None,
    sessions: list[date] | None = None,
) -> dict[str, Any]:
    payload = api.build_sector_momentum(
        market="TW",
        read=CardRead(
            board=board,
            stats_history=stats,
            approvals=approvals,
            accumulation_start=d0,
            stats_rejected=rejected,
        ),
        ok_sessions=ok_map(sessions if sessions is not None else CALENDAR),
        runtime=runtime if runtime is not None else verified_runtime(),
        held=held,
        now=NOW,
        definition=definition,
    )
    return payload.model_dump(mode="json")


def _keys(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def _passed() -> dict[str, Any]:
    return _build(_board(), stats=(_stats(),), approvals=(_approval(),))


# ---------------------------------------------------------------------------
# End to end: zero HTTP and the SQL budget (T-2)
# ---------------------------------------------------------------------------


class _Exploding:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the sector card touched a resolver ({name})")

    def get(self, *args: object) -> object:
        raise AssertionError("the sector card touched a resolver")


def _count_statements(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    statements: list[str] = []
    real_connect = sqlite3.connect

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    return statements


@pytest.mark.parametrize("sector_count", [10, 40])
def test_zero_http_and_at_most_seven_statements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sector_count: int
) -> None:
    live = live_card(tmp_path, sector_count, now=NOW)

    def no_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("the sector card made an HTTP call")

    # The network transports (TestClient talks to the app through its own transport).
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
    app.dependency_overrides[get_market_resolver] = lambda: _Exploding()
    app.dependency_overrides[get_index_resolver] = lambda: _Exploding()
    try:
        with card_client(
            main_db=live.main_db,
            market_db=live.market_db,
            positions=live.positions,
            runtime=verified_runtime(),
            now=NOW,
        ) as client:
            statements = _count_statements(monkeypatch)
            response = client.get("/api/sectors/momentum", params={"market": "TW"})
    finally:
        app.dependency_overrides.pop(get_market_resolver, None)
        app.dependency_overrides.pop(get_index_resolver, None)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert len(body["sectors"]) + len(body["excluded_sectors"]) >= sector_count
    assert len(statements) <= 7, statements
    assert not any(statement.upper().startswith("PRAGMA") for statement in statements)
    # The same statement count for 10 and 40 sectors (the budget does not scale).
    assert len(statements) == 7


def test_only_tw_is_served(tmp_path: Path) -> None:
    live = live_card(tmp_path, 10, now=NOW)
    with card_client(
        main_db=live.main_db,
        market_db=live.market_db,
        positions=live.positions,
        runtime=verified_runtime(),
        now=NOW,
    ) as client:
        assert client.get("/api/sectors/momentum", params={"market": "US"}).status_code == 422
        body = client.get("/api/sectors/momentum").json()
    held = [item["held"] for row in body["sectors"] for item in row["constituents"]]
    assert held and all(isinstance(flag, bool) for flag in held)  # the lookup succeeded


def test_the_openapi_schema_has_no_forbidden_field_names() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    components = schema["components"]["schemas"]
    names = {
        name
        for model, body in components.items()
        if model.startswith(("SectorMomentumResponse", "SectorItem", "Coverage", "Constituent"))
        or model
        in {"Accumulation", "HistoricalStat", "GateCheck", "ExcludedSector", "ExcludedReasonCounts"}
        for name in body.get("properties", {})
    }
    assert {"gate_status", "corporate_action_excluded_count", "turnover_value_ratio_5_20"} <= names
    offenders = sorted(
        name
        for name in names
        if any(word in name.replace("corporate_action", "") for word in FORBIDDEN_FIELD_WORDS)
    )
    assert offenders == []


# ---------------------------------------------------------------------------
# Gate-controlled fields (C-23, C-28, C-41; T-14, T-26)
# ---------------------------------------------------------------------------


def test_not_evaluated_carries_no_historical_number_but_every_descriptive_field() -> None:
    body = _build(_board(), runtime=dataclasses.replace(verified_runtime(), fee_verified_on=None))
    assert body["gate_status"] == "not_evaluated"
    assert "fee_unverified" in body["not_evaluated_reasons"]
    assert body["historical_stat"] is None and body["gate_checks"] is None
    assert not A_CLASS & set(_keys(body))
    assert B_AND_C_CLASS <= set(body)
    assert body["sectors"] and body["coverage"] is not None
    assert body["accumulation"]["accumulation_start"] == D0.isoformat()


def test_pending_review_hides_the_candidate() -> None:
    body = _build(_board(), stats=(_stats(),))
    assert body["gate_status"] == "not_evaluated"
    assert body["not_evaluated_reason"] == "pending_review"
    assert body["historical_stat"] is None and body["gate_checks"] is None
    assert not A_CLASS & set(_keys(body))


def test_passed_publishes_the_statistics_once_with_both_deltas() -> None:
    body = _passed()
    assert body["gate_status"] == "passed"
    assert body["not_evaluated_reason"] is None and body["pit_gaps"] == []
    stat = body["historical_stat"]
    assert stat["delta_real"] == 20.75 and stat["delta_shuffle"] == 3.5
    assert [check["gate"] for check in body["gate_checks"]] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    keys = list(_keys(body))
    assert keys.count("historical_stat") == 1 and keys.count("data_as_of") == 1
    assert "rank" not in body and all("rank" in row for row in body["sectors"])
    assert all("rank" not in item for row in body["sectors"] for item in row["constituents"])


def test_the_label_shuffle_never_moves_the_gate() -> None:
    moved = _build(_board(), stats=(_stats(delta_shuffle=19.0),), approvals=(_approval(),))
    assert moved["gate_status"] == _passed()["gate_status"] == "passed"
    assert moved["historical_stat"]["delta_shuffle"] == 19.0


def test_demo_data_is_always_demo_data_first() -> None:
    body = _build(_board(data_source="demo_synthetic"), d0=None)
    assert body["gate_status"] == "not_evaluated"
    assert body["not_evaluated_reason"] == "demo_data"
    assert "pit_history_missing" in body["not_evaluated_reasons"]
    assert body["data_source"] == "demo_synthetic"


def test_a_deployed_commit_mismatch_is_ne7_at_read_time() -> None:
    body = _build(
        _board(), stats=(_stats(),), approvals=(_approval(),), runtime=verified_runtime("x")
    )
    assert body["not_evaluated_reason"] == "lookahead_tests_failed"
    assert (
        _build(_board(), stats=(_stats(),), runtime=verified_runtime(None))["not_evaluated_reason"]
        == "lookahead_tests_failed"
    )


def test_statistics_refused_on_read_fail_closed() -> None:
    body = _build(_board(), rejected="stats run stats-1: source runs ['9'] are not in ...")
    assert body["gate_status"] == "not_evaluated"
    assert "data_quality" in body["not_evaluated_reasons"]
    assert body["historical_stat"] is None


def test_before_d0_every_pit_gap_is_listed() -> None:
    body = _build(
        _board(), d0=None, runtime=dataclasses.replace(verified_runtime(), de5_verified_on=None)
    )
    assert body["not_evaluated_reason"] == "pit_history_missing"
    assert body["pit_gaps"] == [
        "pit_universe",
        "pit_classification",
        "pit_ex_dividend",
        "de5_unverified",
    ]
    assert body["accumulation"] == {
        "accumulated_samples": 0,
        "accumulation_start": None,
        "required_samples": 150,
    }


def test_ne4_counts_trading_days_from_the_recompute() -> None:
    fresh = _build(
        _board(), stats=(_stats(recompute_session=CALENDAR[-21]),), approvals=(_approval(),)
    )
    stale = _build(
        _board(), stats=(_stats(recompute_session=CALENDAR[-22]),), approvals=(_approval(),)
    )
    assert fresh["gate_status"] == "passed"
    assert stale["not_evaluated_reason"] == "stale_recompute"


# ---------------------------------------------------------------------------
# Descriptive fields (C-33, C-34, C-38, C-37; T-20, T-23, T-24)
# ---------------------------------------------------------------------------


def test_thresholds_are_the_definitions_own_values() -> None:
    body = _build(_board())
    rules = V1.coverage
    assert (
        body["min_constituents"],
        body["sector_coverage_threshold"],
        body["overall_coverage_threshold"],
        body["computable_ratio_min"],
        body["ex_date_tag_ratio_min"],
    ) == (
        rules.min_constituents,
        rules.sector_coverage_threshold,
        rules.overall_coverage_threshold,
        rules.computable_ratio_min,
        rules.ex_date_tag_ratio_min,
    )
    assert body["headline_count"] == 3 and body["market_scope"] == "twse_only"
    assert body["benchmark"] == "equal_weight_market"


def test_held_flags_and_their_unknown_state() -> None:
    known = _build(_board(), held=frozenset({"2400"}))
    flags = {item["symbol"]: item["held"] for item in known["sectors"][0]["constituents"]}
    assert flags == {"2400": True, "2401": False, "2407": False}
    unknown = _build(_board(), held=None)
    assert {item["held"] for row in unknown["sectors"] for item in row["constituents"]} == {None}


def test_positions_failure_means_unknown_not_unheld() -> None:
    class Broken:
        def list_all(self) -> list[object]:
            raise sqlite3.OperationalError("locked")

    assert api._held_symbols(Broken()) is None  # type: ignore[arg-type]


def test_card_counts_and_floored_displays() -> None:
    body = _build(_board(expected=10000, missing=100, ex_date=1900, corporate_action=1))
    assert body["status"] == "insufficient_data"
    assert body["insufficient_reason"] == "computable_ratio_low"
    assert body["computable_ratio_pct_display"] == 79.9
    e, a, b, c = (
        body["market_expected_count"],
        body["market_missing_count"],
        body["market_ex_date_excluded_count"],
        body["market_corporate_action_excluded_count"],
    )
    assert e - a - b - c == body["coverage"]["calculation_count"] == 8000 - 1
    at_floor = _build(_board(expected=10000, missing=100, ex_date=1900, corporate_action=0))
    assert at_floor["status"] == "ok" and at_floor["computable_ratio_pct_display"] == 80.0


@pytest.mark.parametrize(
    ("ex_date", "excluded", "tag"),
    [
        (50, [], True),  # exactly 5%
        (49, [], False),
        (49, [excluded_sector("15", "ex_dividend_exclusion", ex_date=2)], True),
    ],
)
def test_the_ex_date_tag_is_computed_by_the_backend(
    ex_date: int, excluded: list[object], tag: bool
) -> None:
    body = _build(
        _board(
            expected=1000,
            missing=0,
            ex_date=ex_date,
            excluded=[excluded_sector("20", "unranked_category"), *excluded],
        )
    )
    assert body["status"] == "ok"
    assert body["ex_date_tag"] is tag


# ---------------------------------------------------------------------------
# Whole-card insufficiency (C-42..C-45; T-27, T-28)
# ---------------------------------------------------------------------------


def _insufficient_cases() -> dict[str, dict[str, Any]]:
    return {
        "as_of_unknown": _build(None),
        "ex_dividend_feed_gap": _build(_board(feed_covered=False)),
        "overall_completeness_low": _build(_board(expected=1000, missing=21, ex_date=0)),
        "computable_ratio_low": _build(_board(expected=1000, missing=10, ex_date=200)),
        "no_sector_computable": _build(
            _board(
                ranked=[],
                excluded=[
                    excluded_sector("01", "too_few_members", expected=3),
                    excluded_sector("02", "low_coverage", missing=2),
                    excluded_sector("03", "low_coverage", missing=3),
                    excluded_sector("15", "ex_dividend_exclusion", ex_date=2),
                    excluded_sector("20", "unranked_category"),
                ],
            )
        ),
    }


def test_each_reason_alone_replaces_the_whole_card() -> None:
    for code, body in _insufficient_cases().items():
        assert body["status"] == "insufficient_data", code
        assert body["insufficient_reason"] == code
        assert body["reason"], code  # IP-1: never null
        assert body["reason"] != "資料不足，無法計算。"
        assert body["sectors"] == [] and body["excluded_sectors"] == []  # IP-5
        assert body["historical_stat"] is None and body["gate_checks"] is None
        assert body["data_source"] and body["data"]  # IP-6
        assert len(body["disclosures"]) == 1  # only that reason's detail sentence
        main, detail = wording.INSUFFICIENT_SENTENCES[code]
        if "{" not in main:
            assert body["reason"] == wording.with_lookback(main, 5)
        if "{" not in detail:
            assert body["disclosures"] == [wording.with_lookback(detail, 5)]


def test_the_first_reason_in_the_fixed_order_wins() -> None:
    both = _build(_board(feed_covered=False, expected=1000, missing=10, ex_date=200))
    assert both["insufficient_reason"] == "ex_dividend_feed_gap"
    later = _build(_board(expected=1000, missing=30, ex_date=200))
    assert later["insufficient_reason"] == "overall_completeness_low"


def test_the_filled_sentences_bind_their_own_numbers() -> None:
    cases = _insufficient_cases()
    completeness = cases["overall_completeness_low"]
    assert completeness["reason"] == (
        "全市場資料完整率 97.9%，低於 98%（1000 檔中缺漏 21 檔），本次不呈現族群動能排行。"
    )
    computable = cases["computable_ratio_low"]
    assert computable["reason"] == (
        "近 5 日遇除權息或減資等事件而暫不計入的個股較多，全市場可計算比例 79.0%，"
        "低於 80%，本次不呈現族群動能排行。"
    )
    assert computable["disclosures"] == [
        "可計算比例＝全市場應納入計算的上市普通股中，近 5 日未因資料缺漏、除權息或減資等公司行動"
        "而排除的比例。本次應納入 1000 檔，排除資料缺漏 10 檔、除權息 200 檔、公司行動 0 檔，"
        "可計算比例 79.0%，低於 80%。排除過多時，等權全市場已不足以代表全市場，"
        "因此本次不呈現族群動能排行。"
    ]
    assert completeness["disclosures"] == [
        "全市場應有資料 1000 檔，其中 21 檔在計算近 5 日漲跌幅所需的交易日中，"
        "至少一天沒有日線資料（原因未能判定；未取得暫停交易名單時，暫停交易的個股也計入缺漏），"
        "資料完整率 97.9%，低於 98%。缺漏過多時，無法確認缺漏是否集中在特定族群，"
        "因此本卡不呈現族群動能排行。"
    ]
    none_ranked = cases["no_sector_computable"]
    assert none_ranked["excluded_reason_counts"] == {
        "too_few_members": 1,
        "low_coverage": 2,
        "ex_dividend_exclusion": 1,
    }
    assert none_ranked["disclosures"] == [
        "族群須有至少 5 檔可計算成分股，且覆蓋率達 90%，才列入排行；本次所有族群皆未達標準"
        "（成分股不足 1 個、資料覆蓋率不足 2 個、除權息或減資等事件排除 1 個），"
        "因此不呈現族群動能排行。"
    ]
    for code, body in cases.items():
        if code != "no_sector_computable":
            assert body["excluded_reason_counts"] is None


def test_same_named_placeholders_never_share_a_threshold() -> None:
    """C-44 / T-28: ③ never prints ④'s threshold and vice versa."""
    strict = SectorMomentumDefinition(
        method_version=V1.method_version,
        lookback_days=5,
        holding_days=5,
        coverage=CoverageRules(overall_coverage_threshold=0.99, computable_ratio_min=0.85),
    )
    with published(strict):  # a stricter definition is served only once published (C-47)
        third = _build(_board(expected=1000, missing=15, ex_date=0), definition=strict)
        fourth = _build(_board(expected=1000, missing=5, ex_date=200), definition=strict)
    assert third["insufficient_reason"] == "overall_completeness_low"
    assert "低於 99%" in third["reason"] and "85" not in third["reason"]
    assert fourth["insufficient_reason"] == "computable_ratio_low"
    assert "低於 85%" in fourth["reason"] and "99" not in fourth["reason"]
    # {a} and {e} are the same field in ③ and ④.
    assert third["market_expected_count"] == fourth["market_expected_count"] == 1000


def test_the_card_never_uses_the_stock_page_as_of_constant() -> None:
    import inspect

    for module in (api, wording):
        assert "AS_OF_DATE_UNKNOWN_FULL_STATEMENT" not in inspect.getsource(module)
    body = _insufficient_cases()["as_of_unknown"]
    assert body["reason"] == wording.AS_OF_UNKNOWN_MAIN
    assert body["data_as_of"] is None and body["data"]["status"] == "unavailable"


def _assert_as_of_unknown(body: dict[str, Any]) -> None:
    assert body["status"] == "insufficient_data"
    assert body["insufficient_reason"] == "as_of_unknown"
    assert body["reason"] is not None and body["reason"] == wording.AS_OF_UNKNOWN_MAIN
    assert body["disclosures"] == [wording.AS_OF_UNKNOWN_DETAIL]
    assert body["excluded_reason_counts"] is None
    assert body["data_as_of"] is None and body["data"]["status"] == "unavailable"


def test_no_board_is_as_of_unknown_with_a_reason() -> None:
    """Risk item 3, condition 2: board None -> ① with a non-null reason."""
    _assert_as_of_unknown(_build(None))


@pytest.mark.parametrize(
    "excluded",
    [
        [],
        [excluded_sector("01", "too_few_members", expected=0)],
        [
            excluded_sector("01", "too_few_members", expected=0),
            excluded_sector("20", "unranked_category"),
        ],
    ],
)
def test_an_empty_expected_market_is_as_of_unknown_never_no_sector_computable(
    excluded: list[object],
) -> None:
    """R-5: |E_M| = 0 is no usable board -> ①, never ⑤ (「成分股不足 0 個」)."""
    body = _build(
        _board(expected=0, missing=0, ex_date=0, corporate_action=0, ranked=[], excluded=excluded),
        stats=(_stats(),),
        approvals=(_approval(),),
    )
    _assert_as_of_unknown(body)
    assert body["insufficient_reason"] != "no_sector_computable"
    assert body["sectors"] == [] and body["excluded_sectors"] == []
    assert body["market_expected_count"] is None and body["coverage"] is None
    assert not any("成分股不足" in text for text in [body["reason"], *body["disclosures"]])
    assert body["historical_stat"] is None and body["gate_checks"] is None


def test_an_ignored_empty_demo_board_keeps_its_demo_source() -> None:
    """R-5 x IP-6: the ignored board's source still drives the demo warning."""
    body = _build(
        _board(
            data_source="demo_synthetic",
            expected=0,
            missing=0,
            ex_date=0,
            corporate_action=0,
            ranked=[],
            excluded=[],
        )
    )
    assert body["data_source"] == "demo_synthetic"
    assert body["insufficient_reason"] == "as_of_unknown"
    assert body["reason"] == wording.AS_OF_UNKNOWN_MAIN
    assert body["not_evaluated_reason"] == "demo_data"  # the gate saw the same source
    # Deliberately apart: the top-level source keeps the demo warning, while
    # ``data`` describes the board actually used -- none (DataMeta unchanged).
    assert body["status"] == "insufficient_data"
    assert body["data"]["source"] == "none" and body["data"]["status"] == "unavailable"


def test_a_one_stock_market_is_still_read() -> None:
    """The R-5 cut is exactly |E_M| = 0: one expected stock is a real board.

    Its one sector is excluded as ``too_few_members``; the §10 counts n1 + n2 +
    n3 add up to the rankable sectors (``unranked_category`` is not one).
    """
    excluded = [
        excluded_sector("28", "too_few_members", expected=1),
        excluded_sector("20", "unranked_category", expected=0),
    ]
    body = _build(_board(expected=1, missing=0, ex_date=0, ranked=[], excluded=excluded))
    assert body["insufficient_reason"] == "no_sector_computable"
    assert body["data_as_of"] == AS_OF.isoformat()
    counts = body["excluded_reason_counts"]
    assert counts == {"too_few_members": 1, "low_coverage": 0, "ex_dividend_exclusion": 0}
    rankable = [row for row in excluded if row.reason_code != "unranked_category"]
    assert sum(counts.values()) == len(rankable) == 1


def test_standing_disclosures_when_the_card_is_ok() -> None:
    body = _build(_board(ex_date=12, corporate_action=3, taiex=0.0123))
    assert body["reason"] is None
    assert body["disclosures"] == [
        wording.HISTORICAL_DESCRIPTION_ONLY,  # risk suggestion: first (派工單 §13)
        wording.END_OF_DAY_DATA,
        wording.TWSE_ONLY,
        wording.EQUAL_WEIGHT_BENCHMARK,
        wording.TURNOVER_RATIO_DECODE,
        wording.LISTING_ORDER,
        "本次全市場應納入計算的上市普通股共 1000 檔；其中近 5 日因資料缺漏排除 5 檔、"
        "因除權息排除 12 檔、因單日價格變動超過漲跌幅限制（例如減資後恢復交易）排除 3 檔，"
        "這些個股皆未納入族群報酬與等權全市場的計算。",
        "近 5 日內遇到除權息的成分股，不納入本次族群報酬計算（本次共 12 檔）；"
        "因此本排行的數字可能與個股頁以未還原收盤價呈現的走勢不同。",
        wording.TAIEX_REFERENCE,
    ]
    bare = _build(_board(ex_date=0, taiex=None))
    assert wording.TAIEX_REFERENCE not in bare["disclosures"]
    assert not any("本次共" in sentence for sentence in bare["disclosures"])


def _market_exclusion_sentence(body: dict[str, Any]) -> str:
    prefix = wording.MARKET_EXCLUSION_COUNTS.split("{", 1)[0]
    found = [sentence for sentence in body["disclosures"] if sentence.startswith(prefix)]
    assert len(found) == 1, body["disclosures"]
    return found[0]


def _numbers(sentence: str) -> list[int]:
    return [int(number) for number in re.findall(r"\d+", sentence)]


@pytest.mark.parametrize(
    ("missing", "ex_date", "corporate_action"), [(5, 12, 3), (0, 0, 0), (19, 0, 7)]
)
def test_the_market_exclusion_counts_are_always_disclosed_when_ok(
    missing: int, ex_date: int, corporate_action: int
) -> None:
    """R-2: e/a/b/c bound to the response fields; e - a - b - c = |C_M|; 0 is printed."""
    body = _build(_board(missing=missing, ex_date=ex_date, corporate_action=corporate_action))
    assert body["status"] == "ok"
    sentence = _market_exclusion_sentence(body)
    e, a, b, c = (
        body["market_expected_count"],
        body["market_missing_count"],
        body["market_ex_date_excluded_count"],
        body["market_corporate_action_excluded_count"],
    )
    assert sentence == wording.fill(
        wording.MARKET_EXCLUSION_COUNTS, {"e": e, "a": a, "b": b, "c": c}, lookback_days=5
    )
    # 「近 5 日」 is the lookback, then e, a, b, c in that order.
    assert _numbers(sentence) == [e, 5, a, b, c]
    assert (a, b, c) == (missing, ex_date, corporate_action)
    assert e - a - b - c == body["coverage"]["calculation_count"]  # |C_M(t,L)|
    ex_date_sentences = [s for s in body["disclosures"] if "本次共" in s]
    if b:
        # §6.2 (a)'s {m} is R-2's {b}, in the same response.
        assert ex_date_sentences == [
            wording.fill(wording.EX_DATE_EXCLUSION, {"m": b}, lookback_days=5)
        ]
    else:
        assert ex_date_sentences == []  # §6.2 (a) stays conditional (m > 0)


def test_the_market_exclusion_counts_follow_the_lookback() -> None:
    body = _build(_board(lookback_days=20))
    assert "其中近 20 日因資料缺漏排除" in _market_exclusion_sentence(body)


def test_insufficient_cards_never_carry_the_market_exclusion_counts() -> None:
    prefix = wording.MARKET_EXCLUSION_COUNTS.split("{", 1)[0]
    for code, body in _insufficient_cases().items():
        assert not any(sentence.startswith(prefix) for sentence in body["disclosures"]), code


# ---------------------------------------------------------------------------
# DataMeta (D-10 mapping)
# ---------------------------------------------------------------------------


def test_data_meta_follows_the_d10_mapping() -> None:
    body = _build(_board())
    meta = DataMeta.model_validate(body["data"])
    assert meta.status == "cached_stale" and meta.source == "twse_snapshot"
    assert meta.last_bar_date == AS_OF.isoformat() == body["data_as_of"]
    assert meta.bar_count == 6  # t-L .. t
    assert meta.trading_days_behind == 0
    assert meta.staleness_minutes == 120  # recorded 10:00 UTC, read 12:00 UTC
    assert meta.is_within_ttl is True
    assert meta.reason is None


def test_trading_days_behind_is_the_c4_rule_on_the_market_calendar() -> None:
    sessions = frozenset(CALENDAR)

    class Source:
        def market_trading_days(self, market: str, start: date, end: date) -> list[date]:
            return [day for day in sessions if start <= day <= end]

    for last, today in ((CALENDAR[-4], AS_OF), (AS_OF, AS_OF + timedelta(days=3))):
        assert api.trading_days_behind(sessions, last, today) == trading_days_behind_market(
            Source(),
            market="TW",
            last_bar_date=last,
            today=today,  # type: ignore[arg-type]
        )
    assert api.trading_days_behind(frozenset(), AS_OF, AS_OF) is None


def test_no_board_is_unavailable() -> None:
    meta = _build(None)["data"]
    assert meta["status"] == "unavailable" and meta["source"] == "none"
    assert meta["bar_count"] == 0 and meta["trading_days_behind"] is None


# ---------------------------------------------------------------------------
# Gate runtime wiring (ADR-0012 D-1, C-5: installed by the composition root)
# ---------------------------------------------------------------------------


def _request_for(target: object) -> Any:
    return SimpleNamespace(app=target)


def test_the_cards_position_store_is_the_apps_position_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card's own provider (C-5 keeps ``app.api.deps`` out) opens the same database."""
    from app.api import deps

    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(tmp_path / "stock-desk.db"))
    caches = (api._default_positions, deps._default_store)
    for cache in caches:
        cache.cache_clear()
    try:
        card_store = api.get_sector_position_store()
        app_store = deps.get_position_store()
        assert card_store.db_path == app_store.db_path == tmp_path / "stock-desk.db"
    finally:
        for cache in caches:
            cache.cache_clear()


def test_the_composition_root_installs_the_services_runtime() -> None:
    from app.services.sector_runtime import process_gate_runtime

    assert getattr(app.state, api.GATE_RUNTIME_STATE) is process_gate_runtime


def test_an_installed_loader_is_what_the_card_reads() -> None:
    target = FastAPI()
    api.install_gate_runtime(target, verified_runtime)
    assert api.get_sector_gate_runtime(_request_for(target)) == verified_runtime()


def test_without_an_installed_runtime_the_card_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bare = SimpleNamespace(state=SimpleNamespace())
    with caplog.at_level("ERROR"):
        runtime = api.get_sector_gate_runtime(_request_for(bare))
    assert runtime == UNVERIFIED_RUNTIME
    assert "no gate runtime installed" in caplog.text
    body = _build(_board(), stats=(_stats(),), approvals=(_approval(),), runtime=runtime)
    assert body["gate_status"] == "not_evaluated"
    assert {"fee_unverified", "lookahead_tests_failed"} <= set(body["not_evaluated_reasons"])
    assert body["historical_stat"] is None


def test_the_statement_counter_has_teeth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    statements = _count_statements(monkeypatch)
    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute("SELECT 1")
    conn.close()
    assert statements == ["SELECT 1"]
