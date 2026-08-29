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
        self.product_images = []

    def review(self, image, *, headline, cta, brief, product_image=None):
        self.calls += 1
        self.product_images.append(product_image)
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
        def render_image(self, prompt, *, aspect="1:1", reference_images=()):
            prompts.append(prompt)
            return super().render_image(prompt, aspect=aspect)

    _studio(tmp_path, StubQA(flags=1), provider=Recording()).run(SPEC)

    assert len(prompts) == 2
    assert "illegible" in prompts[1]
    assert "illegible" not in prompts[0]


def test_a_render_failure_propagates(tmp_path):
    class Broken(DemoMediaProvider):
        def render_image(self, prompt, *, aspect="1:1", reference_images=()):
            raise RenderError("vendor is down")

    with pytest.raises(RenderError, match="vendor is down"):
        _studio(tmp_path, StubQA(), provider=Broken()).run(SPEC)


def test_events_narrate_the_run(tmp_path):
    seen = []
    _studio(tmp_path, StubQA(flags=1)).run(SPEC, sink=seen.append)

    agents = [event.agent for event in seen]
    assert "renderer" in agents
    assert "vision_qa" in agents


PRODUCT = b"\x89PNG\r\n\x1a\nnot-a-real-photo"


class RecordingProvider(DemoMediaProvider):
    """Captures what the studio actually asked the image model for."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def render_image(self, prompt, *, aspect="1:1", reference_images=()):
        self.calls.append({"prompt": prompt, "reference_images": reference_images})
        return super().render_image(prompt, aspect=aspect)


LOCKED = VariantSpec(
    variant_id=7,
    headline="Raya Deals",
    cta="Shop now",
    brief=BRIEF,
    product_image=PRODUCT,
)


def test_the_product_photo_is_sent_to_the_image_model(tmp_path):
    """The whole point of product lock: the model composes *with* the real
    photo. Pasting it on afterwards is what made creatives look like a
    screenshot dropped into an ad."""
    provider = RecordingProvider()
    _studio(tmp_path, StubQA(), provider=provider).run(LOCKED)

    assert provider.calls[0]["reference_images"] == (PRODUCT,)


def test_a_render_without_product_lock_sends_no_reference(tmp_path):
    provider = RecordingProvider()
    _studio(tmp_path, StubQA(), provider=provider).run(SPEC)

    assert provider.calls[0]["reference_images"] == ()


def test_the_prompt_asks_for_the_product_rather_than_forbidding_it(tmp_path):
    provider = RecordingProvider()
    _studio(tmp_path, StubQA(), provider=provider).run(LOCKED)

    prompt = provider.calls[0]["prompt"]
    assert "never draw packaging" not in prompt.lower()
    assert "attached product photo" in prompt.lower()


def test_a_redo_still_carries_the_product_photo(tmp_path):
    provider = RecordingProvider()
    _studio(tmp_path, StubQA(flags=1), provider=provider).run(LOCKED)

    assert [call["reference_images"] for call in provider.calls] == [(PRODUCT,), (PRODUCT,)]


def test_qa_is_given_the_source_photo_to_check_the_product_against(tmp_path):
    qa = StubQA()
    _studio(tmp_path, qa, provider=RecordingProvider()).run(LOCKED)

    assert qa.product_images == [PRODUCT]
