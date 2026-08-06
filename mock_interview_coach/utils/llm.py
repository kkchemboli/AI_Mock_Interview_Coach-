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
) -> str:
    client = _get_client(config)
    model = config.model
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra:
        kwargs.update(extra)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except AuthenticationError as exc:
            raise LLMConfigError(
                "Invalid Groq API key — check GROQ_API_KEY."
            ) from exc
        except _RETRYABLE as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 8))
            if attempt == 0:
                kwargs["model"] = config.fallback_model
    assert last_error is not None
    raise last_error


def chat_text(
    messages: list[dict],
    temperature: float = 0.4,
    max_tokens: int = 1024,
    config: LLMConfig | None = None,
) -> str:
    config = config or load_config()
    extra = {}
    if _is_reasoning(config.model):
        extra["reasoning_format"] = "hidden"
    return _call(messages, config=config, temperature=temperature,
                 max_tokens=max_tokens, extra=extra)


def chat_json(
    messages: list[dict],
    schema: dict | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    config: LLMConfig | None = None,
) -> dict:
    """Return a parsed dict. When `schema` (from `structured_schema`) is given,
    use Groq strict `json_schema` mode so the response is guaranteed to conform.
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
    raw = _call(messages, config=config, temperature=temperature,
                max_tokens=max_tokens, extra=extra)
    return extract_json(raw)
