"""File storage: Cloud Storage when GCS_BUCKET is set, otherwise the local storage/ folder."""

import logging
from functools import lru_cache

from app.core.config import get_settings
from app.core.paths import STORAGE_DIR

log = logging.getLogger(__name__)


@lru_cache
def _bucket():
    from google.cloud import storage

    return storage.Client(project=get_settings().google_cloud_project or None).bucket(get_settings().gcs_bucket)


def save(path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Save a file and return where it went (gs:// URI or local path)."""
    if get_settings().gcs_bucket:
        try:
            _bucket().blob(path).upload_from_string(data, content_type=content_type)
            return f"gs://{get_settings().gcs_bucket}/{path}"
        except Exception as exc:
            log.warning("Cloud Storage upload failed, keeping a local copy: %s", exc)
    target = STORAGE_DIR / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return str(target)
