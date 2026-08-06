"""Evaluator agent: scores one answer across five dimensions.

Strict structured output via EVALUATION_SCHEMA, then deterministic
normalization: dimension scores are clamped to 1-5 and `overall` is recomputed
from the dimension mean so downstream trend math stays exact.
"""

from typing import Any

from mock_interview_coach.agents._common import make_agent, recent_evaluations
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import (
    DIMENSIONS,
    EVALUATION_SCHEMA,
    clamp_score,
    compute_overall,
)


def _build_context(
    role: str,
    state: ConversationState,
    *,
    question: dict[str, Any],
    answer_text: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "role": role,
        "seniority": state.config.seniority,
        "focus": state.config.focus,
        "persona": state.persona_for("evaluator"),
        "question": question,
        "answer_text": answer_text,
        "recent_evaluations": recent_evaluations(state),
    }


def _postprocess(data: dict[str, Any]) -> dict[str, Any]:
    dims = {d: clamp_score(data["dimension_scores"].get(d, 3.0)) for d in DIMENSIONS}
    data["dimension_scores"] = dims
    data["overall"] = compute_overall(dims)
    return data


build_messages, run = make_agent(
    "evaluator", _build_context, schema=EVALUATION_SCHEMA, postprocess=_postprocess
)
