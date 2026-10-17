import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai import agents, copilot
from app.analytics.factory_report import factory_report
from app.auth.deps import current_user
from app.db.models import User
from app.db.session import get_db
from app.plant.live import get_plant

router = APIRouter(prefix="/api/copilot", tags=["copilot"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = []
    language: str = "en"
    simple: bool = False
    image_base64: str | None = None
    image_type: str | None = None


@router.post("/chat")
def chat(body: ChatIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    image = None
    if body.image_base64:
        if body.image_type not in ("image/jpeg", "image/png", "image/webp"):
            raise HTTPException(400, "Photos must be JPG, PNG or WEBP.")
        try:
            data = base64.b64decode(body.image_base64.split(",")[-1], validate=True)
        except (binascii.Error, ValueError) as err:
            raise HTTPException(400, "The photo could not be read.") from err
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Photos must be under 5 MB.")
        image = (data, body.image_type)
    return copilot.answer(db, body.message, body.history, body.language, body.simple, image)


_briefings: dict[tuple, dict] = {}


@router.post("/briefing")
def briefing(language: str = "en", simple: bool = False, _: User = Depends(current_user)):
    """Gemini-written shift handover, reused for 30 plant minutes to save free-tier quota."""
    key = (language, simple, get_plant().minute // 30)
    if key not in _briefings:
        _briefings.clear()
        _briefings[key] = agents.shift_briefing(factory_report(), language, simple)
    return _briefings[key]
