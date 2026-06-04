import hashlib

from presidio_analyzer import AnalyzerEngine

from .config import settings
from .session import Session

SYSTEM_NOTICE = (
    "Some values in this conversation have been redacted for privacy and replaced "
    'with XML tags of the form <redacted hash="..." type="..."/>. '
    "Each unique hash refers to a distinct redacted value. Do not invent or guess "
    "the original values. Treat hashes as opaque identifiers."
)


def _compute_hash(pii_value: str, session: Session) -> str:
    digest = hashlib.sha256(session.salt + pii_value.encode("utf-8")).hexdigest()
    return digest[: settings.hash_hex_chars]


def _make_tag(hash_val: str, entity_type: str) -> str:
    return f'<redacted hash="{hash_val}" type="{entity_type}"/>'


def sanitize_text(text: str, session: Session, analyzer: AnalyzerEngine) -> str:
    results = analyzer.analyze(
        text=text,
        entities=settings.presidio_entities,
        language="en",
    )
    # Sort by start descending so replacements don't shift earlier indices
    results = sorted(results, key=lambda r: r.start, reverse=True)
    for result in results:
        pii_value = text[result.start : result.end]
        if pii_value in session.pii_to_hash:
            hash_val = session.pii_to_hash[pii_value]
        else:
            hash_val = _compute_hash(pii_value, session)
            session.pii_to_hash[pii_value] = hash_val
            session.hash_to_pii[hash_val] = pii_value
        tag = _make_tag(hash_val, result.entity_type)
        text = text[: result.start] + tag + text[result.end :]
    return text
