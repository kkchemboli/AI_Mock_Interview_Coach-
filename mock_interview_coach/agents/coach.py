"""Coach agent: writes the markdown debrief.

The only agent that emits free-form prose (not JSON). Uses the deterministic
`summary` from analysis.root_cause as its structured input.
"""

from typing import Any

from mock_interview_coach.agents._common import compact_history, make_agent
from mock_interview_coach.state.conversation_state import ConversationState


def _build_context(
    role: str,
    state: ConversationState,
    *,
    summary: dict[str, Any],
    history_limit: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "role": role,
        "seniority": state.config.seniority,
        "persona": state.persona_for("coach"),
        "summary": summary,
        "transcript": compact_history(state, include_evaluations=True, limit=history_limit),
    }


build_messages, run = make_agent(
    "coach", _build_context, temperature=0.4, max_tokens=2048
)
