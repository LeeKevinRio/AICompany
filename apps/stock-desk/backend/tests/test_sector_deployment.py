"""Judgement deployment constraints (ADR-0012 C-52; T-36).

* ``app/services/sector_attestation.py`` and ``app/services/sector_runtime.py``
  read no environment, no ``.env`` and no settings: ``running_commit``,
  ``ci_passed_commit`` and ``suite_hash`` come only from git, the attestation
  file and the test files on disk (with a teeth test);
* an image-shaped layout -- ``app/`` and an attestation copied to a directory
  with no ``.git`` and no ``tests/`` -- fails closed: ``verify()`` reports
  ``git_unreadable`` and ``suite_hash_mismatch``, the statistics row written
  there has ``selfcheck_passed = false``, and the card's
  ``not_evaluated_reasons`` include ``lookahead_tests_failed`` (NE-7);
* ``backend/.dockerignore`` exists and keeps ``app/_build`` out of the image.
"""

from __future__ import annotations

import ast
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.positions.store import PositionStore
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import GateRules, SectorMomentumDefinition
from app.sectors.store import SectorMethodRegistry
from app.services import sector_attestation as att
from app.services.sector_attestation import (
    GIT_UNREADABLE,
    SUITE_HASH_MISMATCH,
    Attestation,
)
from app.services.sector_board import SectorBoardService
from app.services.sector_runtime import runtime_from_check
from tests.sector_board_helpers import card_client, store_market
from tests.sector_eval_helpers import synthetic_market

BACKEND = Path(__file__).resolve().parent.parent
#: The two modules C-52 keeps free of environment and configuration input.
JUDGEMENT_INPUT_MODULES = (
    BACKEND / "app" / "services" / "sector_attestation.py",
    BACKEND / "app" / "services" / "sector_runtime.py",
)
FORBIDDEN_MODULES = ("dotenv", "app.settings")
FORBIDDEN_NAMES = frozenset({"environ", "getenv"})
NOW = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
FAST = SectorMomentumDefinition(
    method_version=V1.method_version,
    lookback_days=V1.lookback_days,
    holding_days=V1.holding_days,
    gate=GateRules(lookahead_sample_dates=4),
)


# ---------------------------------------------------------------------------
# No environment, build argument or settings file behind the NE-7 inputs
# ---------------------------------------------------------------------------


def _config_hits(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []

    def forbidden(name: str) -> bool:
        return any(name == module or name.startswith(f"{module}.") for module in FORBIDDEN_MODULES)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [alias.name for alias in node.names if forbidden(alias.name)]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if forbidden(node.module):
                hits.append(node.module)
            # ``from app import settings`` names the package through its alias.
            hits += [
                f"{node.module}.{alias.name}"
                for alias in node.names
                if forbidden(f"{node.module}.{alias.name}")
            ]
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            hits.append(node.attr)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            hits.append(node.id)
        elif isinstance(node, ast.alias) and node.name in FORBIDDEN_NAMES:
            hits.append(node.name)
    return hits


@pytest.mark.parametrize("path", JUDGEMENT_INPUT_MODULES, ids=lambda path: path.name)
def test_judgement_inputs_read_no_environment_or_settings(path: Path) -> None:
    assert path.is_file()
    assert _config_hits(path) == []


@pytest.mark.parametrize(
    "source",
    [
        "import os\nCOMMIT = os.environ['GIT_COMMIT']\n",
        "import os\nCOMMIT = os.getenv('GIT_COMMIT')\n",
        "from os import getenv\n",
        "from os import environ\n",
        "import dotenv\n",
        "from dotenv import load_dotenv\n",
        "from app.settings.store import SettingsStore\n",
        "from app import settings\n",
        "import app.settings\n",
    ],
)
def test_the_environment_scan_has_teeth(tmp_path: Path, source: str) -> None:
    path = tmp_path / "sector_attestation.py"
    path.write_text(source, encoding="utf-8")
    assert _config_hits(path) != []


# ---------------------------------------------------------------------------
# An image-shaped layout fails closed (NE-7)
# ---------------------------------------------------------------------------


def _image(tmp_path: Path) -> Path:
    """``app/`` plus an attestation of the real suite, without ``.git`` or ``tests/``."""
    image = tmp_path / "image"
    shutil.copytree(
        BACKEND / "app",
        image / "app",
        ignore=shutil.ignore_patterns("__pycache__", "_build"),
    )
    att.write_attestation(
        att.attestation_path(image),
        Attestation(
            ci_passed_commit="c0ffee" * 6 + "c0ff",
            suite_hash=att.suite_hash(BACKEND),
            passed_at=NOW.isoformat(),
        ),
    )
    assert not (image / ".git").exists() and not (image / "tests").exists()
    return image


def test_an_image_layout_cannot_judge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # git must not find an enclosing repository above the temporary directory.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    image = _image(tmp_path)
    check = att.verify(image)
    assert GIT_UNREADABLE in check.problems
    assert SUITE_HASH_MISMATCH in check.problems
    assert not check.ok and check.running_commit is None

    market = synthetic_market(seed=21, warmup=62, forward=48, n_dividends=5)
    store = store_market(market, tmp_path / "market.db")
    main_db = tmp_path / "main.db"
    SectorMethodRegistry(main_db).register(FAST, frozen_commit="c0ffee", registered_at=NOW)
    service = SectorBoardService(
        market_store=store,
        main_db=main_db,
        attestation=lambda: check,
        clock=lambda: NOW,
        definition=FAST,
    )
    result = service.refresh()
    assert result.stats_run_id is not None, result.notes
    row = service.stats.find(result.stats_run_id)
    assert row is not None and not row.selfcheck_passed

    with card_client(
        main_db=main_db,
        market_db=tmp_path / "market.db",
        positions=PositionStore(tmp_path / "positions.db"),
        runtime=runtime_from_check(check),
        now=NOW,
    ) as client:
        response = client.get("/api/sectors/momentum", params={"market": "TW"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "lookahead_tests_failed" in body["not_evaluated_reasons"]
    assert body["historical_stat"] is None


def test_the_dockerignore_keeps_the_local_attestation_out() -> None:
    path = BACKEND / ".dockerignore"
    assert path.is_file()
    patterns = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert any(pattern.rstrip("/") == "app/_build" for pattern in patterns), patterns
