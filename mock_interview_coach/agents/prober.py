"""Prober agent: asks one recovery follow-up probe for a messy answer.

Strict structured output via PROBE_SCHEMA. Escalation stage (0/1) comes from
the orchestrator's probe_context and drives the ladder in the prompt.
"""

from typing import Any

from mock_interview_coach.agents._common import make_agent
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import PROBE_SCHEMA


def _build_context(
    role: str,
    state: ConversationState,
    *,
    question: dict[str, Any],
    answer_text: str,
    evaluation: dict[str, Any],
    escalation_stage: int,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "role": role,
        "seniority": state.config.seniority,
        "persona": state.persona_for("prober"),
        "question": question,
        "answer_text": answer_text,
        "evaluation": evaluation,
        "escalation_stage": escalation_stage,
    }


build_messages, run = make_agent("prober", _build_context, schema=PROBE_SCHEMA)
