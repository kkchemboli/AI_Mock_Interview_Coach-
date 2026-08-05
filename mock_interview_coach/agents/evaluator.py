"""Evaluator agent: scores one answer across five dimensions.

Strict structured output via EVALUATION_SCHEMA, then deterministic
normalization: dimension scores are clamped to 1-5 and `overall` is recomputed
from the dimension mean so downstream trend math stays exact.
"""

from typing import Any

from mock_interview_coach.agents._common import build_messages as _build_messages
from mock_interview_coach.agents._common import load_prompt, recent_evaluations
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.llm import LLMConfig, chat_json
from mock_interview_coach.utils.parser import DIMENSIONS, EVALUATION_SCHEMA, clamp_score, compute_overall

EVALUATOR_SYSTEM = load_prompt("evaluator")


def build_messages(
    role: str,
    state: ConversationState,
    *,
    question: dict[str, Any],
    answer_text: str,
) -> list[dict]:
    context = {
        "role": role,
        "seniority": state.config.seniority,
        "focus": state.config.focus,
        "persona": state.persona_for("evaluator"),
        "question": question,
        "answer_text": answer_text,
        "recent_evaluations": recent_evaluations(state),
    }
    return _build_messages(EVALUATOR_SYSTEM, context)


def run(
    role: str,
    state: ConversationState,
    *,
    question: dict[str, Any],
    answer_text: str,
    config: LLMConfig | None = None,
) -> dict[str, Any]:
    data = chat_json(
        build_messages(role, state, question=question, answer_text=answer_text),
        schema=EVALUATION_SCHEMA,
        config=config,
    )
    dims = {d: clamp_score(data["dimension_scores"].get(d, 3.0)) for d in DIMENSIONS}
    data["dimension_scores"] = dims
    data["overall"] = compute_overall(dims)
    return data
