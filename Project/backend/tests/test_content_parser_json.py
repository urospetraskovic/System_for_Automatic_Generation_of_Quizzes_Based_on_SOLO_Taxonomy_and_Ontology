"""
Tests for ContentParser._extract_json_from_response — the function that pulls
JSON out of an LLM response that may have prose before/after.
"""

from core.content_parser import ContentParser


def _parser():
    # Constructor probes Ollama; conftest blocks the network so it fails fast
    # and falls through cleanly. The instance is still usable for the static-ish
    # _extract_json_from_response method.
    return ContentParser()


def test_pure_json_array_is_parsed():
    parser = _parser()
    result = parser._extract_json_from_response('[{"a": 1}, {"b": 2}]')
    assert result == [{"a": 1}, {"b": 2}]


def test_pure_json_object_is_parsed():
    parser = _parser()
    result = parser._extract_json_from_response('{"question": "Q?", "answer": "A"}')
    assert result == {"question": "Q?", "answer": "A"}


def test_json_surrounded_by_prose_is_extracted():
    """LLMs often wrap JSON in 'Sure, here is the JSON: ...' chatter."""
    response = (
        'Sure! Here is the JSON output you requested:\n\n'
        '[{"title": "X"}]\n\n'
        'Let me know if you need anything else.'
    )
    parser = _parser()
    result = parser._extract_json_from_response(response)
    assert result == [{"title": "X"}]


def test_invalid_json_returns_none():
    parser = _parser()
    result = parser._extract_json_from_response('not json at all, just prose')
    assert result is None


def test_malformed_json_returns_none():
    parser = _parser()
    # Missing closing bracket
    result = parser._extract_json_from_response('{"a": 1, "b": ')
    assert result is None
