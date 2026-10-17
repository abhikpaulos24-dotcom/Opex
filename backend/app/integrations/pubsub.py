"""Optional: publish critical alerts to a Pub/Sub topic so other systems (SMS, WhatsApp,
the maintenance ticketing tool) can subscribe. Does nothing until PUBSUB_ALERTS_TOPIC is set."""

import json
import logging
from functools import lru_cache

from app.core.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def _publisher():
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def publish_alert(payload: dict) -> None:
    settings = get_settings()
    if not (settings.pubsub_alerts_topic and settings.google_cloud_project):
        return
    try:
        topic = _publisher().topic_path(settings.google_cloud_project, settings.pubsub_alerts_topic)
        _publisher().publish(topic, json.dumps(payload).encode(), severity=payload.get("severity", ""))
    except Exception as exc:  # an alert channel being down must never break the app
        log.warning("Pub/Sub publish failed: %s", exc)
