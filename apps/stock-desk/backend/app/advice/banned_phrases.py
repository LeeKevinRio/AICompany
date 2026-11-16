"""The one definition of the banned phrase list (compliance red line; ADR-0030 supp. 3 point 3).

A leaf module: it imports nothing, so a module that needs the phrases (the
advice rule loader, ``app.forecast.definitions``) can take them without
reaching anything else. ``app.advice.loader`` re-exports this very tuple as
``loader.BANNED_PHRASES`` (ADR-0004, ADR-0022, ADR-0025 name it there); the
values and their order are those of the list it replaces.
"""

#: Wording that may never appear in a rule's text (compliance red line).
BANNED_PHRASES: tuple[str, ...] = (
    "保證",
    "必漲",
    "必賺",
    "必跌",
    "穩賺",
    "穩賠",
    "一定會",
    "包賺",
    "零風險",
    "無風險",
)
