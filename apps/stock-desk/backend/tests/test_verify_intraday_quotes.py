"""Offline tests for the CEO-facing ``verify_intraday_quotes.py`` tool.

Everything runs against ``httpx.MockTransport``; nothing touches the network.
The MIS payload shape used here is the one the script documents (rtcode,
msgArray with c/n/z/y/o/h/l/v/t/d/tlong/ex, queryTime) and is synthetic until
the CEO's real run confirms it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

import httpx
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_intraday_quotes.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_intraday_quotes", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


viq = _load_script_module()

NOW = datetime(2026, 10, 2, 10, 30, 0, tzinfo=viq.TAIPEI)  # a Friday
NOW_MS = int(NOW.timestamp() * 1000)
COOKIE_VALUE = "SESSIONSECRET-abc123"
FINMIND_TOKEN = "finmind-token-SECRET-9876"
AV_KEY = "AVKEY-SECRET-5555"


def _mis_item(code: str, ex: str, z: str, age_s: int = 3) -> dict[str, str]:
    return {
        "c": code,
        "n": f"name{code}",
        "ex": ex,
        "z": z,
        "y": "100.0000",
        "o": "101.0000" if z != "-" else "-",
        "h": "102.0000",
        "l": "99.0000",
        "v": "1234",
        "t": "10:29:57",
        "d": "20261002",
        "tlong": str(NOW_MS - age_s * 1000),
        "a": "101.0000_101.5000_",
        "b": "100.5000_100.0000_",
    }


@dataclass
class FakeClock:
    """Shared fake time: ``sleep`` advances it, handlers read it to timestamp requests."""

    t: float = 0.0

    def sleep(self, seconds: float) -> None:
        self.t += seconds

    def now(self) -> datetime:
        return NOW + timedelta(seconds=self.t)


@dataclass
class World:
    """A scripted fake of every host the tool talks to."""

    z: str = "101.5000"
    needs_cookie: bool = False
    block_after: int | None = None  # MIS data requests after this many get HTTP 403
    block_status: int = 403
    yf_age_min: float = 15.0
    yf_price: float = 101.5
    stock_day_close: str = "101.50"
    seen_hosts: list[str] = field(default_factory=list)
    mis_data_calls: int = 0
    clock: FakeClock | None = None
    mis_times: list[float] = field(default_factory=list)  # every MIS request (home + API)
    stock_day_times: list[float] = field(default_factory=list)
    redirect_api: bool = False  # MIS API answers 302 -> /stock/verify.jsp
    redirect_followed: int = 0
    bad_rtcode_after: int | None = None  # MIS data requests after this many get rtcode 9999
    mis_error_after: int | None = None  # MIS data requests after this many raise ConnectError
    mis_error_text: str = "connection reset"
    yahoo_raises: str | None = None
    yf_status: int = 200
    root_status: dict[str, int] = field(default_factory=dict)  # host -> status for "/"
    stock_day_calls: int = 0

    def _now(self) -> float:
        return self.clock.t if self.clock else 0.0

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.seen_hosts.append(host)
        if host == "mis.twse.com.tw":
            self.mis_times.append(self._now())
            return self._mis(request, path)
        if path == "/" and host in self.root_status:
            return httpx.Response(self.root_status[host], text="root")
        if host == "www.twse.com.tw":
            if "STOCK_DAY" in path:
                self.stock_day_calls += 1
                self.stock_day_times.append(self._now())
                return httpx.Response(
                    200,
                    json={
                        "stat": "OK",
                        "data": [
                            [
                                "115/10/02",
                                "1,234,000",
                                "1",
                                "100",
                                "102",
                                "99",
                                self.stock_day_close,
                            ]
                            + ["1.5", "10"]
                        ],
                    },
                )
            return httpx.Response(200, text="<html>twse</html>")
        if host == "query1.finance.yahoo.com":
            if path == "/":
                return httpx.Response(200, text="yahoo")
            if "/v8/finance/chart/" in path:
                if self.yahoo_raises is not None:
                    raise ValueError(self.yahoo_raises)
                if self.yf_status != 200:
                    return httpx.Response(self.yf_status, text="nope")
                last = int(NOW.timestamp() - self.yf_age_min * 60)
                return httpx.Response(
                    200,
                    json={
                        "chart": {
                            "error": None,
                            "result": [
                                {
                                    "meta": {
                                        "regularMarketPrice": self.yf_price,
                                        "regularMarketTime": last,
                                    },
                                    "timestamp": [last],
                                    "indicators": {"quote": [{"close": [self.yf_price]}]},
                                }
                            ],
                        }
                    },
                )
            return httpx.Response(404, text="not found")
        if host == "api.finmindtrade.com":
            if path.startswith("/api/v4/"):
                auth = request.headers.get("authorization", "")
                return httpx.Response(
                    200, json={"status": 402, "msg": f"level too low for {auth} / token={auth}"}
                )
            return httpx.Response(200, text="ok")
        if host == "www.alphavantage.co":
            return httpx.Response(
                200,
                json={
                    "Global Quote": {"05. price": "150.0", "07. latest trading day": "2026-10-01"}
                },
            )
        return httpx.Response(500, text="unexpected host")

    def _mis(self, request: httpx.Request, path: str) -> httpx.Response:
        if path.endswith("verify.jsp"):
            self.redirect_followed += 1
            return httpx.Response(200, text="<html>verify</html>")
        if path.endswith("index.jsp"):
            return httpx.Response(
                200,
                text="<html>home</html>",
                headers={"Set-Cookie": f"JSESSIONID={COOKIE_VALUE}; Path=/"},
            )
        self.mis_data_calls += 1
        if self.redirect_api:
            return httpx.Response(
                302, headers={"Location": "https://mis.twse.com.tw/stock/verify.jsp"}
            )
        if self.block_after is not None and self.mis_data_calls > self.block_after:
            return httpx.Response(self.block_status, text="Forbidden")
        if self.mis_error_after is not None and self.mis_data_calls > self.mis_error_after:
            raise httpx.ConnectError(self.mis_error_text, request=request)
        if self.needs_cookie and COOKIE_VALUE not in request.headers.get("cookie", ""):
            return httpx.Response(200, text="<html>please verify you are human</html>")
        channels = request.url.params.get("ex_ch", "").split("|")
        items = []
        for channel in channels:
            ex, rest = channel.split("_", 1)
            items.append(_mis_item(rest.removesuffix(".tw"), ex, self.z))
        rtcode = (
            "9999"
            if self.bad_rtcode_after is not None and self.mis_data_calls > self.bad_rtcode_after
            else "0000"
        )
        return httpx.Response(
            200,
            json={
                "rtcode": rtcode,
                "rtmessage": "OK",
                "queryTime": {"sysDate": "20261002", "sysTime": "10:30:00"},
                "msgArray": items,
            },
        )


def _run_main(
    tmp_path: Path,
    world: World,
    *extra: str,
    phase: str = "mid",
    clock: FakeClock | None = None,
) -> tuple[int, list[float], Path]:
    sleeps: list[float] = []
    now_fn: Callable[[], datetime] = lambda: NOW  # noqa: E731
    if clock is not None:
        world.clock = clock
        now_fn = clock.now

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if clock is not None:
            clock.sleep(seconds)

    code = viq.main(
        ["--phase", phase, "--output-dir", str(tmp_path), *extra],
        transport=httpx.MockTransport(world.handler),
        now_fn=now_fn,
        sleep_fn=sleep,
    )
    return code, sleeps, tmp_path / f"驗證結果-盤中-2026-10-02-{phase}.md"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(viq.FINMIND_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(viq.ALPHA_VANTAGE_KEY_ENV_VAR, raising=False)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_parse_mis_payload_normal_response() -> None:
    payload = {
        "rtcode": "0000",
        "queryTime": {"sysDate": "20261002", "sysTime": "10:30:00"},
        "msgArray": [_mis_item("2330", "tse", "1,050.0000")],
    }
    parsed = viq.parse_mis_payload(payload)
    assert parsed.problems == ()
    (quote,) = parsed.quotes
    assert str(quote.last) == "1050.0000"
    assert quote.last_is_dash is False
    assert quote.volume_lots == 1234
    assert quote.missing_keys == ()
    assert parsed.server_time == NOW
    assert viq.mis_delay_seconds(quote, parsed.server_time) == pytest.approx(3.0)


def test_parse_mis_payload_reports_missing_fields_and_bad_rtcode() -> None:
    item = _mis_item("2330", "tse", "100")
    del item["tlong"]
    parsed = viq.parse_mis_payload({"rtcode": "5000", "msgArray": [item]})
    assert any("rtcode" in p for p in parsed.problems)
    assert parsed.quotes[0].missing_keys == ("tlong",)
    assert viq.parse_mis_payload("not a dict").problems


def test_z_dash_is_no_price_not_substituted() -> None:
    parsed = viq.parse_mis_payload({"rtcode": "0000", "msgArray": [_mis_item("2330", "tse", "-")]})
    quote = parsed.quotes[0]
    assert quote.last is None
    assert quote.last_is_dash is True
    # Yesterday's close is parsed separately and never leaks into ``last``.
    assert str(quote.prev_close) == "100.0000"


def test_parse_symbols_markets_and_validation() -> None:
    symbols = viq.parse_symbols("2330,5483,0050,00631L,otc:6488,9999")
    assert [s.market for s in symbols] == ["tse", "otc", "tse", "tse", "otc", "tse"]
    assert symbols[-1].market_guessed is True
    assert symbols[1].mis_channel == "otc_5483.tw"
    assert symbols[1].yahoo_symbol == "5483.TWO"
    assert symbols[0].yahoo_symbol == "2330.TW"
    with pytest.raises(ValueError):
        viq.parse_symbols("2330;rm")


# --------------------------------------------------------------------------
# Full run: parse, B6, summary
# --------------------------------------------------------------------------


def test_full_mid_run_summary_and_report(tmp_path: Path) -> None:
    world = World()
    code, _, report_path = _run_main(tmp_path, world, "--rate-probe-requests", "3")
    report = report_path.read_text(encoding="utf-8")
    verdicts = {line.split("|")[1].strip(): line for line in report.splitlines() if "| **" in line}
    assert "PASS" in verdicts["B2"]
    assert "PASS" in verdicts["B3"]
    assert "SKIP" in verdicts["B5"]  # post phase only
    assert "SKIP" in verdicts["B6"]  # no dash in this scenario
    assert "SKIP" in verdicts["E"]  # no token is SKIP, not FAIL
    assert "SKIP" in verdicts["F"]
    assert "證交所盤中報價：可用，延遲約 3 秒" in report
    assert "yfinance：延遲約 15 分鐘，不適合當盤中價" in report
    assert "Asia/Taipei" in report
    assert "起跑當天是否為平日**：是（週五" in report
    assert code == 0
    assert (tmp_path / "驗證結果-盤中-2026-10-02-mid.real.json").exists()


def test_terminal_summary_tells_ceo_to_paste_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_main(tmp_path, World(), "--skip-rate-probe")
    out = capsys.readouterr().out
    assert "請把報告檔內容貼給 Claude" in out
    assert "證交所盤中報價" in out
    assert "yfinance" in out


def test_pre_open_dash_is_reported_and_delay_not_judged(tmp_path: Path) -> None:
    world = World(z="-")
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe", phase="pre-open")
    report = report_path.read_text(encoding="utf-8")
    assert "不以昨收、開盤或委買賣價頂替" in report
    assert "尚無成交價" in report
    assert "本時段不判斷延遲" in report
    d_line = next(line for line in report.splitlines() if line.startswith("| D |"))
    assert "SKIP" in d_line  # nothing comparable without a MIS last price


def test_cookie_required_is_detected_and_handled(tmp_path: Path) -> None:
    world = World(needs_cookie=True)
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    report = report_path.read_text(encoding="utf-8")
    assert "需要先開首頁取得 cookie" in report
    assert "需要先取得 cookie：是" in report
    b2 = next(line for line in report.splitlines() if line.startswith("| B2 |"))
    assert "PASS" in b2


def test_post_phase_reconciles_close_with_official(tmp_path: Path) -> None:
    world = World(stock_day_close="101.50")
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe", phase="post")
    b5 = next(
        line
        for line in report_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("| B5 |")
    )
    assert "PASS" in b5

    world_bad = World(stock_day_close="99.00")
    _, _, report_path = _run_main(tmp_path, world_bad, "--skip-rate-probe", phase="post")
    b5_bad = next(
        line
        for line in report_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("| B5 |")
    )
    assert "FAIL" in b5_bad


# --------------------------------------------------------------------------
# Rate-limit probe
# --------------------------------------------------------------------------


def test_rate_probe_stops_at_first_non_200(tmp_path: Path) -> None:
    # B1 uses 2 data calls, B2 1, B3 6 -> 9 before the probe; block at the 4th probe call.
    world = World(block_after=9 + 3)
    code, _, report_path = _run_main(tmp_path, world, "--rate-probe-requests", "50")
    report = report_path.read_text(encoding="utf-8")
    assert world.mis_data_calls == 9 + 4  # stopped immediately, no further requests
    assert "做到第 4 次就被擋" in report
    b4 = next(line for line in report.splitlines() if line.startswith("| B4 |"))
    assert "FAIL" in b4
    assert code == 1


def test_rate_probe_never_exceeds_hard_cap_and_keeps_spacing(tmp_path: Path) -> None:
    clock = FakeClock()
    world = World()
    _run_main(
        tmp_path,
        world,
        "--rate-probe-requests",
        "100",
        "--poll-count",
        "2",
        clock=clock,
    )
    # Every MIS request (home page + API) is timestamped by the shared fake clock.
    gaps = [b - a for a, b in zip(world.mis_times, world.mis_times[1:], strict=False)]
    assert gaps
    assert all(gap >= viq.MIN_REQUEST_INTERVAL_S for gap in gaps)
    raw = json.loads((tmp_path / "驗證結果-盤中-2026-10-02-mid.real.json").read_text("utf-8"))
    b4_log = next(e for e in raw["entries"] if e["check"] == "B4.log")
    assert len(b4_log["requests"]) <= 100
    assert len(b4_log["requests"]) == viq.MAX_RATE_PROBE_REQUESTS
    # A (1) + B1 (3) + B2 (1) + B3 (2) before the probe, then exactly the B4 requests.
    assert len(world.mis_times) == 7 + len(b4_log["requests"])


def test_rate_probe_limits_rejected_by_cli() -> None:
    with pytest.raises(SystemExit):
        viq.parse_args(["--phase", "mid", "--rate-probe-requests", "101"])
    with pytest.raises(SystemExit):
        viq.parse_args(["--phase", "mid", "--rate-probe-interval", "1.9"])
    with pytest.raises(SystemExit):
        viq.parse_args(["--phase", "mid", "--poll-interval", "0.5"])


def test_skip_rate_probe_sends_no_probe_requests(tmp_path: Path) -> None:
    world = World()
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    assert world.mis_data_calls == 2 + 1 + 6
    assert "連續查詢測試：這次略過" in report_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "make_response",
    [
        lambda: httpx.Response(429, text="slow down"),
        lambda: httpx.Response(200, text=""),
        lambda: httpx.Response(200, text="<html>verify</html>"),
        lambda: httpx.Response(200, json={"rtcode": "0000", "msgArray": []}),
        lambda: httpx.Response(302, headers={"Location": "https://mis.twse.com.tw/verify"}),
        lambda: httpx.Response(301, text=""),
        lambda: httpx.Response(
            200, json={"rtcode": "5000", "msgArray": [_mis_item("2330", "tse", "1")]}
        ),
    ],
)
def test_classify_block_catches_every_stop_condition(
    make_response: Callable[[], httpx.Response],
) -> None:
    resp = make_response()
    data = None
    try:
        data = resp.json()
    except ValueError:
        pass
    outcome = viq.HttpOutcome(resp.status_code, resp.text, data, None, False, 0.0)
    assert viq.classify_block(outcome) is not None
    good = viq.HttpOutcome(
        200, "x", {"rtcode": "0000", "msgArray": [_mis_item("2330", "tse", "1")]}, None, False, 0.0
    )
    assert viq.classify_block(good) is None


# --------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------


def test_tokens_and_cookies_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(viq.FINMIND_TOKEN_ENV_VAR, FINMIND_TOKEN)
    monkeypatch.setenv(viq.ALPHA_VANTAGE_KEY_ENV_VAR, AV_KEY)
    world = World(needs_cookie=True)
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe", "--include-alpha-vantage")
    report = report_path.read_text(encoding="utf-8")
    raw = (tmp_path / "驗證結果-盤中-2026-10-02-mid.real.json").read_text(encoding="utf-8")
    terminal = capsys.readouterr().out
    for secret in (COOKIE_VALUE, FINMIND_TOKEN, AV_KEY):
        assert secret not in report
        assert secret not in raw
        assert secret not in terminal
    # The server echoed the token back in the FinMind body; it must be scrubbed.
    assert "[REDACTED]" in raw
    assert "FINMIND_API_TOKEN 有設定" in report
    assert "ALPHA_VANTAGE_API_KEY 有設定" in report
    assert "MIS cookie 有設定" in report
    entries = json.loads(raw)["entries"]
    assert all(
        "set-cookie" not in {k.lower() for k in e.get("response_headers", {})} for e in entries
    )
    av = next(e for e in entries if e["check"] == "F")
    assert av["params"]["apikey"] == "[REDACTED]"


def test_redactor_unit() -> None:
    redactor = viq.Redactor()
    redactor.add_secret("supersecretvalue")
    redactor.add_cookie_header("JSESSIONID=cookievalue123; Path=/; Secure")
    scrubbed = redactor.scrub_obj(
        {"a": "x supersecretvalue y", "Authorization": "Bearer abc", "n": ["cookievalue123"]}
    )
    assert scrubbed == {"a": "x [REDACTED] y", "Authorization": "[REDACTED]", "n": ["[REDACTED]"]}
    assert "tok123" not in redactor.scrub_text("https://x/y?token=tok123&a=1")


# --------------------------------------------------------------------------
# Optional / permission checks
# --------------------------------------------------------------------------


def test_alpha_vantage_not_called_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(viq.ALPHA_VANTAGE_KEY_ENV_VAR, AV_KEY)
    world = World()
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    assert "www.alphavantage.co" not in world.seen_hosts
    assert "預設不執行" in report_path.read_text(encoding="utf-8")


def test_alpha_vantage_flag_runs_and_warns_about_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(viq.ALPHA_VANTAGE_KEY_ENV_VAR, AV_KEY)
    world = World()
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe", "--include-alpha-vantage")
    report = report_path.read_text(encoding="utf-8")
    assert world.seen_hosts.count("www.alphavantage.co") == 1
    assert "會吃掉 1 次" in report


def test_finmind_without_token_is_skip_and_sends_nothing(tmp_path: Path) -> None:
    world = World()
    code, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    report = report_path.read_text(encoding="utf-8")
    e_line = next(line for line in report.splitlines() if line.startswith("| E |"))
    assert "SKIP" in e_line
    # Only the A connectivity probe (root page) may reach FinMind without a token.
    assert world.seen_hosts.count("api.finmindtrade.com") == 1
    assert code == 0


def test_finmind_with_token_but_no_permission_is_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(viq.FINMIND_TOKEN_ENV_VAR, FINMIND_TOKEN)
    _, _, report_path = _run_main(tmp_path, World(), "--skip-rate-probe")
    e_line = next(
        line
        for line in report_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("| E |")
    )
    assert "FAIL" in e_line


# --------------------------------------------------------------------------
# Unreachable
# --------------------------------------------------------------------------


def test_everything_unreachable_is_reported_not_crashed(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("blocked", request=request)

    sleeps: list[float] = []
    code = viq.main(
        ["--phase", "mid", "--output-dir", str(tmp_path)],
        transport=httpx.MockTransport(refuse),
        now_fn=lambda: NOW,
        sleep_fn=sleeps.append,
    )
    report = (tmp_path / "驗證結果-盤中-2026-10-02-mid.md").read_text(encoding="utf-8")
    assert code == 1
    assert "UNREACHABLE" in report
    assert "證交所盤中報價：連不上" in report
    assert "yfinance：連不上" in report


def test_build_plain_summary_thresholds() -> None:
    facts = viq.Facts(mis_reachable=True, mis_structure_ok=True, mis_delay_s=200.0)
    facts.yf_ok, facts.yf_delay_min = True, 0.5
    lines = viq.build_plain_summary(facts, "mid")
    assert any("延遲偏大" in line and "200 秒" in line for line in lines)
    assert any("接近即時" in line for line in lines)


# --------------------------------------------------------------------------
# Review round: redirects, MIS block flag, rtcode, timing, exceptions, spacing
# --------------------------------------------------------------------------


def _row(report: str, check_id: str) -> str:
    return next(line for line in report.splitlines() if line.startswith(f"| {check_id} |"))


def _read(report_path: Path) -> str:
    return report_path.read_text(encoding="utf-8")


def _run_direct(
    tmp_path: Path,
    world: World,
    now_fn: Callable[[], datetime],
    *extra: str,
    phase: str = "mid",
) -> object:
    args = viq.parse_args(["--phase", phase, "--output-dir", str(tmp_path), *extra])
    return viq.run(
        args,
        transport=httpx.MockTransport(world.handler),
        now_fn=now_fn,
        sleep_fn=lambda _s: None,
    )


class _StartEndClock:
    """First call (run start) returns ``start``; every later call returns ``end``."""

    def __init__(self, start: datetime, end: datetime) -> None:
        self.start, self.end, self.calls = start, end, 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.start if self.calls == 1 else self.end


def test_mis_clients_never_follow_redirects() -> None:
    args = viq.parse_args(["--phase", "mid"])
    ctx = viq.Context(
        args=args,
        now_fn=lambda: NOW,
        sleep_fn=lambda _s: None,
        transport=httpx.MockTransport(World().handler),
        started_at=NOW,
    )
    try:
        assert ctx.new_mis_client().follow_redirects is False
        assert ctx.new_client().follow_redirects is True
        with pytest.raises(ValueError):
            ctx.mis_get("x", viq.MIS_API_URL, client=ctx.new_client())
    finally:
        ctx.close()


def test_mis_redirect_is_not_followed_and_stops_all_mis_requests(tmp_path: Path) -> None:
    world = World(redirect_api=True)
    code, _, report_path = _run_main(tmp_path, world, "--rate-probe-requests", "50")
    report = _read(report_path)
    assert world.redirect_followed == 0  # the Location target was never requested
    assert world.mis_data_calls == 2  # B1 bare + B1 with-session; nothing afterwards
    assert "FAIL" in _row(report, "B1")
    assert "SKIP" in _row(report, "B4")
    assert code == 1


def test_classify_block_names_redirect_and_location() -> None:
    outcome = viq.HttpOutcome(302, "", None, None, False, 0.0, "https://mis.twse.com.tw/x")
    reason = viq.classify_block(outcome)
    assert reason is not None
    assert "302" in reason and "重導向" in reason and "https://mis.twse.com.tw/x" in reason


def test_b3_failure_blocks_b4_and_every_later_mis_request(tmp_path: Path) -> None:
    # B1 uses 2 data calls and B2 one; the very first B3 poll is the 4th call -> 403.
    world = World(block_after=3)
    code, _, report_path = _run_main(tmp_path, world, "--rate-probe-requests", "50")
    report = _read(report_path)
    assert world.mis_data_calls == 4  # B4 sent nothing
    assert "FAIL" in _row(report, "B3")
    b4 = _row(report, "B4")
    assert "SKIP" in b4 and "不送請求" in b4
    assert "證交所盤中輪詢失敗：第 1 次輪詢 HTTP 403" in report
    assert "連續查詢測試：先前的 MIS 請求已被擋" in report
    assert code == 1


def test_any_mis_block_sets_flag_and_later_requests_are_not_sent() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(429, text="slow down")

    ctx = viq.Context(
        args=viq.parse_args(["--phase", "mid"]),
        now_fn=lambda: NOW,
        sleep_fn=lambda _s: None,
        transport=httpx.MockTransport(handler),
        started_at=NOW,
    )
    try:
        client = ctx.new_mis_client()
        first = ctx.mis_get("t", viq.MIS_API_URL, client=client, params=ctx.mis_params())
        assert first.status == 429 and ctx.mis_blocked is True
        second = ctx.mis_get("t", viq.MIS_API_URL, client=client, params=ctx.mis_params())
        assert second.status is None and second.error is not None
        assert len(sent) == 1
    finally:
        ctx.close()


def test_b4_stops_when_rtcode_is_not_0000(tmp_path: Path) -> None:
    # 9 calls before the probe; probe request 1 is fine, request 2 carries rtcode 9999.
    world = World(bad_rtcode_after=10)
    code, _, report_path = _run_main(tmp_path, world, "--rate-probe-requests", "50")
    report = _read(report_path)
    assert world.mis_data_calls == 11
    assert "做到第 2 次就被擋" in report
    assert "rtcode" in report
    assert "FAIL" in _row(report, "B4")
    assert code == 1


def test_phase_warning_uses_start_time_not_finish_time(tmp_path: Path) -> None:
    start = datetime(2026, 10, 2, 8, 59, 30, tzinfo=viq.TAIPEI)
    end = datetime(2026, 10, 2, 9, 12, 0, tzinfo=viq.TAIPEI)  # outside pre-open window
    result = _run_direct(tmp_path, World(), _StartEndClock(start, end), phase="pre-open")
    report = result.report  # type: ignore[attr-defined]
    assert "不在建議時段" not in report
    assert "起跑時間**：2026-10-02 08:59:30" in report
    assert "結束時間**：2026-10-02 09:12:00" in report


def test_phase_warning_outside_window_and_on_weekend(tmp_path: Path) -> None:
    early = datetime(2026, 10, 2, 7, 0, 0, tzinfo=viq.TAIPEI)
    report = _run_direct(tmp_path, World(), _StartEndClock(early, early), phase="pre-open").report  # type: ignore[attr-defined]
    assert "起跑時的台北時間 07:00 不在建議時段 08:30-09:00" in report

    saturday = datetime(2026, 10, 3, 10, 0, 0, tzinfo=viq.TAIPEI)
    report = _run_direct(tmp_path, World(), _StartEndClock(saturday, saturday)).report  # type: ignore[attr-defined]
    assert "今天是週末，市場休市" in report
    assert "否（週六，休市）" in report


def test_report_file_date_and_b5_use_start_date_across_midnight(tmp_path: Path) -> None:
    start = datetime(2026, 10, 2, 23, 58, 0, tzinfo=viq.TAIPEI)
    end = datetime(2026, 10, 3, 0, 3, 0, tzinfo=viq.TAIPEI)
    result = _run_direct(
        tmp_path, World(), _StartEndClock(start, end), "--skip-rate-probe", phase="post"
    )
    assert result.report_path.name == "驗證結果-盤中-2026-10-02-post.md"  # type: ignore[attr-defined]
    assert "PASS" in _row(result.report, "B5")  # type: ignore[attr-defined]


def test_check_exception_becomes_scrubbed_fail_and_run_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(viq.FINMIND_TOKEN_ENV_VAR, FINMIND_TOKEN)
    world = World(yahoo_raises=f"boom {FINMIND_TOKEN}")
    code, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    report = _read(report_path)
    c_row = _row(report, "C")
    assert "FAIL" in c_row and "ValueError" in c_row and "boom [REDACTED]" in c_row
    assert FINMIND_TOKEN not in report
    assert "E" in {line.split("|")[1].strip() for line in report.splitlines() if "| **" in line}
    assert code == 1


def test_keyboard_interrupt_still_writes_marked_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = World()
    count = 0

    def interrupting_sleep(_seconds: float) -> None:
        nonlocal count
        count += 1
        if count == 8:  # inside B3
            raise KeyboardInterrupt

    code = viq.main(
        ["--phase", "mid", "--output-dir", str(tmp_path)],
        transport=httpx.MockTransport(world.handler),
        now_fn=lambda: NOW,
        sleep_fn=interrupting_sleep,
    )
    report = _read(tmp_path / "驗證結果-盤中-2026-10-02-mid.md")
    assert code == 130
    assert "中途中斷" in report
    assert "PASS" in _row(report, "B2")  # collected before the interrupt
    b3 = _row(report, "B3")
    assert "SKIP" in b3 and "中途中斷" in b3
    raw = json.loads((tmp_path / "驗證結果-盤中-2026-10-02-mid.real.json").read_text("utf-8"))
    assert raw["interrupted"] is True
    assert "中途中斷" in capsys.readouterr().out


def test_b5_requests_are_spaced_by_min_interval(tmp_path: Path) -> None:
    clock = FakeClock()
    world = World()
    _run_main(tmp_path, world, "--skip-rate-probe", phase="post", clock=clock)
    times = world.stock_day_times
    assert len(times) == 3  # 2330, 0050, 00631L are listed; 5483 is OTC
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert all(gap >= viq.MIN_REQUEST_INTERVAL_S for gap in gaps)


def test_symbols_over_limit_rejected_by_cli() -> None:
    eleven = ",".join(f"{2300 + i}" for i in range(11))
    with pytest.raises(SystemExit):
        viq.parse_args(["--phase", "post", "--symbols", eleven])
    ten = ",".join(f"{2300 + i}" for i in range(10))
    assert len(viq.parse_args(["--phase", "post", "--symbols", ten]).symbols) == 10


def test_post_phase_dash_skips_b5_and_sends_no_stock_day_request(tmp_path: Path) -> None:
    world = World(z="-")
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe", phase="post")
    report = _read(report_path)
    assert "SKIP" in _row(report, "B5")
    assert "無法對帳" in report
    assert world.stock_day_calls == 0


def test_post_phase_otc_symbol_is_marked_not_reconciled(tmp_path: Path) -> None:
    _, _, report_path = _run_main(tmp_path, World(), "--skip-rate-probe", phase="post")
    report = _read(report_path)
    assert "5483（上櫃）：本腳本無對應官方日線來源，未對帳" in report


def test_mid_summary_states_poll_failure_reason() -> None:
    facts = viq.Facts(
        mis_reachable=True,
        mis_structure_ok=True,
        mis_poll_ok=False,
        mis_poll_reason="第 2 次輪詢 HTTP 429",
    )
    lines = viq.build_plain_summary(facts, "mid")
    assert any("證交所盤中輪詢失敗：第 2 次輪詢 HTTP 429" in line for line in lines)
    assert not any("可用" in line and "證交所" in line for line in lines)


def test_summary_yfinance_failure_is_not_reported_as_connectable(tmp_path: Path) -> None:
    world = World(yf_status=404)
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    report = _read(report_path)
    assert "yfinance：取不到可用資料（2330.TW: HTTP 404" in report
    assert "可連線" not in report
    facts = viq.Facts(yf_ok=False, yf_reason="HTTP 500")
    assert "yfinance：取不到可用資料（HTTP 500）。" in viq.build_plain_summary(facts, "mid")


def test_facts_records_mis_poll_ok(tmp_path: Path) -> None:
    ok = _run_direct(tmp_path, World(), lambda: NOW, "--skip-rate-probe")
    assert ok.facts.mis_poll_ok is True  # type: ignore[attr-defined]
    failed = _run_direct(tmp_path, World(block_after=3), lambda: NOW, "--skip-rate-probe")
    assert failed.facts.mis_poll_ok is False  # type: ignore[attr-defined]
    assert "HTTP 403" in failed.facts.mis_poll_reason  # type: ignore[attr-defined]
    assert viq.Facts().mis_poll_ok is None


def test_cross_check_lists_both_times_and_does_not_blame_yfinance(tmp_path: Path) -> None:
    world = World(yf_price=105.0)
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    report = _read(report_path)
    assert "報價時間 2026-10-02 10:29:57" in report  # MIS trade time
    assert "時間 2026-10-02 10:15:00" in report  # yfinance last trade time
    assert "時間差 15 分鐘" in report or "時間差 14.9 分鐘" in report
    assert "請以時間差判讀" in report
    assert "多半是 yfinance 延遲" not in report
    assert "對照報告 D 項的時間差判讀" in report


def test_connectivity_4xx_5xx_is_fail_and_3xx_is_reachable(tmp_path: Path) -> None:
    world = World(root_status={"api.finmindtrade.com": 503, "www.twse.com.tw": 302})
    _, _, report_path = _run_main(tmp_path, world, "--skip-rate-probe")
    report = _read(report_path)
    assert "FAIL" in _row(report, "A.finmind") and "HTTP 503" in _row(report, "A.finmind")
    assert "PASS" in _row(report, "A.twse") and "連得上（HTTP 302" in _row(report, "A.twse")
    assert "PASS" in _row(report, "A.mis") and "連得上（HTTP 200" in _row(report, "A.mis")


def test_b2_shows_raw_z_string(tmp_path: Path) -> None:
    _, _, report_path = _run_main(tmp_path, World(z="-"), "--skip-rate-probe", phase="pre-open")
    assert "z='-'" in _read(report_path)
    _, _, report_path = _run_main(tmp_path, World(), "--skip-rate-probe")
    assert "z='101.5000'" in _read(report_path)


def test_rate_reason_is_scrubbed_in_terminal_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(viq.FINMIND_TOKEN_ENV_VAR, FINMIND_TOKEN)
    world = World(mis_error_after=10, mis_error_text=f"reset {FINMIND_TOKEN}")
    _run_main(tmp_path, world, "--rate-probe-requests", "50")
    terminal = capsys.readouterr().out
    assert "連續查詢測試：做到第 2 次就被擋" in terminal
    assert FINMIND_TOKEN not in terminal
    assert "[REDACTED]" in terminal
