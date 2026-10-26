"""Login autostart, background mode and DB path resolution (FD-4 FR-AS, C-36).

Only an in-memory registry is used; the real HKCU hive is never touched.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

import flight_deals.autostart as autostart
from flight_deals import cli
from flight_deals.app import RegistryAutostartProbe, build_autostart_probe, create_app
from flight_deals.config import PROJECT_DIR, Config, load_config
from flight_deals.logging_setup import (
    LOG_FILE_NAME,
    RedactingFilter,
    RedactingFormatter,
    setup_file_logging,
)
from flight_deals.ports import AutostartStatus
from flight_deals.redact import register_secret
from flight_deals.scheduler import SchedulerLockHeldError
from tests.conftest import FakeClock, FakeNotifier, ScriptedSource

FAKE_TOKEN = "123456:FAKE-TOKEN-for-log-tests"


class FakeRegistry:
    def __init__(self, values: dict[str, str] | None = None, *, broken: bool = False) -> None:
        self.values = dict(values or {})
        self.broken = broken
        self.writes: list[tuple[str, str]] = []

    def get(self, name: str) -> str | None:
        if self.broken:
            raise PermissionError("access denied")
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        if self.broken:
            raise PermissionError("access denied")
        self.writes.append((name, value))
        self.values[name] = value

    def delete(self, name: str) -> bool:
        if self.broken:
            raise PermissionError("access denied")
        return self.values.pop(name, None) is not None


@pytest.fixture
def project(tmp_path: Path) -> Path:
    scripts = tmp_path / "proj" / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "pythonw.exe").write_bytes(b"")
    return tmp_path / "proj"


def test_expected_command_uses_pythonw_background(project: Path) -> None:
    command = autostart.expected_command(project)
    assert (
        command
        == f'"{project / ".venv" / "Scripts" / "pythonw.exe"}" -m flight_deals.cli --background'
    )
    for secret_hint in ("TOKEN", "CHAT_ID", "runas"):
        assert secret_hint not in command


def test_install_status_uninstall_cycle(project: Path) -> None:  # AC-AS1, AS2, AS5, AS6
    registry = FakeRegistry()
    assert autostart.status(project, registry) == autostart.RegistrationState(False, False, None)
    assert autostart.install(project, registry) == "created"
    assert list(registry.values) == [autostart.VALUE_NAME]  # only the flight-deals value
    state = autostart.status(project, registry)
    assert state.registered and state.points_here
    assert autostart.install(project, registry) == "unchanged"
    assert len(registry.writes) == 1
    registry.values[autostart.VALUE_NAME] = '"D:\\old\\pythonw.exe" -m flight_deals.cli'
    other = autostart.status(project, registry)
    assert other.registered and not other.points_here
    assert autostart.install(project, registry) == "replaced"
    assert autostart.uninstall(registry) == "removed"
    assert autostart.uninstall(registry) == "absent"
    assert registry.values == {}


def test_install_refuses_without_pythonw(tmp_path: Path) -> None:  # AC-AS8 (no half-made entry)
    registry = FakeRegistry()
    assert autostart.install(tmp_path, registry) == "missing_pythonw"
    assert registry.values == {}


def test_cli_autostart_messages(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    registry = FakeRegistry()
    assert cli.run_autostart("status", registry=registry, project_dir=project) == 0
    assert "未安裝" in capsys.readouterr().out
    assert cli.run_autostart("install", registry=registry, project_dir=project) == 0
    assert "已安裝登入自動啟動" in capsys.readouterr().out
    assert cli.run_autostart("install", registry=registry, project_dir=project) == 0
    assert "未變更" in capsys.readouterr().out
    assert cli.run_autostart("status", registry=registry, project_dir=project) == 0
    assert "已安裝（指向此專案）" in capsys.readouterr().out
    assert cli.run_autostart("uninstall", registry=registry, project_dir=project) == 0
    assert "已移除" in capsys.readouterr().out
    assert cli.run_autostart("uninstall", registry=registry, project_dir=project) == 0
    assert "尚未安裝" in capsys.readouterr().out


def test_cli_autostart_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run_autostart("install", registry=FakeRegistry(), project_dir=tmp_path) == 1
    assert "uv sync" in capsys.readouterr().err
    broken = FakeRegistry(broken=True)
    assert cli.run_autostart("status", registry=broken, project_dir=tmp_path) == 1
    assert "無法存取" in capsys.readouterr().err


def test_cli_autostart_parser() -> None:
    args = cli.build_parser().parse_args(["autostart", "install"])
    assert (args.command, args.action) == ("autostart", "install")
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["autostart", "remove"])


def test_windows_registry_refused_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(autostart.AutostartUnavailableError):
        autostart.WindowsRegistry()
    assert cli.run_autostart("status") == 2


def test_probe_returns_none_off_windows_or_on_error(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert RegistryAutostartProbe(project, FakeRegistry(broken=True)).status() is None
    registry = FakeRegistry()
    autostart.install(project, registry)
    assert RegistryAutostartProbe(project, registry).status() == AutostartStatus(True, True)
    monkeypatch.setattr("flight_deals.app.sys.platform", "linux")
    assert build_autostart_probe(project) is None


class StaticProbe:
    def __init__(self, status: AutostartStatus | None, *, fail: bool = False) -> None:
        self._status = status
        self._fail = fail

    def status(self) -> AutostartStatus | None:
        if self._fail:
            raise RuntimeError("probe exploded")
        return self._status


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        (None, None),
        (StaticProbe(None), None),
        (StaticProbe(None, fail=True), None),
        (StaticProbe(AutostartStatus(False, False)), {"registered": False, "points_here": False}),
        (StaticProbe(AutostartStatus(True, True)), {"registered": True, "points_here": True}),
    ],
)
def test_health_page_autostart_context(
    tmp_path: Path, clock: FakeClock, probe: StaticProbe | None, expected: object
) -> None:  # AC-AS5, AC-AS7
    from fastapi.testclient import TestClient

    app = create_app(
        Config(db_path=tmp_path / "a.db"),
        sources=[ScriptedSource(clock)],
        notifier=FakeNotifier(),
        clock=clock,
        start_scheduler=False,
        autostart_probe=probe,
    )
    assert app.state.assembly.services.views.settings_page()["autostart"] == expected
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/settings").status_code == 200


# ---- background mode ----------------------------------------------------------------


@pytest.fixture
def restore_logging() -> Iterator[None]:
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_flight_deals", False):
            root.removeHandler(handler)
            handler.close()


def test_file_logging_is_rotating_and_redacted(tmp_path: Path, restore_logging: None) -> None:
    register_secret(FAKE_TOKEN)
    handler = setup_file_logging(tmp_path / LOG_FILE_NAME)
    assert isinstance(handler, RotatingFileHandler)
    assert any(isinstance(f, RedactingFilter) for f in handler.filters)
    assert isinstance(handler.formatter, RedactingFormatter)
    streams = [
        h
        for h in logging.getLogger().handlers
        if getattr(h, "_flight_deals", False) and not isinstance(h, RotatingFileHandler)
    ]
    assert streams == []
    log = logging.getLogger("flight_deals.test")
    log.warning("token %s in url https://api.telegram.org/bot%s/x", FAKE_TOKEN, FAKE_TOKEN)
    try:
        raise RuntimeError(f"boom {FAKE_TOKEN}")
    except RuntimeError:
        log.exception("failure")
    handler.flush()
    text = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "token *** in url" in text and "failure" in text
    assert FAKE_TOKEN not in text and "FAKE-TOKEN" not in text


def test_background_lock_held_logs_and_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_logging: None,
) -> None:  # AC-AS4
    config = Config(db_path=tmp_path / "data" / "flight-deals.db")
    monkeypatch.setattr(cli, "load_config", lambda production=True: config)

    def held(_config: Config) -> None:
        raise SchedulerLockHeldError("此資料庫已有另一個實例在執行排程")

    monkeypatch.setattr(cli, "acquire_scheduler_lock", held)
    monkeypatch.setattr(cli, "create_app", lambda *a, **k: pytest.fail("must not build app"))
    assert cli.main(["--background"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = (tmp_path / "data" / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "refusing to start" in text


def test_relative_db_path_is_resolved_from_project_dir(tmp_path: Path) -> None:
    relative = load_config({"FLIGHT_DEALS_DB_PATH": "data/other.db"}, dotenv_path=None)
    assert relative.db_path == PROJECT_DIR / "data" / "other.db"
    absolute = tmp_path / "abs.db"
    assert (
        load_config({"FLIGHT_DEALS_DB_PATH": str(absolute)}, dotenv_path=None).db_path == absolute
    )


def test_background_startup_crash_is_logged_with_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_logging: None,
) -> None:  # qa M1: pythonw has no stderr, so the log file must hold the traceback
    from flight_deals.storage.db import MigrationError
    from tests.conftest import FakeLock

    config = Config(db_path=tmp_path / "data" / "flight-deals.db")
    lock = FakeLock(held=True)
    monkeypatch.setattr(cli, "load_config", lambda production=True: config)
    monkeypatch.setattr(cli, "acquire_scheduler_lock", lambda _config: lock)

    def crash(*_args: object, **_kwargs: object) -> None:
        raise MigrationError("migration 2: 1 foreign key violation(s)")

    monkeypatch.setattr(cli, "create_app", crash)
    assert cli.main(["--background"]) == 1
    assert lock.release_calls == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = (tmp_path / "data" / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "startup failed" in text
    assert "Traceback" in text and "MigrationError: migration 2" in text
