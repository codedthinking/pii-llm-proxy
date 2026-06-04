import os

from pii_proxy.desanitizer import desanitize_text
from pii_proxy.session import Session


def _make_session_with_mapping(real: str, fake: str) -> Session:
    session = Session(salt=os.urandom(16))
    session.fake_to_real[fake] = real
    session.real_to_fake[real] = fake
    return session


def test_desanitize_fake_name():
    session = _make_session_with_mapping("Miklos Koren", "John Doe")
    text = "Please contact John Doe."
    result = desanitize_text(text, session)
    assert result == "Please contact Miklos Koren."


def test_desanitize_multiple_fakes():
    session = Session(salt=os.urandom(16))
    session.fake_to_real["Alice Smith"] = "Miklos Koren"
    session.fake_to_real["bob@fake.com"] = "real@example.com"
    session.real_to_fake["Miklos Koren"] = "Alice Smith"
    session.real_to_fake["real@example.com"] = "bob@fake.com"

    text = "Alice Smith emailed bob@fake.com."
    result = desanitize_text(text, session)
    assert result == "Miklos Koren emailed real@example.com."


def test_desanitize_empty_session():
    session = Session(salt=os.urandom(16))
    text = "No fakes here."
    result = desanitize_text(text, session)
    assert result == text


def test_longest_match_first():
    """Ensure 'John Doe' is replaced before 'John'."""
    session = Session(salt=os.urandom(16))
    session.fake_to_real["John Doe"] = "Real Person"
    session.fake_to_real["John"] = "Another"
    text = "Hello John Doe."
    result = desanitize_text(text, session)
    assert result == "Hello Real Person."


def test_roundtrip():
    from pii_proxy.sanitizer import sanitize_text

    session = Session(salt=os.urandom(16))
    original = "My email is john@example.com and SSN is 123-45-6789."

    sanitized = sanitize_text(original, session)
    assert "john@example.com" not in sanitized
    assert "123-45-6789" not in sanitized

    restored = desanitize_text(sanitized, session)
    assert "john@example.com" in restored
    assert "123-45-6789" in restored
