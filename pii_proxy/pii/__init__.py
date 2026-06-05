from .anonymizer import SYSTEM_NOTICE, PiiAnonymizer
from .detector import PiiDetector, PiiEntity
from .regex_detector import RegexPiiDetector

_anonymizer: PiiAnonymizer | None = None


def get_anonymizer() -> PiiAnonymizer:
    """Return the singleton PiiAnonymizer instance."""
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = PiiAnonymizer(detector=RegexPiiDetector())
    return _anonymizer


__all__ = [
    "SYSTEM_NOTICE",
    "PiiAnonymizer",
    "PiiDetector",
    "PiiEntity",
    "RegexPiiDetector",
    "get_anonymizer",
]
