"""Backward-compatible wrapper — delegates to pii_proxy.pii."""

from .pii import SYSTEM_NOTICE, get_anonymizer
from .session import Session

__all__ = ["SYSTEM_NOTICE", "sanitize_text"]


def sanitize_text(text: str, session: Session) -> str:
    return get_anonymizer().sanitize(text, session)
