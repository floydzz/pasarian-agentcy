"""One clock, and it is UTC.

Timestamps are written naive and stored in MySQL `DATETIME` columns, which
carry no zone. That is only safe if every writer agrees which zone the naive
value is in, so they all come from here. The container runs UTC and a developer's
laptop does not, and `datetime.now()` would quietly mean something different in
each — which shows up as a row written seconds ago being displayed as eight
hours old.

The other half of the contract is in `schemas.py`, which stamps these values as
UTC on the way out so a browser converts them to local time instead of reading
them as local time.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Now, in UTC, with the tzinfo dropped for a naive DATETIME column."""
    return datetime.now(UTC).replace(tzinfo=None)
