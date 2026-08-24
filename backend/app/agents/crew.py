"""The generation crew as a LangGraph: copywriter → visual planner → director.

The cycle is the reason this is a graph and not three function calls. The
director can send work back, and where it goes back to matters: rewritten copy
invalidates the visuals planned around it, so `revise_copy` re-enters at the
copywriter and flows forward through the visual planner again, while
`revise_visuals` re-enters at the planner and leaves the copy alone.

The loop is bounded at `MAX_REVISIONS`. Past that the variants fall through
carrying `director_status="flagged"` and the director's last notes, which is the
point: a demo must never hang on an agent and a reviewer must never be handed
work while being told it was approved.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.copywriter import CopyDraft, Copywriter
from app.agents.director import Director
from app.agents.events import AgentEvent, EventSink, emit
from app.agents.visual_planner import VisualDraft, VisualPlanner
from app.domain import Concept, Variant, VisualBrief
from app.rag.store import KnowledgeStore, Retrieved

#: Retries the director gets before the work falls through flagged.
MAX_REVISIONS = 2

#: How much company knowledge the crew works from. Wider than the planner's
#: window: the planner only has to justify an idea, this crew has to write in
#: the voice and stay inside the claim guardrails.
COMPANY_K = 8


class CrewState(TypedDict):
    """What flows around the graph."""

    concept: Concept
    brand_context: list[Retrieved]
    copy: list[CopyDraft]
    visuals: list[VisualDraft]
    #: Times the director has sent the work back, granted or not.
    rejections: int
    verdict: str
    notes: str
    #: Where the nodes report progress. Not state the graph reasons about —
    #: it rides along so each node can announce itself as it runs.
    sink: EventSink | None


@dataclass
class CrewResult:
    variants: list[Variant]
    #: Revision passes actually run — never more than `MAX_REVISIONS`.
    revisions: int

    @property
    def passed(self) -> bool:
        return all(variant.director_status == "pass" for variant in self.variants)


class GenerationCrew:
    def __init__(
        self,
        *,
        copywriter: Copywriter,
        visual_planner: VisualPlanner,
        director: Director,
        store: KnowledgeStore,
        max_revisions: int = MAX_REVISIONS,
        company_k: int = COMPANY_K,
    ) -> None:
        self.copywriter = copywriter
        self.visual_planner = visual_planner
        self.director = director
        self.store = store
        self.max_revisions = max_revisions
        self.company_k = company_k
        self.graph = self._build()

    # -- graph -------------------------------------------------------------

    def _build(self):
        builder = StateGraph(CrewState)
        builder.add_node("copywriter", self._write_copy)
        builder.add_node("visual_planner", self._plan_visuals)
        builder.add_node("director", self._review)

        builder.add_edge(START, "copywriter")
        # Copy always flows into visual planning, so rewritten copy is never
        # left paired with visuals planned for the copy it replaced.
        builder.add_edge("copywriter", "visual_planner")
        builder.add_edge("visual_planner", "director")
        builder.add_conditional_edges(
            "director",
            self._route,
            {"copywriter": "copywriter", "visual_planner": "visual_planner", END: END},
        )
        return builder.compile()

    def run(self, concept: Concept, *, sink: EventSink | None = None) -> CrewResult:
        emit(
            sink,
            AgentEvent(
                "system",
                "started",
                f"Crew opened on “{concept.theme}”",
                {"concept_id": concept.concept_id, "axes": concept.variation_axes},
            ),
        )

        # One retrieval per concept, before the graph starts: every agent and
        # every revision pass judges against the same brand ground truth.
        brand_context = self.store.retrieve_company(
            f"{concept.theme}\n{concept.brand_rationale}", k=self.company_k
        )
        emit(
            sink,
            AgentEvent(
                "system",
                "finished",
                f"Retrieved {len(brand_context)} brand chunks as ground truth",
                {"chunks": [hit.chunk_id for hit in brand_context]},
            ),
        )

        final = self.graph.invoke(
            CrewState(
                concept=concept,
                brand_context=brand_context,
                copy=[],
                visuals=[],
                rejections=0,
                verdict="",
                notes="",
                sink=sink,
            )
        )
        result = self._assemble(final)
        emit(
            sink,
            AgentEvent(
                "system",
                "finished" if result.passed else "failed",
                f"{len(result.variants)} variants after {result.revisions} "
                f"{'revision' if result.revisions == 1 else 'revisions'} — "
                f"{'passed' if result.passed else 'flagged for you'}",
                {"passed": result.passed, "revisions": result.revisions},
            ),
        )
        return result

    # -- nodes -------------------------------------------------------------

    def _write_copy(self, state: CrewState) -> dict:
        sink, concept = state["sink"], state["concept"]
        revising = bool(state["notes"])
        emit(
            sink,
            AgentEvent(
                "copywriter",
                "started",
                f"{'Rewriting' if revising else 'Writing'} {concept.variant_count} "
                f"variants, one per axis",
                {"axes": concept.variation_axes, "revising": revising},
            ),
        )

        copy = self.copywriter.write(
            concept,
            brand_context=state["brand_context"],
            revision_notes=state["notes"] or None,
        )

        emit(
            sink,
            AgentEvent(
                "copywriter",
                "finished",
                f"{len(copy)} variants written",
                {"headlines": [draft.headline for draft in copy]},
            ),
        )
        return {"copy": copy}

    def _plan_visuals(self, state: CrewState) -> dict:
        sink = state["sink"]
        emit(
            sink,
            AgentEvent(
                "visual_planner",
                "started",
                f"Planning {len(state['copy'])} images around the finished copy",
            ),
        )

        visuals = self.visual_planner.plan(
            state["concept"],
            state["copy"],
            brand_context=state["brand_context"],
            revision_notes=state["notes"] or None,
        )

        emit(
            sink,
            AgentEvent(
                "visual_planner", "finished", f"{len(visuals)} image briefs planned"
            ),
        )
        return {"visuals": visuals}

    def _review(self, state: CrewState) -> dict:
        sink = state["sink"]
        emit(
            sink,
            AgentEvent(
                "director",
                "started",
                f"Reviewing {len(state['copy'])} pairs on brand, diversity, execution",
            ),
        )

        verdict = self.director.review(
            state["concept"],
            state["copy"],
            state["visuals"],
            brand_context=state["brand_context"],
        )

        emit(
            sink,
            AgentEvent(
                "director",
                "finished" if verdict.verdict == "pass" else "failed",
                f"Verdict: {verdict.verdict}"
                + (f" — {verdict.notes}" if verdict.notes else ""),
                {"verdict": verdict.verdict, "notes": verdict.notes},
            ),
        )
        return {
            "verdict": verdict.verdict,
            "notes": verdict.notes,
            "rejections": state["rejections"]
            + (0 if verdict.verdict == "pass" else 1),
        }

    def _route(self, state: CrewState) -> str:
        sink = state["sink"]
        if state["verdict"] == "pass":
            return END
        if state["rejections"] > self.max_revisions:
            # Budget spent. Fall through flagged rather than loop on stage.
            emit(
                sink,
                AgentEvent(
                    "system",
                    "failed",
                    f"Revision budget spent after {self.max_revisions} passes — "
                    "handing the work over flagged",
                ),
            )
            return END

        target = "copywriter" if state["verdict"] == "revise_copy" else "visual_planner"
        emit(
            sink,
            AgentEvent(
                "system",
                "started",
                f"Revision {state['rejections']} of {self.max_revisions} → {target}",
                {"target": target, "revision": state["rejections"]},
            ),
        )
        return target

    # -- assembly ----------------------------------------------------------

    def _assemble(self, state: CrewState) -> CrewResult:
        passed = state["verdict"] == "pass"
        variants = [
            Variant(
                variant_id=str(uuid.uuid4()),
                concept_id=state["concept"].concept_id,
                hook_type=written.hook_type,
                headline=written.headline,
                body=written.body,
                cta=written.cta,
                visual_brief=VisualBrief(**planned.model_dump()),
                director_status="pass" if passed else "flagged",
                director_notes=None if passed else state["notes"],
            )
            for written, planned in zip(state["copy"], state["visuals"], strict=True)
        ]
        return CrewResult(
            variants=variants,
            revisions=min(state["rejections"], self.max_revisions),
        )
