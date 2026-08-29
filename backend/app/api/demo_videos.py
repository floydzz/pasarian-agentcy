"""The human review gate for Agentcy's own marketing video."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.demo_video import DemoVideoSpec, DemoVideoStudio, RenderedDemoVideo
from app.api.deps import get_demo_video_studio
from app.api.schemas import DemoVideoCreate, DemoVideoRead
from app.db import get_db
from app.media.base import RenderError
from app.models import DemoVideo

router = APIRouter(prefix="/api", tags=["demo video"])


@router.get("/demo-videos", response_model=list[DemoVideoRead])
def list_demo_videos(db: Session = Depends(get_db)) -> list[DemoVideo]:
    return list(db.scalars(select(DemoVideo).order_by(DemoVideo.id.desc())))


@router.post("/demo-videos/render", response_model=DemoVideoRead)
def render_demo_video(
    payload: DemoVideoCreate,
    db: Session = Depends(get_db),
    studio: DemoVideoStudio = Depends(get_demo_video_studio),
) -> DemoVideo:
    rendered = _render(studio, payload)
    row = _row(payload, rendered)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/demo-videos/{video_id}/redo", response_model=DemoVideoRead)
def redo_demo_video(
    video_id: int,
    db: Session = Depends(get_db),
    studio: DemoVideoStudio = Depends(get_demo_video_studio),
) -> DemoVideo:
    row = _video_or_404(db, video_id)
    payload = DemoVideoCreate(title=row.title, strapline=row.strapline, cta=row.cta)
    rendered = _render(studio, payload)
    superseded = (row.media_url, row.poster_url)
    _apply(row, rendered)
    row.review_status = "pending"
    db.commit()
    _forget(studio, *superseded)
    return row


@router.post("/demo-videos/{video_id}/approve", response_model=DemoVideoRead)
def approve_demo_video(video_id: int, db: Session = Depends(get_db)) -> DemoVideo:
    return _decide(db, video_id, "approved")


@router.post("/demo-videos/{video_id}/reject", response_model=DemoVideoRead)
def reject_demo_video(video_id: int, db: Session = Depends(get_db)) -> DemoVideo:
    return _decide(db, video_id, "rejected")


def _render(studio: DemoVideoStudio, payload: DemoVideoCreate) -> RenderedDemoVideo:
    try:
        return studio.run(
            DemoVideoSpec(
                title=payload.title,
                strapline=payload.strapline,
                cta=payload.cta,
                use_broll=payload.use_broll,
            )
        )
    except RenderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error


def _row(payload: DemoVideoCreate, rendered: RenderedDemoVideo) -> DemoVideo:
    return DemoVideo(
        title=payload.title,
        strapline=payload.strapline,
        cta=payload.cta,
        media_url=rendered.media_url,
        poster_url=rendered.poster_url,
        duration_seconds=rendered.duration_seconds,
        scene_count=rendered.scene_count,
        qa_status=rendered.qa_status,
        qa_notes=rendered.qa_notes,
        review_status="pending",
    )


def _apply(row: DemoVideo, rendered: RenderedDemoVideo) -> None:
    row.media_url = rendered.media_url
    row.poster_url = rendered.poster_url
    row.duration_seconds = rendered.duration_seconds
    row.scene_count = rendered.scene_count
    row.qa_status = rendered.qa_status
    row.qa_notes = rendered.qa_notes


def _decide(db: Session, video_id: int, decision: str) -> DemoVideo:
    row = _video_or_404(db, video_id)
    row.review_status = decision
    db.commit()
    return row


def _video_or_404(db: Session, video_id: int) -> DemoVideo:
    row = db.get(DemoVideo, video_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no demo video {video_id}")
    return row


def _forget(studio: DemoVideoStudio, *urls: str) -> None:
    """A redo replaces both the film and its review poster, best effort."""
    for url in urls:
        try:
            studio.storage.path_for(url).unlink(missing_ok=True)
        except (ValueError, OSError):
            pass
