"""The studio as a LangGraph: renderer → vision QA, with a bounded redo.

A second graph rather than three more nodes on the crew's, because the two run
at completely different speeds. The crew returns in seconds and can be watched
end to end; a render is a vendor round trip per variant. Bolting them together
would mean `crew.run` no longer returns in a length of time anyone will sit
through, and a crash mid-render would lose copy that was already good.

The redo loop is bounded at `MAX_REDOS`, the same shape as the director's
revision loop. Past the budget the asset falls through carrying
`qa_status="flagged"` and QA's last note — a reviewer is never handed work
while being told it was approved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.events import AgentEvent, EventSink, emit
from app.agents.vision_qa import VisionQA
from app.domain import VisualBrief
from app.media.base import MediaProvider
from app.media.compose import compose_creative
from app.media.storage import AssetStorage

#: Redos QA gets before the asset falls through flagged.
MAX_REDOS = 2


@dataclass(frozen=True)
class VariantSpec:
    """One variant, reduced to what the studio needs to render it."""

    variant_id: int
    headline: str
    cta: str
    brief: VisualBrief
    #: The marketer's selected source photo. It is handed to the image model
    #: as a reference so the product is lit and placed inside the scene, and
    #: to vision QA so the render can be checked against it.
    product_image: bytes | None = None


@dataclass
class RenderedAsset:
    variant_id: int
    media_url: str
    qa_status: str
    qa_notes: str | None
    #: Redos actually run — never more than `max_redos`.
    redos: int


class StudioState(TypedDict):
    spec: VariantSpec
    creative: bytes | None
    qa_status: str
    qa_notes: str
    redos: int
    sink: EventSink | None


class Studio:
    def __init__(
        self,
        *,
        provider: MediaProvider,
        qa: VisionQA,
        storage: AssetStorage,
        max_redos: int = MAX_REDOS,
        aspect: str = "1:1",
    ) -> None:
        self.provider = provider
        self.qa = qa
        self.storage = storage
        self.max_redos = max_redos
        self.aspect = aspect
        self.graph = self._build()

    # -- graph -------------------------------------------------------------

    def _build(self):
        builder = StateGraph(StudioState)
        builder.add_node("renderer", self._render)
        builder.add_node("vision_qa", self._check)

        builder.add_edge(START, "renderer")
        builder.add_edge("renderer", "vision_qa")
        builder.add_conditional_edges(
            "vision_qa", self._route, {"renderer": "renderer", END: END}
        )
        return builder.compile()

    def run(self, spec: VariantSpec, *, sink: EventSink | None = None) -> RenderedAsset:
        final = self.graph.invoke(
            StudioState(
                spec=spec,
                creative=None,
                qa_status="",
                qa_notes="",
                redos=0,
                sink=sink,
            )
        )

        # Written once, at the end: a redo that replaces the image should not
        # leave the rejected one on disk with nothing pointing at it.
        media_url = self.storage.save(final["creative"])
        passed = final["qa_status"] == "passed"

        emit(
            sink,
            AgentEvent(
                "system",
                "finished" if passed else "failed",
                f"Creative for variant {spec.variant_id} "
                + ("passed QA" if passed else "flagged for you"),
                {"variant_id": spec.variant_id, "qa_status": final["qa_status"]},
            ),
        )
        return RenderedAsset(
            variant_id=spec.variant_id,
            media_url=media_url,
            qa_status=final["qa_status"],
            qa_notes=final["qa_notes"] or None,
            redos=min(final["redos"], self.max_redos),
        )

    # -- nodes -------------------------------------------------------------

    def _render(self, state: StudioState) -> dict:
        sink, spec = state["sink"], state["spec"]
        redoing = bool(state["qa_notes"])
        emit(
            sink,
            AgentEvent(
                "renderer",
                "started",
                f"{'Re-rendering' if redoing else 'Rendering'} variant "
                f"{spec.variant_id}",
                {"variant_id": spec.variant_id, "redoing": redoing},
            ),
        )

        background = self.provider.render_image(
            self._prompt(spec, state["qa_notes"]),
            aspect=self.aspect,
            reference_images=(spec.product_image,) if spec.product_image else (),
        )
        creative = compose_creative(
            background,
            headline=spec.headline,
            cta=spec.cta,
            zone=spec.brief.placement_zone,
            treatment=spec.brief.text_treatment,
            aspect=self.aspect,
        )

        emit(
            sink,
            AgentEvent(
                "renderer",
                "finished",
                f"Background rendered and headline composited at "
                f"{spec.brief.placement_zone} with {spec.brief.text_treatment}",
            ),
        )
        return {"creative": creative}

    def _check(self, state: StudioState) -> dict:
        sink, spec = state["sink"], state["spec"]
        emit(sink, AgentEvent("vision_qa", "started", "Checking the finished creative"))

        verdict = self.qa.review(
            state["creative"],
            headline=spec.headline,
            cta=spec.cta,
            brief=spec.brief,
            product_image=spec.product_image,
        )

        emit(
            sink,
            AgentEvent(
                "vision_qa",
                "finished" if verdict.status == "passed" else "failed",
                f"QA: {verdict.status}"
                + (f" — {verdict.notes}" if verdict.notes else ""),
                {"status": verdict.status, "notes": verdict.notes},
            ),
        )
        return {
            "qa_status": verdict.status,
            "qa_notes": verdict.notes,
            "redos": state["redos"] + (0 if verdict.status == "passed" else 1),
        }

    def _route(self, state: StudioState) -> str:
        if state["qa_status"] == "passed":
            return END
        if state["redos"] > self.max_redos:
            emit(
                state["sink"],
                AgentEvent(
                    "system",
                    "failed",
                    f"Redo budget spent after {self.max_redos} attempts — "
                    "handing the creative over flagged",
                ),
            )
            return END
        return "renderer"

    # -- prompt ------------------------------------------------------------

    def _prompt(self, spec: VariantSpec, qa_notes: str) -> str:
        """The brief's prompt, plus the negative space the compositor needs.

        The model is never asked to draw the words — they are composited on
        afterwards — so what it is asked for instead is room for them.
        """
        parts = [
            spec.brief.image_prompt,
            f"Leave clear, uncluttered space in the {spec.brief.placement_zone} "
            "of the frame for text to be placed over afterwards. "
            "Do not render any text, words, letters or numbers in the image.",
        ]
        if qa_notes:
            parts.append(f"A previous attempt was rejected: {qa_notes} Fix this.")
        if spec.product_image:
            parts.append(
                "Build the scene around the attached product photo. The product "
                "in it is real: reproduce it exactly as shown — same shape, "
                "colours, packaging, labels and logos — and place it naturally "
                "in the scene, lit to match. Do not redesign it, substitute a "
                "different product, or add a second one."
            )
        return " ".join(parts)
