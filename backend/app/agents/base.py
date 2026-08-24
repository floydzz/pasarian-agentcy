"""Shared plumbing for the agents.

Every agent reaches the model through the same structured-output protocol and
renders retrieved chunks the same way, so a citation looks identical no matter
which agent quoted it.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.rag.store import Retrieved


class Provider(Protocol):
    """Whatever LLM the campaign is running on — see `app.llm`."""

    def structured(self, *, system: str, prompt: str, schema: type[BaseModel]): ...


class CrewError(RuntimeError):
    """A generation agent returned something the pipeline cannot use."""


def with_house_note(system: str, note: str | None) -> str:
    """Append a human's standing instruction to an agent's system prompt.

    Appended rather than substituted, and appended *last*, so a house note can
    add direction — a tone, a market, a thing to always mention — without being
    able to delete a grounding rule the prompt above it already set. It is
    labelled as coming from a person so the model can weigh it as direction
    rather than as ground truth about the brand.
    """
    note = (note or "").strip()
    if not note:
        return system
    return (
        f"{system}\n\n"
        "STANDING INSTRUCTION from the person running this account. Follow it "
        "wherever it does not conflict with the rules above; those rules win.\n"
        f"{note}"
    )


def render_context(context: list[Retrieved], *, empty: str) -> str:
    """Chunks as the agents see them — id first, so citing one is unambiguous."""
    if not context:
        return empty
    return "\n\n".join(
        f"[{hit.chunk_id}] ({hit.source} § {hit.heading})\n{hit.text}"
        for hit in context
    )
