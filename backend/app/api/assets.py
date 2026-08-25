"""Render routes and the asset review gate.

The studio runs on its own route with its own run kind because a render is a
vendor round trip per variant — minutes, not the seconds the crew returns in.
Everything else here is the second half of the gate the plan approval already
established: a human looks at finished creatives and says which ones ship.

Every variant is rendered, including director-flagged ones. The gate is where a
human filters; quietly dropping a flagged variant would hide a decision that is
theirs to make.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.events import AgentEvent
from app.agents.studio import RenderedAsset, Studio, VariantSpec
from app.api.deps import get_campaign_or_404, get_studio
from app.api.history import RENDER, RunLog
from app.api.schemas import AssetRead, CampaignRead, RenderRead
from app.api.streaming import event_stream
from app.config import get_settings
from app.db import get_db
from app.domain import CampaignStatus, VisualBrief
from app.media.base import RenderError
from app.models import Asset, Campaign, Concept, Variant

router = APIRouter(prefix="/api", tags=["assets"])


# -- rendering -------------------------------------------------------------


@router.post("/campaigns/{campaign_id}/render", response_model=RenderRead)
def render(
    campaign_id: int,
    db: Session = Depends(get_db),
    studio: Studio = Depends(get_studio),
) -> RenderRead:
    campaign = _renderable(db, campaign_id)
    todo, skipped = _pending(db, campaign)
    if not todo and skipped == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "no variants to render")

    record = RunLog(campaign, RENDER)
    produced: list[RenderedAsset] = []
    try:
        for spec in todo:
            produced.append(studio.run(spec, sink=record.capture))
    except RenderError as error:
        # Keep whatever earlier variants produced — the run is resumable.
        written = _persist(db, produced)
        _advance(db, campaign, written)
        db.commit()
        record.failed(db, str(error), **_counts(written, produced))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    written = _persist(db, produced)
    _advance(db, campaign, written)
    db.commit()
    _record_render(db, record, written, produced)
    return _summarise(written, skipped=skipped)


@router.post("/campaigns/{campaign_id}/render/stream")
def render_streaming(
    campaign_id: int,
    db: Session = Depends(get_db),
    studio: Studio = Depends(get_studio),
) -> StreamingResponse:
    """The same run as `/render`, narrated to the console as it happens."""
    campaign = _renderable(db, campaign_id)

    # Snapshot the work before the worker starts: the thread runs the studio
    # only and never touches this session.
    todo, skipped = _pending(db, campaign)
    if not todo and skipped == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "no variants to render")

    record = RunLog(campaign, RENDER)

    def work(sink) -> list[RenderedAsset]:
        report = record.tee(sink)
        produced: list[RenderedAsset] = []
        for spec in todo:
            try:
                produced.append(studio.run(spec, sink=report))
            except RenderError as error:
                # Stop here rather than pressing on: whatever finished is kept
                # and the next run picks up the variants that did not.
                report(AgentEvent("system", "failed", str(error)))
                break
        return produced

    def finish(produced: list[RenderedAsset]) -> dict:
        written = _persist(db, produced)
        _advance(db, campaign, written)
        db.commit()
        _record_render(db, record, written, produced)
        return _summarise(written, skipped=skipped).model_dump()

    def recover() -> None:
        record.failed(db, _last_failure(record) or "The render run failed.")

    return StreamingResponse(
        event_stream(work, finish, on_error=recover),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# -- the review gate -------------------------------------------------------


@router.get("/campaigns/{campaign_id}/assets", response_model=list[AssetRead])
def list_assets(campaign_id: int, db: Session = Depends(get_db)) -> list[Asset]:
    get_campaign_or_404(db, campaign_id)
    return list(
        db.scalars(
            select(Asset)
            .join(Variant, Asset.variant_id == Variant.id)
            .join(Concept, Variant.concept_id == Concept.id)
            .where(Concept.campaign_id == campaign_id)
            .order_by(Asset.variant_id, Asset.id)
        )
    )


@router.post("/assets/{asset_id}/approve", response_model=AssetRead)
def approve_asset(asset_id: int, db: Session = Depends(get_db)) -> Asset:
    return _decide(db, asset_id, "approved")


@router.post("/assets/{asset_id}/reject", response_model=AssetRead)
def reject_asset(asset_id: int, db: Session = Depends(get_db)) -> Asset:
    return _decide(db, asset_id, "rejected")


@router.post("/assets/{asset_id}/redo", response_model=AssetRead)
def redo_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    studio: Studio = Depends(get_studio),
) -> Asset:
    """Re-render one creative in place, at the reviewer's request.

    Updated rather than replaced so anything already pointing at this asset
    keeps pointing at it, and the superseded file is deleted — an orphan on the
    volume is storage nobody will ever reclaim.
    """
    asset = _asset_or_404(db, asset_id)
    variant = db.get(Variant, asset.variant_id)

    try:
        rendered = studio.run(_spec(variant))
    except RenderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    superseded = asset.media_url
    asset.media_url = rendered.media_url
    asset.qa_status = rendered.qa_status
    asset.qa_notes = rendered.qa_notes
    # A fresh creative has not been looked at yet, whatever was decided before.
    asset.review_status = "pending"
    db.commit()

    _forget(studio, superseded)
    return asset


@router.post("/campaigns/{campaign_id}/assets/approve", response_model=CampaignRead)
def close_asset_gate(campaign_id: int, db: Session = Depends(get_db)) -> Campaign:
    campaign = get_campaign_or_404(db, campaign_id)
    if campaign.status is not CampaignStatus.PENDING_ASSET_REVIEW:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is {campaign.status}, not "
            f"{CampaignStatus.PENDING_ASSET_REVIEW} — there is no asset gate open",
        )

    if not any(row.review_status == "approved" for row in list_assets(campaign_id, db)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "at least one approved creative is needed before publishing",
        )

    campaign.status = CampaignStatus.READY_TO_PUBLISH
    db.commit()
    return campaign


# -- helpers ---------------------------------------------------------------


#: Statuses a render may start from. `PENDING_ASSET_REVIEW` is included because
#: a render that failed part way through already advanced the campaign, and
#: picking up the variants it never reached is the whole point of resuming.
RENDERABLE = (CampaignStatus.GENERATING, CampaignStatus.PENDING_ASSET_REVIEW)


def _renderable(db: Session, campaign_id: int) -> Campaign:
    campaign = get_campaign_or_404(db, campaign_id)
    if campaign.status not in RENDERABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is {campaign.status}, not {CampaignStatus.GENERATING} — "
            "the crew has to run before there is anything to render",
        )
    return campaign


def _pending(db: Session, campaign: Campaign) -> tuple[list[VariantSpec], int]:
    """Variants still needing a creative, plus how many are being left alone.

    A variant that already has an asset is skipped, so a retry after a partial
    failure resumes instead of writing a second creative beside the first.
    """
    cap = get_settings().max_renders_per_run
    todo: list[VariantSpec] = []
    skipped = 0
    for variant in _variants_of(db, campaign.id):
        if variant.assets:
            skipped += 1
            continue
        if len(todo) >= cap:
            skipped += 1
            continue
        todo.append(_spec(variant))
    return todo, skipped


def _variants_of(db: Session, campaign_id: int) -> list[Variant]:
    return list(
        db.scalars(
            select(Variant)
            .join(Concept, Variant.concept_id == Concept.id)
            .where(Concept.campaign_id == campaign_id)
            .order_by(Variant.concept_id, Variant.id)
        )
    )


def _spec(variant: Variant) -> VariantSpec:
    return VariantSpec(
        variant_id=variant.id,
        headline=variant.headline,
        cta=variant.cta,
        brief=VisualBrief(**variant.visual_brief),
    )


def _persist(db: Session, produced: list[RenderedAsset]) -> list[Asset]:
    rows = [
        Asset(
            variant_id=asset.variant_id,
            media_url=asset.media_url,
            qa_status=asset.qa_status,
            qa_notes=asset.qa_notes,
            review_status="pending",
        )
        for asset in produced
    ]
    db.add_all(rows)
    db.flush()
    return rows


def _advance(db: Session, campaign: Campaign, written: list[Asset]) -> None:
    """Move the campaign on, honouring auto-mode the way the plan gate does.

    Auto-approved assets still carry an explicit approved status, so nothing
    downstream has to know whether a human was in the loop.
    """
    if not written:
        return

    campaign.status = CampaignStatus.PENDING_ASSET_REVIEW
    if not campaign.auto_approve_assets:
        return

    for row in written:
        if row.qa_status == "passed":
            row.review_status = "approved"
    if any(row.review_status == "approved" for row in written):
        campaign.status = CampaignStatus.READY_TO_PUBLISH


def _summarise(written: list[Asset], *, skipped: int) -> RenderRead:
    return RenderRead(
        variants_rendered=len(written),
        variants_skipped=skipped,
        assets=[AssetRead.model_validate(row) for row in written],
    )


def _decide(db: Session, asset_id: int, decision: str) -> Asset:
    asset = _asset_or_404(db, asset_id)
    asset.review_status = decision
    db.commit()
    return asset


def _asset_or_404(db: Session, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no asset {asset_id}")
    return asset


def _forget(studio: Studio, media_url: str) -> None:
    """Delete a superseded creative, through the same storage that wrote it.

    Best effort — a leftover file on the volume is not worth failing a redo the
    reviewer has already been handed.
    """
    try:
        studio.storage.path_for(media_url).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


def _counts(written: list[Asset], produced: list[RenderedAsset]) -> dict[str, int]:
    return {
        # `Run` has no assets column and needs none: for a render pass,
        # variants means creatives made, flagged means QA-flagged, and
        # revisions means redos.
        "variants": len(written),
        "flagged": sum(1 for row in written if row.qa_status == "flagged"),
        "revisions": max((asset.redos for asset in produced), default=0),
    }


def _record_render(
    db: Session, record: RunLog, written: list[Asset], produced: list[RenderedAsset]
) -> None:
    counts = _counts(written, produced)
    flagged = counts["flagged"]
    summary = (
        f"{counts['variants']} "
        f"{'creative' if counts['variants'] == 1 else 'creatives'} rendered"
    )
    summary += f" — {flagged} flagged for you" if flagged else " — all passed QA"
    record.succeeded(db, summary, **counts)


def _last_failure(record: RunLog) -> str | None:
    for event in reversed(record.events):
        if event.get("phase") == "failed":
            return str(event.get("detail") or "")
    return None
