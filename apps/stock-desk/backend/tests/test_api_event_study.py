"""``POST /api/event-study`` -- the web copy of the CLI chart page.

PRD ``work/stock-desk-事件研究網頁版-PRD.md`` FR-2/FR-3/FR-5: the response
carries exactly the page the CLI renders (same model, same sentences), walks
the backtest's data chain, and degrades to ``insufficient_data`` the way every
other endpoint does.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.api.event_study import WEB_CHART_WIDTH, taipei_stamp
from app.backtest.event_study import (
    DEMO_DATA_WARNING,
    FOOTNOTES,
    RESEARCH_USE_NOTICE,
    SCOPE_NOTICE,
    dividend_sentence,
    run_event_study,
)
from app.backtest.event_study_charts import (
    CHART_WIDTH,
    HTML_LEGEND_BASELINE,
    HTML_LEGEND_EVENT,
    HTML_LEGEND_SAMPLE,
    PATH_CHART_TITLE,
    QUARTILE_CHART_TITLE,
    RATE_CHART_TITLE,
    RATE_CHART_TITLE_FIRST_HALF,
    RATE_CHART_TITLE_SECOND_HALF,
)
from app.backtest.event_study_page import PageModel, build_page_model
from app.signals.frame import bars_to_frame
from tests.api_helpers import recent_bars
from tests.conftest import ApiHarness
from tests.signals_helpers import bars_from_closes
from tests.test_backtest_strategies import _FIVE_CLOSES, _FIVE_VOLUMES
from tests.test_event_study_wording import _FRONTEND_TERMS, _shared_terms

_END = date(2026, 7, 20)


def _seed(harness: ApiHarness, *, source: str = "fake") -> None:
    bars = recent_bars(_FIVE_CLOSES, symbol="2330", end=_END, source=source)
    # The five-condition fixture needs its volumes to produce events.
    seeded = [
        bar.model_copy(update={"volume": vol}) for bar, vol in zip(bars, _FIVE_VOLUMES, strict=True)
    ]
    harness.price_service.seed("2330", seeded)
    harness.price_service.source = source


def test_event_study_returns_the_cli_page_model(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    response = api_harness.client.post("/api/event-study", json={"symbol": "2330", "market": "TW"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["symbol"] == "2330" and body["market"] == "TW"
    page = body["page"]
    texts = [item["text"] for item in page["header"]]
    roles = [item["role"] for item in page["header"]]
    # ADR-0008 D-2: the head is an ordered list; the client only renders it top to bottom.
    assert texts[0].startswith("日線 ") and "資料來源：fake" in texts[0]
    assert texts[1] == SCOPE_NOTICE
    assert texts[2].startswith("前後對半切點")
    assert texts[3] == RESEARCH_USE_NOTICE
    # 風控 REQ-W12: on the web the stamp refers to this section, not the whole page.
    assert texts[4].startswith("本節產出時間 ") and texts[4].endswith(
        "，為靜態快照，不會自動更新。"
    )
    assert texts[5].startswith("未還原除權息：")
    assert texts[6:] == [HTML_LEGEND_EVENT, HTML_LEGEND_BASELINE, HTML_LEGEND_SAMPLE]
    assert roles == [
        "meta",
        "notice",
        "meta",
        "notice",
        "meta",
        "notice",
        "legend",
        "legend",
        "legend",
    ]
    assert DEMO_DATA_WARNING not in texts
    assert page["footnotes"] == list(FOOTNOTES)
    assert [s["title"] for s in page["sections"]] == [
        PATH_CHART_TITLE,
        RATE_CHART_TITLE,
        RATE_CHART_TITLE_FIRST_HALF,
        RATE_CHART_TITLE_SECOND_HALF,
        QUARTILE_CHART_TITLE,
    ]
    assert [s["key"] for s in page["sections"]] == [
        "path",
        "rate_full",
        "rate_first_half",
        "rate_second_half",
        "quartile",
    ]
    for section in page["sections"]:
        assert section["svg"] is not None and section["svg"].startswith("<svg ")
        assert "<script" not in section["svg"]
        assert section["empty_statement"] is None


def test_event_study_dividend_line_is_the_event_study_sentence_for_the_resolver_code(
    api_harness: ApiHarness,
) -> None:
    # The harness's dividend store has never been synced: the resolver reports
    # ``never_synced`` and the page prints the CLI's own line for that code,
    # never the backtest's 「本回測…」 note.
    _seed(api_harness)
    page = api_harness.client.post("/api/event-study", json={"symbol": "2330"}).json()["page"]
    texts = [item["text"] for item in page["header"]]
    assert dividend_sentence("never_synced", market="TW") in texts
    assert not any(text.startswith("除權息：") for text in texts)
    assert not any("本回測" in text for text in texts)


def test_event_study_flags_demo_data(api_harness: ApiHarness) -> None:
    _seed(api_harness, source="demo_synthetic")
    page = api_harness.client.post("/api/event-study", json={"symbol": "2330"}).json()["page"]
    texts = [item["text"] for item in page["header"]]
    assert DEMO_DATA_WARNING in texts
    # Demo warning sits after the scope notice and before the research-use notice.
    assert (
        texts.index(SCOPE_NOTICE)
        < texts.index(DEMO_DATA_WARNING)
        < texts.index(RESEARCH_USE_NOTICE)
    )


def test_event_study_without_bars_is_insufficient_data(api_harness: ApiHarness) -> None:
    body = api_harness.client.post("/api/event-study", json={"symbol": "9999"}).json()
    assert body["status"] == "insufficient_data"
    assert body["page"] is None
    assert body["reason"]


def test_event_study_rejects_a_reversed_range(api_harness: ApiHarness) -> None:
    response = api_harness.client.post(
        "/api/event-study", json={"symbol": "2330", "start": "2026-01-02", "end": "2025-01-02"}
    )
    assert response.status_code == 422


def test_event_study_rejects_a_symbol_outside_the_whitelist(api_harness: ApiHarness) -> None:
    # ADR-0008 D-4: reject, never partially clean.
    for bad in ("<svg>", "23 30", "2330;drop", ""):
        response = api_harness.client.post("/api/event-study", json={"symbol": bad})
        assert response.status_code == 422, bad


def test_event_study_honours_the_date_window(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    start = (_END - timedelta(days=90)).isoformat()
    page = api_harness.client.post(
        "/api/event-study", json={"symbol": "2330", "start": start, "end": _END.isoformat()}
    ).json()["page"]
    data_line = page["header"][0]["text"]
    assert data_line.startswith("日線 ")
    n_bars = int(data_line.split(" ")[1])
    assert n_bars <= 91


def test_taipei_stamp_format() -> None:
    moment = datetime(2026, 9, 12, 6, 3, tzinfo=ZoneInfo("UTC"))
    assert taipei_stamp(moment) == "2026-09-12 14:03 台北時間"


# --- ADR-0008 D-5: the SVG is the only innerHTML sink, so it must be inert ----------------

#: What must never appear in a string the browser is handed as markup. ``href``
#: covers ``xlink:href`` too; ``on\w+=`` covers every event-handler attribute.
_SVG_FORBIDDEN = (
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"\son\w+\s*=", re.IGNORECASE),
    re.compile(r"<foreignObject", re.IGNORECASE),
    re.compile(r"href", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"<iframe|<object|<embed|<style|<image|<use", re.IGNORECASE),
)


def _web_page_model(*, symbol: str = "2330", source: str = "demo_synthetic") -> PageModel:
    frame = bars_to_frame(bars_from_closes(_FIVE_CLOSES, volumes=_FIVE_VOLUMES))
    report = run_event_study(frame, symbol=symbol, source=source)
    return build_page_model(
        report,
        dividend_lines=[dividend_sentence("never_synced", market="TW")],
        generated_at="2026-09-12 14:03 台北時間",
        chart_width=WEB_CHART_WIDTH,
        generated_at_subject="本節",
    )


def _page_model_text(model: PageModel) -> str:
    """Every string a client could show, SVG text included, as one blob."""
    parts = [model.title, *(item.text for item in model.header)]
    for section in model.sections:
        parts.extend(
            filter(
                None,
                (
                    section.title,
                    section.note,
                    section.extra_note,
                    section.no_events_note,
                    section.empty_statement,
                    section.svg,
                ),
            )
        )
    parts.extend((model.footnotes_heading, *model.footnotes))
    return "\n".join(parts).replace("&amp;", "&")


@pytest.mark.parametrize("pattern", _SVG_FORBIDDEN, ids=lambda p: p.pattern)
def test_every_section_svg_is_free_of_active_content(pattern: re.Pattern[str]) -> None:
    model = _web_page_model()
    assert model.sections and all(s.svg for s in model.sections)
    for section in model.sections:
        assert section.svg is not None
        assert pattern.search(section.svg) is None, (section.key, pattern.pattern)


def test_symbol_and_source_never_reach_the_svg(api_harness: ApiHarness) -> None:
    # D-5's premise: the SVG's text nodes are numbers and module constants only;
    # request-controlled strings stay in the header's plain-text fields.
    model = _web_page_model(symbol="A.B-1", source="fake-source")
    for section in model.sections:
        assert section.svg is not None
        assert "A.B-1" not in section.svg and "fake-source" not in section.svg
    assert "A.B-1" in model.title
    assert any("fake-source" in item.text for item in model.header)
    # And a hostile symbol is refused before any page is built (D-4).
    for bad in ("<svg onload=alert(1)>", '2330"', "2330'"):
        assert api_harness.client.post("/api/event-study", json={"symbol": bad}).status_code == 422


def test_web_charts_use_the_web_width_and_the_cli_width_differs() -> None:
    # ADR-0008 D-8: 800px on the web, never scaled; the CLI page stays at 900px.
    web = _web_page_model()
    for section in web.sections:
        assert section.svg is not None
        assert f'width="{WEB_CHART_WIDTH}"' in section.svg
    assert WEB_CHART_WIDTH == 800 and CHART_WIDTH == 900


# --- PRD AC-7 / ADR-0008 約束 11: the whole page model is scanned, SVG text included ---


@pytest.mark.parametrize("term", _shared_terms() + _FRONTEND_TERMS)
def test_page_model_carries_no_forbidden_term(term: str) -> None:
    assert term not in _page_model_text(_web_page_model())


def test_page_model_has_no_directive_wording() -> None:
    text = _page_model_text(_web_page_model())
    for index in [i for i in range(len(text)) if text.startswith("建議", i)]:
        preceding = text[max(0, index - 8) : index]
        is_module_name = text[index : index + 4] == "建議引擎"
        assert "不是" in preceding or "不構成" in preceding or is_module_name, preceding


def test_api_response_matches_the_page_model_field_for_field(api_harness: ApiHarness) -> None:
    # The endpoint serialises the model as-is: same keys, same order, nothing renamed.
    _seed(api_harness)
    page = api_harness.client.post("/api/event-study", json={"symbol": "2330"}).json()["page"]
    assert list(page) == ["title", "header", "sections", "footnotes_heading", "footnotes"]
    assert list(page["header"][0]) == ["role", "text"]
    assert list(page["sections"][0]) == [
        "key",
        "title",
        "note",
        "extra_note",
        "no_events_note",
        "empty_statement",
        "svg",
    ]


# --- 風控 2026-09-12 複審 R-1: the dividend line is market-aware and one code, one sentence ----

DIVIDEND_SENTENCES_PINNED = {
    ("adjusted", "TW"): "已還原除權息：套用 3 筆事件（比例法 back-adjustment）。",
    ("never_synced", "TW"): (
        "未還原除權息：本機尚未同步過任何除權息資料"
        "（未執行 uv run python -m app.dividends.sync）；報酬若實際有配息會低估。"
    ),
    ("disabled", "TW"): (
        "未還原除權息（--no-adjust-dividends）：報酬不含股利；若該區間實際有配息，報酬會低估。"
    ),
    ("no_events", "TW"): (
        "未還原除權息：本機雖有除權息資料，但查無本商品在此區間的除權息紀錄。"
        "可能是該期間真的沒有配息，也可能是資料覆蓋不足（目前只涵蓋台股上市，不含上櫃），"
        "系統無法分辨兩者；若實際有配息，前瞻報酬會低估。"
    ),
    ("no_events", "US"): (
        "未還原除權息：本系統的除權息資料只涵蓋台股上市，不涵蓋本市場，"
        "不是查無配息，而是沒有資料可查。若本商品有配息，前瞻報酬會低估。"
    ),
    ("unusable_events", "TW"): (
        "未還原除權息：查到本商品在此區間的除權息紀錄，但欄位不足以推算調整因子，"
        "已整筆略過（2 筆）而非用推估值代替；前瞻報酬會低估。"
        "請重跑同步，或回報此代號與區間供人工覆核來源欄位。"
    ),
}


@pytest.mark.parametrize(("code", "market"), sorted(DIVIDEND_SENTENCES_PINNED))
def test_dividend_sentences_are_pinned_verbatim(code: str, market: str) -> None:
    # creative-lead 起草 2026-09-12（work/事件研究-除權息句-起草.md）; 風控覆核中.
    sentence = dividend_sentence(
        code,
        market="US" if market == "US" else "TW",
        events_applied=3,
        events_skipped=2,
    )
    assert sentence == DIVIDEND_SENTENCES_PINNED[(code, market)]
    # Every sentence names its own subject; callers must not prefix it again (S-1).
    assert sentence.startswith(("已還原除權息", "未還原除權息"))


def test_no_events_outside_taiwan_never_claims_nothing_was_found() -> None:
    # The 2026-08-10 red line: 「查無紀錄」 and 「沒有資料可查」 are different facts.
    tw = dividend_sentence("no_events", market="TW")
    us = dividend_sentence("no_events", market="US")
    assert tw != us
    assert "查無本商品" in tw and "查無本商品" not in us
    assert "沒有資料可查" in us
    # And "found rows but could not use them" is not "found nothing".
    unusable = dividend_sentence("unusable_events", market="TW", events_skipped=1)
    assert unusable != tw and "略過（1 筆）" in unusable
    assert "略過" not in tw and "略過" not in us


def test_an_unknown_reason_code_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError):
        dividend_sentence("not_run", market="TW")


def test_event_study_uses_the_taiwan_no_events_sentence_when_the_store_found_nothing(
    api_harness: ApiHarness,
) -> None:
    from tests.test_api_backtest_dividends import _seed_event

    _seed(api_harness)
    _seed_event(api_harness, symbol="2884")  # store synced, nothing for 2330
    page = api_harness.client.post("/api/event-study", json={"symbol": "2330"}).json()["page"]
    texts = [item["text"] for item in page["header"]]
    assert dividend_sentence("no_events", market="TW") in texts
    assert dividend_sentence("never_synced", market="TW") not in texts
    assert not any("本回測" in text for text in texts)


@pytest.mark.parametrize("market", ["TW", "US"])
def test_event_study_route_hands_its_market_to_the_dividend_sentence(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch, market: str
) -> None:
    # A study can never fall back to the Taiwan wording by omission: the route
    # passes its own ``market`` explicitly, and the *value* is the request's
    # (qa 2026-09-12 second round: TW alone could not tell a constant from a variable).
    import app.api.event_study as route

    seen: dict[str, object] = {}

    def spy(code: str, **kwargs: object) -> str:
        seen.update(code=code, **kwargs)
        return dividend_sentence(code, market="TW")

    monkeypatch.setattr(route, "dividend_sentence", spy)
    # The harness resolver serves TW only; lend the same fake service to US so
    # the request reaches the dividend line with a non-TW market.
    from app.api.deps import get_market_resolver
    from app.main import app

    monkeypatch.setitem(
        app.dependency_overrides,
        get_market_resolver,
        lambda: {"TW": api_harness.price_service, "US": api_harness.price_service},
    )
    _seed(api_harness)
    body = api_harness.client.post("/api/event-study", json={"symbol": "2330", "market": market})
    assert body.status_code == 200 and body.json()["status"] == "ok"
    assert seen["code"] == "never_synced" and seen["market"] == market
