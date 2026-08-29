"""Running independent agent work at the same time.

Two loops dominate the pipeline's wall clock — one crew run per concept, one
render per variant — and both were sequential. Measured against real runs on
2026-08-27: generate took 2096s for three concepts, render 913s for eight
variants. Almost none of that is computation. It is a thread parked on a socket
waiting for a vendor, and nothing in either loop reads what the iteration before
it produced, so the waiting was pure loss.

Threads rather than asyncio because the whole call chain below here — the
OpenAI SDK, Chroma, Pillow, ffmpeg — is synchronous. Making it await-able would
mean rewriting every agent to buy the same overlap a pool buys today.

Two properties the callers depend on, and the tests hold to:

*Order.* Results come back in the order the jobs were submitted, never the
order they finished. Variants are written and displayed in this order, so a
fast concept overtaking a slow one must not quietly reshuffle a campaign.

*A failure keeps what succeeded.* The caller has a half-finished run to persist
and a history row to write, so the exception is handed back rather than raised.
Work that had not started yet is abandoned, which is what the sequential loops
did by stopping at the first error — pressing on would spend vendor calls on a
pass already known to be broken.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TypeVar

J = TypeVar("J")
R = TypeVar("R")


def in_parallel(
    jobs: Sequence[J], work: Callable[[J], R], *, lanes: int
) -> tuple[list[tuple[int, R]], Exception | None]:
    """Run `work` over `jobs`, at most `lanes` at a time.

    Returns `(index, result)` for every job that succeeded — ordered by the
    job's position in `jobs`, not by when it finished — and the first exception
    by that same position, or `None`.
    """
    if not jobs:
        return [], None

    # Clamped rather than trusted: `lanes` comes from a setting, and a zero
    # there should slow the pipeline down, never render nothing at all.
    width = max(1, min(lanes, len(jobs)))

    with ThreadPoolExecutor(max_workers=width) as pool:
        futures: list[Future] = [pool.submit(work, job) for job in jobs]

        done: list[tuple[int, R]] = []
        failure: Exception | None = None
        for index, future in enumerate(futures):
            # Asked before `.result()`, which would raise `CancelledError` for
            # an abandoned job. That happens to be an `Exception` today and was
            # a `BaseException` in earlier Pythons, so the abandoned jobs are
            # recognised by asking rather than by catching.
            if future.cancelled():
                continue
            try:
                done.append((index, future.result()))
            except Exception as error:  # handed back, not raised — see above
                if failure is None:
                    failure = error
                    # Nothing already running is interrupted; a vendor call in
                    # flight has been paid for either way and its result is
                    # still worth keeping.
                    for pending in futures[index + 1 :]:
                        pending.cancel()
        return done, failure
