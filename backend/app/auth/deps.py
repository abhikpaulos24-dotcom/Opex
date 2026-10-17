from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db

from .security import COOKIE_NAME, can, decode_token


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    header = request.headers.get("authorization", "")
    if not token and header.lower().startswith("bearer "):
        token = header[7:]
    claims = decode_token(token) if token else None
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    user = db.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your account is not active.")
    return user


def require(permission: str):
    def checker(user: User = Depends(current_user)) -> User:
        if not can(user.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this. Ask a plant manager.")
        return user

    return checker
