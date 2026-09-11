"""Charts for the five-condition event study: terminal bars and an SVG page.

CEO 2026-09-11「幫我做 CLI 這個（圖形化）」; concept and every sentence from
creative-lead (``work/五條件事件研究圖表化-企劃.md``), risk-compliance reviewed.

Two renderings of the same :class:`~app.backtest.event_study.EventStudyReport`:

* :func:`positive_rate_lines` -- a text block per period for the terminal: one
  0-100% ruler per horizon with the event and baseline positive rates and
  their Wilson intervals drawn on it, so two intervals can be compared without
  arithmetic. Full sample only (the non-overlapping subsample stays in the
  numeric table above it).
* :func:`render_html` -- a self-contained HTML page (inline SVG, no scripts,
  no external assets, fixed 960px, dark surface) with five charts: the
  bar-by-bar forward path (median + Q1-Q3 band), the positive-rate intervals
  per horizon (full sample beside the non-overlapping subsample), the same
  interval chart for each half, and the median / quartile ranges per horizon.

Encoding (dataviz skill, S1 色彩不承載價值判斷): events are blue ``#3987e5``,
solid, circle; the baseline is yellow ``#c98500``, dashed, diamond -- the pair
the product's equity-curve chart already validated on the ``#0a0a0a`` surface.
Full sample = filled marks, non-overlapping subsample = hollow marks. Bands are
the series hue at 12% opacity; the zero line is neutral grey. The yellow is a
category colour only (風控 REQ-9): it must never be re-used for a warning or a
value judgement, and unifying it with the product's amber alert colour is a new
submission. Text wears text
tokens only. Nothing here colours a positive return green or a negative one
red, draws a target or a projection, or writes a conclusion for the reader:
sample sizes sit beside every mark, and the page top and bottom repeat the
study's own scope notice, demo warning and footnotes verbatim.
"""

from __future__ import annotations

import html
from collections.abc import Iterable

from app.backtest.episodes import ProportionInterval
from app.backtest.event_study import (
    DEMO_DATA_WARNING,
    FOOTNOTES,
    RESEARCH_USE_NOTICE,
    SCOPE_NOTICE,
    EventStudyReport,
    HorizonStats,
    PathPoint,
    PeriodReport,
)

# --- wording (creative-lead 定稿, pinned verbatim in tests) -------------------

TERMINAL_GROUP_LEGEND = "事件＝五條同時成立；基準＝同期所有 bar（無條件基準）。"
TERMINAL_BLOCK_TITLE = "正報酬率一覽（全樣本，事件 vs 基準）"
TERMINAL_COLUMNS = "橫軸／群組／長條（0%–100%）／比例／Wilson 95%"
TERMINAL_GROUP_EVENT = "事件"
TERMINAL_GROUP_BASELINE = "基準"
TERMINAL_BAR_LEGEND_1 = "長條中 ▓／● 代表事件，░／◇ 代表基準。"
TERMINAL_BAR_LEGEND_2 = "●／◇ 為正報酬率位置，▓／░ 為 Wilson 95% 區間。"
#: 風控 R4: the drawn interval is the full (overlapping) sample; point back to the table.
TERMINAL_BAR_LEGEND_3 = "本圖區間為全樣本，事件重疊會低估不確定性；上表另附較保守的非重疊子樣本。"
TERMINAL_NO_EVENTS = "本段五條同時成立事件數為 0，長條僅顯示基準。"

HTML_TITLE_SUFFIX = "｜圖表"
HTML_LEGEND_EVENT = "事件（五條同時成立）：圓形、實線、藍。"
HTML_LEGEND_BASELINE = "基準（同期所有 bar，無條件基準）：菱形、虛線、黃。"
HTML_LEGEND_SAMPLE = "全樣本：實心；非重疊子樣本（同一群集僅取最早一根）：空心。"

PATH_CHART_TITLE = "事件後累積報酬分布（全期，0～60 根）"
PATH_CHART_X = "事件後 bar 數（0～60）"
PATH_CHART_Y = "累積報酬（%，中位數與 Q1–Q3）"
PATH_CHART_NOTE = (
    "線為各橫軸各自中位數連線，帶為 Q1–Q3，非單一走勢。"
    "各橫軸樣本數不同（愈遠愈少），事件重疊、樣本不獨立，非預測未來走勢。"
)

RATE_CHART_TITLE = "正報酬率區間比較（全期，各橫軸）"
RATE_CHART_TITLE_FIRST_HALF = "正報酬率區間比較（前半／樣本內）"
RATE_CHART_TITLE_SECOND_HALF = "正報酬率區間比較（後半／樣本外）"
RATE_CHART_SUB_FULL = "全樣本"
RATE_CHART_SUB_INDEPENDENT = "非重疊子樣本"
RATE_CHART_X = "前瞻橫軸（bar 數）"
RATE_CHART_Y = "正報酬率（%）"
RATE_CHART_NOTE = "點為正報酬率，橫線為 Wilson 95% 區間，僅描述歷史。"
RATE_CHART_HALF_NOTE = (
    "本圖比較同一張圖內事件與基準的正報酬率區間。區間重疊與否不構成顯著性檢定。"
    "本研究未擬合任何參數，後半非模型樣本外。"
)

QUARTILE_CHART_TITLE = "中位數與四分位比較（全期，各橫軸）"
QUARTILE_CHART_X = "前瞻橫軸（bar 數）"
QUARTILE_CHART_Y = "報酬（%，中位數與 Q1–Q3）"
QUARTILE_CHART_NOTE = "範圍條為 Q1–Q3，刻度為中位數；描述歷史分布位置。"

FOOTNOTES_HEADING = "說明與限制："
HTML_NO_EVENTS = "本段五條同時成立事件數為 0，此圖僅顯示基準，不繪製事件序列。"


def sample_label(n: int) -> str:
    return f"n={n}"


def independent_sample_label(n: int) -> str:
    return f"n(獨立)={n}"


def no_bars_statement(period_label: str) -> str:
    return f"本段：{period_label}，尚無日線資料，無法繪製此圖。"


def generated_at_line(timestamp: str) -> str:
    """風控 R8: the page is a snapshot; say when it was made."""
    return f"本頁產出時間 {timestamp}，為靜態快照，不會自動更新。"


# --- terminal ------------------------------------------------------------------

#: Cells on the 0-100% ruler. A row is at most 78 code points. Known limit: the
#: block and mark glyphs (▓ ░ ● ◇) are East-Asian-Width *ambiguous*, so a CJK
#: terminal font may render them double-width and stretch the ruler; the cell
#: order and the numbers beside it stay correct either way.
RULER_CELLS = 40


def ruler_cell(proportion: float) -> int:
    """The ruler cell a proportion in [0, 1] falls in (monotonic, clamped)."""
    return max(0, min(RULER_CELLS - 1, int(proportion * RULER_CELLS)))


def _ruler(rate: float | None, interval: ProportionInterval | None, *, event: bool) -> str:
    """One 0-100% ruler: the interval as a run of block glyphs, the rate as a mark."""
    cells = ["·"] * RULER_CELLS
    if rate is None or interval is None:
        return "".join(cells)
    # One rounding rule for every proportion (風控 R10): the cell holding p is
    # floor(p * cells), so low <= rate <= high maps to lo <= point <= hi and the
    # mark can never sit outside its own interval.
    lo, hi, point = (ruler_cell(p) for p in (interval.low, interval.high, rate))
    block = "▓" if event else "░"
    for i in range(lo, hi + 1):
        cells[i] = block
    cells[point] = "●" if event else "◇"
    return "".join(cells)


def _rate_text(rate: float | None) -> str:
    return "—" if rate is None else f"{rate * 100.0:.1f}%"


def _interval_text(interval: ProportionInterval | None) -> str:
    if interval is None:
        return "—"
    return f"({interval.low * 100.0:.1f}%, {interval.high * 100.0:.1f}%)"


def _ruler_row(horizon: str, group: str, stats: HorizonStats, *, event: bool) -> str:
    return (
        f"    {horizon:>4}  {group}  "
        f"{_ruler(stats.positive_rate, stats.positive_interval, event=event)}  "
        f"{_rate_text(stats.positive_rate):>6}  {_interval_text(stats.positive_interval)}"
    )


def positive_rate_lines(period: PeriodReport) -> list[str]:
    """The terminal ruler block for one period (full sample, event vs baseline)."""
    lines = [f"  {TERMINAL_BLOCK_TITLE}", f"    {TERMINAL_COLUMNS}"]
    if period.n_events == 0:
        lines.append(f"    {TERMINAL_NO_EVENTS}")
    for event_stats, base_stats in zip(
        period.events.horizons, period.baseline.horizons, strict=True
    ):
        horizon = str(event_stats.horizon)
        if period.n_events > 0:
            lines.append(_ruler_row(horizon, TERMINAL_GROUP_EVENT, event_stats, event=True))
            horizon = ""
        lines.append(_ruler_row(horizon, TERMINAL_GROUP_BASELINE, base_stats, event=False))
    lines.append(f"    {TERMINAL_BAR_LEGEND_1}")
    lines.append(f"    {TERMINAL_BAR_LEGEND_2}")
    lines.append(f"    {TERMINAL_BAR_LEGEND_3}")
    return lines


# --- SVG primitives -------------------------------------------------------------

EVENT_COLOR = "#3987e5"
BASELINE_COLOR = "#c98500"
SURFACE = "#0a0a0a"
PANEL = "#111111"
GRID = "#262626"
AXIS = "#404040"
ZERO_LINE = "#737373"
TEXT_PRIMARY = "#e5e5e5"
TEXT_SECONDARY = "#a3a3a3"
TEXT_MUTED = "#737373"
BAND_OPACITY = "0.12"

PAGE_WIDTH = 960
CHART_WIDTH = 900
FONT = "font-family:system-ui,-apple-system,'Segoe UI','Noto Sans TC','PingFang TC',sans-serif"


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _fmt(value: float) -> str:
    return f"{value:.1f}"


def _text(
    x: float,
    y: float,
    text: str,
    *,
    size: int = 12,
    fill: str = TEXT_SECONDARY,
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{_fmt(x)}" y="{_fmt(y)}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}">{_esc(text)}</text>'
    )


def _line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    stroke: str,
    width: float = 1,
    dashed: bool = False,
) -> str:
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return (
        f'<line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}" '
        f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="round"{dash}/>'
    )


def _vtext(x: float, y: float, text: str) -> str:
    """A y-axis title, rotated -90 degrees around its own anchor."""
    return (
        f'<text x="{_fmt(x)}" y="{_fmt(y)}" font-size="12" fill="{TEXT_SECONDARY}" '
        f'text-anchor="middle" transform="rotate(-90 {_fmt(x)} {_fmt(y)})">'
        f"{_esc(text)}</text>"
    )


def _circle(x: float, y: float, *, color: str, filled: bool, r: float = 4.5) -> str:
    fill = color if filled else PANEL
    return (
        f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{r}" fill="{fill}" '
        f'stroke="{color}" stroke-width="2"/>'
    )


def _diamond(x: float, y: float, *, color: str, filled: bool, r: float = 5.5) -> str:
    fill = color if filled else PANEL
    corners = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
    points = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in corners)
    return f'<polygon points="{points}" fill="{fill}" stroke="{color}" stroke-width="2"/>'


def _mark(x: float, y: float, *, event: bool, filled: bool) -> str:
    if event:
        return _circle(x, y, color=EVENT_COLOR, filled=filled)
    return _diamond(x, y, color=BASELINE_COLOR, filled=filled)


def _polyline(points: Iterable[tuple[float, float]], *, stroke: str, dashed: bool) -> str:
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return (
        f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"{dash}/>'
    )


def _band(upper: list[tuple[float, float]], lower: list[tuple[float, float]], *, fill: str) -> str:
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in [*upper, *reversed(lower)])
    return f'<polygon points="{pts}" fill="{fill}" fill-opacity="{BAND_OPACITY}" stroke="none"/>'


def _nice_step(span: float, target_ticks: int = 5) -> float:
    raw = span / max(target_ticks, 1)
    magnitude = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
    for candidate in (1, 2, 2.5, 5, 10):
        step = candidate * magnitude
        if step >= raw:
            return float(step)
    return float(10 * magnitude)


def _svg_open(height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CHART_WIDTH}" height="{height}" '
        f'viewBox="0 0 {CHART_WIDTH} {height}" role="img" style="{FONT}">'
    )


# --- chart 1: forward path --------------------------------------------------------


def _path_pct(points: tuple[PathPoint, ...]) -> list[tuple[int, float, float, float]]:
    """(horizon, median%, q1%, q3%) for every step that has a value."""
    out: list[tuple[int, float, float, float]] = []
    for p in points:
        if p.median is None or p.q1 is None or p.q3 is None:
            continue
        out.append((p.horizon, p.median * 100.0, p.q1 * 100.0, p.q3 * 100.0))
    return out


def path_chart_svg(period: PeriodReport, horizons: tuple[int, ...]) -> str:
    left, right, top, bottom = 64, 24, 20, 76
    height = 380
    plot_w = CHART_WIDTH - left - right
    plot_h = height - top - bottom

    event_pts = _path_pct(period.events.path) if period.n_events > 0 else []
    base_pts = _path_pct(period.baseline.path)
    max_h = max(
        [p.horizon for p in period.baseline.path] + [p.horizon for p in period.events.path] + [1]
    )
    values = [v for pts in (event_pts, base_pts) for (_, m, q1, q3) in pts for v in (m, q1, q3)]
    lo = min(values + [0.0])
    hi = max(values + [0.0])
    pad = max((hi - lo) * 0.08, 0.5)
    lo, hi = lo - pad, hi + pad

    def x_of(h: float) -> float:
        return left + plot_w * (h / max_h)

    def y_of(v: float) -> float:
        return top + plot_h * (1 - (v - lo) / (hi - lo))

    parts = [_svg_open(height)]
    # Gridlines on nice y ticks; zero line in neutral grey.
    step = _nice_step(hi - lo)
    tick = (lo // step) * step
    while tick <= hi:
        if lo <= tick <= hi:
            y = y_of(tick)
            if tick != 0:
                parts.append(_line(left, y, left + plot_w, y, stroke=GRID))
            parts.append(_text(left - 8, y + 4, f"{tick:+.0f}%", fill=TEXT_MUTED, anchor="end"))
        tick += step
    if lo <= 0 <= hi:
        parts.append(_line(left, y_of(0), left + plot_w, y_of(0), stroke=ZERO_LINE))
    parts.append(_line(left, top + plot_h, left + plot_w, top + plot_h, stroke=AXIS))
    parts.append(_line(left, top, left, top + plot_h, stroke=AXIS))

    # Horizon ticks with sample sizes beside them (once per summary horizon).
    for h in horizons:
        x = x_of(h)
        parts.append(_line(x, top + plot_h, x, top + plot_h + 5, stroke=AXIS))
        parts.append(_text(x, top + plot_h + 18, str(h), fill=TEXT_SECONDARY, anchor="middle"))
        n_event = next((p.n for p in period.events.path if p.horizon == h), None)
        n_base = next((p.n for p in period.baseline.path if p.horizon == h), None)
        if period.n_events > 0 and n_event is not None:
            parts.append(
                _text(
                    x,
                    top + plot_h + 32,
                    f"● {sample_label(n_event)}",
                    size=11,
                    fill=TEXT_SECONDARY,
                    anchor="middle",
                )
            )
        if n_base is not None:
            parts.append(
                _text(
                    x,
                    top + plot_h + 45,
                    f"◆ {sample_label(n_base)}",
                    size=11,
                    fill=TEXT_SECONDARY,
                    anchor="middle",
                )
            )
    parts.append(_text(left, top + plot_h + 18, "0", fill=TEXT_SECONDARY, anchor="middle"))
    parts.append(
        _text(left + plot_w / 2, height - 4, PATH_CHART_X, fill=TEXT_SECONDARY, anchor="middle")
    )
    parts.append(_vtext(14, top + plot_h / 2, PATH_CHART_Y))

    def draw(pts: list[tuple[int, float, float, float]], *, color: str, dashed: bool) -> None:
        if not pts:
            return
        origin = (x_of(0), y_of(0))
        upper = [origin] + [(x_of(h), y_of(q3)) for h, _, _, q3 in pts]
        lower = [origin] + [(x_of(h), y_of(q1)) for h, _, q1, _ in pts]
        parts.append(_band(upper, lower, fill=color))
        parts.append(
            _polyline(
                [origin] + [(x_of(h), y_of(m)) for h, m, _, _ in pts], stroke=color, dashed=dashed
            )
        )

    draw(base_pts, color=BASELINE_COLOR, dashed=True)
    draw(event_pts, color=EVENT_COLOR, dashed=False)
    parts.append("</svg>")
    return "".join(parts)


# --- chart 2: positive-rate intervals ---------------------------------------------


def _rate_panel(
    stats_pairs: list[tuple[HorizonStats, HorizonStats]],
    *,
    x0: float,
    width: float,
    top: float,
    row_h: float,
    independent: bool,
    draw_events: bool,
) -> list[str]:
    parts: list[str] = []
    title_w = 26
    label_w = 40
    n_w = 78
    plot_x = x0 + title_w + label_w
    plot_w = width - title_w - label_w - n_w

    def x_of(rate: float) -> float:
        return plot_x + plot_w * rate

    for pct in (0, 25, 50, 75, 100):
        x = x_of(pct / 100)
        parts.append(_line(x, top - 6, x, top + row_h * len(stats_pairs), stroke=GRID))
        parts.append(_text(x, top - 10, f"{pct}%", size=11, fill=TEXT_MUTED, anchor="middle"))

    for i, (event_stats, base_stats) in enumerate(stats_pairs):
        y_row = top + row_h * i
        parts.append(
            _text(
                x0 + title_w, y_row + row_h / 2 + 4, str(event_stats.horizon), fill=TEXT_SECONDARY
            )
        )
        rows = [(base_stats, False, y_row + row_h * 0.68)]
        if draw_events:
            rows.insert(0, (event_stats, True, y_row + row_h * 0.32))
        for stats, is_event, y in rows:
            n = stats.independent_n if independent else stats.n
            rate = stats.independent_positive_rate if independent else stats.positive_rate
            interval = (
                stats.independent_positive_interval if independent else stats.positive_interval
            )
            label = independent_sample_label(n) if independent else sample_label(n)
            color = EVENT_COLOR if is_event else BASELINE_COLOR
            if rate is not None and interval is not None:
                parts.append(
                    _line(x_of(interval.low), y, x_of(interval.high), y, stroke=color, width=2)
                )
                parts.append(_mark(x_of(rate), y, event=is_event, filled=not independent))
            parts.append(_text(plot_x + plot_w + 8, y + 4, label, size=11, fill=TEXT_SECONDARY))
    return parts


def rate_chart_svg(period: PeriodReport) -> str:
    row_h = 44
    pairs = list(zip(period.events.horizons, period.baseline.horizons, strict=True))
    top = 40
    height = int(top + row_h * len(pairs) + 44)
    gap = 40
    panel_w = (CHART_WIDTH - gap) / 2
    parts = [_svg_open(height)]
    draw_events = period.n_events > 0
    for j, (sub, independent) in enumerate(
        ((RATE_CHART_SUB_FULL, False), (RATE_CHART_SUB_INDEPENDENT, True))
    ):
        x0 = j * (panel_w + gap)
        parts.append(_text(x0, 14, sub, size=13, fill=TEXT_PRIMARY))
        parts.extend(
            _rate_panel(
                pairs,
                x0=x0,
                width=panel_w,
                top=top,
                row_h=row_h,
                independent=independent,
                draw_events=draw_events,
            )
        )
        parts.append(
            _text(x0 + panel_w / 2, height - 6, RATE_CHART_Y, fill=TEXT_SECONDARY, anchor="middle")
        )
        parts.append(_vtext(x0 + 10, top + row_h * len(pairs) / 2, RATE_CHART_X))
    parts.append("</svg>")
    return "".join(parts)


# --- chart 3: median and quartiles --------------------------------------------------


def quartile_chart_svg(period: PeriodReport) -> str:
    row_h = 48
    pairs = list(zip(period.events.horizons, period.baseline.horizons, strict=True))
    top, left, n_w = 32, 64, 78
    height = int(top + row_h * len(pairs) + 44)
    plot_x = left
    plot_w = CHART_WIDTH - left - n_w - 8
    draw_events = period.n_events > 0

    values: list[float] = []
    for e, b in pairs:
        for s in (e, b) if draw_events else (b,):
            for v in (s.median, s.q1, s.q3):
                if v is not None:
                    values.append(v * 100.0)
    lo = min(values + [0.0])
    hi = max(values + [0.0])
    pad = max((hi - lo) * 0.08, 0.5)
    lo, hi = lo - pad, hi + pad

    def x_of(v: float) -> float:
        return plot_x + plot_w * (v - lo) / (hi - lo)

    parts = [_svg_open(height)]
    step = _nice_step(hi - lo)
    tick = (lo // step) * step
    while tick <= hi:
        if lo <= tick <= hi:
            x = x_of(tick)
            if tick != 0:
                parts.append(_line(x, top - 6, x, top + row_h * len(pairs), stroke=GRID))
            parts.append(
                _text(x, top - 10, f"{tick:+.0f}%", size=11, fill=TEXT_MUTED, anchor="middle")
            )
        tick += step
    if lo <= 0 <= hi:
        parts.append(_line(x_of(0), top - 6, x_of(0), top + row_h * len(pairs), stroke=ZERO_LINE))

    for i, (event_stats, base_stats) in enumerate(pairs):
        y_row = top + row_h * i
        parts.append(
            _text(30, y_row + row_h / 2 + 4, str(event_stats.horizon), fill=TEXT_SECONDARY)
        )
        rows = [(base_stats, False, y_row + row_h * 0.68)]
        if draw_events:
            rows.insert(0, (event_stats, True, y_row + row_h * 0.32))
        for stats, is_event, y in rows:
            color = EVENT_COLOR if is_event else BASELINE_COLOR
            if stats.median is not None and stats.q1 is not None and stats.q3 is not None:
                x1, x2 = x_of(stats.q1 * 100.0), x_of(stats.q3 * 100.0)
                width = _fmt(max(x2 - x1, 1.0))
                parts.append(
                    f'<rect x="{_fmt(x1)}" y="{_fmt(y - 4)}" width="{width}" height="8" '
                    f'rx="3" fill="{color}" fill-opacity="0.35"/>'
                )
                parts.append(_mark(x_of(stats.median * 100.0), y, event=is_event, filled=True))
            parts.append(
                _text(
                    plot_x + plot_w + 8, y + 4, sample_label(stats.n), size=11, fill=TEXT_SECONDARY
                )
            )
    parts.append(
        _text(
            plot_x + plot_w / 2, height - 6, QUARTILE_CHART_Y, fill=TEXT_SECONDARY, anchor="middle"
        )
    )
    parts.append(_vtext(14, top + row_h * len(pairs) / 2, QUARTILE_CHART_X))
    parts.append("</svg>")
    return "".join(parts)


# --- page -------------------------------------------------------------------------

_CSS = (
    f"body{{margin:0;background:{SURFACE};color:{TEXT_PRIMARY};{FONT};font-size:14px;line-height:1.5}}"
    f"main{{width:{PAGE_WIDTH}px;margin:0 auto;padding:24px 30px 40px}}"
    "h1{font-size:20px;margin:0 0 6px}"
    "h2{font-size:15px;margin:28px 0 4px}"
    f".meta{{color:{TEXT_SECONDARY};font-size:14px;margin:2px 0}}"
    f".notice{{border:1px solid {AXIS};border-radius:6px;padding:8px 12px;"
    "margin:10px 0;font-size:14px}"
    f".legend{{color:{TEXT_SECONDARY};font-size:14px;margin:12px 0 4px}}"
    f".legend span{{margin-right:18px}}"
    f".note{{color:{TEXT_SECONDARY};font-size:14px;margin:4px 0 0}}"
    f".empty{{color:{TEXT_SECONDARY};font-size:14px;border:1px dashed {AXIS};"
    "border-radius:6px;padding:10px 12px}"
    f"figure{{margin:6px 0 0;background:{PANEL};border:1px solid {GRID};"
    "border-radius:6px;padding:12px 12px 6px}"
    f"ul.footnotes{{color:{TEXT_SECONDARY};font-size:14px;padding-left:20px}}"
    f"ul.footnotes li{{margin:4px 0}}"
)


def _figure(
    title: str,
    note: str,
    svg: str | None,
    *,
    empty: str | None = None,
    extra_note: str | None = None,
) -> str:
    body = f"<figure>{svg}</figure>" if svg else f'<p class="empty">{_esc(empty or "")}</p>'
    notes = f'<p class="note">{_esc(note)}</p>'
    if extra_note:
        notes += f'<p class="note">{_esc(extra_note)}</p>'
    return f"<section><h2>{_esc(title)}</h2>{body}{notes}</section>"


def _period_or_empty(
    period: PeriodReport, chart: str, title: str, note: str, *, extra_note: str | None = None
) -> str:
    if period.n_bars == 0:
        return _figure(
            title, note, None, empty=no_bars_statement(period.label), extra_note=extra_note
        )
    prefix = f'<p class="note">{_esc(HTML_NO_EVENTS)}</p>' if period.n_events == 0 else ""
    return _figure(title, note, chart, extra_note=extra_note).replace(
        "<figure>", prefix + "<figure>", 1
    )


def render_html(report: EventStudyReport, *, dividend_note: str, generated_at: str) -> str:
    """The self-contained chart page for one report."""
    full, first, second = report.periods[0], report.periods[1], report.periods[2]
    title = f"五項觀察條件 事件研究 — {report.symbol}（{report.market}）{HTML_TITLE_SUFFIX}"
    source = report.source or "未知"
    data_line = (
        f"日線 {report.n_bars} 根｜{report.first_date} ～ {report.last_date}｜資料來源：{source}"
    )
    split_line = f"前後對半切點：bar {report.split_index}（{report.split_date or '—'}）"
    head = [
        f"<h1>{_esc(title)}</h1>",
        f'<p class="meta">{_esc(data_line)}</p>',
        f'<p class="notice">{_esc(SCOPE_NOTICE)}</p>',
        f'<p class="meta">{_esc(split_line)}</p>',
    ]
    if report.source == "demo_synthetic":
        head.append(f'<p class="notice">{_esc(DEMO_DATA_WARNING)}</p>')
    # 風控 R1: the research-use notice stands before the first chart as well as
    # in the footer; a screenshot that loses the tail still carries it.
    head.append(f'<p class="notice">{_esc(RESEARCH_USE_NOTICE)}</p>')
    head.append(f'<p class="meta">{_esc(generated_at_line(generated_at))}</p>')
    # 風控 R9: the dividend line is a return-bias disclosure, never optional,
    # and sits at notice level beside the scope notice.
    head.append(f'<p class="notice">{_esc("除權息：" + dividend_note)}</p>')
    head.append(
        '<p class="legend">'
        f"<span>{_esc(HTML_LEGEND_EVENT)}</span><span>{_esc(HTML_LEGEND_BASELINE)}</span>"
        f"<span>{_esc(HTML_LEGEND_SAMPLE)}</span></p>"
    )

    sections = [
        _period_or_empty(
            full, path_chart_svg(full, report.horizons), PATH_CHART_TITLE, PATH_CHART_NOTE
        ),
        _period_or_empty(full, rate_chart_svg(full), RATE_CHART_TITLE, RATE_CHART_NOTE),
        _period_or_empty(
            first,
            rate_chart_svg(first),
            RATE_CHART_TITLE_FIRST_HALF,
            RATE_CHART_NOTE,
            extra_note=RATE_CHART_HALF_NOTE,
        ),
        _period_or_empty(
            second,
            rate_chart_svg(second),
            RATE_CHART_TITLE_SECOND_HALF,
            RATE_CHART_NOTE,
            extra_note=RATE_CHART_HALF_NOTE,
        ),
        _period_or_empty(full, quartile_chart_svg(full), QUARTILE_CHART_TITLE, QUARTILE_CHART_NOTE),
    ]
    footer = [f"<h2>{_esc(FOOTNOTES_HEADING)}</h2>", '<ul class="footnotes">']
    footer.extend(f"<li>{_esc(note)}</li>" for note in FOOTNOTES)
    footer.append("</ul>")

    return (
        "<!doctype html>\n"
        '<html lang="zh-Hant-TW"><head><meta charset="utf-8">'
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head><body><main>"
        + "".join(head)
        + "".join(sections)
        + "".join(footer)
        + "</main></body></html>\n"
    )


__all__ = [
    "positive_rate_lines",
    "path_chart_svg",
    "rate_chart_svg",
    "quartile_chart_svg",
    "render_html",
]
