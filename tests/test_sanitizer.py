import os

from presidio_analyzer import AnalyzerEngine

from pii_proxy.sanitizer import sanitize_text
from pii_proxy.session import Session


analyzer = AnalyzerEngine()


def _make_session() -> Session:
    return Session(salt=os.urandom(16))


def test_person_name_is_redacted():
    session = _make_session()
    text = "Please contact John Smith about the project."
    result = sanitize_text(text, session, analyzer)
    assert "John Smith" not in result
    assert '<redacted hash="' in result
    assert 'type="PERSON"' in result


def test_email_is_redacted():
    session = _make_session()
    text = "Send it to john.doe@example.com please."
    result = sanitize_text(text, session, analyzer)
    assert "john.doe@example.com" not in result
    assert 'type="EMAIL_ADDRESS"' in result


def test_phone_is_redacted():
    session = _make_session()
    text = "Call me at 555-123-4567."
    result = sanitize_text(text, session, analyzer)
    assert "555-123-4567" not in result
    assert 'type="PHONE_NUMBER"' in result


def test_dedup_same_name_same_hash():
    session = _make_session()
    text = "John Smith met John Smith at the park."
    result = sanitize_text(text, session, analyzer)
    # Should produce the same hash for both occurrences
    assert len(session.pii_to_hash) == 1
    assert "John Smith" in session.pii_to_hash


def test_cross_session_different_hash():
    s1 = _make_session()
    s2 = _make_session()
    text = "John Smith is here."
    sanitize_text(text, s1, analyzer)
    sanitize_text(text, s2, analyzer)
    hash1 = s1.pii_to_hash.get("John Smith")
    hash2 = s2.pii_to_hash.get("John Smith")
    assert hash1 is not None
    assert hash2 is not None
    # Different salts → different hashes (with overwhelming probability)
    assert hash1 != hash2


def test_no_pii_unchanged():
    session = _make_session()
    text = "The weather is nice in the morning."
    result = sanitize_text(text, session, analyzer)
    assert result == text
    assert len(session.pii_to_hash) == 0
