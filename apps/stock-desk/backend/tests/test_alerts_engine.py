"""Tests for the alert evaluation engine: firing, skipping, cooldown, wording."""

from __future__ import annotations

import ast
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.advice.book import FX_APPLIED_NOTE, FX_UNAVAILABLE_NOTE
from app.advice.limits import (
    LIMIT_IDS,
    LIMIT_NAMES,
    PRICE_INPUT_LIMIT_IDS,
    LimitCheck,
    LimitStatus,
    PortfolioContext,
)
from app.alerts import engine as engine_module
from app.alerts.engine import EvaluationResult, SymbolSnapshot, evaluate_alerts
from app.alerts.store import AlertStore
from app.positions.models import Market
from app.services.fx import source_note
from tests.advice_helpers import make_signals, uptrend_signals
from tests.alerts_helpers import (
    RecordingLoader,
    add_rule,
    breaching_context,
    compliant_context,
    insert_legacy_signal_rule,
    limit_rule,
    price_rule,
    signal_rule,
    snapshot,
)

_NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> AlertStore:
    return AlertStore(db_path=tmp_path / "alerts.db")


def _loader(snap: SymbolSnapshot) -> RecordingLoader:
    return RecordingLoader(snap)


def _statuses(result: EvaluationResult) -> list[str]:
    return [outcome.status for outcome in result.outcomes]


# --- Price threshold rules ---------------------------------------------------


def test_price_above_fires_and_states_observation_and_threshold(store: AlertStore) -> None:
    add_rule(store, price_rule(above=True, threshold=100.0))
    result = evaluate_alerts(store, _loader(snapshot(close=120.0)), now=_NOW)
    assert len(result.events) == 1
    event = result.events[0]
    assert "120" in event.message and "100" in event.message
    assert "高於設定的門檻" in event.message
    assert event.observed["close"] == 120.0
    assert event.observed["threshold"] == 100.0
    assert event.acknowledged is False


def test_a_fired_message_carries_the_data_layers_own_sentence(store: AlertStore) -> None:
    """風控 2026-09-15 R1-a: a crossing judged on a spliced or cached series says so
    in the message the user receives, not only on a skip."""
    spliced = "這段日線資料由多個來源拼接（finmind、twse），每筆保留原本的來源；..."
    add_rule(store, price_rule(above=True, threshold=100.0))
    result = evaluate_alerts(
        store, _loader(snapshot(close=120.0, data_disclosure=spliced)), now=_NOW
    )
    assert len(result.events) == 1
    assert result.events[0].message.endswith(spliced)
    # 風控 R4-a: the bar date comes right before it, so "最新收盤價" is dated.
    assert "上述數值之資料日為 2026-07-25。 " + spliced in result.events[0].message
    # Fires again after the cooldown, on a snapshot without a sentence: nothing is invented.
    later = evaluate_alerts(store, _loader(snapshot(close=120.0)), now=_NOW + timedelta(hours=2))
    assert spliced not in later.events[0].message


def test_price_above_stays_quiet_below_the_threshold(store: AlertStore) -> None:
    add_rule(store, price_rule(above=True, threshold=200.0))
    result = evaluate_alerts(store, _loader(snapshot(close=120.0)), now=_NOW)
    assert result.events == []
    assert _statuses(result) == ["quiet"]


def test_price_below_fires_under_the_threshold(store: AlertStore) -> None:
    add_rule(store, price_rule(above=False, threshold=150.0))
    result = evaluate_alerts(store, _loader(snapshot(close=120.0)), now=_NOW)
    assert len(result.events) == 1
    assert "低於設定的門檻" in result.events[0].message


def test_no_price_is_a_skip_with_a_reason_not_a_silent_pass(store: AlertStore) -> None:
    add_rule(store, price_rule(above=True, threshold=100.0))
    result = evaluate_alerts(
        store,
        _loader(snapshot(close=None, reason="沒有可用的日線資料。")),
        now=_NOW,
    )
    assert result.events == []
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == "沒有可用的日線資料。"


@pytest.mark.parametrize("above", [True, False], ids=["above", "below"])
@pytest.mark.parametrize(
    "close",
    [
        pytest.param(0.0, id="zero"),
        pytest.param(-5.0, id="negative"),
        pytest.param(float("nan"), id="nan"),
    ],
)
def test_an_unusable_price_is_a_skip_not_a_comparison(
    store: AlertStore, close: float, above: bool
) -> None:
    # Before the shared guard, a zero close "crossed below" any positive
    # threshold and a NaN one was quietly never above or below it.
    add_rule(store, price_rule(above=above, threshold=100.0))
    result = evaluate_alerts(
        store,
        # An unrelated note on the snapshot must not stand in for the cause.
        _loader(snapshot(close=close, reason="資料來自 backup 層（fake）。")),
        now=_NOW,
    )
    assert result.events == []
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == "沒有可用的最新收盤價。"


# --- Signal condition rules --------------------------------------------------


@pytest.mark.parametrize(
    "close",
    [
        pytest.param(0.0, id="zero"),
        pytest.param(-5.0, id="negative"),
        pytest.param(float("nan"), id="nan"),
    ],
)
def test_an_unusable_close_skips_a_signal_rule_without_an_unrelated_note(
    store: AlertStore, close: float
) -> None:
    # Signals are withheld for the close (A′); a data-layer or FX note on the
    # snapshot is not why, so it must not be given as the reason.
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(
        store,
        _loader(snapshot(close=close, reason="資料來自 cache 層（finmind）。")),
        now=_NOW,
    )
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == "沒有可用的訊號輸出。"


def test_no_bars_still_skips_a_signal_rule_with_the_snapshots_reason(store: AlertStore) -> None:
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(
        store,
        _loader(snapshot(close=None, reason="沒有可用的日線資料。")),
        now=_NOW,
    )
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == "沒有可用的日線資料。"


def test_signal_condition_fires_on_the_signal_vocabulary(store: AlertStore) -> None:
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(store, _loader(snapshot(signals=uptrend_signals(rsi=82.0))), now=_NOW)
    assert len(result.events) == 1
    assert "14 日 RSI 最新值" in result.events[0].message
    assert result.events[0].observed["value"] == 82.0


def test_signal_condition_stays_quiet_when_the_comparison_is_false(store: AlertStore) -> None:
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(store, _loader(snapshot(signals=uptrend_signals(rsi=40.0))), now=_NOW)
    assert _statuses(result) == ["quiet"]


def test_missing_signal_field_is_a_skip_naming_the_field(store: AlertStore) -> None:
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(store, _loader(snapshot(signals=make_signals())), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert "rsi14.last" in (result.outcomes[0].reason or "")


def test_signal_condition_supports_a_field_to_field_reference(store: AlertStore) -> None:
    rule = signal_rule()
    rule["params"] = {"condition": {"field": "ma5.last", "op": "gt", "ref": "ma20.last"}}
    add_rule(store, rule)
    result = evaluate_alerts(store, _loader(snapshot(signals=uptrend_signals())), now=_NOW)
    assert len(result.events) == 1
    assert result.events[0].observed["compared_to"] == 105.0


def test_a_missing_reference_field_is_also_a_skip(store: AlertStore) -> None:
    rule = signal_rule()
    rule["params"] = {"condition": {"field": "ma5.last", "op": "gt", "ref": "ma60.last"}}
    add_rule(store, rule)
    signals = uptrend_signals(ma={"ma_5": 108.0, "ma_20": 105.0})  # no ma_60
    result = evaluate_alerts(store, _loader(snapshot(signals=signals)), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert "ma60.last" in (result.outcomes[0].reason or "")


def test_no_signals_at_all_is_a_skip(store: AlertStore) -> None:
    add_rule(store, signal_rule())
    result = evaluate_alerts(store, _loader(snapshot(signals={})), now=_NOW)
    assert _statuses(result) == ["skipped"]


# --- Risk limit rules --------------------------------------------------------


def test_risk_limit_breach_fires_and_quotes_the_numbered_cap(store: AlertStore) -> None:
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(store, _loader(snapshot(context=breaching_context())), now=_NOW)
    assert len(result.events) == 1
    message = result.events[0].message
    assert "觸發風險上限" in message
    assert "單一標的佔比上限" in message
    assert result.events[0].observed["violated_count"] == 1.0


def test_a_risk_limit_message_is_not_given_one_bar_date(store: AlertStore) -> None:
    """風控 R4-a 覆審: portfolio weights come from every holding's own close (and
    a possibly earlier rate), so a single bar date would overstate precision."""
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(
        store,
        _loader(
            snapshot(
                context=breaching_context(), data_disclosure="資料來自 cached_stale 層（twse）。"
            )
        ),
        now=_NOW,
    )
    message = result.events[0].message
    assert "資料日為" not in message
    assert message.endswith("資料來自 cached_stale 層（twse）。")


def test_risk_limit_rule_can_watch_one_named_cap(store: AlertStore) -> None:
    add_rule(store, limit_rule(limit_id="gross_exposure"))
    result = evaluate_alerts(store, _loader(snapshot(context=breaching_context())), now=_NOW)
    # Gross exposure is not evaluable in that context, and "cannot check" must
    # not read as "checked and fine".
    assert _statuses(result) == ["skipped"]
    assert "無法判定是否違反" in (result.outcomes[0].reason or "")


def test_compliant_book_keeps_the_risk_rule_quiet(store: AlertStore) -> None:
    add_rule(store, limit_rule(limit_id="single_position_weight"))
    result = evaluate_alerts(store, _loader(snapshot(context=compliant_context())), now=_NOW)
    assert _statuses(result) == ["quiet"]


def test_a_watched_cap_absent_from_the_results_is_a_skip(store: AlertStore) -> None:
    # White-box: ``evaluate_limits`` always returns every cap, so this branch is
    # unreachable through the API. It is pinned anyway, because "the cap I was
    # asked to watch is not in the results" must never read as "not breached".
    add_rule(store, limit_rule(limit_id="kelly_fraction"))
    full = snapshot(context=breaching_context())
    partial = replace(full, limits=[check for check in full.limits if check.id != "kelly_fraction"])
    result = evaluate_alerts(store, _loader(partial), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert "不在本次檢查結果中" in (result.outcomes[0].reason or "")


def _cap_4_breaching_context() -> PortfolioContext:
    """:func:`breaching_context` with an ATR: cap 4 is violated beside cap 1."""
    return breaching_context().model_copy(update={"atr": 5.0})


def test_a_fired_risk_limit_message_carries_the_fx_disclosure(store: AlertStore) -> None:
    # ADR-0005 F-4. Every cap in the message is denominated in TWD, so on a
    # foreign-currency holding each figure quoted came through an FX rate. The
    # message is what reaches the feed and the push channels, so the rate's
    # provenance has to be in the message itself.
    # 風控 RK4c（2026-10-08）, cells 一致帳本／混源 push (R4c-8, R4c-13 item 8):
    # which version depends on the caps the message lists. Only cap 1 here, so
    # no listed figure used the quote: the version without it.
    add_rule(store, limit_rule(limit_id="any"))
    disclosure = "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；端點未經查證。"
    with_quote = "報價版揭露（測試用）。"
    result = evaluate_alerts(
        store,
        _loader(
            snapshot(
                context=breaching_context(),
                currency="USD",
                fx_disclosure=with_quote,
                fx_disclosure_without_quote=disclosure,
            )
        ),
        now=_NOW,
    )
    assert len(result.events) == 1
    message = result.events[0].message
    assert "觸發風險上限" in message
    assert "第 4 條" not in message  # not vacuous: cap 4 is not listed
    assert message.endswith(f" {disclosure}")
    assert with_quote not in message


def test_a_fired_message_listing_cap_4_carries_the_quotes_disclosure(store: AlertStore) -> None:
    # 風控 RK4c（2026-10-08）, push with cap 4 in the message (R4c-8, R4c-13
    # item 8): its figure is ATR x the applied quote, so the version with it.
    add_rule(store, limit_rule(limit_id="any"))
    disclosure = "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；端點未經查證。"
    without_quote = "非報價版揭露（測試用）。"
    result = evaluate_alerts(
        store,
        _loader(
            snapshot(
                context=_cap_4_breaching_context(),
                currency="USD",
                fx_disclosure=disclosure,
                fx_disclosure_without_quote=without_quote,
            )
        ),
        now=_NOW,
    )
    assert len(result.events) == 1
    message = result.events[0].message
    assert "第 4 條" in message  # not vacuous: cap 4 is listed
    assert message.endswith(f" {disclosure}")
    assert without_quote not in message


def test_a_twd_holding_gets_no_fx_disclosure_it_did_not_use(store: AlertStore) -> None:
    # Nothing was converted, so there is no rate to qualify; padding every
    # message with the sentence would train the reader to skip past it.
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(store, _loader(snapshot(context=breaching_context())), now=_NOW)
    assert "匯率" not in result.events[0].message


@pytest.mark.parametrize(
    ("field", "context"),
    [
        pytest.param("fx_disclosure", _cap_4_breaching_context(), id="with-quote-cap-4"),
        pytest.param("fx_disclosure_without_quote", breaching_context(), id="without-quote-cap-1"),
    ],
)
def test_the_fx_disclosure_does_not_introduce_action_wording(
    store: AlertStore, field: str, context: PortfolioContext
) -> None:
    # The disclosure is a statement of fact about a data source. It must not
    # drag the message across the line the alert layer keeps: measurement only.
    # 風控 RK4c（2026-10-08）, both push versions (R4c-13 item 9, RK4c-R9 (3)):
    # each is first shown to be in the message, so the scan cannot pass on a
    # message that carries no disclosure.
    add_rule(store, limit_rule(limit_id="any"))
    disclosure = source_note("bank_of_taiwan")
    snap = snapshot(
        context=context,
        currency="USD",
        fx_disclosure=disclosure if field == "fx_disclosure" else None,
        fx_disclosure_without_quote=disclosure if field == "fx_disclosure_without_quote" else None,
    )
    result = evaluate_alerts(store, _loader(snap), now=_NOW)
    message = result.events[0].message
    assert disclosure in message
    banned = ("買進", "賣出", "加碼", "減碼", "建議", "保證", "必漲", "穩賺")
    assert not any(word in message for word in banned)


def test_no_limits_at_all_is_a_skip(store: AlertStore) -> None:
    add_rule(store, limit_rule())
    result = evaluate_alerts(store, _loader(snapshot()), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert "缺少組合估值" in (result.outcomes[0].reason or "")


# --- risk_limit "any": some caps unevaluated, none violated (S-B2) -------------

# Expected strings are the risk-compliance-officer's own expansions (S-B2-A
# (a)/(b)/(c), approved verbatim 2026-10-07), not rebuilt from the template.
_S_B2_A = "本次有 1 條上限未評估，未納入判定：分數 Kelly 部位上限。其餘已評估的上限皆未違反。"
_S_B2_B = (
    "本次有 3 條上限未評估，未納入判定：單一產業佔比上限、總曝險上限、分數 Kelly 部位上限。"
    "其餘已評估的上限皆未違反。"
)
_S_B2_C = (
    "本次有 4 條上限未評估，未納入判定：單一標的佔比上限、單一產業佔比上限、"
    "單筆最大可承受虧損、分數 Kelly 部位上限。其餘已評估的上限皆未違反。"
)
_S_B2_MARKER = "上限未評估，未納入判定"

# Non-empty notes a mixed-quiet reason must never quote: the snapshot's own
# reason (an applied-rate note, which says nothing about why a cap was left
# out), every disclosure, and each cap's detail.
_SENTINEL_REASON = FX_APPLIED_NOTE.format(
    pair="USDTWD", rate="31.5", status="fresh", source="bank_of_taiwan", as_of="2026-07-24"
)
_SENTINEL_FX = "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；端點未經查證。"
_SENTINEL_DATA = "資料來自 cached_stale 層（twse）。"


def _detail(limit_id: str) -> str:
    return f"細節哨兵：{limit_id} 的檢查細節句。"


def _caps(statuses: dict[str, LimitStatus]) -> list[LimitCheck]:
    """Every cap in ``LIMIT_IDS`` order, ``passed`` unless named, each with a detail."""
    return [
        LimitCheck(
            index=index,
            id=limit_id,
            name=LIMIT_NAMES[limit_id],
            status=statuses.get(limit_id, "passed"),
            detail=_detail(limit_id),
            observed=None,
            threshold=None,
        )
        for index, limit_id in enumerate(LIMIT_IDS, start=1)
    ]


def _caps_snapshot(statuses: dict[str, LimitStatus]) -> SymbolSnapshot:
    # 風控 RK4c（2026-10-08）RK4c-R13: both disclosure fields carry the same
    # sentinel. These S-B2 tests do not judge which version a fired message
    # picks (R4c-8 is pinned by tests/test_rk4c_quote_shown.py and by the
    # ``without-quote-cap-1`` case above); both fields must hold a value so the
    # quiet and skip scans below cover each of them.
    return replace(
        snapshot(
            reason=_SENTINEL_REASON,
            fx_disclosure=_SENTINEL_FX,
            fx_disclosure_without_quote=_SENTINEL_FX,
            data_disclosure=_SENTINEL_DATA,
        ),
        limits=_caps(statuses),
    )


def _listed_names(reason: str) -> list[str]:
    return reason.split("：", 1)[1].split("。", 1)[0].split("、")


@pytest.mark.parametrize(
    ("unevaluated", "expected"),
    [
        pytest.param(("kelly_fraction",), _S_B2_A, id="a-one"),
        pytest.param(("sector_weight", "gross_exposure", "kelly_fraction"), _S_B2_B, id="b-three"),
        pytest.param(
            ("single_position_weight", "sector_weight", "per_trade_loss", "kelly_fraction"),
            _S_B2_C,
            id="c-four",
        ),
    ],
)
def test_an_any_rule_with_unevaluated_caps_stays_quiet_and_names_them(
    store: AlertStore, unevaluated: tuple[str, ...], expected: str
) -> None:
    add_rule(store, limit_rule(limit_id="any"))
    snap = _caps_snapshot(dict.fromkeys(unevaluated, "not_evaluable"))
    result = evaluate_alerts(store, _loader(snap), now=_NOW)

    assert _statuses(result) == ["quiet"]
    reason = result.outcomes[0].reason
    assert reason == expected
    # The names: as many as ``{n}``, in ``LIMIT_IDS`` order, each a cap's own name.
    assert reason == engine_module.UNEVALUATED_LIMITS_NOTE.format(
        n=len(unevaluated), names="、".join(LIMIT_NAMES[i] for i in unevaluated)
    )
    names = _listed_names(reason)
    assert len(names) == len(unevaluated)
    assert f"本次有 {len(names)} 條上限未評估" in reason
    assert names == [LIMIT_NAMES[i] for i in LIMIT_IDS if i in unevaluated]
    # Quiet means no event, so nothing reaches the feed or the push channels.
    assert result.events == []
    assert store.list_events() == []


@pytest.mark.parametrize(
    "unevaluated",
    [
        pytest.param(("kelly_fraction",), id="one"),
        pytest.param(("sector_weight", "gross_exposure", "kelly_fraction"), id="three"),
        pytest.param(
            ("single_position_weight", "sector_weight", "per_trade_loss", "kelly_fraction"),
            id="four",
        ),
    ],
)
def test_the_unevaluated_caps_reason_quotes_no_cause_and_no_disclosure(
    store: AlertStore, unevaluated: tuple[str, ...]
) -> None:
    """風控 R-S2-2 negative: the reason discloses *which* caps were left out, never
    why -- so neither the snapshot's note, nor a cap's detail, nor any
    disclosure may be appended to it, even when every one of them is set."""
    add_rule(store, limit_rule(limit_id="any"))
    snap = _caps_snapshot(dict.fromkeys(unevaluated, "not_evaluable"))
    assert snap.reason and snap.as_of and all(check.detail for check in snap.limits)
    result = evaluate_alerts(store, _loader(snap), now=_NOW)

    reason = result.outcomes[0].reason or ""
    assert reason.endswith("其餘已評估的上限皆未違反。")
    for unwanted in (_SENTINEL_REASON, _SENTINEL_FX, _SENTINEL_DATA):
        assert unwanted not in reason
    # Fragments too, so a partial quote cannot slip through.
    for fragment in ("換算為台幣", "資料狀態", "USDTWD", "台灣銀行", "cached_stale", "資料日為"):
        assert fragment not in reason
    assert "細節哨兵" not in reason
    for check in snap.limits:
        assert check.detail not in reason


def test_an_any_rule_over_the_real_caps_reads_the_approved_wording(store: AlertStore) -> None:
    # Through ``evaluate_limits``: the compliant book has no sector, no net
    # worth and no Kelly pair, so caps 2, 3 and 5 are unevaluated (example (b)).
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(
        store,
        _loader(snapshot(context=compliant_context(), reason=_SENTINEL_REASON)),
        now=_NOW,
    )
    assert _statuses(result) == ["quiet"]
    assert result.outcomes[0].reason == _S_B2_B


def test_an_any_rule_with_every_cap_passed_is_quiet_without_a_reason(store: AlertStore) -> None:
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(store, _loader(_caps_snapshot({})), now=_NOW)
    assert _statuses(result) == ["quiet"]
    assert result.outcomes[0].reason is None


@pytest.mark.parametrize("limit_id", LIMIT_IDS)
def test_a_rule_on_one_named_cap_never_reads_the_unevaluated_caps_wording(
    store: AlertStore, limit_id: str
) -> None:
    # The same mixed book as example (b); one watched cap is either passed
    # (quiet, no reason) or unevaluated (the existing skip), never the mix.
    add_rule(store, limit_rule(limit_id=limit_id))
    unevaluated = ("sector_weight", "gross_exposure", "kelly_fraction")
    snap = _caps_snapshot(dict.fromkeys(unevaluated, "not_evaluable"))
    result = evaluate_alerts(store, _loader(snap), now=_NOW)

    [outcome] = result.outcomes
    assert _S_B2_MARKER not in (outcome.reason or "")
    if limit_id in unevaluated:
        assert outcome.status == "skipped"
        # No tail: ``reason`` (an applied-rate sentinel here) is not a cause,
        # and the snapshot carries no failed conversion.
        assert outcome.reason == _unevaluable_skip(LIMIT_NAMES[limit_id])
    else:
        assert outcome.status == "quiet"
        assert outcome.reason is None


def test_a_violated_cap_still_fires_with_the_existing_message(store: AlertStore) -> None:
    # Mixed plus one violation: the fired message is unchanged by S-B2 and says
    # nothing about the unevaluated caps.
    add_rule(store, limit_rule(limit_id="any"))
    snap = _caps_snapshot(
        {
            "single_position_weight": "violated",
            "sector_weight": "not_evaluable",
            "kelly_fraction": "not_evaluable",
        }
    )
    result = evaluate_alerts(store, _loader(snap), now=_NOW)

    assert _statuses(result) == ["fired"]
    assert result.outcomes[0].reason is None
    assert result.events[0].message == (
        "2330 觸發風險上限：第 1 條（單一標的佔比上限）。"
        f"{_detail('single_position_weight')} {_SENTINEL_FX} {_SENTINEL_DATA}"
    )


def test_every_cap_unevaluated_is_still_the_existing_skip(store: AlertStore) -> None:
    add_rule(store, limit_rule(limit_id="any"))
    snap = _caps_snapshot(dict.fromkeys(LIMIT_IDS, "not_evaluable"))
    result = evaluate_alerts(store, _loader(snap), now=_NOW)

    assert _statuses(result) == ["skipped"]
    names = "、".join(LIMIT_NAMES[i] for i in LIMIT_IDS)
    # The main sentence alone: the applied-rate ``reason`` is no longer appended.
    assert result.outcomes[0].reason == _unevaluable_skip(names)

    # With a failed conversion, ``any`` watches per_trade_loss, so it is named.
    failed = replace(snap, price_cap_cause=_FX_FAILURE)
    again = evaluate_alerts(store, _loader(failed), now=_NOW)
    assert again.outcomes[0].reason == f"{_unevaluable_skip(names)} {_FX_FAILURE}"


def test_the_unevaluated_caps_reason_writes_no_event_and_ignores_the_cooldown(
    store: AlertStore,
) -> None:
    rule = add_rule(store, limit_rule(limit_id="any"))
    fired = evaluate_alerts(
        store, _loader(_caps_snapshot({"single_position_weight": "violated"})), now=_NOW
    )
    assert _statuses(fired) == ["fired"]
    last = store.last_triggered_at(rule.id)

    mixed = _loader(_caps_snapshot({"kelly_fraction": "not_evaluable"}))
    # Inside the cooldown window: a quiet rule is not "suppressed" -- it did not cross.
    first = evaluate_alerts(store, mixed, cooldown_minutes=60, now=_NOW + timedelta(minutes=5))
    second = evaluate_alerts(store, mixed, cooldown_minutes=60, now=_NOW + timedelta(minutes=10))
    for result in (first, second):
        assert [(o.status, o.reason) for o in result.outcomes] == [("quiet", _S_B2_A)]
        assert result.events == []
    assert len(store.list_events()) == 1
    assert store.last_triggered_at(rule.id) == last


def test_price_and_signal_rules_stay_quiet_without_a_reason(store: AlertStore) -> None:
    add_rule(store, price_rule(above=True, threshold=200.0))
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(
        store,
        _loader(
            snapshot(
                close=120.0,
                signals=uptrend_signals(rsi=40.0),
                context=compliant_context(),
                reason=_SENTINEL_REASON,
            )
        ),
        now=_NOW,
    )
    assert [(o.status, o.reason) for o in result.outcomes] == [("quiet", None), ("quiet", None)]


# --- risk_limit, every watched cap unevaluated: which cause may follow ---------
#
# 2026-10-07 任務單「risk_limit 全部 not_evaluable 時 skipped 句尾只接匯率失敗成因」,
# 方案 (A): the tail is ``price_cap_cause`` (a failed FX conversion) or nothing,
# behind an A′ gate and a scope gate; ``snapshot.reason`` is never the tail.

# A real failure sentence (the book's own constant), so nothing here is new wording.
_FX_FAILURE = FX_UNAVAILABLE_NOTE.format(
    currency="USD", pair="USDTWD", status="unavailable", source="fake_fx", as_of="未知"
)


def _unevaluable_skip(names: str) -> str:
    """The existing main sentence of an all-unevaluated skip, verbatim."""
    return f"監看的上限（{names}）缺少輸入，無法判定是否違反。"


def test_an_unevaluable_price_cap_names_the_failed_conversion(store: AlertStore) -> None:
    # "缺少輸入" on its own leaves the reader guessing between "no price" and
    # "no FX conversion"; when the conversion failed and the cap reads the price
    # or ATR, the skip says so -- and nothing from ``reason`` comes with it.
    add_rule(store, limit_rule(limit_id="per_trade_loss"))
    snap = snapshot(
        context=breaching_context(),  # no ATR: per_trade_loss is not_evaluable
        reason=f"{_SENTINEL_DATA} {_FX_FAILURE}",
        price_cap_cause=_FX_FAILURE,
    )
    result = evaluate_alerts(store, _loader(snap), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == f"{_unevaluable_skip('單筆最大可承受虧損')} {_FX_FAILURE}"
    assert _SENTINEL_DATA not in (result.outcomes[0].reason or "")


@pytest.mark.parametrize(
    "limit_id", [limit_id for limit_id in LIMIT_IDS if limit_id not in PRICE_INPUT_LIMIT_IDS]
)
def test_a_failed_conversion_is_not_given_as_the_cause_of_a_cap_without_a_price(
    store: AlertStore, limit_id: str
) -> None:
    # Scope gate: a missing rate is not why these caps could not be evaluated.
    add_rule(store, limit_rule(limit_id=limit_id))
    snap = _caps_snapshot(dict.fromkeys(LIMIT_IDS, "not_evaluable"))
    snap = replace(snap, price_cap_cause=_FX_FAILURE)
    result = evaluate_alerts(store, _loader(snap), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == _unevaluable_skip(LIMIT_NAMES[limit_id])


@pytest.mark.parametrize("close", [0.0, -1.0, float("nan")])
@pytest.mark.parametrize("limit_id", ["per_trade_loss", "any"])
def test_an_unusable_close_keeps_the_fx_sentence_off_a_risk_limit_skip(
    store: AlertStore, close: float, limit_id: str
) -> None:
    # A′ gate (風控 R-B1): the price and ATR were withheld for the close, so a
    # failed conversion on the same snapshot is not the cause.
    add_rule(store, limit_rule(limit_id=limit_id))
    snap = _caps_snapshot(dict.fromkeys(LIMIT_IDS, "not_evaluable"))
    snap = replace(snap, close=close, price_cap_cause=_FX_FAILURE)
    result = evaluate_alerts(store, _loader(snap), now=_NOW)
    watched = [LIMIT_NAMES[i] for i in LIMIT_IDS if limit_id in ("any", i)]
    assert _statuses(result) == ["skipped"]
    assert result.outcomes[0].reason == _unevaluable_skip("、".join(watched))


def test_a_missing_close_does_not_trip_the_unusable_close_gate(store: AlertStore) -> None:
    # A′ is "present but unusable"; ``close=None`` is not A′, so the scope gate
    # alone decides.
    add_rule(store, limit_rule(limit_id="per_trade_loss"))
    snap = replace(
        _caps_snapshot(dict.fromkeys(LIMIT_IDS, "not_evaluable")),
        close=None,
        price_cap_cause=_FX_FAILURE,
    )
    result = evaluate_alerts(store, _loader(snap), now=_NOW)
    assert result.outcomes[0].reason == f"{_unevaluable_skip('單筆最大可承受虧損')} {_FX_FAILURE}"


def test_a_risk_limit_skip_does_not_quote_the_snapshots_reason(store: AlertStore) -> None:
    # ``reason`` holds the data layer's note and, on an applied rate, the rate
    # used -- neither is why a cap was unevaluable (both were once appended here).
    add_rule(store, limit_rule(limit_id="per_trade_loss"))
    snap = snapshot(context=breaching_context(), reason=f"{_SENTINEL_DATA} {_SENTINEL_REASON}")
    result = evaluate_alerts(store, _loader(snap), now=_NOW)
    assert result.outcomes[0].reason == _unevaluable_skip("單筆最大可承受虧損")


def test_the_engine_names_no_cap_and_reads_no_book_note() -> None:
    # K-4 / K-5: the scope comes from ``PRICE_INPUT_LIMIT_IDS`` and the cause
    # from a field; the engine neither spells a cap id nor matches note text.
    tree = ast.parse(Path(engine_module.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(module.startswith("app.advice.book") for module in imported)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not literals & set(LIMIT_IDS)


# --- Scheduling behaviour ----------------------------------------------------


def test_disabled_rules_are_not_evaluated(store: AlertStore) -> None:
    add_rule(store, price_rule(threshold=1.0, enabled=False))
    result = evaluate_alerts(store, _loader(snapshot(close=120.0)), now=_NOW)
    assert result.evaluated == 0
    assert result.events == []


def test_cooldown_suppresses_a_repeat_within_the_window(store: AlertStore) -> None:
    add_rule(store, price_rule(threshold=100.0))
    loader = _loader(snapshot(close=120.0))
    first = evaluate_alerts(store, loader, cooldown_minutes=60, now=_NOW)
    second = evaluate_alerts(store, loader, cooldown_minutes=60, now=_NOW + timedelta(minutes=30))
    assert len(first.events) == 1
    assert second.events == []
    assert _statuses(second) == ["suppressed"]
    assert "不重複發出" in (second.outcomes[0].reason or "")


def test_cooldown_expires_and_the_rule_fires_again(store: AlertStore) -> None:
    add_rule(store, price_rule(threshold=100.0))
    loader = _loader(snapshot(close=120.0))
    evaluate_alerts(store, loader, cooldown_minutes=60, now=_NOW)
    later = evaluate_alerts(store, loader, cooldown_minutes=60, now=_NOW + timedelta(minutes=90))
    assert len(later.events) == 1


def test_zero_cooldown_disables_suppression(store: AlertStore) -> None:
    add_rule(store, price_rule(threshold=100.0))
    loader = _loader(snapshot(close=120.0))
    evaluate_alerts(store, loader, cooldown_minutes=0, now=_NOW)
    again = evaluate_alerts(store, loader, cooldown_minutes=0, now=_NOW + timedelta(seconds=1))
    assert len(again.events) == 1


def test_one_snapshot_is_loaded_per_symbol_however_many_rules_watch_it(
    store: AlertStore,
) -> None:
    add_rule(store, price_rule(threshold=100.0))
    add_rule(store, price_rule(threshold=110.0))
    add_rule(store, price_rule(above=False, threshold=90.0))
    loader = _loader(snapshot(close=120.0))
    evaluate_alerts(store, loader, now=_NOW)
    assert loader.calls == [("2330", "TW")]


def test_alert_messages_carry_no_action_wording(store: AlertStore) -> None:
    add_rule(store, price_rule(threshold=100.0))
    add_rule(store, limit_rule(limit_id="single_position_weight"))
    result = evaluate_alerts(
        store, _loader(snapshot(close=120.0, context=breaching_context())), now=_NOW
    )
    banned = ("買進", "賣出", "加碼", "減碼", "建議", "保證", "必漲", "穩賺")
    for event in result.events:
        assert not any(word in event.message for word in banned)


# --- A loader that raises for one symbol (方案 B) ------------------------------


_FAILING = "2330"
_HEALTHY = "2317"


class _FailingForOneSymbol:
    """Raises ``error`` for one symbol, serves a healthy snapshot for any other."""

    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.calls: list[tuple[str, Market]] = []

    def __call__(self, symbol: str, market: Market) -> SymbolSnapshot:
        self.calls.append((symbol, market))
        if symbol == _FAILING:
            raise self._error
        return snapshot(
            symbol=symbol,
            close=120.0,
            signals=uptrend_signals(),
            context=breaching_context(symbol),
        )


def _healthy_rules(store: AlertStore) -> list[int]:
    return [
        add_rule(store, price_rule(threshold=100.0, symbol=_HEALTHY)).id,
        add_rule(store, signal_rule(field="rsi14.last", op="gt", value=0.0, symbol=_HEALTHY)).id,
        add_rule(store, limit_rule(limit_id="single_position_weight", symbol=_HEALTHY)).id,
    ]


def test_a_loader_failure_skips_only_that_symbol(
    store: AlertStore, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The exception text carries the symbol on purpose: it may reach the
    # traceback, never the log line itself.
    loader = _FailingForOneSymbol(RuntimeError(f"boom on {_FAILING}"))
    failing = {
        "price": add_rule(store, price_rule(threshold=100.0, symbol=_FAILING)).id,
        "signal": add_rule(store, signal_rule(symbol=_FAILING)).id,
        "limit": add_rule(store, limit_rule(symbol=_FAILING)).id,
        "beta": insert_legacy_signal_rule(store.db_path, field="beta.value", symbol=_FAILING),
    }
    healthy = _healthy_rules(store)

    with caplog.at_level(logging.WARNING, logger=engine_module.logger.name):
        result = evaluate_alerts(store, loader, now=_NOW)

    outcomes = {outcome.rule_id: outcome for outcome in result.outcomes}
    # Each rule type's existing fallback, verbatim -- no new wording.
    assert outcomes[failing["price"]].reason == "沒有可用的最新收盤價。"
    assert outcomes[failing["signal"]].reason == "沒有可用的訊號輸出。"
    assert outcomes[failing["limit"]].reason == "沒有可用的風險上限檢查結果（缺少組合估值）。"
    assert outcomes[failing["beta"]].reason == (
        "此規則使用的 beta.value（相對指標的 beta），警示不提供作為條件。"
        "每次檢查都會略過此規則，不會觸發。可改用其他欄位的條件，或刪除此規則。"
    )
    assert {outcomes[rule_id].status for rule_id in failing.values()} == {"skipped"}
    # Not retried within the tick, however many rules watch the symbol.
    assert loader.calls.count((_FAILING, "TW")) == 1
    assert loader.calls.count((_HEALTHY, "TW")) == 1

    # The healthy symbol reads exactly as it does on a tick without the failing one.
    baseline_store = AlertStore(db_path=tmp_path / "baseline.db")
    _healthy_rules(baseline_store)
    baseline = evaluate_alerts(baseline_store, _FailingForOneSymbol(RuntimeError()), now=_NOW)
    assert [(outcomes[rule_id].status, outcomes[rule_id].reason) for rule_id in healthy] == [
        (outcome.status, outcome.reason) for outcome in baseline.outcomes
    ]
    assert [event.message for event in result.events] == [
        event.message for event in baseline.events
    ]
    assert len(result.events) == 3

    [record] = [r for r in caplog.records if r.levelno == logging.WARNING]
    # The market, a count and the exception class, nothing else: no symbol, no rule id.
    assert record.getMessage() == (
        "alert evaluation: snapshot load failed (market=TW, RuntimeError); "
        "4 rule(s) skipped this tick"
    )
    assert record.exc_info is not None and record.exc_info[0] is RuntimeError


def test_a_loader_failure_is_logged_once_per_symbol_not_per_rule(
    store: AlertStore, caplog: pytest.LogCaptureFixture
) -> None:
    for threshold in (100.0, 110.0, 120.0):
        add_rule(store, price_rule(threshold=threshold, symbol=_FAILING))
    with caplog.at_level(logging.WARNING, logger=engine_module.logger.name):
        result = evaluate_alerts(store, _FailingForOneSymbol(ValueError("bad bar")), now=_NOW)
    assert _statuses(result) == ["skipped", "skipped", "skipped"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [
        "alert evaluation: snapshot load failed (market=TW, ValueError); "
        "3 rule(s) skipped this tick"
    ]


def test_load_failures_counts_symbols_not_rules(store: AlertStore) -> None:
    for threshold in (100.0, 110.0, 120.0):
        add_rule(store, price_rule(threshold=threshold, symbol=_FAILING))
    _healthy_rules(store)
    result = evaluate_alerts(store, _FailingForOneSymbol(RuntimeError()), now=_NOW)
    assert result.load_failures == 1


def test_load_failures_counts_each_failing_symbol_once(store: AlertStore) -> None:
    other = "2454"

    def load(symbol: str, market: Market) -> SymbolSnapshot:
        if symbol in {_FAILING, other}:
            raise RuntimeError("boom")
        return snapshot(symbol=symbol, close=120.0)

    for symbol in (_FAILING, other):
        for threshold in (100.0, 110.0):
            add_rule(store, price_rule(threshold=threshold, symbol=symbol))
    add_rule(store, price_rule(threshold=100.0, symbol=_HEALTHY))
    result = evaluate_alerts(store, load, now=_NOW)
    assert result.load_failures == 2


def test_a_clean_tick_has_no_load_failures(store: AlertStore) -> None:
    _healthy_rules(store)
    result = evaluate_alerts(store, _FailingForOneSymbol(RuntimeError()), now=_NOW)
    assert result.load_failures == 0


def test_an_interrupt_in_the_loader_is_not_swallowed(store: AlertStore) -> None:
    # Only ``Exception`` is isolated: stopping the process must still stop it.
    add_rule(store, price_rule(symbol=_FAILING))
    with pytest.raises(KeyboardInterrupt):
        evaluate_alerts(store, _FailingForOneSymbol(KeyboardInterrupt()), now=_NOW)
