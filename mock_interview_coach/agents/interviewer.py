"""Interviewer agent: asks one adaptive question.

Strict structured output via QUESTION_SCHEMA (Groq json_schema mode). The
requested difficulty travels in the user message as the calibration target;
the runtime stamps the returned question's `difficulty`.
"""

from typing import Any

from mock_interview_coach.agents._common import compact_history, make_agent
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import QUESTION_SCHEMA


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
        "role": role,
        "seniority": state.config.seniority,
        "focus": state.config.focus,
        "question_type": question_type,
        "difficulty": difficulty,
        "persona": state.persona_for("interviewer"),
        "history": compact_history(state, limit=history_limit),
    }


build_messages, run = make_agent("interviewer", _build_context, schema=QUESTION_SCHEMA)
