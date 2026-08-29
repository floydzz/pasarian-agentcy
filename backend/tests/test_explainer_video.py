import io

import pytest
from PIL import Image

from app.agents.demo_video import DemoVideoSpec, DemoVideoStudio
from app.agents.vision_qa import QAVerdict
from app.media.base import RenderError
from app.media.storage import AssetStorage
from app.video import (
    ExplainerRenderer,
    ExplainerScript,
    MarketingVideoScene,
    MarketingVideoScript,
    RenderedExplainer,
)


def test_storyboard_makes_a_vertical_poster_and_six_scenes(monkeypatch):
    renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
    monkeypatch.setattr(renderer, "_encode", lambda scenes, backdrops=None: b"real-mp4-bytes")

    result = renderer.render(
        ExplainerScript(
            title="Marketing at the speed of ideas",
            strapline="Agentcy runs the workflow.",
            cta="Open Agentcy",
        )
    )

    poster = Image.open(io.BytesIO(result.poster))
    assert poster.format == "PNG"
    assert poster.size == (720, 1280)
    assert result.video == b"real-mp4-bytes"
    assert result.scene_count == 6
    assert result.duration_seconds == 18


def test_renderer_explains_when_ffmpeg_is_not_available():
    renderer = ExplainerRenderer(ffmpeg_binary=None)
    renderer.ffmpeg_binary = None

    with pytest.raises(RenderError, match="needs FFmpeg"):
        renderer._encode([])


def test_renderer_accepts_an_arbitrary_marketing_storyboard(monkeypatch):
    renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
    monkeypatch.setattr(renderer, "_encode", lambda scenes, backdrops=None: b"dynamic-mp4")

    result = renderer.render(
        MarketingVideoScript(
            brand_name="Kawan Kopi",
            product_name="Rumah Blend",
            target_audience="Home coffee brewers in Kuala Lumpur",
            cta="Try Rumah Blend",
            scenes=[
                MarketingVideoScene("Meet the blend", "Coffee that starts at home", "Freshly roasted for the daily cup.", "hero"),
                MarketingVideoScene("What makes it different", "Built for the way you brew", "Chocolatey, balanced and approachable.", "feature"),
                MarketingVideoScene("Your next cup", "Bring better coffee home", "Start with the blend made for your routine.", "cta"),
            ],
        )
    )

    assert result.video == b"dynamic-mp4"
    assert result.scene_count == 3
    assert result.duration_seconds == 9
    assert Image.open(io.BytesIO(result.poster)).size == (720, 1280)


class PassingQA:
    def review(self, image, *, headline, cta, brief, product_image=None):
        return QAVerdict(status="passed", notes="")


class StubRenderer:
    def render(self, script, *, backdrops=None):
        image = Image.new("RGB", (720, 1280), "navy")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return RenderedExplainer(
            video=b"\x00\x00\x00\x18ftypmp42", poster=buffer.getvalue(), duration_seconds=18, scene_count=6
        )


def test_demo_video_studio_saves_an_mp4_and_review_poster(tmp_path):
    storage = AssetStorage(tmp_path)
    studio = DemoVideoStudio(renderer=StubRenderer(), qa=PassingQA(), storage=storage)

    video = studio.run(
        DemoVideoSpec(
            title="Marketing at the speed of ideas",
            strapline="Agentcy runs the workflow.",
            cta="Open Agentcy",
        )
    )

    assert video.media_url.endswith(".mp4")
    assert video.poster_url.endswith(".png")
    assert storage.read(video.media_url).startswith(b"\x00\x00\x00\x18ftyp")
    assert Image.open(io.BytesIO(storage.read(video.poster_url))).size == (720, 1280)
    assert video.qa_status == "passed"


# -- generative b-roll -------------------------------------------------------

from app.video.explainer import HEIGHT, WIDTH


def _script(scenes=2):
    return MarketingVideoScript(
        brand_name="Kawan Kopi",
        product_name="Rumah Blend",
        target_audience="Home brewers",
        cta="Try Rumah Blend",
        scenes=[
            MarketingVideoScene(f"Beat {i}", f"Headline {i}", "Body copy.", "feature")
            for i in range(scenes)
        ],
    )


class TestCaptionLayer:
    """With b-roll behind them the captions must be drawn on transparency,
    or the scene's own background would hide the video entirely."""

    def test_a_scene_over_video_is_rgba(self):
        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        scene = renderer._marketing_scene(_script(), _script().scenes[0], 0, 1,
                                          over_video=True)
        assert scene.mode == "RGBA"

    def test_a_scene_over_video_lets_the_backdrop_through(self):
        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        scene = renderer._marketing_scene(_script(), _script().scenes[0], 0, 1,
                                          over_video=True)
        # Panels and product UI stay deliberately opaque; what has to show
        # through is the background around them, or there was no point
        # generating a backdrop at all.
        alpha = list(scene.getchannel("A").get_flattened_data())
        translucent = sum(1 for a in alpha if a < 200) / len(alpha)
        assert translucent > 0.4, f"only {translucent:.0%} of the frame is see-through"

    def test_the_ordinary_scene_is_still_opaque(self):
        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        scene = renderer._marketing_scene(_script(), _script().scenes[0], 0, 1)
        assert scene.mode == "RGB"


class TestBrollFiltergraph:
    def _graph(self, count=2):
        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        return renderer._broll_filtergraph(count)

    def test_it_overlays_the_captions_on_the_clip(self):
        assert "overlay" in self._graph()

    def test_it_fills_the_frame_by_cropping_not_padding(self):
        """Padding a 16:9 clip into a 9:16 frame leaves black bars behind the
        captions; cropping fills it."""
        graph = self._graph()
        assert "force_original_aspect_ratio=increase" in graph
        assert f"crop={WIDTH}:{HEIGHT}" in graph
        assert "pad=" not in graph

    def test_it_concatenates_every_scene(self):
        assert "concat=n=3:v=1:a=0" in self._graph(3)

    def test_each_scene_pairs_a_clip_input_with_a_caption_input(self):
        graph = self._graph(2)
        # clips are inputs 0 and 2, captions 1 and 3
        for index in range(4):
            assert f"[{index}:v]" in graph


class TestRenderWithBackdrops:
    def test_backdrops_reach_the_encoder(self, monkeypatch):
        seen = {}

        def fake_encode(scenes, backdrops=None):
            seen["backdrops"] = backdrops
            seen["modes"] = [s.mode for s in scenes]
            return b"mp4"

        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        monkeypatch.setattr(renderer, "_encode", fake_encode)
        monkeypatch.setattr(renderer, "_poster_from_video", lambda v: b"poster-png")

        result = renderer.render(_script(2), backdrops=[b"clip-a", b"clip-b"])

        assert seen["backdrops"] == [b"clip-a", b"clip-b"]
        assert seen["modes"] == ["RGBA", "RGBA"]
        assert result.poster == b"poster-png"

    def test_the_poster_comes_from_the_finished_video_not_the_caption_layer(
        self, monkeypatch
    ):
        """A transparent caption layer saved as a poster is a mostly-empty
        PNG, and the QA pass would be judging nothing."""
        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        monkeypatch.setattr(renderer, "_encode", lambda scenes, backdrops=None: b"mp4")
        monkeypatch.setattr(
            renderer, "_poster_from_video", lambda video: b"frame-from-" + video
        )
        result = renderer.render(_script(2), backdrops=[b"a", b"b"])
        assert result.poster == b"frame-from-mp4"

    def test_without_backdrops_nothing_about_the_old_path_changes(self, monkeypatch):
        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        monkeypatch.setattr(renderer, "_encode", lambda scenes, backdrops=None: b"mp4")
        result = renderer.render(_script(2))
        poster = Image.open(io.BytesIO(result.poster))
        assert poster.size == (WIDTH, HEIGHT)
        assert result.scene_count == 2

    def test_a_backdrop_per_scene_is_required(self, monkeypatch):
        renderer = ExplainerRenderer(ffmpeg_binary="ffmpeg")
        monkeypatch.setattr(renderer, "_encode", lambda scenes, backdrops=None: b"mp4")
        with pytest.raises(RenderError, match="one clip per scene"):
            renderer.render(_script(3), backdrops=[b"only-one"])


# -- the studio's b-roll decision --------------------------------------------

from app.agents.video_studio import MarketingVideoSpec, VideoStudio


class _Renderer:
    def __init__(self):
        self.backdrops = "not-called"

    def render(self, script, *, backdrops=None):
        self.backdrops = backdrops
        return RenderedExplainer(b"mp4", b"png", 6, len(script.scenes))


class _QA:
    def review(self, *a, **k):
        return QAVerdict(status="passed", notes="")


class _Storage:
    def save(self, data, *, suffix):
        return f"/media/x{suffix}"

    def path_for(self, url):
        raise AssertionError("not reached")


def _spec(**over):
    base = dict(
        name="Kawan Kopi launch", profile="product_launch", brand_name="Kawan Kopi",
        product_name="Rumah Blend", target_audience="Home brewers", cta="Try it",
        storyboard=[
            MarketingVideoScene("Beat one", "Headline", "Body.", "hero"),
            MarketingVideoScene("Beat two", "Headline", "Body.", "cta"),
        ],
    )
    base.update(over)
    return MarketingVideoSpec(**base)


class _Broll:
    def __init__(self, error=None):
        self.error = error
        self.prompts = []

    def render_clip(self, prompt, *, aspect="9:16", seconds=3):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return b"clip"


def _studio(broll=None, **kw):
    return VideoStudio(renderer=_Renderer(), qa=_QA(), storage=_Storage(),
                       broll=broll, **kw)


class TestBrollIsOptIn:
    def test_it_is_not_generated_unless_asked_for(self):
        broll = _Broll()
        studio = _studio(broll)
        studio.run(_spec(use_broll=False))
        assert broll.prompts == []
        assert studio.renderer.backdrops is None

    def test_asking_for_it_generates_one_clip_per_scene(self):
        broll = _Broll()
        studio = _studio(broll)
        studio.run(_spec(use_broll=True))
        assert len(broll.prompts) == 2
        assert studio.renderer.backdrops == [b"clip", b"clip"]

    def test_it_is_skipped_when_no_provider_is_configured(self):
        studio = _studio(None)
        studio.run(_spec(use_broll=True))
        assert studio.renderer.backdrops is None


class TestBrollDegradesRatherThanBlocks:
    def test_a_vendor_failure_still_produces_a_video(self):
        studio = _studio(_Broll(error=RenderError("quota exhausted")))
        result = studio.run(_spec(use_broll=True))
        assert studio.renderer.backdrops is None
        assert result.media_url.endswith(".mp4")

    def test_an_unexpected_exception_is_caught_too(self):
        studio = _studio(_Broll(error=ValueError("sdk blew up")))
        result = studio.run(_spec(use_broll=True))
        assert studio.renderer.backdrops is None
        assert result.media_url.endswith(".mp4")

    def test_a_storyboard_over_the_clip_limit_renders_without_broll(self):
        broll = _Broll()
        studio = _studio(broll, max_broll_clips=1)
        studio.run(_spec(use_broll=True))
        assert broll.prompts == []
        assert studio.renderer.backdrops is None


class TestBrollPrompt:
    def test_it_forbids_text_in_the_clip(self):
        prompt = VideoStudio.broll_prompt(_spec(), _spec().storyboard[0])
        for banned in ("No text", "no letters", "no words", "no logos"):
            assert banned in prompt

    def test_it_carries_the_brand_and_the_scene(self):
        prompt = VideoStudio.broll_prompt(_spec(), _spec().storyboard[0])
        assert "Kawan Kopi" in prompt
        assert "beat one" in prompt

    def test_it_never_contains_the_headline_the_renderer_will_draw(self):
        """The words are drawn by the renderer. Feeding them to the video
        model invites it to draw them too, badly, underneath."""
        prompt = VideoStudio.broll_prompt(_spec(), _spec().storyboard[0])
        assert "Headline" not in prompt


class TestTheDemoFilmOverGeneratedVideo:
    """Agentcy's own product film, composited over b-roll rather than paint.

    The marketing storyboard has been able to sit on generated video since the
    b-roll provider landed; the six-scene demo film never could, because its
    scene builders always painted an opaque background. Nothing else was
    missing — the scrim, the filtergraph and the poster-from-video path are all
    shared — so this is a wiring gap rather than a feature.
    """

    def test_its_scenes_are_transparent_when_there_is_video_behind_them(self):
        renderer = ExplainerRenderer()

        scenes = renderer._scenes(_explainer(), over_video=True)

        assert len(scenes) == 6
        assert all(scene.mode == "RGBA" for scene in scenes)

    def test_the_backdrop_shows_through_every_scene(self):
        renderer = ExplainerRenderer()

        for scene in renderer._scenes(_explainer(), over_video=True):
            # Fully opaque anywhere would mean paying for a clip nobody sees.
            assert min(scene.getchannel("A").get_flattened_data()) < 255

    def test_painted_scenes_are_still_opaque_without_backdrops(self):
        renderer = ExplainerRenderer()

        assert all(
            scene.mode == "RGB" for scene in renderer._scenes(_explainer())
        )

    def test_backdrops_reach_the_encoder_for_the_demo_film(self, monkeypatch):
        renderer = ExplainerRenderer()
        seen = {}

        def fake_encode(scenes, backdrops=None):
            seen["backdrops"] = backdrops
            seen["mode"] = scenes[0].mode
            return b"mp4"

        monkeypatch.setattr(renderer, "_encode", fake_encode)
        monkeypatch.setattr(renderer, "_poster_from_video", lambda video: b"poster")

        renderer.render(_explainer(), backdrops=[b"clip"] * 6)

        assert seen["backdrops"] == [b"clip"] * 6
        assert seen["mode"] == "RGBA"

    def test_one_clip_per_scene_is_still_required(self, monkeypatch):
        renderer = ExplainerRenderer()
        monkeypatch.setattr(renderer, "_encode", lambda scenes, backdrops=None: b"mp4")

        with pytest.raises(RenderError, match="one clip per scene"):
            renderer.render(_explainer(), backdrops=[b"only-one"])


def _explainer() -> ExplainerScript:
    return ExplainerScript(
        title="Marketing at the speed of your ideas.",
        strapline="Grounded strategy, reviewable creative.",
        cta="Build your next campaign.",
    )


class TestTheDemoFilmAsksForBroll:
    """The demo film, with a generated backdrop behind every scene.

    The film is a fixed six-scene walkthrough, so a b-roll run costs exactly
    six clips whatever the copy says. That is a real amount of money and quota,
    which is why it is opt-in per render rather than a default.

    Failure degrades rather than blocks, exactly as it does for the marketing
    studio: the painted render is a complete, shippable film, so a vendor
    outage should cost the run its backdrops and nothing else.
    """

    class Clips:
        def __init__(self, fail_on: int | None = None) -> None:
            self.prompts: list[str] = []
            self.fail_on = fail_on

        def render_clip(self, prompt: str, *, aspect: str) -> bytes:
            self.prompts.append(prompt)
            if self.fail_on is not None and len(self.prompts) == self.fail_on:
                raise RenderError("the vendor is down")
            return b"clip"

    @pytest.fixture
    def recording(self):
        """A renderer that records the backdrops it was handed."""

        class Recorder(StubRenderer):
            seen: object = "unset"

            def render(self, script, *, backdrops=None):
                Recorder.seen = backdrops
                return super().render(script)

        return Recorder

    def _studio(self, tmp_path, renderer, clips):
        return DemoVideoStudio(
            renderer=renderer(),
            qa=PassingQA(),
            storage=AssetStorage(tmp_path),
            broll=clips,
        )

    def test_it_generates_one_clip_per_scene(self, tmp_path, recording):
        clips = self.Clips()

        self._studio(tmp_path, recording, clips).run(
            DemoVideoSpec(title="T", strapline="S", cta="C", use_broll=True)
        )

        assert len(clips.prompts) == 6
        assert recording.seen == [b"clip"] * 6

    def test_each_scene_gets_its_own_prompt(self, tmp_path, recording):
        clips = self.Clips()

        self._studio(tmp_path, recording, clips).run(
            DemoVideoSpec(title="T", strapline="S", cta="C", use_broll=True)
        )

        assert len(set(clips.prompts)) == 6

    def test_the_clip_is_asked_for_without_any_lettering(self, tmp_path, recording):
        """Every word is drawn by the renderer. Generated lettering is the one
        failure the caption layer exists to avoid, and it cannot be fixed
        without paying for another clip."""
        clips = self.Clips()

        self._studio(tmp_path, recording, clips).run(
            DemoVideoSpec(title="T", strapline="S", cta="C", use_broll=True)
        )

        assert all("No text" in prompt for prompt in clips.prompts)

    def test_it_asks_for_vertical_clips(self, tmp_path, recording):
        clips = self.Clips()
        seen = []

        class Vertical(self.Clips):
            def render_clip(self, prompt, *, aspect):
                seen.append(aspect)
                return b"clip"

        self._studio(tmp_path, recording, Vertical()).run(
            DemoVideoSpec(title="T", strapline="S", cta="C", use_broll=True)
        )

        assert seen == ["9:16"] * 6

    def test_nothing_is_generated_unless_it_is_asked_for(self, tmp_path, recording):
        clips = self.Clips()

        self._studio(tmp_path, recording, clips).run(
            DemoVideoSpec(title="T", strapline="S", cta="C")
        )

        assert clips.prompts == []
        assert recording.seen is None

    def test_a_vendor_failure_costs_the_backdrops_not_the_film(
        self, tmp_path, recording
    ):
        clips = self.Clips(fail_on=3)

        video = self._studio(tmp_path, recording, clips).run(
            DemoVideoSpec(title="T", strapline="S", cta="C", use_broll=True)
        )

        assert recording.seen is None
        assert video.media_url.endswith(".mp4")
        assert video.qa_status == "passed"

    def test_asking_for_broll_without_a_provider_still_renders(
        self, tmp_path, recording
    ):
        studio = DemoVideoStudio(
            renderer=recording(), qa=PassingQA(), storage=AssetStorage(tmp_path)
        )

        video = studio.run(
            DemoVideoSpec(title="T", strapline="S", cta="C", use_broll=True)
        )

        assert recording.seen is None
        assert video.media_url.endswith(".mp4")


class TestTheFilmGetsOutOfTheFootagesWay:
    """Over video, the deck furniture goes; the words stay.

    Wiring `over_video` into `_canvas` only made the *background* transparent.
    Every panel, phone mock, agent card and page number is still painted solid
    `#131B27`, and together they cover forty to fifty per cent of the frame —
    so a film with real footage behind it still read as a slide deck with a
    video wallpaper. Observed on the first paid six-clip render, 2026-08-26.

    The furniture exists to show the product, which is worth doing on a painted
    background and not worth paying for a clip to hide behind. What survives is
    the copy — eyebrow, title, body — plus the closing call to action.
    """

    FURNITURE = (
        "_panel",
        "_phone",
        "_agent_node",
        "_creative_preview",
        "_page_number",
        "_pill",
        "_card_line",
        "_field",
        "_status",
    )

    @pytest.fixture
    def spy(self, monkeypatch):
        """Records which drawing helpers a scene actually reaches for."""
        renderer = ExplainerRenderer()
        called: list[str] = []

        for name in (*self.FURNITURE, "_button", "_eyebrow", "_title", "_body"):
            original = getattr(renderer, name)

            def record(*args, _name=name, _original=original, **kwargs):
                called.append(_name)
                return _original(*args, **kwargs)

            monkeypatch.setattr(renderer, name, record)
        return renderer, called

    def test_no_furniture_is_drawn_over_video(self, spy):
        renderer, called = spy

        renderer._scenes(_explainer(), over_video=True)

        assert [name for name in called if name in self.FURNITURE] == []

    def test_the_copy_still_is(self, spy):
        renderer, called = spy

        renderer._scenes(_explainer(), over_video=True)

        assert called.count("_eyebrow") == 6
        assert called.count("_title") == 6
        assert called.count("_body") == 6

    def test_the_closing_call_to_action_survives(self, spy):
        """A brand film that ends without asking for anything is a screensaver."""
        renderer, called = spy

        renderer._scenes(_explainer(), over_video=True)

        assert called.count("_button") == 1

    def test_the_painted_film_is_untouched(self, spy):
        """No b-roll, no change: this is still the film that renders for free."""
        renderer, called = spy

        renderer._scenes(_explainer())

        for name in ("_panel", "_phone", "_agent_node", "_creative_preview"):
            assert name in called, name
        assert called.count("_page_number") == 6


class TestCaptionsStayLegibleOverAnyFootage:
    """White type has to survive the brightest clip the model might return.

    The renderer does not choose its own backdrop and cannot re-roll a bad one
    without paying again, so legibility has to be a property of the scrim
    rather than a hope about the footage. Measured against pure white, the
    worst case: before this, body copy over a bright clip came out at luminance
    213 against text that peaks at 244 — the same colour, effectively invisible.

    The threshold is the background under the copy, not the copy itself. White
    text sits near 244, so a band mean at or below 120 keeps real contrast.
    """

    #: Where each scene puts words, in the vertical order they are drawn.
    COPY_BANDS = ((60, 100), (140, 385), (400, 620))

    def _over_white(self, scene):
        white = Image.new("RGBA", (scene.width, scene.height), "white")
        return Image.alpha_composite(white, scene).convert("L")

    def _mean(self, image, band):
        crop = image.crop((40, band[0], image.width - 40, band[1]))
        pixels = list(crop.get_flattened_data())
        return sum(pixels) / len(pixels)

    @pytest.mark.parametrize("index", range(6))
    def test_every_scene_keeps_its_copy_readable(self, index):
        renderer = ExplainerRenderer()
        scene = renderer._scenes(_explainer(), over_video=True)[index]

        flattened = self._over_white(scene)

        for band in self.COPY_BANDS:
            assert self._mean(flattened, band) <= 120, (index, band)

    def test_the_footage_is_still_visible_below_the_copy(self):
        """A scrim heavy enough to hide the clip defeats the point of buying it."""
        renderer = ExplainerRenderer()
        scene = renderer._scenes(_explainer(), over_video=True)[3]

        flattened = self._over_white(scene)

        assert self._mean(flattened, (820, 1240)) >= 150


class TestQAIsShownWhatIsActuallyOnThePoster:
    """The poster is the closing frame, so QA must be told the closing copy.

    The poster is the last scene either way — `_png(scenes[-1])` painted, the
    final video frame over b-roll — and that scene sets its headline from
    `spec.cta`, under a button reading OPEN AGENTCY. Telling QA the headline is
    `spec.title` asks it to check the frame against words that appear five
    scenes earlier. It flagged exactly that on 2026-08-27; earlier runs passed
    only because the model let the mismatch go.
    """

    class Watching:
        def __init__(self) -> None:
            self.seen: dict = {}

        def review(self, image, *, headline, cta, brief, product_image=None):
            self.seen = {"headline": headline, "cta": cta}
            return QAVerdict(status="passed", notes="")

    def test_it_is_told_the_closing_headline_not_the_opening_one(self, tmp_path):
        qa = self.Watching()
        studio = DemoVideoStudio(
            renderer=StubRenderer(), qa=qa, storage=AssetStorage(tmp_path)
        )

        studio.run(
            DemoVideoSpec(
                title="Marketing should move at the speed of your ideas.",
                strapline="S",
                cta="Build your next campaign with Agentcy.",
            )
        )

        assert qa.seen["headline"] == "Build your next campaign with Agentcy."

    def test_it_is_told_the_button_the_closing_frame_actually_shows(self, tmp_path):
        qa = self.Watching()
        studio = DemoVideoStudio(
            renderer=StubRenderer(), qa=qa, storage=AssetStorage(tmp_path)
        )

        studio.run(DemoVideoSpec(title="T", strapline="S", cta="C"))

        assert qa.seen["cta"] == "OPEN AGENTCY"


class TestAFailedBackdropSaysWhy:
    """Degrading quietly is how a bad render looks like a good one.

    Falling back to the painted film is right — it is complete and shippable.
    Saying nothing about it is not: the API returns the same 200 and the same
    shape either way, so a run that was refused outright is indistinguishable
    from one that worked. On 2026-08-27 that cost a full round trip to discover
    the vendor had answered `403 AllocationQuota.FreeTierOnly` six times.
    """

    class Refusing:
        def render_clip(self, prompt, *, aspect="9:16", seconds=3):
            raise RenderError("403 the free quota has been exhausted")

    def test_the_reason_is_logged(self, tmp_path, caplog):
        studio = DemoVideoStudio(
            renderer=StubRenderer(),
            qa=PassingQA(),
            storage=AssetStorage(tmp_path),
            broll=self.Refusing(),
        )

        with caplog.at_level("WARNING"):
            studio.run(DemoVideoSpec(title="T", strapline="S", cta="C", use_broll=True))

        assert "quota" in caplog.text
