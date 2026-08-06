"""Groq LLM client.

Thin wrapper around the Groq chat-completions API: config loading, retries with
backoff on rate limits/timeouts, automatic fallback to a second model on 429,
and `chat_json` for strict structured outputs (Groq `json_schema` mode) with
`reasoning_format="hidden"` so no reasoning text leaks into outputs.
"""

import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from groq import (
    Groq,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)

from mock_interview_coach.utils.parser import extract_json

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_FALLBACK_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT_SEC = 45.0

_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


class LLMConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str
    fallback_model: str
    timeout_sec: float


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
        timeout_sec=DEFAULT_TIMEOUT_SEC,
    )


_client: Groq | None = None
_client_config: LLMConfig | None = None


def _get_client(config: LLMConfig) -> Groq:
    global _client, _client_config
    if _client is None or _client_config != config:
        _client = Groq(api_key=config.api_key, timeout=config.timeout_sec)
        _client_config = config
    return _client


def _is_reasoning(model: str) -> bool:
    return model.startswith("openai/")


def _call(
    messages: list[dict],
    *,
    config: LLMConfig,
    temperature: float,
    max_tokens: int,
    extra: dict | None = None,
    allow_fallback: bool = True,
) -> tuple[str, str, bool]:
    """Call the API, returning `(content, model_used, used_fallback)`. On a
    retryable error the primary model is retried, then (unless
    `allow_fallback` is False) the configured fallback model. The model that
    actually produced the content is reported so callers can record provenance.
    """
    client = _get_client(config)
    kwargs = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra:
        kwargs.update(extra)
    last_error: Exception | None = None
    used_fallback = False
    for attempt in range(3):
        try:
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            return content, kwargs["model"], used_fallback
        except AuthenticationError as exc:
            raise LLMConfigError(
                "Invalid Groq API key — check GROQ_API_KEY."
            ) from exc
        except _RETRYABLE as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 8))
            if (
                attempt == 0
                and allow_fallback
                and config.fallback_model != config.model
            ):
                kwargs["model"] = config.fallback_model
                used_fallback = True
    assert last_error is not None
    raise last_error


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
    extra = {}
    if _is_reasoning(config.model):
        extra["reasoning_format"] = "hidden"
    content, model, used_fallback = _call(
        messages, config=config, temperature=temperature,
        max_tokens=max_tokens, extra=extra, allow_fallback=allow_fallback,
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
    if _is_reasoning(config.model):
        extra["reasoning_format"] = "hidden"
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
