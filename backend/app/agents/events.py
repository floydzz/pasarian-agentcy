"""What the agents report about themselves while they work.

The console is a monitor, not a progress bar: it shows which agent holds the
work right now, what it just decided, and why the graph moved where it did. That
only works if the agents say so as it happens, so every node emits `started`
before it calls the model and `finished` when it has something to hand on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Agent = Literal[
    "planner",
    "copywriter",
    "visual_planner",
    "director",
    # The studio's own two — see `app.agents.studio`.
    "renderer",
    "vision_qa",
    "system",
]
Phase = Literal["started", "finished", "failed"]


@dataclass(frozen=True)
class AgentEvent:
    agent: Agent
    phase: Phase
    #: One line, written for a human watching the log scroll past.
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "phase": self.phase,
            "detail": self.detail,
            "data": self.data,
        }


#: Where an agent posts its events. Agents take this as an optional argument so
#: they stay callable — and testable — with no console attached at all.
EventSink = Callable[[AgentEvent], None]


def emit(sink: EventSink | None, event: AgentEvent) -> None:
    if sink is not None:
        sink(event)
