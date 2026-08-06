"""Deterministic semantic validators (Phase 4).

Small, pure helpers shared by the agent validators. Each returns `None` when a
value is acceptable, or a human-readable problem string otherwise, so the agent
factory in `agents._common` can decide between a constrained one-time repair
and the safe fallback path. No LLM calls.
"""

from typing import Any, Iterable


def nonempty(value: Any, label: str) -> str | None:
    if not str(value or "").strip():
        return f"{label} must be non-empty"
    return None


def word_limit(text: Any, max_words: int, label: str) -> str | None:
    text = str(text or "")
    if text.strip() and len(text.split()) > max_words:
        return f"{label} must be at most {max_words} words"
    return None


def char_limit(text: Any, max_chars: int, label: str) -> str | None:
    text = str(text or "")
    if len(text) > max_chars:
        return f"{label} must be at most {max_chars} characters"
    return None


def enum_allowed(value: Any, allowed: Iterable[str], label: str) -> str | None:
    if value not in allowed:
        return f"{label} must be one of {sorted(allowed)}, got {value!r}"
    return None


def list_bounds(
    value: Any, label: str, min_items: int = 0, max_items: int | None = None
) -> str | None:
    if not isinstance(value, list):
        return f"{label} must be a list"
    if len(value) < min_items:
        return f"{label} must have at least {min_items} entries"
    if max_items is not None and len(value) > max_items:
        return f"{label} must have at most {max_items} entries"
    return None


def sections_present(text: str, headers: Iterable[str]) -> str | None:
    missing = [h for h in headers if h not in text]
    if missing:
        return f"missing required section(s): {', '.join(missing)}"
    return None
