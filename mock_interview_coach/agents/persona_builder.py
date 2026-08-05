"""PersonaBuilder agent: turns role + seniority + focus into a persona.

Strict structured output via PERSONA_SCHEMA (Groq json_schema mode).
"""

from typing import Any

from mock_interview_coach.agents._common import build_messages as _build_messages
from mock_interview_coach.agents._common import load_prompt
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.llm import LLMConfig, chat_json
from mock_interview_coach.utils.parser import PERSONA_SCHEMA

PERSONA_SYSTEM = load_prompt("persona_builder")


def build_messages(role: str, state: ConversationState) -> list[dict]:
    context = {
        "role": role,
        "seniority": state.config.seniority,
        "focus": state.config.focus,
        "difficulty": state.config.difficulty,
    }
    return _build_messages(PERSONA_SYSTEM, context)


def run(
    role: str,
    state: ConversationState,
    config: LLMConfig | None = None,
) -> dict[str, Any]:
    return chat_json(build_messages(role, state), schema=PERSONA_SCHEMA, config=config)
