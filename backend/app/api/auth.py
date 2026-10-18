import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require
from app.auth.google import verified_google_account
from app.auth.security import (
    COOKIE_NAME,
    PERMISSIONS,
    ROLE_LABELS,
    SESSION_HOURS,
    create_token,
    manageable_roles,
    verify_password,
)
from app.core.config import get_settings
from app.db.models import AuditLog, User, now_utc
from app.db.seed import unusable_password
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])
_attempts: dict[str, list[float]] = defaultdict(list)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20)  # the ID token Google gives the browser


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


def _rate_limit(key: str, limit: int = 8) -> None:
    now = time.monotonic()
    _attempts[key] = [t for t in _attempts[key] if now - t < 300]
    if len(_attempts[key]) >= limit:
        raise HTTPException(429, "Too many sign-in attempts. Please wait 5 minutes.")
    _attempts[key].append(now)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Password sign-in exists only for the demo accounts. Everyone else uses Google."""
    if not get_settings().demo_mode:
        raise HTTPException(404, "Please sign in with Google.")
    _rate_limit(f"{request.client.host if request.client else '-'}:{body.email.lower()}")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "That email and password don't match.")
    if not user.is_active:
        raise HTTPException(403, "This account has been switched off. Ask your plant manager.")
    log.info("sign-in %s (%s)", user.email, user.role)
    return _start_session(response, user, db)


@router.post("/google")
def google_sign_in(body: GoogleIn, request: Request, response: Response, db: Session = Depends(get_db)):
    # Tokens are checked cryptographically, so guessing is pointless; the limit is generous because a whole
    # shift may sign in from one office address.
    _rate_limit(f"google:{request.client.host if request.client else '-'}", limit=60)
    email, name = verified_google_account(body.credential)
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == email))
    if email == settings.master_admin_email.lower():
        if user is None:
            user = User(email=email, full_name=name, password_hash=unusable_password(), preferences={})
            db.add(user)
        user.role, user.is_active = "manager", True  # the first manager can never be demoted or switched off
    elif user is None:
        raise HTTPException(403, "This Google account has not been added yet. Ask your plant manager.")
    elif not user.is_active:
        raise HTTPException(403, "This account has been switched off. Ask your plant manager.")
    db.commit()
    log.info("google sign-in %s (%s)", user.email, user.role)
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


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None


def _person(user: User) -> dict:
    """What a manager sees about someone they manage: who they are, never their settings."""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "role_label": ROLE_LABELS[user.role],
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
    }


@users_router.get("")
def list_users(admin: User = Depends(require("manage_users")), db: Session = Depends(get_db)):
    below = manageable_roles(admin.role)
    retired_demo = [
        "operator@opex.demo",
        "viewer@opex.demo",
        "guest@opex.demo",
    ]  # switched off when the roles were cut to two
    query = select(User).where(User.role.in_(below), User.email.not_in(retired_demo)).order_by(User.created_at)
    users = db.scalars(query).all()
    return {"manageable_roles": sorted(below), "people": [_person(u) for u in users]}


@users_router.post("")
def create_user(body: UserIn, admin: User = Depends(require("manage_users")), db: Session = Depends(get_db)):
    if body.role not in manageable_roles(admin.role):
        raise HTTPException(
            403, f"As {ROLE_LABELS[admin.role]} you can only add: {', '.join(sorted(manageable_roles(admin.role)))}."
        )
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "That email already has an account.")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        role=body.role,
        password_hash=unusable_password(),  # they sign in with this Google account
        preferences={},
    )
    db.add(user)
    db.add(AuditLog(user_email=admin.email, action="user.create", target=user.email, details={"role": body.role}))
    db.commit()
    return _person(user)


@users_router.patch("/{user_id}")
def update_user(
    user_id: str, body: UserPatch, admin: User = Depends(require("manage_users")), db: Session = Depends(get_db)
):
    below = manageable_roles(admin.role)
    user = db.get(User, user_id)
    if not user or user.role not in below:
        raise HTTPException(404, "No such user.")
    if user.id == admin.id or user.email == get_settings().master_admin_email.lower():
        raise HTTPException(
            403, "You can't change your own role or switch yourself off. That keeps a manager in place."
        )
    if body.role is not None:
        if body.role not in below:
            raise HTTPException(403, f"You can only give these roles: {', '.join(sorted(below))}.")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.add(AuditLog(user_email=admin.email, action="user.update", target=user.email, details=body.model_dump()))
    db.commit()
    return _person(user)
