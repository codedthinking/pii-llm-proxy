import re
from dataclasses import dataclass
from pathlib import Path

from faker import Faker

from .session import Session

SYSTEM_NOTICE = (
    "All PII in this conversation has been replaced with realistic fake values. "
    "Names, emails, phone numbers, and IDs you see are synthetic — do not treat "
    "them as real. If you use them in tool calls, expect mismatches. "
    "The user sees the real values automatically."
)


def _load_name_set() -> set[str]:
    names_file = Path(__file__).parent / "names.txt"
    if names_file.exists():
        return {line.strip().lower() for line in names_file.read_text().splitlines() if line.strip()}
    return set()


_KNOWN_NAMES: set[str] = _load_name_set()


def _load_notable_people() -> set[str]:
    notable_file = Path(__file__).parent / "notable_people.txt"
    if notable_file.exists():
        return {line.strip() for line in notable_file.read_text().splitlines() if line.strip()}
    return set()


_NOTABLE_PEOPLE: set[str] = _load_notable_people()

_STOP_WORDS: set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "need",
    "dare", "ought", "used", "not", "no", "nor", "so", "yet", "both",
    "each", "few", "more", "most", "other", "some", "such", "than",
    "too", "very", "just", "about", "above", "after", "again", "all",
    "also", "any", "because", "before", "between", "during", "even",
    "every", "get", "got", "here", "how", "if", "into", "its", "let",
    "like", "make", "many", "me", "my", "new", "now", "old", "only",
    "our", "out", "over", "own", "put", "said", "she", "still", "take",
    "tell", "that", "their", "them", "then", "there", "these", "they",
    "this", "those", "through", "under", "until", "upon", "what", "when",
    "where", "which", "while", "who", "whom", "why", "you", "your",
    "hello", "dear", "hi", "hey", "regards", "sincerely", "thanks",
    "thank", "please", "sorry", "yes", "no", "ok", "okay",
    "select", "from", "where", "insert", "update", "delete", "create",
    "table", "index", "view", "join", "left", "right", "inner", "outer",
    "group", "order", "having", "limit", "offset", "union", "case",
    "null", "true", "false", "return", "function", "class", "import",
    "export", "default", "const", "var", "type", "interface", "public",
    "private", "static", "void", "string", "number", "boolean",
    "print", "input", "output", "file", "data", "list", "dict", "set",
    "map", "key", "value", "name", "email", "phone", "address", "city",
    "state", "country", "date", "time", "user", "system", "error",
    "test", "main", "run", "start", "stop", "end", "open", "close",
    "read", "write", "send", "call", "find", "search", "check", "help",
    "save", "load", "add", "remove", "show", "hide", "move", "copy",
}

# Match individual capitalized words (Unicode-aware) — used to build name spans
_CAP_WORD = re.compile(r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+")

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


def _is_sentence_start(text: str, pos: int) -> bool:
    """Check if position is at the start of a sentence."""
    if pos == 0:
        return True
    before = text[:pos].rstrip()
    if not before:
        return True
    return before[-1] in ".!?:;\n"


def _find_name_spans(text: str) -> list[_Match]:
    """Find runs of 2+ consecutive capitalized words where at least one is a known name.

    Skips stop words and sentence-initial words that are only capitalized
    due to position.
    """
    cap_words = list(_CAP_WORD.finditer(text))
    spans = []
    i = 0
    while i < len(cap_words):
        word_lower = cap_words[i].group(0).lower()
        # Skip stop words
        if word_lower in _STOP_WORDS:
            i += 1
            continue
        # Skip sentence-initial words that aren't known names
        # (they're likely capitalized only because of position)
        if word_lower not in _KNOWN_NAMES and _is_sentence_start(text, cap_words[i].start()):
            i += 1
            continue
        # Start building a candidate name span: include adjacent capitalized
        # non-stop words, requiring at least one known name in the group
        run_start = i
        has_known = word_lower in _KNOWN_NAMES
        i += 1
        while i < len(cap_words):
            gap = text[cap_words[i - 1].end() : cap_words[i].start()]
            if gap != " ":
                break
            w = cap_words[i].group(0).lower()
            if w in _STOP_WORDS:
                break
            if w in _KNOWN_NAMES:
                has_known = True
            i += 1
        run_len = i - run_start
        if run_len >= 2 and has_known:
            spans.append(_Match(
                start=cap_words[run_start].start(),
                end=cap_words[i - 1].end(),
                entity_type="PERSON",
            ))
    return spans


def _find_all_matches(text: str) -> list[_Match]:
    matches = []
    for entity_type, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            matches.append(_Match(start=m.start(), end=m.end(), entity_type=entity_type))
    if _KNOWN_NAMES:
        matches.extend(_find_name_spans(text))
    matches.sort(key=lambda m: (m.start, -(m.end - m.start)))
    filtered = []
    last_end = 0
    for m in matches:
        if m.start >= last_end:
            filtered.append(m)
            last_end = m.end
    return filtered


def _make_faker(session: Session) -> Faker:
    seed = int.from_bytes(session.salt[:4], "big")
    fake = Faker()
    fake.seed_instance(seed)
    return fake


_FAKER_GENERATORS: dict[str, str] = {
    "PERSON": "name",
    "EMAIL_ADDRESS": "email",
    "PHONE_NUMBER": "phone_number",
    "US_SSN": "ssn",
    "CREDIT_CARD": "credit_card_number",
    "IBAN_CODE": "iban",
    "DATE_TIME": "date",
}


def _generate_fake(entity_type: str, fake: Faker, existing_fakes: set[str]) -> str:
    method_name = _FAKER_GENERATORS.get(entity_type, "word")
    method = getattr(fake, method_name)
    for _ in range(20):
        value = method()
        if value not in existing_fakes:
            return value
    return method()


def sanitize_text(text: str, session: Session) -> str:
    matches = _find_all_matches(text)
    if not matches:
        return text

    fake = _make_faker(session)
    existing_fakes = set(session.fake_to_real.keys())

    for match in reversed(matches):
        real_value = text[match.start : match.end]
        # Skip notable people (public figures with Wikipedia pages)
        if match.entity_type == "PERSON" and real_value in _NOTABLE_PEOPLE:
            continue
        if real_value in session.real_to_fake:
            fake_value = session.real_to_fake[real_value]
        else:
            fake_value = _generate_fake(match.entity_type, fake, existing_fakes)
            session.real_to_fake[real_value] = fake_value
            session.fake_to_real[fake_value] = real_value
            existing_fakes.add(fake_value)
        text = text[: match.start] + fake_value + text[match.end :]
    return text
