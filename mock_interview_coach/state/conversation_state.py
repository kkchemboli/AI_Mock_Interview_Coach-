"""Conversation state for an interview run.

Pure dataclasses and deterministic logic, no LLM calls: the persona gate state
machine, per-dimension score histories and trend, root-cause counters, probe
escalation limits, and focus-coverage gating all live here so they can be
self-tested without an API key.
"""

import os
from dataclasses import dataclass, field
from typing import Any

from mock_interview_coach.utils.parser import (
    DIMENSIONS,
    FOCUS_AREAS,
    QUESTION_TYPES,
    SENIORITY_BANDS,
    compute_overall,
)

DEFAULT_PERSONA: dict[str, Any] = {
    "persona": {
        "title": "Generalist Interviewer",
        "company_type": "Startup",
        "what_they_optimize_for": ["problem-solving", "communication"],
        "vibe": "Direct, collaborative, focused on fundamentals.",
    },
    "scoring_lens": "Evaluate clarity, correctness, structure, and self-awareness.",
    "difficulty_anchors": {
        "low": "Fundamental knowledge",
        "medium": "Applied problems",
        "high": "Ambiguous trade-offs",
    },
    "topic_areas": ["core principles", "common patterns"],
    "edge_case_style": "Probes with concrete examples.",
}

STATUSES = ("configuring", "ready", "in_progress", "completed")
MAX_CONSECUTIVE_PROBES = 2


class PersonaNotReadyError(RuntimeError):
    pass


@dataclass(frozen=True)
class InterviewConfig:
    focus: str = "mixed"
    seniority: str = "mid"
    min_turns: int = 5
    max_turns: int = 7
    exemplar_batch_size: int = 3
    difficulty: float = 5.0

    def __post_init__(self) -> None:
        if self.focus not in FOCUS_AREAS:
            raise ValueError(f"invalid focus: {self.focus!r}")
        if self.seniority not in SENIORITY_BANDS:
            raise ValueError(f"invalid seniority: {self.seniority!r}")
        if not (1 <= self.min_turns <= self.max_turns):
            raise ValueError("min_turns must be >= 1 and <= max_turns")
        if self.exemplar_batch_size < 1:
            raise ValueError("exemplar_batch_size must be >= 1")
        if not (1.0 <= self.difficulty <= 10.0):
            raise ValueError("difficulty must be within 1.0 and 10.0")

    @classmethod
    def from_env(
        cls,
        focus: str = "mixed",
        seniority: str = "mid",
        difficulty: float = 5.0,
    ) -> "InterviewConfig":
        return cls(
            focus=focus,
            seniority=seniority,
            min_turns=int(os.getenv("MIN_TURNS", "5")),
            max_turns=int(os.getenv("MAX_TURNS", "7")),
            exemplar_batch_size=int(os.getenv("EXEMPLAR_BATCH_SIZE", "3")),
            difficulty=difficulty,
        )


@dataclass
class Turn:
    turn_index: int
    question: dict[str, Any]
    answers: list[dict[str, Any]] = field(default_factory=list)

    @property
    def last_answer(self) -> dict[str, Any] | None:
        return self.answers[-1] if self.answers else None


def plan_question_types(focus: str, max_turns: int) -> list[str]:
    """Deterministic type plan. Mixed focus guarantees >=1 behavioral +
    technical + case across the run."""
    if focus not in QUESTION_TYPES:
        if focus != "mixed":
            raise ValueError(f"invalid focus: {focus!r}")
    if focus in QUESTION_TYPES:
        return [focus] * max_turns
    if max_turns < 3:
        return [QUESTION_TYPES[i % 3] for i in range(max_turns)]
    return [QUESTION_TYPES[i % 3] for i in range(max_turns - 3)] + list(QUESTION_TYPES)


class ConversationState:
    """Mutable per-run state. Status: configuring -> ready -> in_progress -> completed."""

    def __init__(self, config: InterviewConfig) -> None:
        self.config = config
        self.persona: dict[str, Any] | None = None
        self.status = "configuring"
        self.turns: list[Turn] = []
        self.dim_histories: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
        self.scores_over_time: list[float] = []
        self.covered_types: dict[str, int] = {t: 0 for t in QUESTION_TYPES}
        self.root_cause_counts: dict[str, int] = {}
        self.consecutive_probes = 0

    @property
    def current_turn(self) -> Turn | None:
        return self.turns[-1] if self.turns else None

    @property
    def is_messy(self) -> bool:
        last = self.current_turn.last_answer if self.current_turn else None
        if last is None or last["evaluation"] is None:
            return False
        return last["evaluation"].get("response_type") in ("vague", "off_topic", "i_dont_know", "short")

    def set_persona(self, persona: dict[str, Any]) -> None:
        if self.status not in ("configuring", "ready"):
            raise ValueError(f"cannot set persona in status {self.status!r}")
        self.persona = persona
        if self.status == "configuring":
            self.status = "ready"

    def start(self, allow_default: bool = False) -> None:
        if self.status not in ("ready", "configuring"):
            raise ValueError(f"cannot start interview from status {self.status!r}")
        if self.persona is None:
            if allow_default:
                self.persona = DEFAULT_PERSONA
            else:
                raise PersonaNotReadyError("no persona set; call set_persona() first")
        self.status = "in_progress"

    def complete(self) -> None:
        if self.status != "in_progress":
            raise ValueError(f"cannot complete interview from status {self.status!r}")
        self.status = "completed"

    def start_turn(self, question: dict[str, Any]) -> None:
        if self.status != "in_progress":
            raise ValueError(f"cannot start a turn in status {self.status!r}")
        qtype = question.get("question_type")
        if qtype not in QUESTION_TYPES:
            raise ValueError(f"invalid question_type: {qtype!r}")
        self.turns.append(Turn(turn_index=len(self.turns) + 1, question=question))
        self.covered_types[qtype] = self.covered_types.get(qtype, 0) + 1
        self.consecutive_probes = 0

    def record_answer(self, answer_text: str, probe: dict[str, Any] | None = None) -> None:
        if self.current_turn is None:
            raise ValueError("no active turn; call start_turn() first")
        self.current_turn.answers.append(
            {"answer_text": answer_text, "probe": probe, "evaluation": None}
        )
        if probe is not None:
            self.consecutive_probes += 1

    def record_evaluation(self, evaluation: dict[str, Any]) -> None:
        last = self.current_turn.last_answer if self.current_turn else None
        if last is None:
            raise ValueError("no answer to evaluate")
        last["evaluation"] = evaluation
        dims = evaluation.get("dimension_scores", {})
        for d in DIMENSIONS:
            self.dim_histories[d].append(float(dims.get(d, 1.0)))
        self.scores_over_time.append(float(evaluation.get("overall", compute_overall(dims))))
        root_cause = evaluation.get("suspected_root_cause")
        if root_cause and root_cause != "none":
            self.root_cause_counts[root_cause] = self.root_cause_counts.get(root_cause, 0) + 1
        if evaluation.get("response_type") == "substantive":
            self.consecutive_probes = 0

    def required_types(self) -> set[str]:
        if self.config.focus == "mixed":
            return set(QUESTION_TYPES)
        return {self.config.focus}

    def uncovered_required(self) -> list[str]:
        required = self.required_types()
        return [t for t in QUESTION_TYPES if t in required and self.covered_types.get(t, 0) == 0]

    def can_follow_up(self) -> bool:
        remaining_new = self.config.max_turns - len(self.turns)
        return remaining_new >= len(self.uncovered_required())

    def probe_allowed(self) -> bool:
        return self.consecutive_probes < MAX_CONSECUTIVE_PROBES and self.can_follow_up()

    def next_question_type(self) -> str:
        required = self.required_types()
        candidates = [t for t in QUESTION_TYPES if t in required]
        return min(candidates, key=lambda t: (self.covered_types.get(t, 0), QUESTION_TYPES.index(t)))

    def trend(self, threshold: float = 0.25) -> str:
        scores = self.scores_over_time
        if len(scores) < 2:
            return "flat"
        mid = len(scores) // 2
        first = sum(scores[:mid]) / mid
        second = sum(scores[mid:]) / (len(scores) - mid)
        diff = second - first
        if diff >= threshold:
            return "improving"
        if diff <= -threshold:
            return "declining"
        return "flat"

    def dimension_averages(self) -> dict[str, float]:
        return {
            d: (sum(vals) / len(vals) if vals else 0.0)
            for d, vals in self.dim_histories.items()
        }

    def persona_for(self, agent: str) -> dict[str, Any] | None:
        if self.persona is None:
            return None
        if agent == "interviewer":
            return {
                "vibe": self.persona["persona"]["vibe"],
                "edge_case_style": self.persona["edge_case_style"],
            }
        if agent == "prober":
            return {
                "vibe": self.persona["persona"]["vibe"],
                "edge_case_style": self.persona["edge_case_style"],
            }
        if agent == "evaluator":
            return {
                "scoring_lens": self.persona["scoring_lens"],
                "difficulty_anchors": self.persona["difficulty_anchors"],
            }
        if agent == "coach":
            return {
                "scoring_lens": self.persona["scoring_lens"],
                "topic_areas": self.persona["topic_areas"],
            }
        return None
