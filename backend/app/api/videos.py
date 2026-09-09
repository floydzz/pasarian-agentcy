"""Reusable marketing-video API and its human review gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.events import AgentEvent
from app.agents.video_studio import (
    MarketingVideoSpec,
    RenderedMarketingVideo,
    VideoStudio,
)
from app.api.deps import get_campaign_or_404, get_video_studio
from app.api.product_references import primary_product_image
from app.api.schemas import MarketingVideoCreate, MarketingVideoRead
from app.api.streaming import event_stream
from app.config import get_settings
from app.db import get_db
from app.media.base import RenderError
from app.models import MarketingVideo, ProductReference
from app.video import MarketingVideoScene, video_brief_for

router = APIRouter(prefix="/api", tags=["marketing videos"])


@router.get("/videos", response_model=list[MarketingVideoRead])
def list_videos(
    campaign_id: int | None = None, db: Session = Depends(get_db)
) -> list[MarketingVideo]:
    """Every video, or only one campaign's.

    The filter is a query parameter rather than a second route because "all
    the video work" is a real question the studio picker asks, and a route
    that could only answer it per campaign would make that question expensive.
    """
    query = select(MarketingVideo).order_by(MarketingVideo.id.desc())
    if campaign_id is not None:
        query = query.where(MarketingVideo.campaign_id == campaign_id)
    return list(db.scalars(query))


@router.get("/campaigns/{campaign_id}/videos", response_model=list[MarketingVideoRead])
def list_campaign_videos(
    campaign_id: int, db: Session = Depends(get_db)
) -> list[MarketingVideo]:
    get_campaign_or_404(db, campaign_id)
    return list(
        db.scalars(
            select(MarketingVideo)
            .where(MarketingVideo.campaign_id == campaign_id)
            .order_by(MarketingVideo.id.desc())
        )
    )


@router.get("/campaigns/{campaign_id}/video-brief", response_model=MarketingVideoCreate)
def campaign_video_brief(campaign_id: int, db: Session = Depends(get_db)) -> dict:
    """A first draft of this campaign's video, for the studio to open with."""
    brief = video_brief_for(db, get_campaign_or_404(db, campaign_id))
    reference = db.scalar(
        select(ProductReference)
        .where(ProductReference.campaign_id == campaign_id)
        .where(ProductReference.is_primary.is_(True))
        .limit(1)
    )
    if reference:
        brief["product_reference_id"] = reference.id
    return brief


@router.post("/campaigns/{campaign_id}/videos/render", response_model=MarketingVideoRead)
def render_campaign_video(
    campaign_id: int,
    payload: MarketingVideoCreate,
    db: Session = Depends(get_db),
    studio: VideoStudio = Depends(get_video_studio),
) -> MarketingVideo:
    get_campaign_or_404(db, campaign_id)
    reference_url, product_image = _campaign_product(
        db, campaign_id, payload.product_reference_id, studio
    )
    reusable = _reusable_video(db, studio, exclude_campaign_id=campaign_id)
    rendered = _render(
        studio, payload, product_image=product_image, reusable=reusable
    )
    row = _row(
        payload, rendered, campaign_id=campaign_id, product_reference_url=reference_url
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/campaigns/{campaign_id}/videos/render/stream")
def render_campaign_video_stream(
    campaign_id: int,
    payload: MarketingVideoCreate,
    db: Session = Depends(get_db),
    studio: VideoStudio = Depends(get_video_studio),
) -> StreamingResponse:
    get_campaign_or_404(db, campaign_id)
    reference_url, product_image = _campaign_product(
        db, campaign_id, payload.product_reference_id, studio
    )
    reusable = _reusable_video(db, studio, exclude_campaign_id=campaign_id)

    def work(sink) -> RenderedMarketingVideo:
        return _render(
            studio,
            payload,
            sink=sink,
            product_image=product_image,
            reusable=reusable,
        )

    def finish(rendered: RenderedMarketingVideo) -> dict:
        row = _row(
            payload,
            rendered,
            campaign_id=campaign_id,
            product_reference_url=reference_url,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return MarketingVideoRead.model_validate(row).model_dump(mode="json")

    return StreamingResponse(
        event_stream(work, finish),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/videos/render", response_model=MarketingVideoRead)
def render_video(
    payload: MarketingVideoCreate,
    db: Session = Depends(get_db),
    studio: VideoStudio = Depends(get_video_studio),
) -> MarketingVideo:
    if payload.product_reference_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "select product images from a campaign video studio")
    rendered = _render(studio, payload)
    row = _row(payload, rendered)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/videos/render/stream")
def render_video_stream(
    payload: MarketingVideoCreate,
    db: Session = Depends(get_db),
    studio: VideoStudio = Depends(get_video_studio),
) -> StreamingResponse:
    """Render the exact same video, narrating each agent to the console."""

    if payload.product_reference_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "select product images from a campaign video studio")

    def work(sink) -> RenderedMarketingVideo:
        return _render(studio, payload, sink=sink)

    def finish(rendered: RenderedMarketingVideo) -> dict:
        row = _row(payload, rendered)
        db.add(row)
        db.commit()
        db.refresh(row)
        return MarketingVideoRead.model_validate(row).model_dump(mode="json")

    return StreamingResponse(
        event_stream(work, finish),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/videos/{video_id}/redo", response_model=MarketingVideoRead)
def redo_video(
    video_id: int,
    db: Session = Depends(get_db),
    studio: VideoStudio = Depends(get_video_studio),
) -> MarketingVideo:
    row = _video_or_404(db, video_id)
    product_image = _stored_product_image(studio, row.product_reference_url)
    rendered = _render(studio, _payload_from(row), product_image=product_image)
    superseded = (row.media_url, row.poster_url)
    _apply(row, rendered)
    row.review_status = "pending"
    db.commit()
    _forget(studio, *superseded)
    return row


@router.post("/videos/{video_id}/approve", response_model=MarketingVideoRead)
def approve_video(video_id: int, db: Session = Depends(get_db)) -> MarketingVideo:
    return _decide(db, video_id, "approved")


@router.post("/videos/{video_id}/reject", response_model=MarketingVideoRead)
def reject_video(video_id: int, db: Session = Depends(get_db)) -> MarketingVideo:
    return _decide(db, video_id, "rejected")


def _render(
    studio: VideoStudio,
    payload: MarketingVideoCreate,
    *,
    sink=None,
    product_image: bytes | None = None,
    reusable: dict | None = None,
) -> RenderedMarketingVideo:
    try:
        if reusable is not None:
            return _reuse_video(studio, payload, reusable, sink=sink)
        return studio.run(
            MarketingVideoSpec(
                name=payload.name,
                profile=payload.profile,
                brand_name=payload.brand_name,
                product_name=payload.product_name,
                target_audience=payload.target_audience,
                cta=payload.cta,
                storyboard=[
                    MarketingVideoScene(**scene.model_dump())
                    for scene in payload.storyboard
                ],
                use_broll=payload.use_broll,
                product_image=product_image,
            ),
            sink=sink,
        )
    except RenderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error


def _reusable_video(
    db: Session,
    studio: VideoStudio,
    *,
    exclude_campaign_id: int | None = None,
) -> dict | None:
    """Read one finished local video before the streaming worker starts."""
    if not get_settings().scripted_demo:
        return None
    query = select(MarketingVideo).order_by(
        (MarketingVideo.review_status == "approved").desc(), MarketingVideo.id.desc()
    )
    if exclude_campaign_id is not None:
        query = query.where(
            or_(
                MarketingVideo.campaign_id.is_(None),
                MarketingVideo.campaign_id != exclude_campaign_id,
            )
        )
    for row in db.scalars(query):
        try:
            return {
                "video": studio.storage.read(row.media_url),
                "video_suffix": studio.storage.path_for(row.media_url).suffix or ".mp4",
                "poster": studio.storage.read(row.poster_url),
                "poster_suffix": studio.storage.path_for(row.poster_url).suffix or ".png",
                "duration_seconds": row.duration_seconds,
            }
        except (ValueError, OSError):
            continue
    return None


def _reuse_video(
    studio: VideoStudio,
    payload: MarketingVideoCreate,
    source: dict,
    *,
    sink=None,
) -> RenderedMarketingVideo:
    """Copy a saved video while narrating the same visible production graph."""
    events = (
        ("planner", "started", f"Reading the {len(payload.storyboard)}-scene scripted demo brief"),
        ("planner", "finished", "Saved campaign story selected"),
        ("visual_planner", "started", "Matching the storyboard to the local video library"),
        ("visual_planner", "finished", "Existing motion sequence matched to the campaign"),
        ("renderer", "started", "Copying the saved generated video into this campaign"),
    )
    if sink is not None:
        for agent, phase, detail in events:
            sink(AgentEvent(agent, phase, detail, {"source": "local_demo_library"}))
    media_url = studio.storage.save(source["video"], suffix=source["video_suffix"])
    try:
        poster_url = studio.storage.save(source["poster"], suffix=source["poster_suffix"])
    except Exception:
        studio.storage.path_for(media_url).unlink(missing_ok=True)
        raise
    if sink is not None:
        sink(AgentEvent("renderer", "finished", "Campaign-owned MP4 copy is ready", {"source": "local_demo_library"}))
        sink(AgentEvent("vision_qa", "started", "Replaying the saved offline review-frame check"))
        sink(AgentEvent("vision_qa", "finished", "QA passed the reused demo video", {"status": "passed"}))
        sink(AgentEvent("system", "finished", "Video is ready for your review gate", {"qa_status": "passed"}))
    return RenderedMarketingVideo(
        media_url=media_url,
        poster_url=poster_url,
        duration_seconds=source["duration_seconds"],
        scene_count=len(payload.storyboard),
        qa_status="passed",
        qa_notes=None,
    )


def _payload_from(row: MarketingVideo) -> MarketingVideoCreate:
    return MarketingVideoCreate(
        name=row.name,
        profile=row.profile,
        brand_name=row.brand_name,
        product_name=row.product_name,
        target_audience=row.target_audience,
        cta=row.cta,
        storyboard=row.storyboard,
        use_broll=row.use_broll,
    )


def _row(
    payload: MarketingVideoCreate,
    rendered: RenderedMarketingVideo,
    *,
    campaign_id: int | None = None,
    product_reference_url: str | None = None,
) -> MarketingVideo:
    return MarketingVideo(
        campaign_id=campaign_id,
        name=payload.name,
        profile=payload.profile,
        brand_name=payload.brand_name,
        product_name=payload.product_name,
        target_audience=payload.target_audience,
        cta=payload.cta,
        use_broll=payload.use_broll,
        product_reference_url=product_reference_url,
        storyboard=[scene.model_dump() for scene in payload.storyboard],
        media_url=rendered.media_url,
        poster_url=rendered.poster_url,
        duration_seconds=rendered.duration_seconds,
        scene_count=rendered.scene_count,
        qa_status=rendered.qa_status,
        qa_notes=rendered.qa_notes,
        review_status="pending",
    )


def _apply(row: MarketingVideo, rendered: RenderedMarketingVideo) -> None:
    row.media_url = rendered.media_url
    row.poster_url = rendered.poster_url
    row.duration_seconds = rendered.duration_seconds
    row.scene_count = rendered.scene_count
    row.qa_status = rendered.qa_status
    row.qa_notes = rendered.qa_notes


def _decide(db: Session, video_id: int, decision: str) -> MarketingVideo:
    row = _video_or_404(db, video_id)
    row.review_status = decision
    db.commit()
    return row


def _video_or_404(db: Session, video_id: int) -> MarketingVideo:
    row = db.get(MarketingVideo, video_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no marketing video {video_id}")
    return row


def _forget(studio: VideoStudio, *urls: str) -> None:
    for url in urls:
        try:
            studio.storage.path_for(url).unlink(missing_ok=True)
        except (ValueError, OSError):
            pass


def _campaign_product(
    db: Session,
    campaign_id: int,
    reference_id: int | None,
    studio: VideoStudio,
) -> tuple[str | None, bytes | None]:
    if reference_id is None:
        return primary_product_image(db, campaign_id, studio.storage)
    reference = db.get(ProductReference, reference_id)
    if reference is None or reference.campaign_id != campaign_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "product image does not belong to this campaign")
    try:
        return reference.media_url, studio.storage.read(reference.media_url)
    except (ValueError, OSError):
        raise HTTPException(status.HTTP_409_CONFLICT, "selected product image is no longer available") from None


def _stored_product_image(studio: VideoStudio, media_url: str | None) -> bytes | None:
    if not media_url:
        return None
    try:
        return studio.storage.read(media_url)
    except (ValueError, OSError):
        return None
