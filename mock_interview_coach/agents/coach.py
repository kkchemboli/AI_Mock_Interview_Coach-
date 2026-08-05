"""Coach agent: writes the markdown debrief.

The only agent that emits free-form prose (not JSON). Uses the deterministic
`summary` from analysis.root_cause as its structured input.
"""

from typing import Any

from mock_interview_coach.agents._common import build_messages as _build_messages
from mock_interview_coach.agents._common import compact_history, load_prompt
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.llm import LLMConfig, chat_text

COACH_SYSTEM = load_prompt("coach")


def build_messages(
    role: str,
    state: ConversationState,
    *,
    summary: dict[str, Any],
    history_limit: int | None = None,
) -> list[dict]:
    context = {
        "role": role,
        "seniority": state.config.seniority,
        "persona": state.persona_for("coach"),
        "summary": summary,
        "transcript": compact_history(state, include_evaluations=True, limit=history_limit),
    }
    return _build_messages(COACH_SYSTEM, context)


def run(
    role: str,
    state: ConversationState,
    *,
    summary: dict[str, Any],
    history_limit: int | None = None,
    config: LLMConfig | None = None,
) -> str:
    return chat_text(
        build_messages(role, state, summary=summary, history_limit=history_limit),
        config=config,
        max_tokens=2048,
    )
