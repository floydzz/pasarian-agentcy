"""FastAPI application entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.api.agents import router as agents_router
from app.api.assets import router as assets_router
from app.api.campaigns import router as campaigns_router
from app.api.chat import router as chat_router
from app.api.cinematic_trailers import router as cinematic_trailers_router
from app.api.demo_videos import router as demo_videos_router
from app.api.generation import router as generation_router
from app.api.history import router as history_router
from app.api.profile import router as profile_router
from app.api.product_references import router as product_references_router
from app.api.system import router as system_router
from app.api.trends import router as trends_router
from app.api.videos import router as videos_router
from app.config import REPO_ROOT, get_settings
from app.media.storage import MEDIA_PREFIX

CONSOLE_DIST = REPO_ROOT / "frontend" / "dist"

app = FastAPI(
    title="Agentcy",
    description="AI marketing campaign generation for Malaysian SMEs.",
    version="0.1.0",
)

# The React/Vite dev server is a separate origin during development. In the
# container the console is served from this app, so nothing crosses an origin
# and this middleware never fires.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(campaigns_router)
app.include_router(chat_router)
app.include_router(generation_router)
app.include_router(assets_router)
app.include_router(agents_router)
app.include_router(history_router)
app.include_router(profile_router)
app.include_router(product_references_router)
app.include_router(demo_videos_router)
app.include_router(videos_router)
app.include_router(cinematic_trailers_router)
app.include_router(system_router)
app.include_router(trends_router)


@app.get("/api/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness for the container. Deliberately touches nothing."""
    return {"status": "ok"}


class ConsoleFiles(StaticFiles):
    """Serve the built console, and let the client router own unknown paths.

    A deep link like `/campaigns/3` is a route in React, not a file on disk, so
    a miss returns index.html and the browser resolves it. Only misses under
    the SPA's own mount reach this — the API is mounted first and answers its
    own 404s.
    """

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def _mount_media() -> None:
    """Generated creatives, served from the same origin as the console.

    Registered before the SPA, which mounts at `/` and answers every unmatched
    path with index.html — a media mount added after it would never be reached.
    """
    assets = get_settings().assets_dir
    assets.mkdir(parents=True, exist_ok=True)
    app.mount(MEDIA_PREFIX, StaticFiles(directory=assets), name="media")


def _mount_console(directory: Path) -> None:
    """Mounted last and only when built — `npm run dev` still owns development."""
    if directory.is_dir():
        app.mount("/", ConsoleFiles(directory=directory, html=True), name="console")


_mount_media()
_mount_console(CONSOLE_DIST)
