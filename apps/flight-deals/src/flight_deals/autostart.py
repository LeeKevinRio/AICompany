r"""Windows login autostart via the per-user Run key (ADR-0002 FD-4 Decision 8, C-36).

Stdlib only, no first-party imports. Only the ``flight-deals`` value under
``HKCU\Software\Microsoft\Windows\CurrentVersion\Run`` is ever read or written, so no
administrator rights are needed. Registry access goes through the injectable
``Registry`` interface; tests use an in-memory fake and never touch the real hive.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "flight-deals"
BACKGROUND_FLAG = "--background"
# A login start stops a previous instance still holding the database (CEO 2026-10-31).
REPLACE_FLAG = "--replace"


class Registry(Protocol):
    """String values of the HKCU Run key."""

    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> bool: ...


class AutostartUnavailableError(RuntimeError):
    """Login autostart is only supported on Windows."""


class WindowsRegistry:
    """``winreg`` access to ``RUN_KEY`` under ``HKEY_CURRENT_USER``."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise AutostartUnavailableError("login autostart is only available on Windows")

    def get(self, name: str) -> str | None:
        if sys.platform != "win32":  # pragma: no cover - guarded in __init__
            return None
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _kind = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        return value if isinstance(value, str) else None

    def set(self, name: str, value: str) -> None:
        if sys.platform != "win32":  # pragma: no cover - guarded in __init__
            return
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name: str) -> bool:
        if sys.platform != "win32":  # pragma: no cover - guarded in __init__
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            return False
        return True


def pythonw_path(project_dir: Path) -> Path:
    """Windowless interpreter of the project's uv-managed virtual environment."""
    return project_dir / ".venv" / "Scripts" / "pythonw.exe"


def expected_command(project_dir: Path) -> str:
    """The Run value this checkout installs (no secrets: those stay in ``.env``)."""
    return f'"{pythonw_path(project_dir)}" -m flight_deals.cli {BACKGROUND_FLAG} {REPLACE_FLAG}'


def _normalise(command: str) -> str:
    return os.path.normcase(" ".join(command.split()))


@dataclass(frozen=True)
class RegistrationState:
    registered: bool
    points_here: bool
    command: str | None


def status(project_dir: Path, registry: Registry) -> RegistrationState:
    current = registry.get(VALUE_NAME)
    if current is None:
        return RegistrationState(False, False, None)
    here = _normalise(current) == _normalise(expected_command(project_dir))
    return RegistrationState(True, here, current)


InstallOutcome = Literal["created", "replaced", "unchanged", "missing_pythonw"]
UninstallOutcome = Literal["removed", "absent"]


def install(project_dir: Path, registry: Registry) -> InstallOutcome:
    """Write (or overwrite) the single Run value; refuses without ``pythonw.exe``."""
    if not pythonw_path(project_dir).is_file():
        return "missing_pythonw"
    previous = registry.get(VALUE_NAME)
    command = expected_command(project_dir)
    if previous is not None and _normalise(previous) == _normalise(command):
        return "unchanged"
    registry.set(VALUE_NAME, command)
    return "created" if previous is None else "replaced"


def uninstall(registry: Registry) -> UninstallOutcome:
    return "removed" if registry.delete(VALUE_NAME) else "absent"
