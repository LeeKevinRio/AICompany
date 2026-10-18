"""R-1: push-channel secrets and data-source API keys never reach a log line.

Every secret below is a fake value, every request goes to ``httpx.MockTransport``
and nothing reaches the network. Sections follow the security acceptance grid
(work/reviews/2026-10-18-R1推播token外洩評估-security-engineer.md, D-1..D-9).
"""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import app.scheduler as scheduler_module
from app.alerts import notify as notify_module
from app.alerts.models import AlertEvent
from app.alerts.notify import (
    DISCORD_WEBHOOK_ENV,
    TELEGRAM_CHAT_ID_ENV,
    TELEGRAM_TOKEN_ENV,
    DeliveryResult,
    notify,
)
from app.data.http import RateLimitedClient
from app.data.providers.alpha_vantage import API_KEY_ENV_VAR, AlphaVantageAdapter
from app.data.providers.finmind import TOKEN_ENV_VAR, FinMindAdapter
from app.data.quota import DAILY_LIMIT_ENV_VAR, SAFETY_MARGIN_ENV_VAR, QuotaLedger
from app.logging_setup import (
    INFO_NAMESPACES,
    QUIET_NAMESPACES,
    SecretRedactionFilter,
    configure_logging,
    describe_failure,
    redact_url,
)
from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Fake secrets only. The Telegram value keeps the <digits>:<secret> shape on
# purpose, but every value is shorter than a real one so secret scanners
# (gitleaks Telegram / Discord rules) do not flag this file.
FAKE_TELEGRAM_TOKEN = "123456789:FAKE-not-real-token"
FAKE_DISCORD_SECRET = "FAKE-discord-not-real"
FAKE_DISCORD_URL = f"https://discord.com/api/webhooks/111122223333444455/{FAKE_DISCORD_SECRET}"
FAKE_FINMIND_TOKEN = "FAKE-finmind-token-not-real"
FAKE_AV_KEY = "FAKE-alphavantage-key-not-real"
ALL_SECRETS = (FAKE_TELEGRAM_TOKEN, FAKE_DISCORD_SECRET, FAKE_FINMIND_TOKEN, FAKE_AV_KEY)

_EVENT = AlertEvent(
    id=1,
    rule_id=1,
    rule_type="price_above",
    symbol="2330",
    market="TW",
    message="2330 最新收盤價 700 TWD，高於設定的門檻 650 TWD。",
    observed={"close": 700.0, "threshold": 650.0},
    triggered_at=datetime(2026, 7, 25, 6, 0, tzinfo=UTC),
    acknowledged=False,
    acknowledged_at=None,
)

Handler = Callable[[httpx.Request], httpx.Response]


# --------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _restore_logger_levels() -> Iterator[None]:
    """configure_logging() mutates global loggers; put every one back afterwards."""
    names = (*INFO_NAMESPACES, *QUIET_NAMESPACES)
    saved = {name: logging.getLogger(name).level for name in names}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


@pytest.fixture(autouse=True)
def _clear_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never inherit a real webhook or key from the developer's environment."""
    for name in (
        DISCORD_WEBHOOK_ENV,
        TELEGRAM_TOKEN_ENV,
        TELEGRAM_CHAT_ID_ENV,
        TOKEN_ENV_VAR,
        API_KEY_ENV_VAR,
    ):
        monkeypatch.delenv(name, raising=False)


@contextmanager
def _owned_root() -> Iterator[logging.Logger]:
    """A root logger with no handlers, as in a freshly started process.

    pytest attaches its capture handlers to root at the start of each test
    phase, so this must run inside the test body (not as a fixture) to detach
    them. configure_logging() then takes the "we own logging" branch exactly
    as it does under uvicorn or ``python -m app.scheduler``. Restored on exit.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    root.handlers = []
    try:
        yield root
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)


def _capture_raw_records(root: logging.Logger, caplog: pytest.LogCaptureFixture) -> None:
    """Attach caplog behind the installed handler, with root opened up to INFO.

    root=INFO is the worst case the security grid asks for (the old scheduler
    ``basicConfig(level=INFO)``): any library logger left at NOTSET would leak.
    """
    root.setLevel(logging.INFO)
    root.addHandler(caplog.handler)


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _configure_both_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISCORD_WEBHOOK_ENV, FAKE_DISCORD_URL)
    monkeypatch.setenv(TELEGRAM_TOKEN_ENV, FAKE_TELEGRAM_TOKEN)
    monkeypatch.setenv(TELEGRAM_CHAT_ID_ENV, "42")


def _assert_no_secret(text: str) -> None:
    for secret in ALL_SECRETS:
        assert secret not in text
    assert "api.telegram.org/bot1" not in text
    assert "/api/webhooks/111122223333444455/FAKE" not in text
    assert "token=FAKE" not in text
    assert "apikey=FAKE" not in text


def _all_log_text(caplog: pytest.LogCaptureFixture) -> str:
    rendered = [record.getMessage() for record in caplog.records]
    return "\n".join([caplog.text, *rendered])


def _by_channel(results: list[DeliveryResult]) -> dict[str, DeliveryResult]:
    return {result.channel: result for result in results}


# ------------------------------------------- D-1 / D-2 / D-4: HTTP status errors


def _status_handler(status: int) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        # A hostile Location header echoes the secret URL back, too.
        headers = {"location": str(request.url)} if 300 <= status < 400 else {}
        return httpx.Response(status, text=f"echo {request.url}", headers=headers)

    return handler


@pytest.mark.parametrize("status", [404, 429, 500, 301])
def test_http_status_failures_keep_both_channel_secrets_out(
    status: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging()
    caplog.set_level(logging.DEBUG)
    _configure_both_channels(monkeypatch)

    results = notify(_EVENT, client=_client(_status_handler(status)))

    by_channel = _by_channel(results)
    expected = f"error_class=HTTPStatusError status={status}"
    for channel in ("discord", "telegram"):
        assert by_channel[channel].status == "failed"
        assert by_channel[channel].detail == expected
    _assert_no_secret(repr(results))
    _assert_no_secret(_all_log_text(caplog))
    failures = [r.getMessage() for r in caplog.records if r.name == notify_module.__name__]
    assert failures == [
        f"alert webhook delivery failed: channel=discord {expected}",
        f"alert webhook delivery failed: channel=telegram {expected}",
    ]
    for record in caplog.records:
        assert record.exc_info is None


# ------------------------------------------------- D-3 / D-4: hostile exceptions


def _hostile(make: Callable[[httpx.Request], Exception]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise make(request)

    return handler


HOSTILE_EXCEPTIONS: dict[str, Callable[[httpx.Request], Exception]] = {
    "ConnectError": lambda request: httpx.ConnectError(f"boom {request.url}"),
    "ReadTimeout": lambda request: httpx.ReadTimeout(f"slow {request.url}", request=request),
    "HTTPStatusError": lambda request: httpx.HTTPStatusError(
        f"bad {request.url}", request=request, response=httpx.Response(502, request=request)
    ),
    "RuntimeError": lambda request: RuntimeError(f"anything {request.url!r}"),
}


@pytest.mark.parametrize("name", sorted(HOSTILE_EXCEPTIONS))
def test_exception_text_embedding_the_url_never_leaks(
    name: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging()
    caplog.set_level(logging.DEBUG)
    _configure_both_channels(monkeypatch)

    results = notify(_EVENT, client=_client(_hostile(HOSTILE_EXCEPTIONS[name])))

    expected = f"error_class={name}" + (" status=502" if name == "HTTPStatusError" else "")
    for result in results:
        assert result.status == "failed"
        assert result.detail == expected
    _assert_no_secret(repr(results))
    _assert_no_secret(_all_log_text(caplog))


def test_describe_failure_ignores_the_message_text() -> None:
    request = httpx.Request("POST", f"https://api.telegram.org/bot{FAKE_TELEGRAM_TOKEN}/x")
    response = httpx.Response(404, request=request)
    status_error = httpx.HTTPStatusError(str(request.url), request=request, response=response)
    assert describe_failure(status_error) == "error_class=HTTPStatusError status=404"
    assert describe_failure(httpx.ConnectError(str(request.url))) == "error_class=ConnectError"
    assert describe_failure(ValueError(FAKE_TELEGRAM_TOKEN)) == "error_class=ValueError"


# -------------------------------------- D-5: success path under the real entries


def test_scheduler_entry_silences_httpx_on_a_successful_push(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with _owned_root() as root:
        ran: list[bool] = []
        monkeypatch.setattr(scheduler_module, "run", lambda: ran.append(True))
        scheduler_module.main()  # the scheduler's real process entry point
        assert ran == [True]
        _capture_raw_records(root, caplog)
        _configure_both_channels(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True})

        results = notify(_EVENT, client=_client(handler))

        assert [r.status for r in results] == ["sent", "sent"]
        for name in QUIET_NAMESPACES:
            assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
        assert not [r for r in caplog.records if r.name.split(".")[0] in QUIET_NAMESPACES]
        _assert_no_secret(_all_log_text(caplog))
        _assert_no_secret(capsys.readouterr().err)


def test_scheduler_entry_installs_the_redacting_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler_module, "run", lambda: None)
    with _owned_root() as root:
        scheduler_module.main()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert any(isinstance(f, SecretRedactionFilter) for f in handler.filters)
        assert root.level == logging.WARNING
        for name in INFO_NAMESPACES:
            assert logging.getLogger(name).level == logging.INFO


def test_api_lifespan_configures_logging() -> None:
    with _owned_root() as root:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
        assert len(root.handlers) == 1
        assert any(isinstance(f, SecretRedactionFilter) for f in root.handlers[0].filters)
        for name in QUIET_NAMESPACES:
            assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


def test_configure_logging_is_idempotent() -> None:
    with _owned_root() as root:
        configure_logging()
        configure_logging()
        configure_logging()
        assert len(root.handlers) == 1
        assert len(root.handlers[0].filters) == 1


def test_an_already_configured_root_only_gets_the_httpx_floor() -> None:
    root = logging.getLogger()
    before = list(root.handlers)
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    configure_logging()
    assert root.handlers == before
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


# --------------------------------------------- D-6: FinMind and Alpha Vantage


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _finmind(handler: Handler) -> FinMindAdapter:
    client = RateLimitedClient(
        base_url="https://api.finmindtrade.com",
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    return FinMindAdapter(client=client)


def _alpha_vantage(handler: Handler, tmp_path: Path) -> AlphaVantageAdapter:
    client = RateLimitedClient(
        base_url="https://www.alphavantage.co",
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    return AlphaVantageAdapter(client=client, ledger=ledger, min_interval_seconds=0.0)


def _respond(status: int, payload: dict[str, object] | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload if payload is not None else {})

    return handler


def _transport_failure(hostile: bool) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {request.url}" if hostile else "network down")

    return handler


DATA_SOURCE_CASES = {
    "success": None,
    "http_500": _respond(500),
    "transport": _transport_failure(hostile=False),
    "hostile_transport": _transport_failure(hostile=True),
}


@pytest.mark.parametrize("case", sorted(DATA_SOURCE_CASES))
def test_finmind_token_never_reaches_the_log_output(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with _owned_root() as root:
        configure_logging()
        _capture_raw_records(root, caplog)
        monkeypatch.setenv(TOKEN_ENV_VAR, FAKE_FINMIND_TOKEN)
        seen: list[str] = []
        handler = DATA_SOURCE_CASES[case] or _respond(
            200, _fixture_json("finmind_taiwan_stock_price_2330.json")
        )

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params.get("token", ""))
            return handler(request)

        _finmind(recording).get_daily_bars("2330", date(2024, 1, 1), date(2024, 1, 31))

        assert FAKE_FINMIND_TOKEN in seen  # the secret really was on the wire
        assert not [r for r in caplog.records if r.name.split(".")[0] in QUIET_NAMESPACES]
        _assert_no_secret(_all_log_text(caplog))
        _assert_no_secret(capsys.readouterr().err)


@pytest.mark.parametrize("case", sorted(DATA_SOURCE_CASES))
def test_alpha_vantage_key_never_reaches_the_log_output(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    with _owned_root() as root:
        configure_logging()
        _capture_raw_records(root, caplog)
        monkeypatch.setenv(API_KEY_ENV_VAR, FAKE_AV_KEY)
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
        monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")
        seen: list[str] = []
        handler = DATA_SOURCE_CASES[case] or _respond(
            200, _fixture_json("alpha_vantage_daily_aapl.json")
        )

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params.get("apikey", ""))
            return handler(request)

        adapter = _alpha_vantage(recording, tmp_path)
        adapter.get_daily_bars("AAPL", date(2023, 12, 29), date(2024, 1, 31))

        assert FAKE_AV_KEY in seen
        assert not [r for r in caplog.records if r.name.split(".")[0] in QUIET_NAMESPACES]
        _assert_no_secret(_all_log_text(caplog))
        _assert_no_secret(capsys.readouterr().err)


# ------------------------------------------------------------ D-7: redact_url()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            f"https://api.telegram.org/bot{FAKE_TELEGRAM_TOKEN}/sendMessage",
            "https://api.telegram.org/bot***/sendMessage",
        ),
        (
            f"https://proxy.example/bot{FAKE_TELEGRAM_TOKEN}/getUpdates",
            "https://proxy.example/bot***/getUpdates",
        ),
        (
            "https://API.TELEGRAM.ORG/botnot-a-token-shape/sendMessage",
            "https://API.TELEGRAM.ORG/bot***/sendMessage",
        ),
        (FAKE_DISCORD_URL, "https://discord.com/api/webhooks/111122223333444455/***"),
        (
            f"https://discordapp.com/api/webhooks/1/{FAKE_DISCORD_SECRET}?wait=true",
            "https://discordapp.com/api/webhooks/1/***?wait=true",
        ),
        (
            f"https://api.finmindtrade.com/api/v4/data?dataset=d&token={FAKE_FINMIND_TOKEN}",
            "https://api.finmindtrade.com/api/v4/data?dataset=d&token=***",
        ),
        (
            f"https://www.alphavantage.co/query?apikey={FAKE_AV_KEY}&function=f",
            "https://www.alphavantage.co/query?apikey=***&function=f",
        ),
        ("https://x.example/q?API_KEY=abc&Token=def", "https://x.example/q?API_KEY=***&Token=***"),
        (
            f"HTTP Request: GET https://www.alphavantage.co/query?function=f&apikey={FAKE_AV_KEY} "
            '"HTTP/1.1 200 OK"',
            "HTTP Request: GET https://www.alphavantage.co/query?function=f&apikey=*** "
            '"HTTP/1.1 200 OK"',
        ),
        (
            f"Client error '404 Not Found' for url "
            f"'https://api.telegram.org/bot{FAKE_TELEGRAM_TOKEN}/sendMessage'",
            "Client error '404 Not Found' for url 'https://api.telegram.org/bot***/sendMessage'",
        ),
    ],
)
def test_redact_url_masks_credentials(raw: str, expected: str) -> None:
    assert redact_url(raw) == expected
    assert redact_url(expected) == expected  # idempotent


@pytest.mark.parametrize(
    "safe",
    [
        "https://discord.test/hook",
        "https://example.com/bots/list",
        "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=AAPL",
        "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=2330",
        "https://x.example/q?access_token_hint=1&tokens=2",
        "alert evaluation: 3 rules evaluated, 1 fired, failed_symbols=0",
        "",
    ],
)
def test_redact_url_leaves_non_secret_text_alone(safe: str) -> None:
    assert redact_url(safe) == safe


def test_filter_redacts_arguments_and_tracebacks() -> None:
    secret_url = f"https://api.telegram.org/bot{FAKE_TELEGRAM_TOKEN}/sendMessage"
    try:
        raise RuntimeError(secret_url)
    except RuntimeError as err:
        exc_info = (type(err), err, err.__traceback__)
    record = logging.LogRecord(
        "app.x", logging.WARNING, __file__, 1, "posting to %s", (secret_url,), exc_info
    )
    record.stack_info = f"Stack: {secret_url}"

    assert SecretRedactionFilter().filter(record) is True

    formatted = logging.Formatter("%(message)s").format(record)
    assert FAKE_TELEGRAM_TOKEN not in formatted
    assert "posting to https://api.telegram.org/bot***/sendMessage" in formatted
    assert "RuntimeError" in formatted


def test_filter_survives_a_malformed_record() -> None:
    record = logging.LogRecord(
        "app.x", logging.WARNING, __file__, 1, f"bad %d {FAKE_DISCORD_URL}", ("x",), None
    )
    assert SecretRedactionFilter().filter(record) is True
    assert FAKE_DISCORD_SECRET not in record.getMessage()


# --------------------------------------------------------- D-9: static checks


NOTIFY_SOURCE = Path(notify_module.__file__).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "forbidden",
    [
        "str(exc)",
        "repr(exc)",
        "{exc",
        "exc!r",
        "exc_info",
        ".exception(",
        "request.url",
        "response.url",
        "traceback",
    ],
)
def test_notify_has_no_forbidden_exception_rendering(forbidden: str) -> None:
    assert forbidden not in NOTIFY_SOURCE


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def test_notify_only_hands_the_exception_to_describe_failure() -> None:
    tree = ast.parse(NOTIFY_SOURCE)
    parents = _parents(tree)
    uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "exc" and isinstance(node.ctx, ast.Load)
    ]
    assert uses, "the except block must still describe the failure"
    for node in uses:
        call = parents[node]
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name) and call.func.id == "describe_failure"
        assert call.args == [node] and not call.keywords


def test_describe_failure_reads_only_class_and_status() -> None:
    import app.logging_setup as logging_setup

    tree = ast.parse(Path(logging_setup.__file__).read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "describe_failure"
    )
    parents = _parents(function)
    for node in ast.walk(function):
        if not (isinstance(node, ast.Name) and node.id == "exc"):
            continue
        if isinstance(node.ctx, ast.Store) or isinstance(parents.get(node), ast.arguments):
            continue
        parent = parents[node]
        if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name):
            assert parent.func.id in {"type", "isinstance"}
            assert parent.args[0] is node
        else:
            # The only attribute path allowed: exc.response.status_code.
            assert isinstance(parent, ast.Attribute) and parent.attr == "response"
            grand = parents[parent]
            assert isinstance(grand, ast.Attribute) and grand.attr == "status_code"
