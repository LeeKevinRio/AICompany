"""Tunable parameters for intraday quotes (ADR-0014 "P" table), in one place.

Every value below is a **pre-measurement default**: the real MIS behaviour
(field presence, latency, rate limits) has not been observed yet, because the
build environment has no route to ``mis.twse.com.tw``. The CEO runs
``scripts/verify_intraday_quotes.py`` on 2026-10-05; the data-engineer then
back-fills these constants from the report and revises the ADR table.

Rules that keep this module honest:

* One module, plain constants, **no environment variables** (a deploy-time knob
  would let the values drift away from the verified report).
* Each constant says which P-number it is and that it is pending field
  verification. A change must cite the measurement that justifies it.
* Only the parameters consumed by ``quote_quality`` and ``intraday_session``
  exist so far (P-3, P-4, P-5, P-6, P-7, P-12, P-13). The remaining ones (P-1,
  P-2, P-8, P-9, P-10, P-11, P-15, P-16) are added to this same module together
  with the service layer that consumes them, so no constant ships unused.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal
from typing import Final

from app.data.interface import QuoteKey

#: Exchange-local session start (09:00 Asia/Taipei). Fixed by the exchange's
#: trading hours, not a measured parameter; it is listed here so the whole
#: intraday window is defined in one place.
INTRADAY_OPEN: Final = time(9, 0)

#: P-3: the feed counts as stalled when the sentinel channel's last trade is
#: older than this. Pending 10/05 field verification.
FEED_LAG_THRESHOLD: Final = timedelta(seconds=120)

#: P-4: tolerated gap between our retrieval time and the source's own
#: ``queryTime``. Pending 10/05 field verification.
CLOCK_SKEW_TOLERANCE: Final = timedelta(seconds=60)

#: P-5: how far a quote's last-trade time may sit ahead of the source's own
#: server time before it is treated as corrupt. Pending 10/05 field verification.
FUTURE_QUOTE_TOLERANCE: Final = timedelta(seconds=5)

#: P-6: end of the intraday window (exclusive), 13:25 Asia/Taipei. It stops
#: before the 13:30 close because the closing auction may emit simulated
#: ("trial match") prices. Pending 10/05 field verification (move to 13:30 only
#: if ``z`` is shown to change on real trades only).
INTRADAY_END: Final = time(13, 25)

#: P-7: whether the window is extended past ``INTRADAY_END`` (up to the daily
#: bar publish cutoff) using the last MIS trade price. Disabled by CEO ruling:
#: between 13:30 and the official close publication the product shows the
#: previous trading day's close. Pending 10/05 field verification.
AFTER_CLOSE_EXTENSION_ENABLED: Final = False

#: P-12: when the source gives no limit-up/limit-down fields, a price further
#: than this fraction from the previous close is rejected as implausible
#: (0.5 = 50%). Pending 10/05 field verification (replaced by the real limit
#: fields if they exist).
IMPLAUSIBLE_MOVE_BAND: Final = Decimal("0.5")

#: P-13: sentinel channel used to judge whether the feed itself is alive
#: (TSMC trades every few seconds in session). Pending 10/05 field verification
#: (an index channel replaces it if one proves usable).
SENTINEL_KEY: Final = QuoteKey(symbol="2330", board="tse")
