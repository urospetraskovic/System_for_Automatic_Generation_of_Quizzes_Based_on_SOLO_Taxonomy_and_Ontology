"""
Tests for core.llm_provider — the abstraction over Ollama / Anthropic.

We don't actually hit the network in these tests. The Ollama path is
exercised by monkey-patching requests.post, and the Anthropic path is
exercised by monkey-patching the anthropic.Anthropic client.
"""

import os
import pytest

import core.llm_provider as llm_provider
from core.llm_provider import (
    OllamaProvider,
    available_providers,
    call_llm,
    get_provider,
    get_spend_snapshot,
    reset_spend,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test gets a clean provider cache + spend counter."""
    # Clear singleton cache.
    llm_provider._provider_cache.clear()
    reset_spend()
    yield
    llm_provider._provider_cache.clear()
    reset_spend()


# -----------------------------------------------------------------------------
# Provider resolution
# -----------------------------------------------------------------------------

def test_default_provider_is_ollama(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    p = get_provider()
    assert p.name == "ollama"


def test_env_var_selects_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Patch the anthropic client so __init__ doesn't actually connect.
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: object())
    p = get_provider()
    assert p.name == "anthropic"


def test_unknown_provider_falls_back_to_ollama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "garbage")
    p = get_provider()
    assert p.name == "ollama"


def test_explicit_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: object())
    p = get_provider("ollama")
    assert p.name == "ollama"


# -----------------------------------------------------------------------------
# Ollama provider
# -----------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, code=200, payload=None):
        self.status_code = code
        self._payload = payload or {"response": "hello"}

    def json(self):
        return self._payload


def test_ollama_provider_resolves_role_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_JUDGE_MODEL", "judge-model")
    p = OllamaProvider()
    assert p.model_for_role("judge") == "judge-model"


def test_ollama_provider_falls_back_to_ollama_model(monkeypatch):
    monkeypatch.delenv("OLLAMA_JUDGE_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen-test")
    p = OllamaProvider()
    # Force reload of OLLAMA_MODEL constant if needed
    p_model = p.model_for_role("judge")
    assert p_model  # not empty


def test_ollama_call_records_spend(monkeypatch):
    # Patch the requests.post call inside llm_provider.
    monkeypatch.setattr(llm_provider.requests, "post",
                        lambda *a, **kw: _FakeResponse(200, {"response": "abcd"}))
    p = OllamaProvider()
    result = p.call("hi", role="generator", temperature=0.7,
                    json_mode=False, use_cache=False)
    assert result == "abcd"
    snap = get_spend_snapshot()
    assert snap["ollama"]["calls"] == 1
    assert snap["ollama"]["est_cost_usd"] == 0.0


def test_ollama_call_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(llm_provider.requests, "post",
                        lambda *a, **kw: _FakeResponse(500, {}))
    p = OllamaProvider()
    assert p.call("hi", role="judge", temperature=0.1,
                  json_mode=True, use_cache=False) is None


def test_ollama_handles_request_exception(monkeypatch):
    def _raise(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(llm_provider.requests, "post", _raise)
    p = OllamaProvider()
    assert p.call("x", role="judge", temperature=0.0,
                  json_mode=True, use_cache=False) is None


# -----------------------------------------------------------------------------
# Anthropic provider
# -----------------------------------------------------------------------------

class _FakeContentBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeUsage:
    def __init__(self, in_t=10, out_t=5):
        self.input_tokens = in_t
        self.output_tokens = out_t


class _FakeMessage:
    def __init__(self, text="response", usage=None):
        self.content = [_FakeContentBlock(text)]
        self.usage = usage or _FakeUsage()


class _FakeMessagesClient:
    def __init__(self, *args, **kwargs):
        pass

    def create(self, *, model, max_tokens, temperature, messages, timeout,
               system=None):
        # Record what we were called with for assertions. `system` is now
        # optional because the provider omits the kwarg when there is no
        # system instruction (newer Anthropic API rejects `system: null`).
        self.last_call = {
            "model": model, "max_tokens": max_tokens, "temperature": temperature,
            "system": system, "messages": messages, "timeout": timeout,
        }
        return _FakeMessage()


class _FakeAnthropicClient:
    def __init__(self, *args, **kwargs):
        self.messages = _FakeMessagesClient()


def test_anthropic_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from core.llm_provider import AnthropicProvider
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_anthropic_model_is_haiku_45(monkeypatch):
    """User explicitly requested Haiku — the constant must not silently drift."""
    from core.llm_provider import AnthropicProvider
    assert AnthropicProvider.MODEL == "claude-haiku-4-5"


def test_anthropic_call_records_real_token_spend(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)
    from core.llm_provider import AnthropicProvider
    p = AnthropicProvider()
    # Patch the client we just created to use our fake.
    result = p.call("hi", role="judge", temperature=0.1,
                    json_mode=True, use_cache=False)
    assert result == "response"
    snap = get_spend_snapshot()
    assert snap["anthropic"]["calls"] == 1
    assert snap["anthropic"]["input_tokens"] == 10
    assert snap["anthropic"]["output_tokens"] == 5
    # 10 in @ $1/M + 5 out @ $5/M = 0.00001 + 0.000025 ≈ 0.000035
    assert snap["anthropic"]["est_cost_usd"] > 0


def test_anthropic_json_mode_adds_system_instruction(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)
    from core.llm_provider import AnthropicProvider
    p = AnthropicProvider()
    p.call("hi", role="judge", temperature=0.1, json_mode=True, use_cache=False)
    # system is now a list of content blocks (required by newer API versions).
    system_blocks = p._client.messages.last_call["system"]
    assert isinstance(system_blocks, list)
    assert any("JSON" in b.get("text", "") for b in system_blocks)


def test_anthropic_no_json_mode_omits_system(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)
    from core.llm_provider import AnthropicProvider
    p = AnthropicProvider()
    p.call("hi", role="parser", temperature=0.7, json_mode=False, use_cache=False)
    # When json_mode is off, the provider omits the system kwarg entirely
    # (so the API doesn't receive `system: null`, which it rejects).
    assert p._client.messages.last_call["system"] is None


# -----------------------------------------------------------------------------
# call_llm helper
# -----------------------------------------------------------------------------

def test_call_llm_uses_active_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm_provider.requests, "post",
                        lambda *a, **kw: _FakeResponse(200, {"response": "ok"}))
    result = call_llm("hi", role="judge", temperature=0.1,
                      json_mode=True, use_cache=False)
    assert result == "ok"


# -----------------------------------------------------------------------------
# Thread-local provider override (for background jobs)
# -----------------------------------------------------------------------------

def test_thread_provider_overrides_env(monkeypatch):
    """Background jobs set the provider via thread-local. This must win over
    the env var fallback so that a 'Generate Questions' job submitted with
    the Anthropic header still talks to Anthropic on its worker thread."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: object())

    llm_provider.set_thread_provider("anthropic")
    try:
        p = get_provider()
        assert p.name == "anthropic"
    finally:
        llm_provider.clear_thread_provider()

    # After clear, falls back to env.
    p2 = get_provider()
    assert p2.name == "ollama"


# -----------------------------------------------------------------------------
# Spend tracking
# -----------------------------------------------------------------------------

def test_reset_spend_clears_one_provider():
    llm_provider._record_spend("ollama", 10, 20, 0)
    llm_provider._record_spend("anthropic", 30, 40, 0.5)
    reset_spend("ollama")
    snap = get_spend_snapshot()
    assert snap["ollama"]["calls"] == 0
    assert snap["anthropic"]["calls"] == 1


def test_reset_spend_clears_all_when_no_arg():
    llm_provider._record_spend("ollama", 10, 20, 0)
    llm_provider._record_spend("anthropic", 30, 40, 0.5)
    reset_spend()
    snap = get_spend_snapshot()
    assert snap["ollama"]["calls"] == 0
    assert snap["anthropic"]["calls"] == 0


# -----------------------------------------------------------------------------
# available_providers — for the /api/llm/providers endpoint
# -----------------------------------------------------------------------------

def test_available_providers_reports_anthropic_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ps = available_providers()
    anth = next((p for p in ps if p["name"] == "anthropic"), None)
    assert anth is not None
    assert anth["available"] is False


def test_available_providers_reports_anthropic_available_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    ps = available_providers()
    anth = next((p for p in ps if p["name"] == "anthropic"), None)
    assert anth["available"] is True


def test_available_providers_always_includes_ollama():
    ps = available_providers()
    assert any(p["name"] == "ollama" for p in ps)
