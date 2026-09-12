"""``POST /api/event-study`` -- the five-condition event study for the web.

PRD: ``work/stock-desk-事件研究網頁版-PRD.md``. The web section on ``/backtest``
shows the very same five charts and the very same sentences the CLI ``--html``
page does (FR-3): both are rendered from
:func:`app.backtest.event_study_page.build_page_model`, so there is one
definition of every chart and every risk-reviewed sentence. This route only
adds the API envelope (``status`` / ``reason`` / ``data`` / ``as_of``) and walks
the same data chain ``POST /api/backtest`` walks (bars via
:func:`app.services.market.load_bars`, 除權息 via
:func:`app.api.backtest.resolve_dividend_adjustment`), so the source line and
the dividend disclosure say exactly what the backtest report on the same page
says.

The SVG strings are produced here from numbers, with every text node passed
through ``html.escape``; the page embeds them as-is (ADR on the web section).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.backtest import resolve_dividend_adjustment
from app.api.common import EnvelopeBase, data_meta, now_iso
from app.api.deps import get_dividend_store, get_market_resolver
from app.backtest.event_study import dividend_sentence, run_event_study
from app.backtest.event_study_page import PageModel, SectionModel, build_page_model
from app.dividends.store import DividendEventStore
from app.positions.models import Market
from app.services.market import MarketDataResolver, load_bars
from app.signals.frame import bars_to_frame

router = APIRouter(prefix="/api/event-study", tags=["event-study"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
DividendStoreDep = Annotated[DividendEventStore, Depends(get_dividend_store)]

#: The "nothing to compute" guard only: one bar cannot form a single forward
#: return. It is deliberately not a statistical floor -- every mark on every
#: chart carries its own ``n=`` and the footnotes say the samples overlap, so a
#: thin window shows as thin instead of being hidden. (風控 2026-09-12 S-4:
#: whether a substantive minimum belongs here is quant-researcher's call, 列管.)
MIN_BARS = 2

#: The `/backtest` column is 896px minus paddings; the SVGs are built at this
#: width so the page never scales them (風控 REQ-W6: text keeps its reviewed
#: pixel size; narrow viewports scroll the figure horizontally instead).
WEB_CHART_WIDTH = 800


class EventStudySection(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    note: str
    extra_note: str | None
    no_events_note: str | None
    empty_statement: str | None
    #: Inline SVG produced by the backend; ``null`` when ``empty_statement`` is set.
    svg: str | None


class EventStudyHeaderItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    text: str


class EventStudyPage(BaseModel):
    """The page in reading order (mirrors ``PageModel`` field for field; ADR-0008 D-2)."""

    model_config = ConfigDict(frozen=True)

    title: str
    #: Ordered; the client renders these top to bottom and never reorders them.
    header: list[EventStudyHeaderItem]
    sections: list[EventStudySection]
    footnotes_heading: str
    footnotes: list[str]


class EventStudyResponse(EnvelopeBase):
    model_config = ConfigDict(frozen=True)

    #: ``null`` exactly when ``status`` is ``insufficient_data``.
    page: EventStudyPage | None


def _to_section(section: SectionModel) -> EventStudySection:
    return EventStudySection(
        key=section.key,
        title=section.title,
        note=section.note,
        extra_note=section.extra_note,
        no_events_note=section.no_events_note,
        empty_statement=section.empty_statement,
        svg=section.svg,
    )


def _to_page(model: PageModel) -> EventStudyPage:
    return EventStudyPage(
        title=model.title,
        header=[EventStudyHeaderItem(role=item.role, text=item.text) for item in model.header],
        sections=[_to_section(section) for section in model.sections],
        footnotes_heading=model.footnotes_heading,
        footnotes=list(model.footnotes),
    )


#: A real TW/US ticker is letters, digits, ``.`` and ``-`` (``BRK.B``, ``BF-B``);
#: anything else is rejected outright, never partially cleaned (ADR-0008 D-4,
#: the same rule the frontend's TradingView symbol guard applies).
SYMBOL_PATTERN = r"^[A-Za-z0-9.-]+$"


class EventStudyRequest(BaseModel):
    """``POST /api/event-study`` body: the backtest form's own four fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    symbol: str = Field(min_length=1, max_length=32, pattern=SYMBOL_PATTERN)
    market: Market = "TW"
    start: date = date(1900, 1, 1)
    end: date = date(2100, 1, 1)

    @model_validator(mode="after")
    def _check_window(self) -> EventStudyRequest:
        if self.end < self.start:
            raise ValueError("end 不可早於 start")
        return self


def taipei_stamp(now: datetime | None = None) -> str:
    """The 產出時間 stamp the page prints (風控 R8), Asia/Taipei wall time."""
    moment = now if now is not None else datetime.now(ZoneInfo("Asia/Taipei"))
    return moment.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M 台北時間")


@router.post("", response_model=EventStudyResponse)
def run_event_study_for_web(
    body: EventStudyRequest,
    resolver: ResolverDep,
    dividend_store: DividendStoreDep,
) -> EventStudyResponse:
    symbol, market, start, end = body.symbol, body.market, body.start, body.end
    loaded = load_bars(resolver, symbol=symbol, market=market, start=start, end=end)
    if not loaded.bars or len(loaded.bars) < MIN_BARS:
        reason = loaded.reason or (
            f"區間內只有 {len(loaded.bars)} 根日線，事件研究至少需要 {MIN_BARS} 根。"
        )
        return EventStudyResponse(
            symbol=symbol,
            market=market,
            status="insufficient_data",
            reason=reason,
            page=None,
            data=data_meta(loaded.meta()),
            as_of=now_iso(),
        )

    # Always attempt the adjustment (PRD: no user switch). The outcome code and
    # counts come from the backtest's own resolver; the sentence is the event
    # study's reviewed line for that code, not the backtest's 「本回測…」 note.
    dividends = resolve_dividend_adjustment(
        loaded.bars, requested=True, symbol=symbol, market=market, store=dividend_store
    )
    block = dividends.block
    dividend_line = dividend_sentence(
        str(block["reason_code"]),
        market=market,
        events_applied=int(block.get("events_applied") or 0),
        events_skipped=int(block.get("events_skipped") or 0),
    )
    report = run_event_study(
        bars_to_frame(dividends.bars), symbol=symbol, market=market, source=loaded.source
    )
    model = build_page_model(
        report,
        dividend_lines=(dividend_line,),
        generated_at=taipei_stamp(),
        chart_width=WEB_CHART_WIDTH,
        generated_at_subject="本節",
    )
    return EventStudyResponse(
        symbol=symbol,
        market=market,
        status="ok",
        reason=None,
        page=_to_page(model),
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )
