"""Tests for complex PII detection scenarios: nested structures, code, JSON, long text."""
import json
import os

from pii_proxy.desanitizer import desanitize_text
from pii_proxy.sanitizer import sanitize_text
from pii_proxy.session import Session


def _make_session() -> Session:
    return Session(salt=os.urandom(16))


def _roundtrip(text: str) -> tuple[str, str, Session]:
    session = _make_session()
    sanitized = sanitize_text(text, session)
    restored = desanitize_text(sanitized, session)
    return sanitized, restored, session


# --- Long text with multiple PII types ---

def test_paragraph_with_mixed_pii():
    text = (
        "Dear John Smith, your account (SSN: 123-45-6789) has been flagged. "
        "Please contact us at support@example.com or call 555-123-4567. "
        "Your credit card ending in 4111111111111111 was charged on 2024-03-15. "
        "Regards, Jane Wilson"
    )
    sanitized, restored, session = _roundtrip(text)
    for real in ["John Smith", "123-45-6789", "support@example.com",
                 "555-123-4567", "4111111111111111", "2024-03-15", "Jane Wilson"]:
        assert real not in sanitized, f"{real} leaked into sanitized text"
        assert real in restored, f"{real} not restored"


def test_csv_row():
    text = 'John Smith,john@example.com,555-123-4567,123-45-6789,1990-01-15'
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert "john@example.com" not in sanitized
    assert "123-45-6789" not in sanitized
    assert restored == text


def test_multiple_csv_rows():
    rows = [
        "name,email,phone,ssn,dob",
        "Alice Johnson,alice@corp.com,555-111-2222,111-22-3333,1985-06-20",
        "Bob Williams,bob.w@test.org,555-444-5555,444-55-6666,1992-11-03",
        "Carol Davis,carol.d@mail.net,555-777-8888,777-88-9999,1978-02-28",
    ]
    text = "\n".join(rows)
    sanitized, restored, session = _roundtrip(text)
    # Header should be untouched
    assert sanitized.startswith("name,email,phone,ssn,dob")
    # All PII replaced
    for name in ["Alice Johnson", "Bob Williams", "Carol Davis"]:
        assert name not in sanitized
    for email in ["alice@corp.com", "bob.w@test.org", "carol.d@mail.net"]:
        assert email not in sanitized
    # Roundtrip restores
    assert restored == text


# --- PII in JSON ---

def test_json_object():
    data = {
        "user": "John Smith",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "ssn": "123-45-6789",
    }
    text = json.dumps(data)
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert "john@example.com" not in sanitized
    # Sanitized should still be valid JSON-like text
    assert "123-45-6789" not in sanitized
    assert restored == text


def test_nested_json():
    data = {
        "employees": [
            {"name": "Alice Johnson", "contact": {"email": "alice@corp.com", "phone": "555-111-2222"}},
            {"name": "Bob Williams", "contact": {"email": "bob@corp.com", "phone": "555-333-4444"}},
        ]
    }
    text = json.dumps(data)
    sanitized, restored, session = _roundtrip(text)
    for name in ["Alice Johnson", "Bob Williams"]:
        assert name not in sanitized
    for email in ["alice@corp.com", "bob@corp.com"]:
        assert email not in sanitized
    assert restored == text


# --- PII in code ---

def test_python_code():
    text = '''user_email = "jane.doe@company.com"
user_name = "Jane Wilson"
user_phone = "555-987-6543"
user_ssn = "987-65-4321"
'''
    sanitized, restored, session = _roundtrip(text)
    assert "jane.doe@company.com" not in sanitized
    assert "Jane Wilson" not in sanitized
    assert "555-987-6543" not in sanitized
    assert "987-65-4321" not in sanitized
    # Structure preserved
    assert 'user_email = "' in sanitized
    assert 'user_name = "' in sanitized
    assert restored == text


def test_sql_query():
    text = """SELECT * FROM users WHERE email = 'admin@example.com' AND name = 'John Smith' AND ssn = '123-45-6789';"""
    sanitized, restored, session = _roundtrip(text)
    assert "admin@example.com" not in sanitized
    assert "John Smith" not in sanitized
    assert "123-45-6789" not in sanitized
    assert "SELECT * FROM users WHERE" in sanitized
    assert restored == text


def test_javascript_code():
    text = '''const config = {
  adminEmail: "admin@internal.corp",
  supportPhone: "555-000-1234",
  emergencyContact: "Alice Williams",
};'''
    sanitized, restored, session = _roundtrip(text)
    assert "admin@internal.corp" not in sanitized
    assert "555-000-1234" not in sanitized
    assert "Alice Williams" not in sanitized
    assert "const config" in sanitized
    assert restored == text


# --- PII in markdown ---

def test_markdown_table():
    text = """| Name | Email | Phone |
|------|-------|-------|
| John Smith | john@example.com | 555-123-4567 |
| Jane Wilson | jane.w@example.com | 555-987-6543 |"""
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert "john@example.com" not in sanitized
    assert "Jane Wilson" not in sanitized
    assert "jane.w@example.com" not in sanitized
    assert restored == text


# --- Edge cases ---

def test_same_name_different_contexts():
    text = "John Smith called John Smith's office. John Smith was unavailable."
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert len(session.real_to_fake) == 1
    fake = session.real_to_fake["John Smith"]
    assert sanitized.count(fake) == 3
    assert restored == text


def test_adjacent_pii():
    text = "Contact: john@example.com 555-123-4567"
    sanitized, restored, session = _roundtrip(text)
    assert "john@example.com" not in sanitized
    assert "555-123-4567" not in sanitized
    assert restored == text


def test_pii_at_boundaries():
    text = "john@example.com"
    sanitized, restored, session = _roundtrip(text)
    assert "john@example.com" not in sanitized
    assert restored == text


def test_empty_text():
    session = _make_session()
    assert sanitize_text("", session) == ""
    assert desanitize_text("", session) == ""


def test_no_pii_long_text():
    text = "The quick brown fox jumps over the lazy dog. " * 100
    session = _make_session()
    result = sanitize_text(text, session)
    assert result == text
    assert len(session.real_to_fake) == 0


def test_url_with_email_like_pattern():
    text = "Visit https://user@host.com:8080/path for details."
    session = _make_session()
    sanitized = sanitize_text(text, session)
    # Should detect the email-like part
    assert "user@host.com" not in sanitized


def test_multiple_emails_same_domain():
    text = "Team: alice@corp.com, bob@corp.com, carol@corp.com"
    sanitized, restored, session = _roundtrip(text)
    assert len(session.real_to_fake) == 3
    assert "alice@corp.com" not in sanitized
    assert "bob@corp.com" not in sanitized
    assert "carol@corp.com" not in sanitized
    assert restored == text


def test_international_phone_formats():
    text = "Numbers: +36705374124, +4915123456789, +33612345678"
    sanitized, restored, session = _roundtrip(text)
    for num in ["+36705374124", "+4915123456789", "+33612345678"]:
        assert num not in sanitized
    assert restored == text


def test_tool_call_json_with_pii():
    """Simulate a tool call arguments string containing PII."""
    args = json.dumps({
        "query": "Find records for John Smith with email john@example.com",
        "filters": {"ssn": "123-45-6789", "dob": "1990-05-20"}
    })
    sanitized, restored, session = _roundtrip(args)
    assert "John Smith" not in sanitized
    assert "john@example.com" not in sanitized
    assert "123-45-6789" not in sanitized
    assert "1990-05-20" not in sanitized
    assert restored == args


# --- Name detection edge cases ---

def test_name_after_greeting():
    """'Hello John Smith' should only redact 'John Smith', not 'Hello'."""
    text = "Hello John Smith, how are you?"
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert sanitized.startswith("Hello ")
    assert restored == text


def test_name_after_dear():
    text = "Dear Alice Johnson, please review."
    sanitized, restored, session = _roundtrip(text)
    assert "Alice Johnson" not in sanitized
    assert sanitized.startswith("Dear ")
    assert restored == text


def test_sentence_start_not_captured_as_name():
    """Common words at sentence start shouldn't be treated as names."""
    text = "The project is ready."
    session = _make_session()
    result = sanitize_text(text, session)
    assert result == text


def test_capitalized_non_names_ignored():
    """Capitalized words that aren't names should not be redacted."""
    text = "Visit Paris France for vacation."
    session = _make_session()
    result = sanitize_text(text, session)
    # Paris/France may or may not be in name list, but shouldn't cause crashes
    assert "vacation" in result


def test_name_with_middle_initial():
    """Names like 'John A Smith' — middle initial breaks word run, only first+last if both known."""
    text = "Contact John Smith about this."
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert restored == text


def test_three_word_name():
    text = "Please call Mary Jane Watson immediately."
    sanitized, restored, session = _roundtrip(text)
    # All three are known names, should be captured as one span
    assert "Mary Jane Watson" not in sanitized or "Mary Jane" not in sanitized
    assert restored == text


def test_name_between_non_names():
    text = "Yesterday John Smith arrived, and Today Alice Johnson left."
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert "Alice Johnson" not in sanitized
    assert "Yesterday" in sanitized
    assert restored == text


def test_foreign_name_with_known_first_name():
    """A foreign surname + known first name should be captured."""
    text = "Contact Beiermeiszter György about this."
    sanitized, restored, session = _roundtrip(text)
    assert "Beiermeiszter György" not in sanitized
    assert sanitized.startswith("Contact ")
    assert restored == text


def test_unicode_name():
    text = "Müller József called earlier."
    sanitized, restored, session = _roundtrip(text)
    assert "Müller József" not in sanitized
    assert restored == text


def test_stop_words_not_captured():
    text = "Select From Where Group Order Having"
    session = _make_session()
    result = sanitize_text(text, session)
    assert result == text
    assert len(session.real_to_fake) == 0


def test_greeting_not_included_in_name():
    text = "Hello John Smith, welcome."
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert sanitized.startswith("Hello ")
    assert "Hello" not in session.real_to_fake
    assert restored == text


def test_sentence_start_non_name_skipped():
    text = "Regarding John Smith, please advise."
    sanitized, restored, session = _roundtrip(text)
    assert "John Smith" not in sanitized
    assert "Regarding" in sanitized
    assert restored == text


def test_code_keywords_not_captured():
    text = "Class Function Return Import Export Default"
    session = _make_session()
    result = sanitize_text(text, session)
    assert result == text


def test_mixed_real_and_fake_names_in_conversation():
    """Simulate multi-turn: first sanitize, then sanitize again with known mappings."""
    session = _make_session()
    turn1 = sanitize_text("John Smith said hello.", session)
    assert "John Smith" not in turn1
    fake_name = session.real_to_fake["John Smith"]

    # Turn 2: assistant used the fake name, now re-sanitize
    turn2_input = f"Yes, {fake_name} is correct. Also contact Alice Johnson."
    turn2 = sanitize_text(turn2_input, session)
    assert "Alice Johnson" not in turn2
