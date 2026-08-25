import io

import pytest
from PIL import Image

from app.agents.studio import Studio, VariantSpec
from app.agents.vision_qa import QAVerdict
from app.domain import VisualBrief
from app.media.base import RenderError
from app.media.demo import DemoMediaProvider
from app.media.storage import AssetStorage

BRIEF = VisualBrief(
    composition_notes="subject left of centre",
    image_prompt="a warung at golden hour",
    text_placement="headline upper left",
    placement_zone="top-left",
)
SPEC = VariantSpec(variant_id=7, headline="Raya Deals", cta="Shop now", brief=BRIEF)


class StubQA:
    """Flags the first `flags` reviews, then passes."""

    def __init__(self, flags=0):
        self.flags = flags
        self.calls = 0

    def review(self, image, *, headline, cta, brief):
        self.calls += 1
        if self.calls <= self.flags:
            return QAVerdict(status="flagged", notes="headline is illegible")
        return QAVerdict(status="passed", notes="")


def _studio(tmp_path, qa, provider=None, **kwargs):
    return Studio(
        provider=provider or DemoMediaProvider(),
        qa=qa,
        storage=AssetStorage(tmp_path),
        **kwargs,
    )


def test_produces_a_composited_asset(tmp_path):
    storage = AssetStorage(tmp_path)
    studio = Studio(provider=DemoMediaProvider(), qa=StubQA(), storage=storage)
    asset = studio.run(SPEC)

    assert asset.variant_id == 7
    assert asset.qa_status == "passed"
    image = Image.open(io.BytesIO(storage.read(asset.media_url)))
    assert image.size == (1024, 1024)


def test_a_clean_pass_does_not_redo(tmp_path):
    qa = StubQA(flags=0)
    asset = _studio(tmp_path, qa).run(SPEC)
    assert qa.calls == 1
    assert asset.redos == 0


def test_one_flag_triggers_one_redo_then_passes(tmp_path):
    qa = StubQA(flags=1)
    asset = _studio(tmp_path, qa).run(SPEC)
    assert qa.calls == 2
    assert asset.redos == 1
    assert asset.qa_status == "passed"


def test_redos_are_bounded_and_the_asset_falls_through_flagged(tmp_path):
    qa = StubQA(flags=99)
    asset = _studio(tmp_path, qa, max_redos=2).run(SPEC)

    assert qa.calls == 3  # the first pass plus two redos
    assert asset.redos == 2
    assert asset.qa_status == "flagged"
    assert "illegible" in asset.qa_notes


def test_qa_notes_are_fed_back_into_the_next_render(tmp_path):
    prompts = []

    class Recording(DemoMediaProvider):
        def render_image(self, prompt, *, aspect="1:1"):
            prompts.append(prompt)
            return super().render_image(prompt, aspect=aspect)

    _studio(tmp_path, StubQA(flags=1), provider=Recording()).run(SPEC)

    assert len(prompts) == 2
    assert "illegible" in prompts[1]
    assert "illegible" not in prompts[0]


def test_a_render_failure_propagates(tmp_path):
    class Broken(DemoMediaProvider):
        def render_image(self, prompt, *, aspect="1:1"):
            raise RenderError("vendor is down")

    with pytest.raises(RenderError, match="vendor is down"):
        _studio(tmp_path, StubQA(), provider=Broken()).run(SPEC)


def test_events_narrate_the_run(tmp_path):
    seen = []
    _studio(tmp_path, StubQA(flags=1)).run(SPEC, sink=seen.append)

    agents = [event.agent for event in seen]
    assert "renderer" in agents
    assert "vision_qa" in agents
