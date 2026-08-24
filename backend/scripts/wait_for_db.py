"""Block until MySQL answers, or give up loudly.

    python scripts/wait_for_db.py [seconds]

Compose's `depends_on: service_healthy` already waits for the container, but a
healthy mysqld and a mysqld that will accept *this* user on *this* database are
not the same moment. This closes that gap so the first migration does not race
the server's own bootstrap.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402

RETRY_SECONDS = 1.0


def wait(timeout: float) -> int:
    target = engine.url.render_as_string(hide_password=True)
    deadline = time.monotonic() + timeout
    last: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print(f"database ready — {target}")
            return 0
        except Exception as error:  # the driver raises a different type per cause
            last = error
            time.sleep(RETRY_SECONDS)

    print(f"database never answered in {timeout:.0f}s — {target}", file=sys.stderr)
    print(f"last error: {last}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(wait(float(sys.argv[1]) if len(sys.argv) > 1 else 60.0))
