"""ADR-0021: the evaluability invariant of rule and alert fields.

The vocabulary is layered. ``KNOWN_FIELDS`` is the *readable* superset -- what a
stored rule may name and what ``build_context`` produces -- and each rule
consumer has its own *creatable* subset (``ADVICE_RULE_FIELDS``,
``ALERT_RULE_FIELDS``) of the fields its pipeline can actually produce. These
tests pin that split from both sides:

* T-1 runs the real pipelines on ample synthetic data and checks that every
  field of a creatable set comes out non-``None`` and every field outside it
  comes out ``None`` -- so the sets cannot claim a field the pipeline does not
  produce, nor omit one it does.
* T-2 inserts old rules naming the excluded fields straight into SQLite and
  checks they still list, skip, disable and delete (K-4 / K-5 / K-6).
* T-3 checks a *submitted* rule naming one is a 422 (K-4).
* T-5 reads the front end's field menu out of ``format.ts`` and its set of
  unevaluable fields out of ``alertFields.ts`` (K-9, 風控 U-5 (i)).
* T-6 checks advice and alerts never touch the index resolver (K-7).
* K-8's start-up diagnostic counts such rules and changes none of them.

T-4 (the advice rule-file loader) lives in ``tests/test_advice_loader.py`` with
the other loader tests.

The two user-facing sentences -- an old rule's skip reason (W-2) and the 422
message (W-4) -- are pinned verbatim as risk-compliance-officer approved them
on 2026-10-06 (`work/reviews/2026-10-06-ADR-0021-警示欄位可評估性-字面-風控審查.md`,
核可字面總表). The expected strings are transcribed from that table by hand,
not built from the production templates: a test that imports the template it
checks would pass on any rewrite. Changing a character goes back to them.

Everything here is offline: fake price services, ``tmp_path`` databases.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app import scheduler as scheduler_module
from app.advice import engine as advice_engine
from app.advice.context import (
    ADVICE_RULE_FIELDS,
    ALERT_RULE_FIELDS,
    FIELD_LABELS,
    KNOWN_FIELDS,
    build_context,
)
from app.advice.limits import PortfolioContext, RiskBudget
from app.advice.loader import BANNED_PHRASES, Comparison
from app.alerts.engine import count_unevaluable_rules, evaluate_alerts, signal_context
from app.alerts.models import AlertRuleInput
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.data.interface import PriceBar
from app.kelly.store import KellyInputStore
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore
from app.settings.store import SettingsStore
from tests.advice_helpers import uptrend_signals
from tests.alerts_helpers import RecordingLoader, add_rule, signal_rule, snapshot
from tests.api_helpers import FakePriceService, UnavailableFxProvider, position_payload
from tests.conftest import ApiHarness
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

SYMBOL = "2330"

#: The fields ADR-0021 K-1 removes from each creatable set.
ADVICE_EXCLUDED = frozenset({"beta.value"})
ALERT_EXCLUDED = frozenset({"beta.value", "position.weight", "position.unrealized_pnl_pct"})

#: ADR-0021 W-2, the three approved expansions, verbatim (核可字面總表).
W2_SKIP_REASON: dict[str, str] = {
    "beta.value": (
        "此規則使用的 beta.value（相對指標的 beta），警示不提供作為條件。"
        "每次檢查都會略過此規則，不會觸發。可改用其他欄位的條件，或刪除此規則。"
    ),
    "position.weight": (
        "此規則使用的 position.weight（此標的佔投資組合比重），警示不提供作為條件。"
        "每次檢查都會略過此規則，不會觸發。可改用其他欄位的條件，或刪除此規則。"
    ),
    "position.unrealized_pnl_pct": (
        "此規則使用的 position.unrealized_pnl_pct（此部位未實現損益率），警示不提供作為條件。"
        "每次檢查都會略過此規則，不會觸發。可改用其他欄位的條件，或刪除此規則。"
    ),
}

#: ADR-0021 W-4, the three approved expansions, verbatim (核可字面總表). Note
#: the closing full-width bracket runs straight into 作為, with no space.
W4_REJECTION: dict[str, str] = {
    "beta.value": "警示不提供 beta.value（相對指標的 beta）作為條件，請改用其他欄位。",
    "position.weight": (
        "警示不提供 position.weight（此標的佔投資組合比重）作為條件，請改用其他欄位。"
    ),
    "position.unrealized_pnl_pct": (
        "警示不提供 position.unrealized_pnl_pct（此部位未實現損益率）作為條件，請改用其他欄位。"
    ),
}

BACKEND_ROOT = Path(__file__).resolve().parents[1]
STOCK_DESK_ROOT = BACKEND_ROOT.parent
FRONTEND_FORMAT = BACKEND_ROOT.parent / "frontend" / "app" / "lib" / "format.ts"
FRONTEND_ALERT_FIELDS = BACKEND_ROOT.parent / "frontend" / "app" / "lib" / "alertFields.ts"

_AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def _ample_bars(count: int = 540, *, end: date | None = None) -> list[PriceBar]:
    """``count`` consecutive daily bars ending ``end`` (default today), rich enough
    for every indicator: a drifting, oscillating close with a real high/low range
    and a volume that varies, so no indicator degenerates to a zero spread."""
    last = end if end is not None else date.today()
    bars: list[PriceBar] = []
    for index in range(count):
        close = 100.0 + 0.05 * index + 8.0 * math.sin(index / 6.0)
        bars.append(
            PriceBar(
                symbol=SYMBOL,
                market="TW",
                date=last - timedelta(days=count - 1 - index),
                open=Decimal(f"{close - 0.4:.4f}"),
                high=Decimal(f"{close + 1.5:.4f}"),
                low=Decimal(f"{close - 1.5:.4f}"),
                close=Decimal(f"{close:.4f}"),
                volume=10_000 + 3_000 * (index % 7) + 500 * (index % 3),
                currency="TWD",
                as_of=_AS_OF,
                source="fake",
            )
        )
    return bars


def _legacy_params(field: str, *, ref: bool = False) -> dict[str, Any]:
    """A stored ``signal_condition`` params document, as the store serialises it."""
    if ref:
        return {"condition": {"field": "close", "op": "gt", "value": None, "ref": field}}
    return {"condition": {"field": field, "op": "gt", "value": 0.5, "ref": None}}


def _insert_legacy_rule(db_path: Path, params: dict[str, Any], *, enabled: bool = True) -> int:
    """Write a rule row directly, bypassing every model -- the shape an older
    build could have left in the database."""
    moment = datetime(2026, 9, 1, tzinfo=UTC).isoformat()
    with closing(sqlite3.connect(db_path)) as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO alert_rules
                (type, symbol, market, params, enabled, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "signal_condition",
                SYMBOL,
                "TW",
                json.dumps(params, ensure_ascii=False),
                int(enabled),
                None,
                moment,
                moment,
            ),
        )
        return int(cursor.lastrowid or 0)


# --- K-1 / K-2: the sets themselves --------------------------------------------


def test_k1_the_creatable_sets_are_the_readable_set_minus_the_unproducible_fields() -> None:
    assert ADVICE_RULE_FIELDS == KNOWN_FIELDS - ADVICE_EXCLUDED
    assert ALERT_RULE_FIELDS == KNOWN_FIELDS - ALERT_EXCLUDED
    assert ALERT_RULE_FIELDS <= ADVICE_RULE_FIELDS <= KNOWN_FIELDS


def test_k2_beta_stays_readable_and_labelled() -> None:
    # Removing it from the readable set would make every stored beta rule fail
    # to load and take ``list_rules`` -- and so every tick -- down with it.
    assert "beta.value" in KNOWN_FIELDS
    assert FIELD_LABELS["beta.value"] == "相對指標的 beta"
    assert "beta.value" in build_context({}, PortfolioContext(symbol=SYMBOL))
    assert Comparison(field="beta.value", op="gt", value=1.0).field == "beta.value"
    assert Comparison(field="close", op="gt", ref="beta.value").ref == "beta.value"


# --- T-1: the sets match what the pipelines produce ------------------------------


def test_t1_the_alert_snapshot_produces_exactly_the_alert_fields(tmp_path: Path) -> None:
    prices = FakePriceService({SYMBOL: _ample_bars()})
    snap = build_snapshot(
        SYMBOL,
        "TW",
        resolver={"TW": prices},
        store=PositionStore(db_path=tmp_path / "positions.db"),
        valuator=PositionValuator(
            market_services={"TW": prices}, fx_provider=UnavailableFxProvider()
        ),
        budget=RiskBudget(),
    )
    context = signal_context(snap)
    assert set(context) == KNOWN_FIELDS
    missing = sorted(path for path in ALERT_RULE_FIELDS if context[path] is None)
    assert missing == [], f"ALERT_RULE_FIELDS 中這些欄位在資料充足時仍為 None：{missing}"
    produced = sorted(
        path for path in KNOWN_FIELDS - ALERT_RULE_FIELDS if context[path] is not None
    )
    assert produced == [], f"這些欄位警示端產得出來，卻不在 ALERT_RULE_FIELDS：{produced}"


def test_t1_every_alert_field_is_evaluated_by_the_engine(tmp_path: Path) -> None:
    # The same check one level up: a rule per creatable field, run through the
    # real engine on a real snapshot, is never skipped -- and a rule per
    # excluded field (stored through the readable model) always is.
    prices = FakePriceService({SYMBOL: _ample_bars()})
    snap = build_snapshot(
        SYMBOL,
        "TW",
        resolver={"TW": prices},
        store=PositionStore(db_path=tmp_path / "positions.db"),
        valuator=PositionValuator(
            market_services={"TW": prices}, fx_provider=UnavailableFxProvider()
        ),
        budget=RiskBudget(),
    )
    store = AlertStore(db_path=tmp_path / "alerts.db")
    field_of: dict[int, str] = {}
    for path in sorted(KNOWN_FIELDS):
        rule = add_rule(store, signal_rule(field=path, op="abs_gt", value=-1.0))
        field_of[rule.id] = path
    result = evaluate_alerts(store, RecordingLoader(snap), cooldown_minutes=0)
    skipped = sorted(field_of[o.rule_id] for o in result.outcomes if o.status == "skipped")
    assert skipped == sorted(KNOWN_FIELDS - ALERT_RULE_FIELDS)


def test_t1_the_advice_card_produces_exactly_the_advice_fields(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_harness.price_service.seed(SYMBOL, _ample_bars())
    created = api_harness.client.post("/api/positions", json=position_payload())
    assert created.status_code == 201
    seen: list[dict[str, float | None]] = []

    def recording_build_context(
        signals: Any, portfolio: PortfolioContext
    ) -> dict[str, float | None]:
        context = build_context(signals, portfolio)
        seen.append(context)
        return context

    monkeypatch.setattr(advice_engine, "build_context", recording_build_context)
    response = api_harness.client.get(f"/api/advice/{SYMBOL}")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert len(seen) == 1
    context = seen[0]
    missing = sorted(path for path in ADVICE_RULE_FIELDS if context[path] is None)
    assert missing == [], f"ADVICE_RULE_FIELDS 中這些欄位在資料充足時仍為 None：{missing}"
    produced = sorted(
        path for path in KNOWN_FIELDS - ADVICE_RULE_FIELDS if context[path] is not None
    )
    assert produced == [], f"這些欄位建議卡產得出來，卻不在 ADVICE_RULE_FIELDS：{produced}"


# --- T-2: old rules stay readable, skippable, editable and deletable -------------


LEGACY_CASES = [
    pytest.param(path, ref, id=f"{path}-{'ref' if ref else 'field'}")
    for path in sorted(ALERT_EXCLUDED)
    for ref in (False, True)
]


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
def test_t2_an_old_rule_lists_and_reads(api_harness: ApiHarness, path: str, ref: bool) -> None:
    rule_id = _insert_legacy_rule(api_harness.alerts.db_path, _legacy_params(path, ref=ref))
    stored = api_harness.alerts.get_rule(rule_id)
    assert stored is not None
    assert [rule.id for rule in api_harness.alerts.list_rules()] == [rule_id]
    assert [rule.id for rule in api_harness.alerts.list_rules(enabled_only=True)] == [rule_id]

    response = api_harness.client.get("/api/alerts")
    assert response.status_code == 200
    condition = response.json()["items"][0]["params"]["condition"]
    assert (condition["ref"] if ref else condition["field"]) == path


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
def test_t2_an_old_rule_is_skipped_by_the_api_tick(
    api_harness: ApiHarness, path: str, ref: bool
) -> None:
    api_harness.price_service.seed(SYMBOL, _ample_bars())
    rule_id = _insert_legacy_rule(api_harness.alerts.db_path, _legacy_params(path, ref=ref))
    response = api_harness.client.post("/api/alerts/evaluate")
    assert response.status_code == 200
    body = response.json()
    assert body["fired"] == 0
    [outcome] = body["outcomes"]
    assert outcome["rule_id"] == rule_id
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == W2_SKIP_REASON[path]


def test_t2_membership_not_the_value_decides_the_skip(tmp_path: Path) -> None:
    # K-6: even on a snapshot whose signal layer *did* carry a beta (as
    # ``/api/signals`` would), a stored beta rule is skipped, never fired or
    # quiet -- the alert path is not the place that value is meant to come from.
    store = AlertStore(db_path=tmp_path / "alerts.db")
    beta_rule = store.create_rule(
        AlertRuleInput.model_validate(signal_rule(field="beta.value", op="gt", value=1.0))
    )
    snap = snapshot(signals=uptrend_signals(beta=1.5))
    assert signal_context(snap)["beta.value"] == 1.5
    result = evaluate_alerts(store, RecordingLoader(snap), cooldown_minutes=0)
    [outcome] = result.outcomes
    assert outcome.rule_id == beta_rule.id
    assert outcome.status == "skipped"
    assert result.events == []


def test_t2_the_permanent_cause_is_reported_ahead_of_a_thin_snapshot(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "alerts.db")
    store.create_rule(AlertRuleInput.model_validate(signal_rule(field="beta.value")))
    thin = snapshot(close=None, signals={}, reason="資料暫時無法取得。")
    [outcome] = evaluate_alerts(store, RecordingLoader(thin)).outcomes
    assert outcome.status == "skipped"
    assert outcome.reason != thin.reason


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
@pytest.mark.parametrize(
    "patch",
    [{"enabled": False}, {"note": "舊規則"}, {"clear_note": True}, {"symbol": "2317"}],
    ids=["enabled", "note", "clear_note", "symbol"],
)
def test_t2_an_old_rule_can_be_patched_without_new_params(
    api_harness: ApiHarness, path: str, ref: bool, patch: dict[str, Any]
) -> None:
    params = _legacy_params(path, ref=ref)
    rule_id = _insert_legacy_rule(api_harness.alerts.db_path, params)
    response = api_harness.client.patch(f"/api/alerts/{rule_id}", json=patch)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == rule_id
    assert body["params"] == params
    for key, value in patch.items():
        if key != "clear_note":
            assert body[key] == value


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
def test_t2_an_old_rule_can_be_deleted(api_harness: ApiHarness, path: str, ref: bool) -> None:
    rule_id = _insert_legacy_rule(api_harness.alerts.db_path, _legacy_params(path, ref=ref))
    assert api_harness.client.delete(f"/api/alerts/{rule_id}").status_code == 204
    assert api_harness.client.get("/api/alerts").json()["items"] == []


# --- T-3: a submitted rule naming an excluded field is a 422 ----------------------


def _submitted(path: str, *, ref: bool) -> dict[str, Any]:
    payload = signal_rule(field=path)
    if ref:
        payload["params"] = {"condition": {"field": "close", "op": "gt", "ref": path}}
    return payload


def _assert_rejected(response: Any, path: str) -> None:
    """A 422 whose only error is the approved W-4 sentence for ``path``, as is:
    no ``Value error, `` prefix (風控 required 3), located at ``params``."""
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert [(error["loc"], error["msg"]) for error in detail] == [
        (["body", "params"], W4_REJECTION[path])
    ]


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
def test_t3_post_rejects_an_excluded_field(api_harness: ApiHarness, path: str, ref: bool) -> None:
    _assert_rejected(api_harness.client.post("/api/alerts", json=_submitted(path, ref=ref)), path)
    assert api_harness.client.get("/api/alerts").json()["items"] == []


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
def test_t3_put_rejects_an_excluded_field(api_harness: ApiHarness, path: str, ref: bool) -> None:
    created = api_harness.client.post("/api/alerts", json=signal_rule()).json()
    response = api_harness.client.put(
        f"/api/alerts/{created['id']}", json=_submitted(path, ref=ref)
    )
    _assert_rejected(response, path)
    [stored] = api_harness.client.get("/api/alerts").json()["items"]
    assert stored["params"] == created["params"]


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
def test_t3_patch_rejects_excluded_params(api_harness: ApiHarness, path: str, ref: bool) -> None:
    created = api_harness.client.post("/api/alerts", json=signal_rule()).json()
    response = api_harness.client.patch(
        f"/api/alerts/{created['id']}", json={"params": _submitted(path, ref=ref)["params"]}
    )
    _assert_rejected(response, path)
    [stored] = api_harness.client.get("/api/alerts").json()["items"]
    assert stored["params"] == created["params"]


@pytest.mark.parametrize(("path", "ref"), LEGACY_CASES)
def test_t3_an_old_rule_cannot_be_resubmitted_as_is(
    api_harness: ApiHarness, path: str, ref: bool
) -> None:
    # Keeping the stored params is a PATCH without ``params``; sending them back
    # in a PUT is a new submission and held to the creatable set.
    params = _legacy_params(path, ref=ref)
    rule_id = _insert_legacy_rule(api_harness.alerts.db_path, params)
    body = {**signal_rule(), "params": params}
    _assert_rejected(api_harness.client.put(f"/api/alerts/{rule_id}", json=body), path)
    _assert_rejected(
        api_harness.client.patch(f"/api/alerts/{rule_id}", json={"params": params}), path
    )
    stored = api_harness.alerts.get_rule(rule_id)
    assert stored is not None
    assert stored.params.model_dump() == params


@pytest.mark.parametrize("path", sorted(ALERT_RULE_FIELDS))
def test_t3_every_alert_field_is_still_accepted(api_harness: ApiHarness, path: str) -> None:
    # The other side of the 422: the check must not reject a creatable field.
    assert api_harness.client.post("/api/alerts", json=signal_rule(field=path)).status_code == 201
    ref = {"condition": {"field": "close", "op": "gt", "ref": path}}
    assert (
        api_harness.client.post("/api/alerts", json=_submitted(path, ref=True)).status_code == 201
    )
    created = api_harness.client.post("/api/alerts", json=signal_rule()).json()
    response = api_harness.client.patch(f"/api/alerts/{created['id']}", json={"params": ref})
    assert response.status_code == 200


# --- W-2 / W-4: which field is named, and what else is left alone --------------


#: (field, ref) pairs naming two excluded fields; the sentence names the first,
#: i.e. the comparison's ``field`` (風控 required 3).
TWO_EXCLUDED = [
    pytest.param("beta.value", "position.weight", id="beta-then-weight"),
    pytest.param("position.weight", "beta.value", id="weight-then-beta"),
    pytest.param("position.unrealized_pnl_pct", "beta.value", id="pnl-then-beta"),
]


@pytest.mark.parametrize(("first", "second"), TWO_EXCLUDED)
def test_w4_names_the_first_of_two_excluded_fields(
    api_harness: ApiHarness, first: str, second: str
) -> None:
    params = {"condition": {"field": first, "op": "gt", "ref": second}}
    _assert_rejected(
        api_harness.client.post("/api/alerts", json={**signal_rule(), "params": params}), first
    )
    created = api_harness.client.post("/api/alerts", json=signal_rule()).json()
    _assert_rejected(
        api_harness.client.put(
            f"/api/alerts/{created['id']}", json={**signal_rule(), "params": params}
        ),
        first,
    )
    _assert_rejected(
        api_harness.client.patch(f"/api/alerts/{created['id']}", json={"params": params}), first
    )


@pytest.mark.parametrize(("first", "second"), TWO_EXCLUDED)
def test_w2_names_the_first_of_two_excluded_fields(tmp_path: Path, first: str, second: str) -> None:
    store = AlertStore(db_path=tmp_path / "alerts.db")
    _insert_legacy_rule(
        store.db_path,
        {"condition": {"field": first, "op": "gt", "value": None, "ref": second}},
    )
    [outcome] = evaluate_alerts(
        store, RecordingLoader(snapshot(signals=uptrend_signals()))
    ).outcomes
    assert outcome.status == "skipped"
    assert outcome.reason == W2_SKIP_REASON[first]


def test_w_r4_a_value_only_edit_of_an_old_beta_rule_reports_w4_at_params(
    api_harness: ApiHarness,
) -> None:
    # 風控 W-R4: the edit dialog sends the whole ``params`` document when only
    # the threshold changed. The front end must surface W-4 from this exact
    # ``loc`` rather than drop it, so the location is pinned here.
    params = _legacy_params("beta.value")
    rule_id = _insert_legacy_rule(api_harness.alerts.db_path, params)
    edited = {"condition": {**params["condition"], "value": 1.2}}
    response = api_harness.client.patch(f"/api/alerts/{rule_id}", json={"params": edited})
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "params"]
    assert error["msg"] == W4_REJECTION["beta.value"]
    stored = api_harness.alerts.get_rule(rule_id)
    assert stored is not None
    assert stored.params.model_dump() == params


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (
            {"field": "rsi14.last", "op": "gt", "value": 70.0},
            "缺少輸入欄位：rsi14.last（14 日 RSI 最新值）",
        ),
        (
            {"field": "close", "op": "gt", "ref": "ma60.last"},
            "缺少輸入欄位：ma60.last（60 日均線最新值）",
        ),
    ],
    ids=["field", "ref"],
)
def test_k10_a_genuinely_missing_alert_field_keeps_the_existing_reason(
    tmp_path: Path, condition: dict[str, Any], expected: str
) -> None:
    # Only the excluded fields moved to W-2; a creatable field that is merely
    # missing on this tick keeps the "missing input" sentence word for word.
    store = AlertStore(db_path=tmp_path / "alerts.db")
    add_rule(store, {**signal_rule(), "params": {"condition": condition}})
    thin_signals = uptrend_signals(rsi=None, ma=None)
    [outcome] = evaluate_alerts(store, RecordingLoader(snapshot(signals=thin_signals))).outcomes
    assert outcome.status == "skipped"
    assert outcome.reason == expected


def _shared_forbidden_terms() -> tuple[str, ...]:
    payload = json.loads(
        (STOCK_DESK_ROOT / "shared" / "forbidden-terms.json").read_text(encoding="utf-8")
    )
    return tuple(payload["guarantee"]) + tuple(payload["price_target"])


@pytest.mark.parametrize(
    "text",
    [*W2_SKIP_REASON.values(), *W4_REJECTION.values()],
)
def test_w2_and_w4_pass_the_wording_scans(text: str) -> None:
    # 風控 required 5: the same scans every other reviewed string goes through.
    terms = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert [term for term in sorted(terms) if term in text] == []
    assert find_bare_realtime_claims(text) == []


# --- T-5: the front end's field menu --------------------------------------------


def _front_end_signal_field_options() -> dict[str, str]:
    """``SIGNAL_FIELD_OPTIONS`` (value -> label) as declared in ``format.ts``.

    Read out of the TypeScript source rather than mirrored here: the two lists
    are hand-copied, and this test is what keeps them from drifting.
    """
    source = FRONTEND_FORMAT.read_text(encoding="utf-8")
    block = re.search(r"SIGNAL_FIELD_OPTIONS\b[^=]*=\s*\[(.*?)\];", source, re.S)
    assert block is not None, f"SIGNAL_FIELD_OPTIONS not found in {FRONTEND_FORMAT}"
    pairs = re.findall(r'\{\s*value:\s*"([^"]+)",\s*label:\s*"([^"]*)"\s*,?\s*\}', block.group(1))
    assert pairs, "SIGNAL_FIELD_OPTIONS parsed as empty"
    options = dict(pairs)
    assert len(options) == len(pairs), "SIGNAL_FIELD_OPTIONS lists a value twice"
    return options


def _front_end_unevaluable_alert_fields() -> dict[str, str]:
    """``UNEVALUABLE_ALERT_FIELDS`` with ``UNEVALUABLE_ALERT_FIELD_LABELS``, as
    declared in ``alertFields.ts`` (field -> legacy label)."""
    source = FRONTEND_ALERT_FIELDS.read_text(encoding="utf-8")
    block = re.search(r"UNEVALUABLE_ALERT_FIELDS\s*=\s*\[(.*?)\]\s*as\s+const", source, re.S)
    assert block is not None, f"UNEVALUABLE_ALERT_FIELDS not found in {FRONTEND_ALERT_FIELDS}"
    fields = re.findall(r'"([^"]+)"', block.group(1))
    labels_block = re.search(r"UNEVALUABLE_ALERT_FIELD_LABELS\b[^=]*=\s*\{(.*?)\};", source, re.S)
    assert labels_block is not None, "UNEVALUABLE_ALERT_FIELD_LABELS not found"
    labels = dict(re.findall(r'"([^"]+)":\s*"([^"]*)"', labels_block.group(1)))
    assert fields, "UNEVALUABLE_ALERT_FIELDS parsed as empty"
    assert len(set(fields)) == len(fields), "UNEVALUABLE_ALERT_FIELDS lists a field twice"
    assert set(labels) == set(fields), "every unevaluable field needs exactly one legacy label"
    return {field: labels[field] for field in fields}


def test_t5_the_front_end_menu_offers_only_alert_fields_labelled_as_the_back_end() -> None:
    # A subset check, not equality: whether ``drawdown.current`` belongs in the
    # menu is product-manager's call (ADR-0021 T-5).
    options = _front_end_signal_field_options()
    assert "beta.value" not in options
    assert set(options) <= ALERT_RULE_FIELDS
    for value, label in options.items():
        assert label == FIELD_LABELS[value], f"「{value}」的前端標籤與 FIELD_LABELS 不一致"


def test_t5_the_front_end_unevaluable_set_mirrors_the_back_end_both_ways() -> None:
    # 風控 U-5 (i): the front end decides W-3 by this set alone, so it must equal
    # KNOWN_FIELDS - ALERT_RULE_FIELDS exactly -- a field missing on the front
    # end would hide W-3, an extra one would show it on a rule that does fire.
    unevaluable = _front_end_unevaluable_alert_fields()
    assert set(unevaluable) == KNOWN_FIELDS - ALERT_RULE_FIELDS
    for field, label in unevaluable.items():
        assert label == FIELD_LABELS[field], f"「{field}」的前端舊規則標籤與 FIELD_LABELS 不一致"
    assert not set(unevaluable) & set(_front_end_signal_field_options())


# --- T-6 / K-7: no benchmark, no index resolver ----------------------------------


def test_t6_the_advice_card_never_reads_an_index_series(api_harness: ApiHarness) -> None:
    api_harness.price_service.seed(SYMBOL, _ample_bars())
    api_harness.client.post("/api/positions", json=position_payload())
    response = api_harness.client.get(f"/api/advice/{SYMBOL}")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert api_harness.index_service.calls == []
    assert api_harness.index_service.cached_calls == []


def test_t6_the_alert_tick_never_reads_an_index_series(api_harness: ApiHarness) -> None:
    api_harness.price_service.seed(SYMBOL, _ample_bars())
    api_harness.client.post("/api/alerts", json=signal_rule(field="rsi14.last", value=-1.0))
    body = api_harness.client.post("/api/alerts/evaluate").json()
    assert [outcome["status"] for outcome in body["outcomes"]] == ["fired"]
    assert api_harness.index_service.calls == []
    assert api_harness.index_service.cached_calls == []


def test_t6_the_scheduled_tick_never_reads_an_index_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prices = FakePriceService({SYMBOL: _ample_bars()})
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    kelly = KellyInputStore(db_path=tmp_path / "kelly.db")
    positions = PositionStore(db_path=tmp_path / "positions.db")
    settings = SettingsStore(db_path=tmp_path / "settings.db")
    index_calls: list[str] = []

    def recording_index_resolver() -> object:
        index_calls.append("get_index_resolver")
        return {}

    def recording_benchmark(*_args: object, **_kwargs: object) -> object:
        index_calls.append("load_market_benchmark")
        raise AssertionError("the alert tick must not load a benchmark (ADR-0021 K-7)")

    monkeypatch.setattr(scheduler_module, "get_position_store", lambda: positions)
    monkeypatch.setattr(scheduler_module, "get_alert_store", lambda: alerts)
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: settings)
    monkeypatch.setattr(scheduler_module, "get_market_resolver", lambda: {"TW": prices})
    monkeypatch.setattr(
        scheduler_module,
        "get_valuator",
        lambda: PositionValuator(
            market_services={"TW": prices}, fx_provider=UnavailableFxProvider()
        ),
    )
    monkeypatch.setattr(scheduler_module, "get_kelly_input_store", lambda: kelly)
    monkeypatch.setattr(scheduler_module, "get_index_resolver", recording_index_resolver)
    monkeypatch.setattr(scheduler_module, "load_market_benchmark", recording_benchmark)
    add_rule(alerts, signal_rule(field="rsi14.last", value=-1.0))

    assert scheduler_module.evaluate_alerts_tick() == 1
    assert index_calls == []


@pytest.mark.parametrize(
    "module_name",
    ["app.api.advice", "app.advice.engine", "app.alerts.engine", "app.alerts.snapshot"],
)
def test_t6_advice_and_alert_modules_do_not_import_the_benchmark_loader(module_name: str) -> None:
    # The static half of K-7: the dynamic tests above catch a call through the
    # wired resolvers, this catches the import that would precede one.
    import importlib

    module = importlib.import_module(module_name)
    for name in ("load_market_benchmark", "get_index_resolver", "IndexServiceResolver"):
        assert not hasattr(module, name), f"{module_name} imports {name}"


# --- K-8: start-up diagnostic, read-only -----------------------------------------


def test_k8_the_diagnostic_counts_enabled_unevaluable_rules_and_changes_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = AlertStore(db_path=tmp_path / "alerts.db")
    _insert_legacy_rule(store.db_path, _legacy_params("beta.value"))
    _insert_legacy_rule(store.db_path, _legacy_params("position.weight", ref=True))
    _insert_legacy_rule(store.db_path, _legacy_params("beta.value"), enabled=False)
    add_rule(store, signal_rule(field="rsi14.last"))
    before = store.list_rules()

    assert count_unevaluable_rules(before) == 3
    with caplog.at_level(logging.INFO, logger=scheduler_module.logger.name):
        assert scheduler_module.log_unevaluable_alert_rules(store) == 2

    assert store.list_rules() == before
    [record] = [r for r in caplog.records if "alert rule diagnostic" in r.getMessage()]
    # A count and nothing else: no symbol, no field name, no rule id.
    message = record.getMessage()
    assert "2" in message
    assert SYMBOL not in message
    assert "beta" not in message


def test_k8_the_diagnostic_never_stops_the_start_up(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenStore:
        def list_rules(self, *, enabled_only: bool = False) -> list[Any]:
            raise sqlite3.OperationalError("database is locked")

    with caplog.at_level(logging.ERROR, logger=scheduler_module.logger.name):
        assert scheduler_module.log_unevaluable_alert_rules(BrokenStore()) is None  # type: ignore[arg-type]
