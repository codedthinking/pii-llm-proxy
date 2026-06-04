import os

from pii_proxy.sanitizer import sanitize_text
from pii_proxy.session import Session


def _make_session() -> Session:
    return Session(salt=os.urandom(16))


def test_person_name_is_redacted():
    session = _make_session()
    text = "Please contact John Smith about the project."
    result = sanitize_text(text, session)
    assert "John Smith" not in result
    assert 'type="PERSON"' in result


def test_email_is_redacted():
    session = _make_session()
    text = "Send it to john.doe@example.com please."
    result = sanitize_text(text, session)
    assert "john.doe@example.com" not in result
    assert 'type="EMAIL_ADDRESS"' in result


def test_phone_is_redacted():
    session = _make_session()
    text = "Call me at 555-123-4567."
    result = sanitize_text(text, session)
    assert "555-123-4567" not in result
    assert 'type="PHONE_NUMBER"' in result


def test_international_phone_is_redacted():
    session = _make_session()
    text = "Call me at +36705374124."
    result = sanitize_text(text, session)
    assert "+36705374124" not in result
    assert 'type="PHONE_NUMBER"' in result


def test_ssn_is_redacted():
    session = _make_session()
    text = "My SSN is 123-45-6789."
    result = sanitize_text(text, session)
    assert "123-45-6789" not in result
    assert 'type="US_SSN"' in result


def test_credit_card_is_redacted():
    session = _make_session()
    text = "Card number 4111111111111111."
    result = sanitize_text(text, session)
    assert "4111111111111111" not in result
    assert 'type="CREDIT_CARD"' in result


def test_date_is_redacted():
    session = _make_session()
    text = "Born on 1983-09-11."
    result = sanitize_text(text, session)
    assert "1983-09-11" not in result
    assert 'type="DATE_TIME"' in result


def test_dedup_same_value_same_hash():
    session = _make_session()
    text = "Email john@example.com and also john@example.com again."
    result = sanitize_text(text, session)
    assert len(session.pii_to_hash) == 1
    assert "john@example.com" in session.pii_to_hash


def test_cross_session_different_hash():
    s1 = _make_session()
    s2 = _make_session()
    text = "Email john@example.com."
    sanitize_text(text, s1)
    sanitize_text(text, s2)
    hash1 = s1.pii_to_hash.get("john@example.com")
    hash2 = s2.pii_to_hash.get("john@example.com")
    assert hash1 is not None
    assert hash2 is not None
    assert hash1 != hash2


def test_no_pii_unchanged():
    session = _make_session()
    text = "The weather is nice in the morning."
    result = sanitize_text(text, session)
    assert result == text
    assert len(session.pii_to_hash) == 0
