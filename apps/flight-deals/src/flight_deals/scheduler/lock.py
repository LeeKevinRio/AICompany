"""Cross-process scheduler lock: at most one scheduler per database (stdlib only).

The lock is an OS advisory/byte-range lock on ``<db_path>.lock``. The OS drops it when
the holding process exits, however it exits, so a leftover lock file is harmless and
is never deleted. The first bytes of the file carry the holder's PID and start time
for display only; they are never used to decide who holds the lock.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# Windows byte-range locks are mandatory: lock one byte past the header so other
# processes can still read who holds the lock.
LOCK_OFFSET = 4096
HEADER_SIZE = 256
HELD_MESSAGE = "此資料庫已有另一個實例在執行排程"


class SchedulerLockHeldError(RuntimeError):
    """Another process already holds the scheduler lock for this database."""


class SchedulerLock(Protocol):
    @property
    def held(self) -> bool: ...

    def acquire(self) -> None:
        """Take the lock without blocking; raise ``SchedulerLockHeldError`` if taken."""

    def release(self) -> None:
        """Give the lock back. Safe to call when not held."""


def _try_lock(fd: int) -> None:
    if sys.platform == "win32":
        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


class FileSchedulerLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
        try:
            _try_lock(fd)
        except OSError as exc:
            os.close(fd)
            holder = self.holder_info()
            detail = f"（{holder}）" if holder else ""
            raise SchedulerLockHeldError(f"{HELD_MESSAGE}{detail}：{self.path}") from exc
        self._fd = fd
        self._write_header(fd)

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            _unlock(fd)
        except OSError:
            pass  # closing the descriptor below releases it anyway
        finally:
            os.close(fd)

    def holder_info(self) -> str | None:
        """Display-only text written by the current holder (may be stale or empty)."""
        try:
            # Unbuffered and bounded: a buffered read would reach the locked byte.
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                raw = os.read(fd, HEADER_SIZE)
            finally:
                os.close(fd)
        except OSError:
            return None
        text = raw.decode("utf-8", errors="replace").strip()
        return text or None

    @staticmethod
    def _write_header(fd: int) -> None:
        started = datetime.now(UTC).isoformat(timespec="seconds")
        header = f"pid={os.getpid()} started_at={started}".encode()[: HEADER_SIZE - 1]
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, header.ljust(HEADER_SIZE - 1) + b"\n")
        except OSError:
            pass  # informational only
