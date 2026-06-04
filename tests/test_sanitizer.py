import os

from pii_proxy.sanitizer import sanitize_text
from pii_proxy.session import Session


def _make_session() -> Session:
    return Session(salt=os.urandom(16))


def test_person_name_is_replaced():
    session = _make_session()
    text = "Please contact John Smith about the project."
    result = sanitize_text(text, session)
    assert "John Smith" not in result
    assert "PERSON" not in result  # no XML tags
    assert len(session.real_to_fake) == 1
    fake_name = session.real_to_fake["John Smith"]
    assert fake_name in result


def test_email_is_replaced():
    session = _make_session()
    text = "Send it to john.doe@example.com please."
    result = sanitize_text(text, session)
    assert "john.doe@example.com" not in result
    assert "@" in result  # fake email still has @


def test_phone_is_replaced():
    session = _make_session()
    text = "Call me at 555-123-4567."
    result = sanitize_text(text, session)
    assert "555-123-4567" not in result


def test_international_phone_is_replaced():
    session = _make_session()
    text = "Call me at +36705374124."
    result = sanitize_text(text, session)
    assert "+36705374124" not in result


def test_ssn_is_replaced():
    session = _make_session()
    text = "My SSN is 123-45-6789."
    result = sanitize_text(text, session)
    assert "123-45-6789" not in result


def test_credit_card_is_replaced():
    session = _make_session()
    text = "Card number 4111111111111111."
    result = sanitize_text(text, session)
    assert "4111111111111111" not in result


def test_date_is_replaced():
    session = _make_session()
    text = "Born on 1983-09-11."
    result = sanitize_text(text, session)
    assert "1983-09-11" not in result


def test_dedup_same_value_same_fake():
    session = _make_session()
    text = "Email john@example.com and also john@example.com again."
    result = sanitize_text(text, session)
    assert len(session.real_to_fake) == 1
    fake = session.real_to_fake["john@example.com"]
    assert result.count(fake) == 2


def test_cross_session_different_fake():
    s1 = _make_session()
    s2 = _make_session()
    text = "Email john@example.com."
    sanitize_text(text, s1)
    sanitize_text(text, s2)
    fake1 = s1.real_to_fake.get("john@example.com")
    fake2 = s2.real_to_fake.get("john@example.com")
    assert fake1 is not None
    assert fake2 is not None
    # Different salts → different fakes (with overwhelming probability)
    assert fake1 != fake2


def test_no_pii_unchanged():
    session = _make_session()
    text = "The weather is nice in the morning."
    result = sanitize_text(text, session)
    assert result == text
    assert len(session.real_to_fake) == 0
