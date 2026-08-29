"""The single workspace's editable company ground truth."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_store
from app.api.schemas import BrandProfileRead, BrandProfileWrite
from app.brand_profile import PROFILE_SOURCE, as_markdown
from app.db import get_db
from app.models import BrandProfile
from app.rag.store import COMPANY_KB, KnowledgeStore

router = APIRouter(prefix="/api", tags=["brand profile"])


@router.get("/brand-profile", response_model=BrandProfileRead)
def read_brand_profile(
    db: Session = Depends(get_db), store: KnowledgeStore = Depends(get_store)
) -> BrandProfileRead:
    profile = _profile(db)
    return _as_read(profile, knowledge_chunks=store.count(COMPANY_KB))


@router.put("/brand-profile", response_model=BrandProfileRead)
def save_brand_profile(
    payload: BrandProfileWrite,
    db: Session = Depends(get_db),
    store: KnowledgeStore = Depends(get_store),
) -> BrandProfileRead:
    profile = _profile(db)
    values = payload.model_dump()
    if profile is None:
        profile = BrandProfile(**values)
        db.add(profile)
    else:
        for field, value in values.items():
            setattr(profile, field, value)

    db.flush()
    try:
        chunks = store.replace_company_kb(as_markdown(profile), source=PROFILE_SOURCE)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "could not update the company knowledge base; your profile was not saved",
        ) from error

    db.commit()
    db.refresh(profile)
    return _as_read(profile, knowledge_chunks=chunks)


def _profile(db: Session) -> BrandProfile | None:
    return db.scalar(select(BrandProfile).order_by(BrandProfile.id).limit(1))


def _as_read(profile: BrandProfile | None, *, knowledge_chunks: int) -> BrandProfileRead:
    if profile is None:
        return BrandProfileRead(
            configured=False,
            knowledge_chunks=knowledge_chunks,
            company_name="",
            industry="",
            website=None,
            description="",
            brand_voice="",
            target_audience="",
            products=[],
            approved_claims=None,
            restrictions=None,
            updated_at=None,
        )
    return BrandProfileRead(
        configured=True,
        knowledge_chunks=knowledge_chunks,
        company_name=profile.company_name,
        industry=profile.industry,
        website=profile.website,
        description=profile.description,
        brand_voice=profile.brand_voice,
        target_audience=profile.target_audience,
        products=profile.products,
        approved_claims=profile.approved_claims,
        restrictions=profile.restrictions,
        updated_at=profile.updated_at,
    )

