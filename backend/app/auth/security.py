"""Passwords (bcrypt), session tokens (signed JWT in an httpOnly cookie) and roles."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

COOKIE_NAME = "opex_session"
SESSION_HOURS = 12
ROLE_LABELS = {
    "manager": "Plant manager",
    "engineer": "Maintenance engineer",
}

# Two roles. Engineers make the day-to-day decisions (approve or reject any action, write investigations,
# add documents). Managers do all of that and also run the plant: people, priorities, costs and demo controls.
PERMISSIONS = {
    "acknowledge_alert": {"manager", "engineer"},
    "decide_minor": {"manager", "engineer"},
    "decide_major": {"manager", "engineer"},
    "manage_knowledge": {"manager", "engineer"},
    "write_report": {"manager", "engineer"},
    "manage_users": {"manager"},
    "edit_settings": {"manager"},
    "demo_controls": {"manager"},
}
# Managers add and manage people in either role.
MANAGEABLE_ROLES = {"manager": {"manager", "engineer"}}
MINOR_ACTIONS = {
    "change_tool",
    "standby",
    "increase_monitoring",
    "recalibrate_sensor",
    "continue_tool",
    "leave_idle_running",
    "ignore_sensor",
}


def manageable_roles(role: str) -> set[str]:
    return MANAGEABLE_ROLES.get(role, set())


def can(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())


def permission_to_approve(action_key: str) -> str:
    return "decide_minor" if action_key in MINOR_ACTIONS else "decide_major"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: str, role: str) -> str:
    payload = {"sub": user_id, "role": role, "exp": datetime.now(UTC) + timedelta(hours=SESSION_HOURS)}
    return jwt.encode(payload, get_settings().secret_key, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
