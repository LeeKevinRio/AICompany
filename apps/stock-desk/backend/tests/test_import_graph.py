"""The import scanner resolves every module name it is handed, the bare root included."""

from __future__ import annotations

from tests.import_graph import APP_ROOT, module_path, reachable_app_modules


def test_the_bare_app_root_resolves_to_its_package_file() -> None:
    assert module_path("app") == APP_ROOT / "__init__.py"
    assert module_path("app.sectors") == APP_ROOT / "sectors" / "__init__.py"
    assert module_path("app.sectors.gate") == APP_ROOT / "sectors" / "gate.py"
    assert module_path("apple") is None
    assert module_path("app.no_such_module") is None


def test_walking_from_the_root_does_not_raise() -> None:
    assert "app" in reachable_app_modules(("app",))
