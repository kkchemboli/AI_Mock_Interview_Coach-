"""PersonaBuilder agent: turns role + seniority + focus into a persona.

Strict structured output via PERSONA_SCHEMA (Groq json_schema mode). The role
text is bounded and carried inside `trusted_task`; a persona that fails
validation (or an LLM error) falls back to `DEFAULT_PERSONA` so the interview
can always start.
"""

from typing import Any

from mock_interview_coach.agents._common import _LIMITS, _normalize, _truncate, make_agent
from mock_interview_coach.state.conversation_state import (
    ConversationState,
    DEFAULT_PERSONA,
)
from mock_interview_coach.utils.parser import PERSONA_SCHEMA
from mock_interview_coach.utils.validation import list_bounds, nonempty


def _build_context(role: str, state: ConversationState, **kwargs: Any) -> dict[str, Any]:
    return {
        "trusted_task": {
            "action": "design_persona",
            "role": _truncate(_normalize(role), _LIMITS["role"]),
            "seniority": state.config.seniority,
            "focus": state.config.focus,
            "difficulty": state.config.difficulty,
        }
    }


def _validate(data: dict[str, Any], request: dict[str, Any]) -> str | None:
    persona = data.get("persona") or {}
    for key, label in (("title", "persona.title"), ("company_type", "persona.company_type")):
        problem = nonempty(persona.get(key), label)
        if problem is not None:
            return problem
    problem = list_bounds(
        persona.get("what_they_optimize_for"),
        "what_they_optimize_for",
        min_items=2,
        max_items=4,
    )
    if problem is not None:
        return problem
    problem = list_bounds(data.get("topic_areas"), "topic_areas", min_items=4)
    if problem is not None:
        return problem
    return nonempty(data.get("scoring_lens"), "scoring_lens")


def _repair_hint(data: dict[str, Any], request: dict[str, Any]) -> str:
    return (
        "Your persona was rejected: title and company_type must be non-empty, "
        "what_they_optimize_for must have 2-4 entries, topic_areas at least 4, "
        "and scoring_lens a concrete paragraph. Re-emit the persona fixing "
        "those fields."
    )


def _fallback(request: dict[str, Any]) -> dict[str, Any]:
    return dict(DEFAULT_PERSONA)


build_messages, run = make_agent(
    "persona_builder",
    _build_context,
    schema=PERSONA_SCHEMA,
    validator=_validate,
    repair_hint=_repair_hint,
    fallback=_fallback,
    on_error=_fallback,
)
