"""The plant only changes once a plant minute, so every report is cached for that minute."""

import threading
from collections.abc import Callable

from app.plant.live import get_plant

_cache: dict = {}
_lock = threading.Lock()


def cached_for_this_minute(key: tuple, build: Callable[[], dict]) -> dict:
    minute = get_plant().minute
    with _lock:
        if (key, minute) in _cache:
            return _cache[(key, minute)]
    value = build()
    with _lock:
        if len(_cache) > 1000:
            _cache.clear()
        _cache[(key, minute)] = value
    return value
