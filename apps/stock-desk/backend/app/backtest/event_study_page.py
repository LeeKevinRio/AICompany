"""The event-study page model: what the CLI page and the web section both say.

ADR-0008 D-1～D-3: one ordered model, built once from an
:class:`~app.backtest.event_study.EventStudyReport`, rendered either to the
self-contained HTML file the CLI writes (:func:`render_html`) or handed to the
API as JSON. Every sentence is a pinned constant from
:mod:`app.backtest.event_study` / :mod:`app.backtest.event_study_charts`; the
model holds **unescaped** text -- escaping happens only in :func:`render_html`
and inside the SVG builders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.backtest.event_study import (
    DEMO_DATA_WARNING,
    FOOTNOTES,
    RESEARCH_USE_NOTICE,
    SCOPE_NOTICE,
    EventStudyReport,
    PeriodReport,
)
from app.backtest.event_study_charts import (
    AXIS,
    CHART_WIDTH,
    FONT,
    FOOTNOTES_HEADING,
    GRID,
    HTML_LEGEND_BASELINE,
    HTML_LEGEND_EVENT,
    HTML_LEGEND_SAMPLE,
    HTML_NO_EVENTS,
    HTML_TITLE_SUFFIX,
    PANEL,
    PATH_CHART_NOTE,
    PATH_CHART_TITLE,
    QUARTILE_CHART_NOTE,
    QUARTILE_CHART_TITLE,
    RATE_CHART_HALF_NOTE,
    RATE_CHART_NOTE,
    RATE_CHART_TITLE,
    RATE_CHART_TITLE_FIRST_HALF,
    RATE_CHART_TITLE_SECOND_HALF,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    escape_text,
    generated_at_line,
    no_bars_statement,
    path_chart_svg,
    quartile_chart_svg,
    rate_chart_svg,
)

PAGE_WIDTH = 960

HeaderRole = Literal["meta", "notice", "legend"]

_esc = escape_text


@dataclass(frozen=True)
class HeaderItem:
    """One line of the page head, in reading order (ADR-0008 D-2)."""

    role: HeaderRole
    text: str


@dataclass(frozen=True)
class SectionModel:
    """One chart section: the risk-approved title / notes and the SVG (or why not)."""

    key: str
    title: str
    note: str
    extra_note: str | None
    #: 「本段…事件數為 0」 when the period has bars but no event; drawn baseline only.
    no_events_note: str | None
    #: 「本段…尚無日線資料」 when the period has no bars; then ``svg`` is None.
    empty_statement: str | None
    svg: str | None


@dataclass(frozen=True)
class PageModel:
    """Everything the page says, in reading order -- the single source the
    CLI page and the web section both render from (PRD FR-3, ADR-0008)."""

    title: str
    #: Ordered: data line, scope notice, split line, [demo warning], research-use
    #: notice, generated-at line, dividend line(s), legend (three entries).
    header: tuple[HeaderItem, ...]
    sections: tuple[SectionModel, ...]
    footnotes_heading: str
    footnotes: tuple[str, ...]


def _section(
    key: str,
    period: PeriodReport,
    chart: str | None,
    title: str,
    note: str,
    *,
    extra_note: str | None = None,
) -> SectionModel:
    if period.n_bars == 0:
        return SectionModel(
            key=key,
            title=title,
            note=note,
            extra_note=extra_note,
            no_events_note=None,
            empty_statement=no_bars_statement(period.label),
            svg=None,
        )
    return SectionModel(
        key=key,
        title=title,
        note=note,
        extra_note=extra_note,
        no_events_note=HTML_NO_EVENTS if period.n_events == 0 else None,
        empty_statement=None,
        svg=chart,
    )


def build_page_model(
    report: EventStudyReport,
    *,
    dividend_lines: Sequence[str],
    generated_at: str,
    chart_width: int = CHART_WIDTH,
    generated_at_subject: str = "本頁",
) -> PageModel:
    """Assemble the page in reading order; every string is a pinned constant."""
    full, first, second = report.periods[0], report.periods[1], report.periods[2]
    source = report.source or "未知"
    header: list[HeaderItem] = [
        HeaderItem(
            "meta",
            f"日線 {report.n_bars} 根｜{report.first_date} ～ {report.last_date}"
            f"｜資料來源：{source}",
        ),
        HeaderItem("notice", SCOPE_NOTICE),
        HeaderItem("meta", f"前後對半切點：bar {report.split_index}（{report.split_date or '—'}）"),
    ]
    if report.source == "demo_synthetic":
        header.append(HeaderItem("notice", DEMO_DATA_WARNING))
    # 風控 R1: the research-use notice stands before the first chart as well
    # as in the footer; a copy that loses the tail still carries it.
    header.append(HeaderItem("notice", RESEARCH_USE_NOTICE))
    header.append(HeaderItem("meta", generated_at_line(generated_at, subject=generated_at_subject)))
    # 風控 R9: the dividend line is a return-bias disclosure, never optional.
    # The dividend sentences name their own subject (「已還原／未還原除權息：」);
    # no second prefix here (風控 2026-09-12 S-1).
    header.extend(HeaderItem("notice", line) for line in dividend_lines)
    header.extend(
        HeaderItem("legend", text)
        for text in (HTML_LEGEND_EVENT, HTML_LEGEND_BASELINE, HTML_LEGEND_SAMPLE)
    )
    return PageModel(
        title=f"五項觀察條件 事件研究 — {report.symbol}（{report.market}）{HTML_TITLE_SUFFIX}",
        header=tuple(header),
        sections=(
            _section(
                "path",
                full,
                path_chart_svg(full, report.horizons, width=chart_width) if full.n_bars else None,
                PATH_CHART_TITLE,
                PATH_CHART_NOTE,
            ),
            _section(
                "rate_full",
                full,
                rate_chart_svg(full, width=chart_width) if full.n_bars else None,
                RATE_CHART_TITLE,
                RATE_CHART_NOTE,
            ),
            _section(
                "rate_first_half",
                first,
                rate_chart_svg(first, width=chart_width) if first.n_bars else None,
                RATE_CHART_TITLE_FIRST_HALF,
                RATE_CHART_NOTE,
                extra_note=RATE_CHART_HALF_NOTE,
            ),
            _section(
                "rate_second_half",
                second,
                rate_chart_svg(second, width=chart_width) if second.n_bars else None,
                RATE_CHART_TITLE_SECOND_HALF,
                RATE_CHART_NOTE,
                extra_note=RATE_CHART_HALF_NOTE,
            ),
            _section(
                "quartile",
                full,
                quartile_chart_svg(full, width=chart_width) if full.n_bars else None,
                QUARTILE_CHART_TITLE,
                QUARTILE_CHART_NOTE,
            ),
        ),
        footnotes_heading=FOOTNOTES_HEADING,
        footnotes=FOOTNOTES,
    )


def _section_html(section: SectionModel) -> str:
    parts = [f"<section><h2>{_esc(section.title)}</h2>"]
    if section.no_events_note:
        parts.append(f'<p class="note">{_esc(section.no_events_note)}</p>')
    if section.svg is not None:
        parts.append(f"<figure>{section.svg}</figure>")
    else:
        parts.append(f'<p class="empty">{_esc(section.empty_statement or "")}</p>')
    parts.append(f'<p class="note">{_esc(section.note)}</p>')
    if section.extra_note:
        parts.append(f'<p class="note">{_esc(section.extra_note)}</p>')
    parts.append("</section>")
    return "".join(parts)


def render_page(model: PageModel) -> str:
    """The self-contained chart page for one page model."""
    head = [f"<h1>{_esc(model.title)}</h1>"]
    legend: list[str] = []
    for item in model.header:
        if item.role == "legend":
            legend.append(f"<span>{_esc(item.text)}</span>")
            continue
        head.append(f'<p class="{item.role}">{_esc(item.text)}</p>')
    if legend:
        head.append('<p class="legend">' + "".join(legend) + "</p>")
    footer = [f"<h2>{_esc(model.footnotes_heading)}</h2>", '<ul class="footnotes">']
    footer.extend(f"<li>{_esc(note)}</li>" for note in model.footnotes)
    footer.append("</ul>")
    return (
        "<!doctype html>\n"
        '<html lang="zh-Hant-TW"><head><meta charset="utf-8">'
        f"<title>{_esc(model.title)}</title><style>{_CSS}</style></head><body><main>"
        + "".join(head)
        + "".join(_section_html(section) for section in model.sections)
        + "".join(footer)
        + "</main></body></html>\n"
    )


def render_html(report: EventStudyReport, *, dividend_note: str, generated_at: str) -> str:
    """The self-contained chart page for one report (CLI ``--html``)."""
    return render_page(
        build_page_model(report, dividend_lines=(dividend_note,), generated_at=generated_at)
    )


# --- CSS -------------------------------------------------------------------------

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


__all__ = [
    "HeaderItem",
    "PageModel",
    "SectionModel",
    "build_page_model",
    "render_page",
    "render_html",
]
