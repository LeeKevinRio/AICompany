"""歸屬語 (風控 R2) and the 情境 1 blocking path, through the wired service.

覆審裁決 (2026-08-12) settled three states and this file pins all of them:

* **情境 1 -- no user record.** The 歸屬語 is not shown at all and the module
  produces no executable directive. The verdict comes from an explicit record,
  never from a date: a system default carries an effective date too, and reading
  authorship out of one would put the user's name on rules they never wrote.
* **情境 2 -- record present, date unreadable.** The sentence is the full one
  with the single permitted status string in place of the date.
* **The normal case.** The date is the 規則版本生效日 and nothing else.

The escape hatch is deliberately outside the gate (CEO EX-2/EX-4): its lines
come from an action the user just submitted, and a precondition on the exit is
the one thing the exit may not have.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook import wording
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore, system_default_params
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import RULE_SET_DATE, TUESDAY, confirm_rule_set

SERIES_END = date(2026, 8, 14)
HISTORY = 40


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    prices = FakePriceService()
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(
        cash=Decimal("1000000"), total_deploy=Decimal("1000000"), source="initial"
    )
    yield Harness(
        service=PlaybookService(
            store=store,
            market_resolver={"TW": prices},
            index_resolver={"TW": index, "US": index},
        ),
        store=store,
    )


def _hold_a_batch(store: PlaybookStore) -> None:
    batch = store.get_batch("2330", 1)
    assert batch is not None
    store.save_batch(
        batch.model_copy(
            update={
                "status": "open",
                "entry_date": date(2026, 7, 1),
                "cost": Decimal("100"),
                "shares": 300,
                "remaining_shares": 300,
                "peak_close": Decimal("100"),
            }
        )
    )


# --- 情境 1: 無使用者紀錄 -----------------------------------------------------


def test_without_a_confirmed_rule_set_no_directive_is_produced(
    harness: Harness,
) -> None:
    """定稿: 在你確認規則集之前不產生任何指令."""
    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.directives == []
    assert evaluation.attribution == wording.ATTRIBUTION_NO_USER_RULES
    assert evaluation.mode_reason == wording.ATTRIBUTION_NO_USER_RULES
    # 阻斷是「不產生」，不是「產生了但不顯示」：指令留存也必須是空的 (R16).
    assert harness.store.directive_log() == []


def test_the_block_lifts_the_moment_the_user_confirms_the_rule_set(
    harness: Harness,
) -> None:
    confirm_rule_set(harness.store)

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert [item.rule_id for item in evaluation.directives] == ["R1"]
    assert evaluation.attribution == (
        f"此指令是你於 {RULE_SET_DATE.isoformat()} 自行設定的規則之機械執行結果，"
        "非本系統的判斷或建議。"
    )


def test_authorship_is_a_flag_and_not_an_inference_from_a_date(
    harness: Harness,
) -> None:
    """判定用明確旗標，不得由日期反推：預設參數集同樣帶著一個生效日."""
    default = system_default_params(TUESDAY)
    assert default.effective_date == TUESDAY  # 預設值也有日期
    assert harness.store.active_params(TUESDAY) == default  # fallback 仍可算數
    assert harness.store.rule_set_authorship(TUESDAY).user_authored is False


def test_a_submitted_rule_change_counts_as_an_authorship_record(
    harness: Harness,
) -> None:
    """「尚無你本人的設定或修改紀錄」：修改紀錄同樣是本人紀錄."""
    from app.playbook.service import request_rule_change
    from tests import playbook_helpers as helper

    request_rule_change(
        store=harness.store,
        calendar=helper.calendar(),
        changes={"s1_ratio": Decimal("0.95")},
        submitted_at=date(2026, 1, 5),
    )

    assert harness.store.rule_set_authorship(TUESDAY).user_authored is True


# --- 情境 2: 有紀錄、日期讀不到 -----------------------------------------------


def test_an_unreadable_effective_date_falls_back_to_the_status_sentence(
    harness: Harness,
) -> None:
    confirmed = confirm_rule_set(harness.store)
    with sqlite3.connect(harness.store.db_path) as conn:
        conn.execute("UPDATE playbook_rule_params SET effective_date = 'n/a'")

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    assert evaluation.attribution == (
        "此指令是你自行設定的規則之機械執行結果，非本系統的判斷或建議"
        f"（規則設定日期缺漏：規則版本 {confirmed.version} 的生效日期讀取失敗）。"
    )
    # 仍然是有紀錄的狀態，指令照常產生，阻斷句不得出現。
    assert evaluation.directives
    assert wording.ATTRIBUTION_NO_USER_RULES not in evaluation.attribution


# --- 出口不受閘門限制 ---------------------------------------------------------


def test_the_emergency_exit_is_not_gated_on_the_rule_set_confirmation(
    harness: Harness,
) -> None:
    """EX-2/EX-4: 出口零摩擦——指令來自使用者剛提交的動作，不是系統代持的規則."""
    _hold_a_batch(harness.store)

    result = harness.service.emergency_exit(today=TUESDAY)

    assert result.total_shares == 300
    assert [item.action for item in result.directives] == ["sell"]
    assert result.attribution == wording.ATTRIBUTION_NO_USER_RULES


def test_the_exit_line_carries_its_own_no_band_sentence(harness: Harness) -> None:
    """定稿: service 的 EXIT 指令不得再掛停損句."""
    confirm_rule_set(harness.store)
    _hold_a_batch(harness.store)

    result = harness.service.emergency_exit(today=TUESDAY)

    (directive,) = result.directives
    assert directive.limit_note == wording.EMERGENCY_EXIT_NO_BAND_NOTE
    assert directive.limit_note != wording.STOP_LOSS_NO_BAND_NOTE
    assert "S/P 系列停損停利仍照常評估。" in directive.rule_summary


def test_the_exit_mode_line_is_rendered_for_today_not_stored(
    harness: Harness,
) -> None:
    """mode_reason 禁存快照字串：出口回報的模式句是當天算出來的第 1 個交易日."""
    confirm_rule_set(harness.store)
    _hold_a_batch(harness.store)

    result = harness.service.emergency_exit(today=TUESDAY)

    assert "第 1/20 交易日" in result.mode_reason
    assert result.mode_reason != result.message
    # The stored log keeps the instruction, never the day counter as a fact.
    assert all("第 1/20" not in str(row) for row in harness.store.directive_log())
