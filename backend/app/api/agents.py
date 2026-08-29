"""Reading and changing how the strategist and crew are tuned.

The shape of this API is taken from `app.agents.tuning` rather than restated
here, so an agent that gains a knob gains it on the settings screen without
anything in this file changing. What this file owns is persistence and the
clamping of submitted values.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import tuning
from app.api.schemas import AgentRead, AgentUpdate, KnobRead
from app.db import get_db
from app.models import AgentSetting

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents", response_model=list[AgentRead])
def list_agents(db: Session = Depends(get_db)) -> list[AgentRead]:
    """The strategist first, then the crew in pipeline order."""
    saved = {row.agent: row for row in db.scalars(select(AgentSetting))}
    return [_read(profile, saved.get(profile.agent)) for profile in tuning.PROFILES]


@router.patch("/agents/{agent}", response_model=AgentRead)
def update_agent(
    agent: str, payload: AgentUpdate, db: Session = Depends(get_db)
) -> AgentRead:
    profile = tuning.BY_AGENT.get(agent)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no agent {agent!r}")

    row = db.scalar(select(AgentSetting).where(AgentSetting.agent == agent))
    if row is None:
        row = AgentSetting(agent=agent)
        db.add(row)

    if payload.standing_note is not None:
        # An empty note is a cleared note, not an empty instruction appended to
        # the prompt — the difference matters to what the model is handed.
        note = payload.standing_note.strip()
        row.standing_note = note or None

    fields = {knob.field for knob in profile.knobs}
    for field in (
        "concept_count",
        "company_k",
        "trend_k",
        "max_revisions",
        "max_redos",
        "context_turns",
    ):
        value = getattr(payload, field)
        if value is None:
            continue
        if field not in fields:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{profile.label} has no {field!r} setting",
            )
        setattr(row, field, tuning.clamp(agent, field, value))

    db.commit()
    return _read(profile, row)


@router.post("/agents/{agent}/reset", response_model=AgentRead)
def reset_agent(agent: str, db: Session = Depends(get_db)) -> AgentRead:
    """Back to what the agent shipped with, note included."""
    profile = tuning.BY_AGENT.get(agent)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no agent {agent!r}")

    row = db.scalar(select(AgentSetting).where(AgentSetting.agent == agent))
    if row is not None:
        db.delete(row)
        db.commit()
    return _read(profile, None)


def _read(profile: tuning.AgentProfile, row: AgentSetting | None) -> AgentRead:
    knobs = [
        KnobRead(
            field=knob.field,
            label=knob.label,
            help=knob.help,
            minimum=knob.minimum,
            maximum=knob.maximum,
            default=knob.default,
            value=_value(knob, row),
        )
        for knob in profile.knobs
    ]
    note = row.standing_note if row else None
    return AgentRead(
        agent=profile.agent,
        label=profile.label,
        role=profile.role,
        boundary=profile.boundary,
        note_placeholder=profile.note_placeholder,
        standing_note=note,
        knobs=knobs,
        is_default=not note and all(knob.value == knob.default for knob in knobs),
    )


def _value(knob: tuning.Knob, row: AgentSetting | None) -> int:
    saved = getattr(row, knob.field, None)
    if saved is None:
        return knob.default
    return max(knob.minimum, min(knob.maximum, saved))
