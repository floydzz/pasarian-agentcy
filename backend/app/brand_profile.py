"""The canonical, citable representation of the workspace's brand profile."""

from __future__ import annotations

from app.models import BrandProfile

PROFILE_SOURCE = "brand-profile.md"


def as_markdown(profile: BrandProfile) -> str:
    """Render a saved profile as the company corpus's sole source document."""
    lines = [
        f"# {profile.company_name}",
        "",
        "## Company",
        f"Industry: {profile.industry}",
    ]
    if profile.website:
        lines.append(f"Website: {profile.website}")
    lines.extend(
        [
            "",
            "## What the company does",
            profile.description,
            "",
            "## Target audience",
            profile.target_audience,
            "",
            "## Brand voice",
            profile.brand_voice,
            "",
            "## Products and services",
        ]
    )
    for product in profile.products:
        lines.extend(["", f"### {product['name']}", product["description"]])
        if product.get("price"):
            lines.append(f"Price: {product['price']}")
        if product.get("benefits"):
            lines.append(f"Key benefits: {product['benefits']}")
    if profile.approved_claims:
        lines.extend(["", "## Approved claims", profile.approved_claims])
    if profile.restrictions:
        lines.extend(["", "## Restrictions and claims to avoid", profile.restrictions])
    return "\n".join(lines)
