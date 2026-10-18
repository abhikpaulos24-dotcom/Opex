"""Google sign-in: the browser gets a signed ID token from Google, and we check it here."""

import logging

from fastapi import HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import get_settings

log = logging.getLogger(__name__)


def verified_google_account(credential: str) -> tuple[str, str]:
    """Returns (email, name) for a valid Google ID token made for this app, else raises 401/503."""
    client_id = get_settings().google_oauth_client_id
    if not client_id:
        raise HTTPException(503, "Google sign-in is not set up yet. The master admin can add it (see AUDIT.md).")
    try:
        claims = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    except ValueError as err:  # bad signature, wrong app, expired
        log.warning("rejected a Google token: %s", err)
        raise HTTPException(401, "Google could not confirm your sign-in. Please try again.") from err
    if not claims.get("email_verified"):
        raise HTTPException(401, "Your Google email address is not verified.")
    return claims["email"].lower(), claims.get("name") or claims["email"].split("@")[0]
