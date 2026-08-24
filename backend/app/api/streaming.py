"""Streaming a run to the console as newline-delimited JSON.

The work happens on a worker thread and posts events to a queue that this
generator drains. A thread rather than LangGraph's own `.stream()` because the
console needs to show an agent as busy *while* it is busy: `.stream()` only
yields once a node has already returned, which would leave the screen idle for
the whole length of a model call — exactly the stretch a monitor exists to show.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

from app.agents.events import AgentEvent

T = TypeVar("T")

#: Pushed onto the queue by the worker to say it has stopped posting events.
_DONE = object()


def ndjson(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str) + "\n"


def event_stream(
    work: Callable[[Callable[[AgentEvent], None]], T],
    finish: Callable[[T], dict[str, Any]],
    *,
    on_error: Callable[[], None] | None = None,
) -> Iterator[str]:
    """Run `work`, streaming its events, then stream what `finish` makes of it.

    `finish` and `on_error` run on this thread rather than the worker's, so they
    are the safe place to touch the database — the worker only ever calls
    agents. `on_error` gets the chance to put a half-advanced record back
    somewhere the human can act on it.
    """
    events: queue.Queue = queue.Queue()
    outcome: dict[str, Any] = {}

    def worker() -> None:
        try:
            outcome["result"] = work(events.put)
        except Exception as error:  # surfaced to the client below
            outcome["error"] = error
        finally:
            events.put(_DONE)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    seq = 0
    while True:
        item = events.get()
        if item is _DONE:
            break
        seq += 1
        yield ndjson({"kind": "event", "seq": seq, **item.as_dict()})

    thread.join()

    if "error" in outcome:
        error = outcome["error"]
        if on_error is not None:
            on_error()
        yield ndjson({"kind": "error", "detail": str(error) or type(error).__name__})
        return

    try:
        yield ndjson({"kind": "result", **finish(outcome["result"])})
    except Exception as error:
        if on_error is not None:
            on_error()
        yield ndjson({"kind": "error", "detail": str(error) or type(error).__name__})
