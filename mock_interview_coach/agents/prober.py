"""Prober agent: asks one recovery follow-up probe for a messy answer.

Strict structured output via PROBE_SCHEMA. Escalation stage (0/1) comes from
the orchestrator's probe_context and drives the ladder in the prompt. The stage
is enforced deterministically at validation time: the prompt keeps its soft
"prefer" guidance, but an off-stage probe_type is repaired to the nearest
allowed value for the stage. If the LLM call fails, the probe is skipped
(`None`) and the runtime moves on.
"""

from typing import Any

from mock_interview_coach.agents._common import (
    _LIMITS,
    _bounded,
    _bounded_evaluation,
    _bounded_question,
    _labeled,
    make_agent,
)
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import PROBE_SCHEMA
from mock_interview_coach.utils.validation import nonempty

_ALLOWED_FOR_STAGE: dict[int, tuple[str, ...]] = {
    0: ("deepen", "redirect"),
    1: ("scaffold", "hint"),
}


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
        "trusted_task": {
            "action": "ask_follow_up_probe",
            "seniority": state.config.seniority,
            "escalation_stage": escalation_stage,
        },
        "untrusted_persona": _labeled(state.persona_for("prober"), "persona_llm"),
        "untrusted_question": _labeled(_bounded_question(question), "interviewer_llm"),
        "untrusted_candidate_answer": _bounded(answer_text, "candidate_submission", _LIMITS["answer"]),
        "untrusted_evaluation": _labeled(_bounded_evaluation(evaluation), "evaluator_llm"),
    }


def _allowed_for(request: dict[str, Any]) -> tuple[str, ...]:
    stage = int(request.get("escalation_stage", 0))
    return _ALLOWED_FOR_STAGE.get(stage, _ALLOWED_FOR_STAGE[0])


def _validate(data: dict[str, Any], request: dict[str, Any]) -> str | None:
    if data.get("probe_type") not in _allowed_for(request):
        return (
            f"probe_type {data.get('probe_type')!r} is not allowed at "
            f"escalation_stage {request.get('escalation_stage', 0)}"
        )
    return nonempty(data.get("question_text"), "question_text")


def _repair(data: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    if data.get("probe_type") not in _allowed_for(request):
        stage = int(request.get("escalation_stage", 0))
        data["probe_type"] = "deepen" if stage == 0 else "scaffold"
    return data


def _fallback(request: dict[str, Any]) -> None:
    return None


build_messages, run = make_agent(
    "prober",
    _build_context,
    schema=PROBE_SCHEMA,
    validator=_validate,
    repair=_repair,
    fallback=_fallback,
    on_error=_fallback,
)
