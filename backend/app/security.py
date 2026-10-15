"""Opaque, revocable cookie sessions; no credentials are stored in the browser."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, and_

from app.clock import utcnow
from app.config import get_settings
from app.db import SessionLocal
from app.models import LoginSession, Membership, User
from app.workspace import Principal, principal, require_media_scope, worker_request

COOKIE = "agentcy_session"
log = logging.getLogger(__name__)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=131072, r=8, p=1, maxmem=256 * 1024 * 1024)
    return f"scrypt${salt}${value.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split("$")
        if algorithm != "scrypt":
            return False
        value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=131072, r=8, p=1, maxmem=256 * 1024 * 1024)
        return hmac.compare_digest(value.hex(), expected)
    except (ValueError, TypeError):
        return False


def bootstrap_file() -> Path:
    return get_settings().bootstrap_file_path


def ensure_bootstrap_token():
    path = bootstrap_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x", opener=lambda name, flags: __import__("os").open(name, flags, 0o600)) as handle:
            handle.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass


def error_body(request: Request, status: int, message: str, code: str | None = None, fields=None):
    return {"detail": message, "code": code or {401: "authentication_required", 403: "permission_denied", 404: "not_found", 409: "conflict", 422: "validation_error", 429: "rate_limited"}.get(status, "request_failed"),
            "request_id": getattr(request.state, "request_id", ""), "retryable": status in (429, 502, 503, 504), "fields": fields or []}


def may_write(role: str, path: str):
    if path.startswith("/api/auth/"):
        return
    settings_path = path.startswith(("/api/agents", "/api/brand-profile", "/api/workspace")) or path.endswith("/auto-mode")
    approval = any(part in path for part in ("/approve", "/reject", "/decision", "/auto-mode"))
    if settings_path and role != "owner":
        raise HTTPException(403, "Only the workspace owner can change these settings")
    if approval and role not in ("owner", "reviewer"):
        raise HTTPException(403, "Owner or reviewer access is required for approvals")
    if not approval and not settings_path and role not in ("owner", "editor"):
        raise HTTPException(403, "Editor access is required for this action")


def authenticate_cookie(raw: str, csrf: str, unsafe: bool) -> Principal:
    if not raw:
        raise HTTPException(401, "Sign in to continue")
    with SessionLocal() as db:
        record = db.execute(select(LoginSession, User, Membership).join(User, User.id == LoginSession.user_id)
            .join(Membership, and_(Membership.user_id == LoginSession.user_id, Membership.workspace_id == LoginSession.workspace_id))
            .where(LoginSession.token_hash == digest(raw), User.disabled.is_(False))).first()
        now = utcnow()
        if not record:
            raise HTTPException(401, "Sign in to continue")
        saved, user, membership = record
        if saved.expires_at <= now or saved.last_seen < now - timedelta(hours=get_settings().session_idle_hours):
            raise HTTPException(401, "Sign in to continue")
        if unsafe and not hmac.compare_digest(csrf, saved.csrf):
            raise HTTPException(403, "Refresh the page before trying again")
        if saved.last_seen < now - timedelta(minutes=5):
            saved.last_seen = now
            db.commit()
        return Principal(user.id, membership.workspace_id, membership.role)


def require_idle_resource(actor: Principal, path: str):
    from app.jobs import resource
    from app.models import Job
    with SessionLocal(info={"workspace_id": actor.workspace_id}) as db:
        key = resource(db, path.removeprefix("/api"))
        if db.scalar(select(Job.id).where(Job.active_key == key).limit(1)):
            raise HTTPException(409, "A saved job is still working on this campaign. Wait for it to finish before changing its approvals or product references.")


def enqueue_operation(actor: Principal, path: str, payload, key: str):
    from app.jobs import submit, job_read
    with SessionLocal(info={"workspace_id": actor.workspace_id}) as db:
        return job_read(submit(db, path, payload, key))


async def security_middleware(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    path = request.url.path
    public = path in ("/api/health", "/api/ready", "/api/auth/status", "/api/auth/login", "/api/auth/setup")
    protected = path.startswith(("/api/", "/media/")) or path in ("/docs", "/redoc", "/openapi.json")
    token = None
    try:
        if protected and not public and request.method != "OPTIONS":
            if worker_request.get() and principal.get() is not None:
                actor = principal.get()
            else:
                actor = await run_in_threadpool(authenticate_cookie, request.cookies.get(COOKIE, ""), request.headers.get("X-CSRF-Token", ""), request.method not in ("GET", "HEAD", "OPTIONS"))
            token = principal.set(actor)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                may_write(actor.role, path)
                if not worker_request.get() and any(part in path for part in ("/approve", "/reject", "/decision", "/auto-mode", "/product-references")):
                    await run_in_threadpool(require_idle_resource, actor, path)
            if path.startswith("/media/"):
                require_media_scope(path, actor.workspace_id)
        if protected and request.method not in ("GET", "HEAD", "OPTIONS") and not worker_request.get():
            origin = request.headers.get("Origin")
            allowed = get_settings().public_origin or f"{request.url.scheme}://{request.url.netloc}"
            if origin and origin != allowed and (get_settings().public_origin or origin not in ("http://localhost:5173", "http://127.0.0.1:5173")):
                raise HTTPException(403, "This origin is not permitted")
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                raise HTTPException(403, "Cross-site requests are not permitted")
        from app.jobs import is_operation
        operation_path = path.removeprefix("/api") + ("?" + request.url.query if request.url.query else "")
        if request.method == "POST" and path.startswith("/api/") and is_operation(operation_path) and not worker_request.get():
            import json
            data = await request.body()
            try:
                payload = json.loads(data) if data else None
            except ValueError:
                raise HTTPException(422, "Enter valid JSON")
            saved = await run_in_threadpool(enqueue_operation, principal.get(), operation_path, payload, request.headers.get("Idempotency-Key", str(uuid.uuid4())))
            response = JSONResponse({"__job__": saved}, status_code=202)
        else:
            response = await call_next(request)
    except HTTPException as error:
        response = JSONResponse(error_body(request, error.status_code, str(error.detail)), status_code=error.status_code)
    except Exception:
        log.exception("request failed request_id=%s", request.state.request_id)
        response = JSONResponse(error_body(request, 500, "Something went wrong. Try again or share the reference with support."), status_code=500)
    finally:
        if token is not None:
            principal.reset(token)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if protected:
        response.headers["Cache-Control"] = "no-store"
    return response
