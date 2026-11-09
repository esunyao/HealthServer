from __future__ import annotations

from enum import Enum

import pytest

from nutriathena_agent.observability import redact_text
from nutriathena_agent.observability.redaction import safe_value


@pytest.mark.parametrize("value, hidden, marker", [
    ("data:image/jpeg;base64,QUJD", "QUJD", "[data-url omitted]"),
    ("https://media.example.test/x?token=hidden", "media.example.test", "[URL removed]"),
    ("Bearer fake-token", "fake-token", "Bearer [redacted]"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123456", "signature123456", "[jwt removed]"),
    ("postgresql://user:fake-password@db.example.test/db", "fake-password", "postgresql://[redacted]@"),
    ("client_secret=fake-secret&scope=read", "fake-secret", "client_secret=[redacted]"),
    ('{"authorization":"fake-secret"}', "fake-secret", '"[redacted]"'),
])
@pytest.mark.parametrize("content", [False, True])
def test_credentials_redacted_in_every_content_mode(value, hidden, marker, content):
    result = redact_text(value, content=content)
    assert hidden not in result
    assert marker in result


def test_structured_fields_redact_nested_secrets_and_preserve_types():
    class Choice(str, Enum):
        VALUE = "value"

    result = safe_value({
        "nested": [{"accessToken": "fake-token", "client_secret": "fake-secret"}],
        "bytes": b"abc", "enum": Choice.VALUE, "flag": True, "count": 1, "missing": None,
    }, content=True)

    assert result == {
        "nested": [{"accessToken": "[redacted]", "client_secret": "[redacted]"}],
        "bytes": "[3 bytes]", "enum": "value", "flag": True, "count": 1, "missing": None,
    }


def test_unknown_object_string_is_redacted():
    class ObjectWithCredentials:
        def __str__(self):
            return "Bearer fake-token"

    assert safe_value(ObjectWithCredentials(), content=True) == "Bearer [redacted]"


def test_validation_input_and_terminal_escape_rules():
    value = "\x1b[31mred\x1b[0m input_value='private meal', input_type=str"
    assert redact_text(value) == "red input_value=[redacted], input_type=str"
    assert redact_text(value, content=True) == "red input_value='private meal', input_type=str"
