from pathlib import Path

from faker import Faker

from ..session import Session
from .detector import PiiDetector

_NOTICE_FILE = Path(__file__).parent / "system_notice.md"
SYSTEM_NOTICE = _NOTICE_FILE.read_text().strip() if _NOTICE_FILE.exists() else ""

_FAKER_GENERATORS: dict[str, str] = {
    "PERSON": "name",
    "EMAIL_ADDRESS": "email",
    "PHONE_NUMBER": "phone_number",
    "US_SSN": "ssn",
    "CREDIT_CARD": "credit_card_number",
    "IBAN_CODE": "iban",
    "DATE_TIME": "date",
}

_DATA_DIR = Path(__file__).parent / "data"


def _load_notable_people() -> set[str]:
    notable_file = _DATA_DIR / "notable_people.txt"
    if notable_file.exists():
        return {line.strip() for line in notable_file.read_text().splitlines() if line.strip()}
    return set()


class PiiAnonymizer:
    """Session-aware anonymizer that uses a PiiDetector for detection
    and Faker for consistent, reversible replacement.

    Detection algorithm is swappable via the detector parameter.
    Anonymization logic (Faker replacement, session mapping, notable-people
    filtering, desanitization) is shared across all detectors.
    """

    def __init__(
        self,
        detector: PiiDetector,
        notable_people: set[str] | None = None,
    ) -> None:
        self.detector = detector
        self.notable_people = notable_people if notable_people is not None else _load_notable_people()

    def sanitize(self, text: str, session: Session) -> str:
        matches = self.detector.detect(text)
        if not matches:
            return text

        fake = self._make_faker(session)
        existing_fakes = set(session.fake_to_real.keys())

        for match in reversed(matches):
            real_value = text[match.start:match.end]
            if match.entity_type == "PERSON" and real_value in self.notable_people:
                continue
            if real_value in session.real_to_fake:
                fake_value = session.real_to_fake[real_value]
            else:
                fake_value = self._generate_fake(match.entity_type, fake, existing_fakes)
                session.real_to_fake[real_value] = fake_value
                session.fake_to_real[fake_value] = real_value
                existing_fakes.add(fake_value)
            text = text[:match.start] + fake_value + text[match.end:]
        return text

    def desanitize(self, text: str, session: Session) -> str:
        if not session.fake_to_real:
            return text
        for fake_val, real_val in sorted(
            session.fake_to_real.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            text = text.replace(fake_val, real_val)
        return text

    @staticmethod
    def _make_faker(session: Session) -> Faker:
        seed = int.from_bytes(session.salt[:4], "big")
        fake = Faker()
        fake.seed_instance(seed)
        return fake

    @staticmethod
    def _generate_fake(entity_type: str, fake: Faker, existing_fakes: set[str]) -> str:
        method_name = _FAKER_GENERATORS.get(entity_type, "word")
        method = getattr(fake, method_name)
        for _ in range(20):
            value = method()
            if value not in existing_fakes:
                return value
        return method()
