"""Thin wrapper around the google-genai SDK (Gemini on Vertex AI, or a Gemini API key).

Every call degrades gracefully: if Gemini is not configured or a call fails, callers get
None and fall back to OpEx's deterministic wording. The numbers never come from the LLM.
"""

import json
import logging
import time
from functools import lru_cache

from app.core.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def client():
    from google import genai

    s = get_settings()
    if s.google_genai_use_vertexai:
        log.info("Gemini via Vertex AI (project %s, %s)", s.google_cloud_project, s.google_cloud_location)
        return genai.Client(vertexai=True, project=s.google_cloud_project, location=s.google_cloud_location)
    log.info("Gemini via API key")
    return genai.Client(api_key=s.gemini_api_key)


def enabled() -> bool:
    return get_settings().gemini_enabled


def generate(
    prompt,
    system: str,
    *,
    fast: bool = False,
    json_schema: dict | None = None,
    tools: list | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
):
    """Returns the response text (or parsed JSON when json_schema is given), or None on any failure."""
    if not enabled():
        return None
    from google.genai import types

    s = get_settings()
    model = s.gemini_fast_model if fast else s.gemini_model
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        max_output_tokens=max_tokens,
        response_mime_type="application/json" if json_schema else None,
        response_json_schema=json_schema,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8) if tools else None,
    )
    started = time.perf_counter()
    try:
        response = client().models.generate_content(model=model, contents=prompt, config=config)
        text = response.text or ""
    except Exception as exc:
        log.warning("Gemini call failed (%s): %s", model, exc)
        return None
    log.info("Gemini %s answered in %.1fs", model, time.perf_counter() - started)
    if json_schema:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("Gemini returned invalid JSON")
            return None
    return text.strip()


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]] | None:
    if not enabled() or not texts:
        return None
    from google.genai import types

    try:
        vectors = []
        for start in range(0, len(texts), 100):
            response = client().models.embed_content(
                model=get_settings().gemini_embedding_model,
                contents=texts[start : start + 100],
                config=types.EmbedContentConfig(task_type=task, output_dimensionality=768),
            )
            vectors.extend(e.values for e in response.embeddings)
        return vectors
    except Exception as exc:
        log.warning("Gemini embeddings failed: %s", exc)
        return None
