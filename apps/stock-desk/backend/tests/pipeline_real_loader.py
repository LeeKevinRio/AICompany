"""Loads ``scripts/pipeline_acceptance_real.py`` inside a test process without keeping its hooks.

The script's first statements replace ``sys.excepthook``, ``threading.excepthook`` and
``sys.unraisablehook`` and call ``warnings.simplefilter("ignore")`` (ADR-0030 supplement 6
addendum point 5, RC-162). Loaded in a pytest process that would leave the test run with
silenced hooks and filters, so the hooks and the warnings filter are saved before the load
and put back after it. The module is loaded once and cached.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import warnings
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_acceptance_real.py"
MODULE_NAME = "pipeline_acceptance_real"
_cache: list[ModuleType] = []


def load_script() -> ModuleType:
    """The script as a module; the process's hooks and warnings filters are as they were."""
    if _cache:
        return _cache[0]
    saved = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        with warnings.catch_warnings():  # restores the filters on exit
            spec.loader.exec_module(module)
    finally:
        sys.excepthook, threading.excepthook, sys.unraisablehook = saved
    _cache.append(module)
    return module
