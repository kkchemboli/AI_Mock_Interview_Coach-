"""PersonaBuilder agent: turns role + seniority + focus into a persona.

Strict structured output via PERSONA_SCHEMA (Groq json_schema mode).
"""

from typing import Any

from mock_interview_coach.agents._common import make_agent
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import PERSONA_SCHEMA


def _build_context(role: str, state: ConversationState, **kwargs: Any) -> dict[str, Any]:
    return {
        "role": role,
        "seniority": state.config.seniority,
        "focus": state.config.focus,
        "difficulty": state.config.difficulty,
    }


build_messages, run = make_agent("persona_builder", _build_context, schema=PERSONA_SCHEMA)
