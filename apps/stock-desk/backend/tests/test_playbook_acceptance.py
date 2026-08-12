"""驗收測試 T1-T9, transcribed one for one from the plan and CEO's rulings.

Each test names the acceptance case it implements and asserts the exact
condition that case states. Where a case has sub-cases (T1 a/b/c, T4 a/b/c) they
are separate tests so a failure names the sub-case.

Sources: 企劃 §7 (T1-T6) and 裁決紀錄 (T7 凍結期間仍須停損, T8 依據資料日欄位,
T9 開盤超出 +2% 不追價).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.playbook.engine import evaluate, settle_directive
from app.playbook.models import (
    BatchState,
    Directive,
    FastMarketState,
    IndexSnapshot,
    MarketSnapshot,
    PlaybookEvaluation,
    PortfolioState,
    RuleParams,
    SymbolState,
)
from app.playbook.service import request_rule_change
from app.playbook.store import PlaybookStore
from tests import playbook_helpers as helper
from tests.playbook_helpers import FRIDAY, TUESDAY, WEDNESDAY


def run(
    *,
    markets: dict[str, MarketSnapshot] | None = None,
    batches: list[BatchState] | None = None,
    portfolio: PortfolioState | None = None,
    index: IndexSnapshot | None = None,
    data_date: date = TUESDAY,
    symbols: dict[str, SymbolState] | None = None,
    rule_params: RuleParams | None = None,
) -> PlaybookEvaluation:
    """Evaluate one day with the fixed test calendar and sensible defaults."""
    return evaluate(
        data_date=data_date,
        calendar=helper.calendar(),
        params=rule_params if rule_params is not None else helper.params(),
        index=index if index is not None else helper.index(data_date=data_date),
        markets=markets or {},
        batches=batches or [],
        symbols=symbols or {},
        portfolio=portfolio if portfolio is not None else helper.portfolio(),
    )


def rule_ids(evaluation: PlaybookEvaluation) -> list[str]:
    return [directive.rule_id for directive in evaluation.directives]


def effect_kinds(evaluation: PlaybookEvaluation) -> list[str]:
    return [effect.kind for effect in evaluation.effects]


# --- T1 停損 ---------------------------------------------------------------


def test_t1a_single_batch_below_cost_times_090_sells_that_batch_and_pauses() -> None:
    """T1(a): 單批收盤 < 成本×0.90 -> 出該批賣出指令 + 該標的排程暫停."""
    evaluation = run(
        markets={"2330": helper.market(close="89", ma25="100")},
        batches=[helper.batch(cost="100", shares=300)],
    )
    (directive,) = [item for item in evaluation.directives if item.rule_id == "S1"]
    assert directive.action == "sell"
    assert directive.shares == 300
    assert "pause_symbol" in effect_kinds(evaluation)
    # 停損指令不設滑價帶，T+1 開盤市價執行 (CEO 裁決七).
    assert directive.limit_low is None and directive.limit_high is None


def test_t1b_symbol_below_average_cost_times_085_liquidates_and_blacklists() -> None:
    """T1(b): 整檔均收盤 < 均成本×0.85 -> 出清整檔 + 進黑名單 60 交易日."""
    evaluation = run(
        markets={"2330": helper.market(close="84", ma25="100")},
        batches=[
            helper.batch(batch_no=1, cost="100", shares=300),
            helper.batch(batch_no=2, cost="100", shares=300),
        ],
    )
    (directive,) = [item for item in evaluation.directives if item.rule_id == "S2"]
    assert directive.shares == 600
    assert directive.batch_no is None
    blacklist = [effect for effect in evaluation.effects if effect.kind == "blacklist"]
    assert blacklist and blacklist[0].value == 60
    # S2 outranks S1: only one line comes out for the symbol.
    assert rule_ids(evaluation) == ["S2"]


def test_t1c_portfolio_unrealized_below_minus_8_freezes_and_allows_only_sells() -> None:
    """T1(c): 組合新倉未實現 < -8% -> 全組合凍結 10 日 + 僅產生賣出類指令."""
    evaluation = run(
        markets={
            "2330": helper.market(close="91", ma25="100"),
            "2454": helper.market("2454", close="91", ma25="100"),
        },
        batches=[
            helper.batch(cost="100", shares=300),
            helper.batch("2454", batch_no=1, status="planned", cost=None, shares=0),
        ],
    )
    assert evaluation.mode == "frozen"
    freeze = [effect for effect in evaluation.effects if effect.kind == "freeze_portfolio"]
    assert freeze and freeze[0].value == 10
    assert all(directive.action == "sell" for directive in evaluation.directives)
    assert "buy" not in [directive.action for directive in evaluation.directives]


# --- T2 順延 ---------------------------------------------------------------


def test_t2_change_above_3pct_defers_and_counts() -> None:
    """T2: 排程日漲幅 >3% -> 順延指令，順延計數 +1."""
    evaluation = run(
        markets={"2330": helper.market(close="105", change_pct="3.5", bias25="2")},
        batches=[helper.planned()],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "R2"
    assert directive.action == "defer"
    increments = [effect for effect in evaluation.effects if effect.kind == "defer_increment"]
    assert increments and increments[0].value == 1


def test_t2_bias_above_10pct_also_defers() -> None:
    """T2: BIAS25 >+10% 同樣順延（兩個條件任一成立）."""
    evaluation = run(
        markets={"2330": helper.market(close="105", change_pct="1", bias25="10.5")},
        batches=[helper.planned()],
    )
    assert rule_ids(evaluation) == ["R2"]


def test_t2_third_deferral_produces_a_skip() -> None:
    """T2: 累計達 3 次時產生「跳過」指令（R3）."""
    evaluation = run(
        markets={"2330": helper.market(close="105", change_pct="3.5", bias25="2")},
        batches=[helper.planned(defer_count=2)],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "R3"
    assert directive.action == "skip"
    assert "batch_skipped" in effect_kinds(evaluation)


# --- T3 防守 ---------------------------------------------------------------


def test_t3_index_below_monthly_line_three_days_enters_defense_and_freezes_entries() -> None:
    """T3: 指數 < 月線連 3 日 -> 防守模式、凍結排程."""
    evaluation = run(
        index=helper.index(close="18000", monthly_line="19000", days_below=3),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    assert evaluation.mode == "defense"
    assert "defense_on" in effect_kinds(evaluation)
    assert evaluation.directives == []


def test_t3_defense_tightens_s1_to_093_and_trails_profitable_batches() -> None:
    """T3: 防守模式下 S1 收緊為 0.93、獲利部位套移動停利."""
    evaluation = run(
        index=helper.index(close="18000", monthly_line="19000", days_below=3),
        markets={
            "2330": helper.market(close="92", ma25="100"),
            "2454": helper.market("2454", close="110", ma25="105"),
        },
        batches=[
            helper.batch(cost="100", shares=300),
            helper.batch("2454", cost="100", shares=300, peak="115"),
        ],
    )
    # 92 sits above the normal 0.90 threshold and below the defense 0.93 one.
    assert rule_ids(evaluation) == ["S1"]
    assert any(
        effect.kind == "trailing_on" and effect.symbol == "2454"
        for effect in evaluation.effects
    )


def test_t3_index_back_above_monthly_line_releases_defense() -> None:
    """T3: 站回月線後模式解除."""
    evaluation = run(
        index=helper.index(close="19500", monthly_line="19000", days_below=0),
        portfolio=helper.portfolio(defense_active=True),
        markets={"2330": helper.market(close="100")},
        batches=[helper.planned()],
    )
    assert "defense_off" in effect_kinds(evaluation)
    assert evaluation.mode == "normal"


# --- T4 停利 ---------------------------------------------------------------


def test_t4a_close_at_120pct_of_cost_sells_one_third() -> None:
    """T4(a): 收盤 ≥ 成本×1.20 -> 賣 1/3."""
    evaluation = run(
        markets={"2330": helper.market(close="120", ma25="110", bias25="5")},
        batches=[helper.batch(cost="100", shares=300)],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "P1"
    assert directive.shares == 100
    assert "p1_done" in effect_kinds(evaluation)


def test_t4b_close_at_135pct_sells_another_third_and_turns_on_the_trailing_stop() -> None:
    """T4(b): 收盤 ≥ 成本×1.35 -> 再賣 1/3 + 餘轉移動停利."""
    evaluation = run(
        markets={"2330": helper.market(close="135", ma25="120", bias25="5")},
        batches=[helper.batch(cost="100", shares=300, remaining=200, p1_done=True)],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "P2"
    assert directive.shares == 100
    assert "trailing_on" in effect_kinds(evaluation)


def test_t4b_trailing_stop_liquidates_the_remainder_below_the_peak() -> None:
    """T4(b) 續：移動停利跌破波段高 ×0.88 出清餘額."""
    evaluation = run(
        markets={"2330": helper.market(close="120", ma25="115", bias25="4")},
        batches=[
            helper.batch(
                cost="100", shares=300, remaining=100, p1_done=True, p2_done=True,
                trailing=True, peak="140",
            )
        ],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "P2"
    assert directive.shares == 100
    assert "batch_closed" in effect_kinds(evaluation)


def test_t4c_bias_above_15pct_forces_a_one_third_reduction() -> None:
    """T4(c): BIAS25 >+15% -> 強制減 1/3."""
    evaluation = run(
        markets={"2330": helper.market(close="118", ma25="100", bias25="18")},
        batches=[helper.batch(cost="100", shares=300, remaining=300)],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "P3"
    assert directive.shares == 100
    assert "p3_marked" in effect_kinds(evaluation)


def test_t4c_high_volatility_list_uses_the_20pct_threshold() -> None:
    """T4(c): 高波動清單的門檻是 +20%，18% 不觸發（改由 P1 判斷）."""
    evaluation = run(
        markets={
            "2330": helper.market(close="118", ma25="100", bias25="18", high_volatility=True)
        },
        batches=[helper.batch(cost="100", shares=300)],
    )
    assert "P3" not in rule_ids(evaluation)


def test_t4c_p3_fires_at_most_once_per_10_trading_days() -> None:
    """T4(c): 每 10 交易日限一次."""
    evaluation = run(
        markets={"2330": helper.market(close="118", ma25="100", bias25="18")},
        batches=[helper.batch(cost="100", shares=300, p3_last=date(2026, 8, 6))],
    )
    assert "P3" not in rule_ids(evaluation)


# --- T5 拒絕求情 -----------------------------------------------------------


def test_t5_rule_change_is_never_effective_today(tmp_path: Path) -> None:
    """T5: 盤中修改規則 -> 拒絕即時生效、記錄待審核、標記次日生效日期."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    receipt = request_rule_change(
        store=store,
        calendar=helper.calendar(),
        changes={"s1_ratio": Decimal("0.95")},
        submitted_at=TUESDAY,
    )
    assert receipt.accepted_immediately is False
    assert receipt.status == "pending"
    assert receipt.effective_date == WEDNESDAY
    # Today still runs on the old version; tomorrow's evaluation picks up the new one.
    assert store.active_params(TUESDAY).s1_ratio == Decimal("0.90")
    assert store.active_params(WEDNESDAY).s1_ratio == Decimal("0.95")
    assert store.pending_rule_changes(TUESDAY)[0].version == receipt.version


def test_t5_fast_market_states_the_volatility_and_does_not_relax(tmp_path: Path) -> None:
    """CEO 裁決六：快市期間拒絕回覆附當前波動率數據與本條說明."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    receipt = request_rule_change(
        store=store,
        calendar=helper.calendar(),
        changes={"s1_ratio": Decimal("0.95")},
        submitted_at=TUESDAY,
        fast_market_vol=41.2,
        fast_market_moves=3,
    )
    assert "快市" in receipt.message
    assert "41.2" in receipt.message
    assert receipt.effective_date == WEDNESDAY


# --- T6 縮批 ---------------------------------------------------------------


def test_t6_entry_is_shrunk_so_cash_stays_at_or_above_30pct() -> None:
    """T6: 現金比例即將跌破 30% -> 該批股數依縮批公式縮減."""
    evaluation = run(
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
        portfolio=helper.portfolio(cash="50000", total_deploy="1000000"),
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "R1"
    # planned = floor(1,000,000/5/3 / 100) = 666; budget = 50,000 - 30% x 50,000
    # = 35,000 -> 350 股, and 350 x 100 leaves exactly the 30% floor.
    assert directive.shares == 350
    assert any("縮減" in warning for warning in evaluation.warnings)


def test_t6_entry_is_dropped_when_nothing_fits_above_the_cash_floor() -> None:
    """T6 邊界：縮到 0 股時不發出「0 股」指令，改為說明本批不進場."""
    evaluation = run(
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
        portfolio=helper.portfolio(cash="0", total_deploy="1000000"),
    )
    assert evaluation.directives == []
    assert any("本批不進場" in warning for warning in evaluation.warnings)


def test_t6_full_allocation_when_cash_is_ample() -> None:
    """CEO 裁決二：BATCH_AMOUNT = TOTAL_DEPLOY / 5 / 3，floor 到整股."""
    evaluation = run(
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    (directive,) = evaluation.directives
    assert directive.shares == 666


def test_last_batch_absorbs_the_rounding_remainder() -> None:
    """CEO 裁決二：差額由該檔末批吸收."""
    evaluation = run(
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[
            helper.batch(batch_no=1, cost="100", shares=666),
            helper.batch(batch_no=2, cost="100", shares=666),
            helper.planned(batch_no=3),
        ],
    )
    (directive,) = [item for item in evaluation.directives if item.rule_id == "R1"]
    # floor(200,000/100) = 2,000 shares for the symbol; 2,000 - 666 - 666 = 668.
    assert directive.shares == 668


# --- T7 凍結期間仍須停損 (CEO 裁決五) --------------------------------------


def test_t7_stop_loss_fires_on_day_four_of_an_s3_freeze() -> None:
    """T7: S3 凍結第 4 日某批跌破 0.90 -> 必須輸出 S1 賣出指令.

    「凍結中不動作」 is the failure condition this test exists to catch.
    """
    evaluation = run(
        data_date=date(2026, 8, 11),  # the fourth trading day of the freeze
        markets={"2330": helper.market(close="89", ma25="100")},
        batches=[helper.batch(cost="100", shares=300), helper.planned("2454", 1)],
        portfolio=helper.portfolio(
            freeze_until=date(2026, 8, 19), freeze_reason="S3 組合熔斷"
        ),
    )
    assert evaluation.mode == "frozen"
    sells = [item for item in evaluation.directives if item.rule_id == "S1"]
    assert sells and sells[0].action == "sell" and sells[0].shares == 300
    # The freeze still suppresses the R series and nothing else.
    assert "R1" not in rule_ids(evaluation)


def test_t7_take_profit_also_survives_a_freeze() -> None:
    """CEO 裁決五：S／P 系列任何模式下永遠活躍."""
    evaluation = run(
        markets={"2330": helper.market(close="121", ma25="110", bias25="5")},
        batches=[helper.batch(cost="100", shares=300)],
        portfolio=helper.portfolio(
            freeze_until=date(2026, 8, 19), freeze_reason="S3 組合熔斷"
        ),
    )
    assert rule_ids(evaluation) == ["P1"]


# --- T8 每筆指令的時序欄位 (CEO 裁決七) ------------------------------------


def test_t8_every_directive_carries_data_date_execution_date_and_reference_price() -> None:
    """T8: 缺依據資料日欄位 = 失敗."""
    evaluation = run(
        markets={
            "2330": helper.market(close="89", ma25="100"),
            "2454": helper.market("2454", close="100", change_pct="0", bias25="0"),
        },
        batches=[helper.batch(cost="100", shares=300), helper.planned("2454", 1)],
    )
    assert evaluation.directives
    for directive in evaluation.directives:
        assert directive.data_date == TUESDAY
        assert directive.execution_date == WEDNESDAY
        assert directive.reference_price is not None


def test_t8_the_rendered_line_shows_the_data_date_and_the_rule_id() -> None:
    from app.playbook.wording import directive_line

    evaluation = run(
        markets={"2330": helper.market(close="89", ma25="100")},
        batches=[helper.batch(cost="100", shares=300)],
    )
    line = directive_line(evaluation.directives[0])
    assert "依據資料日 2026-08-11" in line
    assert "預定執行日 2026-08-12" in line
    assert "規則 S1" in line


def test_t8_non_stop_loss_lines_carry_the_two_percent_band() -> None:
    evaluation = run(
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    (directive,) = evaluation.directives
    assert directive.limit_low == Decimal("98.00")
    assert directive.limit_high == Decimal("102.00")


# --- T9 MISSED 不追價 (CEO 裁決七) ------------------------------------------


def _entry_directive() -> Directive:
    evaluation = run(
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    return evaluation.directives[0]


def test_t9_open_above_the_band_is_marked_missed() -> None:
    """T9: 開盤超出 +2% -> MISSED，不追價."""
    settled = settle_directive(_entry_directive(), open_price=Decimal("103"))
    assert settled.status == "missed"


def test_t9_open_inside_the_band_is_executed() -> None:
    settled = settle_directive(_entry_directive(), open_price=Decimal("101.5"))
    assert settled.status == "executed"


def test_t9_stop_loss_has_no_band_and_always_executes() -> None:
    """停損指令不設滑價帶，T+1 開盤無條件市價執行."""
    evaluation = run(
        markets={"2330": helper.market(close="89", ma25="100")},
        batches=[helper.batch(cost="100", shares=300)],
    )
    settled = settle_directive(evaluation.directives[0], open_price=Decimal("70"))
    assert settled.status == "executed"


def test_t9_a_missed_entry_leaves_the_book_untouched(tmp_path: Path) -> None:
    """MISSED 次日重評：批次仍是 planned，沒有股數也沒有成本."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    store.ensure_batches(["2330"], batches_per_target=3)
    directive = _entry_directive()
    store.settle(settle_directive(directive, open_price=Decimal("103")))
    batch = store.get_batch("2330", 1)
    assert batch is not None
    assert batch.status == "planned"
    assert batch.remaining_shares == 0


def test_a_filled_entry_opens_the_batch(tmp_path: Path) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    store.ensure_batches(["2330"], batches_per_target=3)
    store.settle(settle_directive(_entry_directive(), open_price=Decimal("100")))
    batch = store.get_batch("2330", 1)
    assert batch is not None
    assert batch.status == "open"
    assert batch.remaining_shares == 666


# --- 邊界：資料缺漏 (鐵律⑤ / 風控 R5, R6) ----------------------------------


def test_stale_data_produces_no_directive_for_that_symbol() -> None:
    evaluation = run(
        markets={"2330": helper.market(close="89", ma25="100", status="cached_stale")},
        batches=[helper.batch(cost="100", shares=300)],
    )
    assert evaluation.directives == []
    assert any("cached_stale" in warning for warning in evaluation.warnings)


def test_unavailable_data_produces_no_directive_for_that_symbol() -> None:
    evaluation = run(
        markets={},
        batches=[helper.batch(cost="100", shares=300)],
    )
    assert evaluation.directives == []
    assert any("unavailable" in warning for warning in evaluation.warnings)


def test_demo_data_never_produces_an_executable_directive() -> None:
    from app.demo.series import DEMO_SOURCE

    evaluation = run(
        markets={"2330": helper.market(close="89", ma25="100", source=DEMO_SOURCE)},
        batches=[helper.batch(cost="100", shares=300)],
    )
    assert evaluation.directives == []
    assert any(DEMO_SOURCE in warning for warning in evaluation.warnings)


def test_missing_index_keeps_the_previous_mode_and_defers_the_entry() -> None:
    """企劃 §9.4 + M1-1：大盤資料缺漏時沿用前態，且 R 系列為「順延」不是靜默跳過."""
    evaluation = run(
        index=helper.index(status="unavailable", source="none"),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "M1"
    assert directive.action == "defer"
    assert "M1 今日未評估" in directive.rule_summary
    increments = [effect for effect in evaluation.effects if effect.kind == "defer_increment"]
    assert increments and increments[0].value == 1
    assert "buy" not in [item.action for item in evaluation.directives]
    assert any("加權指數" in warning for warning in evaluation.warnings)


def test_three_index_gap_deferrals_escalate_to_an_r3_skip() -> None:
    """M1-1：指數缺漏的順延吃的是同一個 R3 計數，第 3 次照樣跳過，不會無限順延."""
    evaluation = run(
        index=helper.index(status="cached_stale", source="cache"),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned(defer_count=2)],
    )
    (directive,) = evaluation.directives
    assert directive.rule_id == "R3"
    assert directive.action == "skip"
    assert "batch_skipped" in effect_kinds(evaluation)


def test_a_stale_index_never_enters_the_fast_market_for_the_first_time() -> None:
    """FM-1：快市判定沿用前態，資料缺漏不得成為首次進入快市的理由."""
    evaluation = run(
        # Numbers that *would* fire the test if they were usable at all.
        index=helper.index(status="cached_stale", source="cache", vol=45.0, large_moves=4),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    assert evaluation.fast_market.active is False
    assert evaluation.fast_market.carried_forward is True
    # 覆審: 沒有前次判定可沿用時說的是「尚無前一次快市判定可沿用」，不是假裝沿用了什麼。
    assert any("尚無前一次快市判定可沿用" in warning for warning in evaluation.warnings)
    assert any("不會使系統首次進入快市" in warning for warning in evaluation.warnings)


def test_a_stale_index_carries_an_active_fast_market_forward() -> None:
    """沿用是雙向的：前一日判定為快市時，資料缺漏不會讓它自動解除."""
    previous = FastMarketState(
        active=True,
        annualized_vol_20d=41.2,
        large_move_days=3,
        reason="前一日判定",
        measured_on=date(2026, 8, 10),
    )
    evaluation = evaluate(
        data_date=TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=helper.index(status="unavailable", source="none"),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
        symbols={},
        portfolio=helper.portfolio(),
        previous_fast_market=previous,
    )
    assert evaluation.fast_market.active is True
    assert evaluation.fast_market.carried_forward is True
    assert evaluation.fast_market.measured_on == date(2026, 8, 10)
    assert any("2026-08-10" in warning for warning in evaluation.warnings)


def test_a_usable_index_measures_the_fast_market_and_dates_it() -> None:
    evaluation = run(
        index=helper.index(vol=45.0, large_moves=4),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    assert evaluation.fast_market.active is True
    assert evaluation.fast_market.carried_forward is False
    assert evaluation.fast_market.measured_on == TUESDAY


def test_the_persisted_fast_market_verdict_survives_a_gap(tmp_path: Path) -> None:
    """FM-1 的「持久化」半邊：狀態存在 playbook_state，跨日讀得回來."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    assert store.fast_market_state() is None
    measured = FastMarketState(
        active=True, annualized_vol_20d=41.2, large_move_days=3, reason="快市"
    )
    store.save_fast_market(measured, measured_on=TUESDAY)

    restored = store.fast_market_state()
    assert restored is not None
    assert restored.active is True
    assert restored.annualized_vol_20d == 41.2
    assert restored.measured_on == TUESDAY

    # A carried verdict is not a measurement, so it does not move the date.
    store.save_fast_market(
        restored.model_copy(update={"carried_forward": True}), measured_on=FRIDAY
    )
    assert store.fast_market_state().measured_on == TUESDAY  # type: ignore[union-attr]


# --- 文案：停損失效條件與參考價揭露 (風控 E-1 / R17) ------------------------


def test_the_stop_loss_note_states_when_a_market_order_does_not_fill() -> None:
    """E-1：停損文案禁成交保證，必須附市價單失效條件."""
    from app.playbook import wording

    evaluation = run(
        markets={"2330": helper.market(close="89", ma25="100")},
        batches=[helper.batch(cost="100", shares=300)],
    )
    (directive,) = evaluation.directives
    assert "跌停或無量時可能無法成交" in directive.limit_note
    assert "無條件" not in directive.limit_note
    assert wording.STOP_LOSS_NO_BAND_NOTE == directive.limit_note


def test_every_rendered_line_says_the_reference_price_is_not_intraday() -> None:
    """R17：指令說明附「不反映今日盤中變動」."""
    from app.playbook.wording import directive_line

    evaluation = run(
        markets={
            "2330": helper.market(close="89", ma25="100"),
            "2454": helper.market("2454", close="100", change_pct="0", bias25="0"),
        },
        batches=[helper.batch(cost="100", shares=300), helper.planned("2454", 1)],
    )
    assert evaluation.directives
    for directive in evaluation.directives:
        assert "不反映今日盤中變動" in directive_line(directive)


def test_a_non_schedule_day_produces_no_entry_but_still_evaluates_stops() -> None:
    evaluation = run(
        data_date=FRIDAY,
        markets={
            "2330": helper.market(close="89", ma25="100", data_date=FRIDAY),
            # A profitable second holding keeps the portfolio above the S3
            # threshold, so this test measures the schedule day and nothing else.
            "2454": helper.market("2454", close="110", ma25="100", change_pct="0",
                                  bias25="0", data_date=FRIDAY),
        },
        batches=[
            helper.batch(cost="100", shares=300),
            helper.batch("2454", batch_no=1, cost="100", shares=300),
            helper.planned("2454", 2),
        ],
    )
    assert evaluation.is_schedule_day is False
    assert rule_ids(evaluation) == ["S1"]
    assert any("非排程日" in warning for warning in evaluation.warnings)


def test_a_blacklisted_symbol_gets_no_entry() -> None:
    evaluation = run(
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
        symbols={"2330": SymbolState(symbol="2330", blacklisted=True)},
    )
    assert evaluation.directives == []


def test_standing_back_above_ma25_resumes_the_symbol_and_zeroes_the_counter() -> None:
    """CEO 裁決三：S1 恢復後順延計數歸零."""
    evaluation = run(
        markets={"2330": helper.market(close="101", ma25="100", change_pct="0", bias25="1")},
        batches=[helper.planned(defer_count=2)],
        symbols={"2330": SymbolState(symbol="2330", paused=True, paused_since=date(2026, 7, 1))},
    )
    assert "resume_symbol" in effect_kinds(evaluation)
    assert "defer_reset" in effect_kinds(evaluation)
    # Resumed on the same day, so the entry rule may run again immediately.
    assert "R1" in rule_ids(evaluation)


# --- 文案閘門覆審 (2026-08-12 二輪定稿) 的引擎行為 --------------------------


def test_the_index_gap_deferral_clause_only_appears_on_a_deferring_day() -> None:
    """覆審 INDEX_DATA_GAP 拆句：順延子句以行為為準，不是主句的一部分."""
    deferring = run(
        index=helper.index(status="unavailable", source="none"),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0")},
        batches=[helper.planned()],
    )
    assert any("當日不新開倉。" in warning for warning in deferring.warnings)
    assert any(
        "R 系列進場改為順延並計入順延次數" in warning for warning in deferring.warnings
    )

    quiet_day = run(
        data_date=FRIDAY,  # 非排程日：今天本來就沒有進場要順延
        index=helper.index(status="unavailable", source="none", data_date=FRIDAY),
        markets={"2330": helper.market(close="100", change_pct="0", bias25="0",
                                       data_date=FRIDAY)},
        batches=[helper.planned()],
    )
    assert any("當日不新開倉。" in warning for warning in quiet_day.warnings)
    assert not any(
        "R 系列進場改為順延並計入順延次數" in warning for warning in quiet_day.warnings
    )


def test_a_held_symbol_with_no_data_says_the_stop_loss_was_not_evaluated() -> None:
    """S-2：資料缺漏致停損無法評估須主動顯著揭露，不得靜默."""
    holding = run(
        markets={"2330": helper.market(close="100", status="cached_stale", source="cache")},
        batches=[helper.batch(cost="100", shares=300)],
    )
    assert holding.directives == []
    assert any("【停損今日無法評估】" in warning for warning in holding.warnings)

    empty = run(
        markets={"2330": helper.market(close="100", status="cached_stale", source="cache")},
        batches=[helper.planned()],
    )
    assert not any("【停損今日無法評估】" in warning for warning in empty.warnings)
    assert any("依鐵律⑤當日不產生指令。" in warning for warning in empty.warnings)


def test_the_emergency_mode_line_counts_the_day_it_is_evaluated_on() -> None:
    """覆審：mode_reason 每日渲染，第 N 個交易日隨日期前進."""
    calendar = helper.calendar()
    until = calendar.shift(TUESDAY, 20)
    first = run(
        data_date=WEDNESDAY,
        index=helper.index(data_date=WEDNESDAY),
        portfolio=helper.portfolio(emergency_until=until),
    )
    later = run(
        data_date=calendar.shift(TUESDAY, 6),
        index=helper.index(data_date=calendar.shift(TUESDAY, 6)),
        portfolio=helper.portfolio(emergency_until=until),
    )
    assert first.mode == "emergency_frozen"
    assert "第 1/20 交易日" in first.mode_reason
    assert "第 6/20 交易日" in later.mode_reason
    assert "所有排程" not in first.mode_reason
