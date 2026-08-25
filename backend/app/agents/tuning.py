"""What each agent exposes to the person running it.

The registry below is the single description of the crew's tunable surface, and
both the API and the console read it rather than each keeping their own copy.
Every knob is bounded here, at the definition, because these values buy model
calls: an unbounded "concepts per brief" box is an unbounded bill, and a
retrieval width of 200 does not read the brand better, it just pushes the
guardrails out of the context window.

Nothing here can loosen a grounding rule. The knobs move quantities, and the
standing note is appended after the system prompt rather than replacing any of
it — see `with_house_note`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.crew import COMPANY_K as CREW_COMPANY_K
from app.agents.crew import MAX_REVISIONS
from app.agents.planner import COMPANY_K as PLANNER_COMPANY_K
from app.agents.planner import DEFAULT_CONCEPT_COUNT, TREND_K

PLANNER = "planner"
COPYWRITER = "copywriter"
VISUAL_PLANNER = "visual_planner"
DIRECTOR = "director"
#: Belongs to the studio, not the crew — deliberately outside CREW_AGENTS.
VISION_QA = "vision_qa"

#: The crew shares one retrieval width — all three read the same brand ground
#: truth for a concept, so the copy and the review of it can never disagree
#: about what the guardrails say. The knob lives on the copywriter and the
#: others follow it.
CREW_AGENTS = (COPYWRITER, VISUAL_PLANNER, DIRECTOR)


@dataclass(frozen=True)
class Knob:
    """One integer a person may move, with the range it may move inside."""

    field: str
    label: str
    help: str
    minimum: int
    maximum: int
    default: int


@dataclass(frozen=True)
class AgentProfile:
    agent: str
    label: str
    role: str
    #: What this agent is not allowed to do. Stated because the division of
    #: labour is the design — a director that rewrites is not a director.
    boundary: str
    #: An example of a house note that suits this agent specifically.
    note_placeholder: str
    knobs: tuple[Knob, ...]


PROFILES: tuple[AgentProfile, ...] = (
    AgentProfile(
        agent=PLANNER,
        label="Planner",
        role="Reads the brief, the brand and the trends, and proposes concepts "
        "with their sources attached.",
        boundary="Cannot write copy, and cannot propose a concept it has not "
        "grounded in at least one company-knowledge chunk.",
        note_placeholder="Favour concepts that work as a carousel. Avoid "
        "anything that needs a celebrity.",
        knobs=(
            Knob(
                field="concept_count",
                label="Concepts per brief",
                help="More concepts is more to review, not a better plan.",
                minimum=1,
                maximum=6,
                default=DEFAULT_CONCEPT_COUNT,
            ),
            Knob(
                field="company_k",
                label="Brand chunks read",
                help="Ground truth. Widening this admits more of the brand and "
                "more of the guardrails at once.",
                minimum=2,
                maximum=12,
                default=PLANNER_COMPANY_K,
            ),
            Knob(
                field="trend_k",
                label="Trend chunks read",
                help="Inspiration only — a trend can suggest an angle, never a "
                "fact about the product.",
                minimum=0,
                maximum=12,
                default=TREND_K,
            ),
        ),
    ),
    AgentProfile(
        agent=COPYWRITER,
        label="Copywriter",
        role="Turns one approved concept into one variant per variation axis, "
        "in the brand's voice.",
        boundary="Cannot choose the concept and cannot change how many variants "
        "there are — the axes decide that.",
        note_placeholder="Keep headlines under eight words. Use Manglish only "
        "where the brand book already does.",
        knobs=(
            Knob(
                field="company_k",
                label="Brand chunks read",
                help="Shared by the whole crew, so the writing and the review "
                "of it judge against the same ground truth.",
                minimum=2,
                maximum=16,
                default=CREW_COMPANY_K,
            ),
        ),
    ),
    AgentProfile(
        agent=VISUAL_PLANNER,
        label="Art director",
        role="Plans the image each variant needs, around copy that is already "
        "final.",
        boundary="Cannot rewrite the copy and cannot ask for it to change — it "
        "plans around the exact words it was handed.",
        note_placeholder="Shoot interiors, not studio white. Always leave the "
        "lower third clear for the CTA.",
        knobs=(),
    ),
    AgentProfile(
        agent=DIRECTOR,
        label="Creative director",
        role="Judges copy and image as a pair on brand, diversity and "
        "execution, then passes or sends back.",
        boundary="Cannot fix anything itself — a reviewer that edits its own "
        "work has stopped reviewing.",
        note_placeholder="Be strict about two variants saying the same thing. "
        "Let small voice wobbles through.",
        knobs=(
            Knob(
                field="max_revisions",
                label="Revisions allowed",
                help="The budget before work falls through flagged for you. "
                "Zero means one pass and no send-backs.",
                minimum=0,
                maximum=4,
                default=MAX_REVISIONS,
            ),
        ),
    ),
    AgentProfile(
        agent=VISION_QA,
        label="Quality checker",
        role="Looks at each finished creative before a human does, and flags "
        "the ones worth a second pair of eyes.",
        boundary="Cannot fix an asset and cannot approve one on your behalf — "
        "it decides what deserves your attention, not what ships.",
        note_placeholder="Be strict about hands and about text over faces. "
        "Ignore minor background oddities.",
        knobs=(
            Knob(
                field="max_redos",
                label="Redos allowed",
                help="Each redo is another render, and another charge. Past "
                "this the creative is handed over flagged.",
                minimum=0,
                maximum=3,
                # Stated as a literal rather than imported from `app.agents.studio`,
                # which imports this module's siblings — the same reason the
                # director's default is declared here.
                default=2,
            ),
        ),
    ),
)

BY_AGENT = {profile.agent: profile for profile in PROFILES}


def defaults(agent: str) -> dict[str, int]:
    return {knob.field: knob.default for knob in BY_AGENT[agent].knobs}


def clamp(agent: str, field: str, value: int) -> int:
    """Hold a submitted value inside the range the knob declares.

    Clamped rather than rejected: the range is a property of the machine, not
    of the request, and a person dragging a slider to the end should land at
    the end rather than at an error.
    """
    knob = next(k for k in BY_AGENT[agent].knobs if k.field == field)
    return max(knob.minimum, min(knob.maximum, value))
