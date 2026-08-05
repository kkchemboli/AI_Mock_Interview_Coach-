"""Interviewer agent: asks one adaptive question.

Strict structured output via QUESTION_SCHEMA (Groq json_schema mode).
"""

from typing import Any

from mock_interview_coach.agents._common import build_messages as _build_messages
from mock_interview_coach.agents._common import compact_history, load_prompt
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.llm import LLMConfig, chat_json
from mock_interview_coach.utils.parser import QUESTION_SCHEMA

INTERVIEWER_SYSTEM = load_prompt("interviewer")


def build_messages(
    role: str,
    state: ConversationState,
    *,
    question_type: str,
    difficulty: float,
) -> list[dict]:
    context = {
        "role": role,
        "seniority": state.config.seniority,
        "focus": state.config.focus,
        "question_type": question_type,
        "difficulty": difficulty,
        "persona": state.persona_for("interviewer"),
        "history": compact_history(state),
    }
    return _build_messages(INTERVIEWER_SYSTEM, context)


def run(
    role: str,
    state: ConversationState,
    *,
    question_type: str,
    difficulty: float,
    config: LLMConfig | None = None,
) -> dict[str, Any]:
    return chat_json(
        build_messages(role, state, question_type=question_type, difficulty=difficulty),
        schema=QUESTION_SCHEMA,
        config=config,
    )
