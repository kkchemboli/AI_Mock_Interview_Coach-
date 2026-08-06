"""Deterministic root-cause diagnosis and drill recommendation.

The Evaluator reports a `suspected_root_cause` per answer (LLM judgement). This
module cross-checks that signal with a deterministic signature over the
dimension scores, resolves a final root cause for the whole run, and maps it to
one targeted drill for the Coach. No LLM calls.
"""

from typing import Any

from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import RESPONSE_TYPES, ROOT_CAUSES

_CAUSE_SIGNATURES: dict[str, dict[str, Any]] = {
    "inability-to-identify-question-core": {
        "weights": {"relevance": -2.0, "structure": 0.5, "substance": -0.5},
        "response_types": ["off_topic"],
    },
    "reflexive-we": {
        "weights": {"credibility": -2.0, "differentiation": -1.5, "substance": 0.5},
        "response_types": [],
    },
    "conflict-avoidance": {
        "weights": {"credibility": -1.5, "structure": 1.0, "differentiation": -0.5},
        "response_types": ["vague"],
    },
    "status-anxiety": {
        "weights": {"substance": -1.5, "structure": 1.0, "credibility": 0.5},
        "response_types": ["short", "i_dont_know"],
    },
    "narrative-hoarding": {
        "weights": {"structure": -2.0, "substance": 0.5, "differentiation": -0.5},
        "response_types": [],
    },
    "fear-of-being-wrong": {
        "weights": {"substance": -1.5, "credibility": -1.0, "differentiation": 0.5},
        "response_types": ["i_dont_know", "short"],
    },
    "insufficient-specificity": {
        "weights": {"credibility": -1.0, "differentiation": -1.0, "substance": -0.5},
        "response_types": ["vague", "short"],
    },
}

# Psychological diagnoses (status-anxiety, fear-of-being-wrong) require
# recurrence (>= 2 flagged answers) before they are assigned; a single
# observation resolves to the observable label instead, so the report never
# makes an unsupported inference about the candidate's internal state.
_PSYCHOLOGICAL_CAUSES = ("status-anxiety", "fear-of-being-wrong")
_PSYCHOLOGICAL_THRESHOLD = 2

ROOT_CAUSE_DRILLS: dict[str, dict[str, Any]] = {
    "inability-to-identify-question-core": {
        "label": "Restate-before-answer",
        "target_dimension": "relevance",
        "exercise": (
            "Before answering, restate the question in your own words and name the "
            "core thing the interviewer is asking about (the decision, the evidence, "
            "or the trade-off) in one sentence."
        ),
        "coaching_note": (
            "Off-topic answers usually mean the question was never actually parsed. "
            "The restatement forces a check before the story starts."
        ),
    },
    "reflexive-we": {
        "label": "I-claim audit",
        "target_dimension": "credibility",
        "exercise": (
            "Re-answer your last three stories swapping every 'we/our team' for 'I' "
            "plus one thing you personally decided, did, or owned, with a metric."
        ),
        "coaching_note": (
            "Generic 'we' language hides ownership. Interviewers can't credit what "
            "they can't attribute to you."
        ),
    },
    "conflict-avoidance": {
        "label": "Candid-tradeoff",
        "target_dimension": "credibility",
        "exercise": (
            "Practice a three-sentence stance: state the trade-off, state your call, "
            "state what it cost — even when the call was unpopular."
        ),
        "coaching_note": (
            "Polished, evasive answers read as unwillingness to make decisions. A "
            "clean admission of cost builds more trust than a smooth non-answer."
        ),
    },
    "status-anxiety": {
        "label": "Ground-truth anchoring",
        "target_dimension": "substance",
        "exercise": (
            "Lead with what you know ('Here's what I know, and here's how I'd close "
            "the gap') before hedging or asking for hints."
        ),
        "coaching_note": (
            "Hedging and hint-seeking bury the substance you do have. Answer first, "
            "caveat second."
        ),
    },
    "narrative-hoarding": {
        "label": "SCQA compression",
        "target_dimension": "structure",
        "exercise": (
            "Answer in Situation → Complication → Question → Answer, capped at two "
            "minutes, and cut the third example every time."
        ),
        "coaching_note": (
            "Rich detail without a spine buries the point. A compressed, capped "
            "answer lands harder than a long one."
        ),
    },
    "fear-of-being-wrong": {
        "label": "Commit-first",
        "target_dimension": "substance",
        "exercise": (
            "Give a concrete answer or estimate first — no hand-raising for "
            "permission — then add caveats in a separate sentence."
        ),
        "coaching_note": (
            "Withholding the answer to avoid being wrong reads as not knowing. "
            "Committed estimates are scored on reasoning, not correctness."
        ),
    },
    "none": {
        "label": "Strengthen the strongest",
        "target_dimension": "differentiation",
        "exercise": (
            "For each strong answer, add one line on what you would have done "
            "differently or what makes your approach distinct."
        ),
        "coaching_note": (
            "No recurring weakness found. The highest-leverage move is making good "
            "answers memorable."
        ),
    },
    "insufficient-specificity": {
        "label": "Specificity pass",
        "target_dimension": "credibility",
        "exercise": (
            "In your next three answers, include one concrete example, one "
            "number or named artifact, and one first-person action you took."
        ),
        "coaching_note": (
            "The weakness did not repeat a single pattern, so the evidence "
            "points to under-specified answers rather than one psychological "
            "cause. Grounding claims with specifics is the fix."
        ),
    },
}


def _match_score(cause: str, dims: dict, response_type: str) -> float:
    score = 0.0
    for dim, weight in _CAUSE_SIGNATURES[cause]["weights"].items():
        value = float(dims.get(dim, 3.0))
        score += weight * (value - 3.0)
    if response_type in _CAUSE_SIGNATURES[cause]["response_types"]:
        score += 2.0
    return round(score, 2)


def suggest_root_cause(evaluation: dict[str, Any]) -> str:
    """Deterministic best guess from one evaluation. Returns a ROOT_CAUSES value
    or "none" when no signature clearly fits."""
    dims = evaluation.get("dimension_scores", {})
    response_type = evaluation.get("response_type", "substantive")
    scores = {rc: _match_score(rc, dims, response_type) for rc in ROOT_CAUSES}
    best = max(ROOT_CAUSES, key=lambda rc: (scores[rc], -ROOT_CAUSES.index(rc)))
    return best if scores[best] > 0.0 else "none"


def _required_count(cause: str) -> int:
    """Recurrence requirement: psychological causes need >= 2 flagged answers."""
    return _PSYCHOLOGICAL_THRESHOLD if cause in _PSYCHOLOGICAL_CAUSES else 1


def resolve_root_cause(state: ConversationState) -> str:
    """Combine the Evaluator's inline root causes across the run; fall back to
    the deterministic signature over the averaged profile when none were given.
    Psychological causes only resolve once they recur enough (see
    `_PSYCHOLOGICAL_CAUSES`); otherwise the observable label is returned."""
    counts = {rc: n for rc, n in state.root_cause_counts.items() if n > 0}
    if counts:
        eligible = {
            rc: n for rc, n in counts.items() if n >= _required_count(rc)
        }
        if eligible:
            return max(
                ROOT_CAUSES,
                key=lambda rc: (eligible.get(rc, 0), -ROOT_CAUSES.index(rc)),
            )
        return "insufficient-specificity"
    profile = {
        d: (sum(vals) / len(vals) if vals else 3.0)
        for d, vals in state.dim_histories.items()
    }
    response_types = [
        answer["evaluation"]["response_type"]
        for turn in state.turns
        for answer in turn.answers
        if answer["evaluation"]
    ]
    majority = (
        max(RESPONSE_TYPES, key=response_types.count)
        if response_types
        else "substantive"
    )
    best = suggest_root_cause({"dimension_scores": profile, "response_type": majority})
    if best in _PSYCHOLOGICAL_CAUSES:
        return "insufficient-specificity"
    return best


def drill_for(root_cause: str) -> dict[str, Any]:
    return ROOT_CAUSE_DRILLS.get(root_cause, ROOT_CAUSE_DRILLS["none"])


def coach_summary(state: ConversationState) -> dict[str, Any]:
    root_cause = resolve_root_cause(state)
    scores = state.scores_over_time
    return {
        "root_cause": root_cause,
        "drill": drill_for(root_cause),
        "dimension_averages": state.dimension_averages(),
        "trend": state.trend(),
        "overall_average": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "turns": len(state.turns),
    }
