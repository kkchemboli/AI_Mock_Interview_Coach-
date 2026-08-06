"""Evaluator agent: scores one answer across five dimensions.

Strict structured output via EVALUATION_SCHEMA with integer 1-5 ratings and a
per-dimension `score_rationale` that quotes evidence from the active answer.
The deterministic rubric (`analysis.rubric`) then clamps the ratings, applies
the response-type caps, and computes `overall`. Configured for low variance
(temperature 0, no model fallback) and with a safe failure path: if the LLM
call cannot produce a valid evaluation, a neutral evaluation marked
`validated: false` is returned so the interview continues and the report flags
it.
"""

import re
from typing import Any

from mock_interview_coach.agents._common import (
    _bounded_answer,
    _bounded_question,
    _labeled,
    make_agent,
)
from mock_interview_coach.analysis.rubric import apply_rubric
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import (
    DIMENSIONS,
    EVALUATION_SCHEMA,
    RESPONSE_TYPES,
)
from mock_interview_coach.utils.validation import enum_allowed, nonempty

_NEUTRAL_EVALUATION: dict[str, Any] = {
    "dimension_scores": {d: 3 for d in DIMENSIONS},
    "score_rationale": {d: "" for d in DIMENSIONS},
    "overall": 3.0,
    "strengths": ["The answer was received."],
    "gaps": ["The evaluation could not be completed in this session."],
    "suspected_root_cause": "insufficient-specificity",
    "response_type": "substantive",
    "interviewer_note": "This answer could not be scored.",
    "caps_applied": [],
}


def _build_context(
    role: str,
    state: ConversationState,
    *,
    question: dict[str, Any],
    answer_text: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "trusted_task": {
            "action": "evaluate_answer",
            "seniority": state.config.seniority,
            "focus": state.config.focus,
        },
        "untrusted_persona": _labeled(state.persona_for("evaluator"), "persona_llm"),
        "untrusted_question": _labeled(_bounded_question(question), "interviewer_llm"),
        "untrusted_candidate_answer": _bounded_answer(answer_text, question),
    }


def _postprocess(data: dict[str, Any]) -> dict[str, Any]:
    rubric = apply_rubric(data)
    data["dimension_scores"] = rubric["dimension_scores"]
    data["overall"] = rubric["overall"]
    data["caps_applied"] = rubric["caps_applied"]
    return data


def _validate(data: dict[str, Any], request: dict[str, Any]) -> str | None:
    dims = data.get("dimension_scores", {})
    if not all(
        isinstance(dims.get(d), int) and 1 <= dims[d] <= 5 for d in DIMENSIONS
    ):
        return "dimension_scores must be integers in 1..5"
    rationale = data.get("score_rationale", {})
    for d in DIMENSIONS:
        problem = nonempty(rationale.get(d), f"score_rationale.{d}")
        if problem is not None:
            return problem
        if not _has_grounded_quote(rationale[d], request.get("answer_text", "")):
            return f"score_rationale.{d} must quote candidate-answer evidence"
    return enum_allowed(data.get("response_type"), RESPONSE_TYPES, "response_type")


def _has_grounded_quote(rationale: str, answer: str) -> bool:
    """Ensure a score rationale cites the candidate answer, not the prompt.

    An ellipsis may join two exact fragments, provided both fragments occur in
    order. This mirrors the eval harness and permits concise citations without
    accepting an invented paraphrase as evidence.
    """
    answer_text = " ".join(str(answer).lower().split())
    quotes = re.findall(r'["“]([^"”]+)["”]', str(rationale))
    for quote in quotes:
        cursor = 0
        fragments = [" ".join(item.lower().split()) for item in re.split(r"(?:\.\.\.|…)", quote)]
        fragments = [item for item in fragments if item]
        if not fragments:
            continue
        for fragment in fragments:
            index = answer_text.find(fragment, cursor)
            if index < 0:
                break
            cursor = index + len(fragment)
        else:
            return True
    return False


def _repair_hint(data: dict[str, Any], request: dict[str, Any]) -> str:
    return (
        "Your evaluation was rejected: every dimension must have an integer "
        "score 1-5, and score_rationale must quote the exact words or numbers "
        "from the candidate's answer that justify each score. Do not quote the "
        "question. Put at least one candidate-answer quote in double quotes in "
        "every rationale, then re-emit the evaluation."
    )


def _fallback(request: dict[str, Any]) -> dict[str, Any]:
    return dict(_NEUTRAL_EVALUATION)


build_messages, run = make_agent(
    "evaluator",
    _build_context,
    schema=EVALUATION_SCHEMA,
    temperature=0.0,
    postprocess=_postprocess,
    validator=_validate,
    repair_hint=_repair_hint,
    fallback=_fallback,
    on_error=_fallback,
    allow_fallback=False,
)
