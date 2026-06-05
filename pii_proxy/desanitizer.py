"""Backward-compatible wrapper — delegates to pii_proxy.pii."""

from .pii import get_anonymizer
from .session import Session

__all__ = ["desanitize_text"]


def desanitize_text(text: str, session: Session) -> str:
    return get_anonymizer().desanitize(text, session)
