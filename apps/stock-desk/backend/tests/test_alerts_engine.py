"""Tests for the alert evaluation engine: firing, skipping, cooldown, wording."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.alerts.engine import EvaluationResult, SymbolSnapshot, evaluate_alerts
from app.alerts.store import AlertStore
from app.services.fx import source_note
from tests.advice_helpers import make_signals, uptrend_signals
from tests.alerts_helpers import (
    RecordingLoader,
    add_rule,
    breaching_context,
    compliant_context,
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


# --- Signal condition rules --------------------------------------------------


def test_signal_condition_fires_on_the_signal_vocabulary(store: AlertStore) -> None:
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(
        store, _loader(snapshot(signals=uptrend_signals(rsi=82.0))), now=_NOW
    )
    assert len(result.events) == 1
    assert "14 日 RSI 最新值" in result.events[0].message
    assert result.events[0].observed["value"] == 82.0


def test_signal_condition_stays_quiet_when_the_comparison_is_false(store: AlertStore) -> None:
    add_rule(store, signal_rule(field="rsi14.last", op="gt", value=70.0))
    result = evaluate_alerts(
        store, _loader(snapshot(signals=uptrend_signals(rsi=40.0))), now=_NOW
    )
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
    result = evaluate_alerts(
        store, _loader(snapshot(signals=uptrend_signals())), now=_NOW
    )
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
    result = evaluate_alerts(
        store, _loader(snapshot(context=breaching_context())), now=_NOW
    )
    assert len(result.events) == 1
    message = result.events[0].message
    assert "觸發風險上限" in message
    assert "單一標的佔比上限" in message
    assert result.events[0].observed["violated_count"] == 1.0


def test_risk_limit_rule_can_watch_one_named_cap(store: AlertStore) -> None:
    add_rule(store, limit_rule(limit_id="gross_exposure"))
    result = evaluate_alerts(
        store, _loader(snapshot(context=breaching_context())), now=_NOW
    )
    # Gross exposure is not evaluable in that context, and "cannot check" must
    # not read as "checked and fine".
    assert _statuses(result) == ["skipped"]
    assert "無法判定是否違反" in (result.outcomes[0].reason or "")


def test_compliant_book_keeps_the_risk_rule_quiet(store: AlertStore) -> None:
    add_rule(store, limit_rule(limit_id="single_position_weight"))
    result = evaluate_alerts(
        store, _loader(snapshot(context=compliant_context())), now=_NOW
    )
    assert _statuses(result) == ["quiet"]


def test_a_watched_cap_absent_from_the_results_is_a_skip(store: AlertStore) -> None:
    # White-box: ``evaluate_limits`` always returns every cap, so this branch is
    # unreachable through the API. It is pinned anyway, because "the cap I was
    # asked to watch is not in the results" must never read as "not breached".
    add_rule(store, limit_rule(limit_id="kelly_fraction"))
    full = snapshot(context=breaching_context())
    partial = replace(
        full, limits=[check for check in full.limits if check.id != "kelly_fraction"]
    )
    result = evaluate_alerts(store, _loader(partial), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert "不在本次檢查結果中" in (result.outcomes[0].reason or "")


def test_a_fired_risk_limit_message_carries_the_fx_disclosure(store: AlertStore) -> None:
    # ADR-0005 F-4. Every cap in the message is denominated in TWD, so on a
    # foreign-currency holding each figure quoted came through the FX rate. The
    # message is what reaches the feed and the push channels, so the rate's
    # provenance has to be in the message itself.
    add_rule(store, limit_rule(limit_id="any"))
    disclosure = "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；端點未經查證。"
    result = evaluate_alerts(
        store,
        _loader(
            snapshot(context=breaching_context(), currency="USD", fx_disclosure=disclosure)
        ),
        now=_NOW,
    )
    assert len(result.events) == 1
    message = result.events[0].message
    assert "觸發風險上限" in message
    assert disclosure in message


def test_a_twd_holding_gets_no_fx_disclosure_it_did_not_use(store: AlertStore) -> None:
    # Nothing was converted, so there is no rate to qualify; padding every
    # message with the sentence would train the reader to skip past it.
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(
        store, _loader(snapshot(context=breaching_context())), now=_NOW
    )
    assert "匯率" not in result.events[0].message


def test_the_fx_disclosure_does_not_introduce_action_wording(store: AlertStore) -> None:
    # The disclosure is a statement of fact about a data source. It must not
    # drag the message across the line the alert layer keeps: measurement only.
    add_rule(store, limit_rule(limit_id="any"))
    result = evaluate_alerts(
        store,
        _loader(
            snapshot(
                context=breaching_context(),
                currency="USD",
                fx_disclosure=source_note("bank_of_taiwan"),
            )
        ),
        now=_NOW,
    )
    banned = ("買進", "賣出", "加碼", "減碼", "建議", "保證", "必漲", "穩賺")
    assert not any(word in result.events[0].message for word in banned)


def test_an_unevaluable_cap_says_why_the_inputs_were_missing(store: AlertStore) -> None:
    # "缺少輸入" on its own leaves the reader guessing between "no price" and
    # "no FX conversion"; the snapshot already knows which, so the skip says it.
    add_rule(store, limit_rule(limit_id="gross_exposure"))
    result = evaluate_alerts(
        store,
        _loader(
            snapshot(context=breaching_context(), reason="無法取得匯率換算（USDTWD）。")
        ),
        now=_NOW,
    )
    assert _statuses(result) == ["skipped"]
    reason = result.outcomes[0].reason or ""
    assert "無法判定是否違反" in reason
    assert "無法取得匯率換算" in reason


def test_no_limits_at_all_is_a_skip(store: AlertStore) -> None:
    add_rule(store, limit_rule())
    result = evaluate_alerts(store, _loader(snapshot()), now=_NOW)
    assert _statuses(result) == ["skipped"]
    assert "缺少組合估值" in (result.outcomes[0].reason or "")


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
    second = evaluate_alerts(
        store, loader, cooldown_minutes=60, now=_NOW + timedelta(minutes=30)
    )
    assert len(first.events) == 1
    assert second.events == []
    assert _statuses(second) == ["suppressed"]
    assert "不重複發出" in (second.outcomes[0].reason or "")


def test_cooldown_expires_and_the_rule_fires_again(store: AlertStore) -> None:
    add_rule(store, price_rule(threshold=100.0))
    loader = _loader(snapshot(close=120.0))
    evaluate_alerts(store, loader, cooldown_minutes=60, now=_NOW)
    later = evaluate_alerts(
        store, loader, cooldown_minutes=60, now=_NOW + timedelta(minutes=90)
    )
    assert len(later.events) == 1


def test_zero_cooldown_disables_suppression(store: AlertStore) -> None:
    add_rule(store, price_rule(threshold=100.0))
    loader = _loader(snapshot(close=120.0))
    evaluate_alerts(store, loader, cooldown_minutes=0, now=_NOW)
    again = evaluate_alerts(
        store, loader, cooldown_minutes=0, now=_NOW + timedelta(seconds=1)
    )
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
