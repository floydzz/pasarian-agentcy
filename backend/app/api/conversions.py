"""Turning stored rows back into the domain objects the agents expect.

The agents never see an ORM row. They take the same `domain.Concept` whether it
came fresh out of the planner or back off a table, so nothing downstream has to
care which.
"""

from __future__ import annotations

from app.domain import Concept as DomainConcept
from app.models import Campaign, Concept


def to_domain_concept(concept: Concept, campaign: Campaign) -> DomainConcept:
    return DomainConcept(
        concept_id=str(concept.id),
        theme=concept.theme,
        format=concept.format,
        trend_rationale=concept.trend_rationale,
        brand_rationale=concept.brand_rationale,
        variant_count=concept.variant_count,
        variation_axes=concept.variation_axes,
        status=concept.status,
        # Provenance lives on the campaign — the calendar drafted the brief,
        # not the individual concept.
        provenance=campaign.source_event,
    )
