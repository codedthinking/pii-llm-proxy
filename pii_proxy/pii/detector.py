from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PiiEntity:
    """A detected PII span in text."""

    start: int
    end: int
    entity_type: str  # "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", etc.
    score: float = 1.0


class PiiDetector(ABC):
    """Abstract interface for PII detection.

    Implementations find PII spans in text. They do NOT handle masking,
    session state, or notable-people filtering — that is the anonymizer's job.
    """

    @abstractmethod
    def detect(self, text: str, language: str = "en") -> list[PiiEntity]:
        """Return all PII entities found in text, sorted by start position.

        Overlapping entities should be resolved (non-overlapping output).
        """
        ...
