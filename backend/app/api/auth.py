import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require
from app.auth.security import (
    COOKIE_NAME,
    PERMISSIONS,
    ROLE_LABELS,
    ROLES,
    SESSION_HOURS,
    create_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.db.models import AuditLog, User, now_utc
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])
_attempts: dict[str, list[float]] = defaultdict(list)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=120)


class PreferencesIn(BaseModel):
    preferences: dict


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "role_label": ROLE_LABELS[user.role],
        "preferences": user.preferences or {},
        "permissions": sorted(p for p, roles in PERMISSIONS.items() if user.role in roles),
    }


def _start_session(response: Response, user: User, db: Session) -> dict:
    user.last_login_at = now_utc()
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        create_token(user.id, user.role),
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
    )
    return user_out(user)


def _rate_limit(key: str) -> None:
    now = time.monotonic()
    _attempts[key] = [t for t in _attempts[key] if now - t < 300]
    if len(_attempts[key]) >= 8:
        raise HTTPException(429, "Too many sign-in attempts. Please wait 5 minutes.")
    _attempts[key].append(now)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _rate_limit(f"{request.client.host if request.client else '-'}:{body.email.lower()}")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "That email and password don't match.")
    if not user.is_active:
        raise HTTPException(403, "This account has been switched off. Ask your plant manager.")
    log.info("sign-in %s (%s)", user.email, user.role)
    return _start_session(response, user, db)


@router.post("/guest")
def guest(response: Response, db: Session = Depends(get_db)):
    """One-click read-only access for judges and visitors (demo mode only)."""
    if not get_settings().demo_mode:
        raise HTTPException(404, "Guest access is off.")
    user = db.scalar(select(User).where(User.email == "viewer@opex.demo"))
    if not user:
        raise HTTPException(503, "Guest account missing.")
    return _start_session(response, user, db)


@router.post("/signup")
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
    if not get_settings().allow_signup:
        raise HTTPException(403, "Sign-up is closed. Ask your plant manager for an account.")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name.strip(),
        role="viewer",
        password_hash=hash_password(body.password),
        preferences={},
    )
    db.add(user)
    db.add(AuditLog(user_email=user.email, action="user.signup"))
    db.commit()
    return _start_session(response, user, db)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.put("/me/preferences")
def save_preferences(body: PreferencesIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.preferences = {k: v for k, v in body.preferences.items() if isinstance(v, (str, bool, int, float))}
    db.commit()
    return user_out(user)


class UserIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2)
    role: str
    password: str = Field(min_length=8)


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@users_router.get("")
def list_users(_: User = Depends(require("manage_users")), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return [{**user_out(u), "is_active": u.is_active, "last_login_at": u.last_login_at} for u in users]


@users_router.post("")
def create_user(body: UserIn, admin: User = Depends(require("manage_users")), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(400, "Unknown role.")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "That email already has an account.")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        role=body.role,
        password_hash=hash_password(body.password),
        preferences={},
    )
    db.add(user)
    db.add(AuditLog(user_email=admin.email, action="user.create", target=user.email, details={"role": body.role}))
    db.commit()
    return user_out(user)


@users_router.patch("/{user_id}")
def update_user(
    user_id: str, body: UserPatch, admin: User = Depends(require("manage_users")), db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such user.")
    if user.id == admin.id and (body.role not in (None, "manager") or body.is_active is False):
        raise HTTPException(400, "You cannot remove your own manager access.")
    if body.role:
        if body.role not in ROLES:
            raise HTTPException(400, "Unknown role.")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.add(AuditLog(user_email=admin.email, action="user.update", target=user.email, details=body.model_dump()))
    db.commit()
    return user_out(user)
