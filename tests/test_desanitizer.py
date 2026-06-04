import os

from pii_proxy.desanitizer import desanitize_text
from pii_proxy.session import Session


def _make_session_with_mapping(pii: str, hash_val: str) -> Session:
    session = Session(salt=os.urandom(16))
    session.hash_to_pii[hash_val] = pii
    session.pii_to_hash[pii] = hash_val
    return session


def test_desanitize_full_tag():
    session = _make_session_with_mapping("John Smith", "abc123def456")
    text = 'Please contact <redacted hash="abc123def456" type="PERSON"/>.'
    result = desanitize_text(text, session)
    assert result == "Please contact John Smith."


def test_desanitize_bare_hash():
    session = _make_session_with_mapping("John Smith", "abc123def456")
    text = "The person abc123def456 said hello."
    result = desanitize_text(text, session)
    assert result == "The person John Smith said hello."


def test_desanitize_multiple_hashes():
    session = Session(salt=os.urandom(16))
    session.hash_to_pii["aaa111bbb222"] = "Alice"
    session.hash_to_pii["ccc333ddd444"] = "Bob"
    session.pii_to_hash["Alice"] = "aaa111bbb222"
    session.pii_to_hash["Bob"] = "ccc333ddd444"

    text = '<redacted hash="aaa111bbb222" type="PERSON"/> called <redacted hash="ccc333ddd444" type="PERSON"/>.'
    result = desanitize_text(text, session)
    assert result == "Alice called Bob."


def test_desanitize_empty_session():
    session = Session(salt=os.urandom(16))
    text = "No hashes here."
    result = desanitize_text(text, session)
    assert result == text


def test_roundtrip():
    """Sanitize then desanitize should recover original PII values."""
    from presidio_analyzer import AnalyzerEngine
    from pii_proxy.sanitizer import sanitize_text

    analyzer = AnalyzerEngine()
    session = Session(salt=os.urandom(16))
    original = "My name is John Smith and my email is john@example.com."

    sanitized = sanitize_text(original, session, analyzer)
    assert "John Smith" not in sanitized
    assert "john@example.com" not in sanitized

    restored = desanitize_text(sanitized, session)
    assert "John Smith" in restored
    assert "john@example.com" in restored
