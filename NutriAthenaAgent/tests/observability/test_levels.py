from __future__ import annotations

import pytest

from nutriathena_agent.observability import (
    DebugLevel, LogFormat, parse_debug_level, parse_log_format, parse_log_level,
)


@pytest.mark.parametrize("value", ["", None, "off", "0", "false", "no", "none", " OFF "])
def test_parse_debug_level_off(value):
    assert parse_debug_level(value) is DebugLevel.OFF



@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "debug", "trace", " TRACE "])
def test_parse_debug_level_trace(value):
    assert parse_debug_level(value) is DebugLevel.TRACE



@pytest.mark.parametrize("value", ["full", "verbose", "content", " FULL "])
def test_parse_debug_level_full(value):
    assert parse_debug_level(value) is DebugLevel.FULL



def test_parse_debug_level_rejects_unknown_values():
    with pytest.raises(RuntimeError, match="NUTRIATHENA_DEBUG"):
        parse_debug_level("loud")


@pytest.mark.parametrize("value", [None, "text", "plain", "console", " TEXT ", LogFormat.TEXT])
def test_parse_text_format_aliases(value):
    assert parse_log_format(value) is LogFormat.TEXT


@pytest.mark.parametrize("value", ["json", "jsonl", "ndjson", " JSON ", LogFormat.JSON])
def test_parse_json_format_aliases(value):
    assert parse_log_format(value) is LogFormat.JSON


@pytest.mark.parametrize("value, expected", [(None, "INFO"), ("warn", "WARNING"), ("fatal", "CRITICAL"), (" debug ", "DEBUG")])
def test_parse_base_level_aliases(value, expected):
    assert parse_log_level(value) == expected


@pytest.mark.parametrize("parse, value, variable", [
    (parse_log_format, "xml", "NUTRIATHENA_LOG_FORMAT"),
    (parse_log_level, "silent", "NUTRIATHENA_LOG_LEVEL"),
])
def test_log_parsers_reject_unknown_values(parse, value, variable):
    with pytest.raises(RuntimeError, match=variable):
        parse(value)

