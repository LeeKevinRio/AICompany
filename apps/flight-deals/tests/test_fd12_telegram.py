"""Telegram flight details: price alert line and /watch rows (ADR-0002 FD-12 section 7,
section 0 point 3; C-103; PRD #37, #38, #45)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from flight_deals.domain.messages import (
    BANNED_PHRASES,
    COMMAND_REPLY_MAX_CHARS,
    COMMAND_TIME_NOTE,
    COMMAND_WATCH_TIME_NOTE,
    DISCLAIMER,
    CommandPriceRow,
    CommandWatchDetail,
    all_static_texts,
    command_watch_message,
    flight_alert_line,
    flight_command_text,
    price_alert_message,
)
from flight_deals.domain.rules import Candidate
from flight_deals.domain.trip_labels import BOOKING_FALLBACK_NOTE
from tests.conftest import Harness
from tests.test_domain import cand, evaluate

NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)
BR184 = {
    "carrier": "長榮航空",
    "stops": 0,
    "depart_time": "06:50",
    "flight_numbers": "BR184",
    "arrive_time": "10:30",
    "arrive_day_offset": 0,
    "route_airports": "TPE,NRT",
}


def flight(**changes: object) -> Candidate:
    return replace(cand(9500), **{**BR184, **changes})  # type: ignore[arg-type]


# ---- price alert line (#37) -------------------------------------------------------------------


def test_round_trip_alert_line() -> None:
    assert flight_alert_line(flight(), "round_trip") == (
        "   航班：長榮航空 BR 184｜去程 06:50 → 10:30（當地時間，直飛）"
    )


def test_one_way_alert_line_has_no_outbound_label() -> None:
    line = flight_alert_line(flight(), "one_way")
    assert line == "   航班：長榮航空 BR 184｜06:50 → 10:30（當地時間，直飛）"
    assert "去程" not in line


def test_missing_parts_are_left_out_never_dashed() -> None:
    no_arrival = flight(arrive_time=None, arrive_day_offset=None)
    line = flight_alert_line(no_arrival, "one_way")
    assert line == "   航班：長榮航空 BR 184｜06:50 出發（當地時間，直飛）"
    no_number = flight(flight_numbers=None, stops=None)
    assert flight_alert_line(no_number, "round_trip") == (
        "   航班：長榮航空｜去程 06:50 → 10:30（當地時間）"
    )
    next_day = flight(depart_time="23:55", arrive_time="03:30", arrive_day_offset=1, stops=1,
                      flight_numbers="CZ3088,CZ3575", route_airports="TPE,SZX,NRT")  # fmt: skip
    assert flight_alert_line(next_day, "round_trip") == (
        "   航班：長榮航空 CZ 3088 → CZ 3575｜去程 23:55 → 03:30+1（當地時間，轉機 1 次）"
    )
    for line in (flight_alert_line(c, t) for c in (no_arrival, no_number, next_day)
                 for t in ("round_trip", "one_way")):  # fmt: skip
        assert "—" not in line and "None" not in line


def test_legacy_rows_keep_the_old_line_verbatim() -> None:
    assert flight_alert_line(cand(9500), "round_trip") == "   航空公司：X"
    assert flight_alert_line(replace(cand(9500), carrier=None), "one_way") == "   航空公司：未提供"


def test_alert_line_count_is_unchanged() -> None:
    old = price_alert_message(
        watch_name="東京",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        items=evaluate([cand(9500)]),
        links=[None],
    )
    new = price_alert_message(
        watch_name="東京",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        items=evaluate([flight()]),
        links=[None],
    )
    assert len(old.splitlines()) == len(new.splitlines())
    assert "   航空公司：X" in old and "航班：長榮航空 BR 184｜去程 06:50 → 10:30" in new
    assert DISCLAIMER in new and "（1 人總價）" in new and BOOKING_FALLBACK_NOTE in new
    differing = [(a, b) for a, b in zip(old.splitlines(), new.splitlines(), strict=True) if a != b]
    assert len(differing) == 1


def test_scan_alert_carries_the_flight(harness: Harness) -> None:
    harness.source.flight = {k: v for k, v in BR184.items() if k != "carrier"}
    watch_id = harness.create_watch(budget=20000)
    harness.scan(watch_id)
    text = harness.notifier.sent[-1]
    assert "   航班：測試航空 BR 184｜去程 06:50 → 10:30（當地時間，直飛）" in text
    assert "（1 人總價）" in text  # Telegram keeps the note for one person (C-40 (c))


# ---- /watch rows (#38) and footer (#45) --------------------------------------------------------


def row(**changes: object) -> CommandPriceRow:
    base = CommandPriceRow(
        depart_date=date(2026, 12, 10),
        return_date=date(2026, 12, 15),
        amount_minor=950_000,
        currency="TWD",
        carrier="長榮航空",
        stops=0,
        booking_url="https://www.google.com/travel/flights/search?tfs=x",
        booking_note=None,
        fetched_at=NOW,
        depart_time="06:50",
        duration_minutes=220,
        flight_numbers="BR184",
        arrive_time="10:30",
        arrive_day_offset=0,
        route_airports="TPE,NRT",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def test_command_text_round_trip_and_one_way() -> None:
    assert flight_command_text(row(), "round_trip") == "長榮航空 BR 184 去程 06:50→10:30"
    assert flight_command_text(row(), "one_way") == "長榮航空 BR 184 06:50→10:30"
    late = row(arrive_time="03:30", arrive_day_offset=1)
    assert flight_command_text(late, "one_way") == "長榮航空 BR 184 06:50→03:30+1"


def test_command_text_omits_missing_parts_and_keeps_legacy() -> None:
    assert flight_command_text(row(flight_numbers=None), "one_way") == "長榮航空 06:50→10:30"
    no_times = row(depart_time=None, arrive_time=None, arrive_day_offset=None)
    assert flight_command_text(no_times, "round_trip") == "長榮航空 BR 184"
    legacy = row(flight_numbers=None, arrive_time=None, arrive_day_offset=None, route_airports=None)
    assert flight_command_text(legacy, "round_trip") == "長榮航空"
    assert flight_command_text(replace(legacy, carrier=None), "one_way") == "航空公司未提供"


def detail(
    prices: tuple[CommandPriceRow, ...], trip_type: str = "round_trip"
) -> CommandWatchDetail:
    return CommandWatchDetail(
        watch_id=3,
        name="東京",
        status="active",
        origin="TPE",
        destination="NRT",
        trip_type=trip_type,
        dates="固定 2026-12-10 出發，2026-12-15 回程",
        adults=2,
        children=1,
        cabin="business",
        airlines="不限",
        dep_window="不限",
        max_stops="不限",
        budget="TWD 40,000",
        prices=prices,
        last_run=None,
    )


def test_watch_message_rows_and_footer() -> None:
    text = command_watch_message(detail((row(), row(depart_date=date(2026, 12, 11)))))
    assert "｜長榮航空 BR 184 去程 06:50→10:30｜直飛｜查到" in text
    assert COMMAND_WATCH_TIME_NOTE in text and COMMAND_TIME_NOTE not in text
    assert "（2 大 1 小總價）" in text and DISCLAIMER in text and "查票連結：" in text


LONG_NAME = "測試航空" * 6


@pytest.mark.parametrize(
    "prices",
    [
        # Six segments of flight numbers.
        tuple(
            row(
                flight_numbers="BR1001,BR1002,BR1003,BR1004,BR1005,BR1006",
                route_airports="TPE,HKG,BKK,SIN,KUL,MNL,NRT",
                stops=5,
            )
            for _ in range(3)
        ),
        # The longest airline names.
        tuple(row(carrier=f"{LONG_NAME}、{LONG_NAME}、{LONG_NAME}") for _ in range(3)),
        # Fallback links with the Telegram note.
        tuple(
            row(
                booking_url="https://www.google.com/travel/flights?hl=zh-TW&curr=TWD&q="
                + "Flights%20to%20NRT%20from%20TPE%20on%202026-12-10%20through%202026-12-15",
                booking_note=BOOKING_FALLBACK_NOTE,
                carrier=LONG_NAME,
                flight_numbers="BR1001,BR1002,BR1003,BR1004,BR1005,BR1006",
            )
            for _ in range(3)
        ),
    ],
    ids=["six-segments", "long-airline", "fallback-note"],
)
def test_longest_watch_replies_fit(prices: tuple[CommandPriceRow, ...]) -> None:
    text = command_watch_message(detail(prices))
    assert len(text) <= COMMAND_REPLY_MAX_CHARS
    assert text.count("（2 大 1 小總價）") == 3  # every row shown, each with its note
    assert DISCLAIMER in text and COMMAND_WATCH_TIME_NOTE in text


def test_watch_command_reply_uses_stored_flight(harness: Harness) -> None:
    harness.source.flight = {k: v for k, v in BR184.items() if k != "carrier"}
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    commands = harness.services.commands
    assert commands is not None
    watch = harness.repo.get_watch(watch_id)
    text = commands.watch_text(watch, harness.clock())
    assert "｜測試航空 BR 184 去程 06:50→10:30｜直飛｜" in text
    assert COMMAND_WATCH_TIME_NOTE in text
    list_text = commands.list_text(harness.clock())
    assert COMMAND_TIME_NOTE in list_text and COMMAND_WATCH_TIME_NOTE not in list_text


def test_new_telegram_wording_passes_the_policy() -> None:
    texts = [
        *all_static_texts(),
        flight_alert_line(flight(), "round_trip"),
        flight_command_text(row(), "round_trip"),
    ]
    assert COMMAND_WATCH_TIME_NOTE in texts
    assert [t for t in texts for p in BANNED_PHRASES if p in t] == []


def test_round_trip_alert_without_times_has_no_lone_outbound_label() -> None:
    no_times = flight(depart_time=None, arrive_time=None, arrive_day_offset=None)
    line = flight_alert_line(no_times, "round_trip")
    assert line == "   航班：長榮航空 BR 184（直飛）"
    assert "去程" not in line
    assert flight_command_text(row(depart_time=None, arrive_time=None, arrive_day_offset=None),
                               "round_trip") == "長榮航空 BR 184"  # fmt: skip


def _price_line(text: str) -> str:
    (line,) = [ln for ln in text.splitlines() if ln.startswith("1. ")]
    return line


def test_watch_row_with_all_new_fields_null_is_the_old_line_verbatim() -> None:
    legacy = row(flight_numbers=None, arrive_time=None, arrive_day_offset=None, route_airports=None)
    line = _price_line(command_watch_message(detail((legacy,))))
    # The pre-FD-12 format: "{n}. {dates} {money}{note}｜{carrier}｜{stops}｜查到 {time}".
    assert line == "1. 12/10–12/15 TWD 9,500（2 大 1 小總價）｜長榮航空｜直飛｜查到 10-25 12:00"


@pytest.mark.parametrize(
    "changes",
    [
        {"arrive_time": None, "arrive_day_offset": None, "depart_time": None},  # numbers only
        {"flight_numbers": None, "carrier": None, "route_airports": None},  # times only
    ],
    ids=["numbers-only", "times-only"],
)
def test_watch_row_with_partial_details_has_no_dash_or_none(changes: dict[str, object]) -> None:
    line = _price_line(command_watch_message(detail((row(**changes),))))
    assert "—" not in line and "None" not in line
    assert line.startswith("1. 12/10–12/15 TWD 9,500（2 大 1 小總價）｜")
