"""``flight-deals --replace``: stop a previous instance holding the scheduler lock
(CEO 2026-10-31)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from flight_deals import autostart, cli
from flight_deals.app import SchedulerLockHeldError, scheduler_lock_path
from flight_deals.config import Config

CHILD = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from flight_deals.scheduler.lock import FileSchedulerLock\n"
    "FileSchedulerLock(Path(sys.argv[1])).acquire()\n"
    "print('ready', flush=True)\n"
    "time.sleep(60)\n"
)


class Recorder:
    def __init__(self, *, alive: bool = True, ours: bool = True) -> None:
        self.is_alive = alive
        self.ours = ours
        self.fail_with: BaseException | None = None
        self.terminated: list[int] = []
        self.now = 0.0
        self.sleeps = 0

    def hooks(self) -> cli.ReplaceHooks:
        return cli.ReplaceHooks(
            alive=lambda pid: self.is_alive,
            is_ours=lambda pid: self.ours,
            terminate=self._terminate,
            sleep=self._sleep,
            monotonic=lambda: self.now,
        )

    def _terminate(self, pid: int) -> None:
        self.terminated.append(pid)
        if self.fail_with is not None:
            raise self.fail_with

    def _sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.now += seconds


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(db_path=tmp_path / "data" / "flight-deals.db")


def write_header(config: Config, text: str) -> None:
    path = scheduler_lock_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode().ljust(255) + b"\n")


def always_held(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def held(_config: Config) -> None:
        calls.append(1)
        raise SchedulerLockHeldError("held")

    monkeypatch.setattr(cli, "acquire_scheduler_lock", held)
    return calls


def test_parser_has_replace_flag() -> None:
    assert cli.build_parser().parse_args(["--replace"]).replace is True
    assert cli.build_parser().parse_args([]).replace is False


def test_stale_header_of_an_exited_pid_takes_the_lock_directly(config: Config) -> None:
    write_header(config, "pid=999999 started_at=2026-10-31T00:00:00+00:00")
    recorder = Recorder()
    lock = cli.take_lock(config, replace=True, hooks=recorder.hooks())
    try:
        assert lock.held and recorder.terminated == [] and recorder.sleeps == 0
    finally:
        lock.release()


def test_live_holder_is_stopped_and_the_lock_taken(config: Config) -> None:
    path = scheduler_lock_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, str(path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "ready"
        with pytest.raises(SchedulerLockHeldError):
            cli.take_lock(config, replace=False)
        assert cli.process_alive(child.pid)
        lock = cli.take_lock(config, replace=True)
        try:
            assert lock.held
            assert child.wait(timeout=15) is not None
            assert not cli.process_alive(child.pid)
        finally:
            lock.release()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=15)
        if child.stdout is not None:
            child.stdout.close()


@pytest.mark.parametrize("header", ["", "garbage", "pid=abc started_at=x", "pid=12"])
def test_unreadable_header_refuses(
    config: Config, monkeypatch: pytest.MonkeyPatch, header: str
) -> None:
    write_header(config, header)
    always_held(monkeypatch)
    recorder = Recorder()
    with pytest.raises(SchedulerLockHeldError):
        cli.take_lock(config, replace=True, hooks=recorder.hooks())
    assert recorder.terminated == [] and recorder.sleeps == 0


def test_own_pid_is_never_killed(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    write_header(config, f"pid={os.getpid()} started_at=2026-10-31T00:00:00+00:00")
    always_held(monkeypatch)
    recorder = Recorder()
    with pytest.raises(SchedulerLockHeldError):
        cli.take_lock(config, replace=True, hooks=recorder.hooks())
    assert recorder.terminated == []


def test_without_replace_nothing_is_killed(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    write_header(config, "pid=4242 started_at=2026-10-31T00:00:00+00:00")
    calls = always_held(monkeypatch)
    recorder = Recorder()
    with pytest.raises(SchedulerLockHeldError):
        cli.take_lock(config, replace=False, hooks=recorder.hooks())
    assert calls == [1] and recorder.terminated == [] and recorder.sleeps == 0


def test_gives_up_after_15_seconds(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    write_header(config, "pid=4242 started_at=2026-10-31T00:00:00+00:00")
    calls = always_held(monkeypatch)
    recorder = Recorder()
    with pytest.raises(SchedulerLockHeldError):
        cli.take_lock(config, replace=True, hooks=recorder.hooks())
    assert recorder.terminated == [4242]
    assert recorder.sleeps == 30 and len(calls) == 31  # every 0.5 s for 15 s


def test_serve_refuses_with_exit_2_when_replace_fails(
    config: Config, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_header(config, "garbage")
    always_held(monkeypatch)
    monkeypatch.setattr(cli, "create_app", lambda *a, **k: pytest.fail("must not build app"))
    assert cli._serve(config, 8795, replace=True) == 2
    assert "refusing to start" in caplog.text


def test_autostart_command_line_has_replace(tmp_path: Path) -> None:
    command = autostart.expected_command(tmp_path)
    assert command.endswith("-m flight_deals.cli --background --replace")


@pytest.mark.parametrize(
    "error",
    [PermissionError("denied"), ProcessLookupError("gone"), subprocess.TimeoutExpired("x", 1)],
)
def test_terminate_failure_still_retries_then_refuses_with_exit_2(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: BaseException,
) -> None:  # QA medium 1
    write_header(config, "pid=4242 started_at=2026-10-31T00:00:00+00:00")
    calls = always_held(monkeypatch)
    recorder = Recorder()
    recorder.fail_with = error
    monkeypatch.setattr(cli, "REPLACE_HOOKS", recorder.hooks())
    monkeypatch.setattr(cli, "create_app", lambda *a, **k: pytest.fail("must not build app"))
    assert cli._serve(config, 8795, replace=True) == cli.EXIT_CONFIG == 2
    assert recorder.terminated == [4242] and recorder.sleeps == 30 and len(calls) == 31
    assert "could not terminate pid=4242" in caplog.text and "refusing to start" in caplog.text


def test_foreign_process_is_never_terminated(
    config: Config, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:  # QA medium 2
    write_header(config, "pid=4242 started_at=2026-10-31T00:00:00+00:00")
    always_held(monkeypatch)
    recorder = Recorder(ours=False)
    with pytest.raises(SchedulerLockHeldError):
        cli.take_lock(config, replace=True, hooks=recorder.hooks())
    assert recorder.terminated == [] and recorder.sleeps == 30
    assert "lock holder pid=4242 is not a flight-deals process; not terminating" in caplog.text


def test_identity_check_on_real_processes() -> None:  # QA medium 2
    # The test runner is a python process; on Windows the image name is checked.
    if sys.platform == "win32":
        assert cli.is_flight_deals_process(os.getpid())
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait(timeout=15)
    assert not cli.is_flight_deals_process(finished.pid)
    assert not cli.process_alive(finished.pid)
    assert cli.process_alive(os.getpid())
