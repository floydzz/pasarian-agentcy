"""Initial owner setup, login, workspace membership and session management."""
from datetime import timedelta
import hmac
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import get_settings
from app.db import get_db
from app.models import LoginAttempt, LoginSession, Membership, User, Workspace
from app.security import COOKIE, bootstrap_file, digest, hash_password, verify_password
from app.workspace import principal

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if value.count("@") != 1 or "." not in value.split("@")[-1] or any(c.isspace() for c in value):
            raise ValueError("Enter a valid email address")
        return value


class OwnerSetup(Credentials):
    name: str = Field(min_length=1, max_length=120)
    workspace_name: str = Field(min_length=1, max_length=200)
    setup_token: str = Field(min_length=20, max_length=100)


class MemberCreate(Credentials):
    password: str | None = Field(default=None, min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["editor", "reviewer", "viewer"] = "editor"


def identity(db, saved):
    user = db.get(User, saved.user_id)
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == saved.workspace_id))
    workspaces = db.execute(select(Workspace, Membership.role).join(Membership, Membership.workspace_id == Workspace.id).where(Membership.user_id == user.id)).all()
    return {"user": {"id": user.id, "email": user.email, "name": user.name}, "workspace_id": saved.workspace_id,
            "role": membership.role, "csrf_token": saved.csrf,
            "workspaces": [{"id": row.id, "name": row.name, "role": role} for row, role in workspaces]}


def issue_session(db, response, user, workspace_id):
    raw = secrets.token_urlsafe(32)
    saved = LoginSession(user_id=user.id, workspace_id=workspace_id, token_hash=digest(raw), csrf=secrets.token_urlsafe(32),
                         expires_at=utcnow() + timedelta(hours=get_settings().session_hours), last_seen=utcnow())
    db.add(saved); db.commit()
    response.set_cookie(COOKIE, raw, httponly=True, secure=get_settings().session_secure, samesite="lax", max_age=get_settings().session_hours * 3600, path="/")
    return identity(db, saved)


def throttle(db, request, label):
    # Persisted in MySQL: attempts cannot be reset by switching web workers.
    key = digest(f"{request.client.host if request.client else 'local'}:{label}")
    row = db.scalar(select(LoginAttempt).where(LoginAttempt.key == key).with_for_update())
    now = utcnow()
    if not row:
        row = LoginAttempt(key=key, failures=0, reset_at=now + timedelta(minutes=15)); db.add(row)
    elif row.reset_at <= now:
        row.failures, row.reset_at = 0, now + timedelta(minutes=15)
    if row.failures >= get_settings().auth_login_limit:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    row.failures += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(429, "Please wait before trying again")
    return row


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {"setup_required": db.scalar(select(Membership.id).where(Membership.workspace_id == 1, Membership.role == "owner").limit(1)) is None}


@router.post("/setup")
def setup(payload: OwnerSetup, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, request, "setup")
    path = bootstrap_file()
    if not path.exists() or not hmac.compare_digest(payload.setup_token, path.read_text().strip()):
        raise HTTPException(403, "The setup code is invalid")
    workspace = db.scalar(select(Workspace).where(Workspace.id == 1).with_for_update())
    if workspace is None:
        raise HTTPException(503, "Database setup is incomplete")
    if db.scalar(select(Membership.id).where(Membership.workspace_id == 1, Membership.role == "owner")):
        raise HTTPException(409, "An owner is already configured. Sign in instead.")
    user = User(email=payload.email, name=payload.name.strip(), password_hash=hash_password(payload.password))
    workspace.name = payload.workspace_name.strip()
    db.add(user)
    try:
        db.flush(); db.add(Membership(user_id=user.id, workspace_id=1, role="owner")); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "This account could not be created")
    return issue_session(db, response, user, 1)


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    attempt = throttle(db, request, "login")
    user = db.scalar(select(User).where(User.email == payload.email))
    # Perform the same expensive hash for unknown accounts.
    stored = user.password_hash if user else "scrypt$" + "0" * 32 + "$" + "0" * 128
    valid = verify_password(payload.password, stored)
    if not user or user.disabled or not valid:
        raise HTTPException(401, "Email or password is incorrect")
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id).limit(1))
    if not membership:
        raise HTTPException(403, "This account has no workspace access")
    attempt.failures = 0
    return issue_session(db, response, user, membership.workspace_id)


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    saved = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(request.cookies.get(COOKIE, ""))))
    return identity(db, saved)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(request.cookies.get(COOKIE, ""))))
    db.commit(); response.delete_cookie(COOKIE, path="/")


class WorkspaceWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/workspaces", status_code=201)
def new_workspace(payload: WorkspaceWrite, db: Session = Depends(get_db)):
    if principal.get().role != "owner":
        raise HTTPException(403, "Only workspace owners can create another workspace")
    row = Workspace(name=payload.name.strip()); db.add(row); db.flush()
    db.add(Membership(user_id=principal.get().user_id, workspace_id=row.id, role="owner")); db.commit()
    return {"id": row.id, "name": row.name}


@router.post("/workspaces/{workspace_id}/switch")
def switch(workspace_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    actor = principal.get()
    if not db.scalar(select(Membership.id).where(Membership.user_id == actor.user_id, Membership.workspace_id == workspace_id)):
        raise HTTPException(404, "Workspace not found")
    db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(request.cookies.get(COOKIE, ""))))
    return issue_session(db, response, db.get(User, actor.user_id), workspace_id)


@router.get("/members")
def members(db: Session = Depends(get_db)):
    actor = principal.get()
    if actor.role != "owner":
        raise HTTPException(403, "Only the owner can manage members")
    return [{"id": member.id, "name": user.name, "email": user.email, "role": member.role} for member, user in db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.workspace_id == actor.workspace_id))]


@router.post("/members", status_code=201)
def add_member(payload: MemberCreate, db: Session = Depends(get_db)):
    actor = principal.get()
    if actor.role != "owner":
        raise HTTPException(403, "Only the owner can manage members")
    user = db.scalar(select(User).where(User.email == payload.email))
    existing = user is not None
    if user and user.disabled:
        raise HTTPException(409, "This account is unavailable")
    if user and db.scalar(select(Membership.id).where(Membership.user_id == user.id, Membership.workspace_id == actor.workspace_id)):
        raise HTTPException(409, "This account already has workspace access")
    if not user and payload.password is None:
        raise HTTPException(422, "An initial password of at least 12 characters is required for a new account")
    try:
        if not user:
            user = User(email=payload.email, name=payload.name.strip(), password_hash=hash_password(payload.password))
            db.add(user); db.flush()
        # Grant workspace access without changing an existing account's identity
        # or credentials; removed members can safely be added again.
        row = Membership(user_id=user.id, workspace_id=actor.workspace_id, role=payload.role)
        db.add(row); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Account access changed. Refresh the member list and try again.")
    return {"id": row.id, "email": user.email, "name": user.name, "role": row.role, "existing_account": existing}



@router.delete("/members/{member_id}", status_code=204)
def remove_member(member_id: int, db: Session = Depends(get_db)):
    actor = principal.get()
    row = db.scalar(select(Membership).where(Membership.id == member_id, Membership.workspace_id == actor.workspace_id))
    if actor.role != "owner":
        raise HTTPException(403, "Only the owner can manage members")
    if not row:
        raise HTTPException(404, "Member not found")
    if row.role == "owner":
        raise HTTPException(409, "The workspace owner cannot be removed")
    db.execute(delete(LoginSession).where(LoginSession.user_id == row.user_id, LoginSession.workspace_id == actor.workspace_id))
    db.delete(row); db.commit()


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


@router.post("/password", status_code=204)
def change_password(payload: PasswordChange, db: Session = Depends(get_db)):
    user = db.get(User, principal.get().user_id)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id)); db.commit()
