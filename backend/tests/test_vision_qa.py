import pytest

from app.agents.vision_qa import QAVerdict, VisionQA
from app.domain import VisualBrief

PNG = b"\x89PNG\r\n\x1a\nfake"

BRIEF = VisualBrief(
    composition_notes="subject left of centre",
    image_prompt="a warung at golden hour",
    text_placement="headline upper left",
    placement_zone="top-left",
)


class StubProvider:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []

    def structured(self, *, system, prompt, schema, images=None):
        self.calls.append({"system": system, "prompt": prompt, "images": images})
        return schema(**self.verdict)


def test_passes_a_clean_asset():
    provider = StubProvider({"status": "passed", "notes": ""})
    verdict = VisionQA(provider=provider).review(
        PNG, headline="Raya Deals", cta="Shop now", brief=BRIEF
    )
    assert verdict.status == "passed"


def test_sends_the_image_to_the_model():
    provider = StubProvider({"status": "passed", "notes": ""})
    VisionQA(provider=provider).review(PNG, headline="h", cta="c", brief=BRIEF)
    assert provider.calls[0]["images"] == [PNG]


def test_prompt_carries_the_words_that_were_composited():
    provider = StubProvider({"status": "passed", "notes": ""})
    VisionQA(provider=provider).review(
        PNG, headline="Raya Deals", cta="Shop now", brief=BRIEF
    )
    prompt = provider.calls[0]["prompt"]
    assert "Raya Deals" in prompt
    assert "Shop now" in prompt
    assert "top-left" in prompt


def test_flagged_verdict_carries_its_notes():
    provider = StubProvider(
        {"status": "flagged", "notes": "headline is illegible against the sky"}
    )
    verdict = VisionQA(provider=provider).review(
        PNG, headline="h", cta="c", brief=BRIEF
    )
    assert verdict.status == "flagged"
    assert "illegible" in verdict.notes


def test_a_provider_that_cannot_see_degrades_to_flagged_rather_than_raising():
    class Blind:
        def structured(self, *, system, prompt, schema, images=None):
            raise TypeError("this provider does not accept images")

    verdict = VisionQA(provider=Blind()).review(
        PNG, headline="h", cta="c", brief=BRIEF
    )
    assert verdict.status == "flagged"
    assert "could not be checked" in verdict.notes


def test_standing_note_is_appended_to_the_system_prompt():
    provider = StubProvider({"status": "passed", "notes": ""})
    VisionQA(provider=provider, standing_note="be strict about hands").review(
        PNG, headline="h", cta="c", brief=BRIEF
    )
    assert "be strict about hands" in provider.calls[0]["system"]


PRODUCT = b"\x89PNG\r\n\x1a\nproduct"


def test_the_source_photo_is_attached_alongside_the_creative():
    """QA cannot judge product fidelity without seeing what the product was."""
    provider = StubProvider({"status": "passed", "notes": ""})
    VisionQA(provider=provider).review(
        PNG, headline="h", cta="c", brief=BRIEF, product_image=PRODUCT
    )
    assert provider.calls[0]["images"] == [PNG, PRODUCT]


def test_the_prompt_asks_about_product_fidelity_only_when_locked():
    provider = StubProvider({"status": "passed", "notes": ""})
    qa = VisionQA(provider=provider)

    qa.review(PNG, headline="h", cta="c", brief=BRIEF, product_image=PRODUCT)
    qa.review(PNG, headline="h", cta="c", brief=BRIEF)

    assert "second attached image" in provider.calls[0]["prompt"].lower()
    assert "second attached image" not in provider.calls[1]["prompt"].lower()
