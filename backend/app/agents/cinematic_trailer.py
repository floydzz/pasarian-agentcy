"""Persistent AI-shot workflow for Agentcy's long-form product trailer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import REPO_ROOT
from app.media.base import RenderError
from app.media.storage import AssetStorage
from app.models import CinematicTrailer, CinematicTrailerShot
from app.video.broll import BrollProvider, VideoGenerationRequest
from app.video.trailer import RenderedTrailer, TrailerComposer, TrailerShot


@dataclass(frozen=True)
class SubmittedShots:
    submitted: int
    skipped: int


class CinematicTrailerStudio:
    """Start, resume and finish paid AI shots without losing their task IDs."""

    # HappyHorse allows five concurrent reference-video tasks. Keep one slot
    # free for a manual retry, rather than turning a product-film run into a
    # predictable 429 on its sixth submission.
    MAX_ACTIVE_GENERATIONS = 4

    #: The Agentcy product-film blueprint must use a current product journey,
    #: rather than rely on a generated dashboard that only looks plausible.
    EXACT_SCREEN_FEATURES = frozenset(
        {
            "Marketing strategist",
            "Brand truth becomes action",
            "Campaign command centre",
            "Image Studio in motion",
            "Video Studio in motion",
            "Progress stays visible",
            "The human review gate",
            "Publish for every channel",
            "The history stays useful",
        }
    )

    def __init__(
        self,
        *,
        storage: AssetStorage,
        composer: TrailerComposer,
        provider: BrollProvider | None,
    ) -> None:
        self.storage = storage
        self.composer = composer
        self.provider = provider

    def application_image_url(self, surface: str = "studio") -> str:
        """Copy a checked-in Agentcy UI screen into durable media storage."""
        return self.storage.save(self.application_image_bytes(surface), suffix=".png")

    @staticmethod
    def application_image_bytes(surface: str) -> bytes:
        source = {
            "studio": REPO_ROOT / "image-studio.png",
            "hub": REPO_ROOT / "hub.png",
            "history": REPO_ROOT / "history-work.png",
        }.get(surface)
        if source is None:
            raise RenderError(f"Unknown Agentcy product surface: {surface}.")
        if not source.is_file():
            raise RenderError(f"The bundled Agentcy {surface} screenshot is missing.")
        return source.read_bytes()

    def submit(self, trailer: CinematicTrailer) -> SubmittedShots:
        if self._requires_exact_capture(trailer) and not trailer.application_capture_url:
            raise RenderError(
                "Attach the guided Agentcy screen recording before generating this feature trailer. "
                "It supplies the exact UI frames to the video model and final composition."
            )
        provider = self._provider()
        submitted, skipped = self._submit_available(
            trailer, provider, include_failed=True
        )
        trailer.status = "generating" if submitted else self._status_for(trailer)
        return SubmittedShots(submitted=submitted, skipped=skipped)

    def _submit_available(
        self,
        trailer: CinematicTrailer,
        provider: BrollProvider,
        *,
        include_failed: bool,
    ) -> tuple[int, int]:
        """Fill the provider queue without exceeding its active-task limit."""
        active = sum(
            shot.provider_status in {"pending", "running"}
            for shot in trailer.shots
        )
        remaining = max(0, self.MAX_ACTIVE_GENERATIONS - active)
        submitted = skipped = 0
        for shot in trailer.shots:
            if shot.provider_status in {"pending", "running", "succeeded"}:
                skipped += 1
                continue
            if shot.provider_status == "failed" and not include_failed:
                skipped += 1
                continue
            if remaining == 0:
                continue
            try:
                task = provider.submit_generation(self._request(trailer, shot))
            except RenderError as error:
                shot.provider_status = "failed"
                shot.provider_error = str(error)
                continue
            shot.remote_task_id = task.task_id
            shot.provider_status = task.status
            shot.provider_error = None
            submitted += 1
            if task.status in {"pending", "running"}:
                remaining -= 1
        return submitted, skipped

    def refresh(self, trailer: CinematicTrailer) -> None:
        provider = self._provider()
        for shot in trailer.shots:
            if shot.provider_status not in {"pending", "running"} or not shot.remote_task_id:
                continue
            try:
                task = provider.get_generation(shot.remote_task_id)
            except RenderError as error:
                shot.provider_status = "failed"
                shot.provider_error = str(error)
                continue
            shot.provider_status = task.status
            shot.provider_error = task.error
            if task.status != "succeeded" or not task.video_url:
                continue
            try:
                shot.media_url = self.storage.save(
                    provider.download_generation(task.video_url), suffix=".mp4"
                )
            except RenderError as error:
                shot.provider_status = "failed"
                shot.provider_error = str(error)
                continue
        # A refresh also advances a deliberately rate-limited batch. A person
        # never has to resubmit the trailer just because its product story is
        # longer than the provider's concurrent-task quota.
        self._submit_available(trailer, provider, include_failed=False)
        trailer.status = self._status_for(trailer)

    def compose(self, trailer: CinematicTrailer) -> RenderedTrailer:
        if any(shot.provider_status != "succeeded" or not shot.media_url for shot in trailer.shots):
            raise RenderError("Every trailer shot must finish before the final composition.")
        ordered = self._ordered_shots(trailer.shots)
        application_capture = (
            self.storage.read(trailer.application_capture_url)
            if trailer.application_capture_url else None
        )
        product_image = (
            self.storage.read(trailer.product_reference_url)
            if trailer.product_reference_url else None
        )
        soundtrack = (
            self.storage.read(trailer.soundtrack_url)
            if trailer.soundtrack_url else None
        )
        rendered = self.composer.render(
            [
                TrailerShot(
                    clip=self.storage.read(shot.media_url),
                    duration_seconds=shot.duration_seconds,
                    title_card=shot.title_card,
                    application_image=(
                        None
                        if product_image or self._is_ai_integrated_product(shot)
                        else self._protected_reference(shot, self._surface_for(shot))
                    ),
                    product_image=product_image,
                    # AI-native feature shots own their visual treatment. The
                    # UI capture supplied their exact reference frame at
                    # generation time; composition deliberately does not paste
                    # that frame over the completed AI clip.
                    product_surface=(
                        "product"
                        if product_image
                        else "none"
                        if self._is_ai_integrated_product(shot)
                        else self._surface_for(shot)
                    ),
                    application_capture=(
                        application_capture
                        if (
                            application_capture
                            and not product_image
                            and not self._is_ai_integrated_product(shot)
                            and self._surface_for(shot) != "none"
                        )
                        else None
                    ),
                    flow_offset_seconds=self._flow_offset_for(shot),
                    screen_track=self._screen_track_for(shot),
                )
                for shot in ordered
            ],
            soundtrack=soundtrack,
        )
        previous = (trailer.media_url, trailer.poster_url)
        trailer.media_url = self.storage.save(rendered.video, suffix=".mp4")
        try:
            trailer.poster_url = self.storage.save(rendered.poster, suffix=".png")
        except Exception:
            self.storage.path_for(trailer.media_url).unlink(missing_ok=True)
            trailer.media_url, trailer.poster_url = previous
            raise
        trailer.duration_seconds = rendered.duration_seconds
        trailer.status = "rendered"
        trailer.review_status = "pending"
        return rendered

    def _is_ai_integrated_product(self, shot: CinematicTrailerShot) -> bool:
        """Whether the model, rather than FFmpeg, owns this UI appearance."""
        return (
            self._surface_for(shot) != "none"
            and shot.mode == "reference_to_video"
            and not shot.protect_reference
        )

    def regenerate(
        self, trailer: CinematicTrailer, shots: list[CinematicTrailerShot]
    ) -> SubmittedShots:
        """Request new visual takes without altering the saved screenplay."""
        if not shots:
            raise RenderError("Choose at least one trailer clip to regenerate.")
        if any(shot.provider_status in {"pending", "running"} for shot in shots):
            raise RenderError(
                "Wait for the selected clip to finish before regenerating it. "
                "This prevents a second paid task being started while the first is still active."
            )
        if self._requires_exact_capture(trailer) and not trailer.application_capture_url:
            raise RenderError(
                "Attach the guided Agentcy screen recording before regenerating feature clips."
            )
        for shot in shots:
            shot.remote_task_id = None
            shot.provider_status = "draft"
            shot.provider_error = None
            shot.media_url = None
        trailer.status = "draft"
        trailer.review_status = "pending"
        provider = self._provider()
        submitted, skipped = self._submit_available(
            trailer, provider, include_failed=True
        )
        trailer.status = "generating" if submitted else self._status_for(trailer)
        return SubmittedShots(submitted=submitted, skipped=skipped)

    def _request(
        self, trailer: CinematicTrailer, shot: CinematicTrailerShot
    ) -> VideoGenerationRequest:
        images: tuple[bytes, ...] = ()
        # A protected application screenshot is composited after generation,
        # not given to the model to warp. Other I2V/R2V references are sent as
        # base64 by the provider.
        if not shot.protect_reference:
            images = tuple(self.storage.read(url) for url in shot.reference_asset_urls)
        # A product-flow recording gives the video model a current exact frame
        # for this feature shot; composition projects the same recording back
        # into the scene so labels stay trustworthy in the final master.
        if (
            trailer.application_capture_url
            and self._is_ai_integrated_product(shot)
            and hasattr(self.composer, "reference_frame")
        ):
            frame = self.composer.reference_frame(  # type: ignore[attr-defined]
                self.storage.read(trailer.application_capture_url),
                offset_seconds=self._flow_offset_for(shot),
            )
            # The recorded UI state is deliberately the sole feature reference.
            # A second, generic screenshot makes it too easy for a provider to
            # interpolate the two into a plausible-but-wrong hybrid interface.
            images = (frame,)
        return VideoGenerationRequest(
            # HappyHorse can generate synced audio. The final master preserves
            # that track, while exact title typography stays out of the model.
            prompt=(
                f"{shot.prompt}\n\n"
                f"Spoken narration: {shot.voiceover}\n"
                f"Sound design: {shot.audio_cue}"
            ),
            mode=shot.mode,  # type: ignore[arg-type]  # API schema owns this literal.
            aspect=shot.trailer.aspect_ratio,
            seconds=shot.duration_seconds,
            reference_images=images,
        )

    def _protected_reference(
        self, shot: CinematicTrailerShot, product_surface: str
    ) -> bytes | None:
        if shot.protect_reference and shot.reference_asset_urls:
            return self.storage.read(shot.reference_asset_urls[0])
        if product_surface != "none":
            # Legacy trailers have already-paid-for clips. Let us improve their
            # cut with a verified local screen without resubmitting video jobs.
            return self.application_image_bytes(product_surface)
        return None

    @staticmethod
    def _surface_for(shot: CinematicTrailerShot) -> str:
        if shot.product_surface != "none":
            return shot.product_surface
        # Original demo trailers stored only one protected app image.  These
        # mappings upgrade that cut at composition time, with no new AI bill.
        return {
            "Agentcy arrives": "studio",
            "Start with truth": "hub",
            "The crew": "studio",
            "The work becomes visible": "history",
            "The review gate": "studio",
            "The next campaign": "hub",
            "The invitation": "studio",
        }.get(shot.label, "none")

    @classmethod
    def _requires_exact_capture(cls, trailer: CinematicTrailer) -> bool:
        return any(shot.label in cls.EXACT_SCREEN_FEATURES for shot in trailer.shots)

    @staticmethod
    def _screen_track_for(shot: CinematicTrailerShot) -> str:
        return {
            "Marketing strategist": "monitor",
            "Brand truth becomes action": "network",
            "Campaign command centre": "network",
            "Image Studio in motion": "gallery",
            "Video Studio in motion": "gallery",
            "Progress stays visible": "gallery",
            "The human review gate": "review",
            "Publish for every channel": "launch",
            "The history stays useful": "gallery",
            "Agentcy arrives": "monitor",
            "Agentcy, on screen": "monitor",
            "Start with truth": "network",
            "One brief, connected crew": "network",
            "The crew": "network",
            "The work becomes visible": "gallery",
            "The work takes shape": "gallery",
            "Creative, ready to review": "gallery",
            "The system stays visible": "gallery",
            "The review gate": "review",
            "The next campaign": "launch",
            "The invitation": "launch",
        }.get(shot.label, "gallery")

    @staticmethod
    def _flow_offset_for(shot: CinematicTrailerShot) -> float:
        """Choose a progressing section of the real UI journey per scene."""
        return {
            "Marketing strategist": 0.0,
            "Brand truth becomes action": 5.0,
            "Campaign command centre": 10.0,
            "Image Studio in motion": 15.0,
            "Video Studio in motion": 20.0,
            "Progress stays visible": 25.0,
            "The human review gate": 30.0,
            "Publish for every channel": 35.0,
            "The history stays useful": 40.0,
            "Agentcy arrives": 0.0,
            "Agentcy, on screen": 0.0,
            "Start with truth": 3.8,
            "One brief, connected crew": 7.6,
            "The crew": 7.6,
            "The work becomes visible": 12.0,
            "The work takes shape": 12.0,
            "Creative, ready to review": 17.2,
            "The system stays visible": 17.2,
            "The review gate": 22.0,
            "The next campaign": 25.5,
            "The invitation": 25.5,
        }.get(shot.label, 0.0)

    @staticmethod
    def _ordered_shots(shots: list[CinematicTrailerShot]) -> list[CinematicTrailerShot]:
        """Keep the original fourth-wall moment as the final beat.

        The first generated demo placed it early. Reordering existing finished
        clips costs nothing and restores the requested ending immediately.
        """
        ending = [shot for shot in shots if shot.title_card == "THIS VIDEO WAS MADE BY ME TOO"]
        return [shot for shot in shots if shot not in ending] + ending

    def _provider(self) -> BrollProvider:
        if self.provider is None:
            raise RenderError(
                "AI trailer generation needs VIDEO_PROVIDER=dashscope and a DASHSCOPE_API_KEY."
            )
        return self.provider

    @staticmethod
    def _status_for(trailer: CinematicTrailer) -> str:
        statuses = {shot.provider_status for shot in trailer.shots}
        if "failed" in statuses:
            return "failed"
        if statuses == {"succeeded"}:
            return "ready_to_compose"
        if statuses & {"pending", "running"}:
            return "generating"
        return "draft"
