import io

import pytest
from PIL import Image

from app.media.compose import ZONES, compose_creative, pick_text_colour, resolve_font


def _solid(colour, size=(1024, 1024)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


def test_returns_a_png_of_the_requested_shape():
    out = compose_creative(
        _solid((30, 30, 30)), headline="Raya Deals", cta="Shop now", zone="top-left"
    )
    image = Image.open(io.BytesIO(out))
    assert image.format == "PNG"
    assert image.size == (1024, 1024)


def test_changes_pixels_inside_the_chosen_zone():
    background = _solid((30, 30, 30))
    out = compose_creative(background, headline="Raya Deals", cta="Shop now", zone="top-left")
    before = Image.open(io.BytesIO(background)).convert("RGB")
    after = Image.open(io.BytesIO(out)).convert("RGB")

    left, top, right, bottom = ZONES["top-left"]
    box = (int(left * 1024), int(top * 1024), int(right * 1024), int(bottom * 1024))
    assert before.crop(box).tobytes() != after.crop(box).tobytes()


def test_leaves_the_opposite_zone_alone():
    background = _solid((30, 30, 30))
    out = compose_creative(background, headline="Raya Deals", cta="Shop now", zone="top-left")
    before = Image.open(io.BytesIO(background)).convert("RGB")
    after = Image.open(io.BytesIO(out)).convert("RGB")

    assert before.crop((820, 820, 1024, 1024)).tobytes() == after.crop(
        (820, 820, 1024, 1024)
    ).tobytes()


def test_dark_background_gets_light_text():
    assert pick_text_colour(Image.new("RGB", (10, 10), (10, 10, 10))) == (255, 255, 255)


def test_light_background_gets_dark_text():
    assert pick_text_colour(Image.new("RGB", (10, 10), (245, 245, 245))) == (17, 17, 17)


def test_rejects_a_zone_outside_the_grid():
    with pytest.raises(ValueError, match="unknown placement zone"):
        compose_creative(_solid((30, 30, 30)), headline="h", cta="c", zone="nowhere")


def test_resizes_a_background_that_arrives_at_the_wrong_shape():
    out = compose_creative(
        _solid((30, 30, 30), size=(640, 480)),
        headline="Raya Deals",
        cta="Shop now",
        zone="mid-center",
    )
    assert Image.open(io.BytesIO(out)).size == (1024, 1024)


def test_a_very_long_headline_still_fits_the_frame():
    out = compose_creative(
        _solid((30, 30, 30)),
        headline="A headline so long it could not possibly fit on one line " * 3,
        cta="Shop now",
        zone="bottom-center",
    )
    assert Image.open(io.BytesIO(out)).size == (1024, 1024)


def test_resolve_font_always_returns_something_drawable():
    assert resolve_font(48, bold=True) is not None
