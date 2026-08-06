"""Groq LLM client.

Thin wrapper around the Groq chat-completions API: config loading, retries with
backoff on rate limits/timeouts, automatic fallback to a second model on 429,
and `chat_json` for strict structured outputs (Groq `json_schema` mode) with
`reasoning_format="hidden"` so no reasoning text leaks into outputs.

Transport hardening: `response.choices[0]` is guarded and an empty completion is
treated as a retryable failure (never silently returned as `""`). Rate-limit
`Retry-After` headers are honored; otherwise exponential backoff with jitter is
used, and the whole call sleeps at most `LLM_MAX_BACKOFF_SEC` (default 60)
across `LLM_MAX_ATTEMPTS` (default 3) attempts. The client uses the Groq SDK's
default timeout, and the reasoning-format decision is centralized
(auto-detected by model prefix). When `LLM_MIN_INTERVAL_SEC` is set, consecutive
calls are spaced at least that many seconds apart to stay under RPM/TPM ceilings.
"""

import os
import random
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from groq import (
    Groq,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from mock_interview_coach.utils.parser import extract_json

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_FALLBACK_MODEL = "openai/gpt-oss-20b"

# Random slack added to every computed backoff (seconds).
_JITTER_SEC = 2.0

# Retry budget defaults. Both are overridable through the environment
# (LLM_MAX_ATTEMPTS, LLM_MAX_BACKOFF_SEC) so a headless simulation on a
# rate-limited key can ride out long 429 windows without changing the
# defaults the live app runs with.
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_MAX_BACKOFF_SEC = 60.0

# When LLM_MIN_INTERVAL_SEC is set, `_call` spaces consecutive network calls
# at least this many seconds apart (a simple global rate limiter). Unset by
# default so the Streamlit app is unaffected; a simulation can set it to stay
# under an account's RPM/TPM ceiling.
_last_call_at = 0.0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


class LLMConfigError(RuntimeError):
    pass


class _EmptyResponseError(RuntimeError):
    """Raised when the API returns a response with no usable content. Treated
    like any other retryable error: the call retries and falls back rather than
    returning a blank narrative that would otherwise pass as valid output."""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str
    fallback_model: str


def load_config(env_path: str | None = None) -> LLMConfig:
    load_dotenv(env_path)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return LLMConfig(
        api_key=api_key,
        model=os.getenv("GROQ_MODEL", DEFAULT_MODEL),
        fallback_model=os.getenv("GROQ_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL),
    )


_client: Groq | None = None
_client_config: LLMConfig | None = None


def _get_client(config: LLMConfig) -> Groq:
    global _client, _client_config
    if _client is None or _client_config != config:
        _client = Groq(api_key=config.api_key)
        _client_config = config
    return _client


def _is_reasoning(model: str) -> bool:
    return model.startswith("openai/")


def _reasoning_format(config: LLMConfig) -> str | None:
    """The `reasoning_format` to send for this config, or None to omit. Auto-
    detected by the model prefix (openai/* models are reasoning models on
    Groq), so no reasoning text leaks into outputs."""
    return "hidden" if _is_reasoning(config.model) else None


def _retry_delay(attempt: int, exc: Exception, remaining: float) -> float:
    """Seconds to sleep before the next retry. Rate-limit errors honor the
    `Retry-After` header on `exc.response` when present; otherwise exponential
    backoff is the fallback. Jitter is added in both cases, and the result is
    clamped so the call never spends more than its remaining backoff budget."""
    retry_after: float | None = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers is not None:
        for key in ("retry-after", "Retry-After"):
            raw = headers.get(key) if hasattr(headers, "get") else None
            if raw is None:
                continue
            try:
                retry_after = float(raw)
                break
            except (TypeError, ValueError):
                continue
    if retry_after is None:
        retry_after = min(2 ** attempt, 8)
    return max(min(retry_after + random.uniform(0, _JITTER_SEC), remaining), 0.0)


# Errors the module recognizes. Exported so the agent factory can tell a known
# LLM failure (fall back / degrade) from an unexpected bug (let it crash).
KNOWN_LLM_ERRORS = (
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
    _EmptyResponseError,
)

_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


def _call(
    messages: list[dict],
    *,
    config: LLMConfig,
    temperature: float,
    max_tokens: int,
    extra: dict | None = None,
    allow_fallback: bool = True,
    client: Groq | None = None,
) -> tuple[str, str, bool]:
    """Call the API, returning `(content, model_used, used_fallback)`. On a
    retryable error (rate limit, timeout, connection, server, or empty
    response) the primary model is retried with backoff, then (unless
    `allow_fallback` is False) the configured fallback model. The model that
    actually produced the content is reported so callers can record
    provenance. `client` is injectable for tests.
    """
    client = client if client is not None else _get_client(config)
    kwargs = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra:
        kwargs.update(extra)
    reasoning_format = _reasoning_format(config)
    if reasoning_format is not None:
        kwargs["reasoning_format"] = reasoning_format
    last_error: Exception | None = None
    used_fallback = False
    max_attempts = _env_int("LLM_MAX_ATTEMPTS", _DEFAULT_MAX_ATTEMPTS)
    max_backoff = _env_float("LLM_MAX_BACKOFF_SEC", _DEFAULT_MAX_BACKOFF_SEC)
    _pace_requests(_env_float("LLM_MIN_INTERVAL_SEC", 0.0))
    total_backoff = 0.0
    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(**kwargs)
            if not response.choices:
                raise _EmptyResponseError(
                    "completion returned no choices"
                )
            message = getattr(response.choices[0], "message", None)
            content = getattr(message, "content", None)
            if not content:
                raise _EmptyResponseError(
                    "completion returned empty content"
                )
            return content, kwargs["model"], used_fallback
        except AuthenticationError as exc:
            raise LLMConfigError(
                "Invalid Groq API key — check GROQ_API_KEY."
            ) from exc
        except (_RETRYABLE + (_EmptyResponseError,)) as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                sleep = _retry_delay(
                    attempt, exc, max_backoff - total_backoff
                )
                time.sleep(sleep)
                total_backoff += sleep
            if (
                attempt == 0
                and allow_fallback
                and config.fallback_model != config.model
            ):
                kwargs["model"] = config.fallback_model
                used_fallback = True
    assert last_error is not None
    raise last_error


def _pace_requests(min_interval: float) -> None:
    """Sleep so consecutive `_call`s are at least `min_interval` seconds apart.
    Retries inside a single call keep their own backoff; this only paces the
    start of each new call."""
    global _last_call_at
    if min_interval <= 0.0:
        return
    wait = min_interval - (time.monotonic() - _last_call_at)
    if wait > 0.0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


def _record_meta(meta: dict | None, model: str, used_fallback: bool) -> None:
    if meta is not None:
        meta["model"] = model
        meta["fallback"] = used_fallback


def chat_text(
    messages: list[dict],
    temperature: float = 0.4,
    max_tokens: int = 1024,
    config: LLMConfig | None = None,
    meta: dict | None = None,
    allow_fallback: bool = True,
) -> str:
    config = config or load_config()
    content, model, used_fallback = _call(
        messages, config=config, temperature=temperature,
        max_tokens=max_tokens, allow_fallback=allow_fallback,
    )
    _record_meta(meta, model, used_fallback)
    return content


def chat_json(
    messages: list[dict],
    schema: dict | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    config: LLMConfig | None = None,
    meta: dict | None = None,
    allow_fallback: bool = True,
) -> dict:
    """Return a parsed dict. When `schema` (from `structured_schema`) is given,
    use Groq strict `json_schema` mode so the response is guaranteed to conform.
    `meta`, if given, is populated with the model actually used and whether the
    fallback model was engaged.
    """
    config = config or load_config()
    extra = {}
    if schema is not None:
        extra["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema["name"],
                "schema": schema["schema"],
                "strict": True,
            },
        }
    raw, model, used_fallback = _call(
        messages, config=config, temperature=temperature,
        max_tokens=max_tokens, extra=extra, allow_fallback=allow_fallback,
    )
    _record_meta(meta, model, used_fallback)
    return extract_json(raw)
