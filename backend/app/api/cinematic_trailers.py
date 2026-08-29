"""API for durable, multi-shot AI-generated cinematic trailers."""

from __future__ import annotations

import base64
import binascii
import io

from fastapi import APIRouter, Depends, HTTPException, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.cinematic_trailer import CinematicTrailerStudio
from app.api.deps import get_campaign_or_404, get_cinematic_trailer_studio
from app.api.schemas import (
    CinematicTrailerAssetCreate,
    CinematicTrailerCaptureCreate,
    CinematicTrailerCreate,
    CinematicTrailerRead,
    CinematicTrailerSoundtrackCreate,
)
from app.db import get_db
from app.media.base import RenderError
from app.models import CinematicTrailer, CinematicTrailerShot

router = APIRouter(prefix="/api/cinematic-trailers", tags=["cinematic trailers"])


@router.get("", response_model=list[CinematicTrailerRead])
def list_trailers(
    campaign_id: int | None = None, db: Session = Depends(get_db)
) -> list[CinematicTrailer]:
    query = (
        select(CinematicTrailer)
        .options(selectinload(CinematicTrailer.shots))
        .order_by(CinematicTrailer.id.desc())
    )
    if campaign_id is not None:
        query = query.where(CinematicTrailer.campaign_id == campaign_id)
    return list(db.scalars(query))


@router.post("", response_model=CinematicTrailerRead, status_code=status.HTTP_201_CREATED)
def create_trailer(
    payload: CinematicTrailerCreate,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    if payload.campaign_id is not None:
        get_campaign_or_404(db, payload.campaign_id)
    trailer = CinematicTrailer(
        campaign_id=payload.campaign_id,
        title=payload.title,
        aspect_ratio=payload.aspect_ratio,
        cta=payload.cta,
        duration_seconds=sum(shot.duration_seconds for shot in payload.shots),
    )
    application_urls: dict[str, str] = {}
    for position, shot in enumerate(payload.shots, start=1):
        references = list(shot.reference_asset_urls)
        product_surface = shot.product_surface
        # `use_application_image` keeps custom/legacy payloads working. New
        # presets name the exact screen that should explain this scene.
        if shot.use_application_image and product_surface == "none":
            product_surface = "studio"
        if product_surface != "none":
            if product_surface not in application_urls:
                application_urls[product_surface] = _application_asset(studio, product_surface)
            references.insert(0, application_urls[product_surface])
        trailer.shots.append(
            CinematicTrailerShot(
                position=position,
                label=shot.label,
                title_card=shot.title_card,
                prompt=shot.prompt,
                mode=shot.mode,
                duration_seconds=shot.duration_seconds,
                voiceover=shot.voiceover,
                audio_cue=shot.audio_cue,
                reference_asset_urls=references,
                # `protect_reference` is a creative choice: protected images
                # are locally composited after generation, while an AI-native
                # product shot sends the screenshot to R2V to animate it.
                protect_reference=shot.protect_reference,
                product_surface=product_surface,
            )
        )
    db.add(trailer)
    db.commit()
    db.refresh(trailer)
    return _with_shots(db, trailer.id)


@router.get("/{trailer_id}", response_model=CinematicTrailerRead)
def get_trailer(trailer_id: int, db: Session = Depends(get_db)) -> CinematicTrailer:
    return _with_shots(db, trailer_id)


@router.post("/assets", response_model=dict[str, str], status_code=status.HTTP_201_CREATED)
def upload_reference_asset(
    payload: CinematicTrailerAssetCreate,
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> dict[str, str]:
    """Store a reference image before it is ever sent to a video model."""
    image, suffix = _image_from_data_url(payload.data_url)
    return {"media_url": studio.storage.save(image, suffix=suffix)}


@router.post("/{trailer_id}/product-reference", response_model=CinematicTrailerRead)
def upload_product_reference(
    trailer_id: int,
    payload: CinematicTrailerAssetCreate,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    """Attach a real product image for protected local trailer composition."""
    trailer = _with_shots(db, trailer_id)
    image, suffix = _image_from_data_url(payload.data_url)
    previous = trailer.product_reference_url
    superseded = _invalidate_master(trailer)
    trailer.product_reference_url = studio.storage.save(image, suffix=suffix)
    db.commit()
    _forget(studio, previous)
    _forget(studio, *superseded)
    return _with_shots(db, trailer_id)


@router.post("/{trailer_id}/application-capture", response_model=CinematicTrailerRead)
def upload_application_capture(
    trailer_id: int,
    payload: CinematicTrailerCaptureCreate,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    """Attach a real UI journey for exact screen treatment.

    For feature shots, Agentcy extracts just the matching still frame and
    sends that frame to the video model, so its generated environment is
    guided by the real product state rather than an invented dashboard. The
    finished AI clip is preserved; this route does not paste the recording on
    top of it.
    """
    trailer = _with_shots(db, trailer_id)
    capture = _mp4_from_data_url(payload.data_url)
    previous = trailer.application_capture_url
    superseded = _invalidate_master(trailer)
    trailer.application_capture_url = studio.storage.save(capture, suffix=".mp4")
    db.commit()
    _forget(studio, previous)
    _forget(studio, *superseded)
    return trailer


@router.post("/{trailer_id}/soundtrack", response_model=CinematicTrailerRead)
def upload_soundtrack(
    trailer_id: int,
    payload: CinematicTrailerSoundtrackCreate,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    """Attach an instrumental master track without spending on new clips."""
    audio, suffix = _audio_from_data_url(payload.data_url)
    trailer = _with_shots(db, trailer_id)
    previous = trailer.soundtrack_url
    superseded = _invalidate_master(trailer)
    trailer.soundtrack_url = studio.storage.save(audio, suffix=suffix)
    db.commit()
    _forget(studio, previous)
    _forget(studio, *superseded)
    return _with_shots(db, trailer_id)


@router.post("/{trailer_id}/submit", response_model=CinematicTrailerRead)
def submit_trailer(
    trailer_id: int,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    trailer = _with_shots(db, trailer_id)
    try:
        studio.submit(trailer)
    except RenderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    return trailer


@router.post("/{trailer_id}/refresh", response_model=CinematicTrailerRead)
def refresh_trailer(
    trailer_id: int,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    trailer = _with_shots(db, trailer_id)
    try:
        studio.refresh(trailer)
    except RenderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    return trailer


@router.post("/{trailer_id}/shots/{shot_id}/regenerate", response_model=CinematicTrailerRead)
def regenerate_shot(
    trailer_id: int,
    shot_id: int,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    trailer = _with_shots(db, trailer_id)
    shot = next((item for item in trailer.shots if item.id == shot_id), None)
    if shot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trailer shot {shot_id}")
    old_master = _invalidate_master(trailer)
    old_clip = shot.media_url
    try:
        studio.regenerate(trailer, [shot])
    except RenderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    _forget(studio, old_clip, *old_master)
    return _with_shots(db, trailer_id)


@router.post("/{trailer_id}/shots/regenerate", response_model=CinematicTrailerRead)
def regenerate_all_shots(
    trailer_id: int,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    trailer = _with_shots(db, trailer_id)
    old_master = _invalidate_master(trailer)
    old_clips = [shot.media_url for shot in trailer.shots]
    try:
        studio.regenerate(trailer, list(trailer.shots))
    except RenderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    _forget(studio, *old_clips, *old_master)
    return _with_shots(db, trailer_id)


@router.post("/{trailer_id}/compose", response_model=CinematicTrailerRead)
def compose_trailer(
    trailer_id: int,
    db: Session = Depends(get_db),
    studio: CinematicTrailerStudio = Depends(get_cinematic_trailer_studio),
) -> CinematicTrailer:
    trailer = _with_shots(db, trailer_id)
    try:
        old = (trailer.media_url, trailer.poster_url)
        studio.compose(trailer)
    except RenderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    _forget(studio, *old)
    return trailer


@router.post("/{trailer_id}/approve", response_model=CinematicTrailerRead)
def approve_trailer(trailer_id: int, db: Session = Depends(get_db)) -> CinematicTrailer:
    trailer = _with_shots(db, trailer_id)
    if trailer.status != "rendered":
        raise HTTPException(status.HTTP_409_CONFLICT, "compose the trailer before approving it")
    trailer.review_status = "approved"
    db.commit()
    return trailer


@router.post("/{trailer_id}/reject", response_model=CinematicTrailerRead)
def reject_trailer(trailer_id: int, db: Session = Depends(get_db)) -> CinematicTrailer:
    trailer = _with_shots(db, trailer_id)
    trailer.review_status = "rejected"
    db.commit()
    return trailer


def _with_shots(db: Session, trailer_id: int) -> CinematicTrailer:
    trailer = db.scalar(
        select(CinematicTrailer)
        .where(CinematicTrailer.id == trailer_id)
        .options(selectinload(CinematicTrailer.shots))
    )
    if trailer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no cinematic trailer {trailer_id}")
    return trailer


def _application_asset(studio: CinematicTrailerStudio, surface: str) -> str:
    try:
        return studio.application_image_url(surface)
    except RenderError as error:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(error)) from error


def _image_from_data_url(data_url: str) -> tuple[bytes, str]:
    prefix, separator, encoded = data_url.partition(",")
    if not separator or prefix not in {
        "data:image/png;base64",
        "data:image/jpeg;base64",
        "data:image/webp;base64",
    }:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "send a PNG, JPEG or WEBP data URL")
    try:
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "image data is not valid base64") from None
    if len(image) > 20 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "reference images must be at most 20 MB")
    try:
        with Image.open(io.BytesIO(image)) as decoded:
            decoded.verify()
            if decoded.width < 300 or decoded.height < 300:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "reference images must be at least 300 pixels on each side")
    except UnidentifiedImageError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "reference image bytes are invalid") from None
    suffix = {
        "data:image/png;base64": ".png",
        "data:image/jpeg;base64": ".jpg",
        "data:image/webp;base64": ".webp",
    }[prefix]
    return image, suffix


def _mp4_from_data_url(data_url: str) -> bytes:
    prefix, separator, encoded = data_url.partition(",")
    if prefix != "data:video/mp4;base64" or not separator:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "send an MP4 data URL")
    try:
        video = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "video data is not valid base64") from None
    if len(video) > 120 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "product captures must be at most 120 MB")
    if len(video) < 16 or video[4:8] != b"ftyp":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "product capture is not a valid MP4")
    return video


def _audio_from_data_url(data_url: str) -> tuple[bytes, str]:
    prefix, separator, encoded = data_url.partition(",")
    suffixes = {
        "data:audio/mpeg;base64": ".mp3",
        "data:audio/mp3;base64": ".mp3",
        "data:audio/wav;base64": ".wav",
        "data:audio/x-wav;base64": ".wav",
    }
    if not separator or prefix not in suffixes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "send an MP3 or WAV instrumental track",
        )
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "soundtrack data is not valid base64") from None
    if len(audio) > 50 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "soundtracks must be at most 50 MB")
    if len(audio) < 64:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "soundtrack bytes are invalid")
    return audio, suffixes[prefix]


def _forget(studio: CinematicTrailerStudio, *urls: str | None) -> None:
    for url in urls:
        if not url:
            continue
        try:
            studio.storage.path_for(url).unlink(missing_ok=True)
        except (ValueError, OSError):
            pass


def _invalidate_master(trailer: CinematicTrailer) -> tuple[str | None, str | None]:
    """Make a changed local source visible without repurchasing AI shots.

    A finished master is no longer truthful after its protected product photo
    or real UI capture changes. The generated source shots remain reusable, so
    only the free finishing pass is owed again.
    """
    if trailer.status != "rendered":
        return None, None
    superseded = trailer.media_url, trailer.poster_url
    trailer.media_url = None
    trailer.poster_url = None
    trailer.status = "ready_to_compose"
    trailer.review_status = "pending"
    return superseded
