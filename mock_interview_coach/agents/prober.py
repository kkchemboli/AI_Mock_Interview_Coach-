"""Prober agent: asks one recovery follow-up probe for a messy answer.

Strict structured output via PROBE_SCHEMA. Escalation stage (0/1) comes from
the orchestrator's probe_context and drives the ladder in the prompt.
"""

from typing import Any

from mock_interview_coach.agents._common import build_messages as _build_messages
from mock_interview_coach.agents._common import load_prompt
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.llm import LLMConfig, chat_json
from mock_interview_coach.utils.parser import PROBE_SCHEMA

PROBER_SYSTEM = load_prompt("prober")


def build_messages(
    role: str,
    state: ConversationState,
    *,
    question: dict[str, Any],
    answer_text: str,
    evaluation: dict[str, Any],
    escalation_stage: int,
) -> list[dict]:
    context = {
        "role": role,
        "seniority": state.config.seniority,
        "persona": state.persona_for("prober"),
        "question": question,
        "answer_text": answer_text,
        "evaluation": evaluation,
        "escalation_stage": escalation_stage,
    }
    return _build_messages(PROBER_SYSTEM, context)


def run(
    role: str,
    state: ConversationState,
    *,
    question: dict[str, Any],
    answer_text: str,
    evaluation: dict[str, Any],
    escalation_stage: int,
    config: LLMConfig | None = None,
) -> dict[str, Any]:
    return chat_json(
        build_messages(
            role,
            state,
            question=question,
            answer_text=answer_text,
            evaluation=evaluation,
            escalation_stage=escalation_stage,
        ),
        schema=PROBE_SCHEMA,
        config=config,
    )
