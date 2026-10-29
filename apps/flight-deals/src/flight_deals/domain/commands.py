"""Telegram command parsing (ADR-0002 FD-7 Decision 3, C-51). Pure, stdlib only.

Only a fixed command set is recognised: no free text, no fuzzy matching. Commands that
would create, edit or delete a watch or change a setting simply do not exist here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

MAX_COMMAND_CHARS = 64
# Commands taking exactly one watch id; the rest take no argument.
ID_COMMANDS: frozenset[str] = frozenset({"watch", "scan", "pause", "resume"})
PLAIN_COMMANDS: frozenset[str] = frozenset({"help", "start", "list", "digest", "status"})
COMMANDS: frozenset[str] = ID_COMMANDS | PLAIN_COMMANDS
_WATCH_ID = re.compile(r"[1-9][0-9]{0,8}", re.ASCII)
_BOT_SUFFIX = re.compile(r"@[A-Za-z0-9_]+", re.ASCII)

ParseStatus = Literal["ok", "not_command", "too_long", "unknown", "missing_arg", "bad_arg"]


@dataclass(frozen=True)
class ParsedCommand:
    """``name`` is the lower-case command without "/" (None when not recognised);
    ``text`` is the normalised input cut to ``MAX_COMMAND_CHARS`` characters."""

    status: ParseStatus
    name: str | None
    watch_id: int | None
    text: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def normalise(text: str) -> str:
    """NFKC (full-width "／ｌｉｓｔ" becomes "/list") and surrounding whitespace removed."""
    return unicodedata.normalize("NFKC", text).strip()


def parse_command(text: str | None) -> ParsedCommand:
    """Parse one message text. ``None`` (a non-text message) is ``not_command``."""
    if text is None:
        return ParsedCommand("not_command", None, None, "")
    cleaned = normalise(text)
    shown = cleaned[:MAX_COMMAND_CHARS]
    if len(cleaned) > MAX_COMMAND_CHARS:
        return ParsedCommand("too_long", None, None, shown)
    if not cleaned.startswith("/"):
        return ParsedCommand("not_command", None, None, shown)
    head, *args = cleaned.split()
    name = head[1:].lower()
    suffix = _BOT_SUFFIX.search(name)
    if suffix is not None and suffix.end() == len(name):
        name = name[: suffix.start()]
    if name not in COMMANDS:
        return ParsedCommand("unknown", None, None, shown)
    if name in PLAIN_COMMANDS:
        if args:
            return ParsedCommand("bad_arg", name, None, shown)
        return ParsedCommand("ok", name, None, shown)
    if not args:
        return ParsedCommand("missing_arg", name, None, shown)
    if len(args) > 1 or not _WATCH_ID.fullmatch(args[0]):
        return ParsedCommand("bad_arg", name, None, shown)
    return ParsedCommand("ok", name, int(args[0]), shown)
