"""Interviewer agent: asks one adaptive question.

Strict structured output via QUESTION_SCHEMA (Groq json_schema mode). The
requested difficulty travels in the trusted task data as the calibration
target; the runtime stamps the returned question's `difficulty`. Output is
validated so the emitted `question_type` always matches the requested type and
the question stays within the word budget; a template question is the safe
fallback if validation (or the LLM call) fails.
"""

from typing import Any

from mock_interview_coach.agents._common import (
    _labeled,
    compact_history,
    make_agent,
    WORD_LIMITS,
)
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import QUESTION_SCHEMA
from mock_interview_coach.utils.validation import nonempty, word_limit


def _build_context(
    role: str,
    state: ConversationState,
    *,
    question_type: str,
    difficulty: float,
    history_limit: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "trusted_task": {
            "action": "ask_next_question",
            "seniority": state.config.seniority,
            "focus": state.config.focus,
            "requested_question_type": question_type,
            "requested_difficulty": difficulty,
        },
        "untrusted_persona": _labeled(state.persona_for("interviewer"), "persona_llm"),
        "untrusted_history": compact_history(state, limit=history_limit),
    }


def _validate(data: dict[str, Any], request: dict[str, Any]) -> str | None:
    requested = request.get("question_type")
    if data.get("question_type") != requested:
        return f"question_type must be {requested!r}, got {data.get('question_type')!r}"
    problem = nonempty(data.get("question_text"), "question_text")
    if problem is not None:
        return problem
    return word_limit(data.get("question_text"), WORD_LIMITS["interviewer"], "question_text")


def _repair_hint(data: dict[str, Any], request: dict[str, Any]) -> str:
    return (
        f"Your question was rejected: question_type must be exactly "
        f"{request.get('question_type')!r} and question_text must be a natural, "
        f"non-empty question of at most {WORD_LIMITS['interviewer']} words. "
        "Re-emit the question fixing that."
    )


def _fallback(request: dict[str, Any]) -> dict[str, Any]:
    qtype = request.get("question_type", "behavioral")
    return {
        "question_text": (
            f"Tell me about a concrete {qtype} example from your experience "
            "and what you learned from it."
        ),
        "question_type": qtype,
        "expects_code": False,
        "context": "",
    }


build_messages, run = make_agent(
    "interviewer",
    _build_context,
    schema=QUESTION_SCHEMA,
    validator=_validate,
    repair_hint=_repair_hint,
    fallback=_fallback,
    on_error=_fallback,
)
