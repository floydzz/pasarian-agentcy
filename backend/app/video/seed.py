"""Turn a campaign into a first draft of a video brief.

A person arriving at a campaign's video studio has already done the work of
saying what the campaign is: they wrote the brief, the planner proposed
concepts, and they approved a variant whose headline and call to action have
already survived the plan gate. Asking them to type all of it again into a
storyboard form would be asking twice.

So this seeds. It never decides — every field it fills is editable, and the
video is only rendered when the person presses the button. What it guarantees
is that the storyboard opens saying the same thing the campaign says.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BrandProfile, Campaign, Concept, Variant

#: A storyboard needs at least three beats (the schema enforces it) and reads
#: badly past six, so the middle section is capped rather than following the
#: concept count wherever it goes.
MAX_MIDDLE_SCENES = 3


def video_brief_for(db: Session, campaign: Campaign) -> dict:
    """Best available draft of this campaign's video, as a create payload."""
    profile = db.scalars(select(BrandProfile).order_by(BrandProfile.id)).first()
    concepts = list(
        db.scalars(
            select(Concept).where(Concept.campaign_id == campaign.id).order_by(Concept.id)
        )
    )
    variant = _lead_variant(db, concepts)

    brand_name = profile.company_name if profile else "Your brand"
    audience = (
        profile.target_audience
        if profile and profile.target_audience.strip()
        else "The people this campaign is for."
    )
    product = _product_name(profile) or campaign.name

    return {
        "name": _fit(f"{campaign.name} — video", 280),
        "profile": "product_marketing",
        "brand_name": _fit(brand_name, 200),
        "product_name": _fit(product, 280),
        "target_audience": _fit(audience, 700),
        "cta": _fit(variant.cta if variant else "Find out more.", 280),
        "storyboard": _storyboard(campaign, concepts, variant, brand_name),
    }


def _lead_variant(db: Session, concepts: list[Concept]) -> Variant | None:
    """The approved work, preferred over anything the director flagged.

    An approved concept's passing variant is the one piece of copy in the
    campaign a person has actually signed off, so it leads the film.
    """
    approved = [c.id for c in concepts if c.status.value == "approved"] if concepts else []
    if not approved:
        return None
    variants = list(
        db.scalars(
            select(Variant).where(Variant.concept_id.in_(approved)).order_by(Variant.id)
        )
    )
    if not variants:
        return None
    return next((v for v in variants if v.director_status == "pass"), variants[0])


def _product_name(profile: BrandProfile | None) -> str | None:
    if profile is None:
        return None
    for product in profile.products or []:
        name = str(product.get("name", "")).strip()
        if name:
            return name
    return None


def _storyboard(
    campaign: Campaign,
    concepts: list[Concept],
    variant: Variant | None,
    brand_name: str,
) -> list[dict]:
    brief = campaign.brief.strip()
    opening = {
        "eyebrow": brand_name,
        "headline": variant.headline if variant else campaign.name,
        "body": (variant.body if variant else brief) or campaign.name,
        "layout": "hero",
    }

    middle = [
        {
            "eyebrow": concept.format,
            "headline": concept.theme,
            "body": concept.brand_rationale or concept.trend_rationale or brief,
            "layout": "feature",
        }
        for concept in concepts
        if concept.status.value == "approved"
    ][:MAX_MIDDLE_SCENES]

    # Without an approved concept there is still a brief, and a two-scene film
    # would be rejected by the schema — so the brief itself carries the middle.
    if not middle:
        middle = [
            {
                "eyebrow": "The brief",
                "headline": campaign.name,
                "body": brief or "No brief was written for this campaign yet.",
                "layout": "feature",
            }
        ]

    closing = {
        "eyebrow": "Next",
        "headline": variant.cta if variant else "Find out more.",
        "body": (variant.body if variant else brief) or f"{brand_name} — {campaign.name}",
        "layout": "cta",
    }
    scenes = [opening, *middle, closing]
    # Generated briefs and approved copy can be longer than a video frame.
    # Fit only this editable draft; keep the original campaign/copy unchanged.
    for scene in scenes:
        for field, limit in (("eyebrow", 80), ("headline", 220), ("body", 700)):
            scene[field] = _fit(scene[field], limit)
    return scenes


def _fit(value: str, limit: int) -> str:
    value = value.strip() or "Review this scene."
    if len(value) <= limit:
        return value
    clipped = value[:limit - 1]
    boundary = clipped.rfind(" ")
    return (clipped[:boundary] if boundary > limit // 2 else clipped).rstrip() + "…"
