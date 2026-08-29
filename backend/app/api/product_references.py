"""Campaign-owned product photos for protected creative composition."""

from __future__ import annotations

import base64
import binascii
import io

from fastapi import APIRouter, Depends, HTTPException, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_campaign_or_404, get_storage
from app.api.schemas import (
    ProductReferenceCreate,
    ProductReferencePatch,
    ProductReferenceRead,
)
from app.db import get_db
from app.media.storage import AssetStorage
from app.models import ProductReference

router = APIRouter(prefix="/api", tags=["product references"])


@router.get(
    "/campaigns/{campaign_id}/product-references",
    response_model=list[ProductReferenceRead],
)
def list_product_references(
    campaign_id: int, db: Session = Depends(get_db)
) -> list[ProductReference]:
    get_campaign_or_404(db, campaign_id)
    return list(
        db.scalars(
            select(ProductReference)
            .where(ProductReference.campaign_id == campaign_id)
            .order_by(ProductReference.is_primary.desc(), ProductReference.id.desc())
        )
    )


@router.post(
    "/campaigns/{campaign_id}/product-references",
    response_model=ProductReferenceRead,
    status_code=status.HTTP_201_CREATED,
)
def add_product_reference(
    campaign_id: int,
    payload: ProductReferenceCreate,
    db: Session = Depends(get_db),
    storage: AssetStorage = Depends(get_storage),
) -> ProductReference:
    get_campaign_or_404(db, campaign_id)
    image, suffix = image_from_data_url(payload.data_url)
    existing = list_product_references(campaign_id, db)
    primary = payload.is_primary or not any(row.is_primary for row in existing)
    if primary:
        _clear_primary(db, campaign_id)

    row = ProductReference(
        campaign_id=campaign_id,
        label=payload.label,
        media_url=storage.save(image, suffix=suffix),
        is_primary=primary,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch(
    "/campaigns/{campaign_id}/product-references/{reference_id}",
    response_model=ProductReferenceRead,
)
def update_product_reference(
    campaign_id: int,
    reference_id: int,
    payload: ProductReferencePatch,
    db: Session = Depends(get_db),
) -> ProductReference:
    row = _reference_or_404(db, campaign_id, reference_id)
    if payload.label is not None:
        row.label = payload.label
    if payload.is_primary is True:
        _clear_primary(db, campaign_id)
        row.is_primary = True
    if payload.is_primary is False and row.is_primary:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "choose another primary product image before unsetting this one",
        )
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/campaigns/{campaign_id}/product-references/{reference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product_reference(
    campaign_id: int,
    reference_id: int,
    db: Session = Depends(get_db),
    storage: AssetStorage = Depends(get_storage),
) -> None:
    row = _reference_or_404(db, campaign_id, reference_id)
    media_url, was_primary = row.media_url, row.is_primary
    db.delete(row)
    db.flush()
    if was_primary:
        replacement = db.scalar(
            select(ProductReference)
            .where(ProductReference.campaign_id == campaign_id)
            .order_by(ProductReference.id.desc())
            .limit(1)
        )
        if replacement:
            replacement.is_primary = True
    db.commit()
    try:
        storage.path_for(media_url).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


def primary_product_image(
    db: Session, campaign_id: int, storage: AssetStorage
) -> tuple[str | None, bytes | None]:
    """Return the selected original bytes for product-lock composition."""
    row = db.scalar(
        select(ProductReference)
        .where(ProductReference.campaign_id == campaign_id)
        .where(ProductReference.is_primary.is_(True))
        .limit(1)
    )
    if row is None:
        return None, None
    try:
        return row.media_url, storage.read(row.media_url)
    except (ValueError, OSError):
        # A missing source photo must not turn a long creative run into an
        # opaque 500. The render still works without product lock and the UI
        # can show the broken media URL for repair.
        return row.media_url, None


def image_from_data_url(data_url: str) -> tuple[bytes, str]:
    prefix, separator, encoded = data_url.partition(",")
    allowed = {
        "data:image/png;base64": ".png",
        "data:image/jpeg;base64": ".jpg",
        "data:image/webp;base64": ".webp",
    }
    if not separator or prefix not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "send a PNG, JPEG or WEBP product image",
        )
    try:
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "product image data is not valid base64",
        ) from None
    if len(image) > 20 * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "product images must be at most 20 MB",
        )
    try:
        with Image.open(io.BytesIO(image)) as decoded:
            decoded.verify()
            if decoded.width < 300 or decoded.height < 300:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "product images must be at least 300 pixels on each side",
                )
    except UnidentifiedImageError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "product image bytes are invalid",
        ) from None
    return image, allowed[prefix]


def _clear_primary(db: Session, campaign_id: int) -> None:
    for row in db.scalars(
        select(ProductReference).where(ProductReference.campaign_id == campaign_id)
    ):
        row.is_primary = False


def _reference_or_404(
    db: Session, campaign_id: int, reference_id: int
) -> ProductReference:
    get_campaign_or_404(db, campaign_id)
    row = db.get(ProductReference, reference_id)
    if row is None or row.campaign_id != campaign_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no product reference {reference_id}")
    return row
