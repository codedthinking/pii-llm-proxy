import os
import threading
from dataclasses import dataclass, field
from datetime import datetime

from cachetools import TTLCache

from .config import settings


@dataclass
class Session:
    salt: bytes
    real_to_fake: dict[str, str] = field(default_factory=dict)
    fake_to_real: dict[str, str] = field(default_factory=dict)
    system_notice_injected: bool = False
    created_at: datetime = field(default_factory=datetime.now)


class SessionStore:
    def __init__(self) -> None:
        self._cache: TTLCache[str, Session] = TTLCache(
            maxsize=1024, ttl=settings.session_ttl_seconds
        )
        self._lock = threading.Lock()

    def get_or_create(self, conversation_id: str) -> Session:
        with self._lock:
            if conversation_id in self._cache:
                return self._cache[conversation_id]
            session = Session(salt=os.urandom(settings.salt_length_bytes))
            self._cache[conversation_id] = session
            return session

    def get(self, conversation_id: str) -> Session | None:
        with self._lock:
            return self._cache.get(conversation_id)
