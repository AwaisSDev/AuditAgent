"""Tests for the PII redaction pipeline — this is the tool's core compliance
promise ("PII is redacted before storage"), yet it had zero test coverage
before this: the module's 61% coverage came entirely from being imported by
worker/tasks.py, not from anything actually calling redact_pii().

These run the real Presidio/spaCy pipeline (no mocks) since a mocked
analyzer would tell us nothing about whether PII actually gets caught.
"""

from app.services.redaction import redact_pii


def test_redacts_email_and_phone_in_a_sentence():
    out = redact_pii("Contact John Smith at john.smith@example.com or call 555-867-5309.")
    assert "john.smith@example.com" not in out
    assert "555-867-5309" not in out
    assert "[REDACTED]" in out


def test_redacts_credit_card_number():
    out = redact_pii("Card on file: 4111 1111 1111 1111.")
    assert "4111 1111 1111 1111" not in out
    assert "[REDACTED]" in out


def test_redacts_realistic_ssn_with_context_word():
    # 123-45-6789 is deliberately excluded from this test: Presidio's
    # US_SSN recognizer blacklists it (and a few other famous placeholder
    # SSNs) as a known-fake example number, by design — that's not a
    # redaction gap, so a real-shaped SSN is used here instead.
    out = redact_pii("Customer SSN is 274-51-9834.")
    assert "274-51-9834" not in out
    assert "[REDACTED]" in out


def test_redacts_ssn_shaped_number_even_without_context_word():
    out = redact_pii("Reference: 274-51-9834.")
    assert "274-51-9834" not in out


def test_redacts_ip_address():
    out = redact_pii("User logged in from 203.0.113.42.")
    assert "203.0.113.42" not in out


def test_leaves_clean_text_unchanged():
    text = "No PII here, just a normal ticket about a billing question."
    assert redact_pii(text) == text


def test_passes_through_empty_and_none():
    assert redact_pii("") == ""
    assert redact_pii(None) is None


def test_recurses_into_nested_dicts_and_lists():
    value = {
        "contact": {"email": "a@b.com", "note": "call me at 415-555-0100"},
        "history": ["plain text", "ssn on file: 274-51-9834"],
        "count": 3,
        "active": True,
    }
    out = redact_pii(value)
    assert "a@b.com" not in out["contact"]["email"]
    assert "415-555-0100" not in out["contact"]["note"]
    assert "274-51-9834" not in out["history"][1]
    assert out["history"][0] == "plain text"
    # Non-string values pass through untouched, not stringified.
    assert out["count"] == 3
    assert out["active"] is True
