"""The CG-2 registration values (ADR-0030 supplement 4 point 5 M-2 to M-5; suppl. 6 point 6 (c)).

* M-2: the pre-registration v0.32 blob sha256 (``git cat-file blob HEAD:<path>``);
* M-3: the C-8 decision record blob sha256 (RC-152 point 1) equals
  ``dirdef-v1.0``'s ``c8_decision_sha256``, and ``c8_decision_ref`` is its path;
* M-4: ``dirdef-v1.0`` is in ``PUBLISHED_DIRECTION_DEFINITIONS`` with both hashes
  pinned; its ``definition_logic_sha256`` equals the test stand-in's
  (``tests.dirdef_helpers.dirdef_v1_0``, the definition the D-7 acceptance run
  uses) and the two ``definition_sha256`` differ only in
  ``DEFINITION_NON_LOGIC_FIELDS`` (supplement 6 point 6 (c));
* M-5: h3 / h5 are in ``PUBLISHED_RULESETS`` with ``rules_sha256`` and
  ``rules_logic_sha256`` pinned, and the YAML bytes are the freeze pack §4.1 /
  §4.2 blocks byte for byte (supplement 6 addendum point 8, RC-163), extracted
  by the rule in :data:`FREEZE_PACK_BLOCKS`.

Git blobs are read from ``HEAD`` with ``git cat-file blob``; nothing is written.
"""

from __future__ import annotations

import hashlib
import subprocess
from functools import cache
from pathlib import Path
from typing import Final

import pytest

from app.dirdef.definition import (
    DEFINITION_NON_LOGIC_FIELDS,
    definition_logic_sha256,
    definition_sha256,
)
from app.dirdef.registry import PUBLISHED_DIRECTION_DEFINITIONS, PUBLISHED_RULESETS
from app.dirdef.rules import OUTLOOK_RULE_FIELDS, rules_logic_sha256
from app.dirdef.v1_0 import DIRDEF_V1_0
from app.forecast import definitions
from tests.dirdef_helpers import dirdef_v1_0

BACKEND_DIR: Final = Path(__file__).resolve().parent.parent

#: M-2: pre-registration v0.32 (repo-relative path, sha256 of its blob).
PREREG_DOC_PATH: Final = "work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md"
PREREG_DOC_SHA256: Final = "7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e"

#: M-3: the C-8 decision record (RC-152 point 1: sha256 of the git blob).
C8_RECORD_PATH: Final = "work/dispatch/2026-11-15-C8決策紀錄-F2B.md"
C8_RECORD_SHA256: Final = "c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f"

#: M-4: the two registered definition hashes of ``dirdef-v1.0``.
DEFINITION_VERSION: Final = "dirdef-v1.0"
DEFINITION_LOGIC_SHA256: Final = "4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa"
DEFINITION_SHA256: Final = "2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0"

#: M-5: rules_version -> (horizon, rules_sha256, rules_logic_sha256).
RULESETS: Final = {
    "outlook-market-v1.0-h3": (
        3,
        "f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443",
        "ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484",
    ),
    "outlook-market-v1.0-h5": (
        5,
        "0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c",
        "e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb",
    ),
}

#: The freeze pack whose §4.1 / §4.2 blocks are the rule file bytes (RC-163).
FREEZE_PACK_PATH: Final = "work/research/2026-11-14-NM5凍結包-大盤h3h5-quant.md"
#: Extraction rule: in the freeze pack blob (UTF-8, split into lines keeping their
#: ``\n``), find the line equal to the heading; the block is every line strictly
#: between the first following line equal to :data:`FENCE_OPEN` and the first
#: line after that equal to :data:`FENCE_CLOSE`, joined unchanged. It fails
#: (:class:`FreezePackBlockError`) when the heading line occurs 0 times or more
#: than once, when no opening fence follows the heading before the next heading
#: (a line starting with ``#`` outside a fence) or the end, and when no closing
#: fence follows the opening one (TA CG-2 checklist item 6).
FREEZE_PACK_BLOCKS: Final = {3: "### 4.1 h3.yaml\n", 5: "### 4.2 h5.yaml\n"}
FENCE_OPEN: Final = "```yaml\n"
FENCE_CLOSE: Final = "```\n"


@cache
def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(out.stdout.strip())


@cache
def _blob(path: str) -> bytes:
    """``git cat-file blob HEAD:<path>``: the committed bytes of a repo-relative path."""
    return subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{path}"],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
    ).stdout


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FreezePackBlockError(ValueError):
    """The freeze pack does not hold exactly one well-fenced block under the heading."""


def freeze_pack_block(text: str, heading: str) -> bytes:
    """The fenced YAML block under ``heading`` (the :data:`FREEZE_PACK_BLOCKS` rule)."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line == heading]
    if len(starts) != 1:
        raise FreezePackBlockError(f"the heading occurs {len(starts)} times, not once")
    opening = None
    for i in range(starts[0] + 1, len(lines)):
        if lines[i] == FENCE_OPEN:
            opening = i
            break
        if lines[i].startswith("#"):
            break
    if opening is None:
        raise FreezePackBlockError("no opening fence under the heading")
    closing = next((i for i in range(opening + 1, len(lines)) if lines[i] == FENCE_CLOSE), None)
    if closing is None:
        raise FreezePackBlockError("no closing fence after the opening one")
    return "".join(lines[opening + 1 : closing]).encode("utf-8")


# --- M-2, M-3 ------------------------------------------------------------------------------


def test_m2_the_pre_registration_blob_hash() -> None:
    assert _sha256(_blob(PREREG_DOC_PATH)) == PREREG_DOC_SHA256


def test_m3_the_c8_record_blob_hash_is_the_definitions_c8_field() -> None:
    assert _sha256(_blob(C8_RECORD_PATH)) == C8_RECORD_SHA256
    assert DIRDEF_V1_0.c8_decision_sha256 == C8_RECORD_SHA256
    assert DIRDEF_V1_0.c8_decision_ref == C8_RECORD_PATH
    assert DIRDEF_V1_0.f2_variant == "F2-B"


# --- M-4 -----------------------------------------------------------------------------------


def test_m4_dirdef_v1_0_is_the_one_registered_definition() -> None:
    assert set(PUBLISHED_DIRECTION_DEFINITIONS) == {DEFINITION_VERSION}
    entry = PUBLISHED_DIRECTION_DEFINITIONS[DEFINITION_VERSION]
    assert entry.definition is DIRDEF_V1_0
    assert entry.definition_logic_sha256 == DEFINITION_LOGIC_SHA256
    assert entry.definition_sha256 == DEFINITION_SHA256


def test_m4_the_registered_hashes_are_recomputed_and_accepted() -> None:
    assert definition_logic_sha256(DIRDEF_V1_0) == DEFINITION_LOGIC_SHA256
    assert definition_sha256(DIRDEF_V1_0) == DEFINITION_SHA256
    assert definitions.get_definition(DEFINITION_VERSION) is DIRDEF_V1_0


def test_6c_the_logic_hash_equals_the_acceptance_stand_ins() -> None:
    # Supplement 6 point 6 (c): the D-7 run's definition_logic_sha256 is the stand-in's.
    assert definition_logic_sha256(dirdef_v1_0()) == DEFINITION_LOGIC_SHA256


def test_6c_the_full_hashes_differ_only_in_non_logic_fields() -> None:
    registered = DIRDEF_V1_0.model_dump(mode="json")
    stand_in = dirdef_v1_0().model_dump(mode="json")
    assert set(registered) == set(stand_in)
    differing = {name for name in registered if registered[name] != stand_in[name]}
    assert differing <= DEFINITION_NON_LOGIC_FIELDS
    assert differing == {"c8_decision_ref", "c8_decision_sha256"}
    # So the full hashes differ, and only because of those fields.
    assert definition_sha256(dirdef_v1_0()) != DEFINITION_SHA256
    patched = {**stand_in, **{name: registered[name] for name in differing}}
    assert patched == registered


# --- M-5 -----------------------------------------------------------------------------------


def test_m5_the_two_rule_sets_are_registered() -> None:
    registered = {v: (e.horizon, e.rules_sha256) for v, e in PUBLISHED_RULESETS.items()}
    assert registered == {version: (h, digest) for version, (h, digest, _) in RULESETS.items()}


@pytest.mark.parametrize("version", sorted(RULESETS))
def test_m5_the_rule_files_load_with_the_pinned_hashes(version: str) -> None:
    horizon, digest, logic = RULESETS[version]
    data = definitions.rules_path(horizon).read_bytes()
    assert _sha256(data) == digest
    assert definitions.get_rules_bytes(version) == data
    assert rules_logic_sha256(definitions.get_ruleset(version)) == logic
    assert definitions.get_ruleset_entry(version).horizon == horizon


def test_m5_outlook_rule_fields_are_set() -> None:
    assert len(OUTLOOK_RULE_FIELDS) == 9


@pytest.mark.parametrize("horizon", sorted(FREEZE_PACK_BLOCKS))
def test_rc163_the_rule_file_blob_is_the_freeze_pack_block(horizon: int) -> None:
    text = _blob(FREEZE_PACK_PATH).decode("utf-8")
    block = freeze_pack_block(text, FREEZE_PACK_BLOCKS[horizon])
    yaml_blob = _blob(f"apps/stock-desk/backend/app/outlook/rules/h{horizon}.yaml")
    assert _sha256(block) == _sha256(yaml_blob)
    expected = next(d for h, d, _ in RULESETS.values() if h == horizon)
    assert _sha256(yaml_blob) == expected


def test_rc163_the_extraction_rule_has_teeth() -> None:
    text = "intro\n### 4.1 h3.yaml\n```yaml\na: 1\n\nb: 2\n```\n```yaml\nc: 3\n```\n"
    assert freeze_pack_block(text, "### 4.1 h3.yaml\n") == b"a: 1\n\nb: 2\n"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("intro\n```yaml\na: 1\n```\n", "occurs 0 times"),
        ("### 4.1 h3.yaml\n```yaml\na\n```\n### 4.1 h3.yaml\n```yaml\nb\n```\n", "2 times"),
        ("### 4.1 h3.yaml\ntext\n", "no opening fence"),
        ("### 4.1 h3.yaml\ntext\n### 4.2 h5.yaml\n```yaml\na\n```\n", "no opening fence"),
        ("### 4.1 h3.yaml\n```\na\n```\n", "no opening fence"),
        ("### 4.1 h3.yaml\n```yaml\na: 1\n", "no closing fence"),
        ("### 4.1 h3.yaml\n```yaml\na: 1\n``` \n", "no closing fence"),
    ],
    ids=[
        "heading_absent",
        "heading_twice",
        "no_fence",
        "fence_under_the_next_heading",
        "fence_without_yaml",
        "no_closing_fence",
        "closing_fence_with_trailing_space",
    ],
)
def test_rc163_the_extraction_rule_fails_closed(text: str, message: str) -> None:
    with pytest.raises(FreezePackBlockError, match=message):
        freeze_pack_block(text, "### 4.1 h3.yaml\n")


@pytest.mark.parametrize("version", sorted(RULESETS))
def test_m6_the_registration_phrase_scan_has_no_hit(version: str) -> None:
    scan = definitions.registration_phrase_scan(
        definitions.get_ruleset(version), definitions.get_definition(DEFINITION_VERSION)
    )
    assert scan.hits == ()
    assert (scan.rules_strings, scan.definition_strings, scan.phrases) == (159, 12, 10)


# --- M-7 / RC-183: the three .gitattributes files -------------------------------------------

#: Repo-relative path -> its exact lines (supplement 7 addendum 2 point 5; RC-183): only
#: ``text eol=lf``, no wildcard, no other attribute. The ``uv.lock`` line predates CG-2.
GITATTRIBUTES: Final = {
    "apps/stock-desk/backend/.gitattributes": [
        "uv.lock text eol=lf",
        "/app/outlook/rules/h3.yaml text eol=lf",
        "/app/outlook/rules/h5.yaml text eol=lf",
    ],
    "work/research/.gitattributes": [f"/{Path(PREREG_DOC_PATH).name} text eol=lf"],
    "work/dispatch/.gitattributes": [f"/{Path(C8_RECORD_PATH).name} text eol=lf"],
}


@pytest.mark.parametrize("path", sorted(GITATTRIBUTES))
def test_rc183_each_gitattributes_file_holds_exactly_its_lines(path: str) -> None:
    data = (_repo_root() / path).read_bytes()
    assert data.endswith(b"\n") and b"\r" not in data
    assert data.decode("utf-8").split("\n")[:-1] == GITATTRIBUTES[path]


def test_rc183_the_lines_use_no_wildcard_and_only_text_eol_lf() -> None:
    for lines in GITATTRIBUTES.values():
        for line in lines:
            pattern, *attributes = line.split(" ")
            assert attributes == ["text", "eol=lf"], line
            assert not set(pattern) & set("*?[]!"), line
    assert GITATTRIBUTES["work/research/.gitattributes"] == [
        "/2026-10-15-3日5日方向判斷-事先宣告草案.md text eol=lf"
    ]
    assert GITATTRIBUTES["work/dispatch/.gitattributes"] == [
        "/2026-11-15-C8決策紀錄-F2B.md text eol=lf"
    ]
