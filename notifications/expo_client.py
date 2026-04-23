# notifications/expo_client.py
from __future__ import annotations
import logging, requests
from typing import Iterable, Mapping, Any, List

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
DEFAULT_TIMEOUT = 10

class ExpoClient:
    def __init__(self, base_url: str = EXPO_PUSH_URL, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self._session = requests.Session()

    def send(self, messages: Iterable[Mapping[str, Any]]) -> bool:
        """Best-effort fire-and-forget. Returns True if POST didn’t raise."""
        msgs: List[dict] = [dict(m) for m in messages]
        if not msgs:
            return True
        try:
            resp = self._session.post(self.base_url, json=msgs, timeout=self.timeout)
            # Expo returns 200 even with per-message errors; you can inspect resp.json() if you like.
            if resp.status_code != 200:
                logger.warning("Expo returned %s: %s", resp.status_code, resp.text[:500])
            return True
        except Exception as e:
            logger.exception("Expo push failed: %s", e)
            return False
