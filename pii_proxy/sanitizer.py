import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .session import Session

SYSTEM_NOTICE = (
    "You are a data analyst working with PII-redacted datasets. "
    'Sensitive fields (names, emails, SSNs, etc.) are replaced with <redacted hash="..." type="..."/> tokens.\n'
    "Key rules:\n"
    "- Always reference hashes when sharing PII — the system translates them back for the user.\n"
    "- The type attribute tells you what kind of PII it is (PERSON, EMAIL_ADDRESS, US_SSN, etc.).\n"
    "- Never guess or fabricate PII values — use the hashes as-is.\n"
    "- When writing SQL or analysis, treat hashes as opaque strings for grouping/filtering.\n"
    "- Non-PII fields (company, job, credit card numbers) are generally safe to reference directly."
)


def _load_name_set() -> set[str]:
    """Load common first/last names from bundled text file."""
    names_file = Path(__file__).parent / "names.txt"
    if names_file.exists():
        return {line.strip().lower() for line in names_file.read_text().splitlines() if line.strip()}
    return set()


_KNOWN_NAMES: set[str] = _load_name_set()

# Match 2-4 consecutive capitalized words (potential person names)
_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]+(?:\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]+){1,3})\b"
)


def _is_person_name(candidate: str) -> bool:
    """Check if at least one word in the candidate matches a known name."""
    words = candidate.lower().split()
    return any(w.rstrip(".") in _KNOWN_NAMES for w in words)


# Compiled regex patterns for each PII type
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL_ADDRESS", re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    )),
    ("PHONE_NUMBER", re.compile(
        r"(?<!\w)"
        r"(?:\+?1[\s.\-]?)?"
        r"(?:\(?\d{3}\)?[\s.\-]?)"
        r"\d{3}[\s.\-]?\d{4}"
        r"(?:\s*(?:x|ext\.?)\s*\d+)?"
        r"(?!\w)"
    )),
    ("PHONE_NUMBER", re.compile(
        r"\+\d{1,3}\d{6,14}\b"
    )),
    ("US_SSN", re.compile(
        r"\b\d{3}[\-]\d{2}[\-]\d{4}\b"
    )),
    ("CREDIT_CARD", re.compile(
        r"\b(?:\d[ \-]?){13,19}\b"
    )),
    ("IBAN_CODE", re.compile(
        r"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?(?:[\dA-Z]{4}[\s]?){1,7}[\dA-Z]{1,4}\b"
    )),
    ("DATE_TIME", re.compile(
        r"\b\d{4}[\-/]\d{2}[\-/]\d{2}\b"
        r"|\b\d{2}[\-/]\d{2}[\-/]\d{4}\b"
    )),
]


@dataclass
class _Match:
    start: int
    end: int
    entity_type: str


def _find_all_matches(text: str) -> list[_Match]:
    matches = []
    # Regex-based PII patterns
    for entity_type, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            matches.append(_Match(start=m.start(), end=m.end(), entity_type=entity_type))
    # Name detection: capitalized word sequences with a known name
    if _KNOWN_NAMES:
        for m in _NAME_PATTERN.finditer(text):
            if _is_person_name(m.group(0)):
                matches.append(_Match(start=m.start(), end=m.end(), entity_type="PERSON"))
    # Remove overlapping matches: keep longest, then earliest
    matches.sort(key=lambda m: (m.start, -(m.end - m.start)))
    filtered = []
    last_end = 0
    for m in matches:
        if m.start >= last_end:
            filtered.append(m)
            last_end = m.end
    return filtered


def _compute_hash(pii_value: str, session: Session) -> str:
    digest = hashlib.sha256(session.salt + pii_value.encode("utf-8")).hexdigest()
    return digest[: settings.hash_hex_chars]


def _make_tag(hash_val: str, entity_type: str) -> str:
    return f'<redacted hash="{hash_val}" type="{entity_type}"/>'


def sanitize_text(text: str, session: Session) -> str:
    matches = _find_all_matches(text)
    # Replace right-to-left to preserve indices
    for match in reversed(matches):
        pii_value = text[match.start : match.end]
        if pii_value in session.pii_to_hash:
            hash_val = session.pii_to_hash[pii_value]
        else:
            hash_val = _compute_hash(pii_value, session)
            session.pii_to_hash[pii_value] = hash_val
            session.hash_to_pii[hash_val] = pii_value
        tag = _make_tag(hash_val, match.entity_type)
        text = text[: match.start] + tag + text[match.end :]
    return text
