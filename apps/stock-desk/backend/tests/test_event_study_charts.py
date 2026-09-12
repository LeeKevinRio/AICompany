"""Tests for the event-study charts (CEO 2026-09-11 CLI 圖形化).

Pins, in order of importance:

1. The wording (creative-lead 定稿, risk-compliance reviewed) verbatim, and that
   the HTML page repeats the study's own scope notice, demo warning and
   footnotes without a character changed.
2. The forward path arithmetic behind chart 1 (bar-by-bar quantiles, sample
   size shrinking with the horizon, the same numbers as ``HorizonStats`` at
   the summary horizons).
3. That nothing user-visible carries a forbidden term or a directive, that the
   SVG is well-formed XML, and that an empty cohort draws no geometry.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from app.backtest import event_study_charts as charts
from app.backtest import event_study_page as page_mod
from app.backtest.event_study import (
    DEMO_DATA_WARNING,
    FOOTNOTES,
    HORIZONS,
    PATH_MAX_HORIZON,
    RESEARCH_USE_NOTICE,
    SCOPE_NOTICE,
    EventStudyReport,
    format_report,
    main,
    run_event_study,
    summarise_path_point,
)
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes
from tests.test_backtest_strategies import _FIVE_CLOSES, _FIVE_VOLUMES
from tests.test_event_study_wording import _FRONTEND_TERMS, _shared_terms


def _report(n: int | None = None, source: str | None = "demo_synthetic") -> EventStudyReport:
    closes = _FIVE_CLOSES if n is None else _FIVE_CLOSES[:n]
    volumes = _FIVE_VOLUMES if n is None else _FIVE_VOLUMES[:n]
    frame = bars_to_frame(bars_from_closes(closes, volumes=volumes))
    return run_event_study(frame, symbol="2330", source=source)


def _svg_texts(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    return [t.text or "" for t in root.iter("{http://www.w3.org/2000/svg}text")]


# --- forward path -----------------------------------------------------------------


def test_path_points_run_one_to_the_longest_horizon_and_shrink_with_it() -> None:
    report = _report()
    for cohort in (report.periods[0].events, report.periods[0].baseline):
        assert [p.horizon for p in cohort.path] == list(range(1, PATH_MAX_HORIZON + 1))
        sizes = [p.n for p in cohort.path]
        assert sizes == sorted(sizes, reverse=True)


def test_path_is_clamped_to_the_documented_maximum_horizon() -> None:
    frame = bars_to_frame(bars_from_closes(_FIVE_CLOSES, volumes=_FIVE_VOLUMES))
    report = run_event_study(frame, symbol="2330", horizons=(5, 200))
    assert report.periods[0].baseline.path[-1].horizon == PATH_MAX_HORIZON
    assert [s.horizon for s in report.periods[0].baseline.horizons] == [5, 200]


def test_path_points_agree_with_the_summary_horizons() -> None:
    period = _report().periods[0]
    for cohort in (period.events, period.baseline):
        by_h = {p.horizon: p for p in cohort.path}
        for stats in cohort.horizons:
            point = by_h[stats.horizon]
            assert (point.n, point.median, point.q1, point.q3) == (
                stats.n,
                stats.median,
                stats.q1,
                stats.q3,
            )


def test_summarise_path_point_is_the_plain_quantiles_of_the_defined_returns() -> None:
    returns = np.asarray([0.10, -0.20, 0.30, np.nan], dtype="float64")
    point = summarise_path_point(returns, [0, 1, 2, 3], 7)
    assert point.horizon == 7
    assert point.n == 3
    assert point.median == pytest.approx(0.10)
    assert point.q1 == pytest.approx(-0.05)
    assert point.q3 == pytest.approx(0.20)
    empty = summarise_path_point(returns, [3], 7)
    assert (empty.n, empty.median, empty.q1, empty.q3) == (0, None, None, None)


# --- wording ---------------------------------------------------------------------------


def test_terminal_wording_is_pinned_verbatim() -> None:
    assert charts.TERMINAL_GROUP_LEGEND == "事件＝五條同時成立；基準＝同期所有 bar（無條件基準）。"
    assert charts.TERMINAL_BLOCK_TITLE == "正報酬率一覽（全樣本，事件 vs 基準）"
    assert charts.TERMINAL_COLUMNS == "橫軸／群組／長條（0%–100%）／比例／Wilson 95%"
    assert (charts.TERMINAL_GROUP_EVENT, charts.TERMINAL_GROUP_BASELINE) == ("事件", "基準")
    assert charts.TERMINAL_BAR_LEGEND_1 == "長條中 ▓／● 代表事件，░／◇ 代表基準。"
    assert charts.TERMINAL_BAR_LEGEND_2 == "●／◇ 為正報酬率位置，▓／░ 為 Wilson 95% 區間。"
    assert charts.TERMINAL_BAR_LEGEND_3 == (
        "本圖區間為全樣本，事件重疊會低估不確定性；上表另附較保守的非重疊子樣本。"
    )
    assert charts.TERMINAL_NO_EVENTS == "本段五條同時成立事件數為 0，長條僅顯示基準。"


def test_path_chart_wording_states_the_real_maximum_horizon() -> None:
    # 風控 SUG-3: the 「0～60」 in the title and axis label is the documented
    # maximum; if PATH_MAX_HORIZON ever moves, this trips and the wording goes
    # back through risk-compliance-officer.
    assert f"0～{PATH_MAX_HORIZON} 根" in charts.PATH_CHART_TITLE
    assert f"（0～{PATH_MAX_HORIZON}）" in charts.PATH_CHART_X


def test_html_wording_is_pinned_verbatim() -> None:
    assert charts.HTML_TITLE_SUFFIX == "｜圖表"
    assert charts.HTML_LEGEND_EVENT == "事件（五條同時成立）：圓形、實線、藍。"
    assert charts.HTML_LEGEND_BASELINE == "基準（同期所有 bar，無條件基準）：菱形、虛線、黃。"
    assert charts.HTML_LEGEND_SAMPLE == "全樣本：實心；非重疊子樣本（同一群集僅取最早一根）：空心。"
    assert charts.PATH_CHART_TITLE == "事件後累積報酬分布（全期，0～60 根）"
    assert charts.PATH_CHART_X == "事件後 bar 數（0～60）"
    assert charts.PATH_CHART_Y == "累積報酬（%，中位數與 Q1–Q3）"
    assert charts.PATH_CHART_NOTE == (
        "線為各橫軸各自中位數連線，帶為 Q1–Q3，非單一走勢。"
        "各橫軸樣本數不同（愈遠愈少），事件重疊、樣本不獨立，非預測未來走勢。"
    )
    assert charts.RATE_CHART_TITLE == "正報酬率區間比較（全期，各橫軸）"
    assert charts.RATE_CHART_TITLE_FIRST_HALF == "正報酬率區間比較（前半／樣本內）"
    assert charts.RATE_CHART_TITLE_SECOND_HALF == "正報酬率區間比較（後半／樣本外）"
    assert charts.RATE_CHART_SUB_FULL == "全樣本"
    assert charts.RATE_CHART_SUB_INDEPENDENT == "非重疊子樣本"
    assert charts.RATE_CHART_X == "前瞻橫軸（bar 數）"
    assert charts.RATE_CHART_Y == "正報酬率（%）"
    assert charts.RATE_CHART_NOTE == "點為正報酬率，橫線為 Wilson 95% 區間，僅描述歷史。"
    assert charts.RATE_CHART_HALF_NOTE == (
        "本圖比較同一張圖內事件與基準的正報酬率區間。區間重疊與否不構成顯著性檢定。"
        "本研究未擬合任何參數，後半非模型樣本外。"
    )
    assert charts.QUARTILE_CHART_TITLE == "中位數與四分位比較（全期，各橫軸）"
    assert charts.QUARTILE_CHART_X == "前瞻橫軸（bar 數）"
    assert charts.QUARTILE_CHART_Y == "報酬（%，中位數與 Q1–Q3）"
    assert charts.QUARTILE_CHART_NOTE == "範圍條為 Q1–Q3，刻度為中位數；描述歷史分布位置。"
    assert charts.FOOTNOTES_HEADING == "說明與限制："
    assert charts.HTML_NO_EVENTS == "本段五條同時成立事件數為 0，此圖僅顯示基準，不繪製事件序列。"
    assert charts.sample_label(55) == "n=55"
    assert charts.independent_sample_label(23) == "n(獨立)=23"
    assert charts.no_bars_statement("後半（樣本外）") == (
        "本段：後半（樣本外），尚無日線資料，無法繪製此圖。"
    )
    assert charts.generated_at_line("2026-09-11 14:03 台北時間") == (
        "本頁產出時間 2026-09-11 14:03 台北時間，為靜態快照，不會自動更新。"
    )
    assert charts.generated_at_line("2026-09-11 14:03 台北時間", subject="本節") == (
        "本節產出時間 2026-09-11 14:03 台北時間，為靜態快照，不會自動更新。"
    )


# --- terminal block --------------------------------------------------------------------


@pytest.mark.parametrize("event", [True, False])
@pytest.mark.parametrize("n", [1, 2, 7, 40, 55, 515, 1500, 5000, 20000])
def test_ruler_mark_always_sits_inside_its_own_interval(n: int, event: bool) -> None:
    # 風控 R10: one rounding rule for the rate and both interval ends, so the
    # mark can never land outside the drawn interval -- including intervals
    # narrower than one cell (large n) and the 0% / 100% edges.
    from app.backtest.episodes import wilson_interval

    for k in sorted({0, 1, n // 4, n // 2, (3 * n) // 4, n - 1, n}):
        rate = k / n
        interval = wilson_interval(k, n, alpha=0.05)
        assert interval is not None
        row = charts._ruler(rate, interval, event=event)
        block, mark = ("▓", "●") if event else ("░", "◇")
        assert len(row) == charts.RULER_CELLS
        lo, hi = charts.ruler_cell(interval.low), charts.ruler_cell(interval.high)
        point = row.index(mark)
        assert lo <= point <= hi
        assert set(row[lo : hi + 1]) <= {block, mark}
        assert block not in row[:lo] and block not in row[hi + 1 :]


def test_terminal_block_has_one_ruler_row_per_group_per_horizon_within_78_columns() -> None:
    period = _report().periods[0]
    lines = charts.positive_rate_lines(period)
    assert lines[0].strip() == charts.TERMINAL_BLOCK_TITLE
    assert lines[1].strip() == charts.TERMINAL_COLUMNS
    rows = [
        line
        for line in lines
        if f"  {charts.TERMINAL_GROUP_EVENT}  " in line
        or f"  {charts.TERMINAL_GROUP_BASELINE}  " in line
    ]
    assert len(rows) == 2 * len(HORIZONS)
    for row in rows:
        assert len(row) <= 78
        assert row.count("●") + row.count("◇") == 1
    assert lines[-3].strip() == charts.TERMINAL_BAR_LEGEND_1
    assert lines[-2].strip() == charts.TERMINAL_BAR_LEGEND_2
    assert lines[-1].strip() == charts.TERMINAL_BAR_LEGEND_3


def test_terminal_block_with_no_events_draws_only_the_baseline_and_says_so() -> None:
    period = _report(40).periods[0]
    assert period.n_events == 0
    lines = charts.positive_rate_lines(period)
    assert charts.TERMINAL_NO_EVENTS in "\n".join(lines)
    rows = lines[2:-3]
    assert not any(f"  {charts.TERMINAL_GROUP_EVENT}  " in line for line in rows)
    assert sum(f"  {charts.TERMINAL_GROUP_BASELINE}  " in line for line in rows) == len(HORIZONS)


def test_format_report_prints_the_group_legend_once_and_a_ruler_block_per_period() -> None:
    text = format_report(_report())
    assert text.count(charts.TERMINAL_GROUP_LEGEND) == 3
    assert text.count(charts.TERMINAL_BLOCK_TITLE) == 3
    # The rulers come after the numeric tables and before 說明與限制.
    subsample_heading = "非重疊子樣本（同一群集只取最早一根）"
    assert text.index(subsample_heading) < text.index(charts.TERMINAL_BLOCK_TITLE)
    assert text.rindex(charts.TERMINAL_BAR_LEGEND_3) < text.index("說明與限制：")


# --- HTML page --------------------------------------------------------------------------


def test_html_repeats_the_study_notices_verbatim_and_in_order() -> None:
    page = page_mod.render_html(
        _report(), dividend_note="未還原除權息：測試", generated_at="2026-09-11 14:03 台北時間"
    )
    assert page.startswith("<!doctype html>")
    assert "<script" not in page and "http://" not in page.replace("http://www.w3.org/2000/svg", "")
    for sentence in (SCOPE_NOTICE, DEMO_DATA_WARNING, *FOOTNOTES):
        assert charts.escape_text(sentence) in page
    assert page.index(charts.escape_text(SCOPE_NOTICE)) < page.index(
        charts.escape_text(DEMO_DATA_WARNING)
    )
    assert page.index(charts.escape_text(DEMO_DATA_WARNING)) < page.index(charts.PATH_CHART_TITLE)
    # 風控 R1 / R8: the research-use notice and the snapshot stamp precede the first chart.
    assert page.index(charts.escape_text(RESEARCH_USE_NOTICE)) < page.index(charts.PATH_CHART_TITLE)
    assert page.index("本頁產出時間 2026-09-11 14:03 台北時間") < page.index(
        charts.PATH_CHART_TITLE
    )
    # The footer lists every footnote in order (rindex: the first footnote is also
    # repeated at the top of the page, 風控 R1).
    footnote_positions = [page.rindex(charts.escape_text(note)) for note in FOOTNOTES]
    assert footnote_positions == sorted(footnote_positions)
    assert page.index(charts.QUARTILE_CHART_TITLE) < footnote_positions[0]
    # 風控 R9: the dividend line is a notice, not a muted meta line.
    # 風控 2026-09-12 S-1: the sentence carries its own subject, no second prefix.
    assert '<p class="notice">未還原除權息：測試</p>' in page
    assert "未還原除權息：測試" in page and "除權息：未還原除權息" not in page


def test_html_has_five_charts_in_the_agreed_order() -> None:
    page = page_mod.render_html(
        _report(), dividend_note="未還原除權息：測試", generated_at="2026-09-11 14:03 台北時間"
    )
    titles = [
        charts.PATH_CHART_TITLE,
        charts.RATE_CHART_TITLE,
        charts.RATE_CHART_TITLE_FIRST_HALF,
        charts.RATE_CHART_TITLE_SECOND_HALF,
        charts.QUARTILE_CHART_TITLE,
    ]
    positions = [page.index(f"<h2>{t}</h2>") for t in titles]
    assert positions == sorted(positions)
    assert page.count("<svg ") == 5


def test_html_does_not_flag_demo_data_for_a_real_source() -> None:
    page = page_mod.render_html(
        _report(source="twse"),
        dividend_note="未還原除權息：測試",
        generated_at="2026-09-11 14:03 台北時間",
    )
    assert DEMO_DATA_WARNING not in page
    assert "資料來源：twse" in page


def test_every_svg_is_well_formed_and_carries_sample_sizes_beside_the_marks() -> None:
    report = _report()
    full = report.periods[0]
    for svg in (
        charts.path_chart_svg(full, report.horizons),
        charts.rate_chart_svg(full),
        charts.quartile_chart_svg(full),
    ):
        texts = _svg_texts(svg)  # raises if the SVG is not well-formed XML
        assert any(t.startswith("n=") or "n=" in t for t in texts)
    rate_texts = _svg_texts(charts.rate_chart_svg(full))
    assert any(t.startswith("n(獨立)=") for t in rate_texts)
    assert charts.RATE_CHART_SUB_FULL in rate_texts
    assert charts.RATE_CHART_SUB_INDEPENDENT in rate_texts


def test_a_period_with_no_events_draws_no_event_geometry() -> None:
    report = _report(40)
    period = report.periods[0]
    assert period.n_events == 0
    for svg in (
        charts.path_chart_svg(period, report.horizons),
        charts.rate_chart_svg(period),
        charts.quartile_chart_svg(period),
    ):
        assert charts.EVENT_COLOR not in svg
        assert charts.BASELINE_COLOR in svg
    page = page_mod.render_html(
        report, dividend_note="未還原除權息：測試", generated_at="2026-09-11 14:03 台北時間"
    )
    assert charts.HTML_NO_EVENTS in page


def test_an_empty_period_gets_the_no_bars_statement_instead_of_a_chart() -> None:
    report = run_event_study(bars_to_frame([]), symbol="2330", source="demo_synthetic")
    page = page_mod.render_html(
        report, dividend_note="未還原除權息：測試", generated_at="2026-09-11 14:03 台北時間"
    )
    assert charts.no_bars_statement("全期") in page
    assert "<svg " not in page


# --- forbidden terms ----------------------------------------------------------------------


def _page_text() -> str:
    page = page_mod.render_html(
        _report(), dividend_note="未還原除權息：測試", generated_at="2026-09-11 14:03 台北時間"
    )
    return page.replace("&amp;", "&")


@pytest.mark.parametrize("term", _shared_terms() + _FRONTEND_TERMS)
def test_chart_page_and_terminal_block_carry_no_forbidden_term(term: str) -> None:
    assert term not in _page_text()
    assert term not in "\n".join(charts.positive_rate_lines(_report().periods[0]))


def test_no_directive_wording_on_the_chart_page() -> None:
    page = _page_text()
    for index in [i for i in range(len(page)) if page.startswith("建議", i)]:
        preceding = page[max(0, index - 8) : index]
        is_module_name = page[index : index + 4] == "建議引擎"
        assert "不是" in preceding or "不構成" in preceding or is_module_name, preceding


def test_the_shared_forbidden_terms_file_is_the_one_scanned() -> None:
    path = Path(__file__).resolve().parents[2] / "shared" / "forbidden-terms.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload["guarantee"]) <= set(_shared_terms())


# --- CLI -------------------------------------------------------------------------------------


def test_cli_writes_the_html_page_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bars = bars_from_closes(_FIVE_CLOSES, volumes=_FIVE_VOLUMES)
    monkeypatch.setattr(
        "app.backtest.event_study._load_cached_bars", lambda *a, **k: (bars, "demo_synthetic")
    )
    monkeypatch.setattr(
        "app.backtest.event_study._adjust_for_dividends", lambda b, *a, **k: (b, "測試未還原")
    )
    target = tmp_path / "es.html"
    assert main(["2330", "--html", str(target)]) == 0
    page = target.read_text(encoding="utf-8")
    assert charts.PATH_CHART_TITLE in page
    assert "測試未還原" in page and "除權息：測試未還原" not in page


def test_cli_reports_an_unwritable_html_path_instead_of_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bars = bars_from_closes(_FIVE_CLOSES, volumes=_FIVE_VOLUMES)
    monkeypatch.setattr(
        "app.backtest.event_study._load_cached_bars", lambda *a, **k: (bars, "demo_synthetic")
    )
    monkeypatch.setattr(
        "app.backtest.event_study._adjust_for_dividends", lambda b, *a, **k: (b, "測試未還原")
    )
    target = tmp_path / "missing-dir" / "es.html"
    assert main(["2330", "--html", str(target)]) == 1
    out = capsys.readouterr().out
    assert "圖表頁無法寫入" in out
    assert "請確認目錄存在且可寫入" in out
