"""Generation routes — running the crew over a campaign's approved concepts.

Only approved concepts are generated. That is the whole return on the approval
gate: a rejected concept costs nothing downstream, and the crew never spends a
model call on an idea a human already turned down.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import CrewError
from app.agents.crew import CrewResult, GenerationCrew
from app.agents.events import AgentEvent
from app.agents.parallel import in_parallel
from app.api.deps import get_campaign_or_404, get_crew
from app.api.conversions import to_domain_concept
from app.api.history import GENERATE, RunLog
from app.api.streaming import event_stream
from app.api.schemas import AutoModeUpdate, CampaignRead, GenerationRead, VariantRead
from app.config import get_settings
from app.db import get_db
from app.domain import CampaignStatus, ConceptStatus
from app.models import Campaign, Concept, Variant

router = APIRouter(prefix="/api", tags=["generation"])


@router.patch("/campaigns/{campaign_id}/auto-mode", response_model=CampaignRead)
def set_auto_mode(
    campaign_id: int, payload: AutoModeUpdate, db: Session = Depends(get_db)
) -> Campaign:
    campaign = get_campaign_or_404(db, campaign_id)

    if payload.auto_approve_plan is not None:
        campaign.auto_approve_plan = payload.auto_approve_plan
    if payload.auto_approve_assets is not None:
        campaign.auto_approve_assets = payload.auto_approve_assets

    db.commit()
    return campaign


@router.get("/campaigns/{campaign_id}/variants", response_model=list[VariantRead])
def list_variants(campaign_id: int, db: Session = Depends(get_db)) -> list[Variant]:
    get_campaign_or_404(db, campaign_id)
    return list(
        db.scalars(
            select(Variant)
            .join(Concept, Variant.concept_id == Concept.id)
            .where(Concept.campaign_id == campaign_id)
            .order_by(Variant.concept_id, Variant.id)
        )
    )


@router.post("/campaigns/{campaign_id}/generate", response_model=GenerationRead)
def generate(
    campaign_id: int,
    db: Session = Depends(get_db),
    crew: GenerationCrew = Depends(get_crew),
) -> GenerationRead:
    campaign = get_campaign_or_404(db, campaign_id)
    if campaign.status is not CampaignStatus.GENERATING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is {campaign.status}, not {CampaignStatus.GENERATING} — "
            "the plan has to be approved before the crew runs",
        )

    approved = [c for c in campaign.concepts if c.status is ConceptStatus.APPROVED]
    if not approved:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "no approved concepts left to generate"
        )

    todo, skipped = _pending(campaign)
    record = RunLog(campaign, GENERATE)

    produced, failure = _run_crew(crew, todo, sink=record.capture)

    # Persisted before the failure is raised either way: concepts that finished
    # are work the campaign owns, and the next run resumes from what is here.
    written = _persist(db, produced)
    db.commit()

    if failure is not None:
        record.failed(db, str(failure), **_counts(written, produced))
        if not isinstance(failure, CrewError):
            raise failure
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(failure)) from failure

    _record_crew(db, record, written, produced)
    return _summarise(written, generated=len(produced), skipped=skipped)


@router.post("/campaigns/{campaign_id}/generate/stream")
def generate_streaming(
    campaign_id: int,
    db: Session = Depends(get_db),
    crew: GenerationCrew = Depends(get_crew),
) -> StreamingResponse:
    """The same run as `/generate`, narrated to the console as it happens."""
    campaign = get_campaign_or_404(db, campaign_id)
    if campaign.status is not CampaignStatus.GENERATING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is {campaign.status}, not {CampaignStatus.GENERATING} — "
            "the plan has to be approved before the crew runs",
        )

    # Snapshot the work before the worker starts: the thread runs agents only
    # and never touches this session.
    todo, skipped = _pending(campaign)
    if not todo and skipped == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "no approved concepts left to generate"
        )

    record = RunLog(campaign, GENERATE)

    def work(sink) -> list[tuple[int, CrewResult]]:
        report = record.tee(sink)
        produced, failure = _run_crew(crew, todo, sink=report)
        if failure is not None:
            # Said on the stream rather than raised: whatever finished is kept
            # and the next run picks up the concepts that did not.
            report(AgentEvent("system", "failed", str(failure)))
        return produced

    def finish(produced: list[tuple[int, CrewResult]]) -> dict:
        written = _persist(db, produced)
        db.commit()
        _record_crew(db, record, written, produced)
        return _summarise(
            written, generated=len(produced), skipped=skipped
        ).model_dump()

    def recover() -> None:
        record.failed(db, _last_failure(record) or "The crew run failed.")

    return StreamingResponse(
        event_stream(work, finish, on_error=recover),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _run_crew(
    crew: GenerationCrew,
    todo: list[tuple[int, object]],
    *,
    sink,
) -> tuple[list[tuple[int, CrewResult]], Exception | None]:
    """Every approved concept, generated at the same time.

    The concepts are independent by construction — each is retrieved for,
    written, planned and reviewed against the brand on its own, and no node in
    the crew graph reads another concept's output. Running them one after
    another was three sequential waits on the same vendor for no more work: a
    measured 2096s for three concepts on 2026-08-27.

    Events from the concepts interleave on the console as a result. That is the
    truth of what is happening — three copywriters really are working at once —
    and the console counts work in flight per agent rather than tracking the
    last event it saw, so a lane stays lit until the last of them is done.
    """
    done, failure = in_parallel(
        todo,
        lambda job: crew.run(job[1], sink=sink),
        lanes=get_settings().crew_lanes,
    )
    return [(todo[index][0], result) for index, result in done], failure


def _pending(campaign: Campaign) -> tuple[list[tuple[int, object]], int]:
    """Approved concepts still needing variants, plus how many were already done.

    A concept that already has variants is left alone, so a retry after a
    partial failure resumes instead of writing a second set beside the first.
    """
    todo: list[tuple[int, object]] = []
    skipped = 0
    for concept in campaign.concepts:
        if concept.status is not ConceptStatus.APPROVED:
            continue
        if concept.variants:
            skipped += 1
            continue
        todo.append((concept.id, to_domain_concept(concept, campaign)))
    return todo, skipped


def _persist(db: Session, produced: list[tuple[int, CrewResult]]) -> list[Variant]:
    rows = [
        Variant(
            concept_id=concept_id,
            hook_type=variant.hook_type,
            headline=variant.headline,
            body=variant.body,
            cta=variant.cta,
            visual_brief=variant.visual_brief.model_dump(),
            director_status=variant.director_status,
            director_notes=variant.director_notes,
            revision_count=result.revisions,
        )
        for concept_id, result in produced
        for variant in result.variants
    ]
    db.add_all(rows)
    db.flush()
    return rows


def _summarise(written: list[Variant], *, generated: int, skipped: int) -> GenerationRead:
    return GenerationRead(
        concepts_generated=generated,
        concepts_skipped=skipped,
        variants=[VariantRead.model_validate(row) for row in written],
    )


def _counts(
    written: list[Variant], produced: list[tuple[int, CrewResult]]
) -> dict[str, int]:
    return {
        "concepts": len(produced),
        "variants": len(written),
        "flagged": sum(1 for row in written if row.director_status == "flagged"),
        # The worst case across the concepts, not the total: "two revisions"
        # should mean the same thing in history as it does on the stage.
        "revisions": max((result.revisions for _, result in produced), default=0),
    }


def _record_crew(
    db: Session,
    record: RunLog,
    written: list[Variant],
    produced: list[tuple[int, CrewResult]],
) -> None:
    counts = _counts(written, produced)
    flagged = counts["flagged"]
    summary = (
        f"{counts['variants']} variants across {counts['concepts']} "
        f"{'concept' if counts['concepts'] == 1 else 'concepts'}"
    )
    # Flagged work is the thing a person scanning history is looking for, so it
    # is said in the summary rather than left to a column.
    summary += f" — {flagged} flagged for you" if flagged else " — all passed"
    record.succeeded(db, summary, **counts)


def _last_failure(record: RunLog) -> str | None:
    for event in reversed(record.events):
        if event.get("phase") == "failed":
            return str(event.get("detail") or "")
    return None




