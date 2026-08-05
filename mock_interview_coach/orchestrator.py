"""Deterministic interview orchestrator.

Decides the next step after every candidate answer. No LLM calls: policy lives
here so the flow is reproducible and explainable. Decision priority:

    end -> triage (messy response) -> weak+declining -> weak -> strong -> moderate

The returned `Decision` drives the runtime loop: ask a recovery probe (Prober),
start a new question (Interviewer, possibly eased), or end the interview.
"""

from dataclasses import dataclass
from typing import Any

from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.parser import QUESTION_TYPES

STRONG_THRESHOLD = 4.0
WEAK_THRESHOLD = 3.0
ACTIONS = ("follow_up_probe", "new_topic", "ease_off", "end_interview")


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    probe: dict[str, Any] | None = None
    next_question_type: str | None = None
    difficulty_delta: int = 0
    probe_context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"invalid action: {self.action!r}")
        if self.next_question_type is not None and self.next_question_type not in QUESTION_TYPES:
            raise ValueError(f"invalid next_question_type: {self.next_question_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "probe": self.probe,
            "next_question_type": self.next_question_type,
            "difficulty_delta": self.difficulty_delta,
        }


def _last_overall(state: ConversationState) -> float | None:
    return state.scores_over_time[-1] if state.scores_over_time else None


def should_end(state: ConversationState) -> bool:
    if len(state.turns) >= state.config.max_turns:
        return True
    last = _last_overall(state)
    if (
        len(state.turns) >= state.config.min_turns
        and not state.uncovered_required()
        and last is not None
        and last >= STRONG_THRESHOLD
        and state.trend() != "declining"
    ):
        return True
    return False


def decide(state: ConversationState) -> Decision:
    if should_end(state):
        reason = (
            "max_turns"
            if len(state.turns) >= state.config.max_turns
            else "strong_finish"
        )
        return Decision(action="end_interview", reason=reason)

    if state.is_messy:
        if state.probe_allowed():
            return Decision(
                action="follow_up_probe",
                reason="messy_response",
                probe_context={"escalation_stage": state.consecutive_probes},
            )
        return Decision(
            action="new_topic",
            reason="messy_response_exhausted",
            next_question_type=state.next_question_type(),
            difficulty_delta=-1,
        )

    last = _last_overall(state)
    if last is None:
        return Decision(
            action="new_topic",
            reason="solid_moderate",
            next_question_type=state.next_question_type(),
            difficulty_delta=0,
        )

    trend = state.trend()
    if last < WEAK_THRESHOLD:
        if trend == "declining":
            return Decision(
                action="ease_off",
                reason="weak_declining",
                next_question_type=state.next_question_type(),
                difficulty_delta=-1,
            )
        return Decision(
            action="new_topic",
            reason="weak_stabilizing",
            next_question_type=state.next_question_type(),
            difficulty_delta=-1,
        )

    if last >= STRONG_THRESHOLD:
        return Decision(
            action="new_topic",
            reason="strong_performance",
            next_question_type=state.next_question_type(),
            difficulty_delta=1,
        )

    return Decision(
        action="new_topic",
        reason="solid_moderate",
        next_question_type=state.next_question_type(),
        difficulty_delta=0,
    )
