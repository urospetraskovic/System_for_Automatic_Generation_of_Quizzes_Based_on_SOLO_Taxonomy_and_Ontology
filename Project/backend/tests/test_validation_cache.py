"""
Tests for services.validation_cache.

The cache writes to the production SQLite DB by design (so panels see
exactly what the live backend sees), so we clear it before/after each test
to avoid leaking state into other tests.
"""

import pytest

from services import validation_cache


@pytest.fixture(autouse=True)
def _isolate_cache():
    validation_cache.clear_all()
    yield
    validation_cache.clear_all()


def test_get_returns_none_when_missing():
    assert validation_cache.get('ioc', 42) is None
    assert validation_cache.get_all_for_lesson(42) == {}


def test_put_then_get_roundtrips_payload():
    payload = {'ioc_index': 0.7, 'distribution': {'+1': 5, '0': 3, '-1': 2}}
    validation_cache.put('ioc', 42, payload)
    out = validation_cache.get('ioc', 42)
    assert out['ioc_index'] == 0.7
    assert out['distribution']['+1'] == 5


def test_put_upserts_on_duplicate_key():
    validation_cache.put('ioc', 42, {'v': 1})
    validation_cache.put('ioc', 42, {'v': 2})
    assert validation_cache.get('ioc', 42)['v'] == 2


def test_get_all_for_lesson_returns_only_matching_lesson():
    validation_cache.put('ioc', 1, {'v': 'a'})
    validation_cache.put('lint', 1, {'v': 'b'})
    validation_cache.put('ioc', 2, {'v': 'other'})
    out = validation_cache.get_all_for_lesson(1)
    assert set(out.keys()) == {'ioc', 'lint'}
    assert out['ioc']['v'] == 'a'
    assert out['lint']['v'] == 'b'


def test_get_all_attaches_cached_at_timestamp():
    validation_cache.put('ioc', 1, {'v': 'x'})
    out = validation_cache.get_all_for_lesson(1)
    assert '_cached_at' in out['ioc']


def test_invalidate_lesson_drops_only_that_lessons_rows():
    validation_cache.put('ioc', 1, {'v': 'a'})
    validation_cache.put('lint', 1, {'v': 'b'})
    validation_cache.put('ioc', 2, {'v': 'c'})
    n = validation_cache.invalidate_lesson(1)
    assert n == 2
    assert validation_cache.get_all_for_lesson(1) == {}
    assert validation_cache.get('ioc', 2) == {'v': 'c'}


def test_invalidate_lesson_with_metric_filter():
    validation_cache.put('ioc', 1, {'v': 'a'})
    validation_cache.put('lint', 1, {'v': 'b'})
    n = validation_cache.invalidate_lesson(1, metric_key='ioc')
    assert n == 1
    assert validation_cache.get('ioc', 1) is None
    assert validation_cache.get('lint', 1) == {'v': 'b'}


def test_clear_all_drops_every_row():
    validation_cache.put('ioc', 1, {'v': 'a'})
    validation_cache.put('ioc', 99, {'v': 'b'})
    n = validation_cache.clear_all()
    assert n >= 2
    assert validation_cache.get('ioc', 1) is None
    assert validation_cache.get('ioc', 99) is None
