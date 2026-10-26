"""Structural constraints from ADR-0002 (C-1..C-3, C-14, C-16, C-18, C-26, C-28, C-29, C-31,
C-34..C-36)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from flight_deals.cli import build_uvicorn_kwargs

APP_DIR = Path(__file__).resolve().parents[1]
SRC = APP_DIR / "src" / "flight_deals"
PACKAGE = "flight_deals"

# Allowed first-party dependencies per top-level module (see ADR-0002 module table).
ALLOWED: dict[str, set[str]] = {
    "domain": {"domain"},
    "ports": {"domain"},
    "sources": {"domain", "ports", "redact", "sources"},
    "notify": {"domain", "ports", "redact", "notify"},
    "storage": {"domain", "storage"},
    "services": {"domain", "ports", "storage", "services"},
    "scheduler": {"services", "scheduler"},
    "web": {"services", "web"},
    "config": set(),
    "logging_setup": {"redact"},
    "redact": set(),
    "app": {"*"},
    "autostart": set(),
    "cli": {"app", "config", "logging_setup", "autostart"},
    "__init__": set(),
}
THIRD_PARTY_LIMITS: dict[str, set[str]] = {
    # Top-level modules that may use each third-party package.
    "fast_flights": {"sources"},
    "httpx": {"sources", "notify"},
    "apscheduler": {"scheduler"},
    "fastapi": {"web", "app"},
    "starlette": {"web"},
    "jinja2": {"web"},
    "uvicorn": {"cli"},
}
STDLIB_ONLY = {"domain", "config", "logging_setup", "redact", "autostart"}


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    return rel.parts[0]


def imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def python_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_import_direction() -> None:  # C-3
    violations: list[str] = []
    for path in python_files():
        owner = module_name(path)
        allowed = ALLOWED[owner]
        for name in imports_of(path):
            root = name.split(".")[0]
            if root == PACKAGE:
                parts = name.split(".")
                target = parts[1] if len(parts) > 1 else "__init__"
                if "*" not in allowed and target not in allowed:
                    violations.append(f"{path.relative_to(SRC)} -> {name}")
            elif root in THIRD_PARTY_LIMITS and owner not in THIRD_PARTY_LIMITS[root]:
                violations.append(f"{path.relative_to(SRC)} -> third-party {name}")
    assert violations == []


def test_no_relative_imports() -> None:  # C-3: relative imports would bypass the scan above
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
        for path in python_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.level > 0
    ]
    assert offenders == []


def test_web_does_not_touch_storage_sources_notify() -> None:  # C-3
    for path in (SRC / "web").rglob("*.py"):
        for name in imports_of(path):
            assert not re.match(r"flight_deals\.(storage|sources|notify)", name), (path, name)


def test_stdlib_only_modules() -> None:
    import sys

    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for path in python_files():
        if module_name(path) not in STDLIB_ONLY:
            continue
        for name in imports_of(path):
            root = name.split(".")[0]
            assert root in stdlib or root == PACKAGE, (path, name)


def test_fast_flights_only_in_google_adapter() -> None:  # C-2
    hits = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*")
        if p.is_file()
        and p.suffix in {".py", ".html", ".js"}
        and "fast_flights" in p.read_text(encoding="utf-8")
    ]
    assert hits == ["sources/google_flights.py"]


def test_no_third_party_fetch_modes() -> None:
    source = (SRC / "sources" / "google_flights.py").read_text(encoding="utf-8")
    code_only = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("#", '"""'))
    )
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)]
    for call in calls:
        assert all(
            kw.arg not in {"integration", "fetch_integration", "proxy"} for kw in call.keywords
        )
    for banned in ("bright_data", "BrightData", "searchapi", "SearchAPI", "integrations"):
        assert banned not in code_only


def _assert_stdlib_only(path: Path) -> None:
    import sys

    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for name in imports_of(path):
        root = name.split(".")[0]
        assert root in stdlib or root == PACKAGE, (path, name)


def test_google_payload_parser_is_stdlib_only_and_independent() -> None:  # C-26
    path = SRC / "sources" / "google_payload.py"
    _assert_stdlib_only(path)
    assert "fast_flights" not in path.read_text(encoding="utf-8")


def test_google_adapter_uses_only_query_builder_and_html_fetcher() -> None:  # C-26
    tree = ast.parse((SRC / "sources" / "google_flights.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fast_flights")
        for alias in node.names
    }
    assert imported == {"FlightQuery", "Passengers", "create_query", "fetch_flights_html"}


def test_scheduler_lock_is_stdlib_only_and_never_deletes_or_kills() -> None:  # C-28
    path = SRC / "scheduler" / "lock.py"
    _assert_stdlib_only(path)
    code = path.read_text(encoding="utf-8")
    for banned in ("os.kill", "unlink", "os.remove", "rmtree", "O_EXCL"):
        assert banned not in code, banned


def test_security_headers_middleware_is_added_last() -> None:  # C-29
    tree = ast.parse((SRC / "web" / "server.py").read_text(encoding="utf-8"))
    added = [
        node.args[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_middleware"
        and node.args
        and isinstance(node.args[0], ast.Name)
    ]
    assert added == ["BaseHTTPMiddleware", "TrustedHostMiddleware", "SecurityHeadersMiddleware"]
    assert "@app.middleware" not in (SRC / "web" / "server.py").read_text(encoding="utf-8")


def test_no_node_toolchain() -> None:  # C-1
    offenders = [
        p
        for pattern in ("package.json", "vite.config.*", "*.jsx", "*.tsx")
        for p in APP_DIR.rglob(pattern)
        if ".venv" not in p.parts
    ]
    assert offenders == []
    for path in (SRC / "web").rglob("*"):
        if path.is_file() and path.suffix in {".html", ".js"}:
            text = path.read_text(encoding="utf-8").lower()
            for framework in ("react", "vue", "jquery", "alpine", "htmx", "cdn."):
                assert framework not in text, (path, framework)


def test_js_only_in_static() -> None:  # C-14
    js_files = [p for p in APP_DIR.rglob("*.js") if ".venv" not in p.parts]
    assert js_files and all(p.parent == SRC / "web" / "static" for p in js_files)
    for template in (SRC / "web" / "templates").glob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert "<script>" not in text
        assert re.search(r"\son[a-z]+=", text) is None, template
        for src in re.findall(r'<script[^>]*src="([^"]+)"', text):
            assert src.startswith("/static/"), src


def test_gitignore_covers_local_state() -> None:  # C-16
    lines = (APP_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
    entries = (".venv/", "data/", "*.db", "*.db.lock", "*.sqlite*", "__pycache__/", ".env")
    for entry in (*entries, "*.log"):  # *.log: background-mode log file (C-36)
        assert entry in lines


def test_env_example_has_only_placeholders() -> None:
    text = (APP_DIR / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"bot\d+:[A-Za-z0-9_-]{20,}", text) is None
    assert re.search(r"\d{6,}:[A-Za-z0-9_-]{20,}", text) is None


def test_dependencies_locked() -> None:  # C-18
    lock = (APP_DIR / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "fast-flights"' in lock
    match = re.search(r'name = "apscheduler"\nversion = "(\d+)\.', lock)
    assert match and match.group(1) == "3"
    pyproject = (APP_DIR / "pyproject.toml").read_text(encoding="utf-8")
    assert "typing-extensions" in pyproject or "typing_extensions" in pyproject


def test_server_binds_loopback_single_worker() -> None:  # C-12, C-7
    kwargs = build_uvicorn_kwargs(8795)
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["workers"] == 1 and kwargs["reload"] is False


def test_autostart_has_no_process_or_task_scheduler_tricks() -> None:  # C-36
    banned = ("schtasks", "reg.exe", ".vbs", "subprocess")
    paths = [SRC / "autostart.py", *(SRC / "web").rglob("*"), *(SRC / "services").rglob("*")]
    hits = [
        f"{p.relative_to(SRC).as_posix()}: {word}"
        for p in paths
        if p.is_file() and p.suffix in {".py", ".html", ".js"}
        for word in banned
        if word in p.read_text(encoding="utf-8").lower()
    ]
    assert hits == []


def test_get_updates_only_in_telegram_adapter() -> None:  # C-35
    hits = [
        p.relative_to(SRC).as_posix()
        for p in python_files()
        if "getUpdates" in p.read_text(encoding="utf-8")
        and p.relative_to(SRC).as_posix() != "notify/telegram.py"
    ]
    # cli.py may name the API in user-facing text, but never builds the request.
    assert [h for h in hits if h != "cli.py"] == []
    assert "api.telegram.org" not in (SRC / "cli.py").read_text(encoding="utf-8")


def test_cli_does_not_import_notify_redact_or_domain() -> None:  # C-35
    names = imports_of(SRC / "cli.py")
    assert not [n for n in names if re.match(r"flight_deals\.(notify|redact|domain)", n)]


def test_latest_per_pair_defined_once() -> None:  # C-34
    owners = [
        p.relative_to(SRC).as_posix()
        for p in python_files()
        if re.search(r"^def latest_per_pair\(", p.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert owners == ["services/price_snapshot.py"]


def test_scheduler_imports_only_services() -> None:  # C-32
    for path in (SRC / "scheduler").rglob("*.py"):
        for name in imports_of(path):
            if name.startswith("flight_deals."):
                assert name.split(".")[1] in {"services", "scheduler"}, (path, name)


def test_marked_migrations_only_rebuild_with_foreign_keys_off() -> None:  # C-33
    from flight_deals.storage.db import available_migrations, needs_foreign_keys_off

    for version, sql in available_migrations():
        upper = sql.upper()
        if "DROP TABLE" in upper or "RENAME TO" in upper:
            assert needs_foreign_keys_off(sql), version
