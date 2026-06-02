"""
LLM provider abstraction — Ollama (local) and Anthropic (Claude Haiku 4.5).

Why this exists:
  Every service that calls an LLM (generator, judges, content parser, …)
  used to do its own `requests.post(OLLAMA_BASE_URL/api/generate, ...)`.
  That hard-coded the runtime to Ollama. When the user wants to switch to a
  paid API (Claude Haiku 4.5), we need a single chokepoint that:

    * picks the right provider per request,
    * applies its own caching strategy,
    * surfaces token-spend counters for the cost-tracker widget,
    * speaks a uniform `call(prompt, role, …) -> str` interface to callers.

How provider selection works:
  1. If the Flask request set ``g.llm_provider`` (via the X-LLM-Provider
     header in app.before_request), use that.
  2. Otherwise fall back to the ``LLM_PROVIDER`` env var (default "ollama").

Cache strategy:
  The existing SQLite ``llm_cache`` table keys on (model, prompt, temperature,
  json_mode). To avoid collisions between providers that may use the same
  model name, the Anthropic provider prefixes its model with ``anthropic:``
  in the cache key. Ollama keeps its current cache format so existing
  cached responses remain valid.

Hard-coded constraint:
  The user explicitly asked for Claude Haiku 4.5 (not Sonnet, not Opus).
  AnthropicProvider.MODEL is therefore a constant — switching to a more
  expensive model is a deliberate code edit, not an environment toggle.
"""

import os
import threading
from abc import ABC, abstractmethod
from typing import Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache


# --------------------------------------------------------------------------
# Cost / spend tracking
# --------------------------------------------------------------------------

# Process-wide token counters per provider. The UI polls /api/llm/spend
# to render the cost-tracker widget in the top bar.
_spend_lock = threading.Lock()
_spend = {
    "ollama": {"input_tokens": 0, "output_tokens": 0, "calls": 0, "est_cost_usd": 0.0},
    "anthropic": {"input_tokens": 0, "output_tokens": 0, "calls": 0, "est_cost_usd": 0.0},
}


def _record_spend(provider_name: str, input_tokens: int, output_tokens: int,
                  cost_usd: float) -> None:
    with _spend_lock:
        s = _spend.setdefault(provider_name, {
            "input_tokens": 0, "output_tokens": 0, "calls": 0, "est_cost_usd": 0.0,
        })
        s["input_tokens"] += int(input_tokens)
        s["output_tokens"] += int(output_tokens)
        s["calls"] += 1
        s["est_cost_usd"] += float(cost_usd)


def get_spend_snapshot() -> dict:
    """Return a copy of the spend counters for the cost widget."""
    with _spend_lock:
        return {k: dict(v) for k, v in _spend.items()}


def reset_spend(provider_name: Optional[str] = None) -> None:
    with _spend_lock:
        if provider_name:
            _spend[provider_name] = {
                "input_tokens": 0, "output_tokens": 0,
                "calls": 0, "est_cost_usd": 0.0,
            }
        else:
            for k in _spend:
                _spend[k] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "calls": 0, "est_cost_usd": 0.0,
                }


# --------------------------------------------------------------------------
# Provider base class
# --------------------------------------------------------------------------

class LLMProvider(ABC):
    """A single LLM endpoint that can answer a prompt and return JSON-or-text."""
    name: str = "abstract"

    @abstractmethod
    def model_for_role(self, role: str) -> str:
        """Return the model name appropriate for this service role.
        Roles: "generator", "judge", "cove", "solver", "ioc", "ambiguity",
        "grammar", "face", "miner", "parser", "chatbot"."""

    @abstractmethod
    def call(self, prompt: str, *, role: str, temperature: float,
             json_mode: bool, use_cache: bool = True,
             timeout: int = 60) -> Optional[str]:
        """Make the LLM call and return raw text or None on failure."""


# --------------------------------------------------------------------------
# Ollama provider (preserves existing behaviour)
# --------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    name = "ollama"

    # Each role can override the model via env var. Falls back to OLLAMA_MODEL
    # so existing single-model installs keep working.
    _ROLE_ENV = {
        "generator": "OLLAMA_MODEL",
        "judge": "OLLAMA_JUDGE_MODEL",
        "cove": "OLLAMA_COVE_MODEL",
        "solver": "OLLAMA_SOLVER_MODEL",
        "ioc": "OLLAMA_IOC_MODEL",
        "ambiguity": "OLLAMA_AMBIGUITY_MODEL",
        "grammar": "OLLAMA_GRAMMAR_MODEL",
        "face": "OLLAMA_FACE_MODEL",
        "miner": "OLLAMA_MINER_MODEL",
        "parser": "OLLAMA_MODEL",
        "chatbot": "OLLAMA_MODEL",
    }

    def model_for_role(self, role: str) -> str:
        env_key = self._ROLE_ENV.get(role, "OLLAMA_MODEL")
        return os.getenv(env_key) or OLLAMA_MODEL

    def call(self, prompt: str, *, role: str, temperature: float,
             json_mode: bool, use_cache: bool = True,
             timeout: int = 60) -> Optional[str]:
        model = self.model_for_role(role)

        if use_cache:
            cached = llm_cache.get(model, prompt, temperature, json_mode)
            if cached is not None:
                return cached

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "temperature": temperature,
        }
        if json_mode:
            payload["format"] = "json"

        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
                timeout=timeout,
            )
            if resp.status_code != 200:
                return None
            result = resp.json().get("response", "")
        except Exception:
            return None

        if not result:
            return None

        if use_cache:
            llm_cache.put(model, prompt, temperature, json_mode, result)

        # Ollama doesn't bill, but we still record approximate token counts
        # so the spend widget can show "local: 12,345 tokens" alongside
        # paid providers.
        approx_in = max(1, len(prompt) // 4)
        approx_out = max(1, len(result) // 4)
        _record_spend(self.name, approx_in, approx_out, cost_usd=0.0)

        return result


# --------------------------------------------------------------------------
# Anthropic provider — Claude Haiku 4.5 only (per project requirement)
# --------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    # Hard-coded. Switching to Sonnet/Opus is a deliberate edit here, not an
    # environment toggle, because they cost 3-10× more.
    MODEL = "claude-haiku-4-5"

    # Pricing as of May 2026 in USD per 1M tokens. Used only for the cost
    # widget — actual billing is Anthropic's.
    INPUT_USD_PER_M = 1.0
    OUTPUT_USD_PER_M = 5.0
    MAX_OUTPUT_TOKENS = 4096

    def __init__(self):
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY env var not set. "
                "Get a key at https://console.anthropic.com and add it to backend/.env."
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def model_for_role(self, role: str) -> str:
        return self.MODEL

    def call(self, prompt: str, *, role: str, temperature: float,
             json_mode: bool, use_cache: bool = True,
             timeout: int = 60) -> Optional[str]:
        # Prefix the cache key with our provider name so we don't collide
        # with Ollama entries on shared local models.
        cache_model_key = f"anthropic:{self.MODEL}"

        if use_cache:
            cached = llm_cache.get(cache_model_key, prompt, temperature, json_mode)
            if cached is not None:
                return cached

        # Anthropic uses messages.create with a separate system param. The
        # generator's existing prompts are self-contained (no separate
        # system message), so we send the whole thing as the user turn.
        # If json_mode is on, we add a system instruction asking for JSON.
        #
        # Newer Anthropic API versions reject `system: null` and require the
        # array-of-content-blocks shape. So we (a) wrap the system string in
        # the canonical [{"type":"text","text":...}] form, and (b) omit the
        # kwarg entirely when there is no system instruction to send.
        kwargs = {
            "model": self.MODEL,
            "max_tokens": self.MAX_OUTPUT_TOKENS,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": timeout,
        }
        if json_mode:
            kwargs["system"] = [{
                "type": "text",
                "text": "Respond ONLY with strictly valid JSON. No prose, no markdown fences.",
            }]

        try:
            msg = self._client.messages.create(**kwargs)
        except Exception as e:
            print(f"[Anthropic] API error: {e}", flush=True)
            return None

        # Concatenate all text blocks in the response.
        result = "".join(
            getattr(block, "text", "")
            for block in (msg.content or [])
            if getattr(block, "type", "") == "text"
        )
        if not result:
            return None

        # Track cost from real Anthropic usage figures.
        usage = getattr(msg, "usage", None)
        if usage is not None:
            in_tokens = getattr(usage, "input_tokens", 0)
            out_tokens = getattr(usage, "output_tokens", 0)
            cost = (in_tokens / 1_000_000) * self.INPUT_USD_PER_M + \
                   (out_tokens / 1_000_000) * self.OUTPUT_USD_PER_M
            _record_spend(self.name, in_tokens, out_tokens, cost)

        if use_cache:
            llm_cache.put(cache_model_key, prompt, temperature, json_mode, result)

        return result


# --------------------------------------------------------------------------
# Provider resolution
# --------------------------------------------------------------------------

_provider_cache: dict[str, LLMProvider] = {}
_provider_lock = threading.Lock()

# Per-thread provider override for background jobs.
#
# The Flask `g.llm_provider` chain only works while a request context is
# active. Background jobs (services/jobs.py) run on a worker thread with no
# request context, so the per-call provider choice from the X-LLM-Provider
# header would otherwise be lost and every background call would fall back
# to the env-var default ("ollama"). Jobs submit-time captures g.llm_provider
# and stashes it here on the worker thread; get_provider() reads it.
_thread_provider = threading.local()


def set_thread_provider(name: str) -> None:
    """Pin the active provider on the calling thread (used by background jobs)."""
    _thread_provider.name = (name or "").strip().lower() or None


def clear_thread_provider() -> None:
    if hasattr(_thread_provider, "name"):
        del _thread_provider.name


def _build(name: str) -> LLMProvider:
    if name == "anthropic":
        return AnthropicProvider()
    return OllamaProvider()


def get_provider(name: Optional[str] = None) -> LLMProvider:
    """Resolve the active provider. Priority order:
        1. Explicit `name` arg (e.g. for tests or per-call overrides).
        2. Flask request context (g.llm_provider, set in before_request).
        3. LLM_PROVIDER env var.
        4. "ollama" as the safe default.
    """
    if name is None:
        try:
            from flask import g, has_request_context
            if has_request_context():
                name = getattr(g, "llm_provider", None)
        except Exception:
            pass

    # Thread-local fallback for background jobs (no request context).
    if name is None:
        name = getattr(_thread_provider, "name", None)

    if name is None:
        name = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

    name = (name or "ollama").lower()
    if name not in ("ollama", "anthropic"):
        name = "ollama"

    with _provider_lock:
        prov = _provider_cache.get(name)
        if prov is None:
            prov = _build(name)
            _provider_cache[name] = prov
        return prov


def call_llm(prompt: str, *, role: str = "generator",
             temperature: float = 0.7, json_mode: bool = True,
             use_cache: bool = True, timeout: int = 60,
             provider_name: Optional[str] = None) -> Optional[str]:
    """Service-facing helper. Resolve the active provider and call it.

    This replaces the bespoke `_call_*_llm` HTTP calls that each service
    used to maintain. A service that wants to use a specific provider
    regardless of the request context passes `provider_name=` explicitly.
    """
    provider = get_provider(provider_name)
    return provider.call(
        prompt,
        role=role,
        temperature=temperature,
        json_mode=json_mode,
        use_cache=use_cache,
        timeout=timeout,
    )


def describe_active_model(role: str = "generator") -> str:
    """Return a human-readable label of the model that will handle calls for
    this role right now, e.g. "anthropic:claude-haiku-4-5" or "ollama:qwen2.5:14b".

    Services use this in their startup banner so the log accurately reflects
    where calls are being routed, instead of a hard-coded model constant
    that lied after the provider abstraction landed.
    """
    p = get_provider()
    try:
        return f"{p.name}:{p.model_for_role(role)}"
    except Exception:
        return p.name


def available_providers() -> list[dict]:
    """Surface to the frontend which providers are usable in this install."""
    out = [{
        "name": "ollama",
        "label": "Ollama (local)",
        "model": OLLAMA_MODEL,
        "available": True,  # Ollama is always available; if down, calls fail gracefully.
    }]
    out.append({
        "name": "anthropic",
        "label": "Anthropic Claude Haiku 4.5",
        "model": AnthropicProvider.MODEL,
        "available": bool(os.getenv("ANTHROPIC_API_KEY")),
    })
    return out
