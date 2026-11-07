"""N190-I: an unsettled S/P sell next to a later sell on the same page (N190-C4～C7).

風控 2026-11-04 第二節之 2 (逐字定稿) and 2026-11-05 B-3 (「較晚 sell 列」 has no
EMERGENCY). The pure function first, then the real ladder (QB-7) on the
holiday case that leaves the earlier line stuck.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.playbook import wording
from app.playbook.models import Directive, SettlementResult, UnsettledLine
from app.playbook.service import LoadedSeries, with_earlier_sell_notes
from app.playbook.store import SETTLED_SINCE_RULE_IDS
from tests.n190_helpers import (
    FRI,
    NEXT_MON,
    S1_CLOSE,
    THU,
    TUE,
    WED,
    build,
    hold_shares,
    pending_sell,
    seed_pending,
    settlement_of,
)

_LOADED = {"2330": LoadedSeries([], "fresh", "twse", None)}


def _no_open(line: Directive, status: str = "fresh", source: str = "twse") -> str:
    return wording.SETTLEMENT_NO_OPEN_PRICE.format(
        symbol=line.symbol,
        execution_date=line.execution_date.isoformat(),
        status=status,
        source=source,
    )


def _settlement(*lines: Directive, reasons: list[str] | None = None) -> SettlementResult:
    texts = reasons or [_no_open(line) for line in lines]
    unsettled = [
        UnsettledLine(directive_id=index + 1, directive=line, reason=text)
        for index, (line, text) in enumerate(zip(lines, texts, strict=True))
    ]
    summary = wording.SETTLEMENT_SUMMARY.format(
        settled_on=WED.isoformat(), executed=0, missed=0, pending=len(lines)
    )
    return SettlementResult(
        settled_on=WED,
        settled=[],
        unsettled=unsettled,
        warnings=[*texts, summary],
    )


def _sell(
    batch_no: int | None, execution_date: date, *, rule_id: str = "S1", shares: int = 100
) -> Directive:
    return pending_sell(
        "2330",
        batch_no,
        rule_id=rule_id,
        data_date=TUE,
        execution_date=execution_date,
        shares=shares,
    )


def _note(*later: Directive) -> str:
    items = []
    for line in later:
        if line.batch_no is None:
            items.append(
                wording.SETTLEMENT_EARLIER_SELL_SYMBOL_ITEM.format(
                    symbol=line.symbol,
                    rule_id=line.rule_id,
                    shares=line.shares,
                    execution_date=line.execution_date.isoformat(),
                )
            )
        else:
            items.append(
                wording.SETTLEMENT_EARLIER_SELL_BATCH_ITEM.format(
                    symbol=line.symbol,
                    batch_no=line.batch_no,
                    rule_id=line.rule_id,
                    shares=line.shares,
                    execution_date=line.execution_date.isoformat(),
                )
            )
    return wording.SETTLEMENT_EARLIER_SELL_NOT_DEDUCTED_NOTE.format(later_items="、".join(items))


def _assert_mirrored(result: SettlementResult, before: SettlementResult) -> None:
    """N190-C7: same length, same order, every reason equal to its mirror."""
    assert len(result.warnings) == len(before.warnings)
    for position, line in enumerate(result.unsettled):
        assert result.warnings[position] == line.reason
    assert result.warnings[len(result.unsettled) :] == before.warnings[len(before.unsettled) :]


def test_a_later_sell_of_the_same_batch_appends_n190_i_to_reason_and_mirror() -> None:
    earlier = _sell(1, WED)
    later = _sell(1, THU, shares=77)
    before = _settlement(earlier)

    result = with_earlier_sell_notes(before, logged=[later], loaded=_LOADED)

    (line,) = result.unsettled
    assert line.reason == _no_open(earlier) + _note(later)
    assert "2330第 1 批規則 S1 賣出 77 股（預定執行日 2026-08-13）" in line.reason
    _assert_mirrored(result, before)


def test_s2_on_either_side_widens_the_match_to_the_symbol() -> None:
    s2_later = _sell(None, THU, rule_id="S2", shares=300)
    result = with_earlier_sell_notes(_settlement(_sell(1, WED)), logged=[s2_later], loaded=_LOADED)
    assert result.unsettled[0].reason.endswith(_note(s2_later))
    assert "2330規則 S2 整檔賣出 300 股（預定執行日 2026-08-13）" in result.unsettled[0].reason

    other_batch = _sell(2, THU, rule_id="P1", shares=33)
    result = with_earlier_sell_notes(
        _settlement(_sell(None, WED, rule_id="S2")), logged=[other_batch], loaded=_LOADED
    )
    assert result.unsettled[0].reason.endswith(_note(other_batch))


def test_items_follow_execution_date_then_batch_no() -> None:
    lines = [_sell(None, FRI, rule_id="S2"), _sell(2, THU), _sell(1, FRI, rule_id="P3")]
    result = with_earlier_sell_notes(
        _settlement(_sell(None, WED, rule_id="S2")), logged=lines, loaded=_LOADED
    )
    assert result.unsettled[0].reason.endswith(_note(lines[1], lines[0], lines[2]))


def test_nothing_is_added_when_no_later_sell_qualifies() -> None:
    earlier = _sell(1, WED)
    before = _settlement(earlier)
    not_later = [
        _sell(2, THU),  # another batch, neither is S2
        _sell(1, WED),  # the same day, not later
        pending_sell("2454", 1, data_date=TUE, execution_date=THU),  # another symbol
        _sell(1, THU, rule_id="EMERGENCY"),  # B-3: never a later line
        _sell(1, THU).model_copy(update={"action": "buy"}),
    ]
    assert with_earlier_sell_notes(before, logged=not_later, loaded=_LOADED) == before


def test_only_an_s_p_sell_with_its_own_no_open_price_reason_is_an_earlier_line() -> None:
    later = [_sell(1, THU)]
    emergency = _sell(1, WED, rule_id="EMERGENCY")
    buy = _sell(1, WED).model_copy(update={"action": "buy", "rule_id": "R1"})
    for line in (emergency, buy):
        before = _settlement(line)
        assert with_earlier_sell_notes(before, logged=later, loaded=_LOADED) == before
    # The reason is the template rendered from the settlement's own series, or nothing.
    before = _settlement(_sell(1, WED), reasons=[_no_open(_sell(1, WED), status="backup")])
    assert with_earlier_sell_notes(before, logged=later, loaded=_LOADED) == before


def test_the_s_p_rule_ids_are_the_one_shared_constant() -> None:
    assert SETTLED_SINCE_RULE_IDS == ("S1", "S2", "P1", "P2", "P3")


# --- the real ladder ------------------------------------------------------------------


def test_a_line_stuck_on_a_holiday_carries_n190_i_while_a_later_sell_is_listed(
    tmp_path: Path,
) -> None:
    """[qa-1104] (c): Thursday is a holiday, batch 1's S1 for it never settles.

    Friday evaluates batch 1 again (Decision 7 (i)) and logs a later S1 for it,
    so Thursday's line gets N190-I; ``settle_pending`` -- ``POST /settle`` --
    renders the same settlement without it (N190-C4).
    """
    rig = build(tmp_path, {"2330": S1_CLOSE}, holidays=frozenset({THU}))
    hold_shares(rig, "2330", 1, 2)
    stuck = pending_sell("2330", 1, data_date=WED, execution_date=THU)
    seed_pending(rig.store, stuck)
    rig.warm(["2330"], WED)

    thursday = rig.today(THU, 16)
    assert [line.reason for line in settlement_of(thursday).unsettled] == [
        _no_open(stuck)  # Thursday's own lines are for Thursday: nothing later yet
    ]

    friday = rig.today(FRI, 16)

    (line,) = [item for item in settlement_of(friday).unsettled if item.directive == stuck]
    later = [
        directive
        for directive in friday.directives
        if directive.symbol == "2330" and directive.batch_no == 1
    ]
    assert [(item.rule_id, item.execution_date) for item in later] == [("S1", NEXT_MON)]
    assert line.reason == _no_open(stuck) + _note(*later)
    for position, unsettled in enumerate(settlement_of(friday).unsettled):
        assert settlement_of(friday).warnings[position] == unsettled.reason

    rig.at(FRI, 16, 5)
    plain = rig.desk.settle_pending(today=FRI)
    head = wording.SETTLEMENT_EARLIER_SELL_NOT_DEDUCTED_NOTE.split("{")[0]
    assert stuck in [item.directive for item in plain.unsettled]
    assert all(head not in text for text in plain.warnings)
    assert all(head not in item.reason for item in plain.unsettled)
