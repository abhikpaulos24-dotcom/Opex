"""Photo quality check: Gemini looks at a picture of a machined part.

The answer is linked to what the machine's sensors say right now, so "chatter marks on the
bore" plus "vibration 148% above normal" points at the spindle bearing, not at the tool.
A photo is not a measurement: anything marked 'reject' still goes to the gauge or CMM.
"""

import json

from . import gemini
from .agents import LANGUAGES

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["looks_good", "check_on_gauge", "reject"]},
        "summary": {"type": "string"},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "where": {"type": "string"},
                    "severity": {"type": "string", "enum": ["minor", "major", "critical"]},
                },
                "required": ["type", "where", "severity"],
            },
        },
        "likely_machine_cause": {"type": "string"},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "summary", "defects", "likely_machine_cause", "next_steps"],
}


def inspect_part(image: bytes, mime_type: str, report: dict, language: str = "en") -> dict:
    if not gemini.enabled():
        return {"available": False, "message": "Photo checks need Gemini. Add a free key (AUDIT.md, step 3)."}
    from google.genai import types

    context = {
        "machine": report["machine"],
        "abnormal_signals": [a["sentence"] for a in report["anomalies"][:4]],
        "likely_cause_from_sensors": report["root_cause"]["top"]["name"] if report["root_cause"]["top"] else None,
    }
    prompt = [
        types.Part.from_text(text=f"Inspect this machined part. Machine context: {json.dumps(context)}"),
        types.Part.from_bytes(data=image, mime_type=mime_type),
    ]
    result = gemini.generate(
        prompt,
        system="You are a quality inspector in a CNC automotive-component plant. Describe only defects you can "
        "actually see (burrs, chatter marks, burns, cracks, dents, poor surface finish, wrong colour from heat). "
        "If the photo is unclear or not a machined part, say so and use 'check_on_gauge'. Link what you see to the "
        "machine context when it fits, otherwise say the cause is unclear. Never invent measurements. "
        f"Answer in {LANGUAGES.get(language, 'English')}.",
        json_schema=SCHEMA,
        fast=True,
    )
    if result is None:
        return {"available": False, "message": "Gemini could not check this photo right now. Try again in a minute."}
    return {"available": True, **result}
