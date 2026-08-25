# Image Pipeline (Phase 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take a director-reviewed variant and produce a finished image ad creative — generated background, composited headline and CTA, automated vision QA, and a human review gate — end to end, offline in `demo` mode and against DashScope with a key.

**Architecture:** A second LangGraph (`Studio`) runs after variants are persisted, on its own route with its own run kind, because renders take minutes and the crew must keep returning in seconds. Text is composited with Pillow rather than drawn by the image model, so legibility never depends on the vendor. A bounded redo loop mirrors the director's revision loop exactly.

**Tech Stack:** FastAPI · SQLAlchemy · LangGraph · Pillow · httpx · DashScope Wanx (async task API) · React/TypeScript

**Spec:** `docs/superpowers/specs/2026-08-24-asset-generation-design.md`

## Global Constraints

- Python `>=3.13`; every new module starts with `from __future__ import annotations`.
- Every LLM call is schema-constrained. No agent parses free text (`plan:60`).
- Every loop is bounded. `MAX_REDOS = 2`, matching `MAX_REVISIONS` at `crew.py:31`.
- `media_provider` defaults to `demo`. `docker compose up` with no keys must run the whole pipeline and bill nothing.
- Demo-provider output is stamped `[demo]` so it can never be mistaken for a model's work.
- Tests never touch the network (`README:113`). DashScope is exercised through a stubbed `httpx` transport.
- Existing patterns win: providers demand their key in `__init__`, agents take `provider=` and `standing_note=`, routes come in a plain twin and a `/stream` twin.
- `filterwarnings = ["error::DeprecationWarning:app.*"]` is set — a deprecation warning from `app.*` fails the suite.

---

### Task 1: Media provider foundation

**Files:**
- Create: `backend/app/media/__init__.py`, `backend/app/media/base.py`, `backend/app/media/demo.py`
- Modify: `backend/pyproject.toml:5-17`
- Test: `backend/tests/test_media_providers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `MediaProvider` (ABC, `render_image(prompt, *, aspect="1:1") -> bytes`), `RenderError`, `DemoMediaProvider`, `get_media_provider(name, *, api_key, image_model=None, timeout_seconds=120) -> MediaProvider`, `MEDIA_PROVIDERS: dict[str, type[MediaProvider]]`.

- [ ] **Step 1: Add Pillow to dependencies**

In `backend/pyproject.toml`, add to the `dependencies` list after `"httpx>=0.27",`:

```toml
    "pillow>=11.0",
```

Then install: `cd backend && ../.venv/bin/pip install -e .`

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_media_providers.py`:

```python
import io

import pytest
from PIL import Image

from app.media import MEDIA_PROVIDERS, get_media_provider
from app.media.base import MediaProvider, RenderError
from app.media.demo import DemoMediaProvider


def test_demo_provider_returns_a_decodable_png():
    provider = DemoMediaProvider()
    data = provider.render_image("a warung at golden hour")
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    assert image.size == (1024, 1024)


def test_demo_provider_is_deterministic_for_the_same_prompt():
    provider = DemoMediaProvider()
    assert provider.render_image("same") == provider.render_image("same")


def test_demo_provider_differs_across_prompts():
    provider = DemoMediaProvider()
    assert provider.render_image("one") != provider.render_image("two")


def test_demo_provider_honours_aspect():
    provider = DemoMediaProvider()
    assert Image.open(io.BytesIO(provider.render_image("x", aspect="9:16"))).size == (720, 1280)


def test_demo_provider_needs_no_key():
    assert DemoMediaProvider().api_key == "demo"


def test_registry_resolves_demo():
    assert isinstance(get_media_provider("demo", api_key="demo"), DemoMediaProvider)


def test_registry_names_the_supported_providers_when_asked_for_a_bad_one():
    with pytest.raises(ValueError, match="unknown media provider"):
        get_media_provider("midjourney", api_key="x")


def test_registry_covers_every_declared_provider():
    for name in MEDIA_PROVIDERS:
        assert issubclass(MEDIA_PROVIDERS[name], MediaProvider)


def test_render_error_is_a_runtime_error():
    assert issubclass(RenderError, RuntimeError)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_media_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.media'`

- [ ] **Step 4: Write the ABC**

Create `backend/app/media/base.py`:

```python
"""Provider-neutral image and video rendering.

Mirrors `app.llm.base` on purpose: one abstract class, one registry, one
offline provider, so swapping the vendor is an environment change rather than
an edit to any agent. The plan's risk register calls the media vendor landscape
unreliable, and this is the seam that makes that survivable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

#: Longest a single render may take before it is abandoned. A demo must never
#: hang on a vendor — the same rule the crew follows for agents.
DEFAULT_TIMEOUT_SECONDS = 120

#: Frame shapes the pipeline renders. A channel convention, not a model choice.
ASPECTS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "9:16": (720, 1280),
    "16:9": (1280, 720),
}


class RenderError(RuntimeError):
    """A media provider could not produce a usable asset."""


class MediaProvider(ABC):
    """One prompt in, image bytes out."""

    #: Providers reached over HTTP override this with their API root.
    base_url: str | None = None

    def __init__(
        self,
        *,
        api_key: str,
        image_model: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError(
                f"{type(self).__name__} needs an API key — set the matching "
                "key in .env before rendering"
            )
        self.api_key = api_key
        self.image_model = image_model or self.default_image_model
        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def default_image_model(self) -> str: ...

    @abstractmethod
    def render_image(self, prompt: str, *, aspect: str = "1:1") -> bytes:
        """PNG or JPEG bytes for `prompt`. Raises `RenderError` on failure."""

    @staticmethod
    def size_for(aspect: str) -> tuple[int, int]:
        try:
            return ASPECTS[aspect]
        except KeyError:
            raise RenderError(
                f"unsupported aspect {aspect!r} — supported: "
                f"{', '.join(sorted(ASPECTS))}"
            ) from None
```

- [ ] **Step 5: Write the demo provider**

Create `backend/app/media/demo.py`:

```python
"""An offline image provider for rehearsing the pipeline. Not a model.

Renders a deterministic placeholder from the prompt's own hash, so a rehearsal
looks the same every time it is run and two different briefs never produce the
same picture. Every frame says `[demo]` on it: nothing this returns should ever
reach a deck by accident.
"""

from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageDraw

from .base import MediaProvider


class DemoMediaProvider(MediaProvider):
    def __init__(
        self,
        *,
        api_key: str = "demo",
        image_model: str | None = None,
        timeout_seconds: int = 5,
    ) -> None:
        # Deliberately not calling super(): this provider has no key to demand.
        self.api_key = api_key
        self.image_model = image_model or self.default_image_model
        self.timeout_seconds = timeout_seconds

    @property
    def default_image_model(self) -> str:
        return "demo-offline"

    def render_image(self, prompt: str, *, aspect: str = "1:1") -> bytes:
        width, height = self.size_for(aspect)
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()

        # Two hues from the digest, so the gradient is stable per prompt.
        top = (digest[0], digest[1], digest[2])
        bottom = (digest[3], digest[4], digest[5])

        image = Image.new("RGB", (width, height), top)
        draw = ImageDraw.Draw(image)
        for y in range(height):
            blend = y / max(height - 1, 1)
            draw.line(
                [(0, y), (width, y)],
                fill=tuple(
                    round(top[channel] + (bottom[channel] - top[channel]) * blend)
                    for channel in range(3)
                ),
            )

        draw.text((24, 24), "[demo]", fill=(255, 255, 255))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
```

- [ ] **Step 6: Write the registry**

Create `backend/app/media/__init__.py`:

```python
"""Media provider registry — swap vendors without touching the studio."""

from __future__ import annotations

from .base import ASPECTS, MediaProvider, RenderError
from .demo import DemoMediaProvider

MEDIA_PROVIDERS: dict[str, type[MediaProvider]] = {
    # Offline rehearsal — see app/media/demo.py. Not a model.
    "demo": DemoMediaProvider,
}


def get_media_provider(
    name: str,
    *,
    api_key: str,
    image_model: str | None = None,
    timeout_seconds: int = 120,
) -> MediaProvider:
    try:
        provider_cls = MEDIA_PROVIDERS[name.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown media provider {name!r} — supported: "
            f"{', '.join(sorted(MEDIA_PROVIDERS))}"
        ) from None
    return provider_cls(
        api_key=api_key, image_model=image_model, timeout_seconds=timeout_seconds
    )


__all__ = [
    "ASPECTS",
    "MediaProvider",
    "RenderError",
    "DemoMediaProvider",
    "MEDIA_PROVIDERS",
    "get_media_provider",
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_media_providers.py -v`
Expected: 9 passed

- [ ] **Step 8: Commit**

```bash
git add backend/app/media backend/tests/test_media_providers.py backend/pyproject.toml
git commit -m "feat(media): provider ABC, offline demo provider, registry"
```

---

### Task 2: DashScope image provider

**Files:**
- Create: `backend/app/media/dashscope.py`
- Modify: `backend/app/media/__init__.py` (register it)
- Test: `backend/tests/test_media_providers.py` (append)

**Interfaces:**
- Consumes: `MediaProvider`, `RenderError`, `MediaProvider.size_for` from Task 1.
- Produces: `DashScopeMediaProvider` with `base_url = "https://dashscope-intl.aliyuncs.com"`, registered under `"dashscope"`.

**Background the implementer needs:** DashScope image synthesis is *not* the OpenAI-compatible gateway `QwenProvider` uses at `openai_compatible.py:46`. It is a three-step async task API:

1. `POST /api/v1/services/aigc/text2image/image-synthesis` with header `X-DashScope-Async: enable` → `{"output": {"task_id": "..."}}`
2. `GET /api/v1/tasks/{task_id}` → `{"output": {"task_status": "PENDING|RUNNING|SUCCEEDED|FAILED", "results": [{"url": "..."}]}}`
3. `GET <result url>` → the image bytes

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_media_providers.py`:

```python
import httpx

from app.media.dashscope import DashScopeMediaProvider

IMAGE_BYTES = b"\x89PNG\r\n\x1a\nfake-but-sufficient"


def _provider(handler, **kwargs):
    provider = DashScopeMediaProvider(api_key="sk-test", **kwargs)
    provider._client_factory = lambda: httpx.Client(
        transport=httpx.MockTransport(handler), base_url=provider.base_url
    )
    return provider


def test_submits_polls_and_downloads():
    seen = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            assert request.headers["X-DashScope-Async"] == "enable"
            assert request.headers["Authorization"] == "Bearer sk-test"
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        if "/tasks/" in request.url.path:
            seen["polls"] += 1
            if seen["polls"] < 2:
                return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "results": [{"url": "https://cdn.example/out.png"}],
                    }
                },
            )
        return httpx.Response(200, content=IMAGE_BYTES)

    provider = _provider(handler, poll_interval_seconds=0)
    assert provider.render_image("a warung at golden hour") == IMAGE_BYTES
    assert seen["polls"] == 2


def test_sends_the_size_matching_the_aspect():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        if "/tasks/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "results": [{"url": "https://cdn.example/out.png"}],
                    }
                },
            )
        return httpx.Response(200, content=IMAGE_BYTES)

    provider = _provider(handler, poll_interval_seconds=0)
    provider.render_image("x", aspect="9:16")
    assert captured["parameters"]["size"] == "720*1280"


def test_failed_task_raises_render_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        return httpx.Response(
            200,
            json={"output": {"task_status": "FAILED", "message": "content rejected"}},
        )

    provider = _provider(handler, poll_interval_seconds=0)
    with pytest.raises(RenderError, match="content rejected"):
        provider.render_image("x")


def test_timeout_raises_render_error_rather_than_polling_forever():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    provider = _provider(handler, poll_interval_seconds=0, timeout_seconds=0)
    with pytest.raises(RenderError, match="did not finish"):
        provider.render_image("x")


def test_http_error_on_submit_raises_render_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})

    provider = _provider(handler, poll_interval_seconds=0)
    with pytest.raises(RenderError):
        provider.render_image("x")


def test_dashscope_demands_a_key():
    with pytest.raises(ValueError, match="needs an API key"):
        DashScopeMediaProvider(api_key="")
```

Add `import json` to the imports at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_media_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.media.dashscope'`

- [ ] **Step 3: Write the provider**

Create `backend/app/media/dashscope.py`:

```python
"""Alibaba DashScope image synthesis.

Not the OpenAI-compatible gateway `QwenProvider` uses — image synthesis is a
native async task API. Submit, poll, download. The polling loop is bounded by
`timeout_seconds` and gives up with a `RenderError`, because the studio's
resume logic can pick a variant back up later but a hung request during a demo
has nowhere to go.
"""

from __future__ import annotations

import time

import httpx

from .base import MediaProvider, RenderError

SUBMIT_PATH = "/api/v1/services/aigc/text2image/image-synthesis"
TASK_PATH = "/api/v1/tasks/{task_id}"

#: Terminal task states, per DashScope.
DONE = "SUCCEEDED"
FAILED = {"FAILED", "CANCELED", "UNKNOWN"}


class DashScopeMediaProvider(MediaProvider):
    base_url = "https://dashscope-intl.aliyuncs.com"

    def __init__(self, *, poll_interval_seconds: float = 2.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.poll_interval_seconds = poll_interval_seconds

    @property
    def default_image_model(self) -> str:
        return "wanx2.1-t2i-turbo"

    # Overridden in tests to inject a MockTransport.
    def _client_factory(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=30.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def render_image(self, prompt: str, *, aspect: str = "1:1") -> bytes:
        width, height = self.size_for(aspect)
        with self._client_factory() as client:
            task_id = self._submit(client, prompt, f"{width}*{height}")
            url = self._await_result(client, task_id)
            return self._download(client, url)

    # -- steps -------------------------------------------------------------

    def _submit(self, client: httpx.Client, prompt: str, size: str) -> str:
        response = self._json(
            client.post(
                SUBMIT_PATH,
                headers={**self._headers, "X-DashScope-Async": "enable"},
                json={
                    "model": self.image_model,
                    "input": {"prompt": prompt},
                    "parameters": {"size": size, "n": 1},
                },
            )
        )
        task_id = response.get("output", {}).get("task_id")
        if not task_id:
            raise RenderError(f"DashScope accepted the job but named no task: {response}")
        return task_id

    def _await_result(self, client: httpx.Client, task_id: str) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            output = self._json(
                client.get(TASK_PATH.format(task_id=task_id), headers=self._headers)
            ).get("output", {})
            state = output.get("task_status", "")

            if state == DONE:
                results = output.get("results") or []
                url = results[0].get("url") if results else None
                if not url:
                    raise RenderError("DashScope reported success but returned no image")
                return url

            if state in FAILED:
                reason = output.get("message") or state
                raise RenderError(f"DashScope could not render this prompt: {reason}")

            if time.monotonic() >= deadline:
                raise RenderError(
                    f"DashScope did not finish task {task_id} within "
                    f"{self.timeout_seconds}s — abandoning it"
                )
            time.sleep(self.poll_interval_seconds)

    def _download(self, client: httpx.Client, url: str) -> bytes:
        response = client.get(url)
        if response.status_code >= 400:
            raise RenderError(f"could not download the rendered image: {response.status_code}")
        return response.content

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise RenderError(
                f"DashScope refused the request ({response.status_code}): {response.text}"
            )
        return response.json()
```

- [ ] **Step 4: Register it**

In `backend/app/media/__init__.py`, add the import and the registry entry:

```python
from .dashscope import DashScopeMediaProvider

MEDIA_PROVIDERS: dict[str, type[MediaProvider]] = {
    "dashscope": DashScopeMediaProvider,
    # Offline rehearsal — see app/media/demo.py. Not a model.
    "demo": DemoMediaProvider,
}
```

Add `"DashScopeMediaProvider"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_media_providers.py -v`
Expected: 15 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/media backend/tests/test_media_providers.py
git commit -m "feat(media): DashScope image synthesis over the async task API"
```

---

### Task 3: `placement_zone` on the visual brief

**Files:**
- Modify: `backend/app/domain.py:89-92`, `backend/app/agents/visual_planner.py:18-47`, `backend/app/llm/demo.py:128-151`
- Test: `backend/tests/test_domain.py` (append), `backend/tests/test_crew_agents.py` (update)

**Interfaces:**
- Consumes: nothing.
- Produces: `PlacementZone` literal type and `VisualBrief.placement_zone` / `VisualDraft.placement_zone`, both required, consumed by the compositor in Task 4.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_domain.py`:

```python
import pytest
from pydantic import ValidationError

from app.domain import VisualBrief


def test_visual_brief_requires_a_placement_zone():
    with pytest.raises(ValidationError):
        VisualBrief(
            composition_notes="notes",
            image_prompt="prompt",
            text_placement="upper third",
        )


def test_visual_brief_rejects_a_zone_outside_the_grid():
    with pytest.raises(ValidationError):
        VisualBrief(
            composition_notes="notes",
            image_prompt="prompt",
            text_placement="upper third",
            placement_zone="upper-third",
        )


def test_visual_brief_accepts_a_grid_zone():
    brief = VisualBrief(
        composition_notes="notes",
        image_prompt="prompt",
        text_placement="upper third",
        placement_zone="top-left",
    )
    assert brief.placement_zone == "top-left"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_domain.py -v -k placement`
Expected: FAIL — `test_visual_brief_requires_a_placement_zone` fails because the model accepts the call today

- [ ] **Step 3: Add the field to the domain model**

In `backend/app/domain.py`, above `class VisualBrief`:

```python
#: Where composited text sits. A nine-cell grid rather than free text, because
#: the compositor lays out against it — prose cannot drive a layout engine.
PlacementZone = Literal[
    "top-left", "top-center", "top-right",
    "mid-left", "mid-center", "mid-right",
    "bottom-left", "bottom-center", "bottom-right",
]


class VisualBrief(BaseModel):
    composition_notes: str
    image_prompt: str
    #: Prose, and it stays prose: this is what steers the image prompt toward
    #: leaving usable negative space, which no enum expresses.
    text_placement: str
    #: The same intent as `text_placement`, in the one form Pillow can act on.
    placement_zone: PlacementZone
```

- [ ] **Step 4: Add the field to the agent's output schema**

In `backend/app/agents/visual_planner.py`, update `VisualDraft`:

```python
class VisualDraft(BaseModel):
    """One variant's image brief — mirrors `domain.VisualBrief`."""

    composition_notes: str
    image_prompt: str
    text_placement: str
    placement_zone: PlacementZone
```

Add the import: `from app.domain import Concept, PlacementZone`

Then in `SYSTEM_PROMPT`, replace the `text_placement` bullet with these two:

```
- `text_placement` says where the actual headline and call to action sit in the \
frame, naming the real words being placed.
- `placement_zone` is that same decision as one of: top-left, top-center, \
top-right, mid-left, mid-center, mid-right, bottom-left, bottom-center, \
bottom-right. It must agree with `text_placement`. The headline is composited \
onto the image afterwards at exactly this zone, so `image_prompt` must ask for \
clear, uncluttered space there — never put a face or the subject's focal point \
in the zone you chose.
```

- [ ] **Step 5: Update the offline provider**

In `backend/app/llm/demo.py`, inside `_visuals`, add a zone to each brief. Replace the `briefs.append({...})` call with:

```python
            zone = ["top-left", "bottom-left", "top-center"][index % 3]
            briefs.append(
                {
                    "composition_notes": (
                        "[demo] Subject sits left of centre; the eye lands on the face "
                        "first and the headline occupies the open space above it."
                    ),
                    "image_prompt": (
                        f"[demo] Natural-light photograph, Malaysian setting, with "
                        f"clear uncluttered space at {zone} for a headline."
                    ),
                    "text_placement": (
                        f'[demo] "{headline}" at {zone}; the call to action sits '
                        "directly beneath it."
                    ),
                    "placement_zone": zone,
                }
            )
```

Note the `image_prompt` no longer quotes the headline — the model is no longer being asked to render text, the compositor draws it.

- [ ] **Step 6: Fix the existing crew tests**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -q`

Any test constructing a `VisualDraft` or `VisualBrief` now fails on the missing field. Add `placement_zone="top-left"` to each such construction in `backend/tests/test_crew_agents.py` and `backend/tests/test_crew.py`.

- [ ] **Step 7: Run the full suite**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/domain.py backend/app/agents/visual_planner.py backend/app/llm/demo.py backend/tests/
git commit -m "feat(visual-planner): structured placement_zone driving the compositor"
```

---

### Task 4: The compositor

**Files:**
- Create: `backend/app/media/compose.py`
- Test: `backend/tests/test_compose.py`

**Interfaces:**
- Consumes: `PlacementZone` from Task 3, `ASPECTS` from Task 1.
- Produces: `compose_creative(background: bytes, *, headline: str, cta: str, zone: str, aspect: str = "1:1") -> bytes` returning PNG bytes, `pick_text_colour(region: Image.Image) -> tuple[int, int, int]`, `resolve_font(size: int, *, bold: bool) -> ImageFont.ImageFont`, and the `ZONES` grid.

The `resolve_font` return annotation is deliberately the base `ImageFont.ImageFont`, not `FreeTypeFont` — the fallback path returns Pillow's built-in, which is not a FreeType face.

**Note on fonts:** the spec said "bundle two static TTFs at `backend/data/fonts/`". That is still the preferred source, but the implementation must not *require* it — a native `pytest` run on macOS has no such directory. `resolve_font` tries, in order: any `.ttf` in `backend/data/fonts/`, then known system paths, then `ImageFont.load_default(size)`. The Docker image installs `fonts-dejavu-core` in Task 6 so the container always lands on a real face.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_compose.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_compose.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.media.compose'`

- [ ] **Step 3: Write the compositor**

Create `backend/app/media/compose.py`:

```python
"""Compositing real typography onto a generated background.

The chosen vendor is weakest exactly where the plan is strictest — legible text
in the frame (`plan:40`). So the model is never asked to draw words. It renders
a background with deliberate negative space, and the headline and CTA are drawn
here as real type at the zone the visual planner picked.

Text colour is not something an agent decides. Asking a planner to predict the
brightness of an image that does not exist yet is a guess; the rendered pixels
are ground truth, so contrast is sampled from them.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import REPO_ROOT

from .base import MediaProvider

#: The nine-cell grid as fractions of the frame: (left, top, right, bottom).
ZONES: dict[str, tuple[float, float, float, float]] = {
    "top-left": (0.06, 0.06, 0.60, 0.34),
    "top-center": (0.12, 0.06, 0.88, 0.34),
    "top-right": (0.40, 0.06, 0.94, 0.34),
    "mid-left": (0.06, 0.36, 0.60, 0.64),
    "mid-center": (0.12, 0.36, 0.88, 0.64),
    "mid-right": (0.40, 0.36, 0.94, 0.64),
    "bottom-left": (0.06, 0.66, 0.60, 0.94),
    "bottom-center": (0.12, 0.66, 0.88, 0.94),
    "bottom-right": (0.40, 0.66, 0.94, 0.94),
}

#: Preferred faces, in order. The container installs fonts-dejavu-core.
FONT_DIR = REPO_ROOT / "backend" / "data" / "fonts"
SYSTEM_FONTS = {
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
}

LIGHT_TEXT = (255, 255, 255)
DARK_TEXT = (17, 17, 17)

#: Above this mean luminance the background counts as light.
LUMINANCE_PIVOT = 140


def resolve_font(size: int, *, bold: bool) -> ImageFont.ImageFont:
    """A drawable face at `size`, whatever the host happens to have.

    Falls through to Pillow's built-in so a native test run on a machine with
    no DejaVu still composes rather than raising.
    """
    if FONT_DIR.is_dir():
        wanted = "bold" if bold else "regular"
        for candidate in sorted(FONT_DIR.glob("*.ttf")):
            if wanted in candidate.name.lower():
                return ImageFont.truetype(candidate, size=size)

    for path in SYSTEM_FONTS[bold]:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default(size=size)


def pick_text_colour(region: Image.Image) -> tuple[int, int, int]:
    """Light type on a dark region, dark type on a light one."""
    greyscale = region.convert("L")
    pixels = list(greyscale.getdata())
    mean = sum(pixels) / max(len(pixels), 1)
    return DARK_TEXT if mean > LUMINANCE_PIVOT else LIGHT_TEXT


def compose_creative(
    background: bytes,
    *,
    headline: str,
    cta: str,
    zone: str,
    aspect: str = "1:1",
) -> bytes:
    if zone not in ZONES:
        raise ValueError(
            f"unknown placement zone {zone!r} — expected one of "
            f"{', '.join(sorted(ZONES))}"
        )

    width, height = MediaProvider.size_for(aspect)
    image = Image.open(io.BytesIO(background)).convert("RGB")
    if image.size != (width, height):
        # Cover, then centre-crop: letterboxing an ad would be worse.
        image = _cover(image, width, height)

    left, top, right, bottom = ZONES[zone]
    box = (
        int(left * width),
        int(top * height),
        int(right * width),
        int(bottom * height),
    )
    colour = pick_text_colour(image.crop(box))

    # A scrim under the type, so a busy background cannot beat the contrast we
    # just measured. Drawn on its own layer to keep it translucent.
    scrim = Image.new("RGBA", image.size, (0, 0, 0, 0))
    scrim_colour = (0, 0, 0, 90) if colour == LIGHT_TEXT else (255, 255, 255, 110)
    ImageDraw.Draw(scrim).rounded_rectangle(_pad(box, 18, width, height), 24, fill=scrim_colour)
    image = Image.alpha_composite(image.convert("RGBA"), scrim).convert("RGB")

    draw = ImageDraw.Draw(image)
    box_width = box[2] - box[0]
    box_height = box[3] - box[1]

    headline_font, lines = _fit(draw, headline, box_width, int(box_height * 0.66), bold=True)
    cta_font = resolve_font(max(headline_font.size // 2, 14), bold=False)

    y = box[1]
    for line in lines:
        draw.text((box[0], y), line, font=headline_font, fill=colour)
        y += _line_height(draw, line, headline_font)

    draw.text((box[0], y + 12), cta.upper(), font=cta_font, fill=colour)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# -- helpers ---------------------------------------------------------------


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(round(image.width * scale), width), max(round(image.height * scale), height)),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _pad(box: tuple[int, int, int, int], amount: int, width: int, height: int):
    return (
        max(box[0] - amount, 0),
        max(box[1] - amount, 0),
        min(box[2] + amount, width),
        min(box[3] + amount, height),
    )


def _line_height(draw: ImageDraw.ImageDraw, line: str, font) -> int:
    top, bottom = draw.textbbox((0, 0), line or "X", font=font)[1::2]
    return int((bottom - top) * 1.35)


def _fit(draw, text: str, box_width: int, box_height: int, *, bold: bool):
    """Largest size at which `text` wraps inside the box. Never returns nothing.

    Steps down rather than solving for it: the search is a dozen iterations on
    an image that took seconds to generate, and stepping is easy to read.
    """
    size = max(box_width // 8, 16)
    while size > 12:
        font = resolve_font(size, bold=bold)
        lines = _wrap(draw, text, font, box_width)
        if sum(_line_height(draw, line, font) for line in lines) <= box_height:
            return font, lines
        size -= 4

    font = resolve_font(12, bold=bold)
    return font, _wrap(draw, text, font, box_width)


def _wrap(draw, text: str, font, box_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= box_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_compose.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/media/compose.py backend/tests/test_compose.py
git commit -m "feat(media): composite real typography at the planner's zone"
```

---

### Task 5: Asset storage

**Files:**
- Create: `backend/app/media/storage.py`
- Test: `backend/tests/test_storage.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AssetStorage(root: Path)` with `save(data: bytes, *, suffix: str = ".png") -> str` returning `/media/<uuid><suffix>`, `path_for(media_url: str) -> Path`, and `read(media_url: str) -> bytes`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_storage.py`:

```python
import pytest

from app.media.storage import MEDIA_PREFIX, AssetStorage


def test_save_returns_a_servable_url(tmp_path):
    url = AssetStorage(tmp_path).save(b"bytes")
    assert url.startswith(f"{MEDIA_PREFIX}/")
    assert url.endswith(".png")


def test_saved_bytes_come_back(tmp_path):
    storage = AssetStorage(tmp_path)
    url = storage.save(b"bytes")
    assert storage.read(url) == b"bytes"


def test_two_saves_never_collide(tmp_path):
    storage = AssetStorage(tmp_path)
    assert storage.save(b"a") != storage.save(b"b")


def test_creates_its_directory_on_demand(tmp_path):
    AssetStorage(tmp_path / "nested" / "deeper").save(b"bytes")
    assert (tmp_path / "nested" / "deeper").is_dir()


def test_refuses_a_url_outside_the_media_prefix(tmp_path):
    with pytest.raises(ValueError, match="not a media url"):
        AssetStorage(tmp_path).path_for("/etc/passwd")


def test_refuses_to_traverse_out_of_the_root(tmp_path):
    with pytest.raises(ValueError, match="not a media url"):
        AssetStorage(tmp_path).path_for(f"{MEDIA_PREFIX}/../../etc/passwd")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.media.storage'`

- [ ] **Step 3: Write the storage**

Create `backend/app/media/storage.py`:

```python
"""Where generated creatives live.

Files on a volume, not blobs in MySQL: a creative is served straight to an
`<img>` by the same origin that serves the console, and a row that has to be
decoded before it can be looked at is a row nobody looks at.
"""

from __future__ import annotations

import uuid
from pathlib import Path

#: The URL prefix these files are served under. Mounted in `app.main` before
#: the SPA catch-all, which owns `/` and would otherwise swallow it.
MEDIA_PREFIX = "/media"


class AssetStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, data: bytes, *, suffix: str = ".png") -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}{suffix}"
        (self.root / name).write_bytes(data)
        return f"{MEDIA_PREFIX}/{name}"

    def path_for(self, media_url: str) -> Path:
        if not media_url.startswith(f"{MEDIA_PREFIX}/"):
            raise ValueError(f"not a media url: {media_url!r}")

        name = media_url[len(MEDIA_PREFIX) + 1:]
        candidate = (self.root / name).resolve()
        # A stored url is generated, never user-supplied — but it reaches the
        # filesystem, so it is checked like it were.
        if not candidate.is_relative_to(self.root.resolve()):
            raise ValueError(f"not a media url: {media_url!r}")
        return candidate

    def read(self, media_url: str) -> bytes:
        return self.path_for(media_url).read_bytes()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_storage.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/media/storage.py backend/tests/test_storage.py
git commit -m "feat(media): asset storage with a served media prefix"
```

---

### Task 6: Configuration, static mount, and the container

**Files:**
- Modify: `backend/app/config.py:13-56`, `backend/app/main.py:41-79`, `docker-compose.yml:33-77`, `Dockerfile:47-70`, `.env.example`
- Test: `backend/tests/test_config.py` (append)

**Interfaces:**
- Consumes: `MEDIA_PREFIX` from Task 5.
- Produces: `Settings.media_provider`, `Settings.active_media_key`, `Settings.active_media_model`, `Settings.assets_dir`, `Settings.media_timeout_seconds`, `Settings.max_renders_per_run`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_config.py`:

```python
def test_media_provider_defaults_to_demo():
    settings = Settings(database_url="mysql+pymysql://x/y")
    assert settings.media_provider == "demo"


def test_media_reuses_the_dashscope_key():
    settings = Settings(
        database_url="mysql+pymysql://x/y",
        media_provider="dashscope",
        dashscope_api_key="sk-test",
    )
    assert settings.active_media_key == "sk-test"


def test_missing_media_key_names_its_env_var():
    settings = Settings(database_url="mysql+pymysql://x/y", media_provider="dashscope")
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        settings.active_media_key


def test_demo_media_provider_needs_no_key():
    settings = Settings(database_url="mysql+pymysql://x/y", media_provider="demo")
    assert settings.active_media_key == "demo"


def test_assets_dir_is_absolute():
    settings = Settings(database_url="mysql+pymysql://x/y")
    assert settings.assets_dir.is_absolute()
```

Ensure `pytest` and `Settings` are imported at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_config.py -v -k media`
Expected: FAIL with `AttributeError` / `ValidationError` on the unknown field

- [ ] **Step 3: Extend Settings**

In `backend/app/config.py`, add the type alias beside the others:

```python
MediaProviderName = Literal["dashscope", "demo"]
```

Add the fields after `chroma_path`:

```python
    #: Defaults to the offline provider for the same reason `llm_provider`
    #: does in compose: `docker compose up` with no keys must run the whole
    #: pipeline and bill nothing.
    media_provider: MediaProviderName = "demo"
    dashscope_image_model: str = "wanx2.1-t2i-turbo"
    demo_image_model: str = "demo-offline"

    assets_path: str = "data/assets"
    media_timeout_seconds: int = 120
    #: A runaway guard, not a normal limit — three concepts at six variants is 18.
    max_renders_per_run: int = 24
```

Add a **second** lookup table beside the existing `_KEY_FIELDS` (leave that one
untouched — it maps LLM and embedding providers, which have different names).
Media reuses the DashScope account rather than adding a second key for it:

```python
    _MEDIA_KEY_FIELDS = {
        "dashscope": ("dashscope_api_key", "DASHSCOPE_API_KEY"),
        "demo": ("demo_api_key", ""),
    }
```

And the properties, beside the embedding ones:

```python
    @property
    def active_media_key(self) -> str:
        field, env_name = self._MEDIA_KEY_FIELDS[self.media_provider]
        key = getattr(self, field)
        if not key:
            raise ValueError(
                f"{self.media_provider} is selected for media but {env_name} "
                "is empty — set it in .env"
            )
        return key

    @property
    def active_media_model(self) -> str:
        return getattr(self, f"{self.media_provider}_image_model")

    @property
    def assets_dir(self) -> Path:
        path = Path(self.assets_path)
        return path if path.is_absolute() else REPO_ROOT / "backend" / path
```

- [ ] **Step 4: Mount the media directory**

In `backend/app/main.py`, add the import:

```python
from app.config import REPO_ROOT, get_settings
from app.media.storage import MEDIA_PREFIX
```

Then, immediately after the `health` route and **before** `_mount_console(CONSOLE_DIST)`:

```python
def _mount_media() -> None:
    """Generated creatives, served from the same origin as the console.

    Registered before the SPA, which mounts at `/` and answers every unmatched
    path with index.html — a media mount added after it would never be reached.
    """
    assets = get_settings().assets_dir
    assets.mkdir(parents=True, exist_ok=True)
    app.mount(MEDIA_PREFIX, StaticFiles(directory=assets), name="media")


_mount_media()
_mount_console(CONSOLE_DIST)
```

- [ ] **Step 5: Add the volume to compose**

In `docker-compose.yml`, under the `app` service `environment:` block add:

```yaml
      MEDIA_PROVIDER: ${MEDIA_PROVIDER:-demo}
      DASHSCOPE_IMAGE_MODEL: ${DASHSCOPE_IMAGE_MODEL:-wanx2.1-t2i-turbo}
      ASSETS_PATH: /data/assets
```

Under `volumes:` for the `app` service add:

```yaml
      # Generated creatives. Persisted for the same reason the corpora are:
      # a restart must not throw away work that cost money to make.
      - agentcy_assets:/data/assets
```

And at the bottom, under the top-level `volumes:` key, add `agentcy_assets:`.

- [ ] **Step 6: Add ffmpeg-free font support to the image**

In `Dockerfile`, in the runtime stage after `FROM python:3.13-slim AS runtime`:

```dockerfile
# DejaVu is what the compositor falls back to for headline and CTA type.
# fonts-dejavu-core is ~1MB; a creative with no real face on it is worse.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
```

Update the `ENV` block to add `ASSETS_PATH=/data/assets`, and the `RUN` line to create and own it:

```dockerfile
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /data/chroma /data/assets \
    && useradd --create-home --uid 10001 agentcy \
    && chown -R agentcy:agentcy /data /app
```

- [ ] **Step 7: Document it**

In `.env.example`, after the Chroma block:

```bash
# --- Media generation: dashscope | demo ---
# `demo` renders deterministic offline placeholders — no key, no cost.
# dashscope reuses DASHSCOPE_API_KEY above; it needs no key of its own.
MEDIA_PROVIDER=demo
DASHSCOPE_IMAGE_MODEL=wanx2.1-t2i-turbo
ASSETS_PATH=data/assets
```

- [ ] **Step 8: Run the suite**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add backend/app/config.py backend/app/main.py backend/tests/test_config.py docker-compose.yml Dockerfile .env.example
git commit -m "feat(config): media provider settings, media mount, assets volume"
```

---

### Task 7: Multimodal structured calls

**Files:**
- Modify: `backend/app/llm/base.py:42-49`, `backend/app/llm/claude.py`, `backend/app/llm/openai_compatible.py:17-34`, `backend/app/llm/demo.py:45-62`, `backend/app/agents/base.py:17-20`
- Test: `backend/tests/test_llm_providers.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `LLMProvider.structured(*, system, prompt, schema, images: list[bytes] | None = None)` on every provider, and the matching widened `Provider` protocol in `app.agents.base`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_llm_providers.py`:

```python
import base64

from pydantic import BaseModel

from app.llm.openai_compatible import OpenAIProvider

PNG = b"\x89PNG\r\n\x1a\nfake"


class Verdict(BaseModel):
    status: str


def test_openai_compatible_attaches_images_as_data_uris():
    request = OpenAIProvider(api_key="sk-test").build_request(
        system="s", prompt="p", schema=Verdict, images=[PNG]
    )
    content = request["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "p"}
    assert content[1]["type"] == "image_url"
    assert base64.b64encode(PNG).decode() in content[1]["image_url"]["url"]


def test_openai_compatible_keeps_plain_text_when_no_images():
    request = OpenAIProvider(api_key="sk-test").build_request(
        system="s", prompt="p", schema=Verdict
    )
    assert request["messages"][1]["content"] == "p"


def test_demo_provider_accepts_images_and_ignores_them():
    from app.agents.vision_qa import QAVerdict
    from app.llm.demo import DemoProvider

    verdict = DemoProvider().structured(
        system="s", prompt="p", schema=QAVerdict, images=[PNG]
    )
    assert verdict.status in {"passed", "flagged"}
```

The third test imports `QAVerdict`, which Task 8 creates. Expect it to fail
until then — run only the first two in this task.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_llm_providers.py -v -k images`
Expected: FAIL with `TypeError: build_request() got an unexpected keyword argument 'images'`

- [ ] **Step 3: Widen the ABC**

In `backend/app/llm/base.py`, replace both abstract methods:

```python
    @abstractmethod
    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        """Translate a schema-constrained call into provider-specific kwargs."""

    @abstractmethod
    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        """Run the call and return a validated instance of `schema`.

        `images` is for agents that judge a picture rather than text. A provider
        that cannot accept them raises rather than silently reviewing nothing.
        """
```

- [ ] **Step 4: Implement on the OpenAI-compatible providers**

In `backend/app/llm/openai_compatible.py`, replace both methods:

```python
import base64


class OpenAICompatibleProvider(LLMProvider):
    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_completion_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": self._content(prompt, images)},
            ],
            "response_format": schema,
        }

    @staticmethod
    def _content(prompt: str, images: list[bytes] | None):
        """Plain string when there is nothing to look at — the shape the text
        agents have always sent, kept byte-identical so nothing shifts."""
        if not images:
            return prompt
        return [
            {"type": "text", "text": prompt},
            *(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(image).decode()
                    },
                }
                for image in images
            ),
        ]

    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        completion = client.chat.completions.parse(
            **self.build_request(
                system=system, prompt=prompt, schema=schema, images=images
            )
        )
        return completion.choices[0].message.parsed
```

- [ ] **Step 5: Implement on Claude**

Read `backend/app/llm/claude.py` first. Add the same `images` parameter to
`build_request` and `structured`. Claude takes images as content blocks on the
user message:

```python
    @staticmethod
    def _content(prompt: str, images: list[bytes] | None):
        if not images:
            return prompt
        return [
            *(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image).decode(),
                    },
                }
                for image in images
            ),
            {"type": "text", "text": prompt},
        ]
```

Images go *before* the text, which is what Anthropic's guidance recommends when
the text asks questions about the image.

- [ ] **Step 6: Implement on the demo provider**

In `backend/app/llm/demo.py`, add the parameter to both methods and ignore it:

```python
    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        return {"model": self.model, "system": system, "prompt": prompt,
                "schema": schema.__name__, "images": len(images or [])}

    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
```

- [ ] **Step 7: Widen the agent-facing protocol**

In `backend/app/agents/base.py`:

```python
class Provider(Protocol):
    """Whatever LLM the campaign is running on — see `app.llm`."""

    def structured(self, *, system: str, prompt: str, schema: type[BaseModel],
                   images: list[bytes] | None = None): ...
```

- [ ] **Step 8: Run the suite**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "not vision"`
Expected: all pass — the existing text agents are unaffected because `images` defaults to `None` and `_content` returns the original plain string

- [ ] **Step 9: Commit**

```bash
git add backend/app/llm backend/app/agents/base.py backend/tests/test_llm_providers.py
git commit -m "feat(llm): optional images on structured calls"
```

---

### Task 8: The vision QA agent

**Files:**
- Create: `backend/app/agents/vision_qa.py`
- Modify: `backend/app/llm/demo.py` (canned `QAVerdict`), `backend/app/agents/tuning.py` (register the agent)
- Test: `backend/tests/test_vision_qa.py`

**Interfaces:**
- Consumes: `Provider` (Task 7), `VisualBrief` (Task 3).
- Produces: `QAVerdict(status: Literal["passed","flagged"], notes: str)` and `VisionQA(provider=..., standing_note=...).review(image: bytes, *, headline: str, cta: str, brief: VisualBrief) -> QAVerdict`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_vision_qa.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_vision_qa.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.vision_qa'`

- [ ] **Step 3: Write the agent**

Create `backend/app/agents/vision_qa.py`:

```python
"""The automated QA pass that runs before a human sees a creative.

The plan puts this ahead of the review gate on purpose (`plan:43`): a reviewer's
attention is the scarcest thing in the pipeline, and spending it on an asset with
a warped hand in it is waste. QA is the machine's own first look.

It never blocks. A provider that cannot accept an image, or a model that returns
something unusable, degrades to `flagged` with a note saying so — a degraded QA
pass costs a human a look, a broken one costs the demo.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from app.agents.base import Provider, with_house_note
from app.domain import VisualBrief

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the quality checker for a Malaysian SME's marketing \
team. You are shown one finished ad creative and you decide whether a human \
should be asked to look at it.

The headline and call to action were composited onto the image after it was \
generated, so they are crisp by construction. What you are judging is whether \
they are *readable where they landed* and whether the picture underneath them \
holds up.

Flag the asset if any of these are true:
- The headline or call to action is hard to read against what sits behind it.
- The text covers the subject's face or the focal point of the image.
- The image has obvious generation artifacts — malformed hands, extra limbs, \
nonsense objects, warped faces.
- Anything in the frame contradicts the brand or would embarrass the advertiser.
- There is garbled text *in the picture itself*, separate from the composited words.

Pass it otherwise. Passing is the normal outcome; do not invent problems.

When you flag, `notes` says what is wrong in one sentence, specific enough that \
the image can be re-prompted from it. When you pass, `notes` is empty."""


class QAVerdict(BaseModel):
    """The structured output contract the provider is held to."""

    status: Literal["passed", "flagged"]
    notes: str = ""


class VisionQA:
    def __init__(self, *, provider: Provider, standing_note: str | None = None) -> None:
        self.provider = provider
        self.system = with_house_note(SYSTEM_PROMPT, standing_note)

    def review(
        self,
        image: bytes,
        *,
        headline: str,
        cta: str,
        brief: VisualBrief,
    ) -> QAVerdict:
        try:
            return self.provider.structured(
                system=self.system,
                prompt=self.build_prompt(headline=headline, cta=cta, brief=brief),
                schema=QAVerdict,
                images=[image],
            )
        except Exception as error:
            # Degrade, never block. The human still gets the asset — they just
            # get it without the machine's opinion attached.
            log.warning("vision QA could not review an asset: %s", error)
            return QAVerdict(
                status="flagged",
                notes=(
                    "This asset could not be checked automatically "
                    f"({error}). Please review it yourself."
                ),
            )

    # -- prompt ------------------------------------------------------------

    def build_prompt(self, *, headline: str, cta: str, brief: VisualBrief) -> str:
        return "\n".join(
            [
                "## WHAT WAS COMPOSITED ONTO THIS IMAGE",
                f"Headline: {headline}",
                f"Call to action: {cta}",
                f"Placed at: {brief.placement_zone}",
                "",
                "## WHAT THE IMAGE WAS SUPPOSED TO BE",
                brief.image_prompt,
                "",
                "## HOW IT WAS SUPPOSED TO BE LAID OUT",
                brief.composition_notes,
                "",
                "Judge the attached image against the above.",
            ]
        )
```

- [ ] **Step 4: Add the canned verdict to the offline provider**

In `backend/app/llm/demo.py`, inside `structured`, before the `raise`:

```python
        if name == "QAVerdict":
            return schema(**self._qa())
```

And add the method beside `_verdict`:

```python
    def _qa(self) -> dict:
        """Every third asset comes back flagged.

        A rehearsal where QA always passes hides the redo loop, which is the
        part of this stage worth watching — the same reason `_verdict` sends
        the first crew review back.
        """
        self._checks = getattr(self, "_checks", 0) + 1
        if self._checks % 3 == 0:
            return {
                "status": "flagged",
                "notes": (
                    "[demo] The headline sits over the busiest part of the frame — "
                    "ask for cleaner space where it lands."
                ),
            }
        return {"status": "passed", "notes": ""}
```

- [ ] **Step 5: Register the agent for tuning**

In `backend/app/agents/tuning.py`, add the constant beside the other four
(`tuning.py:24-27`), leaving `CREW_AGENTS` alone — QA belongs to the studio,
not the crew:

```python
VISION_QA = "vision_qa"
```

Add `MAX_REDOS` to the imports from `app.agents.studio` is *not* needed — keep
the knob's default literal here to avoid a circular import, matching how the
director's `max_revisions` default is already declared in this module.

Then append this profile to `PROFILES`:

```python
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
                default=2,
            ),
        ),
    ),
```

Add `max_redos` as a nullable integer column on `AgentSetting` in
`backend/app/models.py` beside the existing knob columns, following exactly how
`max_revisions` is declared there.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_vision_qa.py tests/test_llm_providers.py tests/test_api_agents.py -v`
Expected: all pass, including the `test_demo_provider_accepts_images_and_ignores_them` test deferred from Task 7

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/vision_qa.py backend/app/llm/demo.py backend/app/agents/tuning.py backend/tests/test_vision_qa.py
git commit -m "feat(agents): vision QA pass that degrades rather than blocks"
```

---

### Task 9: The studio graph

**Files:**
- Create: `backend/app/agents/studio.py`
- Test: `backend/tests/test_studio.py`

**Interfaces:**
- Consumes: `MediaProvider`/`RenderError` (Task 1), `compose_creative` (Task 4), `AssetStorage` (Task 5), `VisionQA`/`QAVerdict` (Task 8), `AgentEvent`/`EventSink`/`emit` (`app.agents.events`).
- Produces: `VariantSpec(variant_id: int, headline: str, cta: str, brief: VisualBrief)`, `RenderedAsset(variant_id: int, media_url: str, qa_status: str, qa_notes: str | None, redos: int)`, `MAX_REDOS = 2`, and `Studio(provider=..., qa=..., storage=..., max_redos=MAX_REDOS, aspect="1:1").run(spec, sink=None) -> RenderedAsset`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_studio.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_studio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.studio'`

- [ ] **Step 3: Write the studio**

Create `backend/app/agents/studio.py`:

```python
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
            self._prompt(spec, state["qa_notes"]), aspect=self.aspect
        )
        creative = compose_creative(
            background,
            headline=spec.headline,
            cta=spec.cta,
            zone=spec.brief.placement_zone,
            aspect=self.aspect,
        )

        emit(
            sink,
            AgentEvent(
                "renderer",
                "finished",
                f"Background rendered and headline composited at "
                f"{spec.brief.placement_zone}",
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
        return " ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_studio.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/studio.py backend/tests/test_studio.py
git commit -m "feat(studio): render and QA graph with a bounded redo loop"
```

---

### Task 10: Render routes and the review gate API

**Files:**
- Create: `backend/app/api/assets.py`
- Modify: `backend/app/api/schemas.py`, `backend/app/api/deps.py`, `backend/app/api/history.py:31-32`, `backend/app/models.py:185`, `backend/app/main.py`
- Test: `backend/tests/test_api_assets.py`

**Interfaces:**
- Consumes: `Studio`/`VariantSpec`/`RenderedAsset` (Task 9), `AssetStorage` (Task 5), `get_media_provider` (Task 1), settings from Task 6, `RunLog`/`event_stream` (existing).
- Produces: `AssetRead`, `RenderRead`, `AssetDecision` schemas; `get_studio` dependency; `RENDER = "render"` run kind; seven routes.

**Count mapping for history:** `Run` has no `assets` column and needs none — reuse `variants` for assets rendered, `flagged` for QA-flagged, `revisions` for redos. Update the `kind` docstring at `models.py:185` to mention `"render"`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_api_assets.py`, following the fixture style already used in `backend/tests/test_api_generation.py` (read it first — it shows how the app is built with dependency overrides and how a campaign is walked to a given status).

```python
from app.domain import CampaignStatus

# Build on the helpers in test_api_generation.py: a campaign advanced to
# GENERATING with approved concepts, and variants already persisted.


def test_render_rejects_a_campaign_that_has_not_generated(client, campaign_pending_plan):
    response = client.post(f"/api/campaigns/{campaign_pending_plan.id}/render")
    assert response.status_code == 409


def test_render_produces_one_asset_per_variant(client, campaign_with_variants):
    response = client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    assert response.status_code == 200

    body = response.json()
    assert body["variants_rendered"] == 3
    assert len(body["assets"]) == 3
    assert all(asset["media_url"].startswith("/media/") for asset in body["assets"])


def test_render_advances_the_campaign_to_asset_review(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    campaign = client.get(f"/api/campaigns/{campaign_with_variants.id}").json()
    assert campaign["status"] == CampaignStatus.PENDING_ASSET_REVIEW


def test_rendering_twice_skips_what_is_already_rendered(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    second = client.post(f"/api/campaigns/{campaign_with_variants.id}/render").json()
    assert second["variants_rendered"] == 0
    assert second["variants_skipped"] == 3


def test_approving_an_asset_records_the_decision(client, campaign_with_variants):
    asset_id = client.post(
        f"/api/campaigns/{campaign_with_variants.id}/render"
    ).json()["assets"][0]["id"]

    response = client.post(f"/api/assets/{asset_id}/approve")
    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"


def test_rejecting_an_asset_records_the_decision(client, campaign_with_variants):
    asset_id = client.post(
        f"/api/campaigns/{campaign_with_variants.id}/render"
    ).json()["assets"][0]["id"]

    assert client.post(f"/api/assets/{asset_id}/reject").json()["review_status"] == "rejected"


def test_closing_the_gate_needs_at_least_one_approved_asset(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    response = client.post(f"/api/campaigns/{campaign_with_variants.id}/assets/approve")
    assert response.status_code == 409


def test_closing_the_gate_advances_to_ready_to_publish(client, campaign_with_variants):
    assets = client.post(f"/api/campaigns/{campaign_with_variants.id}/render").json()["assets"]
    client.post(f"/api/assets/{assets[0]['id']}/approve")

    response = client.post(f"/api/campaigns/{campaign_with_variants.id}/assets/approve")
    assert response.status_code == 200
    assert response.json()["status"] == CampaignStatus.READY_TO_PUBLISH


def test_auto_mode_approves_qa_passed_assets_and_skips_the_gate(client, campaign_with_variants):
    client.patch(
        f"/api/campaigns/{campaign_with_variants.id}/auto-mode",
        json={"auto_approve_assets": True},
    )
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")

    campaign = client.get(f"/api/campaigns/{campaign_with_variants.id}").json()
    assert campaign["status"] == CampaignStatus.READY_TO_PUBLISH


def test_render_writes_a_history_row(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    kinds = [run["kind"] for run in client.get("/api/runs").json()]
    assert "render" in kinds


def test_redo_replaces_one_asset(client, campaign_with_variants):
    asset = client.post(f"/api/campaigns/{campaign_with_variants.id}/render").json()["assets"][0]
    response = client.post(f"/api/assets/{asset['id']}/redo")

    assert response.status_code == 200
    assert response.json()["media_url"] != asset["media_url"]


def test_listing_assets_returns_them_for_the_gate(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    listed = client.get(f"/api/campaigns/{campaign_with_variants.id}/assets").json()
    assert len(listed) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_api_assets.py -v`
Expected: FAIL — the routes return 404

- [ ] **Step 3: Add the schemas**

In `backend/app/api/schemas.py`, after `GenerationRead`:

```python
class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    media_url: str
    qa_status: str
    qa_notes: str | None
    review_status: str


class RenderRead(BaseModel):
    """What one render pass did, for the console's result line."""

    variants_rendered: int
    variants_skipped: int
    assets: list[AssetRead]


class AssetDecision(BaseModel):
    """A human's verdict on one creative at the review gate."""

    decision: Literal["approved", "rejected"]
```

- [ ] **Step 4: Add the run kind**

In `backend/app/api/history.py`, beside the existing constants:

```python
RENDER = "render"
```

In `backend/app/models.py:185`, update the comment:

```python
    #: "plan" (the planning agent), "generate" (the three-agent crew) or
    #: "render" (the studio).
```

- [ ] **Step 5: Add the studio dependency**

In `backend/app/api/deps.py`:

```python
from app.agents.studio import Studio
from app.agents.vision_qa import VisionQA
from app.media import get_media_provider
from app.media.storage import AssetStorage


@lru_cache
def get_storage() -> AssetStorage:
    return AssetStorage(get_settings().assets_dir)


def get_studio(tuned: Tuning = Depends(get_tuning)) -> Studio:
    settings = get_settings()
    return Studio(
        provider=get_media_provider(
            settings.media_provider,
            api_key=settings.active_media_key,
            image_model=settings.active_media_model,
            timeout_seconds=settings.media_timeout_seconds,
        ),
        # QA judges with the same model the crew wrote with, for the same
        # reason the crew shares one provider: a reviewer and the thing it
        # reviews should not come from different models by accident.
        qa=VisionQA(provider=_llm(), standing_note=tuned.note(tuning.VISION_QA)),
        storage=get_storage(),
    )
```

- [ ] **Step 6: Write the routes**

Create `backend/app/api/assets.py`. Model it closely on
`backend/app/api/generation.py` — read that file first; the resume helper, the
streaming twin, the `RunLog` usage and the error handling should all look like
siblings, not cousins.

The core route and its helpers, written out:

```python
router = APIRouter(prefix="/api", tags=["assets"])


@router.post("/campaigns/{campaign_id}/render", response_model=RenderRead)
def render(
    campaign_id: int,
    db: Session = Depends(get_db),
    studio: Studio = Depends(get_studio),
) -> RenderRead:
    campaign = get_campaign_or_404(db, campaign_id)
    if campaign.status is not CampaignStatus.GENERATING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is {campaign.status}, not {CampaignStatus.GENERATING} — "
            "the crew has to run before there is anything to render",
        )

    todo, skipped = _pending(db, campaign)
    if not todo and skipped == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "no variants to render")

    record = RunLog(campaign, RENDER)
    produced: list[RenderedAsset] = []
    try:
        for spec in todo:
            produced.append(studio.run(spec, sink=record.capture))
    except RenderError as error:
        # Keep whatever earlier variants produced — the run is resumable.
        written = _persist(db, produced)
        _advance(db, campaign, written)
        db.commit()
        record.failed(db, str(error), **_counts(written, produced))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    written = _persist(db, produced)
    _advance(db, campaign, written)
    db.commit()
    _record_render(db, record, written, produced)
    return RenderRead(
        variants_rendered=len(written),
        variants_skipped=skipped,
        assets=[AssetRead.model_validate(row) for row in written],
    )


def _pending(db: Session, campaign: Campaign) -> tuple[list[VariantSpec], int]:
    """Variants still needing a creative, plus how many already had one.

    Every variant is rendered, including director-flagged ones: the asset gate
    is where a human filters, and the console shows `director_status` on the
    card so a flagged variant is visibly flagged rather than quietly dropped.
    """
    cap = get_settings().max_renders_per_run
    todo: list[VariantSpec] = []
    skipped = 0
    for variant in _variants_of(db, campaign.id):
        if variant.assets:
            skipped += 1
            continue
        if len(todo) >= cap:
            skipped += 1
            continue
        todo.append(
            VariantSpec(
                variant_id=variant.id,
                headline=variant.headline,
                cta=variant.cta,
                brief=VisualBrief(**variant.visual_brief),
            )
        )
    return todo, skipped


def _variants_of(db: Session, campaign_id: int) -> list[Variant]:
    return list(
        db.scalars(
            select(Variant)
            .join(Concept, Variant.concept_id == Concept.id)
            .where(Concept.campaign_id == campaign_id)
            .order_by(Variant.concept_id, Variant.id)
        )
    )


def _persist(db: Session, produced: list[RenderedAsset]) -> list[Asset]:
    rows = [
        Asset(
            variant_id=asset.variant_id,
            media_url=asset.media_url,
            qa_status=asset.qa_status,
            qa_notes=asset.qa_notes,
            review_status="pending",
        )
        for asset in produced
    ]
    db.add_all(rows)
    db.flush()
    return rows


def _advance(db: Session, campaign: Campaign, written: list[Asset]) -> None:
    """Move the campaign on, honouring auto-mode the way the plan gate does.

    Auto-approved assets still carry an explicit approved status, so nothing
    downstream has to know whether a human was in the loop.
    """
    if not written:
        return

    campaign.status = CampaignStatus.PENDING_ASSET_REVIEW
    if not campaign.auto_approve_assets:
        return

    for row in written:
        if row.qa_status == "passed":
            row.review_status = "approved"
    if any(row.review_status == "approved" for row in written):
        campaign.status = CampaignStatus.READY_TO_PUBLISH


def _counts(written: list[Asset], produced: list[RenderedAsset]) -> dict[str, int]:
    return {
        # `Run` has no assets column and needs none: for a render pass,
        # variants means creatives made, flagged means QA-flagged, and
        # revisions means redos.
        "variants": len(written),
        "flagged": sum(1 for row in written if row.qa_status == "flagged"),
        "revisions": max((asset.redos for asset in produced), default=0),
    }


def _record_render(
    db: Session, record: RunLog, written: list[Asset], produced: list[RenderedAsset]
) -> None:
    counts = _counts(written, produced)
    flagged = counts["flagged"]
    summary = (
        f"{counts['variants']} "
        f"{'creative' if counts['variants'] == 1 else 'creatives'} rendered"
    )
    summary += f" — {flagged} flagged for you" if flagged else " — all passed QA"
    record.succeeded(db, summary, **counts)
```

The remaining routes:
- On `RenderError`, keep what finished (same pattern as `generation.py:85-90`),
  mark the run failed, return 502.
- When `campaign.auto_approve_assets` is set, every QA-passed asset is written
  with `review_status="approved"` and the campaign advances straight to
  `READY_TO_PUBLISH` — the same explicit-status principle as `campaigns.py:110`.
- `POST /api/campaigns/{id}/render/stream` — the same run through
  `event_stream`, exactly as `generate_streaming` does.
- `GET /api/campaigns/{id}/assets` → `list[AssetRead]`.
- `POST /api/assets/{id}/approve` and `/reject` → `AssetRead`.
- `POST /api/assets/{id}/redo` — re-runs the studio for that one variant,
  deletes the superseded file via `storage.path_for(...).unlink(missing_ok=True)`,
  updates the row in place, returns `AssetRead`.
- `POST /api/campaigns/{id}/assets/approve` — 409 unless at least one asset is
  approved (mirroring `campaigns.py:217-226`), then advances to
  `READY_TO_PUBLISH`.

- [ ] **Step 7: Register the router**

In `backend/app/main.py`:

```python
from app.api.assets import router as assets_router

app.include_router(assets_router)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_api_assets.py -v`
Expected: 12 passed

- [ ] **Step 9: Run the full suite**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 10: Commit**

```bash
git add backend/app/api backend/app/models.py backend/app/main.py backend/tests/test_api_assets.py
git commit -m "feat(api): render routes and the asset review gate"
```

---

### Task 11: The console

**Files:**
- Create: `frontend/src/components/AssetCard.tsx`, `frontend/src/pages/Export.tsx`
- Modify: `frontend/src/components/os/FlowGraph.tsx:24-36`, `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/Console.tsx`, `frontend/src/App.tsx`
- Test: manual, via `docker compose up --build`

**Interfaces:**
- Consumes: the seven routes and three schemas from Task 10.
- Produces: an asset gate reusing `GateBar`, and an export screen.

- [ ] **Step 1: Add the API types**

In `frontend/src/api/types.ts`, mirroring the Pydantic schemas exactly:

```typescript
export type Asset = {
  id: number
  variant_id: number
  media_url: string
  qa_status: 'passed' | 'flagged'
  qa_notes: string | null
  review_status: 'pending' | 'approved' | 'rejected'
}

export type RenderResult = {
  variants_rendered: number
  variants_skipped: number
  assets: Asset[]
}
```

- [ ] **Step 2: Add the client calls**

In `frontend/src/api/client.ts`, following the existing call style:
`listAssets(campaignId)`, `renderAssets(campaignId)`, `approveAsset(id)`,
`rejectAsset(id)`, `redoAsset(id)`, `approveAllAssets(campaignId)`.

- [ ] **Step 3: Add the two new waypoints to the flow graph**

In `frontend/src/components/os/FlowGraph.tsx`, the nodes array currently ends
`director` at x 588 and `asset_gate` at x 706. Insert two waypoints and
re-space so they stay evenly distributed:

```typescript
  { id: 'planner', label: 'planner', x: 58 },
  { id: 'plan_gate', label: 'plan gate', x: 168, gate: true },
  { id: 'copywriter', label: 'copy', x: 278 },
  { id: 'visual_planner', label: 'art', x: 388 },
  { id: 'director', label: 'director', x: 498 },
  { id: 'renderer', label: 'render', x: 608 },
  { id: 'vision_qa', label: 'QA', x: 706 },
  { id: 'asset_gate', label: 'asset gate', x: 812, gate: true },
```

Add `renderer: 4` and `vision_qa: 5` to the ordering map below it, update the
SVG `viewBox` width and the `aria-label` to name the two new stages, and add
the QA redo return edge in the same style as the two existing director edges.

- [ ] **Step 4: Build the asset card**

Create `frontend/src/components/AssetCard.tsx`, following `VariantCard.tsx`'s
structure. It shows the creative at `media_url`, the QA verdict (with
`qa_notes` when flagged), the variant's `director_status`, and three actions —
approve, redo, reject. A flagged asset must be visibly flagged, not quietly
mixed in with the passes.

- [ ] **Step 5: Wire the gate into the console**

In `frontend/src/pages/Console.tsx`, add the asset gate: it appears when the
campaign is `pending_asset_review`, reuses `GateBar` exactly as the plan gate
does so both gates behave identically (`plan:62`), and closes via
`approveAllAssets`.

- [ ] **Step 6: Build the export screen**

Create `frontend/src/pages/Export.tsx` — the approved creatives at full size,
each with a download link and a copy-text action for the headline, body and CTA.
Route it in `App.tsx` alongside the existing pages.

- [ ] **Step 7: Verify end to end offline**

```bash
docker compose down -v
docker compose up --build
```

Open <http://localhost:8000>, create a campaign, approve a concept, generate,
then render. Confirm: the two new waypoints light up, at least one asset comes
back flagged (the offline provider flags every third), redo works, approving
advances to the export screen, and every image displays.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat(console): asset gate, render waypoints, export screen"
```

---

### Task 12: Documentation

**Files:**
- Modify: `README.md`, `backend/README.md`, `campaign-ai-implementation-plan.md:173-177`

- [ ] **Step 1: Update the root README**

Add the render stage to "What is in there" — the Campaigns section describes
the gates, and there are now two of them working. Document `MEDIA_PROVIDER` in
"Running against a real model", including that `demo` renders offline
placeholders and that DashScope reuses `DASHSCOPE_API_KEY`. Note the
`agentcy_assets` volume beside the existing `agentcy_chroma` one, and that
`docker compose down -v` throws away generated creatives too.

- [ ] **Step 2: Update the backend README**

Document `app/media/` beside the existing module notes, and the `/media` mount.

- [ ] **Step 3: Tick off Phase 3 in the implementation plan**

In `campaign-ai-implementation-plan.md`, check the boxes now true under
**Phase 3**: image generation integration, automated vision QA pre-check agent,
review gate UI, preview/export screen. Leave video unticked — it is 3b.

- [ ] **Step 4: Commit**

```bash
git add README.md backend/README.md campaign-ai-implementation-plan.md
git commit -m "docs: the render stage, media providers and the assets volume"
```

---

## Definition of done

A brief goes from planning, through the approval gate, the crew, render, vision
QA and the asset gate, to an export screen with downloadable image creatives —
offline in `demo` mode with no keys, and against DashScope with a key. The full
suite passes. Video (3b) is a separate plan.
