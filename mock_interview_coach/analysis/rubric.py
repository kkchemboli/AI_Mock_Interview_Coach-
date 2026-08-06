"""Deterministic evaluator rubric (Phase 3).

The Evaluator LLM (temperature 0) emits, per dimension, an integer rating on the
1-5 scale plus a `score_rationale` quoting evidence from the active answer, and
a `response_type`. This module turns that judgement into the *final* scores: it
clamps ratings to integers, applies the response-type caps, and computes the
`overall` as the mean of the five dimension scores (rounded to one decimal). No
LLM calls.

The caps are strict by design (product decision): a "vague" response_type caps
credibility and differentiation at 3 regardless of how good the quoted evidence
reads, because the type classification is itself part of the evidence.

Response-type caps:
- off_topic       -> relevance is forced to 1.
- i_dont_know     -> substance <= 1, differentiation <= 2.
- short           -> substance <= 2.
- vague           -> credibility <= 3, differentiation <= 3.
"""

from typing import Any

from mock_interview_coach.utils.parser import DIMENSIONS, RATING_SCALE

_RESPONSE_TYPE_CAPS: dict[str, dict[str, int]] = {
    "off_topic": {"relevance": 1},
    "i_dont_know": {"substance": 1, "differentiation": 2},
    "short": {"substance": 2},
    "vague": {"credibility": 3, "differentiation": 3},
}


def _clamp_rating(value: Any) -> int:
    try:
        return max(RATING_SCALE[0], min(RATING_SCALE[-1], int(round(float(value)))))
    except (TypeError, ValueError):
        return RATING_SCALE[2]


def _caps_for(response_type: str) -> dict[str, int]:
    return _RESPONSE_TYPE_CAPS.get(response_type, {})


def apply_rubric(rationale: dict[str, Any]) -> dict[str, Any]:
    """Finalize an LLM evaluation: clamp ratings, apply response-type caps, and
    compute the overall. Returns a dict with `dimension_scores` (integers),
    `overall`, and `caps_applied` (list of `dim:cap` pairs that bit).
    """
    raw = rationale.get("dimension_scores", {})
    response_type = rationale.get("response_type", "substantive")
    dims = {d: _clamp_rating(raw.get(d)) for d in DIMENSIONS}
    caps_applied: list[str] = []
    for dim, cap in _caps_for(response_type).items():
        if dim in dims and dims[dim] > cap:
            dims[dim] = cap
            caps_applied.append(f"{dim}:{cap}")
    return {
        "dimension_scores": dims,
        "overall": round(sum(dims.values()) / len(dims), 1),
        "caps_applied": caps_applied,
    }
