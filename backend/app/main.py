"""FastAPI application entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.api.auth import router as auth_router
from app.api.jobs import router as jobs_router
from app.api.workspace import router as workspace_router
from app.security import security_middleware, error_body
from app.db import engine, SCHEMA_REVISION
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.api.calendar import router as calendar_router
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

app.middleware("http")(security_middleware)
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(workspace_router)
app.include_router(campaigns_router)
app.include_router(calendar_router)
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
            response = await super().get_response(path, scope)
        except StarletteHTTPException as error:
            # An obsolete JS chunk must be a real 404, never an HTML document
            # masquerading as a module. Only extensionless client routes fall back.
            if error.status_code != 404 or path.lstrip("/").startswith("assets/") or Path(path).suffix:
                raise
            response = await super().get_response("index.html", scope)
        if path.lstrip("/").startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            # Revalidate the entry document so refreshes reference this deployment.
            response.headers["Cache-Control"] = "no-cache"
        return response


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




@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, error: HTTPException):
    detail = str(error.detail) if error.status_code < 500 else "The service could not complete this action. Check its status before retrying."
    return JSONResponse(error_body(request, error.status_code, detail), status_code=error.status_code, headers=error.headers)


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, error: RequestValidationError):
    fields = [{"field": ".".join(str(part) for part in row["loc"] if part != "body"), "message": row["msg"]} for row in error.errors()]
    return JSONResponse(error_body(request, 422, "; ".join(row["message"] for row in fields), fields=fields), status_code=422)


@app.get("/api/ready", tags=["ops"])
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            from app.clock import utcnow
            from datetime import timedelta
            from app.models import WorkerHeartbeat
            from sqlalchemy import select, func
            workers = connection.scalar(select(func.count()).select_from(WorkerHeartbeat).where(WorkerHeartbeat.last_seen >= utcnow() - timedelta(seconds=120)))
        if revision != SCHEMA_REVISION:
            raise RuntimeError("Pending migrations")
        settings = get_settings()
        if not settings.scripted_demo:
            settings.active_llm_key; settings.active_embedding_key
            settings.active_media_key; settings.active_video_key
        if settings.chroma_host:
            import chromadb
            chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port).heartbeat()
        if not workers:
            return JSONResponse({"status": "unavailable", "worker": "offline"}, status_code=503)
        return {"status": "ready", "worker": "available"}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)


def documented_openapi():
    """Document the public queue contract instead of internal worker responses."""
    if app.openapi_schema:
        return app.openapi_schema
    import re
    from fastapi.openapi.utils import get_openapi
    from app.jobs import is_operation
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {}).update({
        "SessionCookie": {"type": "apiKey", "in": "cookie", "name": "agentcy_session"},
        "CsrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
    })
    public = {"/api/health", "/api/ready", "/api/auth/status", "/api/auth/setup", "/api/auth/login"}
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            if path not in public:
                operation["security"] = [{"SessionCookie": [], **({"CsrfToken": []} if method != "get" else {})}]
                operation.setdefault("responses", {}).update({"401": {"description": "Sign-in required"}, "403": {"description": "CSRF or workspace role check failed"}})
            normalized = re.sub(r"\{[^}]+\}", "1", path.removeprefix("/api"))
            if method == "post" and is_operation(normalized):
                operation["responses"].pop("200", None)
                operation["responses"]["202"] = {"description": "Durable job accepted. Poll GET /api/jobs/{id}; the original result is available when status is succeeded.",
                    "content": {"application/json": {"schema": {"type": "object", "required": ["__job__"], "properties": {"__job__": {"type": "object", "required": ["id", "status"], "properties": {"id": {"type": "string"}, "status": {"type": "string"}}}}}}}}
    app.openapi_schema = schema
    return schema


app.openapi = documented_openapi


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"], include_in_schema=False)
def missing_api(path: str):
    raise HTTPException(404, "API endpoint not found")


# Mount the SPA only after every API route, including readiness and fallback.
_mount_media()
_mount_console(CONSOLE_DIST)
